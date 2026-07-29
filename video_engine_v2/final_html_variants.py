from __future__ import annotations

import argparse
import copy
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import generate

from .timeline_planner import captions_to_srt, planning_to_edit_recipe
from .pilot_005 import _fit_audio_to_duration, _write_json, _write_narration


@dataclass(frozen=True)
class VariantConfig:
    review_id: str
    package_dir: str
    review_path: str
    base_recipe_name: str
    variant_id: str
    title: str
    target_duration: float
    content_purpose: str
    video_type: str
    script_text: str
    scenes: list[dict[str, Any]]
    selected_quote: str
    cta_primary: str
    cta_secondary: str
    asset_roles: dict[str, str] | None = None
    image_dir: str | None = None


def _audio_duration(path: Path) -> float:
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
        text=True,
    )
    return float(result.stdout.strip())


def _source_body(review_path: Path) -> str:
    text = review_path.read_text(encoding="utf-8")
    if "내용:" in text:
        return text.split("내용:", 1)[1].strip()
    return text.strip()


def _planning_from_config(config: VariantConfig, package_dir: Path, base_recipe: dict[str, Any]) -> dict[str, Any]:
    review_body = _source_body(Path(config.review_path))
    return {
        "schema_version": "2.0",
        "project": {
            "review_id": config.review_id,
            "variant_id": config.variant_id,
            "title": config.title,
            "created_at": "2026-06-11",
            "status": "draft",
        },
        "source": {
            "package_dir": str(package_dir),
            "image_dir": base_recipe["source"]["image_dir"],
            "review_text": review_body,
            "existing_script": f"{config.review_id}_{config.variant_id}_script.md",
            "existing_voice": f"{config.review_id}_{config.variant_id}_voice.mp3",
            "existing_srt": f"{config.review_id}_{config.variant_id}.srt",
        },
        "strategy": {
            "content_purpose": config.content_purpose,
            "video_type": config.video_type,
            "target_duration_sec": config.target_duration,
            "platform": "instagram_reels",
            "primary_goal": "lead" if config.content_purpose != "brand_expertise" else "trust",
            "cta_strength": "medium",
            "tone": "field-based, proof-first, not overhyped",
        },
        "analysis": {
            "customer_problem": "",
            "before_pain": "",
            "after_change": "",
            "customer_emotion": [],
            "strongest_review_quotes": [{"edited": config.selected_quote, "selected": True, "risk": "low"}],
            "proof_points": ["actual_review", "field_photos", "before_after_photos"],
            "risk_flags": ["avoid_unsupported_absolute_claims"],
        },
        "hooks": [],
        "selected_hook": {
            "text": config.scenes[0]["caption"]["text"].replace("\n", " "),
            "selection_reason": "첫 장면에서 문제와 타깃을 바로 지정한다.",
        },
        "timeline": {
            "target_duration_sec": config.target_duration,
            "structure": [{"role": scene["role"], "range": scene["time"]} for scene in config.scenes],
            "energy_curve": [[scene["time"][0], scene.get("energy_level", "medium")] for scene in config.scenes],
        },
        "scenes": config.scenes,
        "review_proof": {
            "source_capture_role": "review_capture",
            "source_capture_file": base_recipe["asset_roles"].get("review_capture"),
            "selected_quote": config.selected_quote,
            "display_mode": "blurred_capture_plus_large_quote",
            "time": next(scene["time"] for scene in config.scenes if scene["role"] == "review_proof"),
        },
        "cta": {
            "time": config.scenes[-1]["time"],
            "primary_text": config.cta_primary,
            "secondary_text": config.cta_secondary,
            "tone": "consultative",
            "avoid": ["fake_urgency", "guaranteed_outcome"],
        },
        "narration": {
            "mode": "timeline_first",
            "text": "\n".join(scene["narration"] for scene in config.scenes),
        },
        "audio_sync": {},
        "render_recipe": {},
        "outputs": {},
        "quality_checks": {
            "hook_complete_sentence": True,
            "review_quote_separated_from_capture": True,
            "cta_has_own_scene": True,
            "absolute_claims_avoided": True,
        },
    }


def _write_outputs(config: VariantConfig) -> dict[str, Path]:
    package_dir = Path(config.package_dir).resolve()
    base_recipe_path = package_dir / config.base_recipe_name
    if base_recipe_path.exists():
        base_recipe = json.loads(base_recipe_path.read_text(encoding="utf-8"))
    elif config.asset_roles and config.image_dir:
        base_recipe = {
            "source": {
                "package_dir": str(package_dir),
                "script": "",
                "srt": "",
                "voice": "",
                "image_dir": config.image_dir,
                "reference_edit": None,
            },
            "style_dna": {
                "video_type": config.video_type,
                "content_purpose": config.content_purpose,
                "tone": "review_story_reels",
                "caption_style": "large_yellow_keyword",
                "font": "nelnasamchae.ttf",
                "brand_badge": "none",
                "default_image_motion": "ken_burns",
                "transition_energy": "medium_high",
                "blur_policy": "only_when_layering_cards",
                "proof_ending": "review_capture",
            },
            "asset_roles": config.asset_roles,
            "audio_plan": {},
            "render_targets": {
                "preview": {"fps": 12, "resolution": [720, 1280]},
                "final": {"fps": 30, "resolution": [1080, 1920]},
            },
        }
    else:
        raise FileNotFoundError(f"Base recipe missing and no synthetic assets supplied: {base_recipe_path}")

    issues = generate.validate_script(config.script_text)
    failures = [issue for issue in issues if issue.startswith("[FAIL]")]
    if failures:
        raise ValueError(f"{config.review_id} script validation failed:\n" + "\n".join(failures))

    outputs = {
        "script": package_dir / f"{config.review_id}_{config.variant_id}_script.md",
        "voice": package_dir / f"{config.review_id}_{config.variant_id}_voice.mp3",
        "voice_source": package_dir / f"{config.review_id}_{config.variant_id}_tts_voice.mp3",
        "planning_recipe": package_dir / f"{config.review_id}_{config.variant_id}_planning_recipe.json",
        "edit_recipe": package_dir / f"{config.review_id}_{config.variant_id}_edit_recipe.json",
        "srt": package_dir / f"{config.review_id}_{config.variant_id}.srt",
        "narration": package_dir / f"{config.review_id}_{config.variant_id}_narration.md",
    }
    outputs["script"].write_text(config.script_text, encoding="utf-8")

    generated_voice = generate.generate_voice(
        config.script_text,
        package_dir,
        artifact_stem=f"{config.review_id}_{config.variant_id}_tts",
    )
    _fit_audio_to_duration(generated_voice, outputs["voice"], config.target_duration)
    measured_duration = _audio_duration(outputs["voice"])

    planning = _planning_from_config(config, package_dir, base_recipe)
    planning["source"]["existing_script"] = outputs["script"].name
    planning["source"]["existing_voice"] = outputs["voice"].name
    planning["source"]["existing_srt"] = outputs["srt"].name
    planning["audio_sync"] = {
        "source_of_truth": "planning_recipe",
        "mode": "final_voice_exact_duration",
        "target_duration_sec": config.target_duration,
        "measured_duration_sec": round(measured_duration, 3),
        "requires_new_voice_for_target_duration": False,
    }
    planning["outputs"] = {key: str(value) for key, value in outputs.items()}

    edit_recipe = planning_to_edit_recipe(
        planning,
        base_edit_recipe=base_recipe,
        current_voice_duration_sec=measured_duration,
    )
    edit_recipe["title"] = f"{config.title} HTML"
    edit_recipe["description"] = f"{config.review_id} {config.variant_id} 새 음성 기준 HTML 프리뷰입니다. MP4 렌더 전 검수용입니다."
    edit_recipe["source"]["script"] = outputs["script"].name
    edit_recipe["source"]["srt"] = outputs["srt"].name
    edit_recipe["source"]["voice"] = outputs["voice"].name
    edit_recipe["audio_plan"]["narration"] = outputs["voice"].name
    edit_recipe["audio_plan"]["sync_policy"] = {
        "mode": "final_voice_exact_duration",
        "planned_target_duration_sec": config.target_duration,
        "final_voice_duration_sec": round(measured_duration, 3),
        "render_duration_sec": round(measured_duration, 3),
        "scale_factor": round(measured_duration / config.target_duration, 4),
        "note": "v2 final voice generated from the timeline-first narration.",
    }

    _write_json(outputs["planning_recipe"], planning)
    _write_json(outputs["edit_recipe"], edit_recipe)
    _write_narration(outputs["narration"], planning)
    outputs["srt"].write_text(captions_to_srt(planning), encoding="utf-8")
    return outputs


