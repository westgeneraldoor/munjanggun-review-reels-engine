"""Official hash-bound user approval recording for HTML preview and MP4 render scope."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Any


class ApprovalEvidenceViolation(ValueError):
    pass


_BOOLEAN_LINE = re.compile(
    r"^\s*-\s*(?P<key>photo_checked|pd_plan_approved|html_approved_by_user|mp4_allowed)\s*:\s*(?P<value>true|false)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inside(package: Path, target: str | Path, *, code: str) -> Path:
    path = Path(target).resolve()
    try:
        path.relative_to(package.resolve())
    except ValueError as error:
        raise ApprovalEvidenceViolation(code) from error
    return path


def _read_json(path: Path, *, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ApprovalEvidenceViolation(code) from error
    if not isinstance(value, dict):
        raise ApprovalEvidenceViolation(code)
    return value


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
            temporary.write(text)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _package_identity(package: Path) -> dict[str, str]:
    return {"package_path": str(package.resolve()), "package_name": package.name}


def _validate_identity(value: Any, package: Path, *, code: str) -> None:
    if value != _package_identity(package):
        raise ApprovalEvidenceViolation(code)


def _validate_file_evidence(package: Path, evidence: Any, *, code: str) -> Path:
    if not isinstance(evidence, dict):
        raise ApprovalEvidenceViolation(code)
    relative = evidence.get("relative_path")
    byte_count = evidence.get("bytes")
    digest = evidence.get("sha256")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ApprovalEvidenceViolation(code)
    path = _inside(package, package / relative, code=code)
    if (
        not path.is_file()
        or not isinstance(byte_count, int)
        or path.stat().st_size != byte_count
        or not isinstance(digest, str)
        or _sha256(path) != digest
    ):
        raise ApprovalEvidenceViolation(code)
    return path


def _validate_artifact(package: Path, html: Path) -> Path:
    artifact_path = html.parent / "html_artifact_evidence.json"
    artifact = _read_json(artifact_path, code="CURRENT_HTML_ARTIFACT_INVALID")
    _validate_identity(artifact.get("package_identity"), package, code="CURRENT_HTML_ARTIFACT_INVALID")
    relative_html = html.relative_to(package).as_posix()
    if artifact.get("html_relative_path") != relative_html or artifact.get("html_sha256") != _sha256(html):
        raise ApprovalEvidenceViolation("CURRENT_HTML_ARTIFACT_MISMATCH")
    return artifact_path


def _require_current_manual_html_review(package: Path, html: Path, artifact_path: Path) -> Path:
    review_dir = package / "_work" / "manual_reviews"
    for receipt_path in sorted(review_dir.glob("html_review_*.json"), reverse=True):
        try:
            receipt = _read_json(receipt_path, code="CURRENT_HTML_MANUAL_REVIEW_INVALID")
            _validate_identity(
                receipt.get("package_identity"), package, code="CURRENT_HTML_MANUAL_REVIEW_INVALID"
            )
            if receipt.get("review_kind") != "html" or receipt.get("status") != "passed":
                continue
            target = _validate_file_evidence(
                package, receipt.get("target"), code="CURRENT_HTML_MANUAL_REVIEW_INVALID"
            )
            artifact = _validate_file_evidence(
                package, receipt.get("artifact_evidence"), code="CURRENT_HTML_MANUAL_REVIEW_INVALID"
            )
            _validate_file_evidence(
                package, receipt.get("qa_report"), code="CURRENT_HTML_MANUAL_REVIEW_INVALID"
            )
            frames = receipt.get("qa_frames")
            if not isinstance(frames, list) or not frames:
                raise ApprovalEvidenceViolation("CURRENT_HTML_MANUAL_REVIEW_INVALID")
            for frame in frames:
                _validate_file_evidence(package, frame, code="CURRENT_HTML_MANUAL_REVIEW_INVALID")
            if target == html and artifact == artifact_path:
                return receipt_path
        except ApprovalEvidenceViolation:
            continue
    raise ApprovalEvidenceViolation("CURRENT_HTML_MANUAL_REVIEW_MISSING")


def _read_status(package: Path) -> dict[str, bool]:
    path = package / "STATUS.md"
    if not path.is_file():
        return {}
    return {
        match.group("key").lower(): match.group("value").lower() == "true"
        for match in _BOOLEAN_LINE.finditer(path.read_text(encoding="utf-8", errors="replace"))
    }


def _archive_current_log(package: Path, *, clock: datetime) -> None:
    current = package / "APPROVAL_LOG.md"
    if not current.is_file():
        return
    digest = _sha256(current)[:12]
    archive = package / "_work" / "approval_history" / (
        f"APPROVAL_LOG_{clock.strftime('%Y%m%dT%H%M%S%fZ')}_{digest}.md"
    )
    _atomic_write(archive, current.read_text(encoding="utf-8", errors="replace"))


def _write_live_state(
    package: Path,
    *,
    html_approved: bool,
    mp4_allowed: bool,
    approved_by: str,
    evidence_reference: str,
    clock: datetime,
) -> None:
    prior = _read_status(package)
    status = (
        f"- photo_checked: {str(prior.get('photo_checked', False)).lower()}\n"
        f"- pd_plan_approved: {str(prior.get('pd_plan_approved', False)).lower()}\n"
        f"- html_approved_by_user: {str(html_approved).lower()}\n"
        f"- mp4_allowed: {str(mp4_allowed).lower()}\n"
    )
    lines = []
    if prior.get("photo_checked"):
        lines.append("- approved: photo review recorded by official intake gate")
    if prior.get("pd_plan_approved"):
        lines.append("- approved_scope: PD planning approved")
    if html_approved:
        lines.append("- approved_scope: HTML preview approved")
    else:
        lines.append("- not_approved: HTML preview pending")
    if mp4_allowed:
        lines.append("- approved_scope: MP4 render approved")
    else:
        lines.append("- not_approved: MP4 render pending")
    lines.extend(
        [
            f"- approved_by: {approved_by.strip()}",
            f"- approved_at: {clock.isoformat()}",
            f"- approval_evidence_reference: {evidence_reference.strip()}",
        ]
    )
    _archive_current_log(package, clock=clock)
    _atomic_write(package / "STATUS.md", status)
    _atomic_write(package / "APPROVAL_LOG.md", "\n".join(lines) + "\n")


def _validate_identity_inputs(approved_by: str, evidence_reference: str) -> None:
    if not approved_by.strip() or not evidence_reference.strip():
        raise ApprovalEvidenceViolation("APPROVAL_IDENTITY_MISSING")


def record_html_approval(
    *,
    package_dir: str | Path,
    html_path: str | Path,
    approved_by: str,
    evidence_reference: str,
    now: datetime | None = None,
) -> Path:
    package = Path(package_dir).resolve()
    html = _inside(package, html_path, code="HTML_APPROVAL_TARGET_OUTSIDE_PACKAGE")
    if not html.is_file():
        raise ApprovalEvidenceViolation("CURRENT_HTML_MISSING")
    _validate_identity_inputs(approved_by, evidence_reference)
    artifact_path = _validate_artifact(package, html)
    manual_receipt = _require_current_manual_html_review(package, html, artifact_path)
    clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    payload = {
        "schema_version": "1.0",
        "package_identity": _package_identity(package),
        "html_relative_path": html.relative_to(package).as_posix(),
        "html_sha256": _sha256(html),
        "html_artifact_evidence_sha256": _sha256(artifact_path),
        "manual_html_review_relative_path": manual_receipt.relative_to(package).as_posix(),
        "manual_html_review_sha256": _sha256(manual_receipt),
        "approved_by_user": True,
        "approved_at": clock.isoformat(),
        "approved_by": approved_by.strip(),
        "approval_evidence_reference": evidence_reference.strip(),
    }
    approval_path = package / "HTML_APPROVAL.json"
    _atomic_write_json(approval_path, payload)
    _write_live_state(
        package,
        html_approved=True,
        mp4_allowed=False,
        approved_by=approved_by,
        evidence_reference=evidence_reference,
        clock=clock,
    )
    from video_engine_v2.current_artifacts import CurrentArtifactsViolation, record_current_artifacts

    try:
        record_current_artifacts(
            package,
            producer="approval_evidence.record_html_approval",
            artifacts={"html_approval": approval_path},
        )
    except CurrentArtifactsViolation as error:
        raise ApprovalEvidenceViolation(str(error)) from error
    return approval_path


def _require_current_html_approval(package: Path, html: Path) -> Path:
    approval_path = package / "HTML_APPROVAL.json"
    if not approval_path.is_file():
        raise ApprovalEvidenceViolation("CURRENT_HTML_APPROVAL_MISSING")
    approval = _read_json(approval_path, code="CURRENT_HTML_APPROVAL_INVALID")
    _validate_identity(approval.get("package_identity"), package, code="CURRENT_HTML_APPROVAL_INVALID")
    artifact_path = _validate_artifact(package, html)
    if (
        approval.get("approved_by_user") is not True
        or approval.get("html_relative_path") != html.relative_to(package).as_posix()
        or approval.get("html_sha256") != _sha256(html)
        or approval.get("html_artifact_evidence_sha256") != _sha256(artifact_path)
    ):
        raise ApprovalEvidenceViolation("CURRENT_HTML_APPROVAL_INVALID")
    return approval_path


def record_render_approval(
    *,
    package_dir: str | Path,
    html_path: str | Path,
    approved_by: str,
    evidence_reference: str,
    now: datetime | None = None,
) -> Path:
    package = Path(package_dir).resolve()
    html = _inside(package, html_path, code="RENDER_APPROVAL_TARGET_OUTSIDE_PACKAGE")
    _validate_identity_inputs(approved_by, evidence_reference)
    approval_path = _require_current_html_approval(package, html)
    clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    payload = {
        "schema_version": "review-reel-mp4-render-approval-v1",
        "package_identity": _package_identity(package),
        "html_relative_path": html.relative_to(package).as_posix(),
        "html_sha256": _sha256(html),
        "html_approval_relative_path": approval_path.relative_to(package).as_posix(),
        "html_approval_sha256": _sha256(approval_path),
        "approved_by_user": True,
        "approved_at": clock.isoformat(),
        "approved_by": approved_by.strip(),
        "approval_evidence_reference": evidence_reference.strip(),
    }
    render_approval = package / "MP4_RENDER_APPROVAL.json"
    _atomic_write_json(render_approval, payload)
    _write_live_state(
        package,
        html_approved=True,
        mp4_allowed=True,
        approved_by=approved_by,
        evidence_reference=evidence_reference,
        clock=clock,
    )
    from video_engine_v2.current_artifacts import CurrentArtifactsViolation, record_current_artifacts

    try:
        record_current_artifacts(
            package,
            producer="approval_evidence.record_render_approval",
            artifacts={"mp4_render_approval": render_approval},
        )
    except CurrentArtifactsViolation as error:
        raise ApprovalEvidenceViolation(str(error)) from error
    return render_approval
