"""Read-only cleanup candidate scanner for local review-reel artifacts.

This module deliberately has no apply/delete operation. It reports only narrow,
manually-reviewable candidates and treats customer sources and production
evidence as protected by default.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from typing import Any


ROOT_MEDIA_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".mp3",
    ".wav",
    ".m4a",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".heic",
    ".gif",
}
_FINAL_UPLOAD_MP4 = re.compile(r"upload.*\.mp4$", re.IGNORECASE)
_RECIPE_OR_EVIDENCE = re.compile(
    r"(?:planning_recipe|edit_recipe|sync_manifest|(?:^|[_-])script|\.srt$|voice\.(?:mp3|wav|m4a)$|"
    r"status\.md$|approval_log\.md$|(?:html|mp4_render)_approval\.json$|privacy|production_gates|render_post_qa|representative_frames)",
    re.IGNORECASE,
)
_CANDIDATE_RULES = (
    ("scale_lock", re.compile(r"scale[_-]?lock", re.IGNORECASE)),
    ("one_fps", re.compile(r"(?:^|[_-])1fps(?:$|[_-])|1fps", re.IGNORECASE)),
    ("contact_sheet", re.compile(r"contact[_ -]?sheet", re.IGNORECASE)),
    ("rejected_intermediate", re.compile(r"rejected", re.IGNORECASE)),
    ("frame_intermediate", re.compile(r"(?:^|[\\/_-])frames?(?:$|[\\/_-])|thumbnail|thumb", re.IGNORECASE)),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path, root: Path) -> str:
    return path.absolute().relative_to(root.absolute()).as_posix()


def _within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _protected_reason(path: Path, root: Path) -> str | None:
    if path.is_symlink():
        return "symlink_not_scanned"
    relative = _relative(path, root)
    parts = {part.lower() for part in Path(relative).parts}
    name = path.name
    lowered = relative.lower()
    if "reviews" in parts:
        return "review_source"
    if path.parent.resolve() == root.resolve() and path.suffix.lower() in ROOT_MEDIA_EXTENSIONS:
        return "root_media"
    if _FINAL_UPLOAD_MP4.search(name):
        return "final_upload_mp4"
    if _RECIPE_OR_EVIDENCE.search(lowered):
        return "production_recipe_or_evidence"
    return None


def _candidate_category(path: Path, root: Path) -> str | None:
    relative = _relative(path, root)
    for category, pattern in _CANDIDATE_RULES:
        if pattern.search(relative):
            return category
    return None


def _file_record(path: Path, root: Path, *, category: str | None = None, reason: str | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "relative_path": _relative(path, root),
        "bytes": path.stat().st_size,
    }
    if category:
        record["category"] = category
    if reason:
        record["reason"] = reason
    return record


def scan_cleanup_candidates(root_dir: str | Path) -> dict[str, Any]:
    """Return a read-only inventory of narrow cleanup candidates.

    All files not matching a candidate allowlist are excluded from potential
    savings. No filesystem mutations occur in this function.
    """
    root = Path(root_dir).resolve()
    if not root.is_dir():
        raise ValueError("ROOT_MISSING")

    candidates: list[dict[str, Any]] = []
    protected: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = [
        {"path": "reviews/", "reason": "always protected review/customer source"},
        {"path": "output/*upload*.mp4", "reason": "always protected final upload MP4"},
        {"path": "recipes, voice, SRT, STATUS, APPROVAL, privacy and post-render QA", "reason": "production evidence"},
    ]

    for root_media in root.iterdir():
        if root_media.is_file() and root_media.suffix.lower() in ROOT_MEDIA_EXTENSIONS:
            protected.append(_file_record(root_media, root, reason="root_media"))

    for local_name in ("reviews", "output", "scratch"):
        local_dir = root / local_name
        if not local_dir.is_dir():
            continue
        for path in local_dir.rglob("*"):
            if not path.is_file():
                continue
            reason = _protected_reason(path, root)
            if reason:
                protected.append(_file_record(path, root, reason=reason))
                continue
            category = _candidate_category(path, root)
            if category:
                candidates.append(_file_record(path, root, category=category))

    hashes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        path = root / candidate["relative_path"]
        candidate_hash = _sha256(path)
        candidate["sha256"] = candidate_hash
        hashes[candidate_hash].append(candidate)

    duplicate_groups = [
        {
            "sha256": digest,
            "files": [item["relative_path"] for item in records],
            "duplicate_bytes": sum(int(item["bytes"]) for item in records[1:]),
        }
        for digest, records in sorted(hashes.items())
        if len(records) > 1
    ]
    candidate_categories = Counter(item["category"] for item in candidates)
    protected_reasons = Counter(item["reason"] for item in protected)
    potential_bytes = sum(int(item["bytes"]) for item in candidates)

    return {
        "schema_version": "1.0",
        "mode": "dry_run_only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "summary": {
            "candidate_files": len(candidates),
            "potential_savings_bytes": potential_bytes,
            "protected_files": len(protected),
            "duplicate_candidate_groups": len(duplicate_groups),
            "duplicate_candidate_bytes": sum(int(group["duplicate_bytes"]) for group in duplicate_groups),
            "candidate_categories": dict(sorted(candidate_categories.items())),
            "protected_reasons": dict(sorted(protected_reasons.items())),
        },
        "candidates": sorted(candidates, key=lambda item: (item["category"], item["relative_path"])),
        "duplicate_candidates": duplicate_groups,
        "protected_summary": sorted(protected, key=lambda item: item["relative_path"]),
        "exclusions": exclusions,
        "manual_review_required": [
            "Confirm each candidate is not referenced by an approved package, privacy evidence, or post-render QA.",
            "Review duplicate groups before choosing any retained copy; this report never selects one automatically.",
            "Obtain an explicit cleanup approval before any separate cleanup tool is considered.",
        ],
    }


def validate_report_path(root_dir: str | Path, report_path: str | Path) -> Path:
    """Reject report writes into protected/source/artifact scan directories."""
    root = Path(root_dir).resolve()
    report = Path(report_path).resolve()
    for protected_dir in (root / "reviews", root / "output", root / "scratch"):
        if _within(report, protected_dir):
            raise ValueError("REPORT_PATH_INSIDE_SCANNED_ARTIFACTS")
    return report