SCRIPT_010 = """---
review_id: 4988296656
review_number: 4988296656
product_order_number: 2026051963784331
source_file: 010_구축소음.txt
review_sequence: 010
created: 2026-06-11
content_type: 사연극
---

# 복도 소리 다 들리던 구축 빌라, 현관에서 달라졌습니다

## 스크립트

### [HOOK] 0~2초
복도 소리 다 들리는 구축 빌라라면?
> 내레이션: 복도 소리까지 집 안으로 들어오는 구축 빌라라면,

### [SCENE] 2~6초
벽 얇은 복도와 현관, 냄새까지 신경 쓰였습니다
> 내레이션: 벽은 얇고, 현관 쪽 소음과 냄새까지 계속 신경 쓰였다고 해요.

### [CONFLICT] 6~10초
수평도 벽도 쉽지 않았던 현장
> 내레이션: 게다가 구축이라 수평도 안 맞고 벽 비대칭도 심했습니다.

### [SOLUTION] 10~15초
현장에서 보고 가능한 방식으로 안내했습니다
> 내레이션: 그래도 현장에서 직접 보고, 가능한 방식으로 안내했습니다.

### [TWIST] 15~20초
이전보다 소음 체감이 줄고 깔끔해졌다는 리뷰
> 내레이션: 시공 후에는 이전에 비해 소음이 거의 안 들리고 깔끔하다는 리뷰가 남았습니다.

### [CLOSE] 20~25초
구축 빌라도 먼저 실측으로 확인하세요
> 내레이션: 구축 빌라도 조건이 다르니까, 무료 방문 실측으로 먼저 확인해보세요. 문장군 리뷰에서 가져왔어요.

## 캡션
복도 소리와 냄새가 현관을 타고 들어오는 구축 빌라라면, 중문은 인테리어보다 생활 문제에 가깝습니다.
이번 리뷰는 현관문 쪽 소음이 너무 크게 들려 층간소음보다 더 신경 쓰였던 집이에요.
외부 냄새까지 들어오니 집 안에 있어도 현관 쪽이 계속 불편했고, 오래된 구조라 수평과 벽 상태도 쉽지 않았습니다.
현장 실측 후 집에 맞는 방식으로 시공했고, 리뷰에는 소음 체감이 줄고 냄새도 덜해졌다는 후기가 남았습니다.
구축 현장은 같은 평형이라도 벽 두께, 수평, 현관 폭이 달라서 사진만 보고 단정하기 어렵습니다.
복도식 아파트나 구축 빌라에서 현관 소리 때문에 예민해진 적이 있다면 저장해두세요.
무료 방문 실측으로 우리 집은 어떤 방식이 가능한지 먼저 확인할 수 있습니다.

## 해시태그
#문장군 #문장군중문 #문장군시공 #현관중문 #중문시공 #중문인테리어 #3연동중문 #아파트중문 #슬라이딩중문 #구축빌라 #구축아파트 #복도식아파트 #구축리모델링 #현관소음 #소음차단 #냄새차단 #현관우풍 #단열중문 #중문효과 #무료실측 #방문실측 #현관인테리어 #집꾸미기 #리모델링
"""


