from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import generate

from .review_analyzer import load_review_body
from .timeline_planner import build_planning_recipe, captions_to_srt, planning_to_edit_recipe


def _audio_duration(path: Path) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
        )
        return float(result.stdout.decode("utf-8", errors="replace").strip())
    except Exception:
        return None


def _split_atempo(value: float) -> list[float]:
    factors: list[float] = []
    current = value
    while current > 2.0:
        factors.append(2.0)
        current /= 2.0
    while current < 0.5:
        factors.append(0.5)
        current /= 0.5
    factors.append(round(current, 6))
    return factors


def _fit_audio_to_duration(input_path: Path, output_path: Path, target_seconds: float) -> None:
    duration = _audio_duration(input_path)
    if not duration or duration <= 0:
        raise RuntimeError(f"Cannot measure audio duration: {input_path}")
    ratio = duration / target_seconds
    filters = ",".join(f"atempo={factor}" for factor in _split_atempo(ratio))
    subprocess.run(
        [
            "ffmpeg",
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
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _final_script_text() -> str:
    return """---
review_id: 4991620520
review_number: 4991620520
product_order_number: 2026052855842211
source_file: 005_여름에어컨.txt
review_sequence: 005
created: 2026-06-11
content_type: 사연극
---

# 에어컨 풀가동해도 덥던 거실, 설치 후 달라진 집

## 스크립트

### [HOOK] 0~2초
에어컨 풀가동해도 거실이 덥다면?
> 내레이션: 에어컨을 풀로 틀어도 거실이 덥다면,

### [SCENE] 2~5초
좁아 보일까 봐 미뤘던 중문
> 내레이션: 좁아 보일까 봐 설치를 미뤘던 집.

### [CONFLICT] 5~9초
여름엔 달랐습니다
> 내레이션: 그런데 여름이 되자 에어컨을 틀어도 덥더랍니다.

### [SOLUTION] 9~12초
그래서 선택한 현관 중문
> 내레이션: 그래서 선택한 건 현관 중문.

### [TWIST] 12~16초
설치 후 확실히 더 시원
> 내레이션: 설치 후 에어컨을 켜니 확실히 더 시원하다고 해요.

### [CLOSE] 16~23초
실제 리뷰 확인 후, 우리 집도 가능할까?
> 내레이션: 실제 리뷰에도 이렇게 남았습니다. 우리 집도 가능할지, 무료 방문 실측으로 먼저 확인해보세요. 문장군 리뷰에서 가져왔어요.

## 캡션
에어컨을 계속 틀어도 거실이 시원해지지 않는다면, 현관 쪽 공기 흐름을 한 번 의심해볼 만합니다.
이번 리뷰도 처음에는 “집이 좁아 보이지 않을까?” 때문에 중문 설치를 망설였던 집이에요.
겨울에는 크게 불편하지 않았지만, 여름이 되자 에어컨을 풀가동해도 더운 느낌이 계속 남았다고 합니다.
설치 후에는 에어컨 바람이 훨씬 잘 머무는 체감이 있었고, 리뷰에는 “진작할 걸”이라는 말이 남았습니다.
예쁘게 보이는 것도 중요하지만, 여름에는 냉방 효율과 생활 체감이 더 크게 다가오기도 해요.
우리 집도 현관 쪽 열기 때문에 거실이 덥게 느껴진다면 이 사례를 저장해두세요.
무료 실측으로 구조에 맞는 중문 설치 가능 여부와 냉방 동선을 먼저 확인할 수 있습니다.

## 해시태그
#문장군 #문장군중문 #문장군시공 #현관중문 #중문시공 #중문인테리어 #3연동중문 #아파트중문 #단열중문 #중문추천 #무료실측 #방문실측 #에어컨효율 #냉방효율 #냉방비절약 #여름인테리어 #여름집관리 #현관인테리어 #아파트인테리어 #거실인테리어 #집꾸미기 #홈스타일링 #리모델링
"""


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_narration(path: Path, planning: dict) -> None:
    lines = [
        f"# {planning['project']['title']} Narration",
        "",
        "## Selected Hook",
        planning["selected_hook"]["text"],
        "",
        "## Narration",
    ]
    for scene in planning["scenes"]:
        lines.append(f"- {scene['scene_id']} / {scene['role']} / {scene['time'][0]}~{scene['time'][1]}s")
        lines.append(f"  {scene['narration']}")
    lines.extend(
        [
            "",
            "## Review Quote",
            planning["review_proof"]["selected_quote"],
            "",
            "## CTA",
            planning["cta"]["primary_text"],
            planning["cta"]["secondary_text"],
            "",
            "## Sync Note",
            "This narration targets a new 20-23s ad voice. The sync-safe edit recipe can temporarily use the existing voice.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_005_pilot(package_dir: Path, review_path: Path) -> dict[str, Path]:
    package_dir = package_dir.resolve()
    review_path = review_path.resolve()

    base_recipe_path = package_dir / "005_여름에어컨_edit_recipe_v2.json"
    base_recipe = json.loads(base_recipe_path.read_text(encoding="utf-8"))
    review_text = review_path.read_text(encoding="utf-8")

    planning = build_planning_recipe(
        review_id="005_여름에어컨",
        package_dir=str(package_dir),
        image_dir=base_recipe["source"]["image_dir"],
        review_text=review_text,
        voice=base_recipe["source"]["voice"],
        existing_script=base_recipe["source"]["script"],
        existing_srt=base_recipe["source"]["srt"],
        asset_roles=base_recipe["asset_roles"],
    )

    voice_path = package_dir / base_recipe["source"]["voice"]
    duration = _audio_duration(voice_path)
    if duration is None or duration <= 0:
        raise RuntimeError(f"Cannot measure existing voice duration: {voice_path}")
    edit_recipe = planning_to_edit_recipe(
        planning,
        base_edit_recipe=base_recipe,
        current_voice_duration_sec=duration,
    )

    outputs = {
        "planning_recipe": package_dir / "005_여름에어컨_ad_v2_planning_recipe.json",
        "edit_recipe": package_dir / "005_여름에어컨_ad_v2_edit_recipe.json",
        "narration": package_dir / "005_여름에어컨_ad_v2_narration.md",
        "srt": package_dir / "005_여름에어컨_ad_v2.srt",
    }
    planning["outputs"] = {key: str(value) for key, value in outputs.items()}
    planning["audio_sync"]["current_voice_duration_sec"] = duration

    _write_json(outputs["planning_recipe"], planning)
    _write_json(outputs["edit_recipe"], edit_recipe)
    _write_narration(outputs["narration"], planning)
    outputs["srt"].write_text(captions_to_srt(planning), encoding="utf-8")
    return outputs


def build_005_final_html_inputs(package_dir: Path, review_path: Path) -> dict[str, Path]:
    package_dir = package_dir.resolve()
    review_path = review_path.resolve()

    base_recipe_path = package_dir / "005_여름에어컨_edit_recipe_v2.json"
    base_recipe = json.loads(base_recipe_path.read_text(encoding="utf-8"))
    review_text = review_path.read_text(encoding="utf-8")

    script_text = _final_script_text()
    issues = generate.validate_script(script_text)
    failures = [issue for issue in issues if issue.startswith("[FAIL]")]
    if failures:
        raise ValueError("v2 final script validation failed:\n" + "\n".join(failures))

    outputs = {
        "script": package_dir / "005_여름에어컨_ad_v2_final_script.md",
        "voice": package_dir / "005_여름에어컨_ad_v2_final_voice.mp3",
        "voice_source": package_dir / "005_여름에어컨_ad_v2_final_tts_voice.mp3",
        "planning_recipe": package_dir / "005_여름에어컨_ad_v2_final_planning_recipe.json",
        "edit_recipe": package_dir / "005_여름에어컨_ad_v2_final_edit_recipe.json",
        "srt": package_dir / "005_여름에어컨_ad_v2_final.srt",
        "narration": package_dir / "005_여름에어컨_ad_v2_final_narration.md",
    }
    outputs["script"].write_text(script_text, encoding="utf-8")

    generated_voice = generate.generate_voice(
        script_text,
        package_dir,
        artifact_stem="005_여름에어컨_ad_v2_final_tts",
    )
    _fit_audio_to_duration(generated_voice, outputs["voice"], 23.0)

    final_duration = _audio_duration(outputs["voice"])
    if final_duration is None or final_duration <= 0:
        raise RuntimeError(f"Cannot measure final voice duration: {outputs['voice']}")
    planning = build_planning_recipe(
        review_id="005_여름에어컨",
        package_dir=str(package_dir),
        image_dir=base_recipe["source"]["image_dir"],
        review_text=review_text,
        voice=outputs["voice"].name,
        existing_script=outputs["script"].name,
        existing_srt=outputs["srt"].name,
        asset_roles=base_recipe["asset_roles"],
        variant_id="ad_v2_final",
    )
    planning["source"]["existing_voice"] = outputs["voice"].name
    planning["source"]["existing_script"] = outputs["script"].name
    planning["source"]["existing_srt"] = outputs["srt"].name
    planning["audio_sync"] = {
        "source_of_truth": "planning_recipe",
        "mode": "final_voice_exact_duration",
        "target_duration_sec": 23.0,
        "measured_duration_sec": round(final_duration, 3),
        "requires_new_voice_for_target_duration": False,
    }
    planning["outputs"] = {key: str(value) for key, value in outputs.items()}

    edit_recipe = planning_to_edit_recipe(
        planning,
        base_edit_recipe=base_recipe,
        current_voice_duration_sec=final_duration,
    )
    edit_recipe["title"] = "005 여름에어컨 광고용 v2 final HTML"
    edit_recipe["description"] = "새 v2 내레이션/음성에 맞춘 23초 광고용 HTML 프리뷰 레시피입니다. MP4 렌더 전 검수용입니다."
    edit_recipe["source"]["script"] = outputs["script"].name
    edit_recipe["source"]["srt"] = outputs["srt"].name
    edit_recipe["source"]["voice"] = outputs["voice"].name
    edit_recipe["audio_plan"]["narration"] = outputs["voice"].name
    edit_recipe["audio_plan"]["sync_policy"] = {
        "mode": "final_voice_exact_duration",
        "planned_target_duration_sec": 23.0,
        "final_voice_duration_sec": round(final_duration, 3),
        "render_duration_sec": round(final_duration, 3),
        "scale_factor": round(final_duration / 23.0, 4),
        "note": "v2 final voice generated from the 23s ad narration.",
    }

    _write_json(outputs["planning_recipe"], planning)
    _write_json(outputs["edit_recipe"], edit_recipe)
    _write_narration(outputs["narration"], planning)
    outputs["srt"].write_text(captions_to_srt(planning), encoding="utf-8")
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Build 005_여름에어컨 ad v2 pilot recipes.")
    parser.add_argument(
        "--package-dir",
        default="output/inbox_20260609/005_여름에어컨_20260609_111335",
    )
    parser.add_argument(
        "--review",
        default="reviews/inbox_20260609/005_여름에어컨.txt",
    )
    parser.add_argument(
        "--final-html-inputs",
        action="store_true",
        help="Generate new v2 final script, voice, planning recipe, and edit recipe for HTML preview.",
    )
    args = parser.parse_args()

    if args.final_html_inputs:
        outputs = build_005_final_html_inputs(Path(args.package_dir), Path(args.review))
    else:
        outputs = build_005_pilot(Path(args.package_dir), Path(args.review))
    for key, path in outputs.items():
        print(f"{key}: {path}")


if __name__ == "__main__":
    main()
