"""리뷰 캡처 픽셀 검증.

엔진은 지금까지 recipe에 적힌 숫자를 그대로 믿었다. 그래서 밑줄 좌표가 엉뚱한 줄을
관통해도, 마스킹했다고 선언만 하고 실제로 가리지 않아도 전부 통과했다.

여기서는 실제 이미지를 열어 두 가지를 확인한다.

* 밑줄이 글자 줄 아래 여백에 놓였는가, 글자를 가로지르지 않는가
* 마스킹본이 원본과 선언한 영역에서만 다르고, 그 영역이 실제로 가려졌는가

의존성은 Pillow뿐이다. numpy는 이 저장소의 선언된 의존성이 아니므로 쓰지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from PIL import Image


# 리뷰 캡처는 흰 배경에 짙은 본문이다. 링크 파랑과 별점 빨강도 이 아래로 떨어진다.
DARK_LUMA_THRESHOLD = 140
# 한 행이 글자로 인정받으려면 가로폭의 이 비율만큼 잉크가 있어야 한다.
MIN_LINE_INK_RATIO = 0.008
# 안티에일리어싱 한 줄이 글자 줄로 오인되지 않도록 최소 높이를 둔다.
MIN_LINE_HEIGHT_PX = 4
# Korean glyphs can leave a one-row white gap between the main body and a
# lower stroke.  Treating that stroke as another review line makes visually
# correct consecutive underlines fail while a crossing coordinate can pass.
MAX_INTRA_LINE_ROW_GAP_RATIO = 0.0025
MAX_INTRA_LINE_ROW_GAP_PX_CAP = 4
# 줄이 이보다 적게 검출되면 캡처 구조를 신뢰할 수 없으므로 픽셀 판정을 하지 않는다.
MIN_DETECTED_LINES = 3
# 밑줄은 글자 바로 아래에 붙는다. 한 줄 간격의 이 비율 안에 있어야 그 줄의 밑줄이다.
UNDERLINE_ATTACH_RATIO = 0.9
# 밑줄이 글자 띠 아래끝에 살짝 걸치는 것은 정상이다. 띠 높이의 이 비율만큼은
# 아래쪽을 밑줄 자리로 인정하고, 그보다 위로 파고든 것만 `관통`으로 본다.
UNDERLINE_BASELINE_TOLERANCE_RATIO = 0.25
# 채널 합이 이보다 크게 달라야 사람 눈에 보이는 변경으로 본다.
# JPEG를 다시 저장하면 이미지 전체 픽셀이 조금씩 흔들린다. 실측에서 이 값이 8이면
# 재인코딩 노이즈까지 `변경`으로 잡혀 마스크 영역이 이미지 전체로 번졌고, 24부터
# 실제로 가린 자리로 수렴했다.
PIXEL_CHANGE_THRESHOLD = 24
# 마스킹은 원본 디테일을 최소 이만큼 없애야 한다. 절대 임계값은 쓸 수 없다.
# 어두운 사진의 한 귀퉁이는 가리기 전에도 디테일이 낮기 때문이다.
# 실측: 검은 블록 100% 감소, 실제 블러 79% 감소, 밝기만 살짝 건드리면 0%에 가깝다.
MIN_MASKED_DETAIL_REDUCTION = 0.60


@dataclass(frozen=True)
class TextLine:
    """캡처에서 검출한 글자 한 줄."""

    top_pct: float
    bottom_pct: float
    ink_left_pct: float
    ink_right_pct: float


def _load_grayscale(path: str | Path) -> Image.Image:
    with Image.open(path) as handle:
        return handle.convert("L")


def detect_text_lines(path: str | Path) -> list[TextLine]:
    """행별 잉크 밀도로 글자 줄의 세로 위치를 찾는다.

    OCR이 아니다. 어떤 글자인지는 모르고 글자가 있는 띠가 어디인지만 안다.
    그것만으로도 `밑줄이 글자를 가로지르는가`는 판정할 수 있다.
    """

    image = _load_grayscale(path)
    width, height = image.size
    if width <= 0 or height <= 0:
        return []

    pixels = image.load()
    min_ink = max(2, int(width * MIN_LINE_INK_RATIO))
    dark_rows: list[bool] = []
    for y in range(height):
        ink = 0
        for x in range(width):
            if pixels[x, y] < DARK_LUMA_THRESHOLD:
                ink += 1
                if ink >= min_ink:
                    break
        dark_rows.append(ink >= min_ink)

    bands: list[tuple[int, int]] = []
    start: int | None = None
    for y, is_dark in enumerate(dark_rows + [False]):
        if is_dark and start is None:
            start = y
        elif not is_dark and start is not None:
            bands.append((start, y))
            start = None

    merged_bands: list[tuple[int, int]] = []
    max_intra_line_gap = min(
        MAX_INTRA_LINE_ROW_GAP_PX_CAP,
        max(1, round(height * MAX_INTRA_LINE_ROW_GAP_RATIO)),
    )
    for top, bottom in bands:
        if merged_bands and top - merged_bands[-1][1] <= max_intra_line_gap:
            merged_bands[-1] = (merged_bands[-1][0], bottom)
        else:
            merged_bands.append((top, bottom))

    lines: list[TextLine] = []
    for top, bottom in merged_bands:
        if bottom - top < MIN_LINE_HEIGHT_PX:
            continue
        left, right = _ink_extent(pixels, width, top, bottom)
        lines.append(
            TextLine(
                top_pct=top / height * 100,
                bottom_pct=bottom / height * 100,
                ink_left_pct=left / width * 100,
                ink_right_pct=right / width * 100,
            )
        )
    return lines


def _ink_extent(pixels: Any, width: int, top: int, bottom: int) -> tuple[int, int]:
    left = width
    right = 0
    for x in range(width):
        for y in range(top, bottom):
            if pixels[x, y] < DARK_LUMA_THRESHOLD:
                left = min(left, x)
                right = max(right, x + 1)
                break
    return (0, width) if left >= right else (left, right)


def verify_underline_segments(
    capture_path: str | Path, segments: Sequence[dict[str, Any]]
) -> list[str]:
    """밑줄 좌표가 실제 글자 줄 아래에 놓였는지 확인한다.

    어떤 글자를 덮는지는 판정하지 않는다. 그것은 `line_text` 계약과 사람 검수가 맡는다.
    여기서는 손으로 찍은 좌표가 만들어내는 눈에 보이는 결함만 잡는다.
    """

    segments = list(segments)
    lines = detect_text_lines(capture_path)
    if len(lines) < MIN_DETECTED_LINES:
        return []

    pitch = _median_line_pitch(lines)
    if pitch <= 0:
        return []

    violations: list[str] = []
    attached: list[int] = []
    for segment in segments:
        try:
            top = float(segment["top_pct"])
        except (KeyError, TypeError, ValueError):
            return ["REVIEW_UNDERLINE_SEGMENT_UNREADABLE"]

        if any(line.top_pct < top < _baseline(line) for line in lines):
            violations.append("REVIEW_UNDERLINE_CROSSES_TEXT")
            continue

        owner = _line_above(lines, top, pitch)
        if owner is None:
            violations.append("REVIEW_UNDERLINE_NOT_UNDER_TEXT")
            continue
        attached.append(owner)

    if len(attached) == len(segments) and len(attached) > 1:
        expected = list(range(attached[0], attached[0] + len(attached)))
        if attached != expected:
            violations.append("REVIEW_UNDERLINE_LINES_NOT_CONSECUTIVE")

    # 같은 코드가 여러 segment에서 나와도 한 번만 보고한다.
    return sorted(set(violations))


def _median_line_pitch(lines: Sequence[TextLine]) -> float:
    gaps = [
        lines[index + 1].top_pct - lines[index].top_pct
        for index in range(len(lines) - 1)
        if lines[index + 1].top_pct > lines[index].top_pct
    ]
    if not gaps:
        return 0.0
    gaps.sort()
    return gaps[len(gaps) // 2]


def _baseline(line: TextLine) -> float:
    """글자 띠에서 밑줄이 놓여도 되는 시작 높이."""
    return line.bottom_pct - (line.bottom_pct - line.top_pct) * UNDERLINE_BASELINE_TOLERANCE_RATIO


def _line_above(lines: Sequence[TextLine], top: float, pitch: float) -> int | None:
    """`top`이 밑줄이라면 어느 줄에 붙은 밑줄인지 돌려준다."""
    best: int | None = None
    for index, line in enumerate(lines):
        if _baseline(line) <= top <= line.bottom_pct + pitch * UNDERLINE_ATTACH_RATIO:
            if best is None or line.bottom_pct > lines[best].bottom_pct:
                best = index
    return best


def verify_sanitized_asset(
    source_path: str | Path,
    sanitized_path: str | Path,
    regions: Iterable[dict[str, Any]],
) -> list[str]:
    """마스킹본이 원본과 선언한 영역에서만 다르고 그 영역이 실제로 가려졌는지 본다."""

    with Image.open(source_path) as handle:
        source = handle.convert("RGB")
    with Image.open(sanitized_path) as handle:
        sanitized = handle.convert("RGB")

    if source.size != sanitized.size:
        return ["SANITIZED_ASSET_GEOMETRY_CHANGED"]

    width, height = source.size
    boxes = [_region_box(region, width, height) for region in regions]
    if not boxes or any(box is None for box in boxes):
        return ["SANITIZED_REGION_INVALID"]

    changed = _changed_pixels(source, sanitized)
    if not changed:
        return ["SANITIZED_ASSET_UNCHANGED"]

    violations: list[str] = []
    if any(not any(_inside(point, box) for box in boxes) for point in changed):
        violations.append("SANITIZED_ASSET_CHANGE_OUTSIDE_REGION")

    for box in boxes:
        touched = [point for point in changed if _inside(point, box)]
        if not touched:
            violations.append("SANITIZED_REGION_NOT_APPLIED")
            continue
        # 선언 영역을 실제 마스크보다 넉넉하게 잡는 것은 흔한 일이므로, 남은 디테일은
        # 영역 전체가 아니라 정말로 덮인 픽셀에서만 잰다.
        before = _detail_on(source, touched)
        after = _detail_on(sanitized, touched)
        if before <= 0:
            continue
        if 1 - after / before < MIN_MASKED_DETAIL_REDUCTION:
            violations.append("SANITIZED_REGION_STILL_LEGIBLE")

    return sorted(set(violations))


def _region_box(region: Any, width: int, height: int) -> tuple[int, int, int, int] | None:
    if not isinstance(region, dict):
        return None
    try:
        left = float(region["left_pct"])
        top = float(region["top_pct"])
        right = left + float(region["width_pct"])
        bottom = top + float(region["height_pct"])
    except (KeyError, TypeError, ValueError):
        return None
    if left < 0 or top < 0 or right > 100.001 or bottom > 100.001 or right <= left or bottom <= top:
        return None
    box = (
        int(left / 100 * width),
        int(top / 100 * height),
        min(width, max(1, int(round(right / 100 * width)))),
        min(height, max(1, int(round(bottom / 100 * height)))),
    )
    return box if box[0] < box[2] and box[1] < box[3] else None


def _changed_pixels(source: Image.Image, sanitized: Image.Image) -> list[tuple[int, int]]:
    width, height = source.size
    origin = source.load()
    result = sanitized.load()
    changed: list[tuple[int, int]] = []
    for y in range(height):
        for x in range(width):
            before = origin[x, y]
            after = result[x, y]
            delta = (
                abs(before[0] - after[0])
                + abs(before[1] - after[1])
                + abs(before[2] - after[2])
            )
            if delta > PIXEL_CHANGE_THRESHOLD:
                changed.append((x, y))
    return changed


def _inside(point: tuple[int, int], box: tuple[int, int, int, int] | None) -> bool:
    if box is None:
        return False
    x, y = point
    return box[0] <= x < box[2] and box[1] <= y < box[3]


def _detail_on(image: Image.Image, points: Sequence[tuple[int, int]]) -> float:
    """바뀐 픽셀들 안에서만 잰 국소 기울기.

    읽을 수 있다는 것은 국소 대비가 있다는 뜻이므로 인접 픽셀 차이로 잰다. 실측에서
    밝기 분포(표준편차)는 블러를 통과시켰다. 흐려도 밝고 어두운 폭은 남기 때문이다.
    반대로 변경 영역의 사각형 전체로 재면 블러처럼 변경분이 흩어진 경우 손대지 않은
    자리까지 섞여 희석된다. 그래서 정확히 바뀐 픽셀만, 이웃도 같은 집합일 때만 센다.
    """
    grayscale = image.convert("L")
    pixels = grayscale.load()
    members = set(points)
    total = 0
    count = 0
    for x, y in points:
        if (x - 1, y) in members:
            total += abs(pixels[x, y] - pixels[x - 1, y])
            count += 1
    return total / count if count else 0.0
