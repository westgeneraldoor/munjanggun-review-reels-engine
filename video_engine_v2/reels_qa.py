from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from .qa_guidance import guidance_for_issue


HARD_CPS_LIMIT = 9.0
SOFT_CPS_LIMIT = 8.5
MIN_ONE_SHOT_CPS = 5.0
MAX_VISUAL_LEAD_SEC = 0.05
MAX_REVIEW_PROOF_DWELL_SEC = 6.0
ONE_SHOT_CONTRACT_NAME = "review-reels-one-shot-v2"
REQUIRED_NARRATIVE_ROLES = (
    "event",
    "problem",
    "resolution",
    "felt_result",
    "review_proof",
    "cta",
)
NARRATIVE_ROLE_ORDER = (
    "event",
    "problem",
    "context",
    "choice_turn",
    "resolution",
    "felt_result",
    "review_proof",
    "cta",
)
SUPPORTED_STORY_MODES = {
    "problem_solution",
    "difficult_site",
    "time_lapse_review",
    "human_service",
    "seasonal_comfort",
    "living_convenience",
}
MAX_OPENING_BEAT_SEC = 4.0
MIN_CAPTION_FONT_PX = 32
SUPPORTED_CAPTION_THEMES = {"white", "warning", "proof", "clear", "cta", "stamp"}
SHA256_HEX = re.compile(r"[0-9a-f]{64}")
CORRUPT_MARKERS = ("??", "\ufffd")
WEAK_HOOK_PHRASES = (
    "좋아졌습니다",
    "좋았습니다",
    "진짜입니다",
    "만족했습니다",
    "만족도",
    "설치한 집",
    "드디어 해방",
)
HOOK_TRIGGER_PATTERNS = {
    "curiosity_gap": (
        "이것",
        "이 구조",
        "이유",
        "진짜 이유",
        "따로",
        "왜",
        "어떻게",
        "?",
    ),
    "concrete_number": (
        r"\d",
        "한 달",
        "두 곳",
        "세 곳",
        "금요일",
        "수요일",
        "30분",
        "cm",
        "센티",
        "3연동",
    ),
    "target_callout": (
        "라면",
        "분들",
        "집이라면",
        "사는",
        "쓰는 집",
        "입주민",
        "구축",
        "반려",
        "로봇청소기",
    ),
    "counter_belief": (
        "아닙니다",
        "때문이 아닙니다",
        "보다 중요한",
        "비싼",
        "좋은",
        "따로 있습니다",
    ),
    "loss_aversion": (
        "후회",
        "놓치",
        "손해",
        "망하",
        "떠나",
        "추가 비용",
        "주의",
    ),
    "result_promise": (
        "달라졌",
        "바뀌",
        "만든 결과",
        "가능",
        "줄인",
        "해결",
        "완성",
    ),
}
RISK_TOPIC_KEYWORDS = {
    "noise": ("소음", "층간소음", "방음", "시끄", "소리", "복도소리"),
    "smell": ("냄새", "악취"),
    "dust": ("먼지", "분진"),
    "pet": ("강아지", "고양이", "반려동물", "반려견", "반려묘", "짖"),
    "child": ("아이", "아기", "자녀", "애기", "유아"),
    "difficult_install": ("어려운", "난이도", "포기", "불가", "까다", "비대칭", "수평"),
}
STRONG_CLAIM_KEYWORDS = (
    "90%",
    "100%",
    "완벽",
    "무조건",
    "보장",
    "확실한 방음",
    "완전 차단",
    "완벽 차단",
)
VISUAL_EVIDENCE_CLASSES = {
    "installed_result",
    "before_state",
    "measurement",
    "review_capture",
    "context",
    "detail",
    "installation_process",
}
BASE_REQUIRED_VISUAL_EVIDENCE = {"installed_result", "before_state", "review_capture"}
HIGH_VALUE_VISUAL_EVIDENCE = {"measurement", "installation_process"}
CLAIM_EVIDENCE_KEYWORDS = {
    "measurement": ("실측", "측정", "치수", "재보", "재어", "줄자"),
    "installation_process": ("시공 과정", "설치 과정", "공정", "마감 작업"),
}
EMOTION_CLAIM_KEYWORDS = {
    "anxiety": ("불안", "걱정", "초조", "망설"),
    "relief": ("안심", "다행", "마음놓", "마음 놓", "후련"),
    "satisfaction": ("만족", "대만족", "흡족"),
    "surprise": ("놀랐", "생각보다", "기대이상", "기대 이상"),
}


def _issue(code: str, message: str, *, scene_id: str | None = None, severity: str = "fail") -> dict[str, Any]:
    issue: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "message": message,
    }
    if scene_id:
        issue["scene_id"] = scene_id
    guidance = guidance_for_issue(code)
    if guidance is not None:
        issue["guidance"] = guidance
    return issue