SCENES_010 = [
    {
        "scene_id": "s01",
        "role": "hook",
        "time": [0.0, 2.0],
        "visual_source": {"role": "before_main"},
        "caption": {"text": "복도 소리 다 들리는\n구축 빌라라면?", "emphasis": ["구축 빌라"], "position": "center", "size": "large", "theme": "warning"},
        "narration": "복도 소리까지 집 안으로 들어오는 구축 빌라라면,",
        "energy_level": "high",
        "transition": "zoom_snap",
        "motion": "problem_shake",
    },
    {
        "scene_id": "s02",
        "role": "problem",
        "time": [2.0, 5.2],
        "visual_source": {"role": "place_exterior"},
        "caption": {"text": "벽 얇은\n오래된 구조", "emphasis": ["벽 얇은"], "position": "lower", "size": "medium", "theme": "warning"},
        "narration": "벽은 얇고, 현관 쪽 소음과 냄새까지 계속 신경 쓰였다고 해요.",
        "energy_level": "medium_high",
        "transition": "smooth_slide",
        "motion": "entry_path_pan",
    },
    {
        "scene_id": "s03",
        "role": "context",
        "time": [5.2, 8.6],
        "visual_source": {"role": "place_stairs"},
        "caption": {"text": "소리와 냄새가\n현관으로", "emphasis": ["현관"], "position": "center", "size": "medium", "theme": "warning"},
        "narration": "계단과 복도 생활 소리가 현관 쪽으로 이어지는 구조였습니다.",
        "energy_level": "high",
        "transition": "hit_flash",
        "motion": "problem_shake",
    },
    {
        "scene_id": "s04",
        "role": "process",
        "time": [8.6, 12.5],
        "visual_source": {"role": "measure_level"},
        "caption": {"text": "수평도 벽도\n쉽지 않았던 현장", "emphasis": ["쉽지"], "position": "upper", "size": "medium", "theme": "proof"},
        "narration": "게다가 구축이라 수평도 안 맞고 벽 비대칭도 심했습니다.",
        "energy_level": "proof",
        "transition": "smooth_slide",
        "motion": "measure_scan",
    },
    {
        "scene_id": "s05",
        "role": "solution",
        "time": [12.5, 16.0],
        "visual_source": {"role": "product_thumbnail"},
        "caption": {"text": "현장 보고\n가능한 방식으로", "emphasis": ["현장"], "position": "bottom", "size": "medium", "theme": "proof"},
        "narration": "그래도 현장에서 직접 보고, 가능한 방식으로 안내했습니다.",
        "energy_level": "medium_high",
        "transition": "card_pop",
        "motion": "product_card_flash",
    },
    {
        "scene_id": "s06",
        "role": "before_after",
        "time": [16.0, 19.5],
        "visual_source": {"role": "after_main"},
        "caption": {"text": "이전보다\n조용해진 체감", "emphasis": ["조용"], "position": "center", "size": "large", "theme": "clear"},
        "narration": "시공 후에는 이전에 비해 소음이 거의 안 들리고 깔끔하다는 리뷰가 남았습니다.",
        "energy_level": "high",
        "transition": "flash_glow",
        "motion": "clean_glow_reveal",
    },
    {
        "scene_id": "s07",
        "role": "review_proof",
        "time": [19.5, 22.4],
        "visual_source": {"role": "review_capture"},
        "background_visual_source": {"role": "after_main"},
        "caption": {"text": "“정말정말 좋습니다 ㅠ”", "emphasis": ["좋습니다"], "position": "center", "size": "large", "theme": "proof"},
        "narration": "실제 리뷰에도 정말정말 좋다는 말이 남았습니다.",
        "energy_level": "proof",
        "transition": "pop",
        "motion": "review_capture_scroll",
    },
    {
        "scene_id": "s08",
        "role": "cta",
        "time": [22.4, 25.0],
        "visual_source": {"role": "after_entry_view"},
        "caption": {"text": "구축 빌라도 가능할까?\n무료 방문 실측", "emphasis": ["무료 방문 실측"], "position": "center", "size": "medium", "theme": "cta"},
        "narration": "구축 빌라도 조건이 다르니까, 무료 방문 실측으로 먼저 확인해보세요.",
        "energy_level": "high_cta",
        "transition": "smooth_slide",
        "motion": "clean_room_pan",
    },
]


SCRIPT_004 = """---
review_id: 4991716765
review_number: 4991716765
product_order_number: 2026052221411701
source_file: 004_어려운시공.txt
review_sequence: 004
created: 2026-06-11
content_type: 사연극
---

# 다른 업체가 그냥 가던 현장, 끝까지 마무리했습니다

## 스크립트

### [HOOK] 0~2초
다른 업체가 그냥 가던 현장
> 내레이션: 다른 업체가 그냥 가던 현장이 있었습니다.

### [SCENE] 2~6초
거실 겸 방 사이를 나누고 싶었던 집
> 내레이션: 거실 겸 방 사이를 나누고 싶어 설치를 고민하던 집이었고요.

### [CONFLICT] 6~11초
주차도 자재 이동도 쉽지 않았습니다
> 내레이션: 지역 특성상 주차도 힘들고, 자재를 나르기도 쉽지 않았습니다.

### [SOLUTION] 11~16초
직접 보고 자세히 설명했습니다
> 내레이션: 그래도 직접 방문해서 보고, 가능한 방식과 조건을 자세히 설명했습니다.

### [TWIST] 16~22초
꼼꼼하고 말끔하게 마무리된 시공
> 내레이션: 시공도 꼼꼼하고 말끔하게 마무리되어, 리뷰를 기쁜 마음으로 썼다고 해요.

### [CLOSE] 22~27초
어려운 현장도 먼저 확인해드립니다
> 내레이션: 어려운 현장일수록 사진만 보고 판단하지 말고, 먼저 현장에서 확인해보세요. 문장군 리뷰에서 가져왔어요.

## 캡션
“여긴 어렵다”는 말을 들은 현장일수록, 사진보다 현장 확인이 먼저입니다.
이번 리뷰는 거실 겸 방 사이를 나누고 싶었지만 주차와 자재 이동 조건이 까다로웠던 집이에요.
다른 업체는 추가요금을 말하거나, 현장을 보고도 그냥 가버렸다는 이야기가 남아 있었습니다.
이 사례의 핵심은 예쁜 문보다 “어려운 조건을 어떻게 확인하고 마무리했는가”입니다.
직접 방문해 가능한 방식과 준비 조건을 설명했고, 시공 후에는 말끔하게 끝나 기쁜 마음으로 리뷰를 남겼다고 해요.
시공이 어렵다는 말을 들어본 집이라면 이 사례를 저장해두세요.
무료 방문 실측으로 우리 집 구조, 자재 이동, 설치 가능 여부를 먼저 확인할 수 있습니다.

## 해시태그
#문장군 #문장군중문 #문장군시공 #현관중문 #중문시공 #중문인테리어 #3연동중문 #아파트중문 #슬라이딩중문 #어려운시공 #시공현장 #방문실측 #무료실측 #공간분리 #거실인테리어 #방인테리어 #부분시공 #거주중인테리어 #살면서인테리어 #꼼꼼시공 #인테리어상담 #집꾸미기 #리모델링
"""


