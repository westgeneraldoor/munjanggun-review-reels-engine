from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


REQUIRED_SCAFFOLD_EVIDENCE = ("installed_result", "before_state", "review_capture")


def _first_review_quote(review_text: str) -> str:
    text = " ".join(str(review_text).split())
    if not text:
        raise ValueError("RECIPE_SCAFFOLD_REVIEW_TEXT_MISSING")
    for marker in (".", "!", "?", "。", "！", "？"):
        if marker in text:
            candidate = text.split(marker, 1)[0].strip()
            if candidate:
                return candidate
    return text


def _select_evidence_assets(selected_assets: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    chosen: dict[str, dict[str, Any]] = {}
    for asset in selected_assets:
        if not isinstance(asset, dict):
            continue
        relative_path = asset.get("relative_path")
        classes = asset.get("evidence_classes")
        if not isinstance(relative_path, str) or not relative_path.strip() or not isinstance(classes, list):
            continue
        for evidence_class in classes:
            if evidence_class in REQUIRED_SCAFFOLD_EVIDENCE and evidence_class not in chosen:
                chosen[evidence_class] = asset

    missing = [name for name in REQUIRED_SCAFFOLD_EVIDENCE if name not in chosen]
    if missing:
        raise ValueError("RECIPE_SCAFFOLD_REQUIRED_EVIDENCE_MISSING: " + ", ".join(missing))
    if (chosen["installed_result"].get("visual_quality") or {}).get("full_product_visible") is not True:
        raise ValueError("RECIPE_SCAFFOLD_FULL_PRODUCT_RESULT_MISSING")

    asset_roles = {name: str(chosen[name]["relative_path"]) for name in REQUIRED_SCAFFOLD_EVIDENCE}
    asset_evidence = {
        name: {
            "evidence_class": name,
            "visual_quality": deepcopy(chosen[name].get("visual_quality") or {}),
        }
        for name in REQUIRED_SCAFFOLD_EVIDENCE
    }
    return asset_roles, asset_evidence


def _scene(scene_id: str, role: str, asset_id: str, source_kind: str, narration: str) -> dict[str, Any]:
    return {
        "scene_id": scene_id,
        "narrative_role": role,
        "visual_source": {"asset_id": asset_id, "source_kind": source_kind},
        "caption": {"text": narration},
        "narration": narration,
        "meaning_match": True,
        "meaning_match_evidence": "TODO: bind exact review text and selected photo evidence",
    }


def _body_beat(
    *,
    beat_id: str,
    scene_id: str,
    role: str,
    start: float,
    end: float,
    asset: str,
    text: str,
    keyword: str,
    review_quote: str | None = None,
) -> dict[str, Any]:
    motion = "review_capture_hold" if role == "review_proof" else "calm_push_in"
    source_kind_fields = {"proof_asset_type": "actual_review_capture"} if role == "review_proof" else {}
    compact_text = re.sub(r"[^0-9A-Za-z가-힣]", "", text).casefold()
    keyword_index = compact_text.find(re.sub(r"[^0-9A-Za-z가-힣]", "", keyword).casefold())
    accent_start = start + (end - start) * (max(keyword_index, 0) / max(len(compact_text), 1))
    beat: dict[str, Any] = {
        "id": beat_id,
        "narrative_role": role,
        "planning_scene_id": scene_id,
        "time": [start, end],
        "caption_start_sec": start,
        "caption_chunks": [{"text": text, "start_sec": start, "end_sec": end}],
        "narration_start_sec": start,
        "asset": asset,
        "asset_id": asset,
        "motion": motion,
        "shots": [
            {
                "asset_id": asset,
                "start_sec": start,
                "end_sec": end,
                "motion": motion,
                "motion_reason": "Keep the selected evidence legible with restrained movement.",
                "transition_in": "calm_dissolve",
            }
        ],
        "visual_relevance": "direct",
        "caption": text,
        "caption_layout": {
            "line_count": 1,
            "min_font_px": 46,
            "safe_area": "pass",
            "does_not_cover_subject": True,
            "position": "bottom",
            "size": "medium",
            "align": "center",
            "theme": "white",
        },
        "caption_focus_keywords": [keyword],
        "caption_emphasis": [keyword],
        "caption_accent": {"enabled": True, "style": "event", "start_sec": round(accent_start, 3)},
        "narration_ref": text,
        "meaning_match": True,
        "meaning_match_source": f"planning_scene:{scene_id}",
        **source_kind_fields,
    }
    if role == "review_proof":
        beat["review_emphasis"] = {
            "quote": review_quote,
            "start_sec": start + 0.05,
            "end_sec": end - 0.25,
            # 캡처에서 인용문이 실제로 몇 줄에 걸치는지 보고 줄 수만큼 segment를 나눈다.
            # line_text를 모두 이으면 quote와 정확히 같아야 통과한다.
            "segments": [{"left_pct": 15, "top_pct": 62, "width_pct": 70, "line_text": review_quote}],
            "draw_duration_sec": 0.15,
        }
    return beat


def build_recipe_scaffold(
    *,
    content_id: str,
    review_text: str,
    selected_assets: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a complete but intentionally blocked one-shot recipe starting point."""

    content = str(content_id).strip()
    if not content:
        raise ValueError("RECIPE_SCAFFOLD_CONTENT_ID_MISSING")
    quote = _first_review_quote(review_text)
    asset_roles, asset_evidence = _select_evidence_assets(selected_assets)

    hook_parts = ("완성 결과를 보여줍니다.", "이전 문제를 확인합니다.", "완성 결과로 돌아옵니다.")
    hook_ranges = ((0.0, 1.3), (1.3, 2.6), (2.6, 4.0))
    hook_assets = ("installed_result", "before_state", "installed_result")
    hook_chunks = [
        {"text": text, "start_sec": start, "end_sec": end}
        for text, (start, end) in zip(hook_parts, hook_ranges)
    ]
    hook_shots = [
        {
            "asset_id": asset,
            "start_sec": start,
            "end_sec": end,
            "motion": "calm_push_in",
            "motion_reason": "Keep the result-before-result comparison calm and readable.",
            "transition_in": "cut" if index == 0 else "calm_dissolve",
            "meaning_match_source": f"asset_evidence:{asset}; narration_fragment:{text}",
        }
        for index, (asset, text, (start, end)) in enumerate(zip(hook_assets, hook_parts, hook_ranges))
    ]

    planning = {
        "schema_version": "review-reel-planning-scaffold-v1",
        "content_id": content,
        "scaffold": {
            "status": "incomplete",
            "pending_fields": [
                "analysis",
                "selected_hook",
                "writer_brief",
                "scene narration and captions",
                "review underline geometry",
                "voice-bound timing and hashes",
            ],
        },
        "workflow_contract": {
            "name": "review-reels-one-shot-v2",
            "html_scope_authorized": True,
            "mp4_scope_authorized": False,
        },
        "analysis": {
            "customer_problem": "TODO_FROM_REVIEW",
            "before_pain": "TODO_FROM_REVIEW",
            "after_change": "TODO_FROM_REVIEW",
            "customer_emotion": ["TODO_FROM_REVIEW"],
        },
        "review_source": {
            "text": review_text,
            "review_quote_for_proof": quote,
            "inferred_fields": [],
            "unsupported_story_elements": [],
        },
        "hooks": [{"text": "어떤 변화가 생겼을까요?"}],
        "selected_hook": {"text": "어떤 변화가 생겼을까요?"},
        "writer_brief": {
            "story_mode": "problem_solution",
            "one_line_story": "TODO_FROM_REVIEW",
            "hook_candidates": [{"text": "어떤 변화가 생겼을까요?"}],
            "recommended_hook": "어떤 변화가 생겼을까요?",
            "review_quote_for_proof": quote,
        },
        "photo_qa": {
            "checked": True,
            "asset_count": len(selected_assets),
            "first_frame_asset_id": "installed_result",
            "privacy_status": "passed",
        },
        "review_proof": {"source_capture_kind": "actual_review_capture"},
        "audio_sync": {"mode": "voice_aligned", "sync_checks": {"screen_ahead_of_voice": False}},
        "scenes": [
            _scene("s01", "event", "installed_result", "customer_photo", " ".join(hook_parts)),
            _scene("s02", "problem", "before_state", "customer_photo", "고객이 겪은 현관 문제를 리뷰 원문에서 정확히 작성합니다."),
            _scene("s03", "resolution", "installed_result", "customer_photo", "문제 해결 과정과 선택 이유를 리뷰 근거로 정확히 작성합니다."),
            _scene("s04", "felt_result", "installed_result", "customer_photo", "설치 뒤 고객이 실제로 느낀 변화를 리뷰 문장으로 작성합니다."),
            _scene("s05", "review_proof", "review_capture", "actual_review_capture", "리뷰 원문에도 고객의 변화가 이렇게 남았습니다."),
            _scene("s06", "cta", "installed_result", "customer_photo", "우리 집 조건도 가능한지 현장에서 먼저 정확히 확인해보세요."),
        ],
    }

    hook_text = " ".join(hook_parts)
    hook_beat = {
        "id": "b01",
        "narrative_role": "event",
        "planning_scene_id": "s01",
        "time": [0.0, 4.0],
        "caption_start_sec": 0.0,
        "caption_chunks": hook_chunks,
        "narration_start_sec": 0.0,
        "asset": "installed_result",
        "asset_id": "installed_result",
        "motion": "calm_push_in",
        "shots": hook_shots,
        "visual_relevance": "direct",
        "caption": hook_text,
        "caption_layout": {
            "line_count": 1,
            "min_font_px": 36,
            "safe_area": "pass",
            "does_not_cover_subject": True,
            "position": "bottom",
            "size": "hero-calm",
            "align": "center",
            "theme": "white",
        },
        "caption_focus_keywords": ["완성"],
        "caption_emphasis": ["완성"],
        "caption_accent": {"enabled": True, "style": "event", "start_sec": 0.0},
        "narration_ref": hook_text,
        "meaning_match": True,
        "meaning_match_source": "planning_scene:s01",
    }
    edit = {
        "schema_version": "review-reel-edit-scaffold-v1",
        "scaffold": deepcopy(planning["scaffold"]),
        "source": {
            "image_dir": ".",
            "script": f"{content}_review_reel_script.md",
            "srt": f"{content}_review_reel_subtitles.srt",
            "voice": f"{content}_review_reel_voice.mp3",
            "tts_generation_report": "_work/tts_generation_report.json",
            "privacy_review": {"checked": True, "unresolved_risks": []},
            "privacy_sanitization_report": "_work/privacy_sanitization_report.json",
        },
        "audio_plan": {
            "sync_policy": {"raw_tts_duration_sec": 24.0, "final_voice_duration_sec": 24.0},
            "final_voice_is_master": True,
            "tts_text_matches_narration": True,
            "tts_text_sha256": "0" * 64,
            "final_voice_sha256": "0" * 64,
        },
        "asset_roles": asset_roles,
        "asset_evidence": asset_evidence,
        "hook_visual_contract": {
            "result_asset_id": "installed_result",
            "before_asset_id": "before_state",
        },
        "beats": [
            hook_beat,
            _body_beat(beat_id="b02", scene_id="s02", role="problem", start=4.0, end=8.0, asset="before_state", text="고객이 겪은 현관 문제를 리뷰 원문에서 정확히 작성합니다.", keyword="문제"),
            _body_beat(beat_id="b03", scene_id="s03", role="resolution", start=8.0, end=12.0, asset="installed_result", text="문제 해결 과정과 선택 이유를 리뷰 근거로 정확히 작성합니다.", keyword="해결"),
            _body_beat(beat_id="b04", scene_id="s04", role="felt_result", start=12.0, end=16.0, asset="installed_result", text="설치 뒤 고객이 실제로 느낀 변화를 리뷰 문장으로 작성합니다.", keyword="변화"),
            _body_beat(beat_id="b05", scene_id="s05", role="review_proof", start=16.0, end=20.0, asset="review_capture", text="리뷰 원문에도 고객의 변화가 이렇게 남았습니다.", keyword="리뷰", review_quote=quote),
            _body_beat(beat_id="b06", scene_id="s06", role="cta", start=20.0, end=24.0, asset="installed_result", text="우리 집 조건도 가능한지 현장에서 먼저 정확히 확인해보세요.", keyword="확인"),
        ],
    }
    return planning, edit
