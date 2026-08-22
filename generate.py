"""
문장군 숏폼 콘텐츠 엔진 — generate.py
Phase 2 [F-001] 리뷰 → 사연극 스크립트 생성

사용법:
    python generate.py --input reviews/pilot/review_002.txt --approval-package output/approvals/review_002
    python generate.py --input reviews/pilot/review_002.txt --approval-package output/approvals/review_002 --with-tts
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from itertools import count
from pathlib import Path
import wave

from dotenv import load_dotenv
from google import genai
from google.genai import types

from video_engine_v2.production_gate import GateViolation, validate_generation_gate


# ─── 경로 설정 ───────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
PROMPTS_DIR = BASE_DIR / "prompts"
OUTPUT_DIR = BASE_DIR / "output"
REQUIRED_SECTIONS = ["HOOK", "SCENE", "CONFLICT", "SOLUTION", "TWIST", "CLOSE"]
TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")
TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", "Sulafat")
REFERENCE_NARRATION_CHARS_NO_SPACE = 244
REFERENCE_VOICE_SECONDS = 35.02
TARGET_TTS_CHARS_PER_SECOND = 6.97
LEADING_SILENCE_NOISE_DB = -45
LEADING_SILENCE_MIN_DETECT_SEC = 0.05
LEADING_SILENCE_MAX_ACCEPTED_SEC = 0.25
LEADING_SILENCE_TARGET_SEC = 0.15
SCRIPT_GENERATION_MAX_ATTEMPTS = 3
POSTING_COPY_INSTRUCTION = """

=== 필수 게시문안 규칙 ===

캡션과 해시태그는 선택 사항이 아닙니다.
반드시 script.md 안에 아래 두 섹션을 포함하세요.
별도 caption.txt, hashtag.txt, hashtags.txt 파일을 만들지 않습니다.

## 캡션
[인스타그램 본문 6~9줄]

캡션은 기준 충족용 요약이 아니라 인스타그램 게시글 본문입니다.
아래 구조를 지키세요.
1. 첫 줄: 문제 상황 + 내 이야기인지 묻는 릴스형 훅
2. 상황: 이 집이 왜 불편했는지 원문 리뷰 기반으로 설명
3. 전환: 시공/교체 후 무엇이 달라졌는지
4. 생활 디테일: 원문 리뷰의 구체 포인트 2개 이상
5. 저장 이유: 비슷한 집이 왜 저장할 만한지
6. CTA: 무료 실측/방문 실측/상담 유도 중 1개만 자연스럽게

금지: "이 리뷰를 참고해보세요"처럼 얕은 요약, 원문에 없는 효과 과장, 광고 문구.
주의: "완벽 차단", "무조건 해결", "추가금 걱정 끝"처럼 보장형 표현은 피하고 체감/확인/가능 여부 중심으로 쓰세요.