SCENES_004 = [
    {
        "scene_id": "s01",
        "role": "hook",
        "time": [0.0, 2.0],
        "visual_source": {"role": "place_entry"},
        "caption": {"text": "다른 업체가\n그냥 가던 현장", "emphasis": ["그냥 가던"], "position": "center", "size": "large", "theme": "stamp"},
        "narration": "다른 업체가 그냥 가던 현장이 있었습니다.",
        "energy_level": "high",
        "transition": "zoom_snap",
        "motion": "rejection_stamp",
    },
    {
        "scene_id": "s02",
        "role": "problem",
        "time": [2.0, 5.4],
        "visual_source": {"role": "before_main"},
        "caption": {"text": "거실 겸 방 사이\n공간을 나누고 싶었다", "emphasis": ["공간"], "position": "lower", "size": "medium", "theme": "warning"},
        "narration": "거실 겸 방 사이를 나누고 싶어 설치를 고민하던 집이었고요.",
        "energy_level": "medium",
        "transition": "smooth_slide",
        "motion": "space_anxiety_pull",
    },
    {
        "scene_id": "s03",
        "role": "context",
        "time": [5.4, 8.7],
        "visual_source": {"role": "place_stairs"},
        "caption": {"text": "주차도\n자재 이동도 난이도", "emphasis": ["난이도"], "position": "center", "size": "medium", "theme": "warning"},
        "narration": "지역 특성상 주차도 힘들고, 자재를 나르기도 쉽지 않았습니다.",
        "energy_level": "high",
        "transition": "hit_flash",
        "motion": "obstacle_route_pan",
    },
    {
        "scene_id": "s04",
        "role": "process",
        "time": [8.7, 12.2],
        "visual_source": {"role": "measure_width"},
        "caption": {"text": "직접 보고\n자세히 설명", "emphasis": ["직접"], "position": "upper", "size": "medium", "theme": "proof"},
        "narration": "그래도 직접 방문해서 보고, 가능한 방식과 조건을 자세히 설명했습니다.",
        "energy_level": "proof",
        "transition": "smooth_slide",
        "motion": "precision_scan",
    },
    {
        "scene_id": "s05",
        "role": "process",
        "time": [12.2, 16.0],
        "visual_source": {"role": "during_install"},
        "caption": {"text": "꼼꼼하게\n시공 중", "emphasis": ["꼼꼼"], "position": "lower", "size": "medium", "theme": "proof"},
        "narration": "시공도 꼼꼼하게 진행됐고, 마감까지 말끔하게 이어졌습니다.",
        "energy_level": "medium_high",
        "transition": "smooth_slide",
        "motion": "construction_focus",
    },
    {
        "scene_id": "s06",
        "role": "before_after",
        "time": [16.0, 20.3],
        "visual_source": {"role": "after_main"},
        "caption": {"text": "말끔하게\n마무리", "emphasis": ["마무리"], "position": "center", "size": "large", "theme": "clear"},
        "narration": "결과는 말끔하게 마무리되어, 리뷰를 기쁜 마음으로 썼다고 해요.",
        "energy_level": "clear",
        "transition": "flash_glow",
        "motion": "mission_clear_reveal",
    },
    {
        "scene_id": "s07",
        "role": "review_proof",
        "time": [20.3, 24.1],
        "visual_source": {"role": "review_capture"},
        "background_visual_source": {"role": "after_angle"},
        "caption": {"text": "“걱정할 필요가 없어요”", "emphasis": ["걱정"], "position": "center", "size": "large", "theme": "proof"},
        "narration": "실제 리뷰에는 이런 부분은 걱정할 필요가 없다고 남았습니다.",
        "energy_level": "proof",
        "transition": "pop",
        "motion": "review_capture_scroll",
    },
    {
        "scene_id": "s08",
        "role": "cta",
        "time": [24.1, 27.0],
        "visual_source": {"role": "after_front"},
        "caption": {"text": "어려운 현장도\n먼저 확인해드립니다", "emphasis": ["먼저 확인"], "position": "center", "size": "medium", "theme": "cta"},
        "narration": "어려운 현장일수록 사진만 보고 판단하지 말고, 먼저 현장에서 확인해보세요.",
        "energy_level": "high_cta",
        "transition": "smooth_slide",
        "motion": "clean_room_pan",
    },
]


SCRIPT_020 = """---
review_id: 4926794192
review_number: 4926794192
product_order_number: 2026012634098431
source_file: 020_로봇청소구축리모델링.txt
review_sequence: 020
created: 2026-06-11
content_type: 사연극
---

# 로봇청소기, 문턱에서 자꾸 막힌다면?

## 스크립트

### [HOOK] 0~2초
로봇청소기, 문턱에서 자꾸 막힌다면?
> 내레이션: 로봇청소기가 문턱에서 자꾸 막힌다면,

### [SCENE] 2~5초
오래된 방문이 집 분위기를 눌렀습니다
> 내레이션: 오래된 방문이 집 전체 분위기를 무겁게 만들 수 있습니다.

### [CONFLICT] 5~9초
문짝만이 아니라 문틀과 문턱까지 봐야 했습니다
> 내레이션: 이 집은 문짝만이 아니라 문틀과 문턱까지 함께 봐야 했고요.

### [SOLUTION] 9~12초
문틀과 폭까지 먼저 실측했습니다
> 내레이션: 그래서 문틀과 폭까지 먼저 실측했습니다.

### [TWIST] 12~16초
집 전체 방문을 하루 만에 교체했습니다
> 내레이션: 실측 후 집 전체 방문을 하루 만에 교체했습니다.

### [SCENE] 16~19초
집 분위기가 확 밝아졌습니다
> 내레이션: 교체 후에는 집 분위기가 훨씬 환해졌고,

### [CONFLICT] 19~22초
문턱 정리로 생활 동선까지 편해졌습니다
> 내레이션: 문턱까지 정리되면서 로봇청소기 사용에도 더 편해졌다고 해요.

### [TWIST] 22~25초
실제 리뷰에도 진작 교체할 걸
> 내레이션: 실제 리뷰에도 진작 교체할 걸 하는 생각이 들었다고 남았습니다.

### [CLOSE] 25~27초
문틀까지 봐야 할까? 무료 실측으로 확인
> 내레이션: 문틀까지 봐야 할지, 무료 실측으로 먼저 확인해보세요. 문장군 리뷰에서 가져왔어요.

## 캡션
로봇청소기가 문턱 앞에서 멈추는 집이라면, 방문 교체를 볼 때 문틀과 문턱까지 함께 봐야 합니다.
이번 리뷰는 구축으로 이사 온 뒤 오래된 방문이 계속 눈에 밟혔던 집이에요.
방문 하나가 집 분위기를 무겁게 만들고, 문턱은 로봇청소기와 생활 동선에도 은근한 불편을 만들었습니다.
문틀까지 포함해 집 전체 방문을 하루 만에 교체했고, 문턱까지 정리되면서 분위기와 동선이 함께 좋아졌다는 후기가 남았습니다.
아기 키우는 집이나 로봇청소기를 쓰는 집이라면 “문짝만 바꿀지, 문틀까지 볼지”가 꽤 중요합니다.
구축 이사 후 오래된 방문과 문턱이 계속 신경 쓰인다면 저장해두세요.
무료 실측으로 우리 집은 문짝만 가능한지, 문틀과 문턱까지 봐야 하는지 먼저 확인할 수 있습니다.

## 해시태그
#문장군 #문장군중문 #문장군시공 #방문교체 #문짝교체 #문틀교체 #문턱제거 #방문인테리어 #도어교체 #ABS도어 #로봇청소기 #로봇청소기문턱 #아기있는집 #구축리모델링 #구축아파트 #이사준비 #새집인테리어 #아파트인테리어 #무료실측 #방문실측 #집꾸미기 #홈스타일링 #리모델링
"""


