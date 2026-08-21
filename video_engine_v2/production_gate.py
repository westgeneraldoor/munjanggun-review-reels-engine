"""Hard gates for the current v2 production review-reel path."""

from __future__ import annotations

from datetime import datetime, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote

from video_engine_v2.reels_qa import canonical_tts_input_sha256, build_sync_manifest, validate_html_preflight
from video_engine_v2.capture_verification import (
    verify_sanitized_asset,
    verify_underline_segments,
)
from video_engine_v2.manual_review import HTML_REVIEW_CHECKS, VOICE_REVIEW_CHECKS


FINAL_RENDER_PRESET = {
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "video_bitrate": "11000k",
    "maxrate": "12000k",
    "bufsize": "24000k",
    "audio_bitrate": "192k",
    "audio_sample_rate": 44100,
    "audio_channels": 2,
    "video_codec": "h264",
    "pixel_format": "yuv420p",
}

_BOOLEAN_LINE = re.compile(r"(?mi)^[ \t]*-?[ \t]*(?P<key>[a-z0-9_]+)[ \t]*:[ \t]*(?P<value>true|false)[ \t]*$")
_APPROVAL_LINE = re.compile(r"(?mi)^[ \t]*-?[ \t]*(?P<key>approved_scope|not_approved)[ \t]*:[ \t]*(?P<value>.+?)[ \t]*$")
_FINAL_FILENAME = re.compile(
    r"^.+_final_render_\d{8}(?:_attempt(?P<attempt>\d{2}))?_upload_10mbps\.mp4$",
    re.IGNORECASE,
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PRIVACY_INSPECTION_CATEGORIES = {"face", "vehicle_plate", "address", "family_photo"}
HTML_ARTIFACT_EVIDENCE_FILENAME = "html_artifact_evidence.json"
HTML_APPROVAL_EVIDENCE_FILENAME = "HTML_APPROVAL.json"
MP4_RENDER_APPROVAL_EVIDENCE_FILENAME = "MP4_RENDER_APPROVAL.json"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENGINE_FONT_RELATIVE_PATH = "nelnasamchae.ttf"
ENGINE_FONT_PATH = REPOSITORY_ROOT / DEFAULT_ENGINE_FONT_RELATIVE_PATH


class GateViolation(ValueError):
    """A production action was rejected before it could create an artifact."""

    def __init__(self, *codes: str):
        self.codes = tuple(codes)
        super().__init__(", ".join(self.codes))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, *, missing_code: str, invalid_code: str) -> dict[str, Any]:
    if not path.is_file():
        raise GateViolation(missing_code)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GateViolation(invalid_code) from error
    if not isinstance(payload, dict):
        raise GateViolation(invalid_code)
    return payload


def _ensure_inside(package_dir: Path, path: Path, *, outside_code: str) -> Path:
    package = package_dir.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(package)
    except ValueError as error:
        raise GateViolation(outside_code) from error
    return resolved


def _status_fields(package_dir: Path) -> dict[str, bool]:
    status_path = package_dir / "STATUS.md"
    if not status_path.is_file():
        return {}
    return {
        match.group("key").lower(): match.group("value").lower() == "true"
        for match in _BOOLEAN_LINE.finditer(status_path.read_text(encoding="utf-8", errors="replace"))
    }


def _approval_fields(package_dir: Path) -> dict[str, list[str]]:
    result = {"approved_scope": [], "not_approved": []}
    path = package_dir / "APPROVAL_LOG.md"
    if not path.is_file():
        return result
    for match in _APPROVAL_LINE.finditer(path.read_text(encoding="utf-8", errors="replace")):
        result[match.group("key").lower()].append(match.group("value").strip())
    return result


def _approved_scope(package_dir: Path, pattern: re.Pattern[str]) -> bool:
    fields = _approval_fields(package_dir)
    if any(pattern.search(value) for value in fields["not_approved"]):
        return False
    return any(
        pattern.search(value) and not re.search(r"없음|none|not approved|미승인|보류|pending", value, re.IGNORECASE)
        for value in fields["approved_scope"]
    )


def _require_pd_approval(package_dir: Path) -> None:
    status = _status_fields(package_dir)
    if status.get("pd_plan_approved") is not True or not _approved_scope(
        package_dir, re.compile(r"pd|planning|plan|기획", re.IGNORECASE)
    ):
        raise GateViolation("PD_APPROVAL_MISSING")


def validate_generation_gate(package_dir: str | Path, expected_source_key: str) -> None:
    """Require source-bound photo review and PD approval before script/SRT/TTS generation."""
    package = Path(package_dir).resolve()
    if not package.is_dir():
        raise GateViolation("GENERATION_APPROVAL_PACKAGE_MISSING")
    if not isinstance(expected_source_key, str) or not expected_source_key.strip():
        raise GateViolation("GENERATION_SOURCE_INVALID")
    source_path = package / ".source"
    if not source_path.is_file():
        raise GateViolation("GENERATION_SOURCE_MISSING")
    recorded_source = os.path.normcase(os.path.normpath(source_path.read_text(encoding="utf-8").strip()))
    expected_source = os.path.normcase(os.path.normpath(expected_source_key.strip()))
    if recorded_source != expected_source:
        raise GateViolation("GENERATION_SOURCE_MISMATCH")
    if _status_fields(package).get("photo_checked") is not True:
        raise GateViolation("PHOTO_REVIEW_MISSING")
    _require_pd_approval(package)


def _require_html_approval(package_dir: Path) -> None:
    status = _status_fields(package_dir)
    if status.get("html_approved_by_user") is not True or not _approved_scope(
        package_dir, re.compile(r"html|preview|studio|프리뷰", re.IGNORECASE)
    ):
        raise GateViolation("HTML_APPROVAL_MISSING")


def _require_mp4_approval(package_dir: Path) -> None:
    status = _status_fields(package_dir)
    if status.get("mp4_allowed") is not True or not _approved_scope(
        package_dir, re.compile(r"mp4.*(?:render|approved|승인|렌더)|(?:render|승인|렌더).*mp4", re.IGNORECASE)
    ):
        raise GateViolation("MP4_APPROVAL_MISSING")


def _package_identity(package_dir: Path) -> dict[str, str]:
    package = package_dir.resolve()
    return {"package_path": str(package), "package_name": package.name}


def _require_package_identity(
    value: Any,
    package_dir: Path,
    *,
    invalid_code: str,
    mismatch_code: str,
) -> None:
    if not isinstance(value, dict):
        raise GateViolation(invalid_code)
    expected = _package_identity(package_dir)
    if not all(isinstance(value.get(key), str) and value[key] for key in expected):
        raise GateViolation(invalid_code)
    if value["package_name"] != expected["package_name"]:
        raise GateViolation(mismatch_code)
    try:
        same_package = os.path.samefile(value["package_path"], expected["package_path"])
    except OSError:
        same_package = False
    if not same_package:
        raise GateViolation(mismatch_code)


