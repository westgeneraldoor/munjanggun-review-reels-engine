"""
문장군 리뷰 영상 전략형 렌더러.

010_구축소음 테스트를 위해 만든 두 번째 프로토타입이다.
단순 사진 나열이 아니라 후킹, 장면 역할, 리뷰캡처 마무리 규칙을 반영한다.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


WIDTH = 1080
HEIGHT = 1920
FPS = 24
FONT_REGULAR = Path("C:/Windows/Fonts/malgun.ttf")
FONT_BOLD = Path("C:/Windows/Fonts/malgunbd.ttf")

SECTIONS = ["HOOK", "SCENE", "CONFLICT", "SOLUTION", "TWIST", "CLOSE"]
SCENE_RULES = {
    "HOOK": {
        "role": "before_after_hook",
        "motion": "before_to_after",
        "before": "시공전 메인",
        "after": "시공완료 메인",
        "label": "소음 지옥 → 조용한 현관",
        "sfx": ["low_noise", "door_wipe"],
    },
    "SCENE": {
        "role": "place_context",
        "motion": "documentary_pan",
        "image": "현장사진_외관",
        "label": "구축 빌라의 현장감",
        "sfx": [],
    },
    "CONFLICT": {
        "role": "problem",
        "motion": "problem_pulse",
        "image": "시공전 메인",
        "label": "소음과 냄새의 불편",
        "sfx": ["soft_hit"],
    },
    "SOLUTION": {
        "role": "expert_entry",
        "motion": "measure_focus",
        "image": "실측",
        "label": "무료 방문 견적",
        "sfx": ["click"],
    },
    "TWIST": {
        "role": "after_reveal",
        "motion": "clean_reveal",
        "image": "시공완료 메인",
        "label": "깔끔한 변화",
        "sfx": ["soft_whoosh"],
    },
    "CLOSE": {
        "role": "review_proof",
        "motion": "review_pop",
        "image": "리뷰캡처",
        "bg": "시공완료 현관문에서바라보기",
        "label": "실제 리뷰 증거",
        "sfx": ["pop"],
    },
}


@dataclass
class Subtitle:
    index: int
    start: float
    end: float
    text: str


def ease_out_cubic(x: float) -> float:
    x = min(max(x, 0), 1)
    return 1 - pow(1 - x, 3)


def ease_in_out(x: float) -> float:
    x = min(max(x, 0), 1)
    return 0.5 - 0.5 * math.cos(math.pi * x)


def parse_timestamp(value: str) -> float:
    match = re.match(r"(\d+):(\d+):(\d+),(\d+)", value)
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {value}")
    h, m, s, ms = [int(part) for part in match.groups()]
    return h * 3600 + m * 60 + s + ms / 1000


def parse_srt(path: Path) -> list[Subtitle]:
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip())
    subtitles: list[Subtitle] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        start_text, end_text = [part.strip() for part in lines[1].split("-->")]
        subtitles.append(Subtitle(int(lines[0]), parse_timestamp(start_text), parse_timestamp(end_text), " ".join(lines[2:])))
    return subtitles


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
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


def find_image(image_dir: Path, stem: str) -> Path:
    images = [p for p in image_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
    for image in images:
        if image.stem == stem or image.stem.startswith(stem):
            return image
    raise FileNotFoundError(f"Image matching '{stem}' was not found in {image_dir}")


def load_cover(path: Path, size: tuple[int, int], zoom: float = 1.0, shift_x: float = 0.0, shift_y: float = 0.0) -> Image.Image:
    image = ImageOps.exif_transpose(Image.open(path).convert("RGB"))
    target_w, target_h = size
    scale = max(target_w / image.width, target_h / image.height) * zoom
    resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
    max_left = max(resized.width - target_w, 0)
    max_top = max(resized.height - target_h, 0)
    left = int(max_left * (0.5 + shift_x))
    top = int(max_top * (0.5 + shift_y))
    left = min(max(left, 0), max_left)
    top = min(max(top, 0), max_top)
    return resized.crop((left, top, left + target_w, top + target_h))


def tint(image: Image.Image, brightness: float, contrast: float = 1.0, blur: float = 0.0) -> Image.Image:
    result = ImageEnhance.Brightness(image).enhance(brightness)
    result = ImageEnhance.Contrast(result).enhance(contrast)
    if blur:
        result = result.filter(ImageFilter.GaussianBlur(blur))
    return result


def draw_gradient(draw: ImageDraw.ImageDraw, top: int, bottom: int, alpha_top: int, alpha_bottom: int):
    for y in range(top, bottom):
        ratio = (y - top) / max(bottom - top, 1)
        alpha = int(alpha_top + (alpha_bottom - alpha_top) * ratio)
        draw.line((0, y, WIDTH, y), fill=(10, 12, 12, alpha))


def alpha_paste(base: Image.Image, overlay: Image.Image, xy: tuple[int, int], alpha: int = 255):
    if alpha < 255:
        overlay = overlay.copy()
        a = overlay.getchannel("A") if overlay.mode == "RGBA" else Image.new("L", overlay.size, 255)
        a = ImageEnhance.Brightness(a).enhance(alpha / 255)
        overlay.putalpha(a)
    base.alpha_composite(overlay, xy)


def wrap_korean(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    chunks = text.replace(",", ", ").replace("!", "! ").split()
    lines: list[str] = []
    current = ""
    for chunk in chunks:
        candidate = f"{current} {chunk}".strip()
        if font.getlength(candidate) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = chunk
    if current:
        lines.append(current)
    output: list[str] = []
    for line in lines:
        if font.getlength(line) <= max_width:
            output.append(line)
            continue
        piece = ""
        for char in line:
            if font.getlength(piece + char) <= max_width:
                piece += char
            else:
                output.append(piece)
                piece = char
        if piece:
            output.append(piece)
    return output


def split_hook_text(text: str) -> list[str]:
    if "층간소음" in text:
        return ["현관 소음이", "층간소음보다", "컸던 집"]
    return wrap_korean(text, ImageFont.truetype(str(FONT_BOLD), 82), 850)[:3]


def draw_brand(draw: ImageDraw.ImageDraw):
    font = ImageFont.truetype(str(FONT_BOLD), 33)
    draw.rounded_rectangle((62, 70, 455, 128), radius=29, fill=(255, 255, 255, 232))
    draw.text((92, 86), "문장군 리뷰 보관함", font=font, fill=(25, 27, 27, 255))


def draw_text_block(draw: ImageDraw.ImageDraw, lines: list[str], x: int, y: int, size: int, reveal: float, accent: str = ""):
    font = ImageFont.truetype(str(FONT_BOLD), size)
    shadow = ImageFont.truetype(str(FONT_BOLD), size)
    for i, line in enumerate(lines):
        local = ease_out_cubic((reveal - i * 0.16) / 0.5)
        if local <= 0:
            continue
        yy = int(y + i * (size + 20) + (1 - local) * 36)
        alpha = int(255 * local)
        fill = (255, 255, 255, alpha)
        if accent and accent in line:
            fill = (199, 242, 209, alpha)
        draw.text((x + 4, yy + 5), line, font=shadow, fill=(0, 0, 0, int(alpha * 0.45)))
        draw.text((x, yy), line, font=font, fill=fill)


def make_card(image_path: Path, width: int, radius: int = 28) -> Image.Image:
    image = ImageOps.exif_transpose(Image.open(image_path).convert("RGB"))
    height = int(image.height * width / image.width)
    resized = image.resize((width, height), Image.Resampling.LANCZOS).convert("RGBA")
    mask = Image.new("L", resized.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, resized.width, resized.height), radius=radius, fill=255)
    resized.putalpha(mask)
    return resized


def build_scenes(package_dir: Path) -> tuple[dict, Path, list[dict]]:
    script_path, srt_path, voice_path, image_dir = find_package_files(package_dir)
    subtitles = parse_srt(srt_path)
    audio_duration = probe_duration(voice_path)
    srt_total = max(sub.end for sub in subtitles)
    scale = audio_duration / srt_total if srt_total else 1

    scenes: list[dict] = []
    for subtitle, section in zip(subtitles, SECTIONS):
        rule = SCENE_RULES[section]
        scene = {
            "section": section,
            "start": round(subtitle.start * scale, 3),
            "end": round(subtitle.end * scale, 3),
            "caption": subtitle.text,
            "role": rule["role"],
            "motion": rule["motion"],
            "label": rule["label"],
            "sfx": rule["sfx"],
        }
        if section == "HOOK":
            scene["before_image"] = str(find_image(image_dir, rule["before"]))
            scene["after_image"] = str(find_image(image_dir, rule["after"]))
        elif section == "CLOSE":
            scene["image"] = str(find_image(image_dir, rule["image"]))
            scene["background_image"] = str(find_image(image_dir, rule["bg"]))
        else:
            scene["image"] = str(find_image(image_dir, rule["image"]))
        scene["duration"] = round(scene["end"] - scene["start"], 3)
        scenes.append(scene)

    recipe = {
        "version": "1.0-strategy-prototype",
        "strategy": "review_story_with_before_after_hook",
        "format": "instagram_reels_9_16",
        "size": {"width": WIDTH, "height": HEIGHT},
        "fps": FPS,
        "source": {
            "package_dir": str(package_dir),
            "script": str(script_path),
            "srt": str(srt_path),
            "voice": str(voice_path),
            "image_dir": str(image_dir),
        },
        "audio_direction": {
            "bgm": "future: low-volume upbeat bed, narration first",
            "sfx": "future: low_noise, door_wipe, soft_hit, click, soft_whoosh, pop",
            "current_render": "narration_only",
        },
        "timing": {
            "audio_seconds": round(audio_duration, 3),
            "srt_seconds": round(srt_total, 3),
            "timeline_scale": round(scale, 5),
        },
        "scenes": scenes,
    }
    return recipe, voice_path, scenes


def render_hook(scene: dict, progress: float) -> Image.Image:
    before = tint(load_cover(Path(scene["before_image"]), (WIDTH, HEIGHT), zoom=1.04 + progress * 0.02), 0.58, 1.08)
    after = tint(load_cover(Path(scene["after_image"]), (WIDTH, HEIGHT), zoom=1.02 + progress * 0.04), 1.08, 1.02)

    wipe = ease_in_out((progress - 0.42) / 0.32)
    canvas = before.convert("RGBA")
    if wipe > 0:
        reveal_width = int(WIDTH * wipe)
        left = (WIDTH - reveal_width) // 2
        crop = after.crop((left, 0, left + reveal_width, HEIGHT)).convert("RGBA")
        canvas.alpha_composite(crop, (left, 0))
        draw_wipe = ImageDraw.Draw(canvas)
        draw_wipe.rectangle((left - 5, 0, left + 5, HEIGHT), fill=(255, 255, 255, 160))
        draw_wipe.rectangle((left + reveal_width - 5, 0, left + reveal_width + 5, HEIGHT), fill=(255, 255, 255, 160))

    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw_gradient(draw, 0, HEIGHT, 70, 190)
    draw_brand(draw)

    label_font = ImageFont.truetype(str(FONT_BOLD), 40)
    draw.rounded_rectangle((62, 145, 462, 204), radius=29, fill=(0, 0, 0, 150))
    draw.text((92, 158), "BEFORE  →  AFTER", font=label_font, fill=(204, 244, 213, 255))

    lines = split_hook_text(scene["caption"])
    draw_text_block(draw, lines, 74, 1230, 88, progress, accent="층간소음")
    small_font = ImageFont.truetype(str(FONT_REGULAR), 32)
    draw.text((78, 1692), "첫 3초 후킹: 실제 현장 전후 변화", font=small_font, fill=(235, 235, 235, 210))
    return Image.alpha_composite(canvas, overlay).convert("RGB")


def render_standard(scene: dict, progress: float) -> Image.Image:
    motion = scene["motion"]
    zoom = 1.04 + ease_in_out(progress) * 0.05
    shift_x = 0.08 * math.sin(progress * math.pi * 0.9) if motion == "documentary_pan" else 0
    brightness = 0.76 if motion == "problem_pulse" else 0.96
    if motion == "clean_reveal":
        brightness = 0.92 + ease_out_cubic(progress) * 0.18
    base = tint(load_cover(Path(scene["image"]), (WIDTH, HEIGHT), zoom=zoom, shift_x=shift_x), brightness, 1.04)

    if motion == "problem_pulse" and 0.25 < progress < 0.78:
        enhancer = ImageEnhance.Contrast(base)
        base = enhancer.enhance(1.0 + 0.08 * math.sin(progress * math.pi * 10))

    canvas = base.convert("RGBA")
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw_gradient(draw, 0, HEIGHT, 30, 210)
    draw_brand(draw)

    label_font = ImageFont.truetype(str(FONT_BOLD), 34)
    draw.rounded_rectangle((62, 146, 590, 204), radius=29, fill=(0, 0, 0, 145))
    draw.text((92, 160), scene["label"], font=label_font, fill=(210, 244, 218, 255))

    font_size = 68 if len(scene["caption"]) < 32 else 58
    lines = wrap_korean(scene["caption"], ImageFont.truetype(str(FONT_BOLD), font_size), 900)[:3]
    accent = "소음" if "소음" in scene["caption"] else ("냄새" if "냄새" in scene["caption"] else "")
    draw_text_block(draw, lines, 74, 1320, font_size, ease_out_cubic((progress - 0.06) / 0.74), accent=accent)

    if scene["section"] == "CONFLICT":
        chip_font = ImageFont.truetype(str(FONT_BOLD), 36)
        for i, chip in enumerate(["소음", "냄새", "구축"]):
            alpha = int(230 * ease_out_cubic((progress - 0.18 - i * 0.12) / 0.35))
            if alpha <= 0:
                continue
            x = 74 + i * 178
            y = 1210 + int(math.sin(progress * 20 + i) * 3)
            draw.rounded_rectangle((x, y, x + 140, y + 58), radius=29, fill=(255, 255, 255, alpha))
            draw.text((x + 35, y + 10), chip, font=chip_font, fill=(24, 25, 25, alpha))

    return Image.alpha_composite(canvas, overlay).convert("RGB")


def render_close(scene: dict, progress: float) -> Image.Image:
    bg = tint(load_cover(Path(scene["background_image"]), (WIDTH, HEIGHT), zoom=1.05 + progress * 0.03), 0.64, 1.05, blur=1.5)
    canvas = bg.convert("RGBA")
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw_gradient(draw, 0, HEIGHT, 90, 205)
    draw_brand(draw)

    card = make_card(Path(scene["image"]), 820, radius=30)
    appear = ease_out_cubic((progress - 0.08) / 0.45)
    scale = 0.88 + appear * 0.12
    card = card.resize((int(card.width * scale), int(card.height * scale)), Image.Resampling.LANCZOS)
    x = (WIDTH - card.width) // 2
    y = int(390 + (1 - appear) * 120)

    shadow = Image.new("RGBA", (card.width + 36, card.height + 36), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((18, 18, card.width + 18, card.height + 18), radius=36, fill=(0, 0, 0, int(125 * appear)))
    alpha_paste(overlay, shadow, (x - 18, y - 18), int(255 * appear))
    alpha_paste(overlay, card, (x, y), int(255 * appear))

    quote_font = ImageFont.truetype(str(FONT_BOLD), 72)
    small_font = ImageFont.truetype(str(FONT_REGULAR), 34)
    quote_alpha = int(255 * ease_out_cubic((progress - 0.48) / 0.35))
    draw.text((76, 1295), "정말정말 좋습니다 ㅠㅠ", font=quote_font, fill=(255, 255, 255, quote_alpha))
    draw.text((78, 1400), "문장군 리뷰에서 가져왔어요", font=small_font, fill=(210, 244, 218, quote_alpha))
    return Image.alpha_composite(canvas, overlay).convert("RGB")


def render_frame(scene: dict, frame_time: float) -> Image.Image:
    duration = max(scene["duration"], 0.01)
    progress = min(max(frame_time / duration, 0), 1)
    if scene["section"] == "HOOK":
        return render_hook(scene, progress)
    if scene["section"] == "CLOSE":
        return render_close(scene, progress)
    return render_standard(scene, progress)


def render_frames(scenes: list[dict], frames_dir: Path) -> int:
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    frame_index = 0
    for scene in scenes:
        frame_count = max(1, int(round(scene["duration"] * FPS)))
        for local in range(frame_count):
            image = render_frame(scene, local / FPS)
            image.save(frames_dir / f"frame_{frame_index:05d}.jpg", quality=91)
            frame_index += 1
    return frame_index


def render_video(frames_dir: Path, voice_path: Path, output_path: Path):
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(FPS),
            "-i",
            str(frames_dir / "frame_%05d.jpg"),
            "-i",
            str(voice_path),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(output_path),
        ],
        check=True,
    )


def main():
    global FPS
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--fps", type=int, default=24, help="프리뷰는 12, 최종은 24 권장")
    args = parser.parse_args()
    FPS = args.fps

    package_dir = Path(args.package).resolve()
    recipe, voice_path, scenes = build_scenes(package_dir)
    render_dir = package_dir / "010_구축소음_story_video"
    render_dir.mkdir(exist_ok=True)
    recipe_path = package_dir / "010_구축소음_video_strategy.json"
    recipe_path.write_text(json.dumps(recipe, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.no_render:
        frames_dir = render_dir / "frames"
        frame_count = render_frames(scenes, frames_dir)
        output_path = render_dir / "010_구축소음_story_test.mp4"
        render_video(frames_dir, voice_path, output_path)
        print(f"frames={frame_count}")
        print(output_path)
    print(recipe_path)


if __name__ == "__main__":
    main()