SCRIPT_033 = """---
review_id: 4976120382
review_number: 4976120382
product_order_number: 2026050936782031
source_file: 033_소음차단냄새먼지.txt
review_sequence: 033
created: 2026-06-12
content_type: 사연극
---

# 현관 소리와 냄새, 설치 후 분위기까지 달라졌습니다

## 스크립트

### [HOOK] 0~2초
현관에서 소리랑 냄새가 들어온다면?
> 내레이션: 현관에서 소리랑 냄새가 같이 들어온다면,

### [SCENE] 2~6초
설치 후 집 분위기가 확 달라졌습니다
> 내레이션: 이 리뷰는 설치 후 집 분위기가 확 달라졌다는 이야기입니다.

### [CONFLICT] 6~11초
브론즈 유리라 답답함보다 은은함
> 내레이션: 브론즈 강화유리는 답답하지 않고, 조명 받을 때 은은한 느낌이 살아났고요.

### [SOLUTION] 11~16초
3연동에 댐퍼까지 조용하게
> 내레이션: 3연동 문은 부드럽게 움직이고, 댐퍼 덕분에 닫힐 때도 조용했다고 해요.

### [TWIST] 16~22초
실사용 후 소음과 냄새도 체감됐습니다
> 내레이션: 실사용 후에는 냄새 차단과 소음 감소에도 도움이 되는 느낌이었다고 남았습니다.

### [CLOSE] 22~27초
폭과 구조는 무료 방문 실측으로 먼저 확인
> 내레이션: 현관 폭과 구조는 집마다 다르니까, 무료 방문 실측으로 먼저 확인해보세요. 문장군 리뷰에서 가져왔어요.

## 캡션
현관에서 복도 소리와 냄새가 같이 들어온다면, 이 리뷰는 저장해둘 만합니다.
이번 집은 브론즈 강화유리 3연동 시공 후 집 분위기가 확 달라졌다는 후기를 남겼어요.
답답해 보일 걱정과 달리 개방감이 있었고, 조명 받을 때 은은하게 고급스러운 느낌이 살아났다고 합니다.
댐퍼가 들어가 문 닫힐 때 쾅 소리가 덜하고, 실제 사용 후에는 냄새 차단과 소음 감소에도 도움 되는 느낌이었다고 해요.
폭이 넓은 현장은 추가 조건이 생길 수 있어서, 사진만 보고 단정하기보다 실측으로 먼저 확인하는 편이 좋습니다.
소음, 냄새, 분위기까지 함께 고민되는 현관이라면 이 사례를 저장해두세요.
무료 방문 실측으로 우리 집 현관 폭과 구조에 맞는 방식을 먼저 확인할 수 있습니다.

## 해시태그
#문장군 #문장군중문 #문장군시공 #현관중문 #중문시공 #중문인테리어 #3연동중문 #브론즈유리 #강화유리중문 #아파트중문 #슬라이딩중문 #현관소음 #소음차단 #냄새차단 #현관냄새 #현관인테리어 #댐퍼중문 #무료실측 #방문실측 #아파트인테리어 #집분위기전환 #집꾸미기 #홈스타일링 #리모델링
"""


ASSETS_033 = {
    "review_capture": "고객리뷰.jpg",
    "product_thumbnail": "상품 썸네일.jpg",
    "before_main": "시공전.jpg",
    "after_main": "시공후_1.jpg",
    "after_front": "시공후_2.jpg",
    "after_open": "시공후_3.jpg",
    "after_bronze": "시공후_5.jpg",
    "after_bronze_close": "시공후_6.jpg",
    "after_glass_detail": "시공후_7.jpg",
    "after_entry_view": "시공후_8.jpg",
    "measure_width": "실측_너비.jpg",
    "measure_height": "실측_높이.jpg",
    "measure_depth": "실측_폭.jpg",
    "place_hallway": "현장_복도.jpg",
    "place_exterior": "현장_주차장.jpg",
}


SCENES_033 = [
    {
        "scene_id": "s01",
        "role": "hook",
        "time": [0.0, 2.0],
        "visual_source": {"role": "place_hallway"},
        "caption": {"text": "현관에서\n소리랑 냄새가\n들어온다면?", "emphasis": ["현관"], "position": "center", "size": "medium", "theme": "warning"},
        "narration": "현관에서 소리랑 냄새가 같이 들어온다면,",
        "energy_level": "high",
        "transition": "zoom_snap",
        "motion": "problem_shake",
    },
    {
        "scene_id": "s02",
        "role": "before_after",
        "time": [2.0, 6.0],
        "visual_source": {"role": "after_main"},
        "caption": {"text": "설치 후\n집 분위기가\n확 달라졌습니다", "emphasis": ["집 분위기"], "position": "center", "size": "medium", "theme": "clear"},
        "narration": "이 리뷰는 설치 후 집 분위기가 확 달라졌다는 이야기입니다.",
        "energy_level": "clear",
        "transition": "flash_glow",
        "motion": "clean_glow_reveal",
    },
    {
        "scene_id": "s03",
        "role": "context",
        "time": [6.0, 11.0],
        "visual_source": {"role": "after_bronze"},
        "caption": {"text": "브론즈 강화유리라\n답답함보다 은은함", "emphasis": ["브론즈"], "position": "upper", "size": "medium", "theme": "proof"},
        "narration": "브론즈 강화유리는 답답하지 않고, 조명 받을 때 은은한 느낌이 살아났고요.",
        "energy_level": "proof",
        "transition": "smooth_slide",
        "motion": "detail_probe",
    },
    {
        "scene_id": "s04",
        "role": "solution",
        "time": [11.0, 16.0],
        "visual_source": {"role": "after_open"},
        "caption": {"text": "3연동은 부드럽고\n댐퍼로 조용하게", "emphasis": ["조용"], "position": "lower", "size": "medium", "theme": "proof"},
        "narration": "3연동 문은 부드럽게 움직이고, 댐퍼 덕분에 닫힐 때도 조용했다고 해요.",
        "energy_level": "medium_high",
        "transition": "smooth_slide",
        "motion": "clean_room_pan",
    },
    {
        "scene_id": "s05",
        "role": "review_proof",
        "time": [16.0, 22.0],
        "visual_source": {"role": "review_capture"},
        "background_visual_source": {"role": "after_bronze_close"},
        "caption": {"text": "“냄새 차단”\n“소음 감소”\n체감 후기", "emphasis": ["소음 감소"], "position": "center", "size": "medium", "theme": "proof"},
        "narration": "리뷰에도 냄새 차단이나 소음 감소에 도움 되는 느낌이라고 남았습니다.",
        "energy_level": "proof",
        "transition": "pop",
        "motion": "review_capture_scroll",
    },
    {
        "scene_id": "s06",
        "role": "cta",
        "time": [22.0, 27.0],
        "visual_source": {"role": "measure_width"},
        "caption": {"text": "우리 집 폭도\n가능할까?\n무료 방문 실측", "emphasis": ["무료 방문 실측"], "position": "center", "size": "medium", "theme": "cta"},
        "narration": "현관 폭과 구조는 집마다 다르니까, 무료 방문 실측으로 먼저 확인해보세요.",
        "energy_level": "high_cta",
        "transition": "smooth_slide",
        "motion": "measure_scan",
    },
]


