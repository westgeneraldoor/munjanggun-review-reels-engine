from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VISION_ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"


@dataclass(frozen=True)
class FaceBox:
    vertices: tuple[tuple[int, int], ...]
    detection_confidence: float | None = None
    source: str = "fdBoundingPoly"


def _issue(code: str, message: str, *, path: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"code": code, "message": message}
    if path:
        item["path"] = path
    return item


def load_dotenv_if_present(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def gcloud_access_token() -> str | None:
    try:
        completed = subprocess.run(
            ["gcloud", "auth", "application-default", "print-access-token"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    token = completed.stdout.strip()
    return token or None


def image_files(input_dir: Path, *, recursive: bool = False) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    return sorted(
        path
        for path in input_dir.glob(pattern)
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def _box_from_vertices(vertices: tuple[tuple[int, int], ...], width: int, height: int, padding_ratio: float) -> tuple[int, int, int, int]:
    xs = [x for x, _ in vertices]
    ys = [y for _, y in vertices]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    pad_x = max(4, int((right - left) * padding_ratio))
    pad_y = max(4, int((bottom - top) * padding_ratio))
    return (
        max(0, left - pad_x),
        max(0, top - pad_y),
        min(width, right + pad_x),
        min(height, bottom + pad_y),
    )


def mask_faces(
    image: Image.Image,
    faces: list[FaceBox],
    *,
    padding_ratio: float = 0.18,
    blur_radius: int = 34,
) -> Image.Image:
    result = image.convert("RGB").copy()
    for face in faces:
        if not face.vertices:
            continue
        box = _box_from_vertices(face.vertices, result.width, result.height, padding_ratio)
        x1, y1, x2, y2 = box
        if x2 <= x1 or y2 <= y1:
            continue
        crop = result.crop(box).filter(ImageFilter.GaussianBlur(radius=blur_radius))
        mask = Image.new("L", result.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse(box, fill=255)
        mask_crop = mask.crop(box).filter(ImageFilter.GaussianBlur(radius=2))
        result.paste(crop, box, mask_crop)
    return result


def _vision_vertices(poly: dict[str, Any] | None) -> tuple[tuple[int, int], ...]:
    if not isinstance(poly, dict):
        return tuple()
    vertices = []
    for vertex in poly.get("vertices") or []:
        if not isinstance(vertex, dict):
            continue
        vertices.append((int(vertex.get("x", 0)), int(vertex.get("y", 0))))
    return tuple(vertices)


def parse_vision_faces(response: dict[str, Any]) -> list[FaceBox]:
    faces = []
    annotations = response.get("faceAnnotations") or []
    for annotation in annotations:
        if not isinstance(annotation, dict):
            continue
        vertices = _vision_vertices(annotation.get("fdBoundingPoly")) or _vision_vertices(annotation.get("boundingPoly"))
        if not vertices:
            continue
        confidence = annotation.get("detectionConfidence")
        faces.append(
            FaceBox(
                vertices=vertices,
                detection_confidence=float(confidence) if confidence is not None else None,
                source="fdBoundingPoly" if annotation.get("fdBoundingPoly") else "boundingPoly",
            )
        )
    return faces


def parse_gemini_faces(text: str, *, width: int, height: int) -> list[FaceBox]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    data = json.loads(cleaned)
    faces = []
    for item in data.get("faces", []):
        bbox = item.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        ymin, xmin, ymax, xmax = [float(value) for value in bbox]
        # Gemini visual bounding boxes are requested as normalized [ymin, xmin, ymax, xmax] in 0..1000.
        x1 = max(0, min(width, int(round(width * xmin / 1000))))
        x2 = max(0, min(width, int(round(width * xmax / 1000))))
        y1 = max(0, min(height, int(round(height * ymin / 1000))))
        y2 = max(0, min(height, int(round(height * ymax / 1000))))
        if x2 <= x1 or y2 <= y1:
            continue
        faces.append(
            FaceBox(
                vertices=((x1, y1), (x2, y1), (x2, y2), (x1, y2)),
                detection_confidence=None,
                source="gemini_visual_bbox",
            )
        )
    return faces


def _request_gemini_faces(image_path: Path, *, api_key: str, model: str) -> list[FaceBox]:
    from google import genai
    from google.genai import types

    image = Image.open(image_path)
    prompt = (
        "이 이미지는 시공 릴스 소재입니다. 개인정보 보호를 위해 사람 얼굴만 찾아야 합니다.\n"
        "실제 사람 얼굴뿐 아니라 벽에 걸린 가족사진/액자/거울/유리 반사 속 얼굴도 포함하세요.\n"
        "주소, 건물명, 제품, 식물, 가구, 물건은 제외하세요.\n"
        "JSON만 응답하세요. 좌표는 이미지 전체 기준 0~1000 정규화 bbox [ymin, xmin, ymax, xmax] 형식입니다.\n"
        '형식: {"faces":[{"bbox":[0,0,0,0],"reason":"face in framed photo"}]}\n'
        "얼굴이 없으면 {\"faces\":[]} 로 응답하세요."
    )
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=image_path.read_bytes(), mime_type=f"image/{'jpeg' if image_path.suffix.lower() in {'.jpg', '.jpeg'} else 'png'}"),
            prompt,
        ],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return parse_gemini_faces(response.text or '{"faces":[]}', width=image.width, height=image.height)


def _read_precomputed_detections(path: Path) -> dict[str, list[FaceBox]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    by_file: dict[str, list[FaceBox]] = {}
    for item in data.get("images", []):
        filename = item.get("file")
        faces = []
        for face in item.get("faces", []):
            faces.append(
                FaceBox(
                    vertices=tuple((int(x), int(y)) for x, y in face.get("vertices", [])),
                    detection_confidence=face.get("detection_confidence"),
                    source=face.get("source", "precomputed"),
                )
            )
        if filename:
            by_file[str(filename)] = faces
    return by_file


def _request_google_vision(image_path: Path, *, api_key: str | None, access_token: str | None, max_results: int) -> dict[str, Any]:
    image_content = base64.b64encode(image_path.read_bytes()).decode("ascii")
    payload = {
        "requests": [
            {
                "image": {"content": image_content},
                "features": [{"type": "FACE_DETECTION", "maxResults": max_results}],
            }
        ]
    }
    url = VISION_ENDPOINT
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if api_key:
        url = f"{url}?key={api_key}"
    elif access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    else:
        raise RuntimeError(
            "Google Vision 인증 정보가 없습니다. GOOGLE_CLOUD_VISION_API_KEY 또는 GOOGLE_OAUTH_ACCESS_TOKEN을 설정하세요."
        )

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Google Vision 요청 실패: HTTP {exc.code} {detail}") from exc

    responses = data.get("responses") or []
    if not responses:
        return {}
    first = responses[0]
    if "error" in first:
        raise RuntimeError(f"Google Vision 응답 오류: {first['error']}")
    return first


def build_contact_sheet(image_paths: list[Path], output_path: Path, *, thumb_width: int = 360) -> Path:
    if not image_paths:
        sheet = Image.new("RGB", (720, 420), (245, 245, 238))
        draw = ImageDraw.Draw(sheet)
        draw.text((40, 180), "No faces detected. Manual privacy review still required.", fill=(30, 30, 30))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(output_path, quality=95)
        return output_path

    margin = 24
    label_height = 42
    columns = 2
    thumbs: list[tuple[Path, Image.Image]] = []
    for path in image_paths:
        image = Image.open(path).convert("RGB")
        thumb_height = max(1, int(image.height * thumb_width / image.width))
        thumbs.append((path, image.resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)))

    row_height = max(thumb.height for _, thumb in thumbs) + label_height + margin
    rows = (len(thumbs) + columns - 1) // columns
    sheet = Image.new(
        "RGB",
        (columns * thumb_width + (columns + 1) * margin, rows * row_height + margin),
        (245, 245, 238),
    )
    draw = ImageDraw.Draw(sheet)
    for index, (path, thumb) in enumerate(thumbs):
        x = margin + (index % columns) * (thumb_width + margin)
        y = margin + (index // columns) * row_height
        draw.text((x, y), path.name, fill=(20, 20, 20))
        sheet.paste(thumb, (x, y + label_height))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, quality=95)
    return output_path


def sanitize_images(
    input_dir: Path,
    output_dir: Path,
    *,
    recursive: bool = False,
    api_key: str | None = None,
    access_token: str | None = None,
    precomputed_detections: Path | None = None,
    blur_radius: int = 34,
    padding_ratio: float = 0.18,
    max_results: int = 50,
    gemini_fallback: bool = False,
    gemini_api_key: str | None = None,
    gemini_model: str = "gemini-2.5-flash",
    gemini_fallback_max_images: int = 50,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    detections_by_file = _read_precomputed_detections(precomputed_detections) if precomputed_detections else None
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "privacy_scope": "faces_only",
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "detectors": {
            "google_vision_face_detection": detections_by_file is None,
            "gemini_fallback": gemini_fallback,
            "gemini_model": gemini_model if gemini_fallback else None,
        },
        "images": [],
        "issues": [],
    }
    review_paths: list[Path] = []
    gemini_calls = 0

    for src in image_files(input_dir, recursive=recursive):
        relative = src.relative_to(input_dir)
        dst = output_dir / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        image = Image.open(src).convert("RGB")

        if detections_by_file is not None:
            faces = detections_by_file.get(str(relative).replace("\\", "/")) or detections_by_file.get(src.name) or []
            raw_response: dict[str, Any] | None = None
        else:
            raw_response = _request_google_vision(src, api_key=api_key, access_token=access_token, max_results=max_results)
            faces = parse_vision_faces(raw_response)
        detector_used = "google_vision" if detections_by_file is None else "precomputed"

        if not faces and gemini_fallback:
            if not gemini_api_key:
                report["issues"].append(_issue("GEMINI_API_KEY_MISSING", "Gemini fallback이 켜졌지만 GEMINI_API_KEY가 없습니다.", path=str(src)))
            elif gemini_calls >= gemini_fallback_max_images:
                report["issues"].append(_issue("GEMINI_FALLBACK_LIMIT_REACHED", "Gemini fallback 최대 이미지 수를 초과했습니다.", path=str(src)))
            else:
                gemini_calls += 1
                faces = _request_gemini_faces(src, api_key=gemini_api_key, model=gemini_model)
                detector_used = "gemini_fallback" if faces else "google_vision_then_gemini_none"

        sanitized = mask_faces(image, faces, padding_ratio=padding_ratio, blur_radius=blur_radius)
        sanitized.save(dst, quality=96)
        if faces:
            review_paths.append(dst)
        report["images"].append(
            {
                "file": str(relative).replace("\\", "/"),
                "output": str(dst),
                "face_count": len(faces),
                "detector_used": detector_used,
                "faces": [
                    {
                        "vertices": list(face.vertices),
                        "detection_confidence": face.detection_confidence,
                        "source": face.source,
                    }
                    for face in faces
                ],
                "vision_response_present": raw_response is not None,
            }
        )

    contact_sheet = output_dir / "_face_blur_contact_sheet.jpg"
    build_contact_sheet(review_paths, contact_sheet)
    report["contact_sheet"] = str(contact_sheet)
    report["gemini_fallback_calls"] = gemini_calls
    report["ok_for_human_review"] = True
    return report


def write_report(report: dict[str, Any], report_path: Path) -> Path:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Google Vision 기반 얼굴 전용 블러 처리 도구")
    parser.add_argument("--input-dir", required=True, help="원본 이미지 폴더")
    parser.add_argument("--output-dir", required=True, help="검수용 얼굴 블러 이미지 출력 폴더")
    parser.add_argument("--report", required=True, help="privacy face blur report JSON")
    parser.add_argument("--recursive", action="store_true", help="하위 폴더까지 처리")
    parser.add_argument("--api-key-env", default="GOOGLE_CLOUD_VISION_API_KEY", help="Google Vision API key 환경변수명")
    parser.add_argument("--access-token-env", default="GOOGLE_OAUTH_ACCESS_TOKEN", help="OAuth access token 환경변수명")
    parser.add_argument("--no-gcloud-fallback", action="store_true", help="gcloud application-default token fallback 비활성화")
    parser.add_argument("--detections-json", help="Google 호출 없이 사전 검출 좌표 JSON 적용")
    parser.add_argument("--blur-radius", type=int, default=34)
    parser.add_argument("--padding-ratio", type=float, default=0.18)
    parser.add_argument("--max-results", type=int, default=50)
    parser.add_argument("--gemini-fallback", action="store_true", help="Vision이 0개 얼굴을 반환한 이미지에 Gemini 시각 bbox fallback 적용")
    parser.add_argument("--gemini-api-key-env", default="GEMINI_API_KEY")
    parser.add_argument("--gemini-model", default="gemini-2.5-flash")
    parser.add_argument("--gemini-fallback-max-images", type=int, default=50)
    args = parser.parse_args()
    load_dotenv_if_present()

    access_token = os.environ.get(args.access_token_env)
    if not access_token and not args.no_gcloud_fallback:
        access_token = gcloud_access_token()

    report = sanitize_images(
        Path(args.input_dir),
        Path(args.output_dir),
        recursive=args.recursive,
        api_key=os.environ.get(args.api_key_env) or os.environ.get("GOOGLE_API_KEY"),
        access_token=access_token,
        precomputed_detections=Path(args.detections_json) if args.detections_json else None,
        blur_radius=args.blur_radius,
        padding_ratio=args.padding_ratio,
        max_results=args.max_results,
        gemini_fallback=args.gemini_fallback,
        gemini_api_key=os.environ.get(args.gemini_api_key_env),
        gemini_model=args.gemini_model,
        gemini_fallback_max_images=args.gemini_fallback_max_images,
    )
    write_report(report, Path(args.report))
    print(json.dumps({"ok": True, "report": args.report, "contact_sheet": report["contact_sheet"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
