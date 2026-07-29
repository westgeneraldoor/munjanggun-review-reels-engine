"""Delete only hash-verified, explicitly approved generated intermediates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


CONFIRMATION = "DELETE_GENERATED_INTERMEDIATES"
SAFE_CATEGORIES = frozenset(
    {
        "frame_intermediate",
        "contact_sheet",
        "rejected_intermediate",
    }
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_report(path: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("invalid report") from error
    if (
        not isinstance(report, dict)
        or report.get("schema_version") != "1.0"
        or report.get("mode") != "dry_run_only"
        or not isinstance(report.get("candidates"), list)
    ):
        raise ValueError("invalid report")
    return report


def _preflight(
    root: Path,
    report: dict[str, Any],
    categories: set[str],
) -> list[tuple[Path, int, str]]:
    if not categories or not categories.issubset(SAFE_CATEGORIES):
        raise ValueError("unsupported category")
    recorded_root = Path(str(report.get("root", "")))
    if not recorded_root.is_dir() or not root.samefile(recorded_root):
        raise ValueError("report root mismatch")

    targets: list[tuple[Path, int, str]] = []
    for candidate in report["candidates"]:
        if not isinstance(candidate, dict) or candidate.get("category") not in categories:
            continue
        relative_path = candidate.get("relative_path")
        if not isinstance(relative_path, str) or not relative_path or Path(relative_path).is_absolute():
            raise ValueError("invalid candidate path")
        requested_path = root / relative_path
        if requested_path.is_symlink():
            raise ValueError("symlink candidate")
        try:
            resolved_path = requested_path.resolve(strict=True)
            resolved_path.relative_to(root)
            expected_bytes = int(candidate["bytes"])
            expected_hash = str(candidate["sha256"]).lower()
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise ValueError("invalid candidate") from error
        if (
            not resolved_path.is_file()
            or resolved_path.stat().st_size != expected_bytes
            or _sha256(resolved_path) != expected_hash
        ):
            raise ValueError(f"candidate changed: {relative_path}")
        targets.append((resolved_path, expected_bytes, expected_hash))

    if not targets:
        raise ValueError("no matching candidates")
    return targets


def apply_cleanup(root: Path, report_path: Path, categories: set[str]) -> dict[str, int]:
    root = root.resolve(strict=True)
    report = _load_report(report_path)
    targets = _preflight(root, report, categories)

    for path, expected_bytes, expected_hash in targets:
        if path.stat().st_size != expected_bytes or _sha256(path) != expected_hash:
            raise ValueError(f"candidate changed: {path.relative_to(root).as_posix()}")

    deleted_bytes = 0
    for path, expected_bytes, _ in targets:
        path.unlink()
        deleted_bytes += expected_bytes

    return {
        "deleted_files": len(targets),
        "deleted_bytes": deleted_bytes,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--category", action="append", required=True)
    parser.add_argument("--confirm", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.confirm != CONFIRMATION:
            raise ValueError("confirmation mismatch")
        summary = apply_cleanup(
            Path(args.root),
            Path(args.report),
            set(args.category),
        )
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError) as error:
        print(f"CLEANUP_APPLY_BLOCKED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
