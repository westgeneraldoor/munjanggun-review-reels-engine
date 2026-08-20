"""Durable state and evidence helpers for official background render jobs."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Any


JOB_STATES = frozenset({"queued", "running", "succeeded", "failed"})
_JOB_ID = re.compile(r"^[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}$")
_MUTABLE_FIELDS = frozenset(
    {
        "state",
        "worker_pid",
        "renderer_pid",
        "started_at",
        "completed_at",
        "rendered_frames",
        "output_evidence",
        "failure",
        "exit_code",
    }
)
_STATE_TRANSITIONS = {
    "queued": frozenset({"queued", "running", "failed"}),
    "running": frozenset({"running", "succeeded", "failed"}),
    "succeeded": frozenset({"succeeded"}),
    "failed": frozenset({"failed"}),
}
_FINAL_OUTPUT_NAME = re.compile(
    r"^(?P<prefix>.+_final_render_\d{8})(?:_attempt(?P<attempt>\d{2}))?_upload_10mbps\.mp4$",
    re.IGNORECASE,
)


class RenderJobError(ValueError):
    """A render job contract or containment failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: dict[str, Any]) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _inside(root: Path, candidate: str | Path, code: str) -> Path:
    resolved = Path(candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise RenderJobError(code) from error
    return resolved


def job_record_path(package_dir: str | Path, job_id: str) -> Path:
    if not _JOB_ID.fullmatch(job_id):
        raise RenderJobError("JOB_ID_INVALID")
    return Path(package_dir).resolve() / "_work" / "render_jobs" / job_id / "render_job.json"


def next_retry_output_path(output_path: str | Path) -> Path:
    """Return the next valid, non-overwriting official render attempt name."""
    output = Path(output_path).resolve()
    match = _FINAL_OUTPUT_NAME.fullmatch(output.name)
    if not match:
        raise RenderJobError("FINAL_FILENAME_INVALID")
    next_attempt = int(match.group("attempt") or "1") + 1
    if next_attempt > 99:
        raise RenderJobError("RENDER_ATTEMPT_LIMIT_REACHED")
    return output.with_name(f"{match.group('prefix')}_attempt{next_attempt:02}_upload_10mbps.mp4")


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
            temporary.write(rendered)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _job_snapshot_path(job_path: Path, state: str) -> Path:
    return job_path.parent / f"render_job_{state}.json"


def publish_job_snapshot(
    job_path: str | Path,
    *,
    producer: str,
    extra_artifacts: dict[str, str | Path] | None = None,
) -> Path:
    """Publish one immutable job-state snapshot as current ledger evidence."""
    path = Path(job_path).resolve()
    payload = read_job(path)
    package = Path(payload["bindings"]["package_path"]).resolve()
    from video_engine_v2.current_artifacts import (
        CurrentArtifactsViolation,
        package_uses_ledger,
        record_current_artifacts,
    )

    if not package_uses_ledger(package):
        return path
    snapshot = _job_snapshot_path(path, payload["state"])
    if snapshot.exists():
        try:
            existing = json.loads(snapshot.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RenderJobError("JOB_SNAPSHOT_INVALID") from error
        if existing != payload:
            raise RenderJobError("JOB_SNAPSHOT_CONFLICT")
    else:
        _atomic_write_json(snapshot, payload)
    artifacts: dict[str, str | Path] = {"render_job": snapshot}
    artifacts.update(extra_artifacts or {})
    try:
        record_current_artifacts(
            package,
            producer=producer,
            artifacts=artifacts,
            attempt_id=str(payload.get("job_id") or ""),
        )
    except CurrentArtifactsViolation as error:
        raise RenderJobError(str(error)) from error
    return snapshot


def create_job_record(
    *,
    package_dir: str | Path,
    job_id: str,
    bindings: dict[str, Any],
    receipt_path: str | Path,
    output_path: str | Path,
    expected_frames: int,
) -> Path:
    package = Path(package_dir).resolve()
    job_path = job_record_path(package, job_id)
    if not isinstance(expected_frames, int) or isinstance(expected_frames, bool) or expected_frames <= 0:
        raise RenderJobError("EXPECTED_FRAMES_INVALID")
    receipt = _inside(package, receipt_path, "RECEIPT_OUTSIDE_PACKAGE")
    output = _inside(package, output_path, "OUTPUT_OUTSIDE_PACKAGE")
    if not receipt.is_file():
        raise RenderJobError("RECEIPT_MISSING")

    job_dir = job_path.parent
    if job_dir.exists():
        raise RenderJobError("JOB_ALREADY_EXISTS")
    frame_dir = output.parent / f"{output.stem}_frames"
    log_path = job_dir / "render.log"
    bound = dict(bindings)
    bound.update(
        {
            "package_path": str(package),
            "receipt_path": str(receipt),
            "receipt_sha256": sha256_file(receipt),
            "output_path": str(output),
        }
    )
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "job_id": job_id,
        "state": "queued",
        "created_at": utc_now(),
        "started_at": None,
        "completed_at": None,
        "worker_pid": None,
        "renderer_pid": None,
        "expected_frames": expected_frames,
        "rendered_frames": 0,
        "frame_dir": str(frame_dir.resolve()),
        "log_path": str(log_path.resolve()),
        "bindings": bound,
        "bindings_sha256": _sha256_json(bound),
        "output_evidence": None,
        "failure": None,
        "exit_code": None,
    }
    _atomic_write_json(job_path, payload)
    publish_job_snapshot(job_path, producer="render_job.create_job_record")
    return job_path


def read_job(path: str | Path) -> dict[str, Any]:
    job_path = Path(path).resolve()
    try:
        payload = json.loads(job_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RenderJobError("JOB_RECORD_INVALID") from error
    if not isinstance(payload, dict) or payload.get("state") not in JOB_STATES:
        raise RenderJobError("JOB_RECORD_INVALID")
    package_value = payload.get("bindings", {}).get("package_path")
    job_id = payload.get("job_id")
    if not isinstance(package_value, str) or not isinstance(job_id, str):
        raise RenderJobError("JOB_RECORD_INVALID")
    if payload.get("bindings_sha256") != _sha256_json(payload["bindings"]):
        raise RenderJobError("JOB_BINDINGS_TAMPERED")
    expected = Path(package_value).resolve() / "_work" / "render_jobs" / job_id / "render_job.json"
    if job_path != expected:
        raise RenderJobError("JOB_RECORD_OUTSIDE_PACKAGE")
    return payload


def update_job(path: str | Path, **changes: Any) -> dict[str, Any]:
    unknown = set(changes) - _MUTABLE_FIELDS
    if unknown:
        raise RenderJobError("JOB_FIELD_IMMUTABLE")
    if "state" in changes and changes["state"] not in JOB_STATES:
        raise RenderJobError("JOB_STATE_INVALID")
    payload = read_job(path)
    if "state" in changes and changes["state"] not in _STATE_TRANSITIONS[payload["state"]]:
        raise RenderJobError("JOB_STATE_TRANSITION_INVALID")
    payload.update(changes)
    _atomic_write_json(Path(path).resolve(), payload)
    return payload


def refresh_progress(path: str | Path) -> dict[str, Any]:
    payload = read_job(path)
    frame_dir = Path(payload["frame_dir"])
    rendered = 0
    if frame_dir.is_dir():
        rendered = sum(1 for item in frame_dir.iterdir() if item.is_file() and re.fullmatch(r"frame_[0-9]{5}\.png", item.name))
    refreshed = dict(payload)
    refreshed["rendered_frames"] = rendered
    refreshed["progress"] = f"{rendered} / {payload['expected_frames']}"
    return refreshed
