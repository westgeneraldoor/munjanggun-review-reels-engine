from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .review_analyzer import ReviewAnalysis, analyze_review


def _quote_text(analysis: ReviewAnalysis) -> str:
    for quote in analysis.strongest_review_quotes:
        if quote.get("selected"):
            return str(quote["edited"])
    if analysis.strongest_review_quotes:
        return str(analysis.strongest_review_quotes[0]["edited"])
    return "실제 고객 리뷰로 확인된 변화예요"


def _cooling_hooks() -> list[dict[str, Any]]:
    return [
        {
            "id": "hook_problem_1",
            "style": "problem_empathy",
            "text": "에어컨 풀가동해도 거실이 덥다면?",
            "score": 9.4,
            "reason": "여름 시즌 불편을 2초 안에 바로 찌른다.",
        },
        {
            "id": "hook_curiosity_1",
            "style": "curiosity",
            "text": "중문 하나로 냉방 체감이 달라질 수 있을까?",
            "score": 8.5,
            "reason": "궁금증은 좋지만 첫 타격감은 문제 공감형보다 약하다.",
        },
        {
            "id": "hook_change_1",
            "style": "change",
            "text": "더운 공기 들어오던 현관, 이렇게 바뀌었습니다",
            "score": 8.1,
            "reason": "시각 전환에는 좋지만 광고 첫 문장으로는 조금 설명형이다.",
        },
    ]


