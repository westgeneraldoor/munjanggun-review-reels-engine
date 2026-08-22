"""
edit_recipe_v2.json 기반 HTML 프리뷰 생성기.

렌더링 전 검수용이다. 브라우저에서 voice.mp3와 micro-beat 타임라인을
동기화해 사진, 자막, 모션 흐름을 확인한다.
"""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
from urllib.parse import quote

from video_engine_v2.production_gate import (
    consume_gate_receipt,
    resolve_engine_font_path,
    validate_html_receipt,
    write_html_artifact_evidence,
)


TEMPLATE_PATH = Path(__file__).resolve().parent / "video_engine_v2" / "templates" / "v2_preview.html"


def rel_url(from_dir: Path, target: Path) -> str:
    rel = Path(os.path.relpath(target.resolve(), from_dir.resolve()))
    return quote(rel.as_posix(), safe="/._-()")


def resolve_source(package_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else package_dir / path


def script_json(value: object) -> str:
    """Serialize JSON safely for an inline HTML script block."""
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render_preview_html(
    *,
    recipe: dict[str, object],
    asset_urls: dict[str, str],
    preview_title: str,
    preview_description: str,
) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    return (
        template.replace("__RECIPE_JSON__", script_json(recipe))
        .replace("__ASSET_URLS_JSON__", script_json(asset_urls))
        .replace("__FONT_BODY_URL__", asset_urls["font_body"])
        .replace("__PREVIEW_TITLE__", html.escape(preview_title))
        .replace("__PREVIEW_DESC__", html.escape(preview_description))
    )


def build_layout_probe(
    recipe_path: Path,
    destination_dir: Path,
    engine_font_path: str | Path | None = None,
) -> Path:
    """Render the real template into a disposable directory without production evidence."""
    recipe_path = recipe_path.resolve()
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    package_dir = recipe_path.parent
    destination_dir = destination_dir.resolve()
    destination_dir.mkdir(parents=True, exist_ok=False)
    font_path = resolve_engine_font_path(engine_font_path)
    image_dir = resolve_source(package_dir, recipe["source"]["image_dir"])
    voice_value = recipe["source"].get("voice")
    voice_path = (
        resolve_source(package_dir, voice_value)
        if isinstance(voice_value, str) and voice_value.strip()
        else None
    )

    asset_urls: dict[str, str] = {
        role: rel_url(destination_dir, image_dir / filename)
        for role, filename in recipe["asset_roles"].items()
    }
    asset_urls["voice"] = (
        rel_url(destination_dir, voice_path)
        if voice_path is not None and voice_path.is_file()
        else "data:audio/mpeg;base64,"
    )
    asset_urls["font_body"] = rel_url(destination_dir, font_path)
    display_title = recipe.get("title") or recipe_path.stem.replace("_edit_recipe_v2", "")
    display_desc = recipe.get("description") or "Disposable review-reel layout precheck"
    output_path = destination_dir / "index.html"
    output_path.write_text(
        render_preview_html(
            recipe=recipe,
            asset_urls=asset_urls,
            preview_title=str(display_title),
            preview_description=str(display_desc),
        ),
        encoding="utf-8",
    )
    return output_path


def build_preview(recipe_path: Path, gate_receipt: Path, engine_font_path: str | Path | None = None) -> Path:
    recipe_path = recipe_path.resolve()
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    package_dir = recipe_path.parent
    font_path = resolve_engine_font_path(engine_font_path)
    preview_stem = recipe_path.stem
    for suffix in ("_edit_recipe_v2", "_edit_recipe"):
        if preview_stem.endswith(suffix):
            preview_stem = preview_stem[: -len(suffix)]
            break
    preview_name = preview_stem + "_html_preview_v2"
    preview_dir = package_dir / preview_name
    if preview_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing HTML preview: {preview_dir}")
    validate_html_receipt(gate_receipt, recipe_path)
    consume_gate_receipt(gate_receipt, package_dir, expected_action="html")
    preview_dir.mkdir()

    image_dir = resolve_source(package_dir, recipe["source"]["image_dir"])
    voice_path = resolve_source(package_dir, recipe["source"]["voice"])

    asset_urls: dict[str, str] = {}
    for role, filename in recipe["asset_roles"].items():
        asset_urls[role] = rel_url(preview_dir, image_dir / filename)
    asset_urls["voice"] = rel_url(preview_dir, voice_path)
    asset_urls["font_body"] = rel_url(preview_dir, font_path)

    display_title = recipe.get("title") or recipe_path.stem.replace("_edit_recipe_v2", "")
    display_desc = recipe.get("description") or "문장군 리뷰엔진 micro-beat HTML preview입니다. 컷 속도, 자막, 사진 매칭, 모션 싱크를 먼저 검수합니다."

    rendered_html = render_preview_html(
        recipe=recipe,
        asset_urls=asset_urls,
        preview_title=display_title,
        preview_description=display_desc,
    )

    output_path = preview_dir / "index.html"
    output_path.write_text(rendered_html, encoding="utf-8")
    write_html_artifact_evidence(
        package_dir=package_dir,
        html_path=output_path,
        html_gate_receipt_path=gate_receipt,
        engine_font_path=font_path,
    )
    return output_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipe", required=True, help="edit_recipe_v2.json path")
    parser.add_argument("--gate-receipt", required=True, help="official v2 HTML gate receipt")
    parser.add_argument("--engine-font", help="repository-contained font dependency injection")
    args = parser.parse_args()
    output_path = build_preview(Path(args.recipe), Path(args.gate_receipt), args.engine_font)
    print(output_path)


if __name__ == "__main__":
    main()
