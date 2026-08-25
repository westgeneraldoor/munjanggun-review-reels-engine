"""Official Gemini TTS/SRT gate for review-reels one-shot HTML production."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import generate


CANONICAL_METADATA = "CANONICAL_PACKAGE_METADATA.json"
ONE_SHOT_CONTRACT = "review-reels-one-shot-v2"
TTS_REPORT_SCHEMA = "review-reel-tts-generation-report-v1"
VOICE_TIMELINE_SCHEMA = "review-reel-voice-caption-timeline-v1"
VOICE_ALIGNMENT_SCHEMA = "review-reel-voice-alignment-v1"
TTS_ATTEMPT_SCHEMA = "review-reel-tts-api-attempt-v1"
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
MAX_TTS_API_ATTEMPTS_PER_NARRATION = 2
HOOK_BEFORE_CONTEXT_OVERHANG_TOLERANCE_SEC = 0.15
HOOK_MIN_SHOT_DURATION_SEC = 1.0


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


def _count_tts_api_attempts(package: Path, tts_text_sha256: str) -> int:
    work = package / "_work"
    if not work.is_dir():
        return 0
    attempts = 0
    receipt_report_paths: set[str] = set()
    attempt_dir = work / "tts_attempts"
    if attempt_dir.is_dir():
        for receipt_path in attempt_dir.glob("*.json"):
            receipt = _read_json(receipt_path, code="TTS_ATTEMPT_RECEIPT_INVALID")
            if (
                receipt.get("schema_version") == TTS_ATTEMPT_SCHEMA
                and receipt.get("tts_text_sha256") == tts_text_sha256
            ):
                attempts += 1
                report_relative = receipt.get("tts_report_relative_path")
                if isinstance(report_relative, str) and report_relative:
                    receipt_report_paths.add(report_relative)
    for report_path in work.glob("*_tts_generation_report.json"):
        try:
            report = _read_json(report_path, code="TTS_PROVENANCE_INVALID")
        except OneShotTTSViolation:
            continue
        if (
            report.get("schema_version") == TTS_REPORT_SCHEMA
            and report.get("provider") == "google_gemini_tts"
            and report.get("voice") == "Sulafat"
            and report.get("tts_text_sha256") == tts_text_sha256
            and not report.get("derived_voice")
            and report.get("timeline_source") != VOICE_ALIGNMENT_SCHEMA
            and report_path.relative_to(package).as_posix() not in receipt_report_paths
        ):
            attempts += 1
    return attempts


def _record_tts_api_attempt(package: Path, report_path: Path, tts_text_sha256: str) -> Path:
    """Persist a non-deletable budget receipt once Gemini produced a valid voice report."""

    report = _read_json(report_path, code="TTS_PROVENANCE_INVALID")
    attempt_dir = package / "_work" / "tts_attempts"
    attempt_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": TTS_ATTEMPT_SCHEMA,
        "tts_text_sha256": tts_text_sha256,
        "tts_report_relative_path": report_path.relative_to(package).as_posix(),
        "tts_report_sha256": _sha256(report_path),
        "voice_relative_path": report.get("voice_relative_path"),
        "voice_sha256": report.get("voice_sha256"),
        "provider": report.get("provider"),
        "model": report.get("model"),
        "voice": report.get("voice"),
    }
    for attempt_number in range(1, MAX_TTS_API_ATTEMPTS_PER_NARRATION + 2):
        receipt = attempt_dir / f"{tts_text_sha256[:16]}_{attempt_number:02d}.json"
        try:
            with receipt.open("x", encoding="utf-8") as output:
                json.dump(payload, output, ensure_ascii=False, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            return receipt
        except FileExistsError:
            continue
    raise OneShotTTSViolation("TTS_ATTEMPT_RECEIPT_COLLISION")


def _validate_post_retime(edit: dict[str, Any]) -> None:
    from video_engine_v2.reels_qa import validate_review_reels_one_shot_post_retime

    result = validate_review_reels_one_shot_post_retime(edit)
    if not result["ok"]:
        codes = ",".join(sorted({str(issue.get("code") or "") for issue in result["issues"]}))
        raise OneShotTTSViolation(f"POST_RETIME_AUTHORING_CHECK_FAILED:{codes}")


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


def _prepend_silence_mp3(source: Path, target: Path, lead_in_sec: float) -> None:
    """Create a new MP3 with a short decoder-safe lead-in without touching the source."""
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise OneShotTTSViolation("AUDIO_PADDING_DEPENDENCY_MISSING") from exc
    delay_ms = int(round(lead_in_sec * 1000))
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-y",
        "-i",
        str(source),
        "-af",
        f"adelay={delay_ms}:all=1",
        "-codec:a",
        "libmp3lame",
        "-q:a",
        "2",
        str(target),
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _load_alignment(
    package: Path,
    path: Path,
    source_voice: Path,
    edit: dict[str, Any],
) -> list[dict[str, Any]]:
    payload = _read_json(path, code="VOICE_ALIGNMENT_INVALID")
    if (
        payload.get("schema_version") != VOICE_ALIGNMENT_SCHEMA
        or payload.get("source_voice_relative_path") != source_voice.relative_to(package).as_posix()
        or payload.get("source_voice_sha256") != _sha256(source_voice)
    ):
        raise OneShotTTSViolation("VOICE_ALIGNMENT_STALE")
    expected = [
        (str(beat.get("id") or ""), index, str(chunk.get("text") or "").strip())
        for beat in edit.get("beats") or []
        if isinstance(beat, dict)
        for index, chunk in enumerate(beat.get("caption_chunks") or [], start=1)
        if isinstance(chunk, dict)
    ]
    items = payload.get("items")
    if not isinstance(items, list) or len(items) != len(expected) or not items:
        raise OneShotTTSViolation("VOICE_ALIGNMENT_INVALID")
    previous_end = -1.0
    for item, (beat_id, chunk_index, text) in zip(items, expected, strict=True):
        try:
            start = float(item["start_sec"])
            end = float(item["end_sec"])
        except (KeyError, TypeError, ValueError) as exc:
            raise OneShotTTSViolation("VOICE_ALIGNMENT_INVALID") from exc
        if (
            str(item.get("beat_id") or "") != beat_id
            or item.get("chunk_index") != chunk_index
            or str(item.get("text") or "").strip() != text
            or start < 0
            or end <= start
            or start < previous_end - 0.02
        ):
            raise OneShotTTSViolation("VOICE_ALIGNMENT_INVALID")
        previous_end = end
    return items


def _apply_measured_alignment(
    edit: dict[str, Any],
    items: list[dict[str, Any]],
    *,
    lead_in_sec: float,
    final_duration_sec: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    updated = deepcopy(edit)
    beats = updated.get("beats")
    if not isinstance(beats, list) or not beats:
        raise OneShotTTSViolation("EDIT_TIMELINE_INVALID")
    cursor = 0
    speech_ranges: list[list[tuple[float, float]]] = []
    flat_chunks: list[tuple[dict[str, Any], dict[str, Any], int]] = []
    for beat in beats:
        chunks = beat.get("caption_chunks") if isinstance(beat, dict) else None
        if not isinstance(chunks, list) or not chunks:
            raise OneShotTTSViolation("EDIT_TIMELINE_INVALID")
        beat_ranges: list[tuple[float, float]] = []
        for chunk_index, chunk in enumerate(chunks, start=1):
            item = items[cursor]
            cursor += 1
            speech_start = round(float(item["start_sec"]) + lead_in_sec, 3)
            speech_end = round(float(item["end_sec"]) + lead_in_sec, 3)
            beat_ranges.append((speech_start, speech_end))
            flat_chunks.append((beat, chunk, chunk_index))
        speech_ranges.append(beat_ranges)

    flat_speech = [speech for ranges in speech_ranges for speech in ranges]
    # Captions and scene beats must begin at measured speech onset.  Mid-gap
    # boundaries make the next caption appear before its words are audible.
    chunk_boundaries = [round(speech_start, 3) for speech_start, _ in flat_speech]
    chunk_boundaries.append(round(final_duration_sec, 3))
    timeline: list[dict[str, Any]] = []
    for index, (beat, chunk, chunk_index) in enumerate(flat_chunks):
        chunk["start_sec"] = chunk_boundaries[index]
        chunk["end_sec"] = chunk_boundaries[index + 1]
        timeline.append(
            {
                "beat_id": str(beat.get("id") or ""),
                "chunk_index": chunk_index,
                "start_sec": chunk["start_sec"],
                "end_sec": chunk["end_sec"],
                "text": str(chunk.get("text") or "").strip(),
                "display_text": str(chunk.get("display_text") or chunk.get("text") or "").strip(),
            }
        )

    chunk_cursor = 0
    for index, beat in enumerate(beats):
        old_start, old_end = (float(value) for value in beat["time"])
        chunk_count = len(beat["caption_chunks"])
        new_start = chunk_boundaries[chunk_cursor]
        new_end = chunk_boundaries[chunk_cursor + chunk_count]
        chunk_cursor += chunk_count
        old_span = max(old_end - old_start, 0.001)

        def mapped(value: Any) -> float:
            fraction = (float(value) - old_start) / old_span
            return round(new_start + fraction * (new_end - new_start), 3)

        beat["time"] = [new_start, new_end]
        beat["caption_start_sec"] = beat["caption_chunks"][0]["start_sec"]
        beat["narration_start_sec"] = new_start
        shots = beat.get("shots") or []
        for shot in shots:
            shot["start_sec"] = mapped(shot["start_sec"])
            shot["end_sec"] = mapped(shot["end_sec"])
        if shots:
            shots[0]["start_sec"] = new_start
            shots[-1]["end_sec"] = new_end
        if index == 0 and len(shots) == 3 and len(beat["caption_chunks"]) >= 2:
            second_chunk_start = float(beat["caption_chunks"][1]["start_sec"])
            before_end = min(
                second_chunk_start + HOOK_BEFORE_CONTEXT_OVERHANG_TOLERANCE_SEC,
                new_end - HOOK_MIN_SHOT_DURATION_SEC,
            )
            earliest_feasible_before_end = new_start + (2 * HOOK_MIN_SHOT_DURATION_SEC)
            if before_end < earliest_feasible_before_end - 0.001:
                raise OneShotTTSViolation("HOOK_ALIGNMENT_INFEASIBLE")
            before_start = before_end - HOOK_MIN_SHOT_DURATION_SEC
            shots[0]["end_sec"] = round(before_start, 3)
            shots[1]["start_sec"] = round(before_start, 3)
            shots[1]["end_sec"] = round(before_end, 3)
            shots[2]["start_sec"] = round(before_end, 3)
        accent = beat.get("caption_accent")
        if isinstance(accent, dict) and "start_sec" in accent:
            emphasis_words = beat.get("caption_emphasis") or []
            keyword = re.sub(r"\s+", "", str(emphasis_words[0])).casefold() if emphasis_words else ""
            matched = False
            for chunk in beat["caption_chunks"]:
                display = re.sub(
                    r"\s+",
                    "",
                    str(chunk.get("display_text") or chunk.get("text") or ""),
                ).casefold()
                keyword_index = display.find(keyword)
                if keyword and keyword_index >= 0:
                    start = float(chunk["start_sec"])
                    end = float(chunk["end_sec"])
                    accent["start_sec"] = round(
                        start + (end - start) * (keyword_index / max(len(display), 1)),
                        3,
                    )
                    matched = True
                    break
            if not matched:
                accent["start_sec"] = mapped(accent["start_sec"])
        emphasis = beat.get("review_emphasis")
        if isinstance(emphasis, dict):
            emphasis["start_sec"] = new_start
            emphasis["end_sec"] = beat["caption_chunks"][-1]["end_sec"]
    return updated, timeline


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


def _validate_planning(
    metadata: dict[str, Any],
    planning: dict[str, Any],
    script_text: str,
    *,
    script_sha256: str | None = None,
) -> None:
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
    script_review = planning.get("script_review") or {}
    expected_script_hash = script_sha256 or hashlib.sha256(script_text.encode("utf-8")).hexdigest()
    if (
        script_review.get("status") != "approved"
        or str(script_review.get("script_sha256") or "") != expected_script_hash
    ):
        raise OneShotTTSViolation("SCRIPT_REVIEW_HASH_MISMATCH")


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


def calibrate_one_shot_timeline(
    *,
    package_dir: str | Path,
    planning_path: str | Path,
    edit_path: str | Path,
    script_path: str | Path,
    source_voice_path: str | Path,
    source_report_path: str | Path,
    alignment_path: str | Path,
    lead_in_sec: float = 0.4,
) -> dict[str, Path]:
    """Derive a decoder-safe voice and measured SRT from an approved Gemini voice."""
    package = Path(package_dir).resolve()
    if not package.is_dir():
        raise OneShotTTSViolation("PACKAGE_MISSING")
    planning_file = _inside(package, planning_path, code="PLANNING_OUTSIDE_PACKAGE")
    edit_file = _inside(package, edit_path, code="EDIT_OUTSIDE_PACKAGE")
    script_file = _inside(package, script_path, code="SCRIPT_OUTSIDE_PACKAGE")
    source_voice = _inside(package, source_voice_path, code="VOICE_OUTSIDE_PACKAGE")
    source_report = _inside(package, source_report_path, code="TTS_REPORT_OUTSIDE_PACKAGE")
    alignment_file = _inside(package, alignment_path, code="VOICE_ALIGNMENT_OUTSIDE_PACKAGE")
    if not 0.1 <= float(lead_in_sec) <= 1.0:
        raise OneShotTTSViolation("VOICE_LEAD_IN_INVALID")

    metadata = _validate_package_state(package)
    planning = _read_json(planning_file, code="PLANNING_RECIPE_INVALID")
    edit = _read_json(edit_file, code="EDIT_RECIPE_INVALID")
    try:
        script_text = script_file.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise OneShotTTSViolation("SCRIPT_ARTIFACT_INVALID") from exc
    _validate_planning(metadata, planning, script_text, script_sha256=_sha256(script_file))
    _validate_tts_report(package, source_report, source_voice, script_text)
    items = _load_alignment(package, alignment_file, source_voice, edit)

    artifact_stem = generate.get_artifact_stem_from_script_path(script_file)
    target_voice = package / f"{artifact_stem}_voice.mp3"
    target_srt = package / f"{artifact_stem}.srt"
    target_report = package / "_work" / f"{artifact_stem}_tts_generation_report.json"
    if any(path.exists() for path in (target_voice, target_srt, target_report)):
        raise OneShotTTSViolation("TTS_ARTIFACT_ALREADY_EXISTS")

    original_edit_bytes = edit_file.read_bytes()
    try:
        _prepend_silence_mp3(source_voice, target_voice, float(lead_in_sec))
        final_duration = round(generate.get_audio_duration_seconds(target_voice), 3)
        updated_edit, timeline = _apply_measured_alignment(
            edit,
            items,
            lead_in_sec=float(lead_in_sec),
            final_duration_sec=final_duration,
        )
        _validate_post_retime(updated_edit)
        source = updated_edit.setdefault("source", {})
        source.update(
            {
                "script": script_file.relative_to(package).as_posix(),
                "srt": target_srt.relative_to(package).as_posix(),
                "voice": target_voice.relative_to(package).as_posix(),
                "tts_generation_report": target_report.relative_to(package).as_posix(),
            }
        )
        source_payload = _read_json(source_report, code="TTS_PROVENANCE_INVALID")
        tts_hash = hashlib.sha256(generate.prepare_tts_text(script_text).encode("utf-8")).hexdigest()
        voice_hash = _sha256(target_voice)
        audio_plan = updated_edit.setdefault("audio_plan", {})
        audio_plan.update(
            {
                "tts_text_sha256": tts_hash,
                "final_voice_sha256": voice_hash,
                "final_voice_is_master": True,
                "tts_text_matches_narration": True,
            }
        )
        audio_plan.setdefault("sync_policy", {}).update(
            {
                "raw_tts_duration_sec": source_payload["raw_tts_duration_sec"],
                "final_voice_duration_sec": final_duration,
                "render_duration_sec": final_duration,
                "timeline_source": VOICE_ALIGNMENT_SCHEMA,
            }
        )
        _atomic_write_json(edit_file, updated_edit)
        target_srt.write_text(_srt_from_timeline(timeline), encoding="utf-8")
        report_payload = {
            "schema_version": TTS_REPORT_SCHEMA,
            "provider": "google_gemini_tts",
            "model": source_payload["model"],
            "voice": "Sulafat",
            "tts_text_sha256": tts_hash,
            "voice_relative_path": target_voice.relative_to(package).as_posix(),
            "voice_bytes": target_voice.stat().st_size,
            "voice_sha256": voice_hash,
            "raw_tts_duration_sec": source_payload["raw_tts_duration_sec"],
            "final_voice_duration_sec": final_duration,
            "caption_timeline_schema": VOICE_TIMELINE_SCHEMA,
            "caption_timeline": timeline,
            "timeline_source": VOICE_ALIGNMENT_SCHEMA,
            "alignment_relative_path": alignment_file.relative_to(package).as_posix(),
            "alignment_sha256": _sha256(alignment_file),
            "derived_voice": {
                "source_relative_path": source_voice.relative_to(package).as_posix(),
                "source_sha256": _sha256(source_voice),
                "lead_in_sec": round(float(lead_in_sec), 3),
            },
            "edit_recipe_relative_path": edit_file.relative_to(package).as_posix(),
            "edit_recipe_sha256": _sha256(edit_file),
        }
        _atomic_write_json(target_report, report_payload)
    except Exception:
        edit_file.write_bytes(original_edit_bytes)
        target_voice.unlink(missing_ok=True)
        target_srt.unlink(missing_ok=True)
        target_report.unlink(missing_ok=True)
        raise

    from video_engine_v2.current_artifacts import CurrentArtifactsViolation, record_current_artifacts

    try:
        record_current_artifacts(
            package,
            producer="one_shot_tts.calibrate_one_shot_timeline",
            artifacts={
                "script": script_file,
                "captions": target_srt,
                "voice": target_voice,
                "tts_report": target_report,
            },
        )
    except CurrentArtifactsViolation as error:
        raise OneShotTTSViolation(str(error)) from error
    from video_engine_v2.recipe_revision import RecipeRevisionViolation, lock_bound_recipe

    try:
        lock_bound_recipe(package, edit_file, target_report)
    except RecipeRevisionViolation as error:
        raise OneShotTTSViolation(str(error)) from error
    return {
        "script": script_file,
        "edit": edit_file,
        "srt": target_srt,
        "voice": target_voice,
        "tts_report": target_report,
    }


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
    _validate_planning(metadata, planning, script_text, script_sha256=_sha256(script_file))

    artifact_stem = generate.get_artifact_stem_from_script_path(script_file)
    srt_path = package / f"{artifact_stem}.srt"
    voice_path = package / f"{artifact_stem}_voice.mp3"
    report_path = package / "_work" / f"{artifact_stem}_tts_generation_report.json"
    collision_paths = [srt_path, voice_path, report_path]
    if any(path.exists() for path in collision_paths):
        raise OneShotTTSViolation("TTS_ARTIFACT_ALREADY_EXISTS")

    tts_hash = hashlib.sha256(generate.prepare_tts_text(script_text).encode("utf-8")).hexdigest()
    if _count_tts_api_attempts(package, tts_hash) >= MAX_TTS_API_ATTEMPTS_PER_NARRATION:
        raise OneShotTTSViolation("TTS_ATTEMPT_BUDGET_EXCEEDED")

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
    _record_tts_api_attempt(package, report_path, tts_hash)

    try:
        report = _read_json(report_path, code="TTS_PROVENANCE_INVALID")
        updated_edit, timeline = _retime_edit_to_voice(edit, float(report["final_voice_duration_sec"]))
        _validate_post_retime(updated_edit)
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
    from video_engine_v2.recipe_revision import RecipeRevisionViolation, lock_bound_recipe

    try:
        lock_bound_recipe(package, edit_file, report_path)
    except RecipeRevisionViolation as error:
        raise OneShotTTSViolation(str(error)) from error
    return {
        "script": script_file,
        "edit": edit_file,
        "srt": srt_path,
        "voice": voice_path,
        "tts_report": report_path,
    }