## 해시태그
[20~25개. 모두 #붙여쓰기 형태. #문장군 #문장군중문 #문장군시공 필수]
해시태그는 브랜드 3개 + 제품/시공 5~7개 + 문제상황 5~7개 + 고객상황/행동유도 5~8개로 구성하세요.
예: #현관중문 #중문시공 #구축리모델링 #소음차단 #무료실측 #방문실측
"""


@dataclass
class ScriptSection:
    name: str
    start_seconds: int
    end_seconds: int
    caption: str
    narration: str


@dataclass
class ReviewRecord:
    source_path: Path
    source_stem: str
    source_name: str
    sequence: str
    review_number: str
    product_order_number: str
    content: str
    input_label: str = ""


def safe_print(text: str):
    """Windows cp949 콘솔에서 이모지가 깨지지 않도록 처리."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))


def load_prompt(with_caption: bool = True) -> str:
    """screenplay.txt 프롬프트 템플릿을 로드한다."""
    prompt_path = PROMPTS_DIR / "screenplay.txt"
    if not prompt_path.exists():
        safe_print(f"[ERROR] 프롬프트 파일이 없습니다: {prompt_path}")
        sys.exit(1)

    prompt = prompt_path.read_text(encoding="utf-8")

    return prompt + POSTING_COPY_INSTRUCTION


def load_persona_prompt() -> str:
    """TTS 진행자 페르소나 프롬프트를 로드한다."""
    persona_path = PROMPTS_DIR / "persona.txt"
    if not persona_path.exists():
        safe_print(f"[ERROR] 페르소나 파일이 없습니다: {persona_path}")
        sys.exit(1)
    return persona_path.read_text(encoding="utf-8").strip()


def parse_source_sequence_and_label(source_stem: str) -> tuple[str, str]:
    """파일명에서 순번과 선택 라벨을 추출한다."""
    match = re.match(r"^(?:review[_-])?(?P<seq>\d{1,5})(?:[_-](?P<label>.+))?$", source_stem)
    if not match:
        return "", ""

    sequence = match.group("seq").zfill(3)
    label = (match.group("label") or "").strip("_- ")
    return sequence, label


def parse_review_record(text: str, source_path: Path) -> ReviewRecord:
    """리뷰번호/상품주문번호/내용 형식과 기존 원문-only 형식을 모두 파싱한다."""
    source_stem = source_path.stem
    sequence, input_label = parse_source_sequence_and_label(source_stem)

    review_number_match = re.search(r"(?m)^리뷰번호\s*:\s*(\S+)\s*$", text)
    product_order_match = re.search(r"(?m)^상품주문번호\s*:\s*(\S+)\s*$", text)
    content_match = re.search(r"(?ms)^내용\s*:\s*(?P<content>.*)\Z", text)

    content = content_match.group("content").strip() if content_match else text.strip()
    return ReviewRecord(
        source_path=source_path,
        source_stem=source_stem,
        source_name=source_path.name,
        sequence=sequence,
        review_number=review_number_match.group(1).strip() if review_number_match else "",
        product_order_number=product_order_match.group(1).strip() if product_order_match else "",
        content=content,
        input_label=input_label,
    )


def load_review_record(input_path: str) -> ReviewRecord:
    """리뷰 텍스트 파일을 메타데이터와 함께 로드한다."""
    review_path = Path(input_path)
    if not review_path.is_absolute():
        review_path = BASE_DIR / review_path

    if not review_path.exists():
        safe_print(f"[ERROR] 리뷰 파일이 없습니다: {review_path}")
        sys.exit(1)

    text = review_path.read_text(encoding="utf-8").strip()
    if not text:
        safe_print(f"[ERROR] 리뷰 파일이 비어있습니다: {review_path}")
        sys.exit(1)

    return parse_review_record(text, review_path)


def load_review(input_path: str) -> str:
    """리뷰 본문만 로드한다. 기존 호출부 호환용."""
    return load_review_record(input_path).content


def build_validation_feedback(issues: list[str]) -> str:
    """검증 실패 내용을 다음 Gemini 재시도 프롬프트에 넣을 지시문으로 만든다."""
    failures = [issue for issue in issues if issue.startswith("[FAIL]")]
    if not failures:
        return ""
    return (
        "## 이전 출력 검증 실패\n"
        "아래 실패 항목을 반드시 수정해서 다시 작성하세요.\n"
        + "\n".join(f"- {failure}" for failure in failures)
        + "\n내레이션은 길이보다 내용 품질을 우선하되, 릴스에서 답답하지 않게 간결하게 작성하세요."
    )


def generate_script(review_text: str, with_caption: bool = True, validation_feedback: str = "") -> str:
    """Gemini API를 호출하여 사연극 스크립트를 생성한다."""

    # API 키 로드
    load_dotenv(BASE_DIR / ".env")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key.startswith("여기에"):
        safe_print("[ERROR] .env 파일에 GEMINI_API_KEY를 설정해주세요.")
        safe_print("  Google AI Studio에서 발급: https://aistudio.google.com/apikey")
        sys.exit(1)

    # Gemini 설정 (google.genai 신규 SDK)
    client = genai.Client(api_key=api_key)

    # 프롬프트 조립
    prompt_template = load_prompt(with_caption)
    if validation_feedback:
        prompt_template = prompt_template.replace(
            "아래는 입력된 리뷰 원문입니다:",
            f"{validation_feedback}\n\n아래는 입력된 리뷰 원문입니다:",
        )
    full_prompt = prompt_template.replace("{review_text}", review_text)

    # API 호출
    safe_print("[...] Gemini API 호출 중...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=full_prompt,
        config={
            "temperature": 0.7,
            "max_output_tokens": 8192,
            "thinking_config": {"thinking_budget": 0},
        },
    )

    if not response.text:
        safe_print("[ERROR] Gemini API 응답이 비어있습니다.")
        sys.exit(1)

    # 후처리: created 날짜를 오늘 날짜로 강제 교체 (Gemini가 임의 날짜 생성하는 문제 방지)
    today = datetime.now().strftime("%Y-%m-%d")
    result = re.sub(r"created:\s*\d{4}-\d{2}-\d{2}", f"created: {today}", response.text)

    return result


def parse_front_matter(script_text: str) -> tuple[dict[str, str], str]:
    """YAML front matter를 간단한 key-value dict와 본문으로 분리한다."""
    match = re.match(r"(?s)^---\n(.*?)\n---\n?", script_text.strip())
    if not match:
        return {}, script_text.strip()

    metadata = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    body = script_text.strip()[match.end():].lstrip()
    return metadata, body


def apply_review_metadata(script_text: str, review_record: ReviewRecord) -> str:
    """입력 리뷰의 추적용 메타데이터를 script.md front matter에 강제로 반영한다."""
    metadata, body = parse_front_matter(script_text)
    if review_record.review_number:
        metadata["review_id"] = review_record.review_number
        metadata["review_number"] = review_record.review_number
    elif review_record.sequence:
        metadata.setdefault("review_id", review_record.sequence)

    metadata["source_file"] = review_record.source_name
    if review_record.sequence:
        metadata["review_sequence"] = review_record.sequence
    if review_record.product_order_number:
        metadata["product_order_number"] = review_record.product_order_number
    metadata.setdefault("created", datetime.now().strftime("%Y-%m-%d"))
    metadata.setdefault("content_type", "사연극")

    key_order = [
        "review_id",
        "review_number",
        "product_order_number",
        "source_file",
        "review_sequence",
        "created",
        "content_type",
    ]
    ordered_items = [(key, metadata.pop(key)) for key in key_order if key in metadata and metadata[key]]
    ordered_items.extend((key, value) for key, value in metadata.items() if value)
    front_matter = "\n".join(f"{key}: {value}" for key, value in ordered_items)
    return f"---\n{front_matter}\n---\n\n{body.strip()}\n"


ARTIFACT_STEM_MAX_LENGTH = 30
ARTIFACT_LABEL_MAX_LENGTH = 10


def extract_script_title(script_text: str) -> str:
    """스크립트의 최상위 제목을 추출한다."""
    for line in script_text.split("\n"):
        line = line.strip().strip("\r")
        if line.startswith("# ") and not line.startswith("## "):
            return line[2:].strip()
    return "untitled"


def make_safe_artifact_stem(title: str) -> str:
    """산출물 파일명에 사용할 짧고 안전한 제목을 만든다."""
    safe_title = re.sub(r'[\\/:*?"<>|]', "", title)
    safe_title = re.sub(r"\s+", "_", safe_title).strip("_")
    if len(safe_title) > ARTIFACT_STEM_MAX_LENGTH:
        safe_title = safe_title[:ARTIFACT_STEM_MAX_LENGTH].strip("_")
    return safe_title or "untitled"


def make_short_label(title: str) -> str:
    """긴 HOOK 제목을 운영용 짧은 라벨로 줄인다."""
    if "택배" in title and "고양" in title:
        return "택배고양이"
    if "힘" in title and "방문" in title:
        return "힘주던방문"

    cleaned = re.sub(r"(문장군|중문|도어)", "", title)
    tokens = re.findall(r"[가-힣A-Za-z0-9]+", cleaned)
    stopwords = {
        "이야기",
        "집사님",
        "분",
        "분들",
        "갑자기",
        "어느",
        "날",
        "뻔한",
        "했던",
        "하고",
        "에서",
        "으로",
    }
    pieces = []
    for token in tokens:
        token = re.sub(r"(은|는|이|가|을|를|에|의|로|으로|에게|한테|까지|부터)$", "", token)
        if token and token not in stopwords:
            pieces.append(token)
        if len("".join(pieces)) >= ARTIFACT_LABEL_MAX_LENGTH:
            break

    label = "".join(pieces)[:ARTIFACT_LABEL_MAX_LENGTH]
    return label or make_safe_artifact_stem(title)[:ARTIFACT_LABEL_MAX_LENGTH]


def get_artifact_stem(script_text: str, review_record: ReviewRecord | None = None) -> str:
    """script.md, SRT, MP3가 공유할 산출물 파일명 prefix를 만든다."""
    title = extract_script_title(script_text)
    label = review_record.input_label if review_record and review_record.input_label else make_short_label(title)
    safe_label = make_safe_artifact_stem(label)
    if review_record and review_record.sequence:
        return f"{review_record.sequence}_{safe_label}"
    return safe_label


def get_artifact_stem_from_script_path(script_path: Path) -> str:
    """저장된 script 파일명에서 산출물 prefix를 복원한다."""
    stem = script_path.stem
    if stem.endswith("_script"):
        return stem[: -len("_script")]
    return stem


def make_review_record_from_input_path(input_path: str) -> ReviewRecord:
    """파일을 다시 읽지 않고 input path에서 source 식별자만 만든다."""
    source_path = Path(input_path)
    sequence, input_label = parse_source_sequence_and_label(source_path.stem)
    return ReviewRecord(
        source_path=source_path,
        source_stem=source_path.stem,
        source_name=source_path.name,
        sequence=sequence,
        review_number="",
        product_order_number="",
        content="",
        input_label=input_label,
    )


def get_output_collection_dir(review_record: ReviewRecord) -> Path:
    """입력 리뷰 묶음별 output 하위 폴더를 결정한다."""
    source_path = review_record.source_path
    try:
        relative = source_path.resolve().relative_to((BASE_DIR / "reviews").resolve())
        if len(relative.parts) > 1:
            return OUTPUT_DIR / relative.parts[0]
    except ValueError:
        pass
    return OUTPUT_DIR / "manual"


def get_source_key(review_record: ReviewRecord) -> str:
    """재생성 시 같은 원본을 찾기 위한 안정적인 상대 경로 key를 만든다."""
    try:
        return str(review_record.source_path.resolve().relative_to(BASE_DIR.resolve()))
    except ValueError:
        return str(review_record.source_path)


def create_versioned_output_folder(output_collection_dir: Path, artifact_stem: str) -> Path:
    """Create a new, collision-free output package without touching existing runs."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{artifact_stem}_{timestamp}"

    for version in count():
        suffix = "" if version == 0 else f"_{version:03d}"
        output_folder = output_collection_dir / f"{base_name}{suffix}"
        try:
            output_folder.mkdir(parents=True)
        except FileExistsError:
            continue
        return output_folder


def save_script(script_text: str, input_path: str, review_record: ReviewRecord | None = None) -> Path:
    """생성된 스크립트를 output 폴더에 저장한다.

    폴더명: {제목}_{YYYYMMDD_HHMMSS}[_NNN]
    같은 리뷰 파일을 재생성해도 기존 결과를 보존하고 새 run을 만든다.
    """
    review_record = review_record or make_review_record_from_input_path(input_path)
    safe_title = get_artifact_stem(script_text, review_record)

    output_collection_dir = get_output_collection_dir(review_record)
    source_key = get_source_key(review_record)
    output_folder = create_versioned_output_folder(output_collection_dir, safe_title)

    # 스크립트 저장
    script_path = output_folder / f"{safe_title}_script.md"
    script_path.write_text(script_text, encoding="utf-8")

    # 소재 추적용 마커 파일 저장 (어떤 리뷰에서 생성했는지)
    marker_path = output_folder / ".source"
    marker_path.write_text(source_key, encoding="utf-8")

    return script_path


def parse_script_sections(script_text: str) -> list[ScriptSection]:
    """script.md에서 SRT/TTS 입력 섹션을 추출한다."""
    sections = []
    pattern = re.compile(
        r"(?m)^### \[(HOOK|SCENE|CONFLICT|SOLUTION|TWIST|CLOSE)\]\s+"
        r"(?P<start>\d+)\s*~\s*(?P<end>\d+)초[^\n]*$"
    )
    matches = list(pattern.finditer(script_text))

    for index, match in enumerate(matches):
        block_start = match.end()
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(script_text)
        block = script_text[block_start:block_end].strip()
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        caption = lines[0] if lines else ""
        narration_lines = [line for line in lines[1:] if line.startswith("> 내레이션:")]
        narration = narration_lines[0] if narration_lines else ""
        if narration.startswith("> 내레이션:"):
            narration = narration.removeprefix("> 내레이션:").strip().strip('"')

        sections.append(
            ScriptSection(
                name=match.group(1),
                start_seconds=int(match.group("start")),
                end_seconds=int(match.group("end")),
                caption=caption,
                narration=narration,
            )
        )

    return sections


def format_srt_timestamp(seconds: int) -> str:
    """초 단위 시간을 SRT 타임스탬프로 변환한다."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02}:{minutes:02}:{secs:02},000"


def generate_srt(script_text: str) -> str:
    """script.md의 자막 텍스트를 기준으로 SRT 본문을 생성한다."""
    issues = validate_script(script_text)
    failures = [issue for issue in issues if issue.startswith("[FAIL]")]
    if failures:
        raise ValueError("script.md 표준 포맷 검증 실패:\n" + "\n".join(failures))

    sections = parse_script_sections(script_text)
    if len(sections) != len(REQUIRED_SECTIONS):
        raise ValueError("SRT 생성에는 6개 스크립트 섹션이 필요합니다.")

    entries = []
    previous_end = -1
    for index, section in enumerate(sections, start=1):
        if section.start_seconds < previous_end or section.end_seconds <= section.start_seconds:
            raise ValueError(f"[{section.name}] 타임코드가 순서대로 증가하지 않습니다.")
        if section.end_seconds > 40:
            raise ValueError("SRT 마지막 타임코드가 40초를 초과합니다.")

        entries.append(
            "\n".join(
                [
                    str(index),
                    f"{format_srt_timestamp(section.start_seconds)} --> {format_srt_timestamp(section.end_seconds)}",
                    section.caption,
                ]
            )
        )
        previous_end = section.end_seconds

    return "\n\n".join(entries) + "\n"


def save_srt(script_path: Path, script_text: str) -> Path:
    """script.md와 같은 폴더에 짧은제목_subtitle.srt를 저장한다."""
    artifact_stem = get_artifact_stem_from_script_path(script_path)
    srt_path = script_path.parent / f"{artifact_stem}_subtitle.srt"
    srt_path.write_text(generate_srt(script_text), encoding="utf-8")
    return srt_path


def extract_tts_text(script_text: str) -> str:
    """script.md에서 내레이션만 추출한다."""
    issues = validate_script(script_text)
    failures = [issue for issue in issues if issue.startswith("[FAIL]")]
    if failures:
        raise ValueError("script.md 표준 포맷 검증 실패:\n" + "\n".join(failures))

    sections = parse_script_sections(script_text)
    return "\n".join(section.narration for section in sections if section.narration).strip()


def normalize_tts_text(text: str) -> str:
    """TTS가 자연스럽게 읽도록 내레이션 문장을 가볍게 정규화한다."""
    replacements = {
        "중문없이": "중문 없이",
        "있을때": "있을 때",
        "없을때": "없을 때",
        "써보신분들은": "써보신 분들은",
        "어찌 살았나": "어떻게 살았나",
        "싶을정도로": "싶을 정도로",
        "옥에티": "옥에 티",
    }
    normalized = text
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)

    normalized = normalized.replace('"', "")
    normalized = normalized.replace("..", ".")
    normalized = normalized.replace("...", ".")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\s+([,.!?])", r"\1", normalized)
    return normalized.strip()