ASSETS_020 = {
    "review_capture": "고객리뷰.jpg",
    "product_thumbnail": "상품 썸네일.jpg",
    "place_hallway": "unnamed (1).jpg",
    "place_exterior": "unnamed.jpg",
    "before_main": "시공전_1.jpg",
    "before_bath": "시공전_2.jpg",
    "before_old_door": "시공전_3.jpg",
    "before_room": "시공전_4.jpg",
    "before_threshold": "시공전_5.jpg",
    "after_main": "시공후_1.jpg",
    "after_clean_1": "시공후_2.jpg",
    "after_clean_2": "시공후_4.jpg",
    "after_open": "시공후_5.jpg",
    "after_detail": "시공후_10.jpg",
    "measure_width": "실측_1.jpg",
    "measure_height": "실측_2.jpg",
    "measure_depth": "실측_3.jpg",
}


SCENES_020 = [
    {
        "scene_id": "s01",
        "role": "hook",
        "time": [0.0, 2.0],
        "visual_source": {"role": "before_threshold"},
        "caption": {"text": "로봇청소기,\n문턱에서 막힌다면?", "emphasis": ["문턱"], "position": "center", "size": "large", "theme": "warning"},
        "narration": "로봇청소기가 문턱에서 자꾸 막힌다면,",
        "energy_level": "high",
        "transition": "zoom_snap",
        "motion": "problem_shake",
    },
    {
        "scene_id": "s02",
        "role": "problem",
        "time": [2.0, 5.4],
        "visual_source": {"role": "before_old_door"},
        "caption": {"text": "오래된 방문이\n집 분위기를 눌렀습니다", "emphasis": ["오래된 방문"], "position": "lower", "size": "medium", "theme": "warning"},
        "narration": "오래된 방문이 집 전체 분위기를 무겁게 만들 수 있습니다.",
        "energy_level": "medium_high",
        "transition": "smooth_slide",
        "motion": "space_anxiety_pull",
    },
    {
        "scene_id": "s03",
        "role": "context",
        "time": [5.4, 8.8],
        "visual_source": {"role": "before_room"},
        "caption": {"text": "문틀과 문턱까지\n함께 봐야 했습니다", "emphasis": ["문턱"], "position": "center", "size": "medium", "theme": "warning"},
        "narration": "이 집은 문짝만이 아니라 문틀과 문턱까지 함께 봐야 했고요.",
        "energy_level": "medium_high",
        "transition": "hit_flash",
        "motion": "entry_path_pan",
    },
    {
        "scene_id": "s04",
        "role": "process",
        "time": [8.8, 12.2],
        "visual_source": {"role": "measure_width"},
        "caption": {"text": "문틀과 폭까지\n먼저 실측", "emphasis": ["실측"], "position": "upper", "size": "medium", "theme": "proof"},
        "narration": "그래서 문틀과 폭까지 먼저 실측했습니다.",
        "energy_level": "proof",
        "transition": "smooth_slide",
        "motion": "measure_scan",
    },
    {
        "scene_id": "s05",
        "role": "solution",
        "time": [12.2, 15.8],
        "visual_source": {"role": "product_thumbnail"},
        "caption": {"text": "하루 만에\n방문 교체", "emphasis": ["하루 만에"], "position": "bottom", "size": "medium", "theme": "proof"},
        "narration": "실측 후 집 전체 방문을 하루 만에 교체했습니다.",
        "energy_level": "medium_high",
        "transition": "card_pop",
        "motion": "product_card_flash",
    },
    {
        "scene_id": "s06",
        "role": "before_after",
        "time": [15.8, 19.4],
        "visual_source": {"role": "after_clean_1"},
        "caption": {"text": "집 분위기\n확 밝아졌습니다", "emphasis": ["확"], "position": "center", "size": "large", "theme": "clear"},
        "narration": "교체 후에는 집 분위기가 훨씬 환해졌고,",
        "energy_level": "clear",
        "transition": "flash_glow",
        "motion": "mission_clear_reveal",
    },
    {
        "scene_id": "s07",
        "role": "before_after",
        "time": [19.4, 22.5],
        "visual_source": {"role": "after_open"},
        "caption": {"text": "로봇청소기 동선도\n더 편하게", "emphasis": ["로봇청소기"], "position": "center", "size": "medium", "theme": "clear"},
        "narration": "문턱까지 정리되면서 로봇청소기 사용에도 더 편해졌다고 해요.",
        "energy_level": "clear",
        "transition": "smooth_slide",
        "motion": "clean_room_pan",
    },
    {
        "scene_id": "s08",
        "role": "review_proof",
        "time": [22.5, 25.0],
        "visual_source": {"role": "review_capture"},
        "background_visual_source": {"role": "after_clean_2"},
        "caption": {"text": "“진작 교체할 걸”", "emphasis": ["진작"], "position": "center", "size": "large", "theme": "proof"},
        "narration": "실제 리뷰에도 진작 교체할 걸 하는 생각이 들었다고 남았습니다.",
        "energy_level": "proof",
        "transition": "pop",
        "motion": "review_capture_scroll",
    },
    {
        "scene_id": "s09",
        "role": "cta",
        "time": [25.0, 27.0],
        "visual_source": {"role": "after_main"},
        "caption": {"text": "문틀까지 봐야 할까?\n무료 실측으로 확인", "emphasis": ["무료 실측"], "position": "center", "size": "medium", "theme": "cta"},
        "narration": "문틀까지 봐야 할지, 무료 실측으로 먼저 확인해보세요.",
        "energy_level": "high_cta",
        "transition": "smooth_slide",
        "motion": "clean_room_pan",
    },
]


ASSETS_020_GENINSERT = {
    **ASSETS_020,
    "ai_robot_blocked": "AI인서트_로봇청소기_문턱막힘.png",
    "ai_robot_pass": "AI인서트_로봇청소기_문턱없음통과.png",
}


SCENES_020_GENINSERT = copy.deepcopy(SCENES_020)
for scene, time_range in zip(
    SCENES_020_GENINSERT,
    [
        [0.0, 2.0],
        [2.0, 5.0],
        [5.0, 8.1],
        [8.1, 11.0],
        [11.0, 14.4],
        [14.4, 17.6],
        [17.6, 21.0],
        [21.0, 24.2],
        [24.2, 27.0],
    ],
    strict=True,
):
    scene["time"] = time_range
SCENES_020_GENINSERT[0]["visual_source"] = {"role": "ai_robot_blocked"}
SCENES_020_GENINSERT[0]["caption"] = {
    **SCENES_020_GENINSERT[0]["caption"],
    "text": "문턱에서\n자꾸 막힌다면?",
    "emphasis": ["문턱"],
    "position": "upper",
    "size": "medium",
}
SCENES_020_GENINSERT[6]["visual_source"] = {"role": "ai_robot_pass"}
SCENES_020_GENINSERT[6]["caption"] = {
    **SCENES_020_GENINSERT[6]["caption"],
    "text": "문턱 없이\n동선도 편하게",
    "emphasis": ["문턱 없이"],
    "position": "upper",
    "size": "large",
    "theme": "proof",
}


