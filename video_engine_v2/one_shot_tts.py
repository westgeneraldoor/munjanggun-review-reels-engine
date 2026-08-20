"""Official Gemini TTS/SRT gate for review-reels one-shot HTML production."""

from __future__ import annotations

import hashlib
import json
import os
import re
from copy import deepcopy
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import generate


CANONICAL_METADATA = "CANONICAL_PACKAGE_METADATA.json"
ONE_SHOT_CONTRACT = "review-reels-one-shot-v2"
TTS_REPORT_SCHEMA = "review-reel-tts-generation-report-v1"
VOICE_TIMELINE_SCHEMA = "review-reel-voice-caption-timeline-v1"
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


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _retime_edit_to_voice(edit: dict[str, Any], final_duration_sec: float) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Scale every visual/caption boundary onto the measured final voice clock."""
    beats = edit.get("beats")
    if not isinstance(beats, list) or not beats:
        raise OneShotTTSViolation("EDIT_TIMELINE_INVALID")
    try:
        source_start = float(beats[0]["time"][0])
        source_end = float(beats[-1]["time"][1])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise OneShotTTSViolation("EDIT_TIMELINE_INVALID") from exc
    if abs(source_start) > 0.001 or source_end <= source_start or final_duration_sec <= 0:
        raise OneShotTTSViolation("EDIT_TIMELINE_INVALID")
    scale = final_duration_sec / (source_end - source_start)

    def mapped(value: Any) -> float:
        try:
            result = (float(value) - source_start) * scale
        except (TypeError, ValueError) as exc:
            raise OneShotTTSViolation("EDIT_TIMELINE_INVALID") from exc
        return round(max(0.0, result), 3)

    updated = deepcopy(edit)
    timeline: list[dict[str, Any]] = []
    for beat_index, beat in enumerate(updated["beats"]):
        if not isinstance(beat, dict):
            raise OneShotTTSViolation("EDIT_TIMELINE_INVALID")
        try:
            beat["time"] = [mapped(beat["time"][0]), mapped(beat["time"][1])]
        except (KeyError, IndexError, TypeError) as exc:
            raise OneShotTTSViolation("EDIT_TIMELINE_INVALID") from exc
        for field in ("caption_start_sec", "narration_start_sec"):
            if field in beat:
                beat[field] = mapped(beat[field])
        for field in ("caption_chunks", "shots"):
            values = beat.get(field)
            if not isinstance(values, list) or not values:
                raise OneShotTTSViolation("EDIT_TIMELINE_INVALID")
            for item in values:
                if not isinstance(item, dict) or "start_sec" not in item or "end_sec" not in item:
                    raise OneShotTTSViolation("EDIT_TIMELINE_INVALID")
                item["start_sec"] = mapped(item["start_sec"])
                item["end_sec"] = mapped(item["end_sec"])
        accent = beat.get("caption_accent")
        if isinstance(accent, dict) and "start_sec" in accent:
            accent["start_sec"] = mapped(accent["start_sec"])
        emphasis = beat.get("review_emphasis")
        if isinstance(emphasis, dict):
            for field in ("start_sec", "end_sec"):
                if field in emphasis:
                    emphasis[field] = mapped(emphasis[field])
        for chunk_index, chunk in enumerate(beat["caption_chunks"], start=1):
            timeline.append(
                {
                    "beat_id": str(beat.get("id") or f"beat_{beat_index + 1}"),
                    "chunk_index": chunk_index,
                    "start_sec": chunk["start_sec"],
                    "end_sec": chunk["end_sec"],
                    "text": str(chunk.get("text") or "").strip(),
                    "display_text": str(chunk.get("display_text") or chunk.get("text") or "").strip(),
                }
            )
    updated["beats"][-1]["time"][1] = round(final_duration_sec, 3)
    updated["beats"][-1]["caption_chunks"][-1]["end_sec"] = round(final_duration_sec, 3)
    updated["beats"][-1]["shots"][-1]["end_sec"] = round(final_duration_sec, 3)
    timeline[-1]["end_sec"] = round(final_duration_sec, 3)
    return updated, timeline


def _format_srt_time(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _srt_from_timeline(timeline: list[dict[str, Any]]) -> str:
    entries = []
    for index, item in enumerate(timeline, start=1):
        entries.append(
            "\n".join(
                [
                    str(index),
                    f"{_format_srt_time(item['start_sec'])} --> {_format_srt_time(item['end_sec'])}",
                    item["display_text"],
                ]
            )
        )
    return "\n\n".join(entries) + "\n"


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
    edit_path: str | Path,
    script_path: str | Path,
) -> dict[str, Path]:
    """Generate only standard SRT and Gemini/Sulafat voice artifacts for one-shot HTML."""

    package = Path(package_dir).resolve()
    if not package.is_dir():
        raise OneShotTTSViolation("PACKAGE_MISSING")
    planning_file = _inside(package, planning_path, code="PLANNING_OUTSIDE_PACKAGE")
    edit_file = _inside(package, edit_path, code="EDIT_OUTSIDE_PACKAGE")
    script_file = _inside(package, script_path, code="SCRIPT_OUTSIDE_PACKAGE")
    if not script_file.name.endswith("_script.md"):
        raise OneShotTTSViolation("SCRIPT_ARTIFACT_INVALID")

    metadata = _validate_package_state(package)
    planning = _read_json(planning_file, code="PLANNING_RECIPE_INVALID")
    edit = _read_json(edit_file, code="EDIT_RECIPE_INVALID")
    original_edit_bytes = edit_file.read_bytes()
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
        report = _read_json(report_path, code="TTS_PROVENANCE_INVALID")
        updated_edit, timeline = _retime_edit_to_voice(edit, float(report["final_voice_duration_sec"]))
        source = updated_edit.setdefault("source", {})
        source.update(
            {
                "script": script_file.relative_to(package).as_posix(),
                "srt": srt_path.relative_to(package).as_posix(),
                "voice": voice_path.relative_to(package).as_posix(),
                "tts_generation_report": report_path.relative_to(package).as_posix(),
            }
        )
        audio_plan = updated_edit.setdefault("audio_plan", {})
        audio_plan["tts_text_sha256"] = hashlib.sha256(generate.prepare_tts_text(script_text).encode("utf-8")).hexdigest()
        audio_plan["final_voice_sha256"] = _sha256(voice_path)
        audio_plan["final_voice_is_master"] = True
        audio_plan["tts_text_matches_narration"] = True
        sync_policy = audio_plan.setdefault("sync_policy", {})
        sync_policy.update(
            {
                "raw_tts_duration_sec": report["raw_tts_duration_sec"],
                "final_voice_duration_sec": report["final_voice_duration_sec"],
                "render_duration_sec": report["final_voice_duration_sec"],
                "timeline_source": VOICE_TIMELINE_SCHEMA,
            }
        )
        _atomic_write_json(edit_file, updated_edit)
        report.update(
            {
                "caption_timeline_schema": VOICE_TIMELINE_SCHEMA,
                "caption_timeline": timeline,
                "edit_recipe_relative_path": edit_file.relative_to(package).as_posix(),
                "edit_recipe_sha256": _sha256(edit_file),
            }
        )
        _atomic_write_json(report_path, report)
        srt_path.write_text(_srt_from_timeline(timeline), encoding="utf-8")
    except Exception:
        edit_file.write_bytes(original_edit_bytes)
        srt_path.unlink(missing_ok=True)
        voice_path.unlink(missing_ok=True)
        report_path.unlink(missing_ok=True)
        raise

    from video_engine_v2.current_artifacts import CurrentArtifactsViolation, record_current_artifacts

    try:
        record_current_artifacts(
            package,
            producer="one_shot_tts.generate_one_shot_tts",
            artifacts={
                "script": script_file,
                "captions": srt_path,
                "voice": voice_path,
                "tts_report": report_path,
            },
        )
    except CurrentArtifactsViolation as error:
        raise OneShotTTSViolation(str(error)) from error
    return {
        "script": script_file,
        "edit": edit_file,
        "srt": srt_path,
        "voice": voice_path,
        "tts_report": report_path,
    }