def count_speakable_chars(text: str) -> int:
    """말 속도 기준으로 쓸 공백 제외 글자 수를 계산한다."""
    return len(re.sub(r"\s+", "", text))


def count_script_narration_chars(script_text: str) -> int:
    """script.md 전체 내레이션의 공백 제외 글자 수를 계산한다."""
    sections = parse_script_sections(script_text)
    narration_text = " ".join(section.narration for section in sections if section.narration)
    return count_speakable_chars(normalize_tts_text(narration_text))


def prepare_tts_text(script_text: str) -> str:
    """script.md 내레이션 원문을 유지하면서 TTS용으로만 가볍게 정규화한다."""
    return normalize_tts_text(extract_tts_text(script_text))


def build_tts_prompt(tts_text: str, persona_prompt: str) -> str:
    """Gemini TTS에 전달할 품질 지시문과 대본을 조립한다."""
    return f"""{persona_prompt}

아래 대본을 그대로 읽어주세요.
광고처럼 팔지 말고, 카페에서 친구에게 실제 리뷰를 소개하듯 자연스럽게 읽어주세요.
인스타 릴스 템포에 맞게 빠르고 또렷하게 읽어주세요.
자막이 함께 보이므로 느릿느릿 설명하지 말고, 핵심을 리듬감 있게 읽어주세요.
문장 끝을 과장하지 말고, 과도한 감정 연기는 피해주세요.

대본:
{tts_text}
"""


