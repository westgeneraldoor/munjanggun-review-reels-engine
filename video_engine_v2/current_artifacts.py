"""Current-artifact ledger for new canonical review-reel packages.

The ledger stores pointers only. Approval and review status are computed by
re-validating the pointed receipts with the official authority validators.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from tempfile import NamedTemporaryFile
from typing import Any


SCHEMA_VERSION = "review-reel-current-artifacts-v1"
LEDGER_FILENAME = "CURRENT_ARTIFACTS.json"
METADATA_CONTRACT_FIELD = "current_artifacts_contract"
POINTER_KINDS = frozenset(
    {
        "script",
        "planning_recipe",
        "edit_recipe",
        "captions",
        "voice",
        "tts_report",
        "voice_manual_review",
        "privacy_manifest",
        "sync_manifest",
        "html",
        "html_artifact_evidence",
        "html_qa_report",
        "html_manual_review",
        "html_approval",
        "mp4_render_approval",
        "render_job",
        "upload_mp4",
        "post_render_qa",
        "render_manual_review",
    }
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CurrentArtifactsViolation(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_identity(package: Path) -> dict[str, str]:
    resolved = package.resolve()
    return {"package_path": str(resolved), "package_name": resolved.name}


def ledger_path(package_dir: str | Path) -> Path:
    return Path(package_dir).resolve() / LEDGER_FILENAME


def empty_ledger(
    package_dir: str | Path,
    *,
    now: datetime | None = None,
    identity_dir: str | Path | None = None,
) -> dict[str, Any]:
    clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "schema_version": SCHEMA_VERSION,
        "package_identity": _package_identity(Path(identity_dir or package_dir)),
        "revision": 0,
        "updated_at": clock.isoformat(),
        "pointers": {},
    }


def metadata_declares_ledger(metadata: Any) -> bool:
    return isinstance(metadata, dict) and metadata.get(METADATA_CONTRACT_FIELD) == SCHEMA_VERSION


def read_canonical_metadata(package_dir: str | Path) -> dict[str, Any] | None:
    path = Path(package_dir).resolve() / "CANONICAL_PACKAGE_METADATA.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def package_uses_ledger(package_dir: str | Path) -> bool:
    return metadata_declares_ledger(read_canonical_metadata(package_dir))


def initialize_ledger(
    package_dir: str | Path,
    *,
    now: datetime | None = None,
    identity_dir: str | Path | None = None,
) -> Path:
    path = ledger_path(package_dir)
    if path.exists():
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_EXISTS")
    _atomic_write_json(path, empty_ledger(package_dir, now=now, identity_dir=identity_dir))
    return path


def file_pointer(
    package_dir: str | Path,
    path: str | Path,
    *,
    kind: str,
    producer: str,
    recorded_at: str | None = None,
    attempt_id: str | None = None,
    revision_id: str | None = None,
) -> dict[str, Any]:
    if kind not in POINTER_KINDS:
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_POINTER_KIND_UNKNOWN")
    if not isinstance(producer, str) or not producer.strip():
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_PRODUCER_INVALID")
    package = Path(package_dir).resolve()
    target = Path(path).resolve()
    try:
        relative = target.relative_to(package).as_posix()
    except ValueError as error:
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_PATH_OUTSIDE_PACKAGE") from error
    if not target.is_file():
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_TARGET_MISSING")
    pointer = {
        "relative_path": relative,
        "bytes": target.stat().st_size,
        "sha256": _sha256(target),
        "artifact_kind": kind,
        "producer": producer.strip(),
        "recorded_at": recorded_at or datetime.now(timezone.utc).isoformat(),
    }
    if attempt_id:
        pointer["attempt_id"] = str(attempt_id)
    if revision_id:
        pointer["revision_id"] = str(revision_id)
    return pointer


def _validate_pointer_metadata(package: Path, kind: str, pointer: Any) -> dict[str, Any]:
    """Validate pointer authority fields without requiring the old target to remain current.

    Writers use this only for kinds they are replacing while holding the ledger
    lock. Readers always use the strict content-validating path below.
    """
    if not isinstance(pointer, dict):
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_POINTER_INVALID")
    relative = pointer.get("relative_path")
    byte_count = pointer.get("bytes")
    digest = pointer.get("sha256")
    if (
        not isinstance(relative, str)
        or not relative.strip()
        or Path(relative).is_absolute()
        or relative.replace("\\", "/").startswith("../")
    ):
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_PATH_OUTSIDE_PACKAGE")
    target = (package / relative).resolve()
    try:
        target.relative_to(package)
    except ValueError as error:
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_PATH_OUTSIDE_PACKAGE") from error
    if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 0:
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_BYTES_MISMATCH")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_HASH_MISMATCH")
    if pointer.get("artifact_kind") != kind:
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_POINTER_KIND_MISMATCH")
    if not isinstance(pointer.get("producer"), str) or not pointer["producer"].strip():
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_PRODUCER_INVALID")
    if not isinstance(pointer.get("recorded_at"), str) or not pointer["recorded_at"].strip():
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_POINTER_INVALID")
    return dict(pointer)


def validate_ledger_payload(
    payload: Any,
    package_dir: str | Path,
    *,
    replacing_kinds: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    package = Path(package_dir).resolve()
    if not isinstance(payload, dict):
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_INVALID")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_SCHEMA_INVALID")
    identity = payload.get("package_identity")
    expected = _package_identity(package)
    if not isinstance(identity, dict) or identity.get("package_name") != expected["package_name"]:
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_PACKAGE_MISMATCH")
    try:
        same = os.path.samefile(str(identity.get("package_path") or ""), package)
    except OSError:
        same = False
    if not same:
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_PACKAGE_MISMATCH")
    revision = payload.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_REVISION_INVALID")
    if not isinstance(payload.get("updated_at"), str) or not payload["updated_at"].strip():
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_INVALID")
    pointers = payload.get("pointers")
    if not isinstance(pointers, dict):
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_POINTERS_INVALID")
    validated: dict[str, Any] = {}
    for kind, pointer in pointers.items():
        if kind not in POINTER_KINDS:
            raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_POINTER_KIND_UNKNOWN")
        validated[kind] = (
            _validate_pointer_metadata(package, kind, pointer)
            if kind in replacing_kinds
            else _validate_pointer(package, kind, pointer)
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "package_identity": expected,
        "revision": revision,
        "updated_at": payload["updated_at"],
        "pointers": validated,
    }


def _validate_pointer(package: Path, kind: str, pointer: Any) -> dict[str, Any]:
    validated = _validate_pointer_metadata(package, kind, pointer)
    relative = validated["relative_path"]
    byte_count = validated["bytes"]
    digest = validated["sha256"]
    target = (package / relative).resolve()
    if not target.is_file():
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_TARGET_MISSING")
    if target.stat().st_size != byte_count:
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_BYTES_MISMATCH")
    if _sha256(target) != digest:
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_HASH_MISMATCH")
    return validated


def read_ledger(package_dir: str | Path) -> dict[str, Any]:
    path = ledger_path(package_dir)
    if not path.is_file():
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_MISSING")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_INVALID") from error
    return validate_ledger_payload(payload, package_dir)


def _read_ledger_for_update(package_dir: str | Path, replacing_kinds: frozenset[str]) -> dict[str, Any]:
    """Read a ledger while permitting only explicitly replaced targets to be stale."""
    path = ledger_path(package_dir)
    if not path.is_file():
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_MISSING")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_INVALID") from error
    return validate_ledger_payload(payload, package_dir, replacing_kinds=replacing_kinds)


def pointer_file(package_dir: str | Path, kind: str) -> Path | None:
    ledger = read_ledger(package_dir)
    pointer = ledger["pointers"].get(kind)
    if pointer is None:
        return None
    return (Path(package_dir).resolve() / pointer["relative_path"]).resolve()


def require_ledger_if_enabled(package_dir: str | Path) -> dict[str, Any] | None:
    if not package_uses_ledger(package_dir):
        return None
    return read_ledger(package_dir)


@contextmanager
def _ledger_lock(package: Path):
    lock_dir = package / "_work"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "current_artifacts.lock"
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT)
    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"0")
            os.fsync(fd)
        _acquire_lock(fd)
        yield
    finally:
        try:
            _release_lock(fd)
        finally:
            os.close(fd)


def _acquire_lock(fd: int) -> None:
    deadline = time.time() + 10
    while True:
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError:
            if time.time() >= deadline:
                raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_LOCK_TIMEOUT")
            time.sleep(0.02)


def _release_lock(fd: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
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


def update_pointers(
    package_dir: str | Path,
    pointers: dict[str, dict[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not pointers:
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_POINTERS_INVALID")
    if len(set(pointers)) != len(pointers):
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_POINTER_DUPLICATE")
    package = Path(package_dir).resolve()
    clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    with _ledger_lock(package):
        replacing_kinds = frozenset(pointers)
        current = _read_ledger_for_update(package, replacing_kinds)
        merged = dict(current["pointers"])
        for kind, pointer in pointers.items():
            merged[kind] = _validate_pointer(package, kind, pointer)
        updated = {
            "schema_version": SCHEMA_VERSION,
            "package_identity": _package_identity(package),
            "revision": current["revision"] + 1,
            "updated_at": clock.isoformat(),
            "pointers": merged,
        }
        _atomic_write_json(ledger_path(package), updated)
        return updated


def record_current_artifacts(
    package_dir: str | Path,
    *,
    producer: str,
    artifacts: dict[str, str | Path],
    attempt_id: str | None = None,
    revision_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Update ledger pointers after a successful official writer.

    Legacy packages without the ledger contract are left untouched.
    """

    if not package_uses_ledger(package_dir):
        return None
    pointers = {
        kind: file_pointer(
            package_dir,
            path,
            kind=kind,
            producer=producer,
            attempt_id=attempt_id,
            revision_id=revision_id,
        )
        for kind, path in artifacts.items()
    }
    return update_pointers(package_dir, pointers, now=now)


def require_enabled_ledger(package_dir: str | Path) -> dict[str, Any]:
    if not package_uses_ledger(package_dir):
        raise CurrentArtifactsViolation("CURRENT_ARTIFACTS_NOT_ENABLED")
    return read_ledger(package_dir)
