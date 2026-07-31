"""Official Gemini TTS/SRT gate for review-reels one-shot HTML production."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import generate


CANONICAL_METADATA = "CANONICAL_PACKAGE_METADATA.json"
ONE_SHOT_CONTRACT = "review-reels-one-shot-v2"
TTS_REPORT_SCHEMA = "review-reel-tts-generation-report-v1"
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


class OneShotTTSViolation(RuntimeError):
    """Raised before an unapproved or unbound one-shot audio artifact is created."""


def _inside(package: Path, value: str | Path, *, code: str) -> Path:
    candidate = Path(value).resolve()
    try:
        candidate.relative_to(package)
    except ValueError as exc:
        raise OneShotTTSViolation(code) from exc
    return candidate


def _read_json(path: Path, *, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OneShotTTSViolation(code) from exc
    if not isinstance(value, dict):
        raise OneShotTTSViolation(code)
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_package_state(package: Path) -> dict[str, Any]:
    metadata = _read_json(package / CANONICAL_METADATA, code="CANONICAL_PACKAGE_METADATA_INVALID")
    approvals = metadata.get("approvals") or {}
    if (
        metadata.get("schema_version") != "review-reel-canonical-package-v1"
        or metadata.get("workflow") != "review_reel_production"
    ):
        raise OneShotTTSViolation("CANONICAL_PACKAGE_METADATA_INVALID")
    if metadata.get("lifecycle_state") != "photo_reviewed" or approvals.get("photo_checked") is not True:
        raise OneShotTTSViolation("PHOTO_REVIEW_MISSING")
    if approvals.get("html_scope_authorized") is not False:
        raise OneShotTTSViolation("HTML_SCOPE_MUST_START_UNAUTHORIZED")
    if approvals.get("mp4_scope_authorized") is not False:
        raise OneShotTTSViolation("MP4_SCOPE_MUST_REMAIN_UNAUTHORIZED")
    return metadata


def _validate_planning(metadata: dict[str, Any], planning: dict[str, Any], script_text: str) -> None:
    contract = planning.get("workflow_contract") or {}
    if contract.get("name") != ONE_SHOT_CONTRACT:
        raise OneShotTTSViolation("ONE_SHOT_CONTRACT_MISSING")
    if contract.get("html_scope_authorized") is not True:
        raise OneShotTTSViolation("HTML_SCOPE_NOT_AUTHORIZED")
    if contract.get("mp4_scope_authorized") is not False:
        raise OneShotTTSViolation("MP4_SCOPE_MUST_REMAIN_UNAUTHORIZED")
    if str(planning.get("content_id") or "") != str(metadata.get("content_id") or ""):
        raise OneShotTTSViolation("CONTENT_ID_MISMATCH")

    canonical_hash = str((metadata.get("identity") or {}).get("review_text_sha256") or "")
    planning_hash = str((planning.get("review_source") or {}).get("canonical_text_sha256") or "")
    if not SHA256_HEX.fullmatch(canonical_hash) or planning_hash != canonical_hash:
        raise OneShotTTSViolation("REVIEW_SOURCE_HASH_MISMATCH")

    scenes = planning.get("scenes") or []
    if not isinstance(scenes, list) or not scenes:
        raise OneShotTTSViolation("PLANNING_SCENES_MISSING")
    planning_narration = generate.normalize_tts_text(
        " ".join(str(scene.get("narration") or "") for scene in scenes if isinstance(scene, dict))
    )
    if planning_narration != generate.prepare_tts_text(script_text):
        raise OneShotTTSViolation("SCRIPT_PLANNING_NARRATION_MISMATCH")


def _validate_tts_report(
    package: Path,
    report_path: Path,
    voice_path: Path,
    script_text: str,
) -> None:
    report = _read_json(report_path, code="TTS_PROVENANCE_INVALID")
    expected_text_hash = hashlib.sha256(generate.prepare_tts_text(script_text).encode("utf-8")).hexdigest()
    expected_voice_path = voice_path.relative_to(package).as_posix()
    if (
        report.get("schema_version") != TTS_REPORT_SCHEMA
        or report.get("provider") != "google_gemini_tts"
        or "tts" not in str(report.get("model") or "").lower()
        or report.get("voice") != "Sulafat"
        or report.get("tts_text_sha256") != expected_text_hash
        or report.get("voice_relative_path") != expected_voice_path
        or report.get("voice_bytes") != voice_path.stat().st_size
        or report.get("voice_sha256") != _sha256(voice_path)
    ):
        raise OneShotTTSViolation("TTS_PROVENANCE_INVALID")
    for field in ("raw_tts_duration_sec", "final_voice_duration_sec"):
        if not isinstance(report.get(field), (int, float)) or report[field] <= 0:
            raise OneShotTTSViolation("TTS_PROVENANCE_INVALID")


def generate_one_shot_tts(
    *,
    package_dir: str | Path,
    planning_path: str | Path,
    script_path: str | Path,
) -> dict[str, Path]:
    """Generate only standard SRT and Gemini/Sulafat voice artifacts for one-shot HTML."""

    package = Path(package_dir).resolve()
    if not package.is_dir():
        raise OneShotTTSViolation("PACKAGE_MISSING")
    planning_file = _inside(package, planning_path, code="PLANNING_OUTSIDE_PACKAGE")
    script_file = _inside(package, script_path, code="SCRIPT_OUTSIDE_PACKAGE")
    if not script_file.name.endswith("_script.md"):
        raise OneShotTTSViolation("SCRIPT_ARTIFACT_INVALID")

    metadata = _validate_package_state(package)
    planning = _read_json(planning_file, code="PLANNING_RECIPE_INVALID")
    try:
        script_text = script_file.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise OneShotTTSViolation("SCRIPT_ARTIFACT_INVALID") from exc
    failures = [issue for issue in generate.validate_script(script_text) if issue.startswith("[FAIL]")]
    if failures:
        raise OneShotTTSViolation("SCRIPT_STANDARD_INVALID: " + " | ".join(failures))
    _validate_planning(metadata, planning, script_text)

    artifact_stem = generate.get_artifact_stem_from_script_path(script_file)
    srt_path = package / f"{artifact_stem}.srt"
    voice_path = package / f"{artifact_stem}_voice.mp3"
    report_path = package / "_work" / f"{artifact_stem}_tts_generation_report.json"
    collision_paths = [srt_path, voice_path, report_path]
    if any(path.exists() for path in collision_paths):
        raise OneShotTTSViolation("TTS_ARTIFACT_ALREADY_EXISTS")

    generated_voice = generate.generate_voice(
        script_text,
        package,
        artifact_stem=artifact_stem,
    ).resolve()
    if generated_voice != voice_path.resolve() or not voice_path.is_file():
        raise OneShotTTSViolation("TTS_OUTPUT_INVALID")
    if not report_path.is_file():
        raise OneShotTTSViolation("TTS_PROVENANCE_MISSING")
    _validate_tts_report(package, report_path, voice_path, script_text)

    try:
        srt_path.write_text(generate.generate_srt(script_text), encoding="utf-8")
    except Exception:
        voice_path.unlink(missing_ok=True)
        report_path.unlink(missing_ok=True)
        raise

    return {
        "script": script_file,
        "srt": srt_path,
        "voice": voice_path,
        "tts_report": report_path,
    }