def _require_sha256(value: Any, *, invalid_code: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise GateViolation(invalid_code)
    return value


def _current_file_evidence(package_dir: Path, path: Path) -> dict[str, Any]:
    target = _ensure_inside(package_dir, path, outside_code="MANUAL_REVIEW_EVIDENCE_INVALID")
    if not target.is_file():
        raise GateViolation("MANUAL_REVIEW_EVIDENCE_INVALID")
    return {
        "relative_path": target.relative_to(package_dir.resolve()).as_posix(),
        "bytes": target.stat().st_size,
        "sha256": _sha256(target),
    }


def _manual_receipts(package_dir: Path, review_kind: str) -> list[dict[str, Any]]:
    directory = package_dir / "_work" / "manual_reviews"
    receipts: list[dict[str, Any]] = []
    for path in sorted(directory.glob(f"{review_kind}_review_*.json")) if directory.is_dir() else []:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            receipts.append(payload)
    return receipts


def _manual_receipt_base_matches(
    receipt: dict[str, Any], package_dir: Path, *, review_kind: str, required_checks: frozenset[str]
) -> bool:
    identity = receipt.get("package_identity")
    if not isinstance(identity, dict) or identity.get("package_name") != package_dir.name:
        return False
    try:
        same_package = os.path.samefile(identity.get("package_path", ""), package_dir)
    except OSError:
        same_package = False
    return (
        same_package
        and receipt.get("schema_version") == "review-reel-manual-review-v1"
        and receipt.get("review_kind") == review_kind
        and receipt.get("status") == "passed"
        and receipt.get("checks") == sorted(required_checks)
        and isinstance(receipt.get("reviewed_by"), str)
        and bool(receipt["reviewed_by"].strip())
        and isinstance(receipt.get("evidence_reference"), str)
        and bool(receipt["evidence_reference"].strip())
    )


def _manual_review_candidates(package_dir: Path, *, kind: str, pattern: str) -> list[Path]:
    """Return only authoritative receipt candidates for the package mode.

    Legacy packages retain the historical directory scan. Ledger-enabled
    packages must ignore every receipt except the exact current pointer; an
    orphan written before a failed ledger update cannot become authority.
    """
    directory = package_dir / "_work" / "manual_reviews"
    from video_engine_v2.current_artifacts import (
        CurrentArtifactsViolation,
        package_uses_ledger,
        read_ledger,
    )

    if package_uses_ledger(package_dir):
        try:
            ledger = read_ledger(package_dir)
        except CurrentArtifactsViolation:
            return []
        pointer = (ledger.get("pointers") or {}).get(kind)
        if not isinstance(pointer, dict) or not isinstance(pointer.get("relative_path"), str):
            return []
        candidate = (package_dir / pointer["relative_path"]).resolve()
        try:
            candidate.relative_to(directory.resolve())
        except ValueError:
            return []
        return [candidate] if candidate.is_file() else []
    return sorted(directory.glob(pattern), reverse=True) if directory.is_dir() else []


def find_current_voice_manual_review(package_dir: Path, edit_recipe: dict[str, Any]) -> Path | None:
    """Return the official voice review receipt bound to the current edit inputs."""
    source = edit_recipe.get("source") or {}
    expected: dict[str, dict[str, Any]] = {}
    try:
        for receipt_field, source_field in (
            ("target", "voice"),
            ("srt", "srt"),
            ("tts_report", "tts_generation_report"),
        ):
            path, _ = _package_relative_file(
                package_dir,
                source.get(source_field),
                outside_code="VOICE_MANUAL_REVIEW_INVALID",
            )
            expected[receipt_field] = _current_file_evidence(package_dir, path)
    except GateViolation:
        return None
    for receipt_path in _manual_review_candidates(
        package_dir,
        kind="voice_manual_review",
        pattern="voice_review_*.json",
    ):
        receipt = _read_json_optional(receipt_path)
        if (
            receipt
            and _manual_receipt_base_matches(
                receipt, package_dir, review_kind="voice", required_checks=VOICE_REVIEW_CHECKS
            )
            and all(receipt.get(field) == evidence for field, evidence in expected.items())
        ):
            return receipt_path
    return None


def _require_voice_manual_review(package_dir: Path, edit_recipe: dict[str, Any]) -> None:
    if find_current_voice_manual_review(package_dir, edit_recipe) is not None:
        return
    if not _manual_receipts(package_dir, "voice"):
        raise GateViolation("VOICE_MANUAL_REVIEW_MISSING")
    raise GateViolation("VOICE_MANUAL_REVIEW_STALE_OR_INVALID")


def find_current_html_manual_review(package_dir: Path, html_path: Path) -> Path | None:
    """Return the official HTML review receipt bound to this preview, if any."""
    package = Path(package_dir).resolve()
    html = Path(html_path).resolve()
    artifact_path = html.parent / HTML_ARTIFACT_EVIDENCE_FILENAME
    qa_report_path = html.parent / "html_internal_qa_report.json"
    try:
        qa_report = _read_json(
            qa_report_path,
            missing_code="HTML_MANUAL_REVIEW_MISSING",
            invalid_code="HTML_MANUAL_REVIEW_STALE_OR_INVALID",
        )
        if qa_report.get("automatic_status") != "pass":
            return None
        expected = {
            "target": _current_file_evidence(package, html),
            "artifact_evidence": _current_file_evidence(package, artifact_path),
            "qa_report": _current_file_evidence(package, qa_report_path),
        }
        frame_paths: list[Path] = []
        for key in ("checks", "hook_sequence_checks"):
            values = qa_report.get(key)
            if not isinstance(values, list):
                return None
            for item in values:
                if not isinstance(item, dict) or not isinstance(item.get("frame_relative_path"), str):
                    return None
                frame_paths.append(html.parent / item["frame_relative_path"])
        if not frame_paths:
            return None
        expected_frames = [_current_file_evidence(package, path) for path in frame_paths]
    except GateViolation:
        return None
    for receipt_path in _manual_review_candidates(
        package,
        kind="html_manual_review",
        pattern="html_review_*.json",
    ):
        receipt = _read_json_optional(receipt_path)
        if (
            receipt
            and _manual_receipt_base_matches(
                receipt, package, review_kind="html", required_checks=HTML_REVIEW_CHECKS
            )
            and all(receipt.get(field) == evidence for field, evidence in expected.items())
            and receipt.get("qa_frames") == expected_frames
        ):
            return receipt_path
    return None


def _read_json_optional(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _require_html_manual_review(package_dir: Path, html_path: Path) -> None:
    if find_current_html_manual_review(package_dir, html_path) is not None:
        return
    if not _manual_receipts(package_dir, "html"):
        raise GateViolation("HTML_MANUAL_REVIEW_MISSING")
    raise GateViolation("HTML_MANUAL_REVIEW_STALE_OR_INVALID")


def _path_evidence(path: Path, *, kind: str, scope: str, relative_path: str) -> dict[str, Any]:
    if not path.is_file():
        raise GateViolation("RENDER_DEPENDENCY_MISSING")
    return {
        "kind": kind,
        "scope": scope,
        "relative_path": relative_path,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _package_relative_file(package_dir: Path, value: Any, *, outside_code: str) -> tuple[Path, str]:
    if not isinstance(value, str) or not value.strip() or Path(value).is_absolute():
        raise GateViolation(outside_code)
    path = _ensure_inside(package_dir, package_dir / value, outside_code=outside_code)
    return path, path.relative_to(package_dir.resolve()).as_posix()


def _repository_relative_file(value: Any, *, outside_code: str) -> tuple[Path, str]:
    repository = REPOSITORY_ROOT.resolve()
    if not isinstance(value, str) or not value.strip() or Path(value).is_absolute():
        raise GateViolation(outside_code)
    path = _ensure_inside(repository, repository / value, outside_code=outside_code)
    return path, path.relative_to(repository).as_posix()


def resolve_engine_font_path(value: str | Path | None = None) -> Path:
    """Resolve the default production font or a repository-contained injected font."""
    repository = REPOSITORY_ROOT.resolve()
    candidate = ENGINE_FONT_PATH if value is None else Path(value)
    if not candidate.is_absolute():
        candidate = repository / candidate
    return _ensure_inside(repository, candidate, outside_code="RENDER_DEPENDENCY_OUTSIDE_REPOSITORY")


def _asset_url(from_dir: Path, target: Path) -> str:
    return quote(Path(os.path.relpath(target.resolve(), from_dir.resolve())).as_posix(), safe="/._-()")


def _validate_selected_asset(package_dir: Path, item: Any) -> None:
    if not isinstance(item, dict):
        raise GateViolation("PRIVACY_EVIDENCE_INVALID")
    relative_path = item.get("relative_path")
    expected_bytes = item.get("bytes")
    expected_hash = item.get("sha256")
    if not isinstance(relative_path, str) or not isinstance(expected_bytes, int) or not isinstance(expected_hash, str):
        raise GateViolation("PRIVACY_EVIDENCE_INVALID")
    asset_path = _ensure_inside(package_dir, package_dir / relative_path, outside_code="PRIVACY_ASSET_OUTSIDE_PACKAGE")
    if not asset_path.is_file() or asset_path.stat().st_size != expected_bytes or _sha256(asset_path) != expected_hash:
        raise GateViolation("PRIVACY_ASSET_EVIDENCE_MISMATCH")


def _asset_evidence_map(items: Any, *, invalid_code: str) -> dict[str, tuple[int, str]]:
    if not isinstance(items, list) or not items:
        raise GateViolation(invalid_code)
    result: dict[str, tuple[int, str]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise GateViolation(invalid_code)
        relative_path = item.get("relative_path")
        byte_count = item.get("bytes")
        digest = item.get("sha256")
        if not isinstance(relative_path, str) or not relative_path or not isinstance(byte_count, int):
            raise GateViolation(invalid_code)
        digest = _require_sha256(digest, invalid_code=invalid_code)
        normalized = relative_path.replace("\\", "/")
        if normalized in result:
            raise GateViolation(invalid_code)
        result[normalized] = (byte_count, digest)
    return result


def _validate_privacy_report(package_dir: Path, manifest_path: Path, manifest: dict[str, Any]) -> None:
    report_value = manifest.get("sanitization_report")
    if not isinstance(report_value, str) or not report_value.strip():
        raise GateViolation("PRIVACY_REPORT_INVALID")
    report_path = _ensure_inside(package_dir, package_dir / report_value, outside_code="PRIVACY_REPORT_OUTSIDE_PACKAGE")
    if report_path == manifest_path:
        raise GateViolation("PRIVACY_REPORT_SELF_REFERENCE")
    report = _read_json(report_path, missing_code="PRIVACY_REPORT_MISSING", invalid_code="PRIVACY_REPORT_INVALID")
    if (
        not isinstance(report.get("schema_version"), str)
        or not report["schema_version"].strip()
        or not isinstance(report.get("checked_at"), str)
        or not report["checked_at"].strip()
    ):
        raise GateViolation("PRIVACY_REPORT_INVALID")
    checked = report.get("checked") is True or str(report.get("overall_status", "")).lower() in {"pass", "approved", "complete"}
    if not checked:
        raise GateViolation("PRIVACY_REPORT_INVALID")
    risks = report.get("unresolved_risks")
    if not isinstance(risks, list):
        raise GateViolation("PRIVACY_REPORT_INVALID")
    if risks:
        raise GateViolation("PRIVACY_RISK_UNRESOLVED")
    categories = report.get("inspection_categories")
    if not isinstance(categories, list) or not _PRIVACY_INSPECTION_CATEGORIES.issubset(
        {item for item in categories if isinstance(item, str)}
    ):
        raise GateViolation("PRIVACY_REPORT_INVALID")
    manifest_assets = _asset_evidence_map(manifest.get("selected_assets"), invalid_code="PRIVACY_EVIDENCE_INVALID")
    report_assets = _asset_evidence_map(report.get("checked_assets"), invalid_code="PRIVACY_REPORT_INVALID")
    if manifest_assets != report_assets:
        raise GateViolation("PRIVACY_REPORT_ASSET_MISMATCH")
    for item in report["checked_assets"]:
        try:
            _validate_selected_asset(package_dir, item)
        except GateViolation as error:
            raise GateViolation("PRIVACY_REPORT_ASSET_MISMATCH") from error


def _validate_privacy_manifest(package_dir: Path, privacy_manifest_path: Path) -> dict[str, Any]:
    path = _ensure_inside(package_dir, privacy_manifest_path, outside_code="PRIVACY_MANIFEST_OUTSIDE_PACKAGE")
    payload = _read_json(path, missing_code="PRIVACY_EVIDENCE_MISSING", invalid_code="PRIVACY_EVIDENCE_INVALID")
    checked_at = payload.get("checked_at")
    if (
        not isinstance(payload.get("schema_version"), str)
        or not payload["schema_version"].strip()
        or payload.get("checked") is not True
        or not isinstance(checked_at, str)
        or not checked_at.strip()
        or payload.get("unresolved_risks")
    ):
        raise GateViolation("PRIVACY_EVIDENCE_INVALID")
    selected_assets = payload.get("selected_assets")
    if not isinstance(selected_assets, list) or not selected_assets:
        raise GateViolation("PRIVACY_EVIDENCE_INVALID")
    for item in selected_assets:
        _validate_selected_asset(package_dir, item)
    _validate_privacy_report(package_dir, path, payload)
    return payload


def _validate_edit_assets(package_dir: Path, edit_recipe: dict[str, Any]) -> set[str]:
    source = edit_recipe.get("source") or {}
    roles = edit_recipe.get("asset_roles") or {}
    if not isinstance(source, dict) or not isinstance(roles, dict):
        raise GateViolation("ASSET_SET_MISSING")
    image_dir = source.get("image_dir")
    voice = source.get("voice")
    if not isinstance(image_dir, str) or not isinstance(voice, str) or not roles:
        raise GateViolation("ASSET_SET_MISSING")
    image_root = _ensure_inside(package_dir, package_dir / image_dir, outside_code="ASSET_OUTSIDE_PACKAGE")
    voice_path = _ensure_inside(package_dir, package_dir / voice, outside_code="ASSET_OUTSIDE_PACKAGE")
    if not image_root.is_dir() or not voice_path.is_file():
        raise GateViolation("ASSET_MISSING")
    used_assets: set[str] = set()
    for filename in roles.values():
        if not isinstance(filename, str):
            raise GateViolation("ASSET_SET_MISSING")
        asset_path = _ensure_inside(package_dir, image_root / filename, outside_code="ASSET_OUTSIDE_PACKAGE")
        if not asset_path.is_file():
            raise GateViolation("ASSET_MISSING")
        used_assets.add(asset_path.relative_to(package_dir).as_posix())
    return used_assets


def _voice_gate_input(package_dir: Path, edit_recipe: dict[str, Any]) -> dict[str, Any]:
    source = edit_recipe.get("source") or {}
    voice_value = source.get("voice") if isinstance(source, dict) else None
    voice_path, relative_voice = _package_relative_file(
        package_dir,
        voice_value,
        outside_code="ASSET_OUTSIDE_PACKAGE",
    )
    return _path_evidence(voice_path, kind="voice", scope="package", relative_path=relative_voice)


def _expected_render_dependencies(
    package_dir: Path,
    edit_recipe: dict[str, Any],
    html_path: Path,
    engine_font_path: str | Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    source = edit_recipe.get("source") or {}
    roles = edit_recipe.get("asset_roles") or {}
    if not isinstance(source, dict) or not isinstance(roles, dict) or not roles:
        raise GateViolation("RENDER_DEPENDENCY_INVALID")
    image_dir_value = source.get("image_dir")
    image_dir, _ = _package_relative_file(
        package_dir,
        image_dir_value,
        outside_code="RENDER_DEPENDENCY_OUTSIDE_PACKAGE",
    )
    if not image_dir.is_dir():
        raise GateViolation("RENDER_DEPENDENCY_MISSING")

    image_paths: dict[str, Path] = {}
    asset_urls: dict[str, str] = {}
    for role, filename in roles.items():
        if not isinstance(role, str) or not role or not isinstance(filename, str) or not filename:
            raise GateViolation("RENDER_DEPENDENCY_INVALID")
        image_path = _ensure_inside(
            package_dir,
            image_dir / filename,
            outside_code="RENDER_DEPENDENCY_OUTSIDE_PACKAGE",
        )
        if not image_path.is_file():
            raise GateViolation("RENDER_DEPENDENCY_MISSING")
        relative_image = image_path.relative_to(package_dir.resolve()).as_posix()
        image_paths[relative_image] = image_path
        asset_urls[role] = _asset_url(html_path.parent, image_path)

    voice = _voice_gate_input(package_dir, edit_recipe)
    voice_path, _ = _package_relative_file(
        package_dir,
        voice["relative_path"],
        outside_code="RENDER_DEPENDENCY_OUTSIDE_PACKAGE",
    )
    font_path = resolve_engine_font_path(engine_font_path)
    font_relative = font_path.relative_to(REPOSITORY_ROOT.resolve()).as_posix()

    asset_urls["voice"] = _asset_url(html_path.parent, voice_path)
    asset_urls["font_body"] = _asset_url(html_path.parent, font_path)
    dependencies = [
        *[
            _path_evidence(path, kind="image", scope="package", relative_path=relative_path)
            for relative_path, path in sorted(image_paths.items())
        ],
        voice,
        _path_evidence(font_path, kind="font", scope="repository", relative_path=font_relative),
    ]
    return dependencies, asset_urls


def _html_asset_urls(html_path: Path) -> dict[str, str]:
    try:
        html_text = html_path.read_text(encoding="utf-8")
    except OSError as error:
        raise GateViolation("HTML_MISSING") from error
    match = re.search(r"const assetUrls = (?P<asset_urls>[^\r\n]+);", html_text)
    if not match:
        raise GateViolation("RENDER_DEPENDENCY_HTML_MISMATCH")
    try:
        asset_urls = json.loads(match.group("asset_urls"))
    except json.JSONDecodeError as error:
        raise GateViolation("RENDER_DEPENDENCY_HTML_MISMATCH") from error
    if not isinstance(asset_urls, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in asset_urls.items()):
        raise GateViolation("RENDER_DEPENDENCY_HTML_MISMATCH")
    return asset_urls


def _dependency_map(items: Any, *, invalid_code: str) -> dict[tuple[str, str, str], tuple[int, str]]:
    if not isinstance(items, list) or not items:
        raise GateViolation(invalid_code)
    result: dict[tuple[str, str, str], tuple[int, str]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise GateViolation(invalid_code)
        kind = item.get("kind")
        scope = item.get("scope")
        relative_path = item.get("relative_path")
        byte_count = item.get("bytes")
        if (
            not isinstance(kind, str)
            or not kind
            or not isinstance(scope, str)
            or not scope
            or not isinstance(relative_path, str)
            or not relative_path
            or not isinstance(byte_count, int)
            or byte_count < 0
        ):
            raise GateViolation(invalid_code)
        digest = _require_sha256(item.get("sha256"), invalid_code=invalid_code)
        normalized_path = relative_path.replace("\\", "/")
        if Path(relative_path).is_absolute() or normalized_path.startswith("../"):
            raise GateViolation(invalid_code)
        key = (kind, scope, normalized_path)
        if key in result:
            raise GateViolation(invalid_code)
        result[key] = (byte_count, digest)
    return result


def _validate_render_dependency_binding(
    package_dir: Path,
    html_path: Path,
    edit_path: Path,
    engine_font_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    artifact_path = html_path.parent / HTML_ARTIFACT_EVIDENCE_FILENAME
    artifact = _read_json(
        artifact_path,
        missing_code="HTML_ARTIFACT_EVIDENCE_MISSING",
        invalid_code="HTML_ARTIFACT_EVIDENCE_INVALID",
    )
    edit_recipe = _read_json(edit_path, missing_code="EDIT_MISSING", invalid_code="EDIT_INVALID")
    expected, expected_asset_urls = _expected_render_dependencies(
        package_dir,
        edit_recipe,
        html_path,
        engine_font_path,
    )
    if _html_asset_urls(html_path) != expected_asset_urls:
        raise GateViolation("RENDER_DEPENDENCY_HTML_MISMATCH")
    recorded = artifact.get("render_dependencies")
    expected_map = _dependency_map(expected, invalid_code="RENDER_DEPENDENCY_INVALID")
    recorded_map = _dependency_map(recorded, invalid_code="RENDER_DEPENDENCY_INVALID")
    if recorded_map.keys() != expected_map.keys():
        raise GateViolation("RENDER_DEPENDENCY_SET_MISMATCH")
    for key, expected_value in expected_map.items():
        if recorded_map[key] != expected_value:
            raise GateViolation("RENDER_DEPENDENCY_MISMATCH")
    return expected


def _validate_privacy_asset_binding(used_assets: set[str], privacy_manifest: dict[str, Any]) -> None:
    inspected_assets = {
        item["relative_path"].replace("\\", "/")
        for item in privacy_manifest["selected_assets"]
        if isinstance(item, dict) and isinstance(item.get("relative_path"), str)
    }
    if used_assets != inspected_assets:
        raise GateViolation("PRIVACY_ASSET_SET_MISMATCH")


def _validate_edit_privacy_report_binding(package_dir: Path, edit_recipe: dict[str, Any], privacy_manifest: dict[str, Any]) -> None:
    source = edit_recipe.get("source") or {}
    declared_report = source.get("privacy_sanitization_report") if isinstance(source, dict) else None
    manifest_report = privacy_manifest.get("sanitization_report")
    if not isinstance(declared_report, str) or not isinstance(manifest_report, str):
        raise GateViolation("PRIVACY_REPORT_EDIT_MISMATCH")
    declared_path = _ensure_inside(package_dir, package_dir / declared_report, outside_code="PRIVACY_REPORT_EDIT_MISMATCH")
    manifest_path = _ensure_inside(package_dir, package_dir / manifest_report, outside_code="PRIVACY_REPORT_EDIT_MISMATCH")
    if declared_path != manifest_path:
        raise GateViolation("PRIVACY_REPORT_EDIT_MISMATCH")


def _original_image_root(package_dir: Path) -> Path | None:
    """사용자가 넣은 원본 사진 폴더.

    edit recipe의 `source.image_dir`은 `.`일 수 있어 기준이 되지 못한다. 원본과
    위생처리 산출물을 가르는 것은 canonical metadata가 지정한 이미지 폴더뿐이다.
    """
    metadata_path = package_dir / "CANONICAL_PACKAGE_METADATA.json"
    if not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    name = metadata.get("image_directory_name") if isinstance(metadata, dict) else None
    if not isinstance(name, str) or not name.strip():
        return None
    return _ensure_inside(package_dir, package_dir / name, outside_code="ASSET_OUTSIDE_PACKAGE")


def _asset_root(package_dir: Path, edit_recipe: dict[str, Any]) -> Path | None:
    source = edit_recipe.get("source") or {}
    image_dir = source.get("image_dir") if isinstance(source, dict) else None
    if not isinstance(image_dir, str) or not image_dir.strip():
        return None
    return _ensure_inside(package_dir, package_dir / image_dir, outside_code="ASSET_OUTSIDE_PACKAGE")


def _validate_sanitized_asset_pixels(package_dir: Path, privacy_manifest: dict[str, Any]) -> None:
    """마스킹했다는 선언을 픽셀로 확인한다.

    지금까지는 sanitization report가 파일 경로와 해시만 담았다. 파일 이름에
    `_masked`를 붙이고 아무것도 가리지 않아도 통과했다는 뜻이다. 원본 대비
    무엇이 실제로 달라졌는지를 봐야 그 선언이 증거가 된다.
    """

    report_value = privacy_manifest.get("sanitization_report")
    if not isinstance(report_value, str):
        return
    report_path = _ensure_inside(
        package_dir, package_dir / report_value, outside_code="PRIVACY_REPORT_OUTSIDE_PACKAGE"
    )
    report = _read_json(report_path, missing_code="PRIVACY_REPORT_MISSING", invalid_code="PRIVACY_REPORT_INVALID")

    declared = report.get("sanitized_assets")
    if declared is None:
        declared = []
    if not isinstance(declared, list):
        raise GateViolation("SANITIZED_ASSET_DECLARATION_INVALID")
    by_path = {}
    for item in declared:
        if not isinstance(item, dict) or not isinstance(item.get("relative_path"), str):
            raise GateViolation("SANITIZED_ASSET_DECLARATION_INVALID")
        by_path[item["relative_path"]] = item

    original_root = _original_image_root(package_dir)
    for item in report.get("checked_assets") or []:
        if not isinstance(item, dict):
            continue
        relative_path = item.get("relative_path")
        if not isinstance(relative_path, str):
            continue
        asset_path = _ensure_inside(
            package_dir, package_dir / relative_path, outside_code="PRIVACY_ASSET_OUTSIDE_PACKAGE"
        )
        # 원본 사진 폴더 밖에 있는 asset은 정의상 위생처리 산출물이다. 선언을 빠뜨려
        # 검증을 건너뛰는 것을 막는다.
        outside_image_dir = original_root is not None and original_root not in asset_path.parents
        declaration = by_path.get(relative_path)
        if declaration is None:
            if outside_image_dir:
                raise GateViolation("SANITIZED_ASSET_NOT_DECLARED")
            continue

        source_value = declaration.get("source_relative_path")
        regions = declaration.get("masked_regions")
        if not isinstance(source_value, str) or not isinstance(regions, list) or not regions:
            raise GateViolation("SANITIZED_ASSET_DECLARATION_INVALID")
        source_path = _ensure_inside(
            package_dir, package_dir / source_value, outside_code="PRIVACY_ASSET_OUTSIDE_PACKAGE"
        )
        if not source_path.is_file():
            raise GateViolation("SANITIZED_SOURCE_MISSING")
        violations = verify_sanitized_asset(source_path, asset_path, regions)
        if violations:
            raise GateViolation(violations[0])


def _validate_review_underline_pixels(package_dir: Path, edit_recipe: dict[str, Any]) -> None:
    """밑줄 좌표가 실제 글자 줄 아래에 놓였는지 캡처를 열어 확인한다."""

    beats = edit_recipe.get("beats")
    if not isinstance(beats, list):
        return
    review_beat = next(
        (
            beat
            for beat in beats
            if isinstance(beat, dict)
            and str(beat.get("narrative_role") or beat.get("phase") or "").strip() == "review_proof"
        ),
        None,
    )
    if review_beat is None:
        return
    emphasis = review_beat.get("review_emphasis")
    if not isinstance(emphasis, dict):
        return
    segments = emphasis.get("segments")
    if not isinstance(segments, list) or not segments:
        return

    image_root = _asset_root(package_dir, edit_recipe)
    roles = edit_recipe.get("asset_roles")
    if image_root is None or not isinstance(roles, dict):
        return
    asset_key = review_beat.get("asset_id") or review_beat.get("asset")
    filename = roles.get(asset_key) if isinstance(asset_key, str) else None
    if not isinstance(filename, str) or not filename.strip():
        return
    capture_path = _ensure_inside(
        package_dir, image_root / filename, outside_code="ASSET_OUTSIDE_PACKAGE"
    )
    if not capture_path.is_file():
        return
    violations = verify_underline_segments(capture_path, segments)
    if violations:
        raise GateViolation(violations[0])


def _validate_one_shot_audio_hashes(package_dir: Path, edit_recipe: dict[str, Any]) -> None:
    audio_plan = edit_recipe.get("audio_plan") or {}
    if not isinstance(audio_plan, dict):
        raise GateViolation("TTS_EVIDENCE_HASH_INVALID")
    declared_tts_hash = _require_sha256(audio_plan.get("tts_text_sha256"), invalid_code="TTS_EVIDENCE_HASH_INVALID")
    if declared_tts_hash != canonical_tts_input_sha256(edit_recipe):
        raise GateViolation("TTS_TEXT_HASH_MISMATCH")
    declared_voice_hash = _require_sha256(audio_plan.get("final_voice_sha256"), invalid_code="TTS_EVIDENCE_HASH_INVALID")
    if declared_voice_hash != _voice_gate_input(package_dir, edit_recipe)["sha256"]:
        raise GateViolation("FINAL_VOICE_HASH_MISMATCH")


def _validate_one_shot_package_state(
    package_dir: Path,
    planning_recipe: dict[str, Any],
    privacy_manifest_path: Path,
) -> None:
    metadata = _read_json(
        package_dir / "CANONICAL_PACKAGE_METADATA.json",
        missing_code="CANONICAL_PACKAGE_METADATA_MISSING",
        invalid_code="CANONICAL_PACKAGE_METADATA_INVALID",
    )
    if metadata.get("workflow") != "review_reel_production":
        raise GateViolation("CANONICAL_PACKAGE_METADATA_INVALID")
    content_id = planning_recipe.get("content_id")
    if not isinstance(content_id, str) or not content_id or metadata.get("content_id") != content_id:
        raise GateViolation("CANONICAL_PACKAGE_IDENTITY_MISMATCH")
    approvals = metadata.get("approvals") or {}
    if (
        metadata.get("lifecycle_state") not in {"photo_reviewed", "one_shot_ready"}
        or approvals.get("photo_checked") is not True
        or _status_fields(package_dir).get("photo_checked") is not True
    ):
        raise GateViolation("CANONICAL_PHOTO_REVIEW_STATE_INVALID")
    if approvals.get("mp4_scope_authorized") is not False:
        raise GateViolation("CANONICAL_MP4_SCOPE_INVALID")
    if approvals.get("html_scope_authorized") is not False:
        raise GateViolation("CANONICAL_HTML_SCOPE_INVALID")

    photo_review = metadata.get("photo_review")
    if not isinstance(photo_review, dict):
        raise GateViolation("CANONICAL_PHOTO_REVIEW_EVIDENCE_MISSING")
    bound_paths: dict[str, Path] = {}
    for field in ("selection", "privacy_manifest"):
        evidence = photo_review.get(field)
        if not isinstance(evidence, dict):
            raise GateViolation("CANONICAL_PHOTO_REVIEW_EVIDENCE_INVALID")
        value = evidence.get("relative_path")
        path, relative_path = _package_relative_file(
            package_dir,
            value,
            outside_code="CANONICAL_PHOTO_REVIEW_EVIDENCE_INVALID",
        )
        if (
            evidence.get("bytes") != path.stat().st_size
            or _require_sha256(
                evidence.get("sha256"),
                invalid_code="CANONICAL_PHOTO_REVIEW_EVIDENCE_INVALID",
            )
            != _sha256(path)
        ):
            raise GateViolation("CANONICAL_PHOTO_REVIEW_EVIDENCE_STALE")
        bound_paths[field] = path
    if bound_paths["privacy_manifest"] != privacy_manifest_path.resolve():
        raise GateViolation("CANONICAL_PRIVACY_MANIFEST_MISMATCH")
    selection = _read_json(
        bound_paths["selection"],
        missing_code="CANONICAL_PHOTO_REVIEW_EVIDENCE_MISSING",
        invalid_code="CANONICAL_PHOTO_REVIEW_EVIDENCE_INVALID",
    )
    if (
        selection.get("schema_version") != "review-reel-photo-selection-v2"
        or selection.get("content_id") != content_id
        or selection.get("unresolved_items") != []
        or not isinstance(selection.get("decisions"), list)
        or not selection["decisions"]
    ):
        raise GateViolation("CANONICAL_PHOTO_REVIEW_EVIDENCE_INVALID")

    metadata_source = metadata.get("review_source") or {}
    planning_source = planning_recipe.get("review_source") or {}
    metadata_hash = metadata_source.get("text_sha256")
    planning_hash = planning_source.get("canonical_text_sha256")
    if (
        not isinstance(metadata_hash, str)
        or not _SHA256.fullmatch(metadata_hash)
        or planning_hash != metadata_hash
    ):
        raise GateViolation("CANONICAL_REVIEW_SOURCE_MISMATCH")


def _validate_one_shot_tts_provenance(package_dir: Path, edit_recipe: dict[str, Any]) -> None:
    source = edit_recipe.get("source") or {}
    if not isinstance(source, dict):
        raise GateViolation("TTS_PROVENANCE_MISSING")

    source_paths: dict[str, Path] = {}
    for field, suffix, code in (
        ("script", "_script.md", "SCRIPT_ARTIFACT_INVALID"),
        ("srt", ".srt", "SRT_ARTIFACT_INVALID"),
    ):
        value = source.get(field)
        path, relative_path = _package_relative_file(package_dir, value, outside_code=code)
        if not relative_path.lower().endswith(suffix) or not path.is_file():
            raise GateViolation(code)
        source_paths[field] = path

    report_value = source.get("tts_generation_report")
    report_path, _ = _package_relative_file(
        package_dir,
        report_value,
        outside_code="TTS_PROVENANCE_MISSING",
    )
    report = _read_json(
        report_path,
        missing_code="TTS_PROVENANCE_MISSING",
        invalid_code="TTS_PROVENANCE_INVALID",
    )
    model = report.get("model")
    if (
        report.get("schema_version") != "review-reel-tts-generation-report-v1"
        or report.get("provider") != "google_gemini_tts"
        or not isinstance(model, str)
        or not model.startswith("gemini-")
        or "tts" not in model
        or report.get("voice") != "Sulafat"
    ):
        raise GateViolation("TTS_PROVENANCE_NOT_APPROVED")

    audio_plan = edit_recipe.get("audio_plan") or {}
    sync_policy = audio_plan.get("sync_policy") or {}
    voice_evidence = _voice_gate_input(package_dir, edit_recipe)
    expected = {
        "tts_text_sha256": audio_plan.get("tts_text_sha256"),
        "voice_relative_path": voice_evidence["relative_path"],
        "voice_bytes": voice_evidence["bytes"],
        "voice_sha256": voice_evidence["sha256"],
        "raw_tts_duration_sec": sync_policy.get("raw_tts_duration_sec"),
        "final_voice_duration_sec": sync_policy.get("final_voice_duration_sec"),
    }
    if any(report.get(key) != value for key, value in expected.items()):
        raise GateViolation("TTS_PROVENANCE_STALE")
    if report.get("caption_timeline_schema") != "review-reel-voice-caption-timeline-v1":
        raise GateViolation("VOICE_CAPTION_TIMELINE_INVALID")
    edit_relative = report.get("edit_recipe_relative_path")
    edit_path, _ = _package_relative_file(
        package_dir,
        edit_relative,
        outside_code="VOICE_CAPTION_TIMELINE_INVALID",
    )
    if report.get("edit_recipe_sha256") != _sha256(edit_path):
        raise GateViolation("BOUND_RECIPE_MODIFIED")
    expected_timeline = []
    for beat in edit_recipe.get("beats") or []:
        if not isinstance(beat, dict):
            raise GateViolation("VOICE_CAPTION_TIMELINE_INVALID")
        for index, chunk in enumerate(beat.get("caption_chunks") or [], start=1):
            if not isinstance(chunk, dict):
                raise GateViolation("VOICE_CAPTION_TIMELINE_INVALID")
            expected_timeline.append(
                {
                    "beat_id": str(beat.get("id") or ""),
                    "chunk_index": index,
                    "start_sec": chunk.get("start_sec"),
                    "end_sec": chunk.get("end_sec"),
                    "text": str(chunk.get("text") or "").strip(),
                    "display_text": str(chunk.get("display_text") or chunk.get("text") or "").strip(),
                }
            )
    if not expected_timeline or report.get("caption_timeline") != expected_timeline:
        raise GateViolation("VOICE_CAPTION_TIMELINE_STALE")
    srt_text = source_paths["srt"].read_text(encoding="utf-8-sig")
    for item in expected_timeline:
        start_ms = int(round(float(item["start_sec"]) * 1000))
        end_ms = int(round(float(item["end_sec"]) * 1000))
        def stamp(value: int) -> str:
            hours, remainder = divmod(value, 3_600_000)
            minutes, remainder = divmod(remainder, 60_000)
            seconds, millis = divmod(remainder, 1000)
            return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"
        if f"{stamp(start_ms)} --> {stamp(end_ms)}\n{item['display_text']}" not in srt_text:
            raise GateViolation("VOICE_CAPTION_TIMELINE_STALE")


def _load_recipes(package_dir: Path, planning_path: Path, edit_path: Path) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    planning = _ensure_inside(package_dir, planning_path, outside_code="PLANNING_OUTSIDE_PACKAGE")
    edit = _ensure_inside(package_dir, edit_path, outside_code="EDIT_OUTSIDE_PACKAGE")
    planning_recipe = _read_json(planning, missing_code="PLANNING_MISSING", invalid_code="PLANNING_INVALID")
    edit_recipe = _read_json(edit, missing_code="EDIT_MISSING", invalid_code="EDIT_INVALID")
    return planning, edit, planning_recipe, edit_recipe


def _validate_preflight(
    package_dir: Path,
    planning_path: Path,
    edit_path: Path,
    privacy_manifest_path: Path,
    *,
    allow_one_shot_html_contract: bool = False,
) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    planning, edit, planning_recipe, edit_recipe = _load_recipes(package_dir, planning_path, edit_path)
    if allow_one_shot_html_contract:
        if _status_fields(package_dir).get("photo_checked") is not True:
            raise GateViolation("PHOTO_REVIEW_MISSING")
    else:
        _require_pd_approval(package_dir)
    privacy_manifest = _validate_privacy_manifest(package_dir, privacy_manifest_path)
    _validate_privacy_asset_binding(_validate_edit_assets(package_dir, edit_recipe), privacy_manifest)
    _validate_edit_privacy_report_binding(package_dir, edit_recipe, privacy_manifest)
    _validate_sanitized_asset_pixels(package_dir, privacy_manifest)
    _validate_review_underline_pixels(package_dir, edit_recipe)
    result = validate_html_preflight(
        planning_recipe,
        edit_recipe,
        require_one_shot_contract=allow_one_shot_html_contract,
    )
    if not result["ok"]:
        raise GateViolation("REELS_QA_FAILED")
    if allow_one_shot_html_contract:
        _validate_one_shot_package_state(package_dir, planning_recipe, privacy_manifest_path)
        _validate_one_shot_audio_hashes(package_dir, edit_recipe)
        _validate_one_shot_tts_provenance(package_dir, edit_recipe)
        _require_voice_manual_review(package_dir, edit_recipe)
    return planning, edit, planning_recipe, edit_recipe


def _validate_sync_manifest(
    package_dir: Path,
    sync_manifest_path: Path,
    planning_path: Path,
    edit_path: Path,
    privacy_manifest_path: Path,
    *,
    expected_one_shot_html_contract: bool | None = None,
) -> dict[str, Any]:
    path = _ensure_inside(package_dir, sync_manifest_path, outside_code="SYNC_MANIFEST_OUTSIDE_PACKAGE")
    payload = _read_json(path, missing_code="SYNC_MANIFEST_MISSING", invalid_code="SYNC_MANIFEST_INVALID")
    if payload.get("ok") is not True or payload.get("issues"):
        raise GateViolation("SYNC_MANIFEST_NOT_OK")
    gate_inputs = payload.get("gate_inputs") or {}
    expected = {
        "planning_sha256": _sha256(planning_path),
        "edit_sha256": _sha256(edit_path),
        "privacy_manifest_sha256": _sha256(privacy_manifest_path),
    }
    if any(gate_inputs.get(key) != value for key, value in expected.items()):
        raise GateViolation("SYNC_MANIFEST_STALE_OR_UNVERIFIED")
    if (
        expected_one_shot_html_contract is not None
        and bool(gate_inputs.get("one_shot_html_contract")) is not expected_one_shot_html_contract
    ):
        raise GateViolation("SYNC_MANIFEST_STALE_OR_UNVERIFIED")
    edit_recipe = _read_json(edit_path, missing_code="EDIT_MISSING", invalid_code="EDIT_INVALID")
    if gate_inputs.get("voice") != _voice_gate_input(package_dir, edit_recipe):
        raise GateViolation("SYNC_MANIFEST_STALE_OR_UNVERIFIED")
    audio = payload.get("audio") or {}
    duration = audio.get("final_voice_duration_sec", payload.get("final_voice_duration_sec"))
    total_cps = audio.get("total_voice_cps", payload.get("total_voice_cps"))
    if not isinstance(duration, (int, float)) or duration <= 0 or not isinstance(total_cps, (int, float)) or total_cps >= 9.0:
        raise GateViolation("SYNC_MANIFEST_AUDIO_INVALID")
    scenes = payload.get("scenes") or payload.get("beats") or []
    if not isinstance(scenes, list) or not scenes:
        raise GateViolation("SYNC_MANIFEST_MEANING_MISSING")
    for scene in scenes:
        if not isinstance(scene, dict) or scene.get("meaning_match") is not True or not (
            scene.get("meaning_match_evidence") or scene.get("meaning_match_source")
        ):
            raise GateViolation("SYNC_MANIFEST_MEANING_MISSING")
    return payload


def create_sync_manifest(
    *,
    package_dir: str | Path,
    planning_path: str | Path,
    edit_path: str | Path,
    privacy_manifest_path: str | Path,
    sync_manifest_path: str | Path,
    allow_one_shot_html_contract: bool = False,
) -> dict[str, Any]:
    """Run preflight and atomically create a verified manifest without overwriting one."""
    package = Path(package_dir).resolve()
    planning, edit, _, edit_recipe = _validate_preflight(
        package,
        Path(planning_path),
        Path(edit_path),
        Path(privacy_manifest_path),
        allow_one_shot_html_contract=allow_one_shot_html_contract,
    )
    current_inputs: dict[str, Path] = {"privacy_manifest": Path(privacy_manifest_path).resolve()}
    if allow_one_shot_html_contract:
        source = edit_recipe.get("source") or {}
        script_path, _ = _package_relative_file(package, source.get("script"), outside_code="SCRIPT_OUTSIDE_PACKAGE")
        captions_path, _ = _package_relative_file(package, source.get("srt"), outside_code="SRT_OUTSIDE_PACKAGE")
        voice_path, _ = _package_relative_file(package, source.get("voice"), outside_code="VOICE_OUTSIDE_PACKAGE")
        tts_report_path, _ = _package_relative_file(
            package,
            source.get("tts_generation_report"),
            outside_code="TTS_REPORT_OUTSIDE_PACKAGE",
        )
        voice_review_path = find_current_voice_manual_review(package, edit_recipe)
        if voice_review_path is None:
            raise GateViolation("VOICE_MANUAL_REVIEW_STALE_OR_INVALID")
        current_inputs.update(
            {
                "script": script_path,
                "captions": captions_path,
                "voice": voice_path,
                "tts_report": tts_report_path,
                "voice_manual_review": voice_review_path,
            }
        )
    _require_ledger_current_paths(package, current_inputs)
    sync_path = _ensure_inside(package, Path(sync_manifest_path), outside_code="SYNC_MANIFEST_OUTSIDE_PACKAGE")
    if sync_path.exists():
        raise GateViolation("SYNC_MANIFEST_EXISTS")
    audio_plan = edit_recipe.get("audio_plan") or {}
    sync_policy = audio_plan.get("sync_policy") or {}
    raw_duration = sync_policy.get("raw_tts_duration_sec")
    final_duration = sync_policy.get("final_voice_duration_sec")
    manifest = build_sync_manifest(edit_recipe, raw_tts_duration_sec=raw_duration, final_voice_duration_sec=final_duration)
    if manifest.get("ok") is not True:
        raise GateViolation("REELS_QA_FAILED")
    manifest["gate_inputs"] = {
        "planning_path": str(planning),
        "edit_path": str(edit),
        "planning_sha256": _sha256(planning),
        "edit_sha256": _sha256(edit),
        "privacy_manifest_sha256": _sha256(Path(privacy_manifest_path)),
        "voice": _voice_gate_input(package, edit_recipe),
        "one_shot_html_contract": allow_one_shot_html_contract,
    }
    try:
        with sync_path.open("x", encoding="utf-8") as output:
            json.dump(manifest, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except FileExistsError as error:
        raise GateViolation("SYNC_MANIFEST_EXISTS") from error
    from video_engine_v2.current_artifacts import CurrentArtifactsViolation, record_current_artifacts

    try:
        record_current_artifacts(
            package,
            producer="production_gate.create_sync_manifest",
            artifacts={
                "sync_manifest": sync_path,
                "planning_recipe": planning,
                "edit_recipe": edit,
            },
        )
    except CurrentArtifactsViolation as error:
        raise GateViolation(str(error)) from error
    return manifest


def validate_html_gate(
    *,
    package_dir: str | Path,
    planning_path: str | Path,
    edit_path: str | Path,
    privacy_manifest_path: str | Path,
    sync_manifest_path: str | Path,
    allow_one_shot_html_contract: bool = False,
) -> dict[str, Any]:
    """Validate all HTML gates without creating an HTML preview."""
    package = Path(package_dir).resolve()
    planning, edit, _, _ = _validate_preflight(
        package,
        Path(planning_path),
        Path(edit_path),
        Path(privacy_manifest_path),
        allow_one_shot_html_contract=allow_one_shot_html_contract,
    )
    _validate_sync_manifest(
        package,
        Path(sync_manifest_path),
        planning,
        edit,
        Path(privacy_manifest_path),
        expected_one_shot_html_contract=allow_one_shot_html_contract,
    )
    _require_ledger_current_paths(
        package,
        {
            "planning_recipe": planning,
            "edit_recipe": edit,
            "privacy_manifest": Path(privacy_manifest_path).resolve(),
            "sync_manifest": Path(sync_manifest_path).resolve(),
        },
    )
    return {
        "schema_version": "1.0",
        "action": "html",
        "package_path": str(package),
        "recipe_path": str(edit),
        "recipe_sha256": _sha256(edit),
        "sync_manifest_path": str(Path(sync_manifest_path).resolve()),
        "sync_manifest_sha256": _sha256(Path(sync_manifest_path)),
        "one_shot_html_contract": allow_one_shot_html_contract,
    }


def write_html_artifact_evidence(
    *,
    package_dir: str | Path,
    html_path: str | Path,
    html_gate_receipt_path: str | Path,
    engine_font_path: str | Path | None = None,
) -> Path:
    """Bind an exactly generated HTML artifact to its non-overwriting HTML gate receipt."""
    package = Path(package_dir).resolve()
    html = _ensure_inside(package, Path(html_path), outside_code="HTML_OUTSIDE_PACKAGE")
    if not html.is_file():
        raise GateViolation("HTML_MISSING")
    receipt_path = _ensure_inside(package, Path(html_gate_receipt_path), outside_code="HTML_GATE_RECEIPT_OUTSIDE_PACKAGE")
    receipt = _read_json(receipt_path, missing_code="HTML_GATE_RECEIPT_MISSING", invalid_code="HTML_GATE_RECEIPT_INVALID")
    if receipt.get("action") != "html" or receipt.get("package_path") != str(package):
        raise GateViolation("HTML_GATE_RECEIPT_INVALID")
    recipe_value = receipt.get("recipe_path")
    if not isinstance(recipe_value, str) or not recipe_value:
        raise GateViolation("HTML_GATE_RECEIPT_INVALID")
    recipe_path = _ensure_inside(package, Path(recipe_value), outside_code="HTML_GATE_RECEIPT_INVALID")
    if _require_sha256(receipt.get("recipe_sha256"), invalid_code="HTML_GATE_RECEIPT_INVALID") != _sha256(recipe_path):
        raise GateViolation("HTML_GATE_RECEIPT_INVALID")
    edit_recipe = _read_json(recipe_path, missing_code="EDIT_MISSING", invalid_code="EDIT_INVALID")
    render_dependencies, expected_asset_urls = _expected_render_dependencies(
        package,
        edit_recipe,
        html,
        engine_font_path,
    )
    if _html_asset_urls(html) != expected_asset_urls:
        raise GateViolation("RENDER_DEPENDENCY_HTML_MISMATCH")
    evidence_path = html.parent / HTML_ARTIFACT_EVIDENCE_FILENAME
    if evidence_path.exists():
        raise GateViolation("HTML_ARTIFACT_EVIDENCE_EXISTS")
    evidence = {
        "schema_version": "1.0",
        "package_identity": _package_identity(package),
        "html_relative_path": html.relative_to(package).as_posix(),
        "html_sha256": _sha256(html),
        "html_gate_receipt_path": receipt_path.relative_to(package).as_posix(),
        "html_gate_receipt_sha256": _sha256(receipt_path),
        "render_dependencies": render_dependencies,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    with evidence_path.open("x", encoding="utf-8") as output:
        json.dump(evidence, output, ensure_ascii=False, indent=2)
        output.write("\n")
    return evidence_path


def _validate_html_approval_binding(package_dir: Path, html_path: Path) -> dict[str, str]:
    package = package_dir.resolve()
    html = _ensure_inside(package, html_path, outside_code="HTML_OUTSIDE_PACKAGE")
    current_hash = _sha256(html)
    relative_html = html.relative_to(package).as_posix()
    artifact_path = html.parent / HTML_ARTIFACT_EVIDENCE_FILENAME
    artifact = _read_json(
        artifact_path,
        missing_code="HTML_ARTIFACT_EVIDENCE_MISSING",
        invalid_code="HTML_ARTIFACT_EVIDENCE_INVALID",
    )
    _require_package_identity(
        artifact.get("package_identity"),
        package,
        invalid_code="HTML_ARTIFACT_EVIDENCE_INVALID",
        mismatch_code="HTML_ARTIFACT_PACKAGE_MISMATCH",
    )
    if artifact.get("html_relative_path") != relative_html:
        raise GateViolation("HTML_ARTIFACT_HTML_MISMATCH")
    if _require_sha256(artifact.get("html_sha256"), invalid_code="HTML_ARTIFACT_EVIDENCE_INVALID") != current_hash:
        raise GateViolation("HTML_HASH_MISMATCH")
    receipt_value = artifact.get("html_gate_receipt_path")
    if not isinstance(receipt_value, str) or not receipt_value:
        raise GateViolation("HTML_ARTIFACT_EVIDENCE_INVALID")
    receipt_path = _ensure_inside(package, package / receipt_value, outside_code="HTML_ARTIFACT_EVIDENCE_INVALID")
    receipt = _read_json(
        receipt_path,
        missing_code="HTML_GATE_RECEIPT_MISSING",
        invalid_code="HTML_GATE_RECEIPT_INVALID",
    )
    if receipt.get("action") != "html" or receipt.get("package_path") != str(package):
        raise GateViolation("HTML_GATE_RECEIPT_INVALID")
    if _require_sha256(artifact.get("html_gate_receipt_sha256"), invalid_code="HTML_ARTIFACT_EVIDENCE_INVALID") != _sha256(receipt_path):
        raise GateViolation("HTML_GATE_RECEIPT_MISMATCH")

    approval_path = package / HTML_APPROVAL_EVIDENCE_FILENAME
    approval = _read_json(
        approval_path,
        missing_code="HTML_APPROVAL_EVIDENCE_MISSING",
        invalid_code="HTML_APPROVAL_EVIDENCE_INVALID",
    )
    _require_package_identity(
        approval.get("package_identity"),
        package,
        invalid_code="HTML_APPROVAL_EVIDENCE_INVALID",
        mismatch_code="HTML_APPROVAL_PACKAGE_MISMATCH",
    )
    if approval.get("html_relative_path") != relative_html:
        raise GateViolation("HTML_APPROVAL_HTML_MISMATCH")
    if _require_sha256(approval.get("html_sha256"), invalid_code="HTML_APPROVAL_EVIDENCE_INVALID") != current_hash:
        raise GateViolation("HTML_HASH_MISMATCH")
    if _require_sha256(approval.get("html_artifact_evidence_sha256"), invalid_code="HTML_APPROVAL_EVIDENCE_INVALID") != _sha256(artifact_path):
        raise GateViolation("HTML_APPROVAL_EVIDENCE_INVALID")
    if approval.get("approved_by_user") is not True or not isinstance(approval.get("approved_at"), str) or not approval["approved_at"].strip():
        raise GateViolation("HTML_APPROVAL_EVIDENCE_INVALID")
    if not isinstance(approval.get("approval_evidence_reference"), str) or not approval["approval_evidence_reference"].strip():
        raise GateViolation("HTML_APPROVAL_EVIDENCE_INVALID")
    return {
        "html_sha256": current_hash,
        "html_artifact_evidence_path": str(artifact_path),
        "html_artifact_evidence_sha256": _sha256(artifact_path),
        "html_approval_path": str(approval_path),
        "html_approval_sha256": _sha256(approval_path),
    }


def _validate_mp4_approval_binding(
    package_dir: Path,
    html_path: Path,
    html_binding: dict[str, str],
) -> dict[str, str]:
    package = package_dir.resolve()
    html = _ensure_inside(package, html_path, outside_code="HTML_OUTSIDE_PACKAGE")
    approval_path = package / MP4_RENDER_APPROVAL_EVIDENCE_FILENAME
    approval = _read_json(
        approval_path,
        missing_code="MP4_APPROVAL_EVIDENCE_MISSING",
        invalid_code="MP4_APPROVAL_EVIDENCE_INVALID",
    )
    _require_package_identity(
        approval.get("package_identity"),
        package,
        invalid_code="MP4_APPROVAL_EVIDENCE_INVALID",
        mismatch_code="MP4_APPROVAL_PACKAGE_MISMATCH",
    )
    if (
        approval.get("schema_version") != "review-reel-mp4-render-approval-v1"
        or approval.get("html_relative_path") != html.relative_to(package).as_posix()
        or approval.get("html_sha256") != _sha256(html)
        or approval.get("html_approval_relative_path") != HTML_APPROVAL_EVIDENCE_FILENAME
        or approval.get("html_approval_sha256") != html_binding["html_approval_sha256"]
        or approval.get("approved_by_user") is not True
        or not isinstance(approval.get("approved_at"), str)
        or not approval["approved_at"].strip()
        or not isinstance(approval.get("approved_by"), str)
        or not approval["approved_by"].strip()
        or not isinstance(approval.get("approval_evidence_reference"), str)
        or not approval["approval_evidence_reference"].strip()
    ):
        raise GateViolation("MP4_APPROVAL_EVIDENCE_INVALID")
    return {
        "mp4_render_approval_path": str(approval_path),
        "mp4_render_approval_sha256": _sha256(approval_path),
    }


def _require_ledger_current_paths(package: Path, expected: dict[str, Path]) -> None:
    from video_engine_v2.current_artifacts import CurrentArtifactsViolation, package_uses_ledger, read_ledger

    if not package_uses_ledger(package):
        return
    try:
        ledger = read_ledger(package)
    except CurrentArtifactsViolation as error:
        raise GateViolation(str(error)) from error
    pointers = ledger["pointers"]
    for kind, path in expected.items():
        pointer = pointers.get(kind)
        if (
            not isinstance(pointer, dict)
            or (package / str(pointer.get("relative_path") or "")).resolve() != path.resolve()
        ):
            raise GateViolation(f"CURRENT_ARTIFACT_POINTER_MISSING:{kind}")


def validate_render_gate(
    *,
    package_dir: str | Path,
    html_path: str | Path,
    output_path: str | Path,
    sync_manifest_path: str | Path,
    privacy_manifest_path: str | Path,
    preset: dict[str, Any],
    engine_font_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate final render gates without creating an MP4 or frame directory."""
    package = Path(package_dir).resolve()
    html = _ensure_inside(package, Path(html_path), outside_code="HTML_OUTSIDE_PACKAGE")
    if not html.is_file():
        raise GateViolation("HTML_MISSING")
    output = _ensure_inside(package, Path(output_path), outside_code="OUTPUT_OUTSIDE_PACKAGE")
    filename_match = _FINAL_FILENAME.fullmatch(output.name)
    if not filename_match or (
        filename_match.group("attempt") is not None and int(filename_match.group("attempt")) < 2
    ):
        raise GateViolation("FINAL_FILENAME_INVALID")
    if output.exists():
        raise GateViolation("OUTPUT_ALREADY_EXISTS")
    if any(preset.get(key) != value for key, value in FINAL_RENDER_PRESET.items()):
        raise GateViolation("FINAL_PRESET_INVALID")
    _require_html_approval(package)
    _require_mp4_approval(package)
    html_binding = _validate_html_approval_binding(package, html)
    mp4_approval_binding = _validate_mp4_approval_binding(package, html, html_binding)
    privacy_path = _ensure_inside(package, Path(privacy_manifest_path), outside_code="PRIVACY_MANIFEST_OUTSIDE_PACKAGE")
    sync_path = _ensure_inside(package, Path(sync_manifest_path), outside_code="SYNC_MANIFEST_OUTSIDE_PACKAGE")
    payload = _read_json(sync_path, missing_code="SYNC_MANIFEST_MISSING", invalid_code="SYNC_MANIFEST_INVALID")
    gate_inputs = payload.get("gate_inputs")
    if not isinstance(gate_inputs, dict):
        raise GateViolation("SYNC_MANIFEST_STALE_OR_UNVERIFIED")
    planning_value = gate_inputs.get("planning_path")
    edit_value = gate_inputs.get("edit_path")
    if not isinstance(planning_value, str) or not planning_value or not isinstance(edit_value, str) or not edit_value:
        raise GateViolation("SYNC_MANIFEST_STALE_OR_UNVERIFIED")
    planning_path = _ensure_inside(package, Path(planning_value), outside_code="SYNC_MANIFEST_STALE_OR_UNVERIFIED")
    edit_path = _ensure_inside(package, Path(edit_value), outside_code="SYNC_MANIFEST_STALE_OR_UNVERIFIED")
    one_shot_html_contract = gate_inputs.get("one_shot_html_contract") is True
    _validate_preflight(
        package,
        planning_path,
        edit_path,
        privacy_path,
        allow_one_shot_html_contract=one_shot_html_contract,
    )
    _validate_sync_manifest(
        package,
        sync_path,
        planning_path,
        edit_path,
        privacy_path,
        expected_one_shot_html_contract=one_shot_html_contract,
    )
    render_dependencies = _validate_render_dependency_binding(package, html, edit_path, engine_font_path)
    _require_html_manual_review(package, html)
    manual_review_path = find_current_html_manual_review(package, html)
    if manual_review_path is None:
        raise GateViolation("HTML_MANUAL_REVIEW_STALE_OR_INVALID")
    _require_ledger_current_paths(
        package,
        {
            "html": html,
            "html_artifact_evidence": html.parent / HTML_ARTIFACT_EVIDENCE_FILENAME,
            "html_qa_report": html.parent / "html_internal_qa_report.json",
            "html_manual_review": manual_review_path,
            "html_approval": package / HTML_APPROVAL_EVIDENCE_FILENAME,
            "mp4_render_approval": package / MP4_RENDER_APPROVAL_EVIDENCE_FILENAME,
            "privacy_manifest": privacy_path,
            "sync_manifest": sync_path,
            "planning_recipe": planning_path,
            "edit_recipe": edit_path,
        },
    )
    return {
        "schema_version": "1.0",
        "action": "render",
        "package_path": str(package),
        "html_path": str(html),
        **html_binding,
        **mp4_approval_binding,
        "output_path": str(output),
        "preset": dict(FINAL_RENDER_PRESET),
        "sync_manifest_path": str(sync_path),
        "sync_manifest_sha256": _sha256(sync_path),
        "privacy_manifest_path": str(privacy_path),
        "privacy_manifest_sha256": _sha256(privacy_path),
        "render_dependencies": render_dependencies,
    }


def write_gate_receipt(package_dir: str | Path, receipt: dict[str, Any]) -> Path:
    """Write a non-overwriting receipt only after every gate for the action passed."""
    package = Path(package_dir).resolve()
    receipt_dir = package / "_work" / "production_gates"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{receipt['action']}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    for suffix in range(1000):
        path = receipt_dir / f"{prefix}_{suffix:03d}.json"
        try:
            with path.open("x", encoding="utf-8") as output:
                json.dump({**receipt, "issued_at": datetime.now(timezone.utc).isoformat()}, output, ensure_ascii=False, indent=2)
                output.write("\n")
            return path
        except FileExistsError:
            continue
    raise GateViolation("GATE_RECEIPT_COLLISION")


def _official_gate_receipt(
    receipt_path: str | Path,
    package_dir: str | Path,
    *,
    expected_action: str,
) -> tuple[Path, Path, dict[str, Any]]:
    package = Path(package_dir).resolve()
    receipt_dir = (package / "_work" / "production_gates").resolve()
    receipt_file = Path(receipt_path).resolve()
    if receipt_file.parent != receipt_dir:
        raise GateViolation("GATE_RECEIPT_OUTSIDE_OFFICIAL_DIR")
    receipt = _read_json(
        receipt_file,
        missing_code="GATE_RECEIPT_MISSING",
        invalid_code="GATE_RECEIPT_INVALID",
    )
    if (
        receipt.get("action") != expected_action
        or receipt.get("package_path") != str(package)
        or not isinstance(receipt.get("issued_at"), str)
        or not receipt["issued_at"].strip()
    ):
        raise GateViolation("GATE_RECEIPT_INVALID")
    return package, receipt_file, receipt


def _compact_receipt_hash(receipt_file: Path) -> str:
    """Keep one-time receipt markers below Windows' legacy path limit."""
    return base64.urlsafe_b64encode(bytes.fromhex(_sha256(receipt_file))).decode("ascii").rstrip("=")


def _gate_receipt_consumption_markers(package: Path, receipt_file: Path) -> tuple[Path, Path]:
    consumed_dir = package / "_work" / "production_gates" / "consumed"
    receipt_hash = _sha256(receipt_file)
    return (
        consumed_dir / f"{_compact_receipt_hash(receipt_file)}.json",
        consumed_dir / f"{receipt_hash}.json",
    )


def assert_gate_receipt_available(
    receipt_path: str | Path,
    package_dir: str | Path,
    *,
    expected_action: str,
) -> None:
    """Reject a receipt that has already crossed its one-time artifact boundary."""
    package, receipt_file, _ = _official_gate_receipt(
        receipt_path,
        package_dir,
        expected_action=expected_action,
    )
    if any(marker_path.exists() for marker_path in _gate_receipt_consumption_markers(package, receipt_file)):
        raise GateViolation("GATE_RECEIPT_ALREADY_CONSUMED")


def consume_gate_receipt(
    receipt_path: str | Path,
    package_dir: str | Path,
    *,
    expected_action: str,
) -> Path:
    """Atomically consume a gate receipt without mutating its hash-bound JSON."""
    package, receipt_file, receipt = _official_gate_receipt(
        receipt_path,
        package_dir,
        expected_action=expected_action,
    )
    marker_path, legacy_marker_path = _gate_receipt_consumption_markers(package, receipt_file)
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    if legacy_marker_path.exists():
        raise GateViolation("GATE_RECEIPT_ALREADY_CONSUMED")
    marker = {
        "schema_version": "1.0",
        "action": expected_action,
        "receipt_sha256": _sha256(receipt_file),
        "receipt_issued_at": receipt["issued_at"],
        "consumed_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with marker_path.open("x", encoding="utf-8") as output:
            json.dump(marker, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except FileExistsError as error:
        raise GateViolation("GATE_RECEIPT_ALREADY_CONSUMED") from error
    return marker_path


def validate_html_receipt(receipt_path: str | Path, recipe_path: str | Path) -> None:
    """Used by the internal HTML builder before it creates a preview folder."""
    recipe = Path(recipe_path).resolve()
    package = recipe.parent
    _, _, receipt = _official_gate_receipt(receipt_path, package, expected_action="html")
    assert_gate_receipt_available(receipt_path, package, expected_action="html")
    if receipt.get("action") != "html" or receipt.get("recipe_path") != str(recipe) or receipt.get("recipe_sha256") != _sha256(recipe):
        raise GateViolation("GATE_RECEIPT_INVALID")


def _gate_reason(error: GateViolation) -> str:
    code = str(error.codes[0]) if error.codes else str(error)
    return code.lower()


def inspect_html_preview_chain(package_dir: str | Path, html_path: str | Path) -> dict[str, Any]:
    """Read-only check of HTML, artifact evidence, official gate receipt, and render deps."""
    package = Path(package_dir).resolve()
    try:
        html = _ensure_inside(package, Path(html_path), outside_code="HTML_OUTSIDE_PACKAGE")
    except GateViolation as error:
        return {"status": "stale_html", "stale_html_reason": _gate_reason(error)}
    result: dict[str, Any] = {
        "status": "stale_html",
        "html": html,
        "html_relative_path": html.relative_to(package).as_posix() if html.is_file() or html.exists() else None,
    }
    if not html.is_file():
        result["stale_html_reason"] = "html_missing"
        return result
    result["html_relative_path"] = html.relative_to(package).as_posix()
    artifact_path = html.parent / HTML_ARTIFACT_EVIDENCE_FILENAME
    try:
        artifact = _read_json(
            artifact_path,
            missing_code="html_artifact_evidence_missing",
            invalid_code="html_artifact_evidence_invalid",
        )
        _require_package_identity(
            artifact.get("package_identity"),
            package,
            invalid_code="html_artifact_evidence_invalid",
            mismatch_code="html_artifact_package_mismatch",
        )
        if artifact.get("html_relative_path") != result["html_relative_path"]:
            result["stale_html_reason"] = "html_relative_path_mismatch"
            return result
        if _require_sha256(artifact.get("html_sha256"), invalid_code="html_sha256_missing") != _sha256(html):
            result["stale_html_reason"] = "html_sha256_mismatch"
            return result
        receipt_value = artifact.get("html_gate_receipt_path")
        if not isinstance(receipt_value, str) or not receipt_value:
            result["stale_html_reason"] = "html_gate_receipt_missing"
            return result
        receipt_path = _ensure_inside(package, package / receipt_value, outside_code="html_gate_receipt_missing")
        if _require_sha256(artifact.get("html_gate_receipt_sha256"), invalid_code="html_gate_receipt_missing") != _sha256(receipt_path):
            result["stale_html_reason"] = "html_gate_receipt_mismatch"
            return result
        receipt = _read_json(
            receipt_path,
            missing_code="html_gate_receipt_missing",
            invalid_code="html_gate_receipt_invalid",
        )
        if receipt.get("action") != "html":
            result["stale_html_reason"] = "html_gate_receipt_invalid"
            return result
        package_path_value = receipt.get("package_path")
        try:
            same_package = isinstance(package_path_value, str) and os.path.samefile(package_path_value, package)
        except OSError:
            same_package = False
        if not same_package:
            result["stale_html_reason"] = "html_gate_package_mismatch"
            return result
        recipe_value = receipt.get("recipe_path")
        if not isinstance(recipe_value, str) or not recipe_value:
            result["stale_html_reason"] = "html_gate_recipe_missing"
            return result
        recipe_path = _ensure_inside(package, Path(recipe_value), outside_code="html_gate_recipe_missing")
        if not recipe_path.is_file():
            result["stale_html_reason"] = "html_gate_recipe_missing"
            return result
        if _require_sha256(receipt.get("recipe_sha256"), invalid_code="html_gate_recipe_mismatch") != _sha256(recipe_path):
            result["stale_html_reason"] = "html_gate_recipe_mismatch"
            return result
        sync_value = receipt.get("sync_manifest_path")
        if not isinstance(sync_value, str) or not sync_value:
            result["stale_html_reason"] = "html_gate_sync_missing"
            return result
        sync_path = _ensure_inside(package, Path(sync_value), outside_code="html_gate_sync_missing")
        if not sync_path.is_file():
            result["stale_html_reason"] = "html_gate_sync_missing"
            return result
        if _require_sha256(receipt.get("sync_manifest_sha256"), invalid_code="html_gate_sync_mismatch") != _sha256(sync_path):
            result["stale_html_reason"] = "html_gate_sync_mismatch"
            return result
        if not isinstance(receipt.get("one_shot_html_contract"), bool):
            result["stale_html_reason"] = "html_gate_receipt_invalid"
            return result
        recorded = _dependency_map(artifact.get("render_dependencies"), invalid_code="render_dependency_invalid")
        kinds = {kind for kind, _scope, _path in recorded}
        if not {"image", "voice", "font"}.issubset(kinds):
            result["stale_html_reason"] = "render_dependencies_incomplete"
            return result
        for (kind, scope, relative_path), (byte_count, digest) in recorded.items():
            if scope == "package":
                dependency = _ensure_inside(package, package / relative_path, outside_code=f"dependency_mismatch:{kind}")
            elif scope == "repository":
                dependency = _ensure_inside(
                    REPOSITORY_ROOT,
                    REPOSITORY_ROOT / relative_path,
                    outside_code=f"dependency_mismatch:{kind}",
                )
            else:
                result["stale_html_reason"] = "render_dependency_invalid"
                return result
            if not dependency.is_file() or dependency.stat().st_size != byte_count or _sha256(dependency) != digest:
                result["stale_html_reason"] = f"dependency_mismatch:{kind}"
                return result
    except GateViolation as error:
        result["stale_html_reason"] = _gate_reason(error)
        return result
    result.update(
        {
            "status": "valid",
            "artifact_path": artifact_path,
            "evidence": artifact,
            "receipt_path": receipt_path,
            "recipe_path": recipe_path,
            "sync_path": sync_path,
        }
    )
    return result


def html_approval_is_current(package_dir: str | Path, html_path: str | Path) -> bool:
    package = Path(package_dir).resolve()
    try:
        html = _ensure_inside(package, Path(html_path), outside_code="HTML_OUTSIDE_PACKAGE")
        _validate_html_approval_binding(package, html)
        _require_html_manual_review(package, html)
    except GateViolation:
        return False
    return True


def mp4_approval_is_current(package_dir: str | Path, html_path: str | Path) -> bool:
    if not html_approval_is_current(package_dir, html_path):
        return False
    package = Path(package_dir).resolve()
    try:
        html = _ensure_inside(package, Path(html_path), outside_code="HTML_OUTSIDE_PACKAGE")
        html_binding = _validate_html_approval_binding(package, html)
        _validate_mp4_approval_binding(package, html, html_binding)
    except GateViolation:
        return False
    return True
