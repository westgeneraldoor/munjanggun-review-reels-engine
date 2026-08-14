"""Read-only state mapping for review-video packages.

Legacy package contents are evidence, not permission to mutate the package.  This
module therefore only reads an output tree and returns a versioned state report.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from video_engine_v2.manual_review import RENDER_REVIEW_CHECKS


SCHEMA_VERSION = "1.0"
UNKNOWN = "unknown"
_PACKAGE_NAME = re.compile(r"^(?P<review_id>\d{1,5})(?:[_-]|$)")
_BOOLEAN_LINE = re.compile(r"(?mi)^[ \t]*-?[ \t]*(?P<key>[a-z0-9_]+)[ \t]*:[ \t]*(?P<value>true|false)[ \t]*$")
_APPROVAL_LINE = re.compile(r"(?mi)^[ \t]*-?[ \t]*(?P<key>approved_scope|not_approved)[ \t]*:[ \t]*(?P<value>.+?)[ \t]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_path(package_dir: Path, path: Path) -> str:
    return path.relative_to(package_dir).as_posix()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return content if isinstance(content, dict) else None


def _parse_boolean_fields(path: Path) -> dict[str, bool]:
    if not path.is_file():
        return {}
    values: dict[str, bool] = {}
    for match in _BOOLEAN_LINE.finditer(path.read_text(encoding="utf-8", errors="replace")):
        values[match.group("key").lower()] = match.group("value").lower() == "true"
    return values


def _parse_approval_fields(path: Path) -> dict[str, list[str]]:
    values = {"approved_scope": [], "not_approved": []}
    if not path.is_file():
        return values
    for match in _APPROVAL_LINE.finditer(path.read_text(encoding="utf-8", errors="replace")):
        values[match.group("key").lower()].append(match.group("value").strip())
    return values


def _approval_value(approval_fields: dict[str, list[str]], pattern: re.Pattern[str]) -> bool | str:
    if any(pattern.search(value) for value in approval_fields["not_approved"]):
        return False
    for scope in approval_fields["approved_scope"]:
        if pattern.search(scope) and not re.search(r"없음|none|not approved|미승인|보류|pending", scope, re.IGNORECASE):
            return True
    return UNKNOWN


def _reconcile_approval(
    *,
    field: str,
    status_value: bool | str,
    log_value: bool | str,
    conflicts: list[dict[str, Any]],
) -> bool | str:
    if log_value != UNKNOWN:
        if isinstance(status_value, bool) and status_value != log_value:
            conflicts.append(
                {
                    "field": field,
                    "status_value": status_value,
                    "approval_log_value": log_value,
                    "selected_evidence": "APPROVAL_LOG.md",
                }
            )
        return log_value
    return status_value


def _artifact_kind(path: Path) -> str | None:
    name = path.name.lower()
    parts = {part.lower() for part in path.parts}
    if name.endswith("_planning_recipe.json") or name == "planning_recipe.json":
        return "planning_recipe"
    if name.endswith("_edit_recipe.json") or name == "edit_recipe.json":
        return "edit_recipe"
    if name == "sync_manifest.json":
        return "sync_manifest"
    if name == "status.md":
        return "status"
    if name == "approval_log.md":
        return "approval_log"
    if name == "render_post_qa_report.json":
        return "post_render_qa"
    if "manual_reviews" in parts and name.startswith("voice_review_") and name.endswith(".json"):
        return "voice_manual_review"
    if "manual_reviews" in parts and name.startswith("html_review_") and name.endswith(".json"):
        return "html_manual_review"
    if "manual_reviews" in parts and name.startswith("render_review_") and name.endswith(".json"):
        return "render_manual_review"
    if name.endswith(".mp4") and "upload" in name:
        return "upload_mp4"
    if name.endswith("_script.md"):
        return "script"
    if name.endswith(".srt"):
        return "subtitle"
    if name.endswith("_voice.mp3"):
        return "voice"
    if name == "index.html" and any("html_preview" in part for part in parts):
        return "html_preview"
    if name in {"privacy_asset_manifest.json", "privacy_manifest.json"}:
        return "privacy_manifest"
    return None


def _artifact_records(package_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(path for path in package_dir.rglob("*") if path.is_file()):
        kind = _artifact_kind(path)
        if kind is None:
            continue
        records.append(
            {
                "kind": kind,
                "relative_path": _relative_path(package_dir, path),
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return records


def _find_direct_file(package_dir: Path, name: str) -> Path | None:
    path = package_dir / name
    return path if path.is_file() else None


def _infer_format(artifacts: list[dict[str, Any]]) -> tuple[str, str]:
    paths = " ".join(artifact["relative_path"].lower() for artifact in artifacts)
    if re.search(r"(?:v3[._-]?1|v31)", paths):
        return "v3.1", "experimental"
    if re.search(r"(?:^|[_./-])v3(?:[_./-]|$)", paths):
        return "v3", "experimental"
    if re.search(r"(?:^|[_./-])v2(?:[_./-]|$)", paths):
        return "v2", "production"
    if re.search(r"(?:^|[_./-])v1(?:[_./-]|$)", paths):
        return "v1", "archived"
    return "legacy", "archived"


def _package_is_candidate(path: Path) -> bool:
    if not path.is_dir() or not _PACKAGE_NAME.match(path.name):
        return False
    direct_names = {child.name.lower() for child in path.iterdir() if child.is_file()}
    if {".source", "status.md", "approval_log.md"} & direct_names:
        return True
    return any(
        name.endswith(("_script.md", "_planning_recipe.json", "_edit_recipe.json", ".mp4"))
        for name in direct_names
    )


def _package_dirs_at_output_boundary(output_root: Path) -> list[Path]:
    """Return package roots only, never nested render work directories."""
    candidates: list[Path] = []
    for child in output_root.iterdir():
        if _package_is_candidate(child):
            candidates.append(child)
            continue
        if not child.is_dir():
            continue
        candidates.extend(package for package in child.iterdir() if _package_is_candidate(package))
    return sorted(candidates)


def _current_evidence_matches(package_dir: Path, value: Any, *, expected_relative_path: str | None = None) -> bool:
    if not isinstance(value, dict):
        return False
    relative_path = value.get("relative_path")
    if (
        not isinstance(relative_path, str)
        or not relative_path.strip()
        or Path(relative_path).is_absolute()
        or (expected_relative_path is not None and relative_path != expected_relative_path)
        or not isinstance(value.get("bytes"), int)
        or value["bytes"] < 0
        or not isinstance(value.get("sha256"), str)
        or not _SHA256.fullmatch(value["sha256"])
    ):
        return False
    path = (package_dir / relative_path).resolve()
    try:
        path.relative_to(package_dir.resolve())
    except ValueError:
        return False
    return path.is_file() and path.stat().st_size == value["bytes"] and _sha256(path) == value["sha256"]


def _manual_qa_state(
    artifacts: list[dict[str, Any]], package_dir: Path, render_complete_mp4_relative_path: str | None
) -> bool | str:
    if render_complete_mp4_relative_path is None:
        return UNKNOWN
    upload_artifacts = {
        artifact["relative_path"]: artifact for artifact in artifacts if artifact["kind"] == "upload_mp4"
    }
    sync_manifest_artifacts = {
        artifact["relative_path"]: artifact for artifact in artifacts if artifact["kind"] == "sync_manifest"
    }
    for artifact in (item for item in artifacts if item["kind"] == "render_manual_review"):
        receipt = _read_json(package_dir / artifact["relative_path"])
        if (
            not receipt
            or receipt.get("schema_version") != "review-reel-manual-review-v1"
            or receipt.get("review_kind") != "render"
            or receipt.get("status") != "passed"
            or receipt.get("checks") != sorted(RENDER_REVIEW_CHECKS)
            or not isinstance(receipt.get("reviewed_at"), str)
            or not receipt["reviewed_at"].strip()
            or not isinstance(receipt.get("reviewed_by"), str)
            or not receipt["reviewed_by"].strip()
            or not isinstance(receipt.get("evidence_reference"), str)
            or not receipt["evidence_reference"].strip()
            or not _package_identity_matches(receipt.get("package_identity"), package_dir)
            or not _current_evidence_matches(
                package_dir, receipt.get("target"), expected_relative_path=render_complete_mp4_relative_path
            )
            or not _current_evidence_matches(package_dir, receipt.get("post_qa_report"))
        ):
            continue
        report_evidence = receipt["post_qa_report"]
        report_path = package_dir / report_evidence["relative_path"]
        report = _read_json(report_path)
        if not report or str(report.get("auto_status", "")).lower() != "pass":
            continue
        candidate_path, limitation = _validate_hash_bound_post_render_report(
            report,
            package_dir=package_dir,
            upload_artifacts=upload_artifacts,
            sync_manifest_artifacts=sync_manifest_artifacts,
        )
        if limitation or candidate_path != render_complete_mp4_relative_path:
            continue
        report_frames = report.get("representative_frames")
        receipt_frames = receipt.get("qa_frames")
        if not isinstance(report_frames, list) or not report_frames or not isinstance(receipt_frames, list):
            continue
        expected_frame_paths: list[str] = []
        valid_report_frames = True
        for item in report_frames:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                valid_report_frames = False
                break
            frame_path = Path(item["path"])
            if not frame_path.is_absolute():
                frame_path = package_dir / frame_path
            try:
                expected_frame_paths.append(frame_path.resolve().relative_to(package_dir.resolve()).as_posix())
            except ValueError:
                valid_report_frames = False
                break
        if not valid_report_frames or len(receipt_frames) != len(expected_frame_paths):
            continue
        if all(
            _current_evidence_matches(package_dir, evidence, expected_relative_path=relative_path)
            for evidence, relative_path in zip(receipt_frames, expected_frame_paths)
        ):
            return True
    return UNKNOWN


def _package_identity(package_dir: Path) -> dict[str, str]:
    package = package_dir.resolve()
    return {"package_path": str(package), "package_name": package.name}


def _package_identity_matches(value: Any, package_dir: Path) -> bool:
    if not isinstance(value, dict):
        return False
    expected = _package_identity(package_dir)
    package_path = value.get("package_path")
    package_name = value.get("package_name")
    if not isinstance(package_path, str) or not package_path or package_name != expected["package_name"]:
        return False
    try:
        return os.path.samefile(package_path, expected["package_path"])
    except OSError:
        return False


def _validate_hash_bound_post_render_report(
    payload: dict[str, Any],
    *,
    package_dir: Path,
    upload_artifacts: dict[str, dict[str, Any]],
    sync_manifest_artifacts: dict[str, dict[str, Any]],
) -> tuple[str | None, str | None]:
    """Return a bound upload path or one evidence-limitation code, without mutation."""
    if not isinstance(payload.get("mp4_sha256"), str) or not _SHA256.fullmatch(payload["mp4_sha256"]):
        return None, "legacy_report_missing_mp4_hash"
    identity = payload.get("package_identity")
    if not isinstance(identity, dict):
        return None, "post_render_qa_package_identity_missing"
    if not _package_identity_matches(identity, package_dir):
        return None, "post_render_qa_package_identity_mismatch"
    relative_path = payload.get("mp4_relative_path")
    if not isinstance(relative_path, str) or not relative_path.strip() or Path(relative_path).is_absolute():
        return None, "post_render_qa_mp4_outside_package"
    candidate = (package_dir / relative_path).resolve()
    try:
        normalized_relative_path = candidate.relative_to(package_dir.resolve()).as_posix()
    except ValueError:
        return None, "post_render_qa_mp4_outside_package"
    if not candidate.is_file():
        return None, "post_render_qa_mp4_missing"
    if not candidate.name.lower().endswith(".mp4") or "upload_10mbps" not in candidate.name.lower():
        return None, "post_render_qa_mp4_not_upload_artifact"
    if normalized_relative_path not in upload_artifacts:
        return None, "post_render_qa_mp4_not_upload_artifact"
    expected_bytes = payload.get("mp4_bytes")
    if not isinstance(expected_bytes, int) or expected_bytes < 0:
        return None, "post_render_qa_mp4_bytes_missing"
    if candidate.stat().st_size != expected_bytes:
        return None, "post_render_qa_mp4_bytes_mismatch"
    if _sha256(candidate) != payload["mp4_sha256"]:
        return None, "post_render_qa_mp4_hash_mismatch"
    artifact = upload_artifacts[normalized_relative_path]
    if artifact["bytes"] != expected_bytes or artifact["sha256"] != payload["mp4_sha256"]:
        return None, "post_render_qa_mp4_artifact_mismatch"

    sync_relative_path = payload.get("sync_manifest_relative_path")
    sync_expected_bytes = payload.get("sync_manifest_bytes")
    sync_expected_hash = payload.get("sync_manifest_sha256")
    if (
        not isinstance(sync_relative_path, str)
        or not sync_relative_path.strip()
        or Path(sync_relative_path).is_absolute()
        or not isinstance(sync_expected_bytes, int)
        or sync_expected_bytes < 0
        or not isinstance(sync_expected_hash, str)
        or not _SHA256.fullmatch(sync_expected_hash)
    ):
        return None, "post_render_qa_sync_manifest_binding_missing"
    sync_candidate = (package_dir / sync_relative_path).resolve()
    try:
        normalized_sync_relative_path = sync_candidate.relative_to(package_dir.resolve()).as_posix()
    except ValueError:
        return None, "post_render_qa_sync_manifest_outside_package"
    if not sync_candidate.is_file():
        return None, "post_render_qa_sync_manifest_missing"
    if normalized_sync_relative_path not in sync_manifest_artifacts:
        return None, "post_render_qa_sync_manifest_not_current_artifact"
    if sync_candidate.stat().st_size != sync_expected_bytes:
        return None, "post_render_qa_sync_manifest_bytes_mismatch"
    if _sha256(sync_candidate) != sync_expected_hash:
        return None, "post_render_qa_sync_manifest_hash_mismatch"
    sync_artifact = sync_manifest_artifacts[normalized_sync_relative_path]
    if sync_artifact["bytes"] != sync_expected_bytes or sync_artifact["sha256"] != sync_expected_hash:
        return None, "post_render_qa_sync_manifest_artifact_mismatch"
    return normalized_relative_path, None


def _post_render_qa_evidence_state(
    artifacts: list[dict[str, Any]], package_dir: Path
) -> tuple[bool | str, bool | str, str | None, list[str]]:
    """Separate historical auto-pass reports from current hash-bound completion."""
    upload_artifacts = {
        artifact["relative_path"]: artifact
        for artifact in artifacts
        if artifact["kind"] == "upload_mp4"
    }
    sync_manifest_artifacts = {
        artifact["relative_path"]: artifact
        for artifact in artifacts
        if artifact["kind"] == "sync_manifest"
    }
    historical_pass: bool | str = UNKNOWN
    bound_path: str | None = None
    limitations: list[str] = []
    for report in (artifact for artifact in artifacts if artifact["kind"] == "post_render_qa"):
        payload = _read_json(package_dir / report["relative_path"])
        if str((payload or {}).get("auto_status", "")).lower() != "pass":
            continue
        historical_pass = True
        if not payload:
            limitations.append("post_render_qa_report_invalid")
            continue
        candidate_path, limitation = _validate_hash_bound_post_render_report(
            payload,
            package_dir=package_dir,
            upload_artifacts=upload_artifacts,
            sync_manifest_artifacts=sync_manifest_artifacts,
        )
        if candidate_path is not None:
            bound_path = candidate_path
        elif limitation:
            limitations.append(limitation)
    return (True if bound_path is not None else UNKNOWN), historical_pass, bound_path, sorted(set(limitations))


def map_legacy_package(package_dir: Path, *, run_key: str | None = None) -> dict[str, Any]:
    """Map one existing package without modifying files inside it."""
    match = _PACKAGE_NAME.match(package_dir.name)
    if not match:
        raise ValueError(f"Not a numeric review package: {package_dir}")

    artifacts = _artifact_records(package_dir)
    artifact_kinds = {artifact["kind"] for artifact in artifacts}
    status_path = _find_direct_file(package_dir, "STATUS.md")
    approval_path = _find_direct_file(package_dir, "APPROVAL_LOG.md")
    sync_path = _find_direct_file(package_dir, "sync_manifest.json")
    status_fields = _parse_boolean_fields(status_path) if status_path else {}
    approval_fields = _parse_approval_fields(approval_path) if approval_path else {"approved_scope": [], "not_approved": []}
    conflicts: list[dict[str, Any]] = []

    html_log = _approval_value(approval_fields, re.compile(r"html|프리뷰|preview|studio", re.IGNORECASE))
    mp4_log = _approval_value(approval_fields, re.compile(r"mp4.*(?:렌더|render|승인|approved)|(?:렌더|render).*mp4", re.IGNORECASE))
    html_approved = _reconcile_approval(
        field="html_approved",
        status_value=status_fields.get("html_approved_by_user", UNKNOWN),
        log_value=html_log,
        conflicts=conflicts,
    )
    mp4_render_approved = _reconcile_approval(
        field="mp4_render_approved",
        status_value=status_fields.get("mp4_allowed", UNKNOWN),
        log_value=mp4_log,
        conflicts=conflicts,
    )

    sync_manifest = _read_json(sync_path) if sync_path else None
    sync_ok: bool | str = sync_manifest.get("ok") if isinstance(sync_manifest, dict) and isinstance(sync_manifest.get("ok"), bool) else UNKNOWN
    final_voice_duration = UNKNOWN
    if sync_manifest:
        audio = sync_manifest.get("audio") or {}
        duration = audio.get("final_voice_duration_sec", sync_manifest.get("final_voice_duration_sec"))
        if isinstance(duration, (int, float)) and duration > 0:
            final_voice_duration = duration

    format_version, format_status = _infer_format(artifacts)
    render_complete, post_render_qa_pass_evidence_present, render_complete_mp4_relative_path, render_evidence_limitations = (
        _post_render_qa_evidence_state(artifacts, package_dir)
    )
    qa_reviewed = _manual_qa_state(artifacts, package_dir, render_complete_mp4_relative_path)
    final_delivery_complete = True if render_complete is True and qa_reviewed is True else UNKNOWN
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "state_source": "legacy_read_only_scan",
        "review_id": match.group("review_id").zfill(3),
        "run_id": f"legacy:{hashlib.sha256((run_key or package_dir.name).encode('utf-8')).hexdigest()[:16]}",
        "format_version": format_version,
        "format_status": format_status,
        "channel_targets": ["instagram", "naver_clip"],
        "render_artifact_present": True if "upload_mp4" in artifact_kinds else UNKNOWN,
        "post_render_qa_pass_evidence_present": post_render_qa_pass_evidence_present,
        "render_complete": render_complete,
        "render_complete_mp4_relative_path": render_complete_mp4_relative_path or UNKNOWN,
        "render_evidence_limitations": render_evidence_limitations,
        "qa_reviewed": qa_reviewed,
        "final_delivery_complete": final_delivery_complete,
        "published": status_fields.get("published", UNKNOWN),
        "performance_observed": status_fields.get("performance_observed", UNKNOWN),
        "planning_approved": status_fields.get("pd_plan_approved", UNKNOWN),
        "html_approved": html_approved,
        "mp4_render_approved": mp4_render_approved,
        "privacy_checked": status_fields.get("photo_checked", UNKNOWN),
        "sync_ok": sync_ok,
        "final_voice_duration_sec": final_voice_duration,
        "artifacts": artifacts,
        "legacy_evidence_sources": [
            artifact["relative_path"]
            for artifact in artifacts
            if artifact["kind"] in {"status", "approval_log", "sync_manifest", "post_render_qa", "upload_mp4"}
        ],
        "conflicts": conflicts,
    }
    unresolved = [
        field
        for field in (
            "render_artifact_present",
            "post_render_qa_pass_evidence_present",
            "render_complete",
            "qa_reviewed",
            "final_delivery_complete",
            "published",
            "performance_observed",
            "planning_approved",
            "html_approved",
            "mp4_render_approved",
            "privacy_checked",
            "sync_ok",
        )
        if state[field] == UNKNOWN
    ]
    state["unresolved_fields"] = unresolved
    state["state_confidence"] = (
        "manual_required" if conflicts else "legacy_evidence_backed" if not unresolved else "legacy_partial"
    )
    return state


def scan_legacy_output(output_root: str | Path) -> dict[str, Any]:
    """Return a read-only, versioned mapping for numeric review packages."""
    root = Path(output_root).resolve()
    if not root.is_dir():
        raise ValueError(f"Output root does not exist: {root}")
    packages = [
        map_legacy_package(path, run_key=_relative_path(root, path))
        for path in _package_dirs_at_output_boundary(root)
    ]
    def count(field: str, value: bool | str) -> int:
        return sum(package[field] == value for package in packages)

    upload_mp4_artifact_count = sum(
        sum(artifact["kind"] == "upload_mp4" for artifact in package["artifacts"])
        for package in packages
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "legacy_review_package_state",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "field_definitions": {
            "render_artifact_present": "An upload-named MP4 artifact exists; this alone does not prove media integrity.",
            "render_complete": "True only when a retained post-render QA pass binds package identity, upload MP4, and sync manifest paths, bytes, and SHA-256 values to their current files; otherwise unknown.",
            "qa_reviewed": "True only when a separate human render-review receipt binds the current upload MP4, current post-render QA report, and every reviewed representative frame by bytes and SHA-256; otherwise unknown.",
            "final_delivery_complete": "True only when both render_complete and qa_reviewed are true for the same current upload MP4; otherwise unknown.",
            "post_render_qa_pass_evidence_present": "A retained report recorded auto_status=pass; this is historical evidence and does not prove the current MP4 bytes.",
            "render_evidence_limitations": "Why a historical post-render QA pass could not be bound to the current upload MP4 and sync manifest bytes and SHA-256 values.",
            "published": "Only explicit retained status evidence can set true or false; absence is unknown.",
            "performance_observed": "Only explicit retained status evidence can set true or false; absence is unknown.",
        },
        "packages": packages,
        "summary": {
            "package_count": len(packages),
            "distinct_review_count": len({package["review_id"] for package in packages}),
            "upload_mp4_package_count": count("render_artifact_present", True),
            "upload_mp4_artifact_count": upload_mp4_artifact_count,
            "post_render_qa_pass_evidence_package_count": count("post_render_qa_pass_evidence_present", True),
            "render_complete_true_count": count("render_complete", True),
            "render_complete_unknown_count": count("render_complete", UNKNOWN),
            "final_delivery_complete_true_count": count("final_delivery_complete", True),
            "final_delivery_complete_unknown_count": count("final_delivery_complete", UNKNOWN),
            "render_evidence_limitation_count": sum(bool(package["render_evidence_limitations"]) for package in packages),
            "published_known_true_count": count("published", True),
            "published_known_false_count": count("published", False),
            "published_unknown_count": count("published", UNKNOWN),
            "performance_known_true_count": count("performance_observed", True),
            "performance_known_false_count": count("performance_observed", False),
            "performance_unknown_count": count("performance_observed", UNKNOWN),
            "conflict_package_count": sum(bool(package["conflicts"]) for package in packages),
            "manual_review_required_count": sum(
                bool(package["unresolved_fields"]) or bool(package["conflicts"]) for package in packages
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only legacy review-package state scanner")
    parser.add_argument("--output-root", required=True, help="Existing output root to scan without modification")
    parser.add_argument("--report", help="Optional JSON report path outside the scanned output root")
    args = parser.parse_args()

    output_root = Path(args.output_root).resolve()
    report = scan_legacy_output(output_root)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if not args.report:
        print(rendered, end="")
        return 0

    report_path = Path(args.report).resolve()
    try:
        report_path.relative_to(output_root)
    except ValueError:
        pass
    else:
        raise ValueError("Report path must stay outside the scanned output root to preserve legacy packages.")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(rendered, encoding="utf-8")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