def build_planning_recipe(
    *,
    review_id: str,
    package_dir: str,
    image_dir: str,
    review_text: str,
    voice: str,
    existing_script: str,
    existing_srt: str,
    asset_roles: dict[str, str],
    variant_id: str = "ad_v2",
) -> dict[str, Any]:
    analysis = analyze_review(review_text)
    quote = _quote_text(analysis)
    hooks = _cooling_hooks()
    selected_hook = hooks[0]

    scenes = [
        {
            "scene_id": "s01",
            "role": "hook",
            "time": [0.0, 2.0],
            "visual_source": {"role": "before_main", "file": asset_roles.get("before_main")},
            "visual_instruction": "heat discomfort push-in, complete hook sentence, no left-top label",
            "caption": {
                "text": "에어컨 풀가동해도\n거실이 덥다면?",
                "emphasis": ["덥다면?"],
                "position": "center",
                "size": "large",
                "theme": "warning",
            },
            "narration": "에어컨을 풀로 틀어도 거실이 덥다면,",
            "energy_level": "high",
            "transition": "zoom_snap",
            "motion": "heat_haze_problem",
        },
        {
            "scene_id": "s02",
            "role": "problem",
            "time": [2.0, 5.2],
            "visual_source": {"role": "before_entry", "file": asset_roles.get("before_entry")},
            "visual_instruction": "show hesitation and narrow-space concern",
            "caption": {
                "text": "좁아 보일까 봐\n미뤘던 중문",
                "emphasis": ["미뤘던"],
                "position": "lower",
                "size": "medium",
                "theme": "default",
            },
            "narration": "좁아 보일까 봐 설치를 미뤘던 집.",
            "energy_level": "medium",
            "transition": "smooth_slide",
            "motion": "space_anxiety_pull",
        },
        {
            "scene_id": "s03",
            "role": "problem",
            "time": [5.2, 8.6],
            "visual_source": {"role": "place_hallway", "file": asset_roles.get("place_hallway")},
            "visual_instruction": "make hallway air feel like the source of heat",
            "caption": {
                "text": "여름엔\n달랐습니다",
                "emphasis": ["여름엔"],
                "position": "center",
                "size": "large",
                "theme": "warning",
            },
            "narration": "그런데 여름이 되자 에어컨을 틀어도 덥더랍니다.",
            "energy_level": "high",
            "transition": "hit_flash",
            "motion": "heat_haze_problem",
        },
        {
            "scene_id": "s04",
            "role": "solution",
            "time": [8.6, 11.8],
            "visual_source": {"role": "product_thumbnail", "file": asset_roles.get("product_thumbnail")},
            "visual_instruction": "brief product thumbnail, caption low enough not to block product",
            "caption": {
                "text": "그래서 선택한\n현관 중문",
                "emphasis": ["현관 중문"],
                "position": "bottom",
                "size": "medium",
                "theme": "proof",
            },
            "narration": "그래서 선택한 건 현관 중문.",
            "energy_level": "medium_high",
            "transition": "card_pop",
            "motion": "product_card_flash",
        },
        {
            "scene_id": "s05",
            "role": "before_after",
            "time": [11.8, 16.0],
            "visual_source": {"role": "after_main", "file": asset_roles.get("after_main")},
            "alt_visual_source": {"role": "after_open", "file": asset_roles.get("after_open")},
            "visual_instruction": "clean result reveal with cool-air motion",
            "caption": {
                "text": "설치 후\n확실히 더 시원",
                "emphasis": ["더 시원"],
                "position": "center",
                "size": "large",
                "theme": "clear",
            },
            "narration": "설치 후 에어컨을 켜니 확실히 더 시원하다고 해요.",
            "energy_level": "high",
            "transition": "flash_glow",
            "motion": "cool_air_reveal",
        },
        {
            "scene_id": "s06",
            "role": "review_proof",
            "time": [16.0, 20.3],
            "visual_source": {"role": "review_capture", "file": asset_roles.get("review_capture")},
            "background_visual_source": {"role": "after_main", "file": asset_roles.get("after_main")},
            "visual_instruction": "review capture is evidence; quote is the readable copy",
            "caption": {
                "text": f"“{quote}”",
                "emphasis": ["확실히", "시원"],
                "position": "center",
                "size": "medium",
                "theme": "proof",
            },
            "narration": "리뷰에도 이렇게 남았습니다.",
            "energy_level": "high",
            "transition": "pop",
            "motion": "review_capture_scroll",
        },
        {
            "scene_id": "s07",
            "role": "cta",
            "time": [20.3, 23.0],
            "visual_source": {"role": "after_front", "file": asset_roles.get("after_front")},
            "visual_instruction": "clean after shot, consultative CTA, no hard sell",
            "caption": {
                "text": "우리 집도 가능할까?\n무료 방문 실측 상담",
                "emphasis": ["무료 방문 실측"],
                "position": "center",
                "size": "medium",
                "theme": "cta",
            },
            "narration": "우리 집도 가능할지, 현장에서 먼저 확인해보세요.",
            "energy_level": "high_cta",
            "transition": "smooth_slide",
            "motion": "clean_room_pan",
        },
    ]

    return {
        "schema_version": "2.0",
        "project": {
            "review_id": review_id,
            "variant_id": variant_id,
            "title": f"{review_id} 광고용 v2",
            "created_at": date.today().isoformat(),
            "status": "draft",
        },
        "source": {
            "package_dir": package_dir,
            "image_dir": image_dir,
            "existing_script": existing_script,
            "existing_voice": voice,
            "existing_srt": existing_srt,
        },
        "strategy": {
            "content_purpose": analysis.content_purpose,
            "video_type": analysis.video_type,
            "target_duration_sec": 23,
            "platform": "instagram_reels",
            "primary_goal": "lead",
            "cta_strength": "medium",
            "tone": "practical, sensory, not overhyped",
        },
        "analysis": {
            "customer_problem": analysis.customer_problem,
            "before_pain": analysis.before_pain,
            "after_change": analysis.after_change,
            "customer_emotion": analysis.customer_emotion,
            "strongest_review_quotes": analysis.strongest_review_quotes,
            "proof_points": analysis.proof_points,
            "risk_flags": analysis.risk_flags,
        },
        "hooks": hooks,
        "selected_hook": {
            "hook_id": selected_hook["id"],
            "text": selected_hook["text"],
            "selection_reason": "계절성, 자기 관련성, 궁금증이 모두 첫 2초 안에 들어간다.",
        },
        "timeline": {
            "target_duration_sec": 23,
            "structure": [{"role": scene["role"], "range": scene["time"]} for scene in scenes],
            "energy_curve": [
                [0, "high"],
                [2, "medium"],
                [5.2, "high"],
                [11.8, "high"],
                [16, "proof"],
                [20.3, "high_cta"],
            ],
        },
        "scenes": scenes,
        "review_proof": {
            "source_capture_role": "review_capture",
            "source_capture_file": asset_roles.get("review_capture"),
            "quote_candidates": analysis.strongest_review_quotes,
            "selected_quote": quote,
            "display_mode": "blurred_capture_plus_large_quote",
            "time": [16.0, 20.3],
        },
        "cta": {
            "time": [20.3, 23.0],
            "primary_text": "우리 집도 가능할까?",
            "secondary_text": "무료 방문 실측 상담",
            "tone": "consultative",
            "avoid": ["fake_urgency", "guaranteed_outcome"],
        },
        "narration": {
            "mode": "timeline_first",
            "text": "\n".join(str(scene["narration"]) for scene in scenes),
        },
        "audio_sync": {
            "source_of_truth": "planning_recipe",
            "requires_new_voice_for_target_duration": True,
            "current_voice_can_render_sync_safe_variant": True,
        },
        "render_recipe": {},
        "outputs": {},
        "quality_checks": {
            "hook_complete_sentence": True,
            "review_quote_separated_from_capture": True,
            "cta_has_own_scene": True,
            "absolute_claims_avoided": True,
        },
    }


