from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


HARD_CPS_LIMIT = 9.0
SOFT_CPS_LIMIT = 8.5
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


def _review_capture_count(beats: list[dict[str, Any]]) -> int:
    count = 0
    for beat in beats:
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


def _validate_audio_metadata(edit_recipe: dict[str, Any], *, require_raw_tts: bool = False) -> list[dict[str, Any]]:
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
    if total_voice_cps >= HARD_CPS_LIMIT:
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


def validate_html_preflight(planning_recipe: dict[str, Any], edit_recipe: dict[str, Any]) -> dict[str, Any]:
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
    issues.extend(_validate_audio_metadata(edit_recipe, require_raw_tts=True))
    issues.extend(_validate_privacy_metadata(edit_recipe))
    issues.extend(validate_review_source_integrity(planning_recipe)["issues"])

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