SCRIPT_114 = """---
review_id: 4928837480
review_number: 4928837480
product_order_number: 2026030766922971
source_file: 114_반려동물소음차단.txt
review_sequence: 114
created: 2026-06-13
content_type: 사연극
---

# 강아지 때문에 설치한 문, 집이 훨씬 평온해졌습니다

## 스크립트

### [HOOK] 0~2초
복도 소리만 나면 짖던 강아지라면?
> 내레이션: 복도 소리에 강아지가 자주 짖는 집이라면,

### [SCENE] 2~5초
복도식 아파트라 바깥소리가 바로 들어왔습니다
> 내레이션: 이 집은 복도식 아파트라 바깥소리만 나도 강아지가 많이 짖었다고 해요.

### [CONFLICT] 5~8초
상담부터 실측, 시공까지 친절하게
> 내레이션: 상담부터 실측, 시공까지 친절했고 일정도 오래 걸리지 않았습니다.

### [SOLUTION] 8~13초
설치 후, 반응이 달라졌습니다
> 내레이션: 설치 후에는 이젠 진짜 한 번 짖을까 말까 한다는 후기가 남았습니다.

### [TWIST] 13~21초
강아지도 집도 평온해진 느낌
> 내레이션: 강아지도 얼떨떨할 만큼 집 안이 훨씬 평온해졌고, 외풍 체감도 같이 달라졌다고 해요.

### [CLOSE] 21~28초
반려견이 복도 소리에 예민하다면
> 내레이션: 반려견이 복도 소리에 예민하다면 무료 실측으로 먼저 확인해보세요. 문장군 리뷰에서 가져왔어요.

## 캡션
복도식 아파트에서 반려견이 바깥소리에 자주 반응한다면, 이 리뷰는 저장해둘 만합니다.

이번 고객님은 강아지가 외부소음에 많이 짖어서 중문 설치를 고민한 사례였어요.
상담부터 실측, 시공까지 친절하게 진행됐고, 설치 후에는 “이젠 진짜 한 번 짖을까 말까 해요”라는 후기가 남았습니다.
소음 체감뿐 아니라 중문 밖과 안쪽의 온도차도 느껴질 만큼 외풍 체감이 달라졌다고 해요.

반려견 소리 반응, 복도식 아파트 소음, 현관 외풍이 같이 고민된다면 사진만 보고 판단하지 말고 무료 방문 실측으로 먼저 확인해보세요.

## 해시태그
#문장군 #문장군중문 #문장군시공 #현관중문 #중문시공 #중문인테리어 #3연동중문 #아파트중문 #복도식아파트 #반려견있는집 #강아지있는집 #반려동물인테리어 #현관소음 #복도소음 #소음차단 #외풍차단 #단열중문 #중문후기 #시공후기 #무료실측 #방문실측 #현관인테리어 #집꾸미기 #리모델링
"""


ASSETS_114 = {
    "review_capture": "고객리뷰.jpg",
    "product_thumbnail": "상품썸네일.jpg",
    "before_main": "시공전.jpg",
    "after_main": "시공후_1.jpg",
    "after_open": "시공후_2.jpg",
    "after_detail": "시공후_3.jpeg",
    "after_front": "시공후_4.jpg",
    "after_entry": "시공후_5.jpg",
    "measure_height": "실측_높이.jpg",
    "measure_width": "실측_폭.jpg",
    "place_hallway": "현장_복도.jpg",
    "place_exterior": "현장_외관.jpg",
}


SCENES_114 = [
    {
        "scene_id": "s01",
        "role": "hook",
        "time": [0.0, 2.8],
        "visual_source": {"role": "before_main"},
        "caption": {"text": "복도 소리만 나면\n짖던 강아지라면?", "emphasis": ["강아지"], "position": "center", "size": "medium", "theme": "warning"},
        "narration": "복도 소리에 강아지가 자주 짖는 집이라면,",
        "energy_level": "high",
        "transition": "zoom_snap",
        "motion": "problem_shake",
    },
    {
        "scene_id": "s02",
        "role": "problem",
        "time": [2.8, 7.0],
        "visual_source": {"role": "place_hallway"},
        "caption": {"text": "복도식 아파트\n바깥소리 문제", "emphasis": ["바깥소리"], "position": "center", "size": "medium", "theme": "warning"},
        "narration": "이 집은 복도식 아파트라 바깥소리만 나도 강아지가 많이 짖었다고 해요.",
        "energy_level": "medium_high",
        "transition": "smooth_slide",
        "motion": "entry_path_pan",
    },
    {
        "scene_id": "s03",
        "role": "process",
        "time": [7.0, 10.8],
        "visual_source": {"role": "measure_width"},
        "caption": {"text": "상담부터 실측까지\n친절하게", "emphasis": ["실측"], "position": "lower", "size": "medium", "theme": "proof"},
        "narration": "상담부터 실측, 시공까지 친절했고 일정도 오래 걸리지 않았습니다.",
        "energy_level": "proof",
        "transition": "smooth_slide",
        "motion": "measure_scan",
    },
    {
        "scene_id": "s04",
        "role": "change",
        "time": [10.8, 14.6],
        "visual_source": {"role": "after_open"},
        "caption": {"text": "한 번 짖을까\n말까 한대요", "emphasis": ["짖을까"], "position": "bottom", "size": "medium", "theme": "clear"},
        "narration": "설치 후에는 이젠 진짜 한 번 짖을까 말까 한다는 후기가 남았습니다.",
        "energy_level": "clear",
        "transition": "flash_glow",
        "motion": "clean_glow_reveal",
    },
    {
        "scene_id": "s05",
        "role": "feeling",
        "time": [14.6, 17.5],
        "visual_source": {"role": "after_front"},
        "caption": {"text": "강아지도 집도\n평온해진 느낌", "emphasis": ["평온"], "position": "center", "size": "medium", "theme": "clear"},
        "narration": "강아지도 얼떨떨할 만큼 집 안이 훨씬 평온해진 거죠.",
        "energy_level": "clear",
        "transition": "smooth_slide",
        "motion": "clean_room_pan",
    },
    {
        "scene_id": "s06",
        "role": "extra_benefit",
        "time": [17.5, 21.4],
        "visual_source": {"role": "after_entry"},
        "caption": {"text": "외풍 체감도\n같이 달라졌습니다", "emphasis": ["외풍"], "position": "lower", "size": "medium", "theme": "proof"},
        "narration": "중문 밖은 추운데 안쪽은 온도차가 느껴질 정도로 외풍도 줄었다고 해요.",
        "energy_level": "proof",
        "transition": "smooth_slide",
        "motion": "clean_room_pan",
    },
    {
        "scene_id": "s07",
        "role": "review_proof",
        "time": [21.4, 24.6],
        "visual_source": {"role": "review_capture"},
        "background_visual_source": {"role": "after_main"},
        "caption": {"text": "“한 번 짖을까\n말까 해요”", "emphasis": ["짖을까"], "position": "center", "size": "medium", "theme": "proof"},
        "narration": "실제 리뷰에도 강아지 반응이 달라졌다는 말이 남았습니다.",
        "energy_level": "proof",
        "transition": "pop",
        "motion": "review_capture_scroll",
    },
    {
        "scene_id": "s08",
        "role": "cta",
        "time": [24.6, 28.5],
        "visual_source": {"role": "after_detail"},
        "caption": {"text": "반려견 소음\n무료 실측 먼저", "emphasis": ["무료 실측"], "position": "center", "size": "medium", "theme": "cta"},
        "narration": "반려견이 복도 소리에 예민하다면 무료 실측으로 먼저 확인해보세요.",
        "energy_level": "high_cta",
        "transition": "smooth_slide",
        "motion": "clean_room_pan",
    },
]


