"""Recoverable migration from dated output inboxes to flat package paths."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Any

from .package_state import map_legacy_package


METADATA_FILENAME = "CANONICAL_PACKAGE_METADATA.json"
STATE_DIRECTORY = ".review_reel_production"
ACTIVE_POINTER_FILENAME = "active_package.json"
REGISTRY_FILENAME = "registry.json"
REPORT_SCHEMA_VERSION = "review-reel-output-flatten-plan-v1"
RECEIPT_SCHEMA_VERSION = "review-reel-output-flatten-receipt-v1"
CONFIRMATION = "FLATTEN_REVIEW_PACKAGES"
_CONTENT_PREFIX = re.compile(r"^\d{3}_")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class OutputLayoutViolation(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


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


def _is_inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _tree_evidence(directory: Path) -> dict[str, Any]:
    if not directory.is_dir() or directory.is_symlink():
        raise OutputLayoutViolation("OUTPUT_FLATTEN_SOURCE_INVALID")
    digest = hashlib.sha256()
    file_count = 0
    total_bytes = 0
    for path in sorted(directory.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if path.is_symlink():
            raise OutputLayoutViolation("OUTPUT_FLATTEN_REPARSE_POINT_FORBIDDEN")
        if not path.is_file():
            continue
        relative = path.relative_to(directory).as_posix()
        data = path.read_bytes()
        file_digest = hashlib.sha256(data).hexdigest()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(data)).encode("ascii"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        digest.update(b"\n")
        file_count += 1
        total_bytes += len(data)
    return {
        "file_count": file_count,
        "total_bytes": total_bytes,
        "tree_sha256": digest.hexdigest(),
    }


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OutputLayoutViolation(code) from error
    if not isinstance(value, dict):
        raise OutputLayoutViolation(code)
    return value


def create_flatten_plan(
    *, output_root: str | Path, report_path: str | Path, now: datetime | None = None
) -> dict[str, Any]:
    """Write a non-mutating, hash-bound plan for numeric inbox packages only."""

    root = Path(output_root).resolve()
    report = Path(report_path).resolve()
    if not root.is_dir():
        raise OutputLayoutViolation("OUTPUT_ROOT_MISSING")
    if _is_inside(root, report):
        raise OutputLayoutViolation("OUTPUT_FLATTEN_REPORT_MUST_BE_OUTSIDE_OUTPUT")

    moves: list[dict[str, Any]] = []
    protected_packages: list[dict[str, str]] = []
    planned_destinations: set[str] = set()
    for inbox in sorted(root.glob("inbox_*"), key=lambda path: path.name.casefold()):
        if not inbox.is_dir() or inbox.is_symlink():
            continue
        for source in sorted(inbox.iterdir(), key=lambda path: path.name.casefold()):
            if not source.is_dir() or not _CONTENT_PREFIX.match(source.name):
                continue
            state = map_legacy_package(source)
            if state.get("render_complete") is True:
                protected_packages.append(
                    {
                        "source_relative_path": source.relative_to(root).as_posix(),
                        "reason": "verified_render_evidence_path_bound",
                    }
                )
                continue
            destination = root / source.name
            destination_key = destination.as_posix().casefold()
            if destination.exists() or destination_key in planned_destinations:
                raise OutputLayoutViolation("OUTPUT_FLAT_DESTINATION_COLLISION")
            planned_destinations.add(destination_key)
            evidence = _tree_evidence(source)
            moves.append(
                {
                    "source_relative_path": source.relative_to(root).as_posix(),
                    "destination_relative_path": destination.relative_to(root).as_posix(),
                    **evidence,
                }
            )

    clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    payload = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "created_at": clock.isoformat(),
        "output_root": str(root),
        "move_count": len(moves),
        "total_file_count": sum(move["file_count"] for move in moves),
        "total_bytes": sum(move["total_bytes"] for move in moves),
        "moves": moves,
        "protected_packages": protected_packages,
        "excluded_scopes": [
            ".review_reel_production",
            "blog_reels_prototypes",
            "pilot",
            "playwright",
            "CAND-*",
            "direct inbox files",
        ],
        "source_container_policy": "preserve; no inbox directory deletion",
        "rollback": "rename every destination back to its recorded source path",
    }
    _atomic_write_json(report, payload)
    return payload


def _restore_bytes(path: Path, value: bytes | None) -> None:
    if value is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def apply_flatten_plan(
    *,
    output_root: str | Path,
    report_path: str | Path,
    report_sha256: str,
    confirm: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Apply a verified plan and roll back all completed moves on any error."""

    if confirm != CONFIRMATION:
        raise OutputLayoutViolation("OUTPUT_FLATTEN_CONFIRMATION_REQUIRED")
    if not isinstance(report_sha256, str) or not _SHA256.fullmatch(report_sha256):
        raise OutputLayoutViolation("OUTPUT_FLATTEN_REPORT_HASH_MISMATCH")
    root = Path(output_root).resolve()
    report_path_value = Path(report_path).resolve()
    if _is_inside(root, report_path_value):
        raise OutputLayoutViolation("OUTPUT_FLATTEN_REPORT_MUST_BE_OUTSIDE_OUTPUT")
    try:
        report_bytes = report_path_value.read_bytes()
    except OSError as error:
        raise OutputLayoutViolation("OUTPUT_FLATTEN_REPORT_INVALID") from error
    if hashlib.sha256(report_bytes).hexdigest() != report_sha256:
        raise OutputLayoutViolation("OUTPUT_FLATTEN_REPORT_HASH_MISMATCH")
    plan = _load_json(report_path_value, "OUTPUT_FLATTEN_REPORT_INVALID")
    if plan.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise OutputLayoutViolation("OUTPUT_FLATTEN_REPORT_SCHEMA_INVALID")
    if Path(str(plan.get("output_root", ""))).resolve() != root:
        raise OutputLayoutViolation("OUTPUT_FLATTEN_ROOT_MISMATCH")
    moves = plan.get("moves")
    if not isinstance(moves, list) or plan.get("move_count") != len(moves):
        raise OutputLayoutViolation("OUTPUT_FLATTEN_REPORT_INVALID")

    resolved_moves: list[tuple[Path, Path, dict[str, Any]]] = []
    seen_sources: set[str] = set()
    seen_destinations: set[str] = set()
    for move in moves:
        if not isinstance(move, dict):
            raise OutputLayoutViolation("OUTPUT_FLATTEN_REPORT_INVALID")
        source = (root / str(move.get("source_relative_path", ""))).resolve()
        destination = (root / str(move.get("destination_relative_path", ""))).resolve()
        if not _is_inside(root, source) or not _is_inside(root, destination):
            raise OutputLayoutViolation("OUTPUT_FLATTEN_PATH_INVALID")
        if source.parent.parent != root or not source.parent.name.startswith("inbox_"):
            raise OutputLayoutViolation("OUTPUT_FLATTEN_PATH_INVALID")
        if destination.parent != root or destination.name != source.name:
            raise OutputLayoutViolation("OUTPUT_FLATTEN_PATH_INVALID")
        source_key = source.as_posix().casefold()
        destination_key = destination.as_posix().casefold()
        if source_key in seen_sources or destination_key in seen_destinations:
            raise OutputLayoutViolation("OUTPUT_FLAT_DESTINATION_COLLISION")
        seen_sources.add(source_key)
        seen_destinations.add(destination_key)
        if destination.exists():
            raise OutputLayoutViolation("OUTPUT_FLAT_DESTINATION_COLLISION")
        if map_legacy_package(source).get("render_complete") is True:
            raise OutputLayoutViolation("OUTPUT_FLATTEN_VERIFIED_RENDER_PROTECTED")
        evidence = _tree_evidence(source)
        if any(evidence[key] != move.get(key) for key in evidence):
            raise OutputLayoutViolation("OUTPUT_FLATTEN_SOURCE_CHANGED")
        resolved_moves.append((source, destination, move))

    state_dir = root / STATE_DIRECTORY
    pointer_path = state_dir / ACTIVE_POINTER_FILENAME
    registry_path = state_dir / REGISTRY_FILENAME
    state_backups = {
        pointer_path: pointer_path.read_bytes() if pointer_path.is_file() else None,
        registry_path: registry_path.read_bytes() if registry_path.is_file() else None,
    }
    metadata_backups: dict[Path, bytes] = {}
    moved: list[tuple[Path, Path]] = []
    receipt_path = report_path_value.with_name(f"{report_path_value.stem}.applied.json")
    if receipt_path.exists():
        raise OutputLayoutViolation("OUTPUT_FLATTEN_RECEIPT_EXISTS")
    mapping = {
        move["source_relative_path"]: move["destination_relative_path"]
        for _, _, move in resolved_moves
    }
    try:
        for source, destination, _ in resolved_moves:
            source.rename(destination)
            moved.append((source, destination))

        for _, destination, _ in resolved_moves:
            metadata_path = destination / METADATA_FILENAME
            if not metadata_path.is_file():
                continue
            metadata_backups[metadata_path] = metadata_path.read_bytes()
            metadata = _load_json(metadata_path, "OUTPUT_FLATTEN_METADATA_INVALID")
            metadata["package_relative_path"] = destination.relative_to(root).as_posix()
            _atomic_write_json(metadata_path, metadata)

        if registry_path.is_file():
            registry = _load_json(registry_path, "OUTPUT_FLATTEN_REGISTRY_INVALID")
            active = registry.get("active_package_relative_path")
            if active in mapping:
                registry["active_package_relative_path"] = mapping[active]
            records = registry.get("packages")
            if isinstance(records, list):
                for record in records:
                    if isinstance(record, dict) and record.get("package_relative_path") in mapping:
                        record["package_relative_path"] = mapping[record["package_relative_path"]]
            _atomic_write_json(registry_path, registry)

        if pointer_path.is_file():
            pointer = _load_json(pointer_path, "OUTPUT_FLATTEN_POINTER_INVALID")
            active = pointer.get("package_relative_path")
            if active in mapping:
                pointer["package_relative_path"] = mapping[active]
                metadata_path = root / mapping[active] / METADATA_FILENAME
                if not metadata_path.is_file():
                    raise OutputLayoutViolation("OUTPUT_FLATTEN_ACTIVE_METADATA_MISSING")
                pointer["metadata_sha256"] = hashlib.sha256(metadata_path.read_bytes()).hexdigest()
            _atomic_write_json(pointer_path, pointer)

        clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        receipt = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "status": "applied",
            "applied_at": clock.isoformat(),
            "output_root": str(root),
            "plan_relative_path": report_path_value.name,
            "plan_sha256": report_sha256,
            "move_count": len(resolved_moves),
            "moves": [
                {
                    "source_relative_path": source.relative_to(root).as_posix(),
                    "destination_relative_path": destination.relative_to(root).as_posix(),
                }
                for source, destination, _ in resolved_moves
            ],
        }
        _atomic_write_json(receipt_path, receipt)
    except Exception:
        for path, value in state_backups.items():
            _restore_bytes(path, value)
        for path, value in metadata_backups.items():
            _restore_bytes(path, value)
        for source, destination in reversed(moved):
            if destination.exists() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                destination.rename(source)
        raise

    return receipt
