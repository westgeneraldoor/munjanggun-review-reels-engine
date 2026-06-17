"""
edit_recipe_v2.json 기반 HTML 프리뷰 생성기.

렌더링 전 검수용이다. 브라우저에서 voice.mp3와 micro-beat 타임라인을
동기화해 사진, 자막, 모션 흐름을 확인한다.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import quote


def rel_url(from_dir: Path, target: Path) -> str:
    rel = Path(os.path.relpath(target.resolve(), from_dir.resolve()))
    return quote(rel.as_posix(), safe="/._-()")


def resolve_source(package_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else package_dir / path


def build_preview(recipe_path: Path) -> Path:
    recipe_path = recipe_path.resolve()
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    package_dir = recipe_path.parent
    project_dir = Path(__file__).resolve().parent
    preview_stem = recipe_path.stem
    for suffix in ("_edit_recipe_v2", "_edit_recipe"):
        if preview_stem.endswith(suffix):
            preview_stem = preview_stem[: -len(suffix)]
            break
    preview_name = preview_stem + "_html_preview_v2"
    preview_dir = package_dir / preview_name
    preview_dir.mkdir(exist_ok=True)

    image_dir = resolve_source(package_dir, recipe["source"]["image_dir"])
    voice_path = resolve_source(package_dir, recipe["source"]["voice"])

    asset_urls: dict[str, str] = {}
    for role, filename in recipe["asset_roles"].items():
        asset_urls[role] = rel_url(preview_dir, image_dir / filename)
    asset_urls["voice"] = rel_url(preview_dir, voice_path)
    asset_urls["font_body"] = rel_url(preview_dir, project_dir / "nelnasamchae.ttf")

    display_title = recipe.get("title") or recipe_path.stem.replace("_edit_recipe_v2", "")
    display_desc = recipe.get("description") or "문장군 리뷰엔진 micro-beat HTML preview입니다. 컷 속도, 자막, 사진 매칭, 모션 싱크를 먼저 검수합니다."

    html = HTML_TEMPLATE.replace("__RECIPE_JSON__", json.dumps(recipe, ensure_ascii=False))
    html = html.replace("__ASSET_URLS_JSON__", json.dumps(asset_urls, ensure_ascii=False))
    html = html.replace("__FONT_BODY_URL__", asset_urls["font_body"])
    html = html.replace("__PREVIEW_TITLE__", display_title)
    html = html.replace("__PREVIEW_DESC__", display_desc)

    output_path = preview_dir / "index.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path


HTML_TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__PREVIEW_TITLE__ HTML Preview v2</title>
  <style>
    @font-face {
      font-family: "MunjangBody";
      src: url("__FONT_BODY_URL__") format("truetype");
      font-display: swap;
    }

    :root {
      --stage-w: min(56.25vh, 390px);
      --stage-h: calc(var(--stage-w) * 16 / 9);
      --yellow: #ffd84d;
      --yellow-soft: #ffe98a;
      --ink: #161616;
      --paper: #f8f5ef;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      background: #20211f;
      color: #f6f2e8;
      font-family: "MunjangBody", "Malgun Gothic", "Apple SD Gothic Neo", system-ui, sans-serif;
      letter-spacing: 0;
      display: grid;
      grid-template-columns: minmax(360px, 1fr) minmax(340px, 440px);
      gap: 24px;
      padding: 24px;
    }

    .preview-shell {
      display: grid;
      place-items: center;
      min-height: calc(100vh - 48px);
    }

    .phone {
      width: var(--stage-w);
      height: var(--stage-h);
      max-width: 100%;
      background: #111;
      border-radius: 28px;
      overflow: hidden;
      box-shadow: 0 24px 80px rgba(0, 0, 0, 0.45);
      position: relative;
    }

    .stage {
      position: absolute;
      inset: 0;
      overflow: hidden;
      background: #151515;
    }

    .stage::after {
      content: "";
      position: absolute;
      inset: 0;
      pointer-events: none;
      background:
        linear-gradient(to bottom, rgba(0,0,0,0.12), transparent 23%, transparent 67%, rgba(0,0,0,0.26)),
        radial-gradient(circle at 50% 48%, transparent 0 54%, rgba(0,0,0,0.18) 100%);
      opacity: 0.72;
      z-index: 2;
    }

    .asset {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
      transform-origin: center;
      will-change: transform, opacity, filter;
      transition: opacity 180ms ease, filter 180ms ease;
    }

    .asset.backdrop {
      opacity: 0;
      filter: blur(10px) brightness(0.6);
      transform: scale(1.08);
    }

    .stage.product_card_flash .asset.backdrop,
    .stage.review_capture_scroll .asset.backdrop {
      opacity: 1;
    }

    .flash-layer {
      position: absolute;
      inset: 0;
      background: radial-gradient(circle at 50% 40%, rgba(255,255,255,0.95), rgba(255,255,255,0.08) 35%, transparent 70%);
      opacity: 0;
      pointer-events: none;
      z-index: 9;
    }

    .wipe-layer {
      position: absolute;
      inset: 0;
      transform: translateX(-115%);
      background: linear-gradient(100deg, transparent 0 20%, rgba(255,255,255,0.86) 45%, rgba(255,216,77,0.6) 55%, transparent 78% 100%);
      opacity: 0;
      pointer-events: none;
      z-index: 8;
      mix-blend-mode: screen;
    }

    .sparkle {
      position: absolute;
      inset: 0;
      opacity: 0;
      background-image:
        radial-gradient(circle, rgba(255,255,255,0.92) 0 2px, transparent 3px),
        radial-gradient(circle, rgba(255,216,77,0.88) 0 2px, transparent 3px);
      background-size: 90px 90px, 130px 130px;
      background-position: 12px 28px, 48px 66px;
      mix-blend-mode: screen;
      pointer-events: none;
      z-index: 8;
    }

    .caption {
      position: absolute;
      left: 42px;
      right: 42px;
      bottom: 320px;
      display: grid;
      gap: 6px;
      font-weight: 900;
      font-family: "MunjangBody", "Malgun Gothic", sans-serif;
      font-size: clamp(32px, 5.1vh, 56px);
      line-height: 1.05;
      color: var(--yellow);
      text-align: center;
      text-shadow: 0 4px 0 rgba(0, 0, 0, 0.75), 0 8px 24px rgba(0, 0, 0, 0.65);
      paint-order: stroke fill;
      -webkit-text-stroke: 1.3px rgba(25,25,25,0.88);
      transform-origin: center;
      z-index: 6;
      white-space: normal;
      word-break: keep-all;
      overflow-wrap: normal;
    }

    .caption .em {
      color: #fff2a8;
      font-size: 1em;
      display: inline-block;
      white-space: nowrap;
    }

    .caption.accent-keyword .em {
      color: #fff5a9;
      font-size: 1.06em;
      margin: 0 0.015em;
      text-shadow:
        0 3px 0 rgba(0, 0, 0, 0.78),
        0 9px 24px rgba(0, 0, 0, 0.62),
        0 0 18px rgba(255, 231, 100, 0.28);
      transform-origin: center 70%;
      animation: keywordAccentIn 420ms cubic-bezier(.2, 1.22, .28, 1) both;
      animation-delay: calc(var(--accent-delay-ms, 90ms) + (var(--accent-index, 0) * 65ms));
    }

    .caption.accent-keyword.accent-soft .em {
      font-size: 1.045em;
    }

    .caption.accent-keyword.accent-proof .em {
      color: #fff7ba;
      font-size: 1.06em;
    }

    .caption.accent-keyword.accent-result .em {
      color: #ffffff;
      font-size: 1.075em;
    }

    @keyframes keywordAccentIn {
      0% {
        opacity: 0.72;
        transform: translateY(5px) scale(0.96);
      }
      55% {
        opacity: 1;
        transform: translateY(-1px) scale(1.035);
      }
      100% {
        opacity: 1;
        transform: translateY(0) scale(1);
      }
    }

    .caption-line {
      display: block;
      white-space: normal;
      word-break: keep-all;
      overflow-wrap: anywhere;
      max-width: 100%;
    }

    .caption.theme-warning {
      color: #ff5959;
      text-shadow: 0 4px 0 rgba(0,0,0,0.85), 0 10px 24px rgba(0,0,0,0.68);
      -webkit-text-stroke: 1.5px rgba(20,20,20,0.92);
    }

    .caption.theme-warning .em {
      color: #fff0d0;
    }

    .caption.theme-proof {
      color: #7ef0ff;
      text-shadow: 0 4px 0 rgba(0,0,0,0.78), 0 8px 24px rgba(0,0,0,0.7);
      -webkit-text-stroke: 1.25px rgba(20,20,20,0.9);
    }

    .caption.theme-proof .em {
      color: #fff4a7;
    }

    .caption.theme-clear {
      color: #dcff77;
      text-shadow: 0 4px 0 rgba(0,0,0,0.76), 0 8px 24px rgba(0,0,0,0.66);
      -webkit-text-stroke: 1.25px rgba(20,20,20,0.9);
    }

    .caption.theme-cta {
      color: #ffe66b;
      background: linear-gradient(180deg, rgba(0,0,0,0.52), rgba(0,0,0,0.34));
      border: 1px solid rgba(255,255,255,0.2);
      border-radius: 22px;
      box-shadow: 0 18px 42px rgba(0,0,0,0.38);
      padding: 18px 22px 20px;
      text-shadow: 0 4px 0 rgba(0,0,0,0.9), 0 12px 28px rgba(0,0,0,0.72);
      -webkit-text-stroke: 1.45px rgba(10,10,10,0.95);
    }

    .caption.theme-cta .em {
      color: #ffffff;
    }

    .caption.theme-stamp {
      color: #ffef78;
      text-transform: uppercase;
      transform: rotate(-4deg);
      border: 5px solid rgba(255,239,120,0.86);
      border-radius: 10px;
      padding: 12px 14px;
      background: rgba(18,18,18,0.18);
      box-shadow: 0 18px 44px rgba(0,0,0,0.35);
    }

    .caption.size-small {
      font-size: clamp(25px, 3.7vh, 40px);
      line-height: 1.08;
    }

    .caption.size-medium {
      font-size: clamp(32px, 4.8vh, 52px);
    }

    .caption.size-large {
      font-size: clamp(42px, 6.2vh, 70px);
    }

    .caption.pos-upper {
      top: 155px;
      bottom: auto;
    }

    .caption.pos-center {
      top: 50%;
      bottom: auto;
    }

    .caption.pos-lower {
      bottom: 270px;
    }

    .caption.pos-bottom {
      bottom: 120px;
    }

    .paper {
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      background: transparent;
      opacity: 0;
      z-index: 5;
    }

    .paper-ball {
      width: 172px;
      height: 132px;
      background: var(--paper);
      color: var(--ink);
      display: grid;
      place-items: center;
      font-size: 42px;
      font-weight: 900;
      transform: rotate(-11deg);
      clip-path: polygon(12% 18%, 30% 4%, 52% 14%, 78% 7%, 94% 28%, 84% 52%, 96% 78%, 70% 91%, 44% 82%, 18% 96%, 4% 70%, 10% 43%);
      box-shadow: 0 18px 45px rgba(0,0,0,0.45), inset 12px 12px 24px rgba(0,0,0,0.08);
    }

    .product-card {
      position: absolute;
      left: 50%;
      top: 50%;
      width: 74%;
      aspect-ratio: 1 / 1;
      transform: translate(-50%, -50%) scale(0.8) rotate(-2deg);
      border-radius: 14px;
      overflow: hidden;
      opacity: 0;
      box-shadow: 0 28px 70px rgba(0,0,0,0.5);
      z-index: 4;
      background: #111;
    }

    .transition-hit.t-zoom_snap .asset.main,
    .transition-hit.t-paper_open .asset.main {
      animation: imageSnap 520ms cubic-bezier(.12,1.05,.26,1) both;
    }

    .transition-hit.t-flash_glow .flash-layer,
    .transition-hit.t-hit_flash .flash-layer,
    .transition-hit.t-glow .flash-layer {
      animation: flashBang 520ms ease-out both;
    }

    .transition-hit.t-flash_glow .sparkle,
    .transition-hit.t-glow .sparkle {
      animation: sparkleBurst 760ms ease-out both;
    }

    .transition-hit.t-slide_up .asset.main {
      animation: slideUpIn 520ms cubic-bezier(.16,.92,.24,1) both;
    }

    .transition-hit.t-card_pop .product-card {
      animation: productPop 520ms cubic-bezier(.16,1.15,.3,1) both;
    }

    .stage.review_capture_scroll.transition-hit.t-pop .review-card {
      animation: reviewPop 620ms cubic-bezier(.16,1.1,.3,1) both;
    }

    .transition-hit.t-caption_swap .caption,
    .transition-hit.t-smooth_slide .caption,
    .transition-hit.t-cut .caption {
      animation: captionPop 180ms cubic-bezier(.16,1.2,.36,1) both;
    }

    .transition-hit.t-smooth_cut .wipe-layer,
    .transition-hit.t-smooth_slide .wipe-layer {
      animation: wipeAcross 620ms cubic-bezier(.2,.8,.2,1) both;
    }

    @keyframes flashBang {
      0% { opacity: 0.95; }
      100% { opacity: 0; }
    }

    @keyframes wipeAcross {
      0% { opacity: 0; transform: translateX(-115%); }
      15% { opacity: 0.95; }
      100% { opacity: 0; transform: translateX(115%); }
    }

    @keyframes captionPop {
      0% { opacity: 0.45; transform: translateY(16px) scale(0.92); filter: blur(1px); }
      68% { opacity: 1; transform: translateY(-5px) scale(1.05); filter: blur(0); }
      100% { opacity: 1; transform: translateY(0) scale(1); filter: blur(0); }
    }

    @keyframes imageSnap {
      0% { transform: scale(1.13); filter: brightness(1.16) blur(2px); }
      100% { transform: scale(1.04); filter: brightness(1) blur(0); }
    }

    @keyframes slideUpIn {
      0% { transform: scale(1.11) translateY(46px); filter: blur(2px) brightness(0.92); }
      100% { transform: scale(1.06) translateY(0); filter: blur(0) brightness(1); }
    }

    @keyframes productPop {
      0% { opacity: 0; transform: translate(-50%, -50%) scale(0.62) rotate(-7deg); }
      68% { opacity: 1; transform: translate(-50%, -50%) scale(1.05) rotate(1deg); }
      100% { opacity: 1; transform: translate(-50%, -50%) scale(1) rotate(0deg); }
    }

    @keyframes reviewPop {
      0% { opacity: 0; transform: translate(-50%, -36%) scale(0.78); filter: blur(4px); }
      100% { opacity: 1; transform: translate(-50%, -50%) scale(1); filter: blur(0); }
    }

    @keyframes sparkleBurst {
      0% { opacity: 0; transform: scale(0.92); }
      35% { opacity: 0.85; }
      100% { opacity: 0; transform: scale(1.12); }
    }

    .product-card img,
    .review-card img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }

    .review-card {
      position: absolute;
      left: 50%;
      top: 42%;
      width: 82%;
      transform: translate(-50%, -50%) scale(0.92);
      border-radius: 18px;
      overflow: hidden;
      opacity: 0;
      z-index: 4;
      background: #fff;
      box-shadow: 0 28px 70px rgba(0,0,0,0.58);
    }

    .semantic-overlay {
      position: absolute;
      inset: 0;
      z-index: 5;
      pointer-events: none;
      opacity: 0;
      transform: translateY(12px) scale(0.98);
      --p: 0;
      --wave: 0;
    }

    .overlay-chip,
    .overlay-badge {
      position: absolute;
      padding: 8px 12px 9px;
      border-radius: 999px;
      color: #191714;
      background: rgba(255, 216, 77, 0.95);
      border: 2px solid rgba(255,255,255,0.9);
      box-shadow: 0 10px 28px rgba(0,0,0,0.34);
      font-size: 18px;
      font-weight: 900;
      line-height: 1;
      text-shadow: none;
      white-space: nowrap;
    }

    .overlay-badge {
      background: rgba(255, 82, 82, 0.96);
      color: #fff;
      border-color: rgba(255,255,255,0.72);
      text-shadow: 0 2px 0 rgba(0,0,0,0.36);
    }

    .overlay-line {
      position: absolute;
      height: 5px;
      border-radius: 999px;
      background: linear-gradient(90deg, transparent, #ffe66b, #fff, #ffe66b, transparent);
      box-shadow: 0 0 22px rgba(255,230,107,0.82);
      transform-origin: left center;
    }

    .overlay-vline {
      position: absolute;
      width: 5px;
      border-radius: 999px;
      background: linear-gradient(180deg, transparent, #7ef0ff, #fff, #7ef0ff, transparent);
      box-shadow: 0 0 22px rgba(126,240,255,0.72);
    }

    .overlay-zone {
      position: absolute;
      border: 4px solid rgba(255,216,77,0.92);
      border-radius: 18px;
      box-shadow: 0 0 0 999px rgba(0,0,0,0.05), 0 0 30px rgba(255,216,77,0.42);
      background: rgba(255,216,77,0.06);
    }

    .overlay-arrow {
      position: absolute;
      height: 7px;
      border-radius: 999px;
      background: linear-gradient(90deg, #7ef0ff, #fff7a8);
      box-shadow: 0 0 22px rgba(126,240,255,0.65);
      transform-origin: left center;
    }

    .overlay-arrow::after {
      content: "";
      position: absolute;
      right: -11px;
      top: 50%;
      width: 0;
      height: 0;
      border-top: 12px solid transparent;
      border-bottom: 12px solid transparent;
      border-left: 18px solid #fff7a8;
      transform: translateY(-50%);
      filter: drop-shadow(0 0 8px rgba(126,240,255,0.55));
    }

    .overlay-dot {
      position: absolute;
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: #7ef0ff;
      border: 4px solid #fff;
      box-shadow: 0 0 28px rgba(126,240,255,0.9), 0 8px 20px rgba(0,0,0,0.35);
    }

    .semantic-overlay.kind-threshold_block .overlay-zone { left: 26%; right: 22%; bottom: 165px; height: 92px; }
    .semantic-overlay.kind-threshold_block .overlay-arrow { left: 18%; top: 61%; width: 38%; transform: rotate(8deg) scaleX(calc(0.35 + var(--p) * 0.65)); }
    .semantic-overlay.kind-threshold_block .overlay-badge { left: 50%; bottom: 248px; transform: translateX(-50%) rotate(-4deg); }
    .semantic-overlay.kind-threshold_block .overlay-chip { right: 28px; bottom: 198px; }
    .semantic-overlay.kind-threshold_block .overlay-dot { left: calc(24% + var(--p) * 24%); top: 57%; }

    .semantic-overlay.kind-old_door_mood .overlay-zone { left: 14%; right: 14%; top: 135px; bottom: 135px; border-color: rgba(255,82,82,0.8); background: rgba(255,82,82,0.05); }
    .semantic-overlay.kind-old_door_mood .overlay-badge { left: 32px; top: 160px; transform: rotate(-5deg); }
    .semantic-overlay.kind-old_door_mood .overlay-chip { right: 34px; bottom: 230px; background: rgba(255,255,255,0.92); }

    .semantic-overlay.kind-frame_threshold_focus .overlay-zone { left: 17%; right: 17%; top: 130px; bottom: 220px; }
    .semantic-overlay.kind-frame_threshold_focus .overlay-line { left: 18%; right: 18%; bottom: 225px; }
    .semantic-overlay.kind-frame_threshold_focus .overlay-vline.left { left: 17%; top: 130px; bottom: 220px; }
    .semantic-overlay.kind-frame_threshold_focus .overlay-vline.right { right: 17%; top: 130px; bottom: 220px; }
    .semantic-overlay.kind-frame_threshold_focus .overlay-badge { left: 36px; top: 150px; }
    .semantic-overlay.kind-frame_threshold_focus .overlay-chip { right: 34px; bottom: 236px; }

    .semantic-overlay.kind-measure_precision .overlay-line { left: 15%; right: 15%; top: 44%; transform: scaleX(calc(0.2 + var(--p) * 0.8)); }
    .semantic-overlay.kind-measure_precision .overlay-vline.left { left: 18%; top: 31%; height: 30%; }
    .semantic-overlay.kind-measure_precision .overlay-vline.right { right: 18%; top: 31%; height: 30%; }
    .semantic-overlay.kind-measure_precision .overlay-badge { left: 50%; top: 170px; transform: translateX(-50%); background: rgba(126,240,255,0.95); color: #101010; }
    .semantic-overlay.kind-measure_precision .overlay-chip { left: 50%; top: 49%; transform: translateX(-50%); }

    .semantic-overlay.kind-one_day_replace .overlay-badge { left: 50%; top: 130px; transform: translateX(-50%) rotate(-3deg); }
    .semantic-overlay.kind-one_day_replace .overlay-card { position: absolute; top: 245px; width: 86px; height: 116px; border-radius: 12px; background: rgba(255,255,255,0.88); border: 3px solid rgba(255,216,77,0.94); box-shadow: 0 16px 34px rgba(0,0,0,0.32); display: grid; place-items: center; color: #191714; font-size: 18px; font-weight: 900; }
    .semantic-overlay.kind-one_day_replace .overlay-card:nth-child(2) { left: 58px; transform: rotate(-8deg) translateY(calc((1 - var(--p)) * 22px)); }
    .semantic-overlay.kind-one_day_replace .overlay-card:nth-child(3) { left: 50%; transform: translateX(-50%) rotate(1deg) translateY(calc((1 - var(--p)) * 12px)); }
    .semantic-overlay.kind-one_day_replace .overlay-card:nth-child(4) { right: 58px; transform: rotate(8deg) translateY(calc((1 - var(--p)) * 22px)); }
    .semantic-overlay.kind-one_day_replace .overlay-chip { left: 50%; bottom: 190px; transform: translateX(-50%); }

    .semantic-overlay.kind-brightness_before_after .overlay-arrow { left: 22%; top: 49%; width: 54%; transform: scaleX(calc(0.25 + var(--p) * 0.75)); }
    .semantic-overlay.kind-brightness_before_after .overlay-badge { left: 38px; top: 170px; background: rgba(35,35,35,0.82); }
    .semantic-overlay.kind-brightness_before_after .overlay-chip { right: 42px; top: 170px; background: rgba(220,255,119,0.96); }

    .semantic-overlay.kind-robot_path .overlay-arrow { left: 20%; bottom: 220px; width: 55%; transform: rotate(-7deg) scaleX(calc(0.18 + var(--p) * 0.82)); }
    .semantic-overlay.kind-robot_path .overlay-dot { left: calc(19% + var(--p) * 50%); bottom: calc(210px + var(--p) * 46px); }
    .semantic-overlay.kind-robot_path .overlay-badge { left: 36px; bottom: 285px; background: rgba(126,240,255,0.96); color: #111; text-shadow: none; }
    .semantic-overlay.kind-robot_path .overlay-chip { right: 32px; bottom: 185px; }

    .semantic-overlay.kind-review_quote .overlay-badge { left: 50%; bottom: 145px; transform: translateX(-50%); background: rgba(255,216,77,0.98); color: #191714; text-shadow: none; }
    .semantic-overlay.kind-review_quote .overlay-chip { left: 50%; top: 140px; transform: translateX(-50%); background: rgba(126,240,255,0.94); }

    .semantic-overlay.kind-cta_checklist .overlay-chip { left: 50%; transform: translateX(-50%); background: rgba(255,255,255,0.94); }
    .semantic-overlay.kind-cta_checklist .overlay-chip.first { top: 155px; }
    .semantic-overlay.kind-cta_checklist .overlay-chip.second { bottom: 190px; background: rgba(255,216,77,0.96); }

    .motion-note {
      position: absolute;
      left: 20px;
      bottom: 20px;
      z-index: 8;
      color: rgba(255,255,255,0.42);
      font-size: 11px;
      display: none;
    }

    .side {
      min-height: calc(100vh - 48px);
      display: grid;
      align-content: start;
      gap: 16px;
    }

    .panel {
      background: #2a2b28;
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 14px;
      padding: 16px;
      box-shadow: 0 10px 36px rgba(0,0,0,0.18);
    }

    h1 {
      margin: 0 0 6px;
      font-size: 20px;
      line-height: 1.25;
    }

    p {
      margin: 0;
      color: rgba(246,242,232,0.72);
      font-size: 13px;
      line-height: 1.55;
    }

    .controls {
      display: grid;
      gap: 12px;
    }

    .button-row {
      display: flex;
      gap: 10px;
      align-items: center;
    }

    button {
      border: 0;
      border-radius: 10px;
      background: var(--yellow);
      color: #191714;
      font-size: 15px;
      font-weight: 900;
      padding: 10px 15px;
      cursor: pointer;
    }

    button.secondary {
      background: #3b3c38;
      color: #f6f2e8;
      border: 1px solid rgba(255,255,255,0.1);
    }

    input[type="range"] {
      width: 100%;
      accent-color: var(--yellow);
    }

    .time-readout {
      margin-left: auto;
      font-variant-numeric: tabular-nums;
      color: rgba(246,242,232,0.8);
      font-size: 14px;
    }

    .beat-list {
      display: grid;
      gap: 7px;
      max-height: 56vh;
      overflow: auto;
      padding-right: 4px;
    }

    .beat-item {
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.035);
      border-radius: 10px;
      padding: 9px 10px;
      cursor: pointer;
      transition: background 0.15s ease, border 0.15s ease;
    }

    .beat-item.active {
      background: rgba(255,216,77,0.17);
      border-color: rgba(255,216,77,0.55);
    }

    .beat-meta {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      color: rgba(246,242,232,0.62);
      font-size: 11px;
      margin-bottom: 5px;
    }

    .beat-caption {
      color: #fff3a6;
      font-size: 14px;
      font-weight: 800;
      line-height: 1.28;
      white-space: pre-line;
    }

    .beat-asset {
      color: rgba(246,242,232,0.58);
      font-size: 11px;
      margin-top: 5px;
    }

    @media (max-width: 900px) {
      body {
        grid-template-columns: 1fr;
      }
      .side {
        min-height: auto;
      }
    }
  </style>
</head>
<body>
  <main class="preview-shell">
    <div class="phone">
      <section class="stage" id="stage">
        <img class="asset backdrop" id="backdrop" alt="" />
        <img class="asset main" id="mainAsset" alt="" />
        <div class="flash-layer" id="flashLayer"></div>
        <div class="wipe-layer" id="wipeLayer"></div>
        <div class="sparkle" id="sparkle"></div>
        <div class="paper" id="paper"><div class="paper-ball" id="paperBall">문장군</div></div>
        <div class="product-card" id="productCard"><img id="productImg" alt="" /></div>
        <div class="review-card" id="reviewCard"><img id="reviewImg" alt="" /></div>
        <div class="semantic-overlay" id="semanticOverlay"></div>
        <div class="caption" id="caption"></div>
        <div class="motion-note" id="motionNote"></div>
      </section>
    </div>
  </main>

  <aside class="side">
    <section class="panel">
      <h1>__PREVIEW_TITLE__ HTML Preview v2</h1>
      <p>__PREVIEW_DESC__</p>
    </section>

    <section class="panel controls">
      <audio id="audio" preload="auto"></audio>
      <div class="button-row">
        <button id="playBtn">재생</button>
        <button class="secondary" id="restartBtn">처음</button>
        <span class="time-readout"><span id="timeNow">0.0</span>s / <span id="duration">32.6</span>s</span>
      </div>
      <input id="scrubber" type="range" min="0" max="32.6" step="0.01" value="0" />
      <p id="currentInfo">대기 중</p>
    </section>

    <section class="panel">
      <h1>Micro Beats</h1>
      <div class="beat-list" id="beatList"></div>
    </section>
  </aside>

  <script>
    const recipe = __RECIPE_JSON__;
    const assetUrls = __ASSET_URLS_JSON__;
    const beats = recipe.beats;
    const totalDuration = Math.max(...beats.map(b => b.time[1]));

    const stage = document.getElementById('stage');
    const mainAsset = document.getElementById('mainAsset');
    const backdrop = document.getElementById('backdrop');
    const caption = document.getElementById('caption');
    const flashLayer = document.getElementById('flashLayer');
    const wipeLayer = document.getElementById('wipeLayer');
    const sparkle = document.getElementById('sparkle');
    const paper = document.getElementById('paper');
    const paperBall = document.getElementById('paperBall');
    const productCard = document.getElementById('productCard');
    const productImg = document.getElementById('productImg');
    const reviewCard = document.getElementById('reviewCard');
    const reviewImg = document.getElementById('reviewImg');
    const semanticOverlay = document.getElementById('semanticOverlay');
    const audio = document.getElementById('audio');
    const playBtn = document.getElementById('playBtn');
    const restartBtn = document.getElementById('restartBtn');
    const scrubber = document.getElementById('scrubber');
    const timeNow = document.getElementById('timeNow');
    const durationText = document.getElementById('duration');
    const currentInfo = document.getElementById('currentInfo');
    const beatList = document.getElementById('beatList');
    const motionNote = document.getElementById('motionNote');

    let activeBeatId = null;
    let manualTime = 0;
    let isScrubbing = false;

    audio.src = assetUrls.voice;
    scrubber.max = totalDuration.toFixed(2);
    durationText.textContent = totalDuration.toFixed(1);

    function clamp(value, min, max) {
      return Math.min(Math.max(value, min), max);
    }

    function easeOutCubic(x) {
      x = clamp(x, 0, 1);
      return 1 - Math.pow(1 - x, 3);
    }

    function easeInOut(x) {
      x = clamp(x, 0, 1);
      return 0.5 - 0.5 * Math.cos(Math.PI * x);
    }

    function assetFor(beat) {
      if (beat.asset === 'paper_graphic') return null;
      return assetUrls[beat.asset] || '';
    }

    function backgroundFor(beat) {
      if (beat.background_asset) return assetUrls[beat.background_asset];
      if (beat.motion === 'product_card_flash') return assetUrls.measure_wall || assetUrls.before_main;
      return assetFor(beat);
    }

    function splitCaption(text) {
      return String(text || '').split('\n');
    }

    function highlightCaption(text, emphasis = [], accent = {}) {
      const limit = Math.max(0, Math.min(Number(accent.max_keywords || 2), 2));
      const words = (emphasis || []).filter(Boolean).slice(0, limit);
      return splitCaption(text).map(line => {
        let html = esc(line);
        words.forEach((word, index) => {
          const safe = String(word).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
          html = html.replace(new RegExp(safe, 'g'), `<span class="em" style="--accent-index:${index}">${esc(word)}</span>`);
        });
        return `<span class="caption-line">${html}</span>`;
      }).join('');
    }

    function esc(text) {
      return String(text || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function semanticMarkup(overlay) {
      if (!overlay || !overlay.kind) return '';
      const label = esc(overlay.label);
      const accent = esc(overlay.accent);
      switch (overlay.kind) {
        case 'threshold_block':
          return `<div class="overlay-zone"></div><div class="overlay-arrow"></div><div class="overlay-dot"></div><div class="overlay-badge">${label}</div><div class="overlay-chip">${accent}</div>`;
        case 'old_door_mood':
          return `<div class="overlay-zone"></div><div class="overlay-badge">${label}</div><div class="overlay-chip">${accent}</div>`;
        case 'frame_threshold_focus':
          return `<div class="overlay-zone"></div><div class="overlay-line"></div><div class="overlay-vline left"></div><div class="overlay-vline right"></div><div class="overlay-badge">${label}</div><div class="overlay-chip">${accent}</div>`;
        case 'measure_precision':
          return `<div class="overlay-line"></div><div class="overlay-vline left"></div><div class="overlay-vline right"></div><div class="overlay-badge">${label}</div><div class="overlay-chip">${accent}</div>`;
        case 'one_day_replace':
          const items = Array.isArray(overlay.items) && overlay.items.length ? overlay.items : [label, label, label];
          return `<div class="overlay-badge">${accent}</div>${items.slice(0, 3).map(item => `<div class="overlay-card">${esc(item)}</div>`).join('')}<div class="overlay-chip">${label}</div>`;
        case 'brightness_before_after':
          return `<div class="overlay-arrow"></div><div class="overlay-badge">Before</div><div class="overlay-chip">After</div>`;
        case 'robot_path':
          return `<div class="overlay-arrow"></div><div class="overlay-dot"></div><div class="overlay-badge">${label}</div><div class="overlay-chip">${accent}</div>`;
        case 'review_quote':
          return `<div class="overlay-chip">${label}</div><div class="overlay-badge">${accent}</div>`;
        case 'cta_checklist':
          return `<div class="overlay-chip first">${label}</div><div class="overlay-chip second">${accent}</div>`;
        default:
          return `<div class="overlay-chip">${label || accent}</div>`;
      }
    }

    function applyCaptionLayout(beat) {
      const layout = beat.caption_layout || {};
      const position = layout.position || 'center';
      const size = layout.size || 'medium';
      const align = layout.align || 'center';
      const theme = layout.theme || 'yellow';
      const accent = beat.caption_accent || {};
      const accentEnabled = accent.enabled === true && Array.isArray(beat.caption_emphasis) && beat.caption_emphasis.length > 0;
      const accentStyle = classSafe(accent.style || 'soft');
      caption.className = `caption pos-${position} size-${size} theme-${theme}${accentEnabled ? ` accent-keyword accent-${accentStyle}` : ''}`;
      caption.style.textAlign = align;
      if (accentEnabled) {
        const delay = Math.max(0, Math.min(Number(accent.delay_ms || 90), 150));
        caption.style.setProperty('--accent-delay-ms', `${delay}ms`);
      } else {
        caption.style.removeProperty('--accent-delay-ms');
      }
    }

    function classSafe(value) {
      return String(value || 'cut').toLowerCase().replace(/[^a-z0-9_-]+/g, '_');
    }

    function findBeat(time) {
      return beats.find(b => time >= b.time[0] && time < b.time[1]) || beats[beats.length - 1];
    }

    function progressFor(beat, time) {
      return clamp((time - beat.time[0]) / Math.max(beat.time[1] - beat.time[0], 0.001), 0, 1);
    }

    function setActiveList(beat) {
      document.querySelectorAll('.beat-item').forEach(el => {
        el.classList.toggle('active', el.dataset.id === beat.id);
      });
    }

    function enterBeat(beat) {
      activeBeatId = beat.id;
      stage.className = `stage ${beat.motion} t-${classSafe(beat.transition_in)} out-${classSafe(beat.transition_out)}`;
      caption.innerHTML = highlightCaption(beat.caption, beat.caption_emphasis, beat.caption_accent);
      applyCaptionLayout(beat);
      const overlay = beat.semantic_overlay || {};
      semanticOverlay.className = `semantic-overlay kind-${classSafe(overlay.kind || 'none')}`;
      semanticOverlay.innerHTML = semanticMarkup(overlay);
      motionNote.textContent = `${beat.motion} · ${beat.transition_in} → ${beat.transition_out}`;
      currentInfo.textContent = `${beat.id} · ${beat.phase} · ${beat.motion}`;
      setActiveList(beat);

      const mainUrl = assetFor(beat);
      const bgUrl = backgroundFor(beat);
      mainAsset.style.opacity = mainUrl ? 1 : 0;
      if (mainUrl) mainAsset.src = mainUrl;
      if (bgUrl) backdrop.src = bgUrl;

      paperBall.textContent = splitCaption(beat.caption)[0] || '문장군';
      productImg.src = assetUrls.product_thumbnail || '';
      reviewImg.src = assetUrls.review_capture || '';

      flashLayer.style.transition = 'none';
      flashLayer.style.opacity = 0;
      requestAnimationFrame(() => {
        flashLayer.style.transition = 'opacity 260ms ease';
      });
      stage.classList.remove('transition-hit');
      void stage.offsetWidth;
      stage.classList.add('transition-hit');
    }

    function renderAt(time) {
      const beat = findBeat(time);
      const p = progressFor(beat, time);
      const e = easeOutCubic(p);
      const s = easeInOut(p);
      const wave = Math.sin(p * Math.PI);
      const beatNumber = Number(String(beat.id).replace('b', '')) || 1;
      const direction = beatNumber % 2 === 0 ? 1 : -1;

      if (beat.id !== activeBeatId) enterBeat(beat);

      timeNow.textContent = time.toFixed(1);
      scrubber.value = String(time);

      mainAsset.style.filter = 'none';
      mainAsset.style.opacity = 1;
      mainAsset.style.transform = `scale(${1.035 + s * 0.05}) translate(${direction * (0.5 - s) * 16}px, ${(0.5 - s) * 10}px)`;
      backdrop.style.opacity = 0;
      paper.style.opacity = 0;
      productCard.style.opacity = 0;
      reviewCard.style.opacity = 0;
      semanticOverlay.style.opacity = 0;
      semanticOverlay.style.transform = 'translateY(12px) scale(0.98)';
      semanticOverlay.style.setProperty('--p', p.toFixed(4));
      semanticOverlay.style.setProperty('--wave', wave.toFixed(4));
      sparkle.style.opacity = 0;
      caption.style.opacity = 1;
      caption.style.transform = `translateY(${(1 - e) * 24}px) scale(${0.9 + e * 0.1})`;
      applyCaptionLayout(beat);

      if (beat.semantic_overlay && beat.semantic_overlay.kind) {
        semanticOverlay.style.opacity = Math.min(1, e * 1.35);
        semanticOverlay.style.transform = `translateY(${(1 - e) * 12}px) scale(${0.98 + e * 0.02})`;
      }

      if (beat.motion === 'paper_crumple_pop') {
        mainAsset.style.opacity = 0;
        paper.style.opacity = 1;
        paperBall.style.transform = `rotate(${-18 + e * 16}deg) scale(${0.58 + e * 0.56})`;
        caption.style.opacity = 0;
      }

      if (beat.motion === 'keyword_pop') {
        mainAsset.style.transform = `scale(${1.05 + s * 0.035 + wave * 0.018}) translate(${direction * (0.5 - s) * 18}px, ${Math.sin(p * 10) * 2}px)`;
        if (beat.phase.includes('problem')) mainAsset.style.filter = 'brightness(0.82) contrast(1.05)';
        caption.style.transform = `scale(${0.88 + e * 0.16 + wave * 0.035}) rotate(${Math.sin(p * Math.PI * 2) * 0.6}deg)`;
      }

      if (beat.motion === 'before_after_flash') {
        mainAsset.style.transform = `scale(${1.02 + s * 0.075}) translateY(${(0.5 - s) * 12}px)`;
        sparkle.style.opacity = 0.75 * wave;
        flashLayer.style.opacity = p < 0.2 ? 1 - p / 0.2 : 0;
        caption.style.transform = `translateY(${(1 - e) * 18}px) scale(${0.9 + e * 0.12})`;
      }

      if (beat.motion === 'heat_haze_problem') {
        mainAsset.style.filter = `brightness(${0.84 + wave * 0.05}) contrast(1.08) saturate(0.92)`;
        mainAsset.style.transform = `scale(${1.08 + s * 0.035}) translate(${Math.sin(p * 34) * 4}px, ${Math.cos(p * 23) * 5}px) skewX(${Math.sin(p * 18) * 0.7}deg)`;
        flashLayer.style.opacity = p < 0.18 ? 0.28 * (1 - p / 0.18) : 0;
        caption.style.transform = `scale(${0.94 + wave * 0.09}) translateY(${Math.sin(p * 18) * 3}px)`;
      }

      if (beat.motion === 'cool_air_reveal') {
        mainAsset.style.filter = `brightness(${1.02 + wave * 0.1}) contrast(1.02) saturate(1.04)`;
        mainAsset.style.transform = `scale(${1.045 + s * 0.055}) translateY(${(0.5 - s) * 20}px)`;
        sparkle.style.opacity = 0.36 * wave;
        wipeLayer.style.opacity = 0.32 * wave;
        wipeLayer.style.transform = `translateX(${-110 + p * 220}%)`;
        caption.style.transform = `translateY(${(1 - e) * 20}px) scale(${0.92 + e * 0.12})`;
      }

      if (beat.motion === 'space_anxiety_pull') {
        mainAsset.style.filter = 'brightness(0.9) contrast(1.04)';
        mainAsset.style.transform = `scale(${1.12 - s * 0.035}) translate(${direction * (0.5 - s) * 24}px, ${(0.5 - s) * 32}px)`;
        caption.style.transform = `scale(${0.9 + e * 0.1}) translateY(${(1 - e) * 24}px)`;
      }

      if (beat.motion === 'air_leak_wipe') {
        mainAsset.style.filter = `brightness(${0.92 + wave * 0.05}) contrast(1.05)`;
        mainAsset.style.transform = `scale(${1.07 + s * 0.03}) translate(${direction * (0.5 - s) * 28}px, ${(0.5 - s) * 16}px)`;
        wipeLayer.style.opacity = 0.45 * wave;
        wipeLayer.style.transform = `translateX(${-120 + p * 240}%)`;
        caption.style.transform = `scale(${0.95 + wave * 0.06})`;
      }

      if (beat.motion === 'clean_room_pan') {
        mainAsset.style.filter = `brightness(${1.01 + wave * 0.06}) contrast(1.01)`;
        mainAsset.style.transform = `scale(${1.03 + s * 0.06}) translate(${direction * (0.5 - s) * 18}px, ${(0.5 - s) * 22}px)`;
        caption.style.transform = `translateY(${(1 - e) * 22}px) scale(${0.93 + e * 0.09})`;
      }

      if (beat.motion === 'entry_path_pan') {
        mainAsset.style.transform = `scale(${1.09 + s * 0.025}) translate(${direction * 10}px, ${(0.5 - s) * 70}px)`;
        caption.style.transform = `translateY(${(1 - e) * 26}px) scale(${0.94 + e * 0.06})`;
      }

      if (beat.motion === 'problem_shake') {
        mainAsset.style.filter = 'brightness(0.86) contrast(1.08)';
        mainAsset.style.transform = `scale(${1.08 + s * 0.025}) translate(${Math.sin(p * 38) * 5}px, ${Math.cos(p * 31) * 4}px)`;
        caption.style.transform = `scale(${0.96 + wave * 0.08}) translateX(${Math.sin(p * 26) * 3}px)`;
      }

      if (beat.motion === 'rejection_stamp') {
        mainAsset.style.filter = `brightness(${0.74 + wave * 0.06}) contrast(1.18) saturate(0.76)`;
        mainAsset.style.transform = `scale(${1.08 + s * 0.035}) translate(${Math.sin(p * 26) * 7}px, ${Math.cos(p * 18) * 4}px)`;
        flashLayer.style.opacity = p < 0.16 ? 0.55 * (1 - p / 0.16) : 0;
        caption.style.transform = `rotate(${-5 + Math.sin(p * 18) * 1.2}deg) scale(${0.9 + e * 0.13 + wave * 0.03})`;
      }

      if (beat.motion === 'obstacle_route_pan') {
        mainAsset.style.filter = `brightness(${0.82 + wave * 0.05}) contrast(1.12) saturate(0.9)`;
        mainAsset.style.transform = `scale(${1.13 + s * 0.035}) translate(${direction * (0.5 - s) * 34}px, ${(0.5 - s) * 90}px)`;
        wipeLayer.style.opacity = 0.34 * wave;
        wipeLayer.style.transform = `translateY(${-120 + p * 240}%) rotate(90deg)`;
        caption.style.transform = `translateY(${(1 - e) * 22}px) scale(${0.93 + e * 0.08})`;
      }

      if (beat.motion === 'precision_scan') {
        mainAsset.style.filter = `brightness(${0.96 + wave * 0.06}) contrast(1.09)`;
        mainAsset.style.transform = `scale(${1.08 + s * 0.06}) translate(${direction * (0.5 - s) * 26}px, ${(0.5 - s) * 34}px)`;
        wipeLayer.style.opacity = 0.48 * wave;
        wipeLayer.style.transform = `translateX(${-120 + p * 240}%)`;
        caption.style.transform = `translateY(${(1 - e) * 18}px) scale(${0.94 + e * 0.08})`;
      }

      if (beat.motion === 'construction_focus') {
        mainAsset.style.filter = `brightness(${0.9 + wave * 0.06}) contrast(1.14) saturate(0.95)`;
        mainAsset.style.transform = `scale(${1.06 + s * 0.055}) translate(${Math.sin(p * 12) * 5}px, ${(0.5 - s) * 22}px)`;
        caption.style.transform = `scale(${0.93 + e * 0.1}) translateY(${(1 - e) * 20}px)`;
      }

      if (beat.motion === 'mission_clear_reveal') {
        mainAsset.style.filter = `brightness(${1.0 + wave * 0.08}) contrast(1.04) saturate(1.03)`;
        mainAsset.style.transform = `scale(${1.03 + s * 0.06}) translate(${direction * (0.5 - s) * 18}px, ${(0.5 - s) * 20}px)`;
        sparkle.style.opacity = 0.28 * wave;
        caption.style.transform = `rotate(${-2 + e * 2}deg) scale(${0.9 + e * 0.12})`;
      }

      if (beat.motion === 'detail_probe') {
        mainAsset.style.filter = `brightness(${0.98 + wave * 0.05}) contrast(1.06)`;
        mainAsset.style.transform = `scale(${1.12 + s * 0.04}) translate(${direction * (0.5 - s) * 48}px, ${(0.5 - s) * 48}px)`;
        caption.style.transform = `translateY(${(1 - e) * 18}px) scale(${0.94 + e * 0.07})`;
      }

      if (beat.motion === 'measure_scan') {
        mainAsset.style.transform = `scale(${1.045 + s * 0.085}) translate(${direction * (0.5 - s) * 22}px, ${(0.5 - s) * 28}px)`;
        caption.style.transform = `translateY(${(1 - e) * 18}px) scale(${0.94 + e * 0.08})`;
      }

      if (beat.motion === 'product_card_flash') {
        backdrop.style.opacity = 1;
        mainAsset.style.opacity = 0;
        productCard.style.opacity = e;
        productCard.style.transform = `translate(-50%, -50%) scale(${0.72 + e * 0.28 + wave * 0.018}) rotate(${-5 + e * 5}deg)`;
        backdrop.style.transform = `scale(${1.1 + s * 0.04}) translateY(${(0.5 - s) * 18}px)`;
        flashLayer.style.opacity = p < 0.22 ? 0.8 * (1 - p / 0.22) : 0;
        caption.style.transform = `translateY(${(1 - e) * 18}px) scale(${0.94 + e * 0.06})`;
      }

      if (beat.motion === 'clean_glow_reveal') {
        mainAsset.style.filter = `brightness(${1.02 + wave * 0.12}) contrast(1.02)`;
        mainAsset.style.transform = `scale(${1.02 + s * 0.07}) translate(${direction * (0.5 - s) * 14}px, ${(0.5 - s) * 12}px)`;
        sparkle.style.opacity = 0.46 * wave;
        caption.style.transform = `scale(${0.9 + e * 0.13})`;
      }

      if (beat.motion === 'review_capture_scroll') {
        backdrop.style.opacity = 1;
        mainAsset.style.opacity = 0;
        reviewCard.style.opacity = e;
        reviewCard.style.transform = `translate(-50%, ${-50 - (1 - e) * -12}%) scale(${0.88 + e * 0.12})`;
        backdrop.style.transform = `scale(${1.1 + s * 0.025}) translateY(${(0.5 - s) * 18}px)`;
        caption.style.opacity = easeOutCubic((p - 0.32) / 0.45);
        caption.style.transform = `translateY(${(1 - e) * 26}px) scale(${0.92 + e * 0.08})`;
      }

      const captionDelay = Number(beat.caption_delay_sec || 0);
      if (captionDelay > 0) {
        const localTime = Math.max(0, time - beat.time[0]);
        const gate = easeOutCubic((localTime - captionDelay) / 0.24);
        const currentOpacity = Number(caption.style.opacity || 1);
        caption.style.opacity = Math.max(0, Math.min(1, currentOpacity * gate));
      }
    }

    function tick() {
      const time = isScrubbing ? manualTime : Math.min(audio.currentTime || manualTime, totalDuration);
      renderAt(time);
      if (!audio.paused) requestAnimationFrame(tick);
    }

    playBtn.addEventListener('click', async () => {
      if (audio.paused) {
        if (audio.currentTime >= totalDuration - 0.05) audio.currentTime = 0;
        await audio.play();
        playBtn.textContent = '일시정지';
        requestAnimationFrame(tick);
      } else {
        audio.pause();
        playBtn.textContent = '재생';
        renderAt(audio.currentTime);
      }
    });

    restartBtn.addEventListener('click', () => {
      audio.pause();
      audio.currentTime = 0;
      manualTime = 0;
      playBtn.textContent = '재생';
      renderAt(0);
    });

    scrubber.addEventListener('input', () => {
      isScrubbing = true;
      manualTime = Number(scrubber.value);
      audio.currentTime = manualTime;
      renderAt(manualTime);
    });

    scrubber.addEventListener('change', () => {
      isScrubbing = false;
      audio.currentTime = Number(scrubber.value);
      renderAt(audio.currentTime);
      if (!audio.paused) requestAnimationFrame(tick);
    });

    audio.addEventListener('ended', () => {
      playBtn.textContent = '재생';
      renderAt(totalDuration);
    });

    function buildBeatList() {
      for (const beat of beats) {
        const item = document.createElement('div');
        item.className = 'beat-item';
        item.dataset.id = beat.id;
        item.innerHTML = `
          <div class="beat-meta"><span>${beat.id} · ${beat.phase}</span><span>${beat.time[0].toFixed(1)}-${beat.time[1].toFixed(1)}s</span></div>
          <div class="beat-caption">${String(beat.caption).replace(/</g, '&lt;')}</div>
          <div class="beat-asset">${beat.asset} · ${beat.motion}</div>
        `;
        item.addEventListener('click', () => {
          audio.currentTime = beat.time[0] + 0.02;
          manualTime = audio.currentTime;
          renderAt(manualTime);
          if (!audio.paused) requestAnimationFrame(tick);
        });
        beatList.appendChild(item);
      }
    }

    buildBeatList();
    const initialTime = Number(new URLSearchParams(window.location.search).get('t'));
    if (Number.isFinite(initialTime) && initialTime >= 0) {
      manualTime = Math.min(initialTime, totalDuration);
      audio.currentTime = manualTime;
      renderAt(manualTime);
    } else {
      renderAt(0);
    }
  </script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipe", required=True, help="edit_recipe_v2.json path")
    args = parser.parse_args()
    output_path = build_preview(Path(args.recipe))
    print(output_path)


if __name__ == "__main__":
    main()