def write_wave_file(path: Path, pcm: bytes, channels: int = 1, rate: int = 24000, sample_width: int = 2):
    """Gemini TTS PCM 데이터를 WAV 파일로 저장한다."""
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(rate)
        wav_file.writeframes(pcm)


def convert_wav_to_mp3(wav_path: Path, mp3_path: Path):
    """WAV 파일을 MP3로 변환한다."""
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("MP3 변환을 위해 imageio-ffmpeg가 필요합니다.") from exc

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(wav_path),
        "-codec:a",
        "libmp3lame",
        "-q:a",
        "2",
        str(mp3_path),
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def split_atempo_filters(speed_ratio: float) -> list[float]:
    """ffmpeg atempo 필터를 안전한 배율 조합으로 나눈다."""
    filters = []
    remaining = speed_ratio
    while remaining > 2.0:
        filters.append(2.0)
        remaining /= 2.0
    if remaining < 0.5:
        filters.append(0.5)
    else:
        filters.append(round(remaining, 3))
    return filters


def get_audio_duration_seconds(path: Path) -> float:
    """ffmpeg 출력에서 오디오 길이를 초 단위로 읽는다."""
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("오디오 길이 확인을 위해 imageio-ffmpeg가 필요합니다.") from exc

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run([ffmpeg, "-i", str(path)], capture_output=True)
    stderr = result.stderr.decode("utf-8", errors="replace")
    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", stderr)
    if not match:
        raise RuntimeError(f"오디오 길이를 확인할 수 없습니다: {path}")
    return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))


