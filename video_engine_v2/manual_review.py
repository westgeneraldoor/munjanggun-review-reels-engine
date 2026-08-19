"""Hash-bound human review receipts for voice, HTML, and final render evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


VOICE_REVIEW_CHECKS = frozenset({"pronunciation_clear", "tone_approved", "caption_sync_approved"})
HTML_REVIEW_CHECKS = frozenset(
    {
        "hook_sequence_reviewed",
        "meaning_sync_reviewed",
        "caption_layout_reviewed",
        "privacy_reviewed",
        "review_capture_reviewed",
        # 엔진은 캡처 이미지를 읽지 못한다. 밑줄이 인용한 그 줄 위에 실제로 놓였는지는
        # 대표 프레임을 본 사람만 확인할 수 있다.
        "review_underline_alignment_reviewed",
        "cta_reviewed",
    }
)
RENDER_REVIEW_CHECKS = frozenset(
    {
        "caption_layout_reviewed",
        "privacy_reviewed",
        "review_capture_reviewed",
        "voice_caption_visual_sync_reviewed",
        "hook_and_cta_reviewed",
    }
)


class ManualReviewViolation(ValueError):
    pass


def _inside(package: Path, target: str | Path, *, code: str) -> Path:
    package = package.resolve()
    path = Path(target).resolve()
    try:
        path.relative_to(package)
    except ValueError as error:
        raise ManualReviewViolation(code) from error
    return path


def _file_evidence(path: Path, package: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ManualReviewViolation("MANUAL_REVIEW_TARGET_MISSING")
    return {
        "relative_path": path.resolve().relative_to(package.resolve()).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _read_json(path: Path, *, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ManualReviewViolation(code) from error
    if not isinstance(value, dict):
        raise ManualReviewViolation(code)
    return value


def _base_receipt(
    *, package: Path, review_kind: str, reviewer: str, evidence_reference: str, checks: Iterable[str], required: frozenset[str]
) -> dict[str, Any]:
    supplied = list(checks)
    if set(supplied) != required or len(supplied) != len(required):
        raise ManualReviewViolation("MANUAL_REVIEW_CHECKS_INCOMPLETE")
    if not reviewer.strip() or not evidence_reference.strip():
        raise ManualReviewViolation("MANUAL_REVIEW_IDENTITY_MISSING")
    return {
        "schema_version": "review-reel-manual-review-v1",
        "review_kind": review_kind,
        "status": "passed",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_by": reviewer.strip(),
        "evidence_reference": evidence_reference.strip(),
        "package_identity": {
            "package_path": str(package.resolve()),
            "package_name": package.name,
        },
        "checks": sorted(required),
    }


def _write_receipt(package: Path, kind: str, receipt: dict[str, Any]) -> Path:
    directory = package / "_work" / "manual_reviews"
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = directory / f"{kind}_review_{timestamp}.json"
    if path.exists():
        raise ManualReviewViolation("MANUAL_REVIEW_RECEIPT_EXISTS")
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def record_voice_review(
    *, package_dir: str | Path, voice_path: str | Path, srt_path: str | Path, tts_report_path: str | Path,
    reviewer: str, evidence_reference: str, checks: Iterable[str],
) -> Path:
    package = Path(package_dir).resolve()
    receipt = _base_receipt(
        package=package, review_kind="voice", reviewer=reviewer, evidence_reference=evidence_reference,
        checks=checks, required=VOICE_REVIEW_CHECKS,
    )
    receipt["target"] = _file_evidence(_inside(package, voice_path, code="VOICE_REVIEW_TARGET_OUTSIDE_PACKAGE"), package)
    receipt["srt"] = _file_evidence(_inside(package, srt_path, code="VOICE_REVIEW_SRT_OUTSIDE_PACKAGE"), package)
    tts_report = _inside(package, tts_report_path, code="VOICE_REVIEW_REPORT_OUTSIDE_PACKAGE")
    _read_json(tts_report, code="VOICE_REVIEW_REPORT_INVALID")
    receipt["tts_report"] = _file_evidence(tts_report, package)
    return _write_receipt(package, "voice", receipt)


def record_html_review(
    *, package_dir: str | Path, html_path: str | Path, reviewer: str, evidence_reference: str,
    checks: Iterable[str],
) -> Path:
    package = Path(package_dir).resolve()
    html = _inside(package, html_path, code="HTML_REVIEW_TARGET_OUTSIDE_PACKAGE")
    preview = html.parent
    artifact = preview / "html_artifact_evidence.json"
    qa_report_path = preview / "html_internal_qa_report.json"
    qa_report = _read_json(qa_report_path, code="HTML_REVIEW_QA_REPORT_INVALID")
    if qa_report.get("automatic_status") != "pass":
        raise ManualReviewViolation("HTML_REVIEW_AUTOMATIC_QA_NOT_PASSED")
    receipt = _base_receipt(
        package=package, review_kind="html", reviewer=reviewer, evidence_reference=evidence_reference,
        checks=checks, required=HTML_REVIEW_CHECKS,
    )
    receipt["target"] = _file_evidence(html, package)
    receipt["artifact_evidence"] = _file_evidence(artifact, package)
    receipt["qa_report"] = _file_evidence(qa_report_path, package)
    frame_values = [
        item.get("frame_relative_path")
        for key in ("checks", "hook_sequence_checks")
        for item in qa_report.get(key, [])
        if isinstance(item, dict)
    ]
    if not frame_values or any(not isinstance(value, str) or not value.strip() for value in frame_values):
        raise ManualReviewViolation("HTML_REVIEW_QA_FRAMES_MISSING")
    frames: list[dict[str, Any]] = []
    for value in frame_values:
        frame = _inside(package, preview / value, code="HTML_REVIEW_FRAME_OUTSIDE_PACKAGE")
        frames.append(_file_evidence(frame, package))
    receipt["qa_frames"] = frames
    return _write_receipt(package, "html", receipt)


def record_render_review(
    *, package_dir: str | Path, mp4_path: str | Path, post_qa_report_path: str | Path,
    reviewer: str, evidence_reference: str, checks: Iterable[str],
) -> Path:
    package = Path(package_dir).resolve()
    mp4 = _inside(package, mp4_path, code="RENDER_REVIEW_TARGET_OUTSIDE_PACKAGE")
    report_path = _inside(package, post_qa_report_path, code="RENDER_REVIEW_REPORT_OUTSIDE_PACKAGE")
    report = _read_json(report_path, code="RENDER_REVIEW_REPORT_INVALID")
    target = _file_evidence(mp4, package)
    if (
        report.get("auto_status") != "pass"
        or report.get("mp4_relative_path") != target["relative_path"]
        or report.get("mp4_bytes") != target["bytes"]
        or report.get("mp4_sha256") != target["sha256"]
    ):
        raise ManualReviewViolation("RENDER_REVIEW_REPORT_TARGET_MISMATCH")
    receipt = _base_receipt(
        package=package, review_kind="render", reviewer=reviewer, evidence_reference=evidence_reference,
        checks=checks, required=RENDER_REVIEW_CHECKS,
    )
    receipt["target"] = target
    receipt["post_qa_report"] = _file_evidence(report_path, package)
    frames: list[dict[str, Any]] = []
    for item in report.get("representative_frames") or []:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ManualReviewViolation("RENDER_REVIEW_QA_FRAMES_MISSING")
        frame = _inside(package, item["path"], code="RENDER_REVIEW_FRAME_OUTSIDE_PACKAGE")
        frames.append(_file_evidence(frame, package))
    if not frames:
        raise ManualReviewViolation("RENDER_REVIEW_QA_FRAMES_MISSING")
    receipt["qa_frames"] = frames
    return _write_receipt(package, "render", receipt)