CONFIGS = {
    "114": VariantConfig(
        review_id="114_반려동물소음차단",
        package_dir="output/inbox_20260609/114_반려동물소음차단_20260612_102821",
        review_path="reviews/inbox_20260609/114_반려동물소음차단.txt",
        base_recipe_name="114_반려동물소음차단_pet_noise_relief_v1_base_missing.json",
        variant_id="pet_noise_relief_v1",
        title="114 반려동물 소음반응 완화형 v1",
        target_duration=28.5,
        content_purpose="lead",
        video_type="pet_noise_relief",
        script_text=SCRIPT_114,
        scenes=SCENES_114,
        selected_quote="이젠 진짜 한번 짖을까말까해요",
        cta_primary="반려견 소음 반응",
        cta_secondary="무료 실측으로 먼저",
        asset_roles=ASSETS_114,
        image_dir="114_반려동물소음차단_이미지",
    ),
    "033": VariantConfig(
        review_id="033_소음차단냄새먼지",
        package_dir="output/inbox_20260609/033_소음차단냄새먼지_20260612_102821",
        review_path="reviews/inbox_20260609/033_소음차단냄새먼지.txt",
        base_recipe_name="033_소음차단냄새먼지_entry_noise_smell_v2_base_missing.json",
        variant_id="entry_noise_smell_v2",
        title="033 소음차단냄새먼지 전환형 v2",
        target_duration=27.0,
        content_purpose="retargeting",
        video_type="entry_noise_smell_design",
        script_text=SCRIPT_033,
        scenes=SCENES_033,
        selected_quote="냄새 차단이나 소음 감소에도 도움",
        cta_primary="우리 집 폭도 가능할까?",
        cta_secondary="무료 방문 실측",
        asset_roles=ASSETS_033,
        image_dir="033_소음차단냄새먼지_이미지",
    ),
    "010": VariantConfig(
        review_id="010_구축소음",
        package_dir="output/inbox_20260609/010_구축소음_20260609_095709",
        review_path="reviews/inbox_20260609/010_구축소음.txt",
        base_recipe_name="010_구축소음_edit_recipe_v2.json",
        variant_id="old_building_noise_v2_final",
        title="010 구축소음 전환형 v2 final",
        target_duration=25.0,
        content_purpose="retargeting",
        video_type="old_building_noise",
        script_text=SCRIPT_010,
        scenes=SCENES_010,
        selected_quote="정말정말 좋습니다 ㅠ",
        cta_primary="구축 빌라도 가능할까?",
        cta_secondary="무료 방문 실측",
    ),
    "004": VariantConfig(
        review_id="004_어려운시공",
        package_dir="output/inbox_20260609/004_어려운시공_20260609_102346",
        review_path="reviews/inbox_20260609/004_어려운시공.txt",
        base_recipe_name="004_어려운시공_edit_recipe_v2.json",
        variant_id="difficult_installation_v2_final",
        title="004 어려운시공 신뢰형 v2 final",
        target_duration=27.0,
        content_purpose="brand_expertise",
        video_type="difficult_installation",
        script_text=SCRIPT_004,
        scenes=SCENES_004,
        selected_quote="걱정할 필요가 없어요",
        cta_primary="어려운 현장도",
        cta_secondary="먼저 확인해드립니다",
    ),
    "020": VariantConfig(
        review_id="020_로봇청소구축리모델링",
        package_dir="output/inbox_20260609/020_로봇청소구축리모델링_20260609_160414",
        review_path="reviews/inbox_20260609/020_로봇청소구축리모델링.txt",
        base_recipe_name="020_로봇청소구축리모델링_living_flow_v2_base_missing.json",
        variant_id="living_flow_v2_final",
        title="020 로봇청소 생활동선형 v2 final",
        target_duration=27.0,
        content_purpose="feed_trust",
        video_type="living_flow_threshold",
        script_text=SCRIPT_020,
        scenes=SCENES_020,
        selected_quote="진작 교체할 걸",
        cta_primary="문짝만 바꾸면 될까?",
        cta_secondary="무료 실측으로 확인",
        asset_roles=ASSETS_020,
        image_dir="020_로봇청소구축리모델링_script",
    ),
    "020-gen": VariantConfig(
        review_id="020_로봇청소구축리모델링",
        package_dir="output/inbox_20260609/020_로봇청소구축리모델링_20260609_160414",
        review_path="reviews/inbox_20260609/020_로봇청소구축리모델링.txt",
        base_recipe_name="020_로봇청소구축리모델링_living_flow_geninsert_v3_base_missing.json",
        variant_id="living_flow_geninsert_v3",
        title="020 로봇청소 생성 인서트 v3",
        target_duration=27.0,
        content_purpose="feed_trust",
        video_type="living_flow_threshold_generated_insert",
        script_text=SCRIPT_020,
        scenes=SCENES_020_GENINSERT,
        selected_quote="진작 교체할 걸",
        cta_primary="문짝만 바꾸면 될까?",
        cta_secondary="무료 실측으로 확인",
        asset_roles=ASSETS_020_GENINSERT,
        image_dir="020_로봇청소구축리모델링_script",
    ),
}


def build_variants(keys: list[str]) -> dict[str, dict[str, Path]]:
    result: dict[str, dict[str, Path]] = {}
    for key in keys:
        result[key] = _write_outputs(CONFIGS[key])
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Build v2 final HTML inputs for 004 and 010.")
    parser.add_argument("--reviews", nargs="+", choices=sorted(CONFIGS), default=sorted(CONFIGS))
    args = parser.parse_args()
    outputs = build_variants(args.reviews)
    for key, files in outputs.items():
        print(f"[{key}]")
        for name, path in files.items():
            print(f"{name}: {path}")


if __name__ == "__main__":
    main()