def speed_adjust_mp3(input_path: Path, output_path: Path, target_seconds: float):
    """원문을 자르지 않고 말 속도만 조정해 목표 길이에 맞춘다."""
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("MP3 속도 조정을 위해 imageio-ffmpeg가 필요합니다.") from exc

    duration = get_audio_duration_seconds(input_path)
    if duration <= 0:
        raise RuntimeError(f"오디오 길이가 올바르지 않습니다: {input_path}")

    speed_ratio = duration / target_seconds
    filters = ",".join(f"atempo={value}" for value in split_atempo_filters(speed_ratio))
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-filter:a",
        filters,
        "-codec:a",
        "libmp3lame",
        "-q:a",
        "2",
        str(output_path),
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def detect_leading_silence_seconds(path: Path) -> float:
    """Measure an initial silent region without treating later pauses as lead-in."""

    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("선행 무음 확인을 위해 imageio-ffmpeg가 필요합니다.") from exc
    result = subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-i", str(path),
            "-af", f"silencedetect=noise={LEADING_SILENCE_NOISE_DB}dB:d={LEADING_SILENCE_MIN_DETECT_SEC}",
            "-f", "null", "-",
        ],
        capture_output=True,
    )
    stderr = result.stderr.decode("utf-8", errors="replace")
    start_match = re.search(r"silence_start:\s*([0-9.]+)", stderr)
    end_match = re.search(r"silence_end:\s*([0-9.]+)", stderr)
    if not start_match or not end_match or float(start_match.group(1)) > 0.03:
        return 0.0
    return round(float(end_match.group(1)), 6)


def normalize_leading_silence_mp3(path: Path) -> dict[str, float | bool]:
    """Trim only excess leading silence while retaining a decoder-safe 0.15-second lead-in."""

    detected = detect_leading_silence_seconds(path)
    result: dict[str, float | bool] = {
        "applied": False,
        "detected_leading_silence_sec": round(detected, 3),
        "normalized_leading_silence_sec": round(detected, 3),
        "target_leading_silence_sec": LEADING_SILENCE_TARGET_SEC,
    }
    if detected <= LEADING_SILENCE_MAX_ACCEPTED_SEC:
        return result
    trim_start = detected - LEADING_SILENCE_TARGET_SEC
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("선행 무음 정규화를 위해 imageio-ffmpeg가 필요합니다.") from exc
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", dir=path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
        command = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-i", str(path),
            "-af", f"atrim=start={trim_start:.6f},asetpts=PTS-STARTPTS",
            "-codec:a", "libmp3lame",
            "-q:a", "2",
            str(temporary_path),
        ]
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    normalized = detect_leading_silence_seconds(path)
    if normalized > LEADING_SILENCE_MAX_ACCEPTED_SEC:
        raise RuntimeError("선행 무음 정규화 결과가 허용 범위를 벗어났습니다.")
    result.update(
        {
            "applied": True,
            "trimmed_sec": round(trim_start, 3),
            "normalized_leading_silence_sec": round(normalized, 3),
        }
    )
    return result


def get_srt_target_seconds(script_text: str) -> float:
    """스크립트 섹션의 마지막 종료 시간을 TTS 목표 길이로 사용한다."""
    sections = parse_script_sections(script_text)
    if not sections:
        return 35.0
    return float(max(section.end_seconds for section in sections))


def get_reference_speed_target_seconds(tts_text: str) -> float:
    """리뷰2 레퍼런스 말속도에 맞춰 TTS 목표 길이를 계산한다."""
    speakable_chars = count_speakable_chars(tts_text)
    if speakable_chars <= 0:
        return REFERENCE_VOICE_SECONDS
    return max(speakable_chars / TARGET_TTS_CHARS_PER_SECOND, 1.0)