def count_nonspace_chars(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _compact_text(value: Any) -> str:
    return re.sub(r"\s+", "", _as_text(value))


def _flatten_planning_story_text(planning_recipe: dict[str, Any]) -> str:
    parts: list[str] = []
    for hook in planning_recipe.get("hooks") or []:
        if isinstance(hook, dict):
            parts.extend(_as_text(hook.get(key)) for key in ("text", "caption", "headline"))
        else:
            parts.append(_as_text(hook))
    selected_hook = planning_recipe.get("selected_hook") or {}
    if isinstance(selected_hook, dict):
        parts.extend(_as_text(selected_hook.get(key)) for key in ("text", "caption", "headline"))
    for scene in planning_recipe.get("scenes") or []:
        caption = scene.get("caption")
        if isinstance(caption, dict):
            parts.append(_as_text(caption.get("text")))
        else:
            parts.append(_as_text(caption))
        parts.append(_as_text(scene.get("narration")))
    narration = planning_recipe.get("narration") or {}
    if isinstance(narration, dict):
        parts.append(_as_text(narration.get("text")))
    return "\n".join(part for part in parts if part)


def _review_source_metadata(planning_recipe: dict[str, Any]) -> dict[str, Any]:
    source = planning_recipe.get("review_source")
    if isinstance(source, dict):
        return source

    review_proof = planning_recipe.get("review_proof") or {}
    if isinstance(review_proof, dict):
        selected_quote = review_proof.get("review_quote_for_proof") or review_proof.get("selected_quote")
    else:
        selected_quote = ""

    return {
        "text": planning_recipe.get("review_text") or planning_recipe.get("source_review_text") or "",
        "review_quote_for_proof": selected_quote or planning_recipe.get("review_quote_for_proof") or "",
        "inferred_fields": planning_recipe.get("inferred_fields") or [],
        "unsupported_story_elements": planning_recipe.get("unsupported_story_elements") or [],
    }


def validate_review_source_integrity(planning_recipe: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    source = _review_source_metadata(planning_recipe)
    review_text = _as_text(source.get("text")).strip()
    proof_quote = _as_text(source.get("review_quote_for_proof")).strip()
    inferred_fields = source.get("inferred_fields") or []
    unsupported_story_elements = source.get("unsupported_story_elements") or []

    if not review_text:
        issues.append(_issue("REVIEW_SOURCE_MISSING", "원본 리뷰 텍스트 메타데이터가 없습니다."))
    if not proof_quote:
        issues.append(_issue("REVIEW_QUOTE_FOR_PROOF_MISSING", "review_quote_for_proof가 없습니다."))
    elif review_text and _compact_text(proof_quote) not in _compact_text(review_text):
        issues.append(_issue("REVIEW_QUOTE_NOT_IN_SOURCE", "review_quote_for_proof가 원본 리뷰에 실제로 포함되어 있지 않습니다."))

    if unsupported_story_elements:
        issues.append(
            _issue(
                "UNSUPPORTED_STORY_ELEMENTS_PRESENT",
                "원문 근거 없는 스토리 요소가 남아 있습니다: " + ", ".join(map(str, unsupported_story_elements)),
            )
        )

    story_text = _flatten_planning_story_text(planning_recipe)
    compact_source = _compact_text(review_text)
    compact_story = _compact_text(story_text)
    compact_inferences = _compact_text(" ".join(map(str, inferred_fields)))

    for topic, keywords in RISK_TOPIC_KEYWORDS.items():
        story_has_topic = any(_compact_text(keyword) in compact_story for keyword in keywords)
        source_has_topic = any(_compact_text(keyword) in compact_source for keyword in keywords)
        inference_has_topic = any(_compact_text(keyword) in compact_inferences for keyword in keywords)
        if story_has_topic and not source_has_topic and not inference_has_topic:
            issues.append(
                _issue(
                    "UNSUPPORTED_RISK_TOPIC",
                    f"원문에 없는 위험 소재가 대본/기획에 등장합니다: {topic}",
                )
            )

    for keyword in STRONG_CLAIM_KEYWORDS:
        compact_keyword = _compact_text(keyword)
        if compact_keyword and compact_keyword in compact_story and compact_keyword not in compact_source:
            issues.append(
                _issue(
                    "UNSUPPORTED_STRONG_CLAIM",
                    f"원문 근거 없는 강한 claim 표현이 있습니다: {keyword}",
                )
            )

    for emotion, keywords in EMOTION_CLAIM_KEYWORDS.items():
        story_has_emotion = any(_compact_text(keyword) in compact_story for keyword in keywords)
        source_has_emotion = any(_compact_text(keyword) in compact_source for keyword in keywords)
        inference_has_emotion = any(_compact_text(keyword) in compact_inferences for keyword in keywords)
        if story_has_emotion and not source_has_emotion and not inference_has_emotion:
            issues.append(
                _issue(
                    "UNSUPPORTED_EMOTION_CLAIM",
                    f"원문에 없는 고객 감정 표현이 대본/기획에 등장합니다: {emotion}",
                )
            )

    return {
        "ok": not any(issue["severity"] == "fail" for issue in issues),
        "issues": issues,
    }


def _beat_duration(beat: dict[str, Any]) -> float:
    time_range = beat.get("time")
    if not isinstance(time_range, list | tuple) or len(time_range) != 2:
        return 0.0
    try:
        return max(0.0, float(time_range[1]) - float(time_range[0]))
    except (TypeError, ValueError):
        return 0.0


def _contains_corrupt_marker(text: str) -> bool:
    return any(marker in text for marker in CORRUPT_MARKERS)


def _total_narration_chars(beats: list[dict[str, Any]]) -> int:
    total = 0
    for beat in beats:
        narration = _as_text(beat.get("narration_ref") or beat.get("narration"))
        total += count_nonspace_chars(narration)
    return total


def validate_sync(edit_recipe: dict[str, Any], *, soft_limit: float = SOFT_CPS_LIMIT, hard_limit: float = HARD_CPS_LIMIT) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    scene_reports: list[dict[str, Any]] = []
    beats = edit_recipe.get("beats") or []

    if not beats:
        issues.append(_issue("NO_BEATS", "edit_recipe에 beats가 없습니다."))

    for index, beat in enumerate(beats, start=1):
        scene_id = _as_text(beat.get("id") or beat.get("scene_id") or f"scene_{index:02d}")
        narration = _as_text(beat.get("narration_ref") or beat.get("narration"))
        caption = _as_text(beat.get("caption"))
        asset = _as_text(beat.get("asset"))
        duration = _beat_duration(beat)
        chars = count_nonspace_chars(narration)
        scene_cps = round(chars / duration, 2) if duration > 0 else 0.0

        report = {
            "scene_id": scene_id,
            "asset": asset,
            "caption": caption,
            "narration": narration,
            "planned_time": beat.get("time"),
            "narration_chars_no_space": chars,
            "scene_cps": scene_cps,
            "risk": "pass",
        }

        if not narration:
            issues.append(_issue("MISSING_NARRATION_REF", "beat에 narration_ref가 없습니다.", scene_id=scene_id))
            report["risk"] = "fail"
        if duration <= 0:
            issues.append(_issue("INVALID_SCENE_TIME", "beat time 범위가 유효하지 않습니다.", scene_id=scene_id))
            report["risk"] = "fail"
        if narration and duration > 0 and scene_cps >= hard_limit:
            issues.append(
                _issue(
                    "SCENE_CPS_TOO_HIGH",
                    f"장면별 CPS가 {scene_cps}자/초로 하드 기준 {hard_limit} 이상입니다.",
                    scene_id=scene_id,
                )
            )
            report["risk"] = "fail"
        elif narration and duration > 0 and scene_cps > soft_limit:
            issues.append(
                _issue(
                    "SCENE_CPS_NEEDS_REVIEW",
                    f"장면별 CPS가 {scene_cps}자/초로 권장 기준 {soft_limit}를 넘습니다.",
                    scene_id=scene_id,
                    severity="warn",
                )
            )
            report["risk"] = "warn"

        if _contains_corrupt_marker(caption) or _contains_corrupt_marker(narration):
            issues.append(_issue("CORRUPT_TEXT_MARKER", "caption/narration에 깨진 문자 마커가 있습니다.", scene_id=scene_id))
            report["risk"] = "fail"

        scene_reports.append(report)

    return {
        "ok": not any(issue["severity"] == "fail" for issue in issues),
        "issues": issues,
        "scenes": scene_reports,
    }


def _audio_report(raw_tts_duration_sec: float | None, final_voice_duration_sec: float | None, *, total_chars: int = 0) -> dict[str, Any]:
    report: dict[str, Any] = {
        "raw_tts_duration_sec": raw_tts_duration_sec,
        "final_voice_duration_sec": final_voice_duration_sec,
        "compression_ratio": None,
        "total_narration_chars_no_space": total_chars,
        "total_voice_cps": None,
    }
    if raw_tts_duration_sec and final_voice_duration_sec and raw_tts_duration_sec > 0 and final_voice_duration_sec > 0:
        report["compression_ratio"] = round(float(raw_tts_duration_sec) / float(final_voice_duration_sec), 3)
    if final_voice_duration_sec and final_voice_duration_sec > 0:
        report["total_voice_cps"] = round(total_chars / float(final_voice_duration_sec), 2)
    return report


def build_sync_manifest(
    edit_recipe: dict[str, Any],
    *,
    raw_tts_duration_sec: float | None = None,
    final_voice_duration_sec: float | None = None,
) -> dict[str, Any]:
    sync_result = validate_sync(edit_recipe)
    issues = list(sync_result["issues"])
    scenes: list[dict[str, Any]] = []

    for beat_report, beat in zip(sync_result["scenes"], edit_recipe.get("beats") or []):
        meaning_match = beat.get("meaning_match") is True
        evidence = _as_text(beat.get("meaning_match_source") or beat.get("meaning_match_evidence")).strip()
        scene = {
            **beat_report,
            "duration_sec": round(_beat_duration(beat), 3),
            "meaning_match": meaning_match,
            "meaning_match_evidence": evidence,
            "meaning_match_source": evidence,
        }
        if meaning_match and not evidence:
            scene["risk"] = "fail"
        elif not meaning_match:
            scene["risk"] = "fail"
        scenes.append(scene)

    total_chars = _total_narration_chars(edit_recipe.get("beats") or [])
    audio = _audio_report(raw_tts_duration_sec, final_voice_duration_sec, total_chars=total_chars)
    if raw_tts_duration_sec is None:
        issues.append(_issue("RAW_TTS_DURATION_UNVERIFIED", "sync_manifest에 원본 TTS 길이가 없습니다."))
    elif raw_tts_duration_sec <= 0:
        issues.append(_issue("RAW_TTS_DURATION_INVALID", "sync_manifest의 원본 TTS 길이가 0 이하입니다."))
    if final_voice_duration_sec is None:
        issues.append(_issue("VOICE_DURATION_UNVERIFIED", "sync_manifest에 최종 voice 길이가 없습니다."))
    elif final_voice_duration_sec <= 0:
        issues.append(_issue("VOICE_DURATION_INVALID", "sync_manifest의 최종 voice 길이가 0 이하입니다."))
    compression = audio.get("compression_ratio")
    if compression is not None and compression >= 1.2:
        issues.append(_issue("VOICE_COMPRESSION_TOO_HIGH", f"원본/최종 음성 압축률이 {compression:.2f}배입니다."))
    total_voice_cps = audio.get("total_voice_cps")
    if total_voice_cps is not None and total_voice_cps >= HARD_CPS_LIMIT:
        issues.append(_issue("TOTAL_VOICE_CPS_TOO_HIGH", f"최종 음성 기준 전체 CPS가 {total_voice_cps:.2f}자/초입니다."))
    elif total_voice_cps is not None and total_voice_cps > SOFT_CPS_LIMIT:
        issues.append(
            _issue(
                "TOTAL_VOICE_CPS_NEEDS_REVIEW",
                f"최종 음성 기준 전체 CPS가 {total_voice_cps:.2f}자/초로 주의 구간입니다.",
                severity="warn",
            )
        )

    if any(not scene["meaning_match"] for scene in scenes):
        issues.append(_issue("MEANING_MATCH_UNVERIFIED", "sync_manifest에 meaning_match true가 아닌 scene이 있습니다."))
    if any(scene["meaning_match"] and not scene["meaning_match_evidence"] for scene in scenes):
        issues.append(_issue("MEANING_MATCH_EVIDENCE_MISSING", "sync_manifest에 meaning_match true지만 근거가 없는 scene이 있습니다."))

    return {
        "schema_version": "1.0",
        "ok": not any(issue["severity"] == "fail" for issue in issues),
        "audio": audio,
        "issues": issues,
        "scenes": scenes,
    }


def _scene_caption_text(scene: dict[str, Any]) -> str:
    caption = scene.get("caption")
    if isinstance(caption, dict):
        return _as_text(caption.get("text"))
    return _as_text(caption)


def _scene_asset_role(scene: dict[str, Any]) -> str:
    visual = scene.get("visual_source")
    if isinstance(visual, dict):
        return _as_text(visual.get("role"))
    return _as_text(scene.get("asset") or scene.get("visual_role"))


def _planning_scene_key(scene: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _scene_asset_role(scene).strip(),
        _scene_caption_text(scene).strip(),
        _as_text(scene.get("narration")).strip(),
    )


def _beat_key(beat: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _as_text(beat.get("asset")).strip(),
        _as_text(beat.get("caption")).strip(),
        _as_text(beat.get("narration_ref") or beat.get("narration")).strip(),
    )


def apply_sync_evidence(
    planning_recipe: dict[str, Any],
    edit_recipe: dict[str, Any],
    *,
    raw_tts_duration_sec: float,
    final_voice_duration_sec: float,
) -> dict[str, Any]:
    enriched = copy.deepcopy(edit_recipe)
    planning_scenes = planning_recipe.get("scenes") or []
    evidence_by_key: dict[tuple[str, str, str], str] = {}

    for index, scene in enumerate(planning_scenes, start=1):
        if scene.get("meaning_match") is not True:
            continue
        scene_id = _as_text(scene.get("scene_id") or scene.get("id") or f"s{index:02d}")
        evidence_by_key[_planning_scene_key(scene)] = f"planning_scene:{scene_id}"

    for beat in enriched.get("beats") or []:
        source = evidence_by_key.get(_beat_key(beat))
        if source:
            beat["meaning_match"] = True
            beat["meaning_match_source"] = source

    audio_plan = enriched.setdefault("audio_plan", {})
    sync_policy = audio_plan.setdefault("sync_policy", {})
    sync_policy["raw_tts_duration_sec"] = raw_tts_duration_sec
    sync_policy["final_voice_duration_sec"] = final_voice_duration_sec
    sync_policy["compression_ratio"] = (
        round(raw_tts_duration_sec / final_voice_duration_sec, 3)
        if raw_tts_duration_sec > 0 and final_voice_duration_sec > 0
        else None
    )

    enriched["sync_manifest"] = build_sync_manifest(
        enriched,
        raw_tts_duration_sec=raw_tts_duration_sec,
        final_voice_duration_sec=final_voice_duration_sec,
    )
    return enriched


def write_sync_manifest(path: str | Path, manifest: dict[str, Any]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def _analysis_missing(analysis: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in ("customer_problem", "before_pain", "after_change"):
        if not _as_text(analysis.get(field)).strip():
            missing.append(field)
    emotion = analysis.get("customer_emotion")
    if not emotion:
        missing.append("customer_emotion")
    return missing


def _planning_analysis(planning_recipe: dict[str, Any]) -> dict[str, Any]:
    nested = planning_recipe.get("analysis")
    if isinstance(nested, dict):
        merged = dict(nested)
    else:
        merged = {}
    for field in ("customer_problem", "before_pain", "after_change", "customer_emotion"):
        if not merged.get(field) and planning_recipe.get(field):
            merged[field] = planning_recipe[field]
    return merged


def _hook_text(planning_recipe: dict[str, Any]) -> str:
    selected_hook = planning_recipe.get("selected_hook") or {}
    text = selected_hook.get("text") or selected_hook.get("caption") or selected_hook.get("headline")
    return _as_text(text).replace("\n", " ").strip()


def _is_weak_hook(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return True
    return any(re.sub(r"\s+", "", phrase) in compact for phrase in WEAK_HOOK_PHRASES)


def _hook_has_pattern(text: str, pattern: str) -> bool:
    if pattern == r"\d":
        return re.search(pattern, text) is not None
    return _compact_text(pattern) in _compact_text(text)


def detect_hook_triggers(text: str) -> list[str]:
    triggers: list[str] = []
    for trigger, patterns in HOOK_TRIGGER_PATTERNS.items():
        if any(_hook_has_pattern(text, pattern) for pattern in patterns):
            triggers.append(trigger)
    return triggers


def validate_hook_formula(text: str) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    hook = _as_text(text).strip()
    triggers = detect_hook_triggers(hook)
    if not triggers:
        issues.append(
            _issue(
                "HOOK_TRIGGER_MISSING",
                "최종 훅에 호기심/숫자/타깃/통념반박/손실/결과 트리거가 없습니다.",
            )
        )
    return {
        "ok": not any(issue["severity"] == "fail" for issue in issues),
        "issues": issues,
        "triggers": triggers,
    }


def _review_capture_count(beats: list[dict[str, Any]]) -> int:
    count = 0
    for beat in beats:
        if _is_actual_review_capture(beat):
            count += 1
            continue
        for key in ("asset", "background_asset"):
            if _as_text(beat.get(key)) == "review_capture":
                count += 1
    return count


def _validate_generated_asset_metadata(beats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    required = ("generated_reason", "not_real_proof", "visual_claim", "literal_qa_result")
    for index, beat in enumerate(beats, start=1):
        if not beat.get("generated_asset"):
            continue
        scene_id = _as_text(beat.get("id") or f"scene_{index:02d}")
        missing = [field for field in required if beat.get(field) in (None, "", False)]
        if missing:
            issues.append(
                _issue(
                    "GENERATED_ASSET_METADATA_MISSING",
                    "생성 인서트에 필수 메타데이터가 없습니다: " + ", ".join(missing),
                    scene_id=scene_id,
                )
            )
    return issues


def _first_present(primary: dict[str, Any], secondary: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in primary:
            return primary[key]
        if key in secondary:
            return secondary[key]
    return None


def _validate_audio_metadata(
    edit_recipe: dict[str, Any],
    *,
    require_raw_tts: bool = False,
    minimum_cps: float | None = None,
    maximum_cps: float | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    audio_plan = edit_recipe.get("audio_plan") or {}
    sync_policy = audio_plan.get("sync_policy") or {}
    raw_duration = _first_present(
        audio_plan,
        sync_policy,
        "raw_tts_duration_sec",
        "source_voice_duration_sec",
    )
    final_duration = _first_present(
        audio_plan,
        sync_policy,
        "final_voice_duration_sec",
        "voice_duration_sec",
    )

    if final_duration is None:
        issues.append(_issue("VOICE_DURATION_UNVERIFIED", "최종 voice 길이 메타데이터가 없습니다. render_duration_sec는 대체값으로 인정하지 않습니다."))
        return issues

    try:
        final_value = float(final_duration)
    except (TypeError, ValueError):
        issues.append(_issue("VOICE_DURATION_INVALID", "최종 voice 길이 메타데이터가 숫자가 아닙니다."))
        return issues

    if final_value <= 0:
        issues.append(_issue("VOICE_DURATION_INVALID", "최종 voice 길이 메타데이터가 0 이하입니다."))
        return issues

    total_chars = _total_narration_chars(edit_recipe.get("beats") or [])
    total_voice_cps = round(total_chars / final_value, 2)
    if minimum_cps is not None and total_voice_cps < minimum_cps:
        issues.append(
            _issue(
                "TOTAL_VOICE_CPS_TOO_LOW",
                f"최종 음성 기준 전체 CPS가 {total_voice_cps:.2f}자/초로 one-shot 허용 최저 {minimum_cps:.1f} 미만입니다.",
            )
        )
    elif maximum_cps is not None and total_voice_cps > maximum_cps:
        issues.append(
            _issue(
                "TOTAL_VOICE_CPS_TOO_HIGH",
                f"최종 음성 기준 전체 CPS가 {total_voice_cps:.2f}자/초로 one-shot 허용 최고 {maximum_cps:.1f}를 넘습니다.",
            )
        )
    elif total_voice_cps >= HARD_CPS_LIMIT:
        issues.append(_issue("TOTAL_VOICE_CPS_TOO_HIGH", f"최종 음성 기준 전체 CPS가 {total_voice_cps:.2f}자/초로 실패 기준 {HARD_CPS_LIMIT} 이상입니다."))
    elif total_voice_cps > SOFT_CPS_LIMIT:
        issues.append(
            _issue(
                "TOTAL_VOICE_CPS_NEEDS_REVIEW",
                f"최종 음성 기준 전체 CPS가 {total_voice_cps:.2f}자/초로 권장 기준 {SOFT_CPS_LIMIT}를 넘습니다.",
                severity="warn",
            )
        )

    if raw_duration is not None:
        try:
            raw_value = float(raw_duration)
        except (TypeError, ValueError):
            issues.append(_issue("RAW_TTS_DURATION_INVALID", "원본 TTS 길이 메타데이터가 숫자가 아닙니다."))
            return issues
        if raw_value <= 0:
            issues.append(_issue("RAW_TTS_DURATION_INVALID", "원본 TTS 길이 메타데이터가 0 이하입니다."))
            return issues
        compression = raw_value / final_value
        if compression >= 1.2:
            issues.append(
                _issue(
                    "VOICE_COMPRESSION_TOO_HIGH",
                    f"원본/최종 음성 압축률이 {compression:.2f}배로 실패 기준 1.20 이상입니다.",
                )
            )
        elif compression >= 1.13:
            issues.append(
                _issue(
                    "VOICE_COMPRESSION_NEEDS_REVIEW",
                    f"원본/최종 음성 압축률이 {compression:.2f}배로 주의 구간입니다.",
                    severity="warn",
                )
            )
    else:
        severity = "fail" if require_raw_tts else "warn"
        issues.append(_issue("RAW_TTS_DURATION_UNVERIFIED", "원본 TTS 길이 메타데이터가 없어 압축률을 검증할 수 없습니다.", severity=severity))

    return issues


def _validate_privacy_metadata(edit_recipe: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    source = edit_recipe.get("source") or {}
    privacy_review = source.get("privacy_review") or edit_recipe.get("privacy_review") or {}
    sanitization_report = _as_text(source.get("privacy_sanitization_report") or edit_recipe.get("privacy_sanitization_report")).strip()

    checked = privacy_review.get("checked") is True if isinstance(privacy_review, dict) else False
    if not checked and not sanitization_report:
        issues.append(
            _issue(
                "PRIVACY_REVIEW_MISSING",
                "소재 개인정보 검수 메타데이터가 없습니다. 얼굴/가족사진/반사 얼굴/차량번호/송장/도어락/실명 검수 또는 익명화 리포트가 필요합니다.",
            )
        )

    if isinstance(privacy_review, dict):
        unresolved = privacy_review.get("unresolved_risks") or []
        if unresolved:
            issues.append(
                _issue(
                    "PRIVACY_RISK_UNRESOLVED",
                    "해결되지 않은 개인정보 위험이 남아 있습니다: " + ", ".join(map(str, unresolved)),
                )
            )

    return issues


def _role(value: dict[str, Any]) -> str:
    return _as_text(value.get("narrative_role") or value.get("role") or value.get("phase")).strip()


def _caption_has_literal_newline(text: str) -> bool:
    return r"\n" in text or "/n" in text


def _is_actual_review_capture(source: dict[str, Any]) -> bool:
    return _as_text(source.get("source_kind") or source.get("proof_asset_type")).strip() == "actual_review_capture"


def canonical_tts_input_narration(edit_recipe: dict[str, Any]) -> str:
    """Return whitespace-insensitive spoken text represented by edit beats."""
    beats = edit_recipe.get("beats") or []
    if not isinstance(beats, list):
        return ""
    normalized_beats = []
    for beat in beats:
        narration = beat.get("narration_ref") if isinstance(beat, dict) else ""
        normalized = unicodedata.normalize("NFC", _as_text(narration))
        normalized_beats.append(re.sub(r"\s+", " ", normalized).strip())
    return " ".join(part for part in normalized_beats if part)


def canonical_tts_input_sha256(edit_recipe: dict[str, Any]) -> str:
    """Hash the canonical TTS narration exactly as the one-shot evidence contract defines."""
    return hashlib.sha256(canonical_tts_input_narration(edit_recipe).encode("utf-8")).hexdigest()


SUPPORTED_MOTIONS = {
    "air_leak_wipe", "before_after_flash", "clean_glow_reveal", "clean_room_pan",
    "construction_focus", "cool_air_reveal", "detail_probe", "entry_path_pan",
    "heat_haze_problem", "keyword_pop", "measure_scan", "mission_clear_reveal",
    "obstacle_route_pan", "paper_crumple_pop", "precision_scan", "problem_shake",
    "product_card_flash", "rejection_stamp", "review_capture_scroll",
    "calm_glide_left", "calm_glide_right", "calm_glide_up", "calm_pull_out", "calm_push_in",
    "micro_pull_out", "micro_push_in", "review_capture_hold", "space_anxiety_pull", "static_hold",
}

STATIC_PHOTO_MOTIONS = {"review_capture_hold", "static_hold"}
MAX_ONE_SHOT_TOTAL_SHOTS = 12
ONE_SHOT_CALM_MOTIONS = {
    "calm_glide_left", "calm_glide_right", "calm_glide_up", "calm_pull_out", "calm_push_in",
    "review_capture_hold", "static_hold",
}
ONE_SHOT_CALM_TRANSITIONS = {"calm_dissolve", "cut"}
ONE_SHOT_BODY_CAPTION_SIZE = "medium"
MIN_ONE_SHOT_BODY_CAPTION_FONT_PX = 44
CAPTION_ACCENT_ONSET_EARLY_TOLERANCE_SEC = 0.20
CAPTION_ACCENT_ONSET_LATE_TOLERANCE_SEC = 0.45
MAX_REVIEW_UNDERLINE_START_DELAY_SEC = 0.10
MAX_REVIEW_UNDERLINE_DRAW_SEC = 0.20
# 렌더된 리뷰 캡처에서 한 줄 높이는 최소 이만큼은 떨어진다.
MIN_REVIEW_UNDERLINE_LINE_GAP_PCT = 1.0
CALM_DISSOLVE_MS = 380
CALM_SCALE_DELTA = 0.05
CALM_HORIZONTAL_TRAVEL_PX = 24
CALM_VERTICAL_TRAVEL_PX = 20
CAPTION_SAFE_TOP_PX = 220
CAPTION_SAFE_BOTTOM_PX = 1470
MAX_CONTEXTUAL_CAPTION_CHUNKS = 4
MIN_CONTEXTUAL_CAPTION_CHARS = 7
MIN_ONE_SHOT_HOOK_SHOT_SEC = 1.0
MIN_ONE_SHOT_FINAL_RESULT_SEC = 2.5

SUPPORTED_TRANSITIONS = {
    "card_pop", "caption_swap", "cross_dissolve", "cut", "flash_glow", "glow",
    "hit_flash", "paper_open", "pop", "slide_up", "smooth_cut", "smooth_slide",
    "calm_dissolve", "soft_cut", "soft_dissolve",
    "zoom_snap",
}


def _validate_beat_shots(beat: dict[str, Any], asset_roles: dict[str, Any], scene_id: str) -> list[dict[str, Any]]:
    """한 beat 안에서 사진이 여러 장 바뀔 때 자산·모션·구간을 검증한다."""
    shots = beat.get("shots")
    if shots in (None, []):
        motion = _as_text(beat.get("motion")).strip()
        if motion and motion not in SUPPORTED_MOTIONS:
            return [_issue("MOTION_UNSUPPORTED", f"Unsupported motion: {motion}", scene_id=scene_id)]
        return []
    if not isinstance(shots, list):
        return [_issue("BEAT_SHOTS_INVALID", "shots must be a list.", scene_id=scene_id)]

    issues: list[dict[str, Any]] = []
    try:
        beat_start, beat_end = float(beat["time"][0]), float(beat["time"][1])
    except (KeyError, IndexError, TypeError, ValueError):
        return [_issue("BEAT_SHOTS_INVALID", "Beat time is required for shots.", scene_id=scene_id)]

    previous_end = beat_start
    for index, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict):
            issues.append(_issue("BEAT_SHOTS_INVALID", f"shots[{index}] must be an object.", scene_id=scene_id))
            continue
        asset_id = _as_text(shot.get("asset_id")).strip()
        if not asset_id or asset_id not in asset_roles:
            issues.append(_issue("SHOT_ASSET_UNKNOWN", f"shots[{index}] asset_id must exist in asset_roles.", scene_id=scene_id))
        motion = _as_text(shot.get("motion")).strip()
        if motion and motion not in SUPPORTED_MOTIONS:
            issues.append(_issue("MOTION_UNSUPPORTED", f"shots[{index}] uses unsupported motion: {motion}", scene_id=scene_id))
        elif motion and motion not in STATIC_PHOTO_MOTIONS and not _as_text(shot.get("motion_reason")).strip():
            issues.append(
                _issue(
                    "SHOT_MOTION_REASON_MISSING",
                    f"shots[{index}] must explain why non-static motion supports the story.",
                    scene_id=scene_id,
                )
            )
        transition = _as_text(shot.get("transition_in")).strip()
        if transition and transition not in SUPPORTED_TRANSITIONS:
            issues.append(
                _issue(
                    "TRANSITION_UNSUPPORTED",
                    f"shots[{index}] uses unsupported transition: {transition}",
                    scene_id=scene_id,
                )
            )
        try:
            start, end = float(shot["start_sec"]), float(shot["end_sec"])
        except (KeyError, TypeError, ValueError):
            issues.append(_issue("SHOT_TIME_INVALID", f"shots[{index}] needs start_sec and end_sec.", scene_id=scene_id))
            continue
        if (
            end <= start
            or start < beat_start - 0.001
            or end > beat_end + 0.001
            or abs(start - previous_end) > 0.001
        ):
            issues.append(
                _issue("SHOT_TIME_INVALID", f"shots[{index}] must stay inside the beat and move forward.", scene_id=scene_id)
            )
        previous_end = end
    if abs(previous_end - beat_end) > 0.05:
        issues.append(_issue("SHOT_TIME_INVALID", "shots must cover the whole beat.", scene_id=scene_id))
    return issues


def _validate_result_first_hook_contract(edit_recipe: dict[str, Any]) -> list[dict[str, Any]]:
    """Require a compact result -> before -> result opening and cap total shot density."""
    issues: list[dict[str, Any]] = []
    beats = [beat for beat in edit_recipe.get("beats") or [] if isinstance(beat, dict)]
    total_shots = sum(len(beat.get("shots") or []) for beat in beats if isinstance(beat.get("shots") or [], list))
    if total_shots > MAX_ONE_SHOT_TOTAL_SHOTS:
        issues.append(
            _issue(
                "SHOT_DENSITY_EXCESSIVE",
                f"One-shot review reels may use at most {MAX_ONE_SHOT_TOTAL_SHOTS} shots; found {total_shots}.",
            )
        )

    evidence = edit_recipe.get("asset_evidence") or {}
    available_photo_assets = {
        _as_text(asset_id).strip()
        for asset_id, metadata in evidence.items()
        if isinstance(metadata, dict)
        and _as_text(metadata.get("evidence_class")).strip() != "review_capture"
        and _as_text(asset_id).strip()
    }
    non_review_shots = [
        shot
        for beat in beats
        for shot in beat.get("shots") or []
        if isinstance(shot, dict) and _as_text(shot.get("asset_id")).strip() in available_photo_assets
    ]
    used_photo_assets = {_as_text(shot.get("asset_id")).strip() for shot in non_review_shots}
    if len(non_review_shots) >= 8:
        minimum_distinct = min(6, len(available_photo_assets), (len(non_review_shots) + 1) // 2)
        if len(used_photo_assets) < minimum_distinct:
            issues.append(
                _issue(
                    "PHOTO_VARIETY_LOW",
                    "A long photo edit is recycling too few of the available narrative-safe assets: "
                    f"used {len(used_photo_assets)}, expected at least {minimum_distinct} distinct photos.",
                    severity="warn",
                )
            )

    contract = edit_recipe.get("hook_visual_contract")
    if not isinstance(contract, dict):
        return issues + [_issue("RESULT_FIRST_HOOK_MISSING", "hook_visual_contract is required.")]
    result_asset_id = _as_text(contract.get("result_asset_id")).strip()
    before_asset_id = _as_text(contract.get("before_asset_id")).strip()
    if not result_asset_id or not before_asset_id or result_asset_id == before_asset_id:
        return issues + [_issue("RESULT_FIRST_HOOK_INVALID", "Result and before asset IDs must be distinct and non-empty.")]

    first_beat = beats[0] if beats else {}
    shots = first_beat.get("shots") or []
    sequence = [_as_text(shot.get("asset_id")).strip() for shot in shots[:3] if isinstance(shot, dict)]
    if sequence != [result_asset_id, before_asset_id, result_asset_id]:
        issues.append(
            _issue(
                "RESULT_FIRST_HOOK_SEQUENCE_INVALID",
                "The opening must show result -> before -> result in its first three shots.",
                scene_id=_as_text(first_beat.get("id") or "scene_01"),
            )
        )

    opening_shots = shots[:3] if isinstance(shots, list) else []
    if len(opening_shots) == 3:
        for index, shot in enumerate(opening_shots):
            if not isinstance(shot, dict):
                continue
            shot_asset_id = _as_text(shot.get("asset_id")).strip()
            evidence = _as_text(shot.get("meaning_match_source")).strip()
            if not evidence or f"asset_evidence:{shot_asset_id}" not in evidence or "narration_fragment:" not in evidence:
                issues.append(
                    _issue(
                        "HOOK_SHOT_MEANING_EVIDENCE_MISSING",
                        f"Hook shots[{index}] must bind its asset and spoken narration fragment as meaning evidence.",
                        scene_id=_as_text(first_beat.get("id") or "scene_01"),
                    )
                )
    return issues


def _validate_visual_evidence_contract(
    planning_recipe: dict[str, Any], edit_recipe: dict[str, Any]
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    evidence = edit_recipe.get("asset_evidence")
    if not isinstance(evidence, dict) or not evidence:
        return [_issue("ASSET_EVIDENCE_CONTRACT_MISSING", "asset_evidence is required for one-shot production.")]

    used_assets = {
        _as_text(shot.get("asset_id")).strip()
        for beat in edit_recipe.get("beats") or []
        if isinstance(beat, dict)
        for shot in beat.get("shots") or []
        if isinstance(shot, dict) and _as_text(shot.get("asset_id")).strip()
    }
    evidence_classes_by_asset: dict[str, str] = {}
    for asset_id, metadata in evidence.items():
        if not isinstance(asset_id, str) or not isinstance(metadata, dict):
            issues.append(_issue("ASSET_EVIDENCE_INVALID", "Every asset_evidence entry must be an object."))
            continue
        evidence_class = _as_text(metadata.get("evidence_class")).strip()
        if evidence_class not in VISUAL_EVIDENCE_CLASSES:
            issues.append(_issue("ASSET_EVIDENCE_INVALID", f"Unsupported evidence class for {asset_id}: {evidence_class or '(empty)'}"))
            continue
        evidence_classes_by_asset[asset_id] = evidence_class

    missing_metadata = sorted(used_assets - set(evidence_classes_by_asset))
    if missing_metadata:
        issues.append(
            _issue(
                "USED_ASSET_EVIDENCE_MISSING",
                "Used photo assets are missing evidence metadata: " + ", ".join(missing_metadata),
            )
        )

    used_classes = {evidence_classes_by_asset[asset_id] for asset_id in used_assets if asset_id in evidence_classes_by_asset}
    missing_base = sorted(BASE_REQUIRED_VISUAL_EVIDENCE - used_classes)
    if missing_base:
        issues.append(
            _issue(
                "REQUIRED_VISUAL_EVIDENCE_MISSING",
                "Required one-shot evidence classes are not used: " + ", ".join(missing_base),
            )
        )

    hook = edit_recipe.get("hook_visual_contract") or {}
    result_asset_id = _as_text(hook.get("result_asset_id")).strip()
    before_asset_id = _as_text(hook.get("before_asset_id")).strip()
    result_metadata = evidence.get(result_asset_id) if isinstance(evidence.get(result_asset_id), dict) else {}
    before_metadata = evidence.get(before_asset_id) if isinstance(evidence.get(before_asset_id), dict) else {}
    if (
        result_metadata.get("evidence_class") != "installed_result"
        or (result_metadata.get("visual_quality") or {}).get("full_product_visible") is not True
    ):
        issues.append(
            _issue(
                "HOOK_RESULT_NOT_FULLY_VISIBLE",
                "The result-first hook must use an installed_result asset whose full product is visible.",
            )
        )
    if before_metadata.get("evidence_class") != "before_state":
        issues.append(_issue("HOOK_BEFORE_EVIDENCE_INVALID", "The comparison hook must use a before_state asset."))

    story_text = " ".join(
        [
            _as_text((planning_recipe.get("review_source") or {}).get("text")),
            *(
                f"{_as_text(beat.get('caption'))} {_as_text(beat.get('narration_ref'))}"
                for beat in edit_recipe.get("beats") or []
                if isinstance(beat, dict)
            ),
        ]
    )
    for evidence_class, keywords in CLAIM_EVIDENCE_KEYWORDS.items():
        if any(keyword in story_text for keyword in keywords) and evidence_class not in used_classes:
            issues.append(
                _issue(
                    "CLAIM_EVIDENCE_MISSING",
                    f"The story claims {evidence_class}, but no matching evidence asset is used.",
                )
            )

    for asset_id, evidence_class in evidence_classes_by_asset.items():
        if (
            evidence_class in HIGH_VALUE_VISUAL_EVIDENCE
            and asset_id not in used_assets
            and not _as_text(evidence[asset_id].get("unused_reason")).strip()
        ):
            issues.append(
                _issue(
                    "UNUSED_HIGH_VALUE_EVIDENCE_REASON_MISSING",
                    f"Unused high-value evidence needs a reason: {asset_id} ({evidence_class}).",
                )
            )
    return issues


def _validate_one_shot_visual_edit_contract(edit_recipe: dict[str, Any]) -> list[dict[str, Any]]:
    """Lock production one-shot reels to the approved calm-photo editing language."""
    issues: list[dict[str, Any]] = []
    beats = [beat for beat in edit_recipe.get("beats") or [] if isinstance(beat, dict)]
    contract = edit_recipe.get("hook_visual_contract") or {}
    result_asset_id = _as_text(contract.get("result_asset_id")).strip()

    for beat_index, beat in enumerate(beats):
        scene_id = _as_text(beat.get("id") or f"scene_{beat_index + 1:02d}")
        shots = beat.get("shots")
        if not isinstance(shots, list) or not shots:
            issues.append(
                _issue(
                    "ONE_SHOT_SHOTS_REQUIRED",
                    "Every production one-shot beat must declare the exact photo shots it renders.",
                    scene_id=scene_id,
                )
            )
            shots = []

        caption_chunks = beat.get("caption_chunks")
        if not isinstance(caption_chunks, list) or not caption_chunks:
            issues.append(
                _issue(
                    "ONE_SHOT_CAPTION_CHUNKS_REQUIRED",
                    "Every production one-shot beat must provide contextual caption chunks bound to the narration.",
                    scene_id=scene_id,
                )
            )

        layout = beat.get("caption_layout") or {}
        size = _as_text(layout.get("size")).strip()
        theme = _as_text(layout.get("theme")).strip()
        emphasis = beat.get("caption_emphasis")
        accent = beat.get("caption_accent") or {}
        if beat_index == 0:
            if size != "hero-calm":
                issues.append(_issue("HOOK_CAPTION_SIZE_INVALID", "The opening caption must use hero-calm.", scene_id=scene_id))
        elif size != ONE_SHOT_BODY_CAPTION_SIZE:
            issues.append(
                _issue(
                    "ONE_SHOT_BODY_CAPTION_SIZE_INCONSISTENT",
                    "Non-hook one-shot captions must keep the medium body size instead of shrinking during the story.",
                    scene_id=scene_id,
                )
            )
        try:
            minimum_font_px = float(layout.get("min_font_px"))
        except (TypeError, ValueError):
            minimum_font_px = 0.0
        if beat_index > 0 and minimum_font_px < MIN_ONE_SHOT_BODY_CAPTION_FONT_PX:
            issues.append(
                _issue(
                    "ONE_SHOT_BODY_CAPTION_SIZE_INCONSISTENT",
                    f"Non-hook one-shot captions need at least {MIN_ONE_SHOT_BODY_CAPTION_FONT_PX}px.",
                    scene_id=scene_id,
                )
            )
        if theme != "white":
            issues.append(
                _issue(
                    "ONE_SHOT_CAPTION_THEME_INVALID",
                    "Production one-shot captions use the white ivory-and-mint theme.",
                    scene_id=scene_id,
                )
            )
        if not isinstance(emphasis, list) or len(emphasis) != 1 or not _as_text(emphasis[0]).strip():
            issues.append(
                _issue(
                    "CAPTION_EMPHASIS_DENSITY_INVALID",
                    "Each production one-shot beat needs exactly one emphasis keyword.",
                    scene_id=scene_id,
                )
            )
        if accent.get("enabled") is not True:
            issues.append(
                _issue(
                    "CAPTION_ACCENT_REQUIRED",
                    "The single one-shot emphasis keyword must enable the restrained accent treatment.",
                    scene_id=scene_id,
                )
            )
        elif isinstance(emphasis, list) and len(emphasis) == 1:
            keyword = _compact_text(emphasis[0]).casefold()
            matching_chunk = None
            keyword_index = -1
            for chunk in caption_chunks if isinstance(caption_chunks, list) else []:
                if not isinstance(chunk, dict):
                    continue
                display_text = _as_text(chunk.get("display_text") or chunk.get("text"))
                compact_display = _compact_text(display_text).casefold()
                candidate_index = compact_display.find(keyword)
                if keyword and candidate_index >= 0:
                    matching_chunk = chunk
                    keyword_index = candidate_index
                    break
            try:
                accent_start = float(accent.get("start_sec"))
                chunk_start = float(matching_chunk["start_sec"])
                chunk_end = float(matching_chunk["end_sec"])
                compact_display = _compact_text(
                    matching_chunk.get("display_text") or matching_chunk.get("text")
                ).casefold()
                estimated_onset = chunk_start + (chunk_end - chunk_start) * (
                    keyword_index / max(len(compact_display), 1)
                )
            except (KeyError, TypeError, ValueError):
                issues.append(
                    _issue(
                        "CAPTION_ACCENT_VOICE_SYNC_INVALID",
                        "Caption accent needs an absolute start_sec bound to the chunk containing its spoken keyword.",
                        scene_id=scene_id,
                    )
                )
            else:
                if (
                    accent_start < chunk_start - 0.001
                    or accent_start > chunk_end + 0.001
                    or accent_start < estimated_onset - CAPTION_ACCENT_ONSET_EARLY_TOLERANCE_SEC
                    or accent_start > estimated_onset + CAPTION_ACCENT_ONSET_LATE_TOLERANCE_SEC
                ):
                    issues.append(
                        _issue(
                            "CAPTION_ACCENT_VOICE_SYNC_INVALID",
                            "Caption accent start_sec must follow the estimated spoken onset of its keyword.",
                            scene_id=scene_id,
                        )
                    )

        for shot_index, shot in enumerate(shots):
            if not isinstance(shot, dict):
                continue
            motion = _as_text(shot.get("motion") or beat.get("motion")).strip()
            transition = _as_text(shot.get("transition_in")).strip()
            if motion not in ONE_SHOT_CALM_MOTIONS:
                issues.append(
                    _issue(
                        "ONE_SHOT_MOTION_NOT_CALM",
                        f"Production one-shot motion is too aggressive or undefined: {motion or '(empty)'}.",
                        scene_id=scene_id,
                    )
                )
            if transition not in ONE_SHOT_CALM_TRANSITIONS:
                issues.append(
                    _issue(
                        "ONE_SHOT_TRANSITION_NOT_CALM",
                        f"Production one-shot transition is too aggressive or undefined: {transition or '(empty)'}.",
                        scene_id=scene_id,
                    )
                )
            elif beat_index > 0 and transition != "calm_dissolve":
                issues.append(
                    _issue(
                        "ONE_SHOT_TRANSITION_NOT_CALM",
                        "Photo changes after the opening must use calm_dissolve.",
                        scene_id=scene_id,
                    )
                )

        shot_motion_paths = {
            _as_text(shot.get("motion") or beat.get("motion")).strip()
            for shot in shots
            if isinstance(shot, dict)
        }
        if len(shot_motion_paths) > 1:
            issues.append(
                _issue(
                    "SHOT_MOTION_PATH_DISCONTINUITY",
                    "All photo shots inside one production beat must keep one camera direction.",
                    scene_id=scene_id,
                )
            )

        if beat_index == 0 and shots:
            transitions = [_as_text(shot.get("transition_in")).strip() for shot in shots if isinstance(shot, dict)]
            if len(shots) != 3 or transitions != ["cut", "calm_dissolve", "calm_dissolve"]:
                issues.append(
                    _issue(
                        "HOOK_TRANSITION_SEQUENCE_INVALID",
                        "The opening transitions must be cut -> calm_dissolve -> calm_dissolve across exactly three shots.",
                        scene_id=scene_id,
                    )
                )
            for shot in shots[:3]:
                try:
                    duration = float(shot["end_sec"]) - float(shot["start_sec"])
                except (KeyError, TypeError, ValueError):
                    continue
                if duration < MIN_ONE_SHOT_HOOK_SHOT_SEC - 0.001:
                    issues.append(
                        _issue(
                            "HOOK_SHOT_TOO_SHORT",
                            f"Each opening comparison shot must stay at least {MIN_ONE_SHOT_HOOK_SHOT_SEC:.1f} seconds.",
                            scene_id=scene_id,
                        )
                    )
                    break

        if _role(beat) == "review_proof" and (
            len(shots) != 1
            or _as_text(beat.get("motion")).strip() != "review_capture_hold"
            or any(_as_text(shot.get("motion")).strip() != "review_capture_hold" for shot in shots if isinstance(shot, dict))
        ):
            issues.append(
                _issue(
                    "REVIEW_PROOF_MUST_HOLD_STILL",
                    "Review proof must use one static review_capture_hold shot.",
                    scene_id=scene_id,
                )
            )

    if beats:
        final_beat = beats[-1]
        final_shots = final_beat.get("shots") or []
        final_shot = final_shots[-1] if isinstance(final_shots, list) and final_shots else {}
        try:
            final_dwell = float(final_shot["end_sec"]) - float(final_shot["start_sec"])
        except (KeyError, TypeError, ValueError):
            final_dwell = 0.0
        if (
            not result_asset_id
            or _as_text(final_shot.get("asset_id")).strip() != result_asset_id
            or final_dwell < MIN_ONE_SHOT_FINAL_RESULT_SEC - 0.001
        ):
            issues.append(
                _issue(
                    "FINAL_RESULT_DWELL_INVALID",
                    f"The final shot must hold the completed result for at least {MIN_ONE_SHOT_FINAL_RESULT_SEC:.1f} seconds.",
                    scene_id=_as_text(final_beat.get("id") or "scene_final"),
                )
            )
    return issues


def _validate_review_emphasis_contract(
    planning_recipe: dict[str, Any], edit_recipe: dict[str, Any]
) -> list[dict[str, Any]]:
    """Bind the review underline to exact source text, review timing, and normalized geometry."""
    review_beat = next(
        (beat for beat in edit_recipe.get("beats") or [] if isinstance(beat, dict) and _role(beat) == "review_proof"),
        None,
    )
    emphasis = (review_beat or {}).get("review_emphasis")
    if not isinstance(emphasis, dict):
        return [_issue("REVIEW_EMPHASIS_MISSING", "The review proof beat needs review_emphasis evidence.")]

    issues: list[dict[str, Any]] = []
    quote = _as_text(emphasis.get("quote")).strip()
    review_text = _as_text(_review_source_metadata(planning_recipe).get("text")).strip()
    if not quote or _compact_text(quote) not in _compact_text(review_text):
        issues.append(
            _issue(
                "REVIEW_EMPHASIS_QUOTE_NOT_IN_SOURCE",
                "review_emphasis.quote must be an exact source-review substring after whitespace normalization.",
            )
        )

    try:
        beat_start, beat_end = float(review_beat["time"][0]), float(review_beat["time"][1])
        start, end = float(emphasis["start_sec"]), float(emphasis["end_sec"])
    except (KeyError, IndexError, TypeError, ValueError):
        start = end = beat_start = beat_end = 0.0
        issues.append(_issue("REVIEW_EMPHASIS_TIME_INVALID", "Review emphasis needs numeric timing inside the review beat."))
    else:
        if end <= start or start < beat_start - 0.001 or end > beat_end + 0.001:
            issues.append(_issue("REVIEW_EMPHASIS_TIME_INVALID", "Review emphasis timing must stay inside the review beat."))
        try:
            draw_duration = float(emphasis["draw_duration_sec"])
        except (KeyError, TypeError, ValueError):
            draw_duration = 0.0
        if (
            start - beat_start > MAX_REVIEW_UNDERLINE_START_DELAY_SEC + 0.001
            or draw_duration <= 0
            or draw_duration > MAX_REVIEW_UNDERLINE_DRAW_SEC + 0.001
        ):
            issues.append(
                _issue(
                    "REVIEW_EMPHASIS_NOT_IMMEDIATE",
                    "The review underline must begin with the review scene and finish drawing within 0.20 seconds.",
                )
            )

    segments = emphasis.get("segments")
    if not isinstance(segments, list) or not 1 <= len(segments) <= 3:
        issues.append(_issue("REVIEW_EMPHASIS_SEGMENT_INVALID", "Review emphasis needs one to three underline segments."))
        return issues

    geometry_ok = True
    previous_top: float | None = None
    for segment in segments:
        try:
            left = float(segment["left_pct"])
            top = float(segment["top_pct"])
            width = float(segment["width_pct"])
        except (KeyError, TypeError, ValueError):
            issues.append(_issue("REVIEW_EMPHASIS_SEGMENT_INVALID", "Underline segments need numeric left/top/width percentages."))
            geometry_ok = False
            break
        if left < 0 or top < 0 or width <= 0 or left + width > 100 or top > 100:
            issues.append(_issue("REVIEW_EMPHASIS_SEGMENT_INVALID", "Underline segments must stay inside the review capture."))
            geometry_ok = False
            break
        # 캡처 안에서 인용문은 위에서 아래로 읽힌다. 같은 높이를 두 번 쓰거나
        # 거슬러 올라가면 좌표를 눈대중으로 찍었다는 뜻이다.
        if previous_top is not None and top <= previous_top + MIN_REVIEW_UNDERLINE_LINE_GAP_PCT - 0.001:
            issues.append(
                _issue(
                    "REVIEW_EMPHASIS_SEGMENT_ORDER_INVALID",
                    "Underline segments must move down the capture, one rendered line at a time.",
                )
            )
            geometry_ok = False
            break
        previous_top = top

    if not geometry_ok:
        return issues

    # 엔진은 캡처 이미지를 읽지 못하므로 top_pct가 맞는 줄인지 스스로 알 수 없다.
    # 대신 segment마다 그 줄이 실제로 덮는 인용문 조각을 받아 적게 해서,
    # 줄 수가 틀리면 (120번처럼 두 줄을 segment 하나로 처리하면) 반드시 걸리게 한다.
    line_texts = [_as_text(segment.get("line_text")).strip() for segment in segments]
    if not all(line_texts):
        issues.append(
            _issue(
                "REVIEW_EMPHASIS_SEGMENT_TEXT_MISMATCH",
                "Every underline segment needs line_text naming the quote fragment that rendered line covers.",
            )
        )
    elif _compact_text("".join(line_texts)) != _compact_text(quote):
        issues.append(
            _issue(
                "REVIEW_EMPHASIS_SEGMENT_TEXT_MISMATCH",
                "Joining every segment line_text must reproduce review_emphasis.quote exactly, "
                "so the underline covers the whole quote and nothing else.",
            )
        )
    return issues


def _split_sentences(text: str) -> list[str]:
    """마침표/물음표/느낌표 뒤에서 끊어 낭독 단위 문장을 얻는다."""
    return [part.strip() for part in re.split(r"(?<=[.?!])\s+", _as_text(text).strip()) if part.strip()]


def _validate_caption_chunks(beat: dict[str, Any], scene_id: str) -> list[dict[str, Any]]:
    """D-027: 구절 자막을 이어붙이면 내레이션 전문과 글자까지 같아야 한다."""
    chunks = beat.get("caption_chunks")
    if chunks in (None, []):
        return []
    issues: list[dict[str, Any]] = []
    if not isinstance(chunks, list):
        return [_issue("CAPTION_CHUNKS_INVALID", "caption_chunks must be a list.", scene_id=scene_id)]
    if len(chunks) > MAX_CONTEXTUAL_CAPTION_CHUNKS:
        issues.append(
            _issue(
                "CAPTION_CHUNK_DENSITY_EXCESSIVE",
                "A beat may use at most four contextual caption phrases.",
                scene_id=scene_id,
            )
        )

    narration = _compact_text(_as_text(beat.get("narration_ref")))
    joined = _compact_text(" ".join(_as_text(chunk.get("text")) for chunk in chunks if isinstance(chunk, dict)))
    if joined != narration:
        issues.append(
            _issue(
                "CAPTION_TEXT_NOT_NARRATION",
                "구절 자막을 이어붙인 결과가 내레이션 전문과 다릅니다. 자막은 음성을 축약하지 않습니다.",
                scene_id=scene_id,
            )
        )

    try:
        beat_start, beat_end = float(beat["time"][0]), float(beat["time"][1])
    except (KeyError, IndexError, TypeError, ValueError):
        return issues + [_issue("CAPTION_CHUNK_TIME_INVALID", "Beat time is required for caption chunks.", scene_id=scene_id)]

    previous_end = beat_start
    for index, chunk in enumerate(chunks, start=1):
        if not isinstance(chunk, dict) or not _as_text(chunk.get("text")).strip():
            issues.append(_issue("CAPTION_CHUNKS_INVALID", f"caption_chunks[{index}] needs text.", scene_id=scene_id))
            continue
        chunk_text = _as_text(chunk.get("text")).strip()
        if re.search(r"[.!?。！？]\s*\S", chunk_text):
            issues.append(
                _issue(
                    "CAPTION_CHUNK_SENTENCE_BOUNDARY_INVALID",
                    f"caption_chunks[{index}] must end when a spoken sentence ends.",
                    scene_id=scene_id,
                )
            )
        display_text = chunk.get("display_text")
        if display_text is not None:
            digit_words = str.maketrans({"0": "영", "1": "일", "2": "이", "3": "삼", "4": "사", "5": "오", "6": "육", "7": "칠", "8": "팔", "9": "구"})
            spoken_key = re.sub(r"[^0-9A-Za-z가-힣]", "", _as_text(chunk.get("text"))).translate(digit_words).casefold()
            display_key = re.sub(r"[^0-9A-Za-z가-힣]", "", _as_text(display_text)).translate(digit_words).casefold()
            if not display_key or display_key != spoken_key:
                issues.append(
                    _issue(
                        "CAPTION_DISPLAY_TEXT_MISMATCH",
                        f"caption_chunks[{index}].display_text may normalize number glyphs and spacing only.",
                        scene_id=scene_id,
                    )
                )
        readable_chars = len(re.sub(r"[^0-9A-Za-z가-힣]", "", _as_text(chunk.get("text"))))
        if len(chunks) > 1 and readable_chars < MIN_CONTEXTUAL_CAPTION_CHARS:
            issues.append(
                _issue(
                    "CAPTION_CHUNK_CONTEXT_TOO_THIN",
                    f"caption_chunks[{index}] is too short to carry understandable context.",
                    scene_id=scene_id,
                )
            )
        lines = _as_text(chunk.get("text")).split("\n")
        if not 1 <= len(lines) <= 2:
            issues.append(
                _issue("CAPTION_CHUNK_LINE_COUNT_INVALID", f"caption_chunks[{index}] must have one or two lines.", scene_id=scene_id)
            )
        try:
            start, end = float(chunk["start_sec"]), float(chunk["end_sec"])
        except (KeyError, TypeError, ValueError):
            issues.append(_issue("CAPTION_CHUNK_TIME_INVALID", f"caption_chunks[{index}] needs start_sec and end_sec.", scene_id=scene_id))
            continue
        if (
            end <= start
            or start < beat_start - 0.001
            or end > beat_end + 0.001
            or abs(start - previous_end) > 0.001
        ):
            issues.append(
                _issue(
                    "CAPTION_CHUNK_TIME_INVALID",
                    f"caption_chunks[{index}] must stay inside the beat and move forward.",
                    scene_id=scene_id,
                )
            )
        previous_end = end
    if abs(previous_end - beat_end) > 0.001:
        issues.append(
            _issue(
                "CAPTION_CHUNK_TIME_INVALID",
                "Caption chunks must cover the entire beat without gaps.",
                scene_id=scene_id,
            )
        )
    return issues


def validate_review_reels_one_shot_contract(planning_recipe: dict[str, Any], edit_recipe: dict[str, Any]) -> dict[str, Any]:
    """Validate the HTML-only one-shot contract without granting MP4 authority."""
    issues: list[dict[str, Any]] = []
    scaffold = planning_recipe.get("scaffold") or edit_recipe.get("scaffold")
    if isinstance(scaffold, dict) and (
        scaffold.get("status") != "complete" or scaffold.get("pending_fields")
    ):
        issues.append(
            _issue(
                "RECIPE_SCAFFOLD_INCOMPLETE",
                "Complete every scaffold pending field and set scaffold.status to complete before production.",
            )
        )
    elif isinstance(scaffold, dict):
        serialized = json.dumps({"planning": planning_recipe, "edit": edit_recipe}, ensure_ascii=False)
        if "TODO" in serialized:
            issues.append(
                _issue(
                    "RECIPE_SCAFFOLD_PLACEHOLDER_REMAINS",
                    "A scaffold cannot become complete while TODO content values remain.",
                )
            )
    contract = planning_recipe.get("workflow_contract") or {}
    if _as_text(contract.get("name")).strip() != ONE_SHOT_CONTRACT_NAME:
        issues.append(_issue("ONE_SHOT_CONTRACT_MISSING", f"workflow_contract.name must be {ONE_SHOT_CONTRACT_NAME}."))
    if contract.get("html_scope_authorized") is not True:
        issues.append(_issue("HTML_SCOPE_NOT_AUTHORIZED", "The one-shot contract must explicitly authorize HTML scope."))
    if contract.get("mp4_scope_authorized") is not False:
        issues.append(_issue("MP4_SCOPE_MUST_REMAIN_UNAUTHORIZED", "The one-shot contract must not authorize MP4 rendering."))
    issues.extend(_validate_result_first_hook_contract(edit_recipe))
    issues.extend(_validate_visual_evidence_contract(planning_recipe, edit_recipe))
    issues.extend(_validate_one_shot_visual_edit_contract(edit_recipe))
    issues.extend(_validate_review_emphasis_contract(planning_recipe, edit_recipe))

    writer_brief = planning_recipe.get("writer_brief") or {}
    required_writer_fields = (
        "story_mode",
        "one_line_story",
        "hook_candidates",
        "recommended_hook",
        "review_quote_for_proof",
    )
    missing_writer = [field for field in required_writer_fields if not writer_brief.get(field)]
    if missing_writer:
        issues.append(_issue("WRITER_BRIEF_INCOMPLETE", "writer_brief is missing: " + ", ".join(missing_writer)))
    story_mode = _as_text(writer_brief.get("story_mode")).strip()
    if story_mode and story_mode not in SUPPORTED_STORY_MODES:
        issues.append(_issue("STORY_MODE_INVALID", f"Unsupported one-shot story mode: {story_mode}"))

    photo_qa = planning_recipe.get("photo_qa") or {}
    if photo_qa.get("checked") is not True:
        issues.append(_issue("PHOTO_QA_MISSING", "Photo role and privacy QA must be complete before the script."))
    if not isinstance(photo_qa.get("asset_count"), int) or photo_qa.get("asset_count", 0) <= 0:
        issues.append(_issue("PHOTO_INVENTORY_MISSING", "photo_qa.asset_count must record reviewed photos."))
    first_frame_asset_id = _as_text(photo_qa.get("first_frame_asset_id")).strip()
    if not first_frame_asset_id:
        issues.append(_issue("FIRST_FRAME_EVIDENCE_MISSING", "photo_qa.first_frame_asset_id is required."))

    scenes = planning_recipe.get("scenes") or []
    scene_roles = [_role(scene) for scene in scenes if isinstance(scene, dict)]
    missing_roles = [role for role in REQUIRED_NARRATIVE_ROLES if role not in scene_roles]
    if missing_roles:
        issues.append(_issue("NARRATIVE_ROLE_MISSING", "Narrative roles are missing: " + ", ".join(missing_roles)))
    if scene_roles and scene_roles[0] != "event":
        issues.append(_issue("STORY_MUST_START_WITH_EVENT", "The first scene must be a customer event."))

    role_index = {role: scene_roles.index(role) for role in NARRATIVE_ROLE_ORDER if role in scene_roles}
    ordered_roles = [role_index[role] for role in NARRATIVE_ROLE_ORDER if role in role_index]
    if len(ordered_roles) > 1 and ordered_roles != sorted(ordered_roles):
        issues.append(_issue("NARRATIVE_ROLE_ORDER_INVALID", "Narrative roles must stay in the one-shot order."))

    if scenes:
        first_scene = scenes[0] if isinstance(scenes[0], dict) else {}
        first_visual = first_scene.get("visual_source") or {}
        if not isinstance(first_visual, dict) or _as_text(first_visual.get("source_kind")).strip() != "customer_photo":
            issues.append(_issue("FIRST_FRAME_NOT_PHOTO_EVIDENCE", "The first frame must use a customer-photo evidence asset."))
        elif first_frame_asset_id and _as_text(first_visual.get("asset_id")).strip() != first_frame_asset_id:
            issues.append(_issue("FIRST_FRAME_EVIDENCE_MISMATCH", "The first scene and photo QA must identify the same asset."))

    review_scene = next((scene for scene in scenes if isinstance(scene, dict) and _role(scene) == "review_proof"), None)
    review_visual = (review_scene or {}).get("visual_source") or {}
    review_proof = planning_recipe.get("review_proof") or {}
    if not _is_actual_review_capture(review_visual if isinstance(review_visual, dict) else {}):
        issues.append(_issue("REVIEW_PROOF_NOT_ACTUAL_CAPTURE", "Review proof must use an actual review capture."))
    if _as_text(review_proof.get("source_capture_kind")).strip() != "actual_review_capture":
        issues.append(_issue("REVIEW_PROOF_SOURCE_UNVERIFIED", "review_proof.source_capture_kind must be actual_review_capture."))

    audio_sync = planning_recipe.get("audio_sync") or {}
    sync_checks = audio_sync.get("sync_checks") or {}
    if _as_text(audio_sync.get("mode")).strip() != "voice_aligned" or sync_checks.get("screen_ahead_of_voice") is not False:
        issues.append(_issue("VOICE_MASTER_SYNC_UNVERIFIED", "Final TTS must remain the master timeline."))

    audio_plan = edit_recipe.get("audio_plan") or {}
    source = edit_recipe.get("source") or {}
    script_path = _as_text(source.get("script")).strip()
    srt_path = _as_text(source.get("srt")).strip()
    tts_report_path = _as_text(source.get("tts_generation_report")).strip()
    if not script_path.lower().endswith("_script.md"):
        issues.append(_issue("SCRIPT_ARTIFACT_INVALID", "One-shot production requires the standard *_script.md artifact."))
    if not srt_path.lower().endswith(".srt"):
        issues.append(_issue("SRT_ARTIFACT_INVALID", "One-shot production requires an SRT artifact."))
    if not tts_report_path:
        issues.append(_issue("TTS_PROVENANCE_MISSING", "One-shot production requires a hash-bound Gemini TTS generation report."))
    for field in ("final_voice_is_master", "tts_text_matches_narration"):
        if audio_plan.get(field) is not True:
            issues.append(_issue("TTS_MASTER_EVIDENCE_MISSING", f"audio_plan.{field} must be true."))
    for field in ("tts_text_sha256", "final_voice_sha256"):
        value = _as_text(audio_plan.get(field)).strip()
        if not value:
            issues.append(_issue("TTS_EVIDENCE_HASH_MISSING", f"audio_plan.{field} is required."))
        elif not SHA256_HEX.fullmatch(value):
            issues.append(_issue("TTS_EVIDENCE_HASH_INVALID", f"audio_plan.{field} must be 64 lowercase hexadecimal characters."))

    beats = edit_recipe.get("beats") or []
    beat_roles = [_role(beat) for beat in beats if isinstance(beat, dict)]
    missing_beat_roles = [role for role in REQUIRED_NARRATIVE_ROLES if role not in beat_roles]
    if missing_beat_roles:
        issues.append(_issue("EDIT_NARRATIVE_ROLE_MISSING", "Edit roles are missing: " + ", ".join(missing_beat_roles)))
    if "review_proof" not in beat_roles or "cta" not in beat_roles or (
        "review_proof" in beat_roles and "cta" in beat_roles and beat_roles.index("cta") <= beat_roles.index("review_proof")
    ):
        issues.append(_issue("CTA_AFTER_REVIEW_PROOF_MISSING", "A CTA must follow review proof."))
    if beats and isinstance(beats[0], dict) and _beat_duration(beats[0]) > MAX_OPENING_BEAT_SEC:
        issues.append(
            _issue(
                "OPENING_BEAT_TOO_LONG",
                f"The opening hook must turn within {MAX_OPENING_BEAT_SEC:.1f} seconds.",
                scene_id=_as_text(beats[0].get("id") or "scene_01"),
            )
        )

    scene_ids = {
        _as_text(scene.get("scene_id") or scene.get("id")).strip(): _role(scene)
        for scene in scenes
        if isinstance(scene, dict)
    }
    assets: dict[str, list[dict[str, Any]]] = {}
    for index, beat in enumerate(beats, start=1):
        if not isinstance(beat, dict):
            issues.append(_issue("INVALID_EDIT_BEAT", "edit_recipe.beats items must be objects."))
            continue
        scene_id = _as_text(beat.get("id") or f"scene_{index:02d}")
        planning_scene_id = _as_text(beat.get("planning_scene_id")).strip()
        if not planning_scene_id or planning_scene_id not in scene_ids or scene_ids.get(planning_scene_id) != _role(beat):
            issues.append(_issue("PLANNING_EDIT_ROLE_MISMATCH", "Each beat must point to the planning scene with the same role.", scene_id=scene_id))
        if _as_text(beat.get("visual_relevance")).strip() != "direct":
            issues.append(_issue("VISUAL_RELEVANCE_UNVERIFIED", "Each beat needs direct visual relevance.", scene_id=scene_id))

        caption = _as_text(beat.get("caption"))
        if _caption_has_literal_newline(caption):
            issues.append(_issue("CAPTION_LITERAL_NEWLINE", "Captions must not contain literal \\n or /n.", scene_id=scene_id))
        caption_lines = caption.split("\n")
        layout = beat.get("caption_layout")
        if not isinstance(layout, dict):
            issues.append(_issue("CAPTION_LAYOUT_EVIDENCE_MISSING", "Caption layout evidence is required.", scene_id=scene_id))
        else:
            theme = _as_text(layout.get("theme")).strip()
            if theme and theme not in SUPPORTED_CAPTION_THEMES:
                issues.append(_issue("CAPTION_THEME_UNSUPPORTED", f"Unsupported caption theme: {theme}", scene_id=scene_id))
            if layout.get("line_count") != len(caption_lines) or not 1 <= len(caption_lines) <= 2:
                issues.append(_issue("CAPTION_LINE_COUNT_INVALID", "Captions must have one or two lines.", scene_id=scene_id))
            try:
                font_size = float(layout.get("min_font_px"))
            except (TypeError, ValueError):
                font_size = 0.0
            if font_size < MIN_CAPTION_FONT_PX or layout.get("safe_area") != "pass" or layout.get("does_not_cover_subject") is not True:
                issues.append(_issue("CAPTION_READABILITY_UNVERIFIED", "Caption size, safe area, and subject clearance must be verified.", scene_id=scene_id))
        keywords = beat.get("caption_focus_keywords") or []
        if not isinstance(keywords, list) or not 1 <= len(keywords) <= 2:
            issues.append(_issue("CAPTION_KEYWORD_DENSITY_INVALID", "Each caption needs one or two focus keywords.", scene_id=scene_id))

        issues.extend(_validate_caption_chunks(beat, scene_id))
        issues.extend(_validate_beat_shots(beat, edit_recipe.get("asset_roles") or {}, scene_id))

        try:
            caption_start = float(beat.get("caption_start_sec"))
            narration_start = float(beat.get("narration_start_sec"))
        except (TypeError, ValueError):
            caption_start = narration_start = None
        if caption_start is None or narration_start is None:
            issues.append(_issue("CAPTION_VOICE_ALIGNMENT_MISSING", "Caption and narration timestamps are required.", scene_id=scene_id))
        elif caption_start < narration_start:
            issues.append(_issue("CAPTION_AHEAD_OF_VOICE", "Captions must not precede their narration.", scene_id=scene_id))

        time_range = beat.get("time")
        try:
            visual_start = float(time_range[0]) if isinstance(time_range, list) else None
        except (IndexError, TypeError, ValueError):
            visual_start = None
        if (
            visual_start is not None
            and narration_start is not None
            and visual_start < narration_start - MAX_VISUAL_LEAD_SEC
        ):
            issues.append(
                _issue(
                    "VISUAL_AHEAD_OF_VOICE",
                    f"Visuals must not start more than {MAX_VISUAL_LEAD_SEC:.2f} seconds before their narration.",
                    scene_id=scene_id,
                )
            )

        asset_id = _as_text(beat.get("asset_id") or beat.get("asset")).strip()
        if asset_id:
            assets.setdefault(asset_id, []).append(beat)
        if _role(beat) == "review_proof":
            if beat.get("generated_asset") or not _is_actual_review_capture(beat) or _as_text(beat.get("asset")).strip() != "review_capture":
                issues.append(_issue("REVIEW_PROOF_NOT_ACTUAL_CAPTURE", "Review proof must not use a generated card.", scene_id=scene_id))
            if _beat_duration(beat) > MAX_REVIEW_PROOF_DWELL_SEC:
                issues.append(
                    _issue(
                        "REVIEW_PROOF_DWELL_TOO_LONG",
                        f"Review proof must not hold one capture longer than {MAX_REVIEW_PROOF_DWELL_SEC:.1f} seconds.",
                        scene_id=scene_id,
                    )
                )

    result_asset_id = _as_text((edit_recipe.get("hook_visual_contract") or {}).get("result_asset_id")).strip()
    for asset_id, asset_beats in assets.items():
        total_duration = sum(_beat_duration(beat) for beat in asset_beats)
        is_declared_result = bool(result_asset_id) and all(
            _as_text(beat.get("asset")).strip() == result_asset_id for beat in asset_beats
        )
        if is_declared_result:
            continue
        if len(asset_beats) >= 3 and total_duration >= 8.0:
            issues.append(_issue("REPEATED_PHOTO_FILLER", f"Asset {asset_id} is repeated {len(asset_beats)} times for {total_duration:.1f}s."))

    return {
        "ok": not any(issue["severity"] == "fail" for issue in issues),
        "issues": issues,
    }


def validate_html_preflight(
    planning_recipe: dict[str, Any],
    edit_recipe: dict[str, Any],
    *,
    require_one_shot_contract: bool = False,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    analysis = _planning_analysis(planning_recipe)
    missing_analysis = _analysis_missing(analysis)
    if missing_analysis:
        issues.append(
            _issue(
                "PLANNING_ANALYSIS_EMPTY",
                "planning analysis 필수 필드가 비어 있습니다: " + ", ".join(missing_analysis),
            )
        )

    hooks = planning_recipe.get("hooks") or []
    if not hooks:
        issues.append(_issue("HOOKS_EMPTY", "훅 후보가 비어 있습니다."))

    hook = _hook_text(planning_recipe)
    if _is_weak_hook(hook):
        issues.append(_issue("WEAK_HOOK", f"최종 첫 화면 훅이 약하거나 추상적입니다: {hook}"))
    issues.extend(validate_hook_formula(hook)["issues"])

    beats = edit_recipe.get("beats") or []
    review_capture_count = _review_capture_count(beats)
    if review_capture_count > 1:
        issues.append(_issue("DUPLICATE_REVIEW_CAPTURE", f"review_capture가 {review_capture_count}회 사용되었습니다."))

    for index, beat in enumerate(beats, start=1):
        scene_id = _as_text(beat.get("id") or f"scene_{index:02d}")
        evidence = _as_text(beat.get("meaning_match_source") or beat.get("meaning_match_evidence")).strip()
        if beat.get("meaning_match") is not True:
            issues.append(_issue("MEANING_MATCH_UNVERIFIED", "asset/caption/narration 의미 일치 근거가 true가 아닙니다.", scene_id=scene_id))
        elif not evidence:
            issues.append(_issue("MEANING_MATCH_EVIDENCE_MISSING", "meaning_match는 true지만 meaning_match_source/evidence가 없습니다.", scene_id=scene_id))
        if _contains_corrupt_marker(_as_text(beat.get("caption"))) or _contains_corrupt_marker(_as_text(beat.get("narration_ref"))):
            issues.append(_issue("CORRUPT_TEXT_MARKER", "caption/narration에 깨진 문자 마커가 있습니다.", scene_id=scene_id))

    issues.extend(_validate_generated_asset_metadata(beats))
    is_one_shot = require_one_shot_contract or _as_text(
        (planning_recipe.get("workflow_contract") or {}).get("name")
    ).strip() == ONE_SHOT_CONTRACT_NAME
    issues.extend(
        _validate_audio_metadata(
            edit_recipe,
            require_raw_tts=True,
            minimum_cps=MIN_ONE_SHOT_CPS if is_one_shot else None,
            maximum_cps=SOFT_CPS_LIMIT if is_one_shot else None,
        )
    )
    issues.extend(_validate_privacy_metadata(edit_recipe))
    issues.extend(validate_review_source_integrity(planning_recipe)["issues"])
    if require_one_shot_contract or planning_recipe.get("workflow_contract"):
        issues.extend(validate_review_reels_one_shot_contract(planning_recipe, edit_recipe)["issues"])

    sync_result = validate_sync(edit_recipe)
    issues.extend(sync_result["issues"])

    return {
        "ok": not any(issue["severity"] == "fail" for issue in issues),
        "issues": issues,
        "sync": sync_result,
    }


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def build_status_markdown(
    *,
    review_id: str,
    variant_id: str,
    current_html: str = "",
    current_voice: str = "",
    current_recipe: str = "",
    photo_checked: bool = False,
    pd_plan_approved: bool = False,
    script_created: bool = False,
    tts_created: bool = False,
    html_created: bool = False,
    html_approved_by_user: bool = False,
    mp4_allowed: bool = False,
    blocked_reason: str = "",
) -> str:
    return "\n".join(
        [
            f"# {review_id} 상태",
            "",
            f"- review_id: {review_id}",
            f"- current_variant: {variant_id}",
            f"- photo_checked: {_bool_text(photo_checked)}",
            f"- pd_plan_approved: {_bool_text(pd_plan_approved)}",
            f"- script_created: {_bool_text(script_created)}",
            f"- tts_created: {_bool_text(tts_created)}",
            f"- html_created: {_bool_text(html_created)}",
            f"- html_approved_by_user: {_bool_text(html_approved_by_user)}",
            f"- mp4_allowed: {_bool_text(mp4_allowed)}",
            f"- current_html: {current_html}",
            f"- current_voice: {current_voice}",
            f"- current_recipe: {current_recipe}",
            f"- blocked_reason: {blocked_reason}",
            "",
        ]
    )


def build_approval_log_markdown(*, user_order: str, approved_scope: str, not_approved: str, timestamp: str | None = None) -> str:
    stamp = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return "\n".join(
        [
            f"## {stamp}",
            "",
            f"- user_order: {user_order}",
            f"- approved_scope: {approved_scope}",
            f"- not_approved: {not_approved}",
            "",
        ]
    )


def write_package_control_files(
    package_dir: str | Path,
    *,
    review_id: str,
    variant_id: str,
    current_html: str = "",
    current_voice: str = "",
    current_recipe: str = "",
    photo_checked: bool = False,
    pd_plan_approved: bool = False,
    script_created: bool = False,
    tts_created: bool = False,
    html_created: bool = False,
    html_approved_by_user: bool = False,
    mp4_allowed: bool = False,
    blocked_reason: str = "",
    overwrite_status: bool = False,
) -> dict[str, Path]:
    package_path = Path(package_dir)
    package_path.mkdir(parents=True, exist_ok=True)
    status_path = package_path / "STATUS.md"
    approval_path = package_path / "APPROVAL_LOG.md"

    if overwrite_status or not status_path.exists():
        status_path.write_text(
            build_status_markdown(
                review_id=review_id,
                variant_id=variant_id,
                current_html=current_html,
                current_voice=current_voice,
                current_recipe=current_recipe,
                photo_checked=photo_checked,
                pd_plan_approved=pd_plan_approved,
                script_created=script_created,
                tts_created=tts_created,
                html_created=html_created,
                html_approved_by_user=html_approved_by_user,
                mp4_allowed=mp4_allowed,
                blocked_reason=blocked_reason,
            ),
            encoding="utf-8",
        )

    if not approval_path.exists():
        approval_path.write_text(
            build_approval_log_markdown(
                user_order="initial control files created",
                approved_scope="없음",
                not_approved="script/SRT/TTS/HTML/MP4",
            ),
            encoding="utf-8",
        )

    return {"status": status_path, "approval_log": approval_path}


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _duration_from_recipe(edit_recipe: dict[str, Any]) -> tuple[float | None, float | None]:
    audio_plan = edit_recipe.get("audio_plan") or {}
    sync_policy = audio_plan.get("sync_policy") or {}
    raw_duration = _first_present(
        audio_plan,
        sync_policy,
        "raw_tts_duration_sec",
        "source_voice_duration_sec",
    )
    final_duration = _first_present(
        audio_plan,
        sync_policy,
        "final_voice_duration_sec",
        "voice_duration_sec",
    )

    def as_float(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    return as_float(raw_duration), as_float(final_duration)


def run_reels_qa(
    *,
    edit_path: str | Path,
    planning_path: str | Path | None = None,
    sync_manifest_out: str | Path | None = None,
    json_output: bool = False,
) -> int:
    edit_recipe = _load_json(edit_path)
    if planning_path:
        result = validate_html_preflight(_load_json(planning_path), edit_recipe)
    else:
        result = validate_sync(edit_recipe)
    manifest: dict[str, Any] | None = None

    if sync_manifest_out:
        raw_duration, final_duration = _duration_from_recipe(edit_recipe)
        manifest = build_sync_manifest(
            edit_recipe,
            raw_tts_duration_sec=raw_duration,
            final_voice_duration_sec=final_duration,
        )
        write_sync_manifest(sync_manifest_out, manifest)
        if not manifest["ok"]:
            result = {
                **result,
                "ok": False,
                "issues": [*result.get("issues", []), *manifest.get("issues", [])],
                "sync_manifest_ok": False,
            }

    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for issue in result["issues"]:
            print(f"[{issue['severity'].upper()}] {issue['code']}: {issue['message']}")
        print("OK" if result["ok"] else "FAIL")
    return 0 if result["ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="문장군 리뷰 릴스 HTML 생성 전 QA 도구")
    parser.add_argument("--planning", help="planning_recipe.json 경로")
    parser.add_argument("--edit", required=True, help="edit_recipe.json 경로")
    parser.add_argument("--sync-manifest-out", help="sync_manifest.json 저장 경로")
    parser.add_argument("--json", action="store_true", help="결과를 JSON으로 출력")
    args = parser.parse_args()

    return run_reels_qa(
        edit_path=args.edit,
        planning_path=args.planning,
        sync_manifest_out=args.sync_manifest_out,
        json_output=args.json,
    )


if __name__ == "__main__":
    raise SystemExit(main())
