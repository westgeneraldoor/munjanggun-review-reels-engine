"""
문장군 리뷰 영상 프로토타입 렌더러.

기존 script/SRT/voice/image 폴더를 읽어 9:16 테스트 MP4와 video_recipe.json을 만든다.
첫 목적은 CapCut 이전 단계의 자동 편집 가능성을 검증하는 것이다.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


WIDTH = 1080
HEIGHT = 1920
FPS = 24
FONT_REGULAR = Path("C:/Windows/Fonts/malgun.ttf")
FONT_BOLD = Path("C:/Windows/Fonts/malgunbd.ttf")
SECTION_LABELS = {
    "HOOK": "문제 발견",
    "SCENE": "현장 상황",
    "CONFLICT": "불편 확대",
    "SOLUTION": "상담/실측",
    "TWIST": "시공 후 변화",
    "CLOSE": "실제 리뷰",
}
IMAGE_RULES = {
    "HOOK": ["시공전 메인", "현장사진_외관", "상품썸네일"],
    "SCENE": ["현장사진_외관", "현장사진_입구계단", "시공전 메인"],
    "CONFLICT": ["시공전 메인", "현장사진_계단들", "실측"],
    "SOLUTION": ["실측", "실측 (2)", "실측 (3)"],
    "TWIST": ["시공완료 메인", "시공완료 측면", "시공완료 3연동 문열림"],
    "CLOSE": ["리뷰캡처", "시공완료 현관문에서바라보기", "시공완료 메인"],
}


@dataclass
class Subtitle:
    index: int
    start: float
    end: float
    text: str


def parse_timestamp(value: str) -> float:
    match = re.match(r"(\d+):(\d+):(\d+),(\d+)", value)
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {value}")
    hours, minutes, seconds, millis = [int(part) for part in match.groups()]
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def parse_srt(path: Path) -> list[Subtitle]:
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip())
    subtitles: list[Subtitle] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        start_text, end_text = [part.strip() for part in lines[1].split("-->")]
        subtitles.append(
            Subtitle(
                index=int(lines[0]),
                start=parse_timestamp(start_text),
                end=parse_timestamp(end_text),
                text=" ".join(lines[2:]),
            )
        )
    return subtitles


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def find_package_files(package_dir: Path) -> tuple[Path, Path, Path, Path]:
    scripts = sorted(package_dir.glob("*_script.md"))
    srts = sorted(package_dir.glob("*_subtitle.srt"))
    voices = sorted(package_dir.glob("*_voice.mp3"))
    image_dirs = [p for p in package_dir.iterdir() if p.is_dir() and p.name.endswith("_이미지")]
    if not scripts or not srts or not voices or not image_dirs:
        raise FileNotFoundError("script/SRT/voice/image folder set is incomplete.")
    return scripts[0], srts[0], voices[0], image_dirs[0]


def choose_image(image_dir: Path, section: str) -> Path:
    images = [p for p in image_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
    for keyword in IMAGE_RULES[section]:
        for image in images:
            if image.stem == keyword or image.stem.startswith(keyword):
                return image
    return sorted(images, key=lambda p: p.name)[0]


def cover_image(path: Path, size: tuple[int, int]) -> Image.Image:
    image = ImageOps.exif_transpose(Image.open(path).convert("RGB"))
    target_w, target_h = size
    scale = max(target_w / image.width, target_h / image.height)
    resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def rounded_rectangle(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if font.getlength(candidate) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    wrapped: list[str] = []
    for line in lines:
        if font.getlength(line) <= max_width:
            wrapped.append(line)
            continue
        piece = ""
        for char in line:
            if font.getlength(piece + char) <= max_width:
                piece += char
            else:
                wrapped.append(piece)
                piece = char
        if piece:
            wrapped.append(piece)
    return wrapped


def draw_scene(scene, output_path: Path):
    base = cover_image(Path(scene["image_path"]), (WIDTH, HEIGHT))
    blurred = base.filter(ImageFilter.GaussianBlur(22))
    framed = cover_image(Path(scene["image_path"]), (930, 1240))
    canvas = blurred
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=(20, 22, 22, 96))
    rounded_rectangle(draw, (75, 220, 1005, 1460), 36, (255, 255, 255, 230))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)
    canvas.paste(framed, (75, 220))

    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font_brand = ImageFont.truetype(str(FONT_BOLD), 34)
    font_section = ImageFont.truetype(str(FONT_BOLD), 38)
    font_caption = ImageFont.truetype(str(FONT_BOLD), 62)
    font_meta = ImageFont.truetype(str(FONT_REGULAR), 28)

    rounded_rectangle(draw, (72, 80, 600, 146), 33, (255, 255, 255, 232))
    draw.text((105, 99), "문장군 리뷰 보관함", font=font_brand, fill=(28, 30, 30, 255))
    draw.text((76, 154), "010 구축소음 · 자동 영상 테스트", font=font_meta, fill=(245, 245, 245, 235))

    panel_top = 1490
    draw.rectangle((0, panel_top, WIDTH, HEIGHT), fill=(16, 18, 18, 226))
    draw.text((76, panel_top + 58), f"{scene['section']} · {scene['label']}", font=font_section, fill=(201, 231, 207, 255))

    y = panel_top + 130
    for line in wrap_text(scene["caption"], font_caption, 900)[:3]:
        draw.text((76, y), line, font=font_caption, fill=(255, 255, 255, 255))
        y += 82

    draw.text((76, HEIGHT - 116), scene["source_image"], font=font_meta, fill=(220, 220, 220, 218))
    canvas = Image.alpha_composite(canvas, overlay).convert("RGB")
    canvas.save(output_path, quality=94)


def write_concat_file(scene_files: list[tuple[Path, float]], concat_path: Path):
    lines: list[str] = []
    for path, duration in scene_files:
        safe = path.as_posix().replace("'", "'\\''")
        lines.append(f"file '{safe}'")
        lines.append(f"duration {duration:.3f}")
    safe = scene_files[-1][0].as_posix().replace("'", "'\\''")
    lines.append(f"file '{safe}'")
    concat_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_video(scene_files: list[tuple[Path, float]], audio_path: Path, output_path: Path):
    concat_path = output_path.with_suffix(".concat.txt")
    write_concat_file(scene_files, concat_path)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-i",
            str(audio_path),
            "-vf",
            f"fps={FPS},format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(output_path),
        ],
        check=True,
    )


def build_recipe(package_dir: Path) -> tuple[dict, Path, list[tuple[Path, float]]]:
    script_path, srt_path, voice_path, image_dir = find_package_files(package_dir)
    subtitles = parse_srt(srt_path)
    audio_duration = probe_duration(voice_path)
    srt_total = max(sub.end for sub in subtitles)
    scale = audio_duration / srt_total if srt_total else 1
    sections = list(SECTION_LABELS.keys())
    render_dir = package_dir / "010_구축소음_video_test"
    render_dir.mkdir(exist_ok=True)

    scenes = []
    scene_files: list[tuple[Path, float]] = []
    for subtitle, section in zip(subtitles, sections):
        image_path = choose_image(image_dir, section)
        start = round(subtitle.start * scale, 3)
        end = round(subtitle.end * scale, 3)
        scene = {
            "section": section,
            "label": SECTION_LABELS[section],
            "start": start,
            "end": end,
            "duration": round(end - start, 3),
            "caption": subtitle.text,
            "image_path": str(image_path),
            "source_image": image_path.name,
        }
        scene_png = render_dir / f"{subtitle.index:02d}_{section}.jpg"
        draw_scene(scene, scene_png)
        scenes.append(scene)
        scene_files.append((scene_png, scene["duration"]))

    recipe = {
        "version": "0.1-prototype",
        "format": "vertical_9_16",
        "size": {"width": WIDTH, "height": HEIGHT},
        "fps": FPS,
        "source": {
            "package_dir": str(package_dir),
            "script": str(script_path),
            "srt": str(srt_path),
            "voice": str(voice_path),
            "image_dir": str(image_dir),
        },
        "timing": {
            "audio_seconds": round(audio_duration, 3),
            "srt_seconds": round(srt_total, 3),
            "timeline_scale": round(scale, 5),
        },
        "scenes": scenes,
    }
    return recipe, render_dir, scene_files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True, help="output 하위 리뷰 패키지 폴더")
    parser.add_argument("--no-render", action="store_true", help="MP4 렌더링 없이 recipe/scene 이미지만 생성")
    args = parser.parse_args()

    package_dir = Path(args.package).resolve()
    recipe, render_dir, scene_files = build_recipe(package_dir)
    recipe_path = package_dir / "010_구축소음_video_recipe.json"
    recipe_path.write_text(json.dumps(recipe, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.no_render:
        voice_path = Path(recipe["source"]["voice"])
        output_path = render_dir / "010_구축소음_test.mp4"
        render_video(scene_files, voice_path, output_path)
        print(output_path)
    print(recipe_path)


if __name__ == "__main__":
    main()