def write_tts_generation_report(
    *,
    output_folder: Path,
    artifact_stem: str,
    tts_text: str,
    raw_tts_duration_sec: float,
    final_voice_path: Path,
    final_voice_duration_sec: float,
    leading_silence_normalization: dict[str, float | bool] | None = None,
) -> Path:
    """Write hash-bound provenance for an approved Gemini/Sulafat voice."""

    work_dir = output_folder / "_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    report_path = work_dir / f"{artifact_stem}_tts_generation_report.json"
    normalized_text = normalize_tts_text(tts_text)
    payload = {
        "schema_version": "review-reel-tts-generation-report-v1",
        "provider": "google_gemini_tts",
        "model": TTS_MODEL,
        "voice": TTS_VOICE,
        "tts_text_sha256": hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
        "voice_relative_path": final_voice_path.resolve().relative_to(output_folder.resolve()).as_posix(),
        "voice_bytes": final_voice_path.stat().st_size,
        "voice_sha256": hashlib.sha256(final_voice_path.read_bytes()).hexdigest(),
        "raw_tts_duration_sec": round(float(raw_tts_duration_sec), 3),
        "final_voice_duration_sec": round(float(final_voice_duration_sec), 3),
    }
    if leading_silence_normalization is not None:
        payload["leading_silence_normalization"] = leading_silence_normalization
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report_path


def generate_voice(script_text: str, output_folder: Path, artifact_stem: str | None = None) -> Path:
    """script.md 내레이션을 Gemini TTS로 읽어 짧은제목_voice.mp3를 생성한다."""
    load_dotenv(BASE_DIR / ".env")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key.startswith("여기에"):
        safe_print("[ERROR] .env 파일에 GEMINI_API_KEY를 설정해주세요.")
        sys.exit(1)

    persona_prompt = load_persona_prompt()
    tts_text = prepare_tts_text(script_text)
    prompt = build_tts_prompt(tts_text, persona_prompt)

    client = genai.Client(api_key=api_key)
    safe_print(f"[...] Gemini TTS 호출 중... model={TTS_MODEL}, voice={TTS_VOICE}")
    response = client.models.generate_content(
        model=TTS_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=TTS_VOICE,
                    )
                )
            ),
        ),
    )

    data = response.candidates[0].content.parts[0].inline_data.data
    artifact_stem = artifact_stem or get_artifact_stem(script_text)
    wav_path = output_folder / f"{artifact_stem}_voice.wav"
    raw_mp3_path = output_folder / f"{artifact_stem}_voice_raw.mp3"
    mp3_path = output_folder / f"{artifact_stem}_voice.mp3"
    write_wave_file(wav_path, data)
    convert_wav_to_mp3(wav_path, raw_mp3_path)
    raw_duration = get_audio_duration_seconds(raw_mp3_path)
    target_seconds = get_reference_speed_target_seconds(tts_text)
    safe_print(
        "[OK] TTS 속도 기준 적용: "
        f"공백 제외 {count_speakable_chars(tts_text)}자 / 목표 {target_seconds:.2f}초 "
        f"(레퍼런스 {REFERENCE_NARRATION_CHARS_NO_SPACE}자/{REFERENCE_VOICE_SECONDS:.2f}초)"
    )
    speed_adjust_mp3(raw_mp3_path, mp3_path, target_seconds=target_seconds)
    leading_silence = normalize_leading_silence_mp3(mp3_path)
    final_duration = get_audio_duration_seconds(mp3_path)
    write_tts_generation_report(
        output_folder=output_folder,
        artifact_stem=artifact_stem,
        tts_text=tts_text,
        raw_tts_duration_sec=raw_duration,
        final_voice_path=mp3_path,
        final_voice_duration_sec=final_duration,
        leading_silence_normalization=leading_silence,
    )
    wav_path.unlink(missing_ok=True)
    raw_mp3_path.unlink(missing_ok=True)
    return mp3_path


def extract_markdown_section(text: str, heading: str) -> str:
    """Return the body under a level-2 markdown heading."""
    pattern = re.compile(
        rf"(?ms)^##\s+{re.escape(heading)}\s*\n(?P<body>.*?)(?=^##\s+|\Z)"
    )
    match = pattern.search(text)
    if not match:
        return ""
    return match.group("body").strip()


def extract_hashtags(text: str) -> list[str]:
    """Extract Instagram-style hashtags from a markdown section."""
    return re.findall(r"#[0-9A-Za-z가-힣_]+", text)


def count_korean_copy_chars(text: str) -> int:
    """Count non-space characters for Korean posting-copy quality checks."""
    return len(re.sub(r"\s+", "", text))


