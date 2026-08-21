"""Immutable edit-recipe evidence and safe visual-only revision helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


LOCK_SCHEMA = "review-reel-bound-recipe-lock-v1"
FORK_SCHEMA = "review-reel-voice-reuse-fork-v1"
_EDIT_VERSION = re.compile(r"^(?P<prefix>.+)_v(?P<version>\d+)_edit_recipe\.json$")
_PLANNING_VERSION = re.compile(r"^(?P<prefix>.+)_v(?P<version>\d+)_planning_recipe\.json$")


class RecipeRevisionViolation(RuntimeError):
    """Raised when immutable recipe evidence cannot be trusted or reused."""


def _inside(package: Path, value: str | Path, *, code: str) -> Path:
    package = package.resolve()
    candidate = Path(value).resolve()
    try:
        candidate.relative_to(package)
    except ValueError as error:
        raise RecipeRevisionViolation(code) from error
    return candidate


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path, *, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RecipeRevisionViolation(code) from error
    if not isinstance(value, dict):
        raise RecipeRevisionViolation(code)
    return value


def _atomic_create_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as output:
            json.dump(payload, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
            temporary = Path(output.name)
        if path.exists():
            raise RecipeRevisionViolation("BOUND_RECIPE_LOCK_EXISTS")
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _lock_path(package: Path, edit: Path) -> Path:
    return package / "_work" / "recipe_locks" / f"{edit.name}.lock.json"


def lock_bound_recipe(
    package_dir: str | Path,
    edit_path: str | Path,
    report_path: str | Path,
) -> Path:
    """Bind a TTS report to its original edit and make that edit read-only."""

    package = Path(package_dir).resolve()
    edit = _inside(package, edit_path, code="EDIT_OUTSIDE_PACKAGE")
    report = _inside(package, report_path, code="TTS_REPORT_OUTSIDE_PACKAGE")
    if not edit.is_file() or not report.is_file():
        raise RecipeRevisionViolation("BOUND_RECIPE_EVIDENCE_MISSING")
    report_payload = _read_json(report, code="TTS_PROVENANCE_INVALID")
    edit_relative = edit.relative_to(package).as_posix()
    edit_hash = _sha256(edit)
    if (
        report_payload.get("edit_recipe_relative_path") != edit_relative
        or report_payload.get("edit_recipe_sha256") != edit_hash
    ):
        raise RecipeRevisionViolation("BOUND_RECIPE_MODIFIED")
    payload = {
        "schema_version": LOCK_SCHEMA,
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "edit_recipe_relative_path": edit_relative,
        "edit_recipe_bytes": edit.stat().st_size,
        "edit_recipe_sha256": edit_hash,
        "tts_report_relative_path": report.relative_to(package).as_posix(),
        "tts_report_bytes": report.stat().st_size,
        "tts_report_sha256": _sha256(report),
    }
    lock = _lock_path(package, edit)
    _atomic_create_json(lock, payload)
    try:
        edit.chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
    except OSError:
        lock.unlink(missing_ok=True)
        raise
    return lock


def verify_bound_recipe_lock(
    package_dir: str | Path,
    edit_path: str | Path,
    report_path: str | Path,
) -> dict[str, Any]:
    """Verify the immutable edit/report pair without changing any artifact."""

    package = Path(package_dir).resolve()
    edit = _inside(package, edit_path, code="EDIT_OUTSIDE_PACKAGE")
    report = _inside(package, report_path, code="TTS_REPORT_OUTSIDE_PACKAGE")
    lock = _lock_path(package, edit)
    payload = _read_json(lock, code="BOUND_RECIPE_LOCK_MISSING")
    expected = {
        "schema_version": LOCK_SCHEMA,
        "edit_recipe_relative_path": edit.relative_to(package).as_posix(),
        "edit_recipe_bytes": edit.stat().st_size if edit.is_file() else None,
        "edit_recipe_sha256": _sha256(edit) if edit.is_file() else None,
        "tts_report_relative_path": report.relative_to(package).as_posix(),
        "tts_report_bytes": report.stat().st_size if report.is_file() else None,
        "tts_report_sha256": _sha256(report) if report.is_file() else None,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise RecipeRevisionViolation("BOUND_RECIPE_MODIFIED")
    return payload


def _source_path(package: Path, source: dict[str, Any], field: str, *, code: str) -> Path:
    value = source.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RecipeRevisionViolation(code)
    return _inside(package, package / value, code=code)


def _require_current_voice_evidence(package: Path, edit: dict[str, Any]) -> None:
    from video_engine_v2.current_artifacts import package_uses_ledger, pointer_file

    if not package_uses_ledger(package):
        return
    source = edit.get("source") or {}
    if not isinstance(source, dict):
        raise RecipeRevisionViolation("TTS_PROVENANCE_MISSING")
    expected = {
        "script": _source_path(package, source, "script", code="SCRIPT_ARTIFACT_INVALID"),
        "captions": _source_path(package, source, "srt", code="SRT_ARTIFACT_INVALID"),
        "voice": _source_path(package, source, "voice", code="VOICE_OUTSIDE_PACKAGE"),
        "tts_report": _source_path(package, source, "tts_generation_report", code="TTS_PROVENANCE_MISSING"),
    }
    try:
        for kind, path in expected.items():
            if pointer_file(package, kind) != path:
                raise RecipeRevisionViolation("CURRENT_ARTIFACTS_PATH_NOT_CURRENT")
    except RecipeRevisionViolation:
        raise
    except Exception as error:
        raise RecipeRevisionViolation(str(error)) from error


def check_voice_reuse_candidate(
    package_dir: str | Path,
    edit_path: str | Path,
) -> dict[str, Any]:
    """Read-only proof that a candidate edit can retain current voice evidence."""

    from video_engine_v2.production_gate import (
        GateViolation,
        _validate_one_shot_audio_hashes,
        _validate_one_shot_tts_provenance,
    )

    package = Path(package_dir).resolve()
    edit_file = _inside(package, edit_path, code="EDIT_OUTSIDE_PACKAGE")
    edit = _read_json(edit_file, code="EDIT_INVALID")
    direct_lock_path = _lock_path(package, edit_file)
    if direct_lock_path.is_file():
        direct_lock = _read_json(direct_lock_path, code="BOUND_RECIPE_LOCK_MISSING")
        direct_report_relative = direct_lock.get("tts_report_relative_path")
        if not isinstance(direct_report_relative, str) or not direct_report_relative.strip():
            raise RecipeRevisionViolation("BOUND_RECIPE_MODIFIED")
        direct_report = _inside(
            package,
            package / direct_report_relative,
            code="TTS_REPORT_OUTSIDE_PACKAGE",
        )
        verify_bound_recipe_lock(package, edit_file, direct_report)
    try:
        _validate_one_shot_audio_hashes(package, edit)
        _validate_one_shot_tts_provenance(package, edit)
    except GateViolation as error:
        raise RecipeRevisionViolation(str(error)) from error
    source = edit.get("source") or {}
    if not isinstance(source, dict):
        raise RecipeRevisionViolation("TTS_PROVENANCE_MISSING")
    report = _source_path(
        package,
        source,
        "tts_generation_report",
        code="TTS_PROVENANCE_MISSING",
    )
    report_payload = _read_json(report, code="TTS_PROVENANCE_INVALID")
    bound_relative = report_payload.get("edit_recipe_relative_path")
    if not isinstance(bound_relative, str) or not bound_relative.strip():
        raise RecipeRevisionViolation("TTS_PROVENANCE_INVALID")
    bound_edit = _inside(package, package / bound_relative, code="EDIT_OUTSIDE_PACKAGE")
    lock = verify_bound_recipe_lock(package, bound_edit, report)
    _require_current_voice_evidence(package, edit)
    return {
        "eligible_for_voice_reuse": True,
        "candidate_edit": str(edit_file),
        "bound_edit": str(bound_edit),
        "bound_edit_sha256": lock["edit_recipe_sha256"],
        "voice": str(_source_path(package, source, "voice", code="VOICE_OUTSIDE_PACKAGE")),
        "tts_report": str(report),
        "next_action": "run_authoring_check_then_layout_check_without_regenerating_tts",
    }


def _exclusive_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as output:
        output.write(source.read_bytes())
        output.flush()
        os.fsync(output.fileno())


def fork_recipe_for_voice_reuse(
    package_dir: str | Path,
    *,
    planning_path: str | Path,
    edit_path: str | Path,
) -> dict[str, Any]:
    """Create the next immutable-safe recipe revision while retaining audio evidence."""

    package = Path(package_dir).resolve()
    planning = _inside(package, planning_path, code="PLANNING_OUTSIDE_PACKAGE")
    edit = _inside(package, edit_path, code="EDIT_OUTSIDE_PACKAGE")
    if planning.parent != package or edit.parent != package:
        raise RecipeRevisionViolation("RECIPE_FORK_SOURCE_NOT_PACKAGE_ROOT")
    planning_match = _PLANNING_VERSION.fullmatch(planning.name)
    edit_match = _EDIT_VERSION.fullmatch(edit.name)
    if (
        planning_match is None
        or edit_match is None
        or planning_match.group("prefix") != edit_match.group("prefix")
        or planning_match.group("version") != edit_match.group("version")
    ):
        raise RecipeRevisionViolation("RECIPE_FORK_SOURCE_NAME_INVALID")
    check_voice_reuse_candidate(package, edit)
    prefix = edit_match.group("prefix")
    versions = [
        int(match.group("version"))
        for path in package.glob(f"{prefix}_v*_edit_recipe.json")
        if (match := _EDIT_VERSION.fullmatch(path.name)) is not None
        and match.group("prefix") == prefix
    ]
    next_version = max(versions, default=int(edit_match.group("version"))) + 1
    next_planning = package / f"{prefix}_v{next_version}_planning_recipe.json"
    next_edit = package / f"{prefix}_v{next_version}_edit_recipe.json"
    receipt = package / "_work" / "recipe_forks" / f"{prefix}_v{next_version}.json"
    created: list[Path] = []
    try:
        _exclusive_copy(planning, next_planning)
        created.append(next_planning)
        _exclusive_copy(edit, next_edit)
        created.append(next_edit)
        payload = {
            "schema_version": FORK_SCHEMA,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_planning_relative_path": planning.relative_to(package).as_posix(),
            "source_planning_sha256": _sha256(planning),
            "source_edit_relative_path": edit.relative_to(package).as_posix(),
            "source_edit_sha256": _sha256(edit),
            "forked_planning_relative_path": next_planning.relative_to(package).as_posix(),
            "forked_planning_sha256": _sha256(next_planning),
            "forked_edit_relative_path": next_edit.relative_to(package).as_posix(),
            "forked_edit_sha256": _sha256(next_edit),
            "voice_reuse": check_voice_reuse_candidate(package, next_edit),
        }
        _atomic_create_json(receipt, payload)
        created.append(receipt)
    except FileExistsError as error:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise RecipeRevisionViolation("RECIPE_FORK_COLLISION") from error
    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    return {
        "status": "forked_for_voice_reuse",
        "planning": str(next_planning),
        "edit": str(next_edit),
        "fork_receipt": str(receipt),
        "voice_reuse": payload["voice_reuse"],
        "next_action": "edit_visual_metadata_only_then_run_voice_reuse_check",
    }