def planning_to_edit_recipe(
    planning: dict[str, Any],
    *,
    base_edit_recipe: dict[str, Any],
    current_voice_duration_sec: float | None = None,
) -> dict[str, Any]:
    scenes = planning["scenes"]
    target = float(planning["timeline"]["target_duration_sec"])
    has_measured_voice = current_voice_duration_sec is not None
    render_duration = current_voice_duration_sec if has_measured_voice else target
    scale = render_duration / target if target else 1.0

    beats: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes, start=1):
        start, end = scene["time"]
        caption = scene["caption"]
        visual = scene["visual_source"]
        beat: dict[str, Any] = {
            "id": f"v2b{index:02d}",
            "phase": scene["role"],
            "time": [round(float(start) * scale, 2), round(float(end) * scale, 2)],
            "asset": visual["role"],
            "caption": caption["text"],
            "caption_emphasis": caption.get("emphasis", []),
            "caption_layout": {
                "position": caption.get("position", "center"),
                "size": caption.get("size", "medium"),
                "align": "center",
                "theme": caption.get("theme", "default"),
            },
            "motion": scene.get("motion", "clean_room_pan"),
            "transition_in": scene.get("transition", "smooth_slide"),
            "transition_out": "smooth_slide",
            "sfx": None,
            "narration_ref": scene.get("narration", ""),
        }
        if scene.get("background_visual_source"):
            beat["background_asset"] = scene["background_visual_source"]["role"]
        if scene.get("semantic_overlay"):
            beat["semantic_overlay"] = scene["semantic_overlay"]
        beats.append(beat)

    sync_policy = {
        "mode": "current_voice_sync_safe",
        "planned_target_duration_sec": target,
        "render_duration_sec": round(render_duration, 2),
        "scale_factor": round(scale, 4),
        "note": "새 23초 음성이 생기기 전까지 기존 음성 길이에 맞춰 컷을 늘린다.",
    }
    if has_measured_voice:
        sync_policy["final_voice_duration_sec"] = round(float(current_voice_duration_sec), 2)

    recipe = {
        "version": "2.1",
        "title": f"{planning['project']['review_id']} 광고용 v2 sync-safe",
        "description": "planning recipe v2에서 생성한 광고형 HTML 렌더 레시피입니다. 현재 음성 길이에 맞춘 sync-safe 버전입니다.",
        "source": base_edit_recipe["source"],
        "style_dna": {
            **base_edit_recipe.get("style_dna", {}),
            "video_type": planning["strategy"]["video_type"],
            "content_purpose": planning["strategy"]["content_purpose"],
            "planning_recipe": "ad_v2",
            "pd_note": "첫 2초 완성형 훅, 리뷰 캡처+핵심 문장 분리, CTA 독립 씬을 적용한 v2 파일럿.",
        },
        "asset_roles": base_edit_recipe["asset_roles"],
        "beats": beats,
        "audio_plan": {
            **base_edit_recipe.get("audio_plan", {}),
            "sync_policy": sync_policy,
        },
        "render_targets": base_edit_recipe.get("render_targets", {}),
    }
    return recipe


def captions_to_srt(planning: dict[str, Any]) -> str:
    def fmt(seconds: float) -> str:
        whole = int(seconds)
        ms = int(round((seconds - whole) * 1000))
        h = whole // 3600
        m = (whole % 3600) // 60
        s = whole % 60
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    entries = []
    for index, scene in enumerate(planning["scenes"], start=1):
        start, end = scene["time"]
        entries.append(f"{index}\n{fmt(float(start))} --> {fmt(float(end))}\n{scene['caption']['text']}")
    return "\n\n".join(entries) + "\n"