def validate_script(script_text: str) -> list[str]:
    """생성된 스크립트가 SRT/TTS 입력으로 안전한지 검증한다."""
    issues = []

    def fail(message: str):
        issues.append(f"[FAIL] {message}")

    def warn(message: str):
        issues.append(f"[WARN] {message}")

    # 메타데이터 확인
    if not re.search(r"(?m)^created:\s*\d{4}-\d{2}-\d{2}\s*$", script_text):
        fail("created 날짜 형식이 YYYY-MM-DD가 아닙니다.")

    if not re.search(r"(?m)^content_type:\s*사연극\s*$", script_text):
        fail("content_type: 사연극 메타데이터가 없습니다.")

    title_match = re.search(r"(?m)^#\s+(.+)$", script_text)
    if not title_match:
        fail("제목(# ...)이 없습니다.")

    sections = parse_script_sections(script_text)
    parsed_sections = {section.name: section for section in sections}

    # 6단계 섹션 존재 확인
    for section in REQUIRED_SECTIONS:
        if f"[{section}]" not in script_text:
            fail(f"[{section}] 섹션이 없습니다.")

    # 각 섹션 자막/내레이션 확인
    for section in REQUIRED_SECTIONS:
        parsed = parsed_sections.get(section)
        if parsed is None:
            fail(f"[{section}] 섹션에 자막 텍스트와 '> 내레이션:' 형식이 모두 필요합니다.")
            continue

        caption = parsed.caption
        narration = parsed.narration

        if not caption:
            fail(f"[{section}] 자막 텍스트가 비어 있습니다.")
        if not narration:
            fail(f"[{section}] 내레이션 형식은 '> 내레이션:'으로 시작해야 합니다.")
        if "[자막 텍스트]" in caption or "[자막 텍스트]" in narration:
            fail(f"[{section}]에 '[자막 텍스트]' placeholder가 남아 있습니다.")
        if caption.startswith("[") and caption.endswith("]"):
            fail(f"[{section}] 자막 텍스트는 앞뒤 대괄호 없이 작성해야 합니다.")

    # 청각 앵커 확인
    close_section = parsed_sections.get("CLOSE")
    if not close_section or "문장군 리뷰에서 가져왔어요" not in close_section.narration:
        fail("[CLOSE]에 '문장군 리뷰에서 가져왔어요' 앵커가 없습니다.")

    # HOOK 브랜드명 금지 확인. 중문/도어는 고객 사건의 대상이므로 허용한다.
    # 광고형 훅은 아래 질문/공감 패턴과 원문·claim 게이트가 별도로 차단한다.
    hook_text_parts = []
    if title_match:
        hook_text_parts.append(title_match.group(1))
    if "HOOK" in parsed_sections:
        hook_section = parsed_sections["HOOK"]
        hook_text_parts.extend([hook_section.caption, hook_section.narration])

    hook_text = " ".join(hook_text_parts)
    if "문장군" in hook_text:
        fail("HOOK 제목/자막/내레이션에 브랜드명 금지어가 있습니다: '문장군'")

    # 제품명이 등장하는 고객 사건은 허용하되, 운영원칙이 금지한 종류·장점·가격
    # 설명형 훅은 좁게 차단한다. 가격 걱정이나 선택 갈등 자체를 말하는 사건형 훅은
    # 설명/비교/정리 어휘가 없으므로 이 규칙에 걸리지 않는다.
    hook_explainer_patterns = [
        r"(?:중문|도어)(?:의|\s)*(?:종류|장점).{0,20}?(?:\d+\s*가지|[한두세네]\s*가지|몇\s*가지|비교|설명|정리|알려|소개)",
        r"(?:중문|도어)(?:의|\s)*가격.{0,20}?(?:얼마|비교|설명|정리|알려|소개)",
    ]
    for pattern in hook_explainer_patterns:
        if re.search(pattern, hook_text):
            fail(f"HOOK은 고객 사건이 아닌 제품 설명형으로 시작하면 안 됩니다: /{pattern}/")

    hook_fail_patterns = [
        r"하시죠\?",
        r"하셨죠\?",
        r"고민이셨나요\?",
        r"불편하셨나요\?",
        r"스트레스\s*받으셨나요\?",
        r"고통받으셨죠\?",
        r"있으신가요\?",
        r"분들\?",
    ]
    for pattern in hook_fail_patterns:
        if re.search(pattern, hook_text):
            fail(f"HOOK은 공감 질문형 광고 문장으로 시작하면 안 됩니다: /{pattern}/")

    hook_warn_patterns = [
        "공감하실 거예요",
        "아마 느껴보셨을 거예요",
        "많은 분들이 겪습니다",
    ]
    for phrase in hook_warn_patterns:
        if phrase in hook_text:
            warn(f"HOOK 공감형 광고 표현 주의: '{phrase}'")

    # 금지 표현 검사
    banned = [
        "여러분~",
        "안녕하세요~",
        "오늘의 사연입니다~",
        "고객님께서는~",
        "보양 작업",
        "하루 20개 시공",
    ]
    for word in banned:
        if word in script_text:
            fail(f"금지 표현 발견: '{word}'")

    post_caption = extract_markdown_section(script_text, "캡션")
    hashtag_section = extract_markdown_section(script_text, "해시태그")
    hashtags = extract_hashtags(hashtag_section)
    required_hashtags = {"#문장군", "#문장군중문", "#문장군시공"}

    if not post_caption:
        fail("script.md 안에 '## 캡션' 섹션이 없습니다.")
    if not hashtag_section:
        fail("script.md 안에 '## 해시태그' 섹션이 없습니다.")
    if post_caption:
        caption_lines = [line.strip() for line in post_caption.splitlines() if line.strip()]
        caption_chars = count_korean_copy_chars(post_caption)
        if len(caption_lines) < 5:
            fail(f"캡션은 최소 5줄 이상 필요합니다. 현재 {len(caption_lines)}줄입니다.")
        if caption_chars < 180:
            fail(f"캡션은 최소 180자 이상 필요합니다. 현재 공백 제외 {caption_chars}자입니다.")
        if not re.search(r"저장|무료\s*실측|프로필|상담|문의|확인", post_caption):
            fail("캡션에 저장/문의/무료 실측 등 자연스러운 행동 유도가 없습니다.")
        weak_caption_phrases = [
            "이 리뷰를 참고해보세요",
            "고민이시라면",
            "꼭 고려해보세요",
            "만족도가 높은 리뷰입니다",
            "추천할만한 제품입니다",
        ]
        for phrase in weak_caption_phrases:
            if phrase in post_caption:
                fail(f"캡션이 얕은 요약/광고 문장에 가깝습니다: '{phrase}'")
    if hashtag_section and not hashtags:
        fail("'## 해시태그' 섹션에 #붙여쓰기 해시태그가 없습니다.")
    if hashtags and not required_hashtags.issubset(set(hashtags)):
        missing = ", ".join(sorted(required_hashtags - set(hashtags)))
        fail(f"필수 브랜드 해시태그가 없습니다: {missing}")
    if hashtags and len(hashtags) < 10:
        fail("해시태그는 최소 10개 이상 필요합니다.")
    if hashtags and not 20 <= len(hashtags) <= 25:
        warn(f"인스타그램 표준 해시태그 수는 20~25개입니다. 현재 {len(hashtags)}개입니다.")

    if re.search(r"\d+\s*(?:만\s*)?원", script_text):
        fail("구체적 가격 수치 표현이 있습니다.")

    # AI 냄새 표현 검사
    ai_smell = ["물론", "또한", "더불어", "이처럼", "효과적입니다"]
    for word in ai_smell:
        if word in script_text:
            warn(f"AI 냄새 표현 발견: '{word}'")

    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="문장군 리뷰 -> 사연극 스크립트 생성기",
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="리뷰 텍스트 파일 경로 (예: reviews/pilot/review_002.txt)",
    )
    parser.add_argument(
        "--with-caption",
        action="store_true",
        default=True,
        help="캡션과 해시태그는 기본 생성됩니다. 하위 호환용 옵션입니다.",
    )
    parser.add_argument(
        "--with-tts",
        action="store_true",
        default=False,
        help="Gemini TTS로 짧은제목_voice.mp3도 생성",
    )
    parser.add_argument(
        "--approval-package",
        required=True,
        help="현재 리뷰의 .source, STATUS.md, APPROVAL_LOG.md가 있는 승인 패키지",
    )
    args = parser.parse_args(argv)

    # 리뷰 로드
    review_record = load_review_record(args.input)
    try:
        validate_generation_gate(args.approval_package, get_source_key(review_record))
    except GateViolation as error:
        print(f"GATE_BLOCKED: {error}", file=sys.stderr)
        return 2
    review_text = review_record.content
    safe_print(f"[OK] 리뷰 로드 완료 ({len(review_text)}자)")
    if review_record.review_number:
        safe_print(f"[OK] 리뷰번호: {review_record.review_number}")
    if review_record.product_order_number:
        safe_print(f"[OK] 상품주문번호: {review_record.product_order_number}")

    # 스크립트 생성 + 검증 실패 시 재시도
    validation_feedback = ""
    script_text = ""
    issues = []
    for attempt in range(1, SCRIPT_GENERATION_MAX_ATTEMPTS + 1):
        if attempt > 1:
            safe_print(f"[재시도] 스크립트 검증 실패 항목 반영 중... ({attempt}/{SCRIPT_GENERATION_MAX_ATTEMPTS})")

        script_text = generate_script(
            review_text,
            args.with_caption,
            validation_feedback=validation_feedback,
        )
        script_text = apply_review_metadata(script_text, review_record)
        issues = validate_script(script_text)
        failures = [issue for issue in issues if issue.startswith("[FAIL]")]
        if not failures:
            break
        validation_feedback = build_validation_feedback(issues)

    # 품질 검증
    if issues:
        safe_print("\n[검증 결과]")
        for issue in issues:
            safe_print(f"  {issue}")
        if any(issue.startswith("[FAIL]") for issue in issues):
            safe_print("\n[ERROR] 스크립트 표준 포맷 검증 실패로 저장하지 않습니다.")
            sys.exit(1)
    else:
        safe_print("[OK] 품질 검증 통과!")

    narration_chars = count_script_narration_chars(script_text)
    safe_print(
        "[INFO] 내레이션 길이 참고: "
        f"{narration_chars}자 "
        f"(음원 속도는 레퍼런스 {REFERENCE_NARRATION_CHARS_NO_SPACE}자/{REFERENCE_VOICE_SECONDS:.2f}초 기준으로 조정)"
    )

    # 저장
    saved_path = save_script(script_text, args.input, review_record=review_record)
    safe_print(f"\n[저장] {saved_path}")

    srt_path = save_srt(saved_path, script_text)
    safe_print(f"[저장] {srt_path}")

    if args.with_tts:
        voice_path = generate_voice(
            script_text,
            saved_path.parent,
            artifact_stem=get_artifact_stem_from_script_path(saved_path),
        )
        safe_print(f"[저장] {voice_path}")

    safe_print("\n" + "=" * 60)
    safe_print("[생성된 스크립트]")
    safe_print("=" * 60)
    safe_print(script_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
