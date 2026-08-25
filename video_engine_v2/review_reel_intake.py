"""Canonical, local-only intake for the review-reel production workflow.

This module deliberately creates only the pre-photo package boundary.  It does
not create a script, voice, HTML, or MP4.  HTML may be requested later through
the existing production orchestrator after its independent gates pass.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import uuid4

from PIL import Image, ImageChops, ImageDraw, UnidentifiedImageError

from .recipe_scaffold import build_recipe_scaffold


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
METADATA_FILENAME = "CANONICAL_PACKAGE_METADATA.json"
POINTER_DIRECTORY = ".review_reel_production"
ACTIVE_POINTER_FILENAME = "active_package.json"
REGISTRY_FILENAME = "registry.json"
SOURCE_REGISTRY_FILENAME = "source_registry_private.json"
MATERIAL_BANK_INVENTORY_FILENAME = "material_bank_inventory_private.json"
INVENTORY_SCHEMA_VERSION = "review-reel-inventory-v1"
PACKAGE_SCHEMA_VERSION = "review-reel-canonical-package-v1"
SOURCE_REGISTRY_SCHEMA_VERSION = "review-reel-source-registry-v1"
_CONTENT_ID = re.compile(r"^\d{3}$")
_CONTENT_PREFIX = re.compile(r"^(\d{3})_")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_UNSAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_CANDIDATE_PREFIX = "CAND-"
_CANDIDATE_ID = re.compile(r"^CAND-\d{8}-\d{4}$")
_CANDIDATE_EVIDENCE_EXTENSIONS = frozenset({".json", ".md", ".source", ".txt"})
_MAX_CANDIDATE_EVIDENCE_BYTES = 2 * 1024 * 1024
_SELECTION_QUARANTINE_REASON_CODES = frozenset(
    {"duplicate_existing_review", "policy_excluded", "wrong_selection"}
)
_PHOTO_MEDIA_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".heif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
PHOTO_SELECTION_SCHEMA_VERSION = "review-reel-photo-selection-v2"
PRIVACY_BLOCKING_CATEGORIES = frozenset(
    {
        "identifiable_face",
        "reflected_identifiable_face",
        "family_photo",
        "resident_name",
        "phone_number",
        "account_identifier",
        "apartment_unit_number",
        "door_lock_code",
        "intercom_identifier",
        "vehicle_plate",
        "delivery_label",
        "mail_document",
        "order_information",
    }
)
EDITORIAL_CATEGORIES = frozenset(
    {
        "selected_story_evidence",
        "alternate_held",
        "not_required_by_narrative",
        "duplicate",
        "unusable_quality",
        "unrelated_to_review",
        "privacy_unrecoverable",
    }
)
EVIDENCE_CLASSES = frozenset(
    {
        "installed_result",
        "before_state",
        "measurement",
        "review_capture",
        "context",
        "detail",
        "installation_process",
    }
)
SANITIZING_ACTIONS = frozenset({"crop", "blur", "mask", "replace"})
MASKING_INFEASIBLE_CATEGORIES = frozenset(
    {"risk_covers_essential_subject", "sanitization_failed", "source_integrity_constraint"}
)
REVIEW_CAPTURE_MAX_MASK_AREA_RATIO = 0.12


class IntakeViolation(ValueError):
    """A routing or intake request did not meet the canonical contract."""

    def __init__(self, *codes: str):
        self.codes = tuple(codes)
        super().__init__(", ".join(self.codes))


@dataclass(frozen=True)
class CanonicalPackage:
    package_dir: Path
    image_dir: Path
    metadata: dict[str, Any]
    reused_existing: bool


def _normalise_command(command: str) -> str:
    if not isinstance(command, str) or not command.strip():
        raise IntakeViolation("USER_COMMAND_INVALID")
    return re.sub(r"[.?!]+", "", " ".join(command.casefold().split()))


def route_user_command(command: str, *, active_review_reel_package: bool = False) -> dict[str, str]:
    """Map a short Korean request to exactly one workflow state transition.

    Reel-specific phrases are checked before generic review-content phrases so a
    mixed message can never fall back to a material-bank flow.
    """

    normalised = _normalise_command(command)
    compact = re.sub(r"\s+", "", normalised)
    html_approval_context = "html" in compact and "승인" in compact
    render_requested = "렌더" in compact and any(
        stem in compact for stem in ("진행", "시작", "해줘", "하자", "까지")
    )
    if render_requested and (active_review_reel_package or html_approval_context):
        state = (
            "html_approval_and_mp4_render_intent_requested"
            if html_approval_context
            else "mp4_render_intent_requested"
        )
        return {
            "workflow": "review_reel_production",
            "state": state,
            "next_action": "resolve_active_package_then_record_hash_bound_approvals",
        }
    if (
        "사진" in compact
        and any(stem in compact for stem in ("넣었", "준비됐", "준비완료"))
        and "html" in compact
        and any(stem in compact for stem in ("가자", "만들", "진행", "까지"))
    ):
        return {
            "workflow": "review_reel_production",
            "state": "one_shot_html_requested",
            "next_action": "resolve_active_canonical_package",
        }
    if (
        "리뷰" in compact
        and "폴더" in compact
        and any(stem in compact for stem in ("골라", "고르"))
        and any(stem in compact for stem in ("만들", "준비"))
    ):
        return {
            "workflow": "review_reel_production",
            "state": "canonical_package_create_requested",
            "next_action": "select_inventory_record",
        }
    # 이 저장소에서 릴스·숏폼·쇼츠·리뷰 영상 제작은 같은 공식 리뷰 릴스
    # 파이프라인을 가리킨다. 자연어 표기가 달라도 generic 흐름으로 내리지 않는다.
    review_reel_term = any(term in compact for term in ("릴스", "숏폼", "쇼츠", "리뷰영상"))
    if review_reel_term and any(
        stem in compact for stem in ("만들", "제작", "시작", "진행", "발행", "해보", "하자", "가자")
    ):
        return {
            "workflow": "review_reel_production",
            "state": "selection_required",
            "next_action": "select_inventory_record",
        }
    return {
        "workflow": "generic_review_content",
        "state": "generic_review_content_requested",
        "next_action": "follow_review_content_command",
    }


def _read_json(path: Path, *, missing: str, invalid: str) -> dict[str, Any]:
    if not path.is_file():
        raise IntakeViolation(missing)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise IntakeViolation(invalid) from error
    if not isinstance(payload, dict):
        raise IntakeViolation(invalid)
    return payload


def _required_text(record: dict[str, Any], field: str, code: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise IntakeViolation(code)
    return value.strip()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_slug(value: str) -> str:
    slug = value.strip()
    if not slug or slug in {".", ".."} or _WINDOWS_UNSAFE_NAME.search(slug):
        raise IntakeViolation("CONTENT_SLUG_INVALID")
    if _CANDIDATE_PREFIX in slug.upper():
        raise IntakeViolation("CANDIDATE_NAME_EXPOSURE_FORBIDDEN")
    return slug


def _resolve_inventory_record(inventory_path: Path, record_key: str) -> tuple[dict[str, Any], Path]:
    inventory = _read_json(inventory_path, missing="INVENTORY_MISSING", invalid="INVENTORY_INVALID")
    if inventory.get("schema_version") != INVENTORY_SCHEMA_VERSION:
        raise IntakeViolation("INVENTORY_SCHEMA_INVALID")
    records = inventory.get("records")
    if not isinstance(records, list):
        raise IntakeViolation("INVENTORY_RECORDS_INVALID")
    matches = [record for record in records if isinstance(record, dict) and record.get("record_key") == record_key]
    if len(matches) != 1:
        raise IntakeViolation("INVENTORY_RECORD_NOT_UNIQUE")
    record = dict(matches[0])

    content_id = _required_text(record, "content_id", "CONTENT_ID_MISSING")
    if not _CONTENT_ID.fullmatch(content_id):
        raise IntakeViolation("CONTENT_ID_INVALID")
    record["content_id"] = content_id
    record["content_slug"] = _safe_slug(_required_text(record, "content_slug", "CONTENT_SLUG_MISSING"))
    record["review_text"] = _required_text(record, "review_text", "REVIEW_TEXT_MISSING")
    for field, code in (
        ("product_order_number", "PRODUCT_ORDER_NUMBER_MISSING"),
        ("review_article_id", "REVIEW_ARTICLE_ID_MISSING"),
        ("source_reference", "SOURCE_REFERENCE_MISSING"),
    ):
        record[field] = _required_text(record, field, code)

    candidate_reference = record.get("candidate_reference")
    if candidate_reference is not None:
        if not isinstance(candidate_reference, str) or not _CANDIDATE_ID.fullmatch(candidate_reference):
            raise IntakeViolation("CANDIDATE_REFERENCE_INVALID")
        record["candidate_reference"] = candidate_reference

    source_value = _required_text(record, "review_source_path", "REVIEW_SOURCE_PATH_MISSING")
    source_path = Path(source_value)
    if not source_path.is_absolute():
        source_path = _inside(
            REPOSITORY_ROOT,
            REPOSITORY_ROOT / source_path,
            code="REVIEW_SOURCE_OUTSIDE_REPOSITORY",
        )
    source_path = source_path.resolve()
    if not source_path.is_file():
        raise IntakeViolation("REVIEW_SOURCE_MISSING")
    try:
        source_text = source_path.read_text(encoding="utf-8")
    except OSError as error:
        raise IntakeViolation("REVIEW_SOURCE_UNREADABLE") from error
    if source_text != record["review_text"]:
        raise IntakeViolation("REVIEW_SOURCE_TEXT_MISMATCH")
    return record, source_path


def _identity(record: dict[str, Any]) -> dict[str, str]:
    return {
        "content_id": record["content_id"],
        "review_text_sha256": _sha256_text(record["review_text"]),
        "product_order_number": record["product_order_number"],
        "review_article_id": record["review_article_id"],
    }


def _generation_source_key(source_path: Path) -> str:
    """Match generate.py's source-key contract without importing its API client."""

    resolved_source = source_path.resolve()
    try:
        return str(resolved_source.relative_to(REPOSITORY_ROOT.resolve()))
    except ValueError:
        return str(resolved_source)


def _inside(root: Path, candidate: Path, *, code: str) -> Path:
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as error:
        raise IntakeViolation(code) from error
    return resolved_candidate


def _read_metadata(package_dir: Path, *, code_prefix: str) -> dict[str, Any]:
    metadata = _read_json(
        package_dir / METADATA_FILENAME,
        missing=f"{code_prefix}_METADATA_MISSING",
        invalid=f"{code_prefix}_METADATA_INVALID",
    )
    if metadata.get("schema_version") != PACKAGE_SCHEMA_VERSION:
        raise IntakeViolation(f"{code_prefix}_METADATA_SCHEMA_INVALID")
    return metadata


def _canonical_metadata_paths(output_root: Path) -> list[Path]:
    """Return current flat packages plus read-compatible legacy inbox packages."""

    paths: list[Path] = []
    if not output_root.is_dir():
        return paths
    for child in output_root.iterdir():
        if child.is_dir() and _CONTENT_PREFIX.match(child.name):
            metadata = child / METADATA_FILENAME
            if metadata.is_file():
                paths.append(metadata)
    paths.extend(output_root.glob(f"inbox_*/*/{METADATA_FILENAME}"))
    return sorted(set(paths), key=lambda path: path.as_posix().casefold())


def _find_existing(output_root: Path, identity: dict[str, str]) -> CanonicalPackage | None:
    if not output_root.is_dir():
        return None
    for metadata_path in _canonical_metadata_paths(output_root):
        package_dir = metadata_path.parent
        if package_dir.name.startswith("."):
            continue
        try:
            metadata = _read_metadata(package_dir, code_prefix="EXISTING_PACKAGE")
        except IntakeViolation:
            continue
        if metadata.get("content_id") == identity["content_id"] and metadata.get("identity") != identity:
            raise IntakeViolation("CONTENT_ID_ALREADY_BOUND")
        if metadata.get("identity") != identity:
            continue
        image_name = metadata.get("image_directory_name")
        if not isinstance(image_name, str):
            continue
        image_dir = package_dir / image_name
        if image_dir.is_dir():
            return CanonicalPackage(package_dir.resolve(), image_dir.resolve(), metadata, reused_existing=True)
    return None


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


def _atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
            temporary.write(value)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


@contextmanager
def _exclusive_allocation_lock(state_dir: Path):
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = state_dir / ".source-allocation.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise IntakeViolation("SOURCE_ALLOCATION_LOCKED") from error
    try:
        os.close(descriptor)
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def _read_jsonl_record(path: Path, *, candidate_id: str) -> dict[str, Any]:
    if not path.is_file():
        raise IntakeViolation("MATERIAL_BANK_MISSING")
    if not _CANDIDATE_ID.fullmatch(candidate_id):
        raise IntakeViolation("CANDIDATE_REFERENCE_INVALID")
    matches: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as source:
            for raw_line in source:
                if not raw_line.strip():
                    continue
                record = json.loads(raw_line)
                if not isinstance(record, dict):
                    raise IntakeViolation("MATERIAL_BANK_INVALID")
                if record.get("candidate_id") == candidate_id:
                    matches.append(record)
    except (OSError, json.JSONDecodeError) as error:
        raise IntakeViolation("MATERIAL_BANK_INVALID") from error
    if len(matches) != 1:
        raise IntakeViolation("MATERIAL_BANK_RECORD_NOT_UNIQUE")
    return dict(matches[0])


def _load_source_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": SOURCE_REGISTRY_SCHEMA_VERSION, "records": []}
    registry = _read_json(path, missing="SOURCE_REGISTRY_MISSING", invalid="SOURCE_REGISTRY_INVALID")
    if registry.get("schema_version") != SOURCE_REGISTRY_SCHEMA_VERSION:
        raise IntakeViolation("SOURCE_REGISTRY_SCHEMA_INVALID")
    records = registry.get("records")
    if not isinstance(records, list):
        raise IntakeViolation("SOURCE_REGISTRY_RECORDS_INVALID")
    content_ids: set[str] = set()
    candidate_references: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise IntakeViolation("SOURCE_REGISTRY_RECORD_INVALID")
        content_id = record.get("content_id")
        candidate_reference = record.get("candidate_reference")
        identity = record.get("identity")
        if not isinstance(content_id, str) or not _CONTENT_ID.fullmatch(content_id):
            raise IntakeViolation("SOURCE_REGISTRY_CONTENT_ID_INVALID")
        _safe_slug(_required_text(record, "content_slug", "SOURCE_REGISTRY_SLUG_INVALID"))
        if (
            not isinstance(candidate_reference, str)
            or not _CANDIDATE_ID.fullmatch(candidate_reference)
        ):
            raise IntakeViolation("SOURCE_REGISTRY_CANDIDATE_INVALID")
        if content_id in content_ids:
            raise IntakeViolation("SOURCE_REGISTRY_CONTENT_ID_DUPLICATE")
        if candidate_reference in candidate_references:
            raise IntakeViolation("SOURCE_REGISTRY_CANDIDATE_DUPLICATE")
        if not isinstance(identity, dict):
            raise IntakeViolation("SOURCE_REGISTRY_IDENTITY_INVALID")
        for field in (
            "candidate_reference",
            "inventory_id",
            "review_article_id",
            "product_order_number",
        ):
            _required_text(identity, field, "SOURCE_REGISTRY_IDENTITY_INVALID")
        review_hash = identity.get("review_text_sha256")
        if not isinstance(review_hash, str) or not _SHA256.fullmatch(review_hash):
            raise IntakeViolation("SOURCE_REGISTRY_IDENTITY_INVALID")
        if identity["candidate_reference"] != candidate_reference:
            raise IntakeViolation("SOURCE_REGISTRY_IDENTITY_INVALID")
        content_ids.add(content_id)
        candidate_references.add(candidate_reference)
    return registry


def _load_material_bank_inventory(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": INVENTORY_SCHEMA_VERSION, "records": []}
    inventory = _read_json(
        path,
        missing="MATERIAL_BANK_INVENTORY_MISSING",
        invalid="MATERIAL_BANK_INVENTORY_INVALID",
    )
    if inventory.get("schema_version") != INVENTORY_SCHEMA_VERSION:
        raise IntakeViolation("MATERIAL_BANK_INVENTORY_SCHEMA_INVALID")
    if not isinstance(inventory.get("records"), list):
        raise IntakeViolation("MATERIAL_BANK_INVENTORY_RECORDS_INVALID")
    return inventory


def _used_content_ids(*, output_root: Path, reviews_root: Path, registry: dict[str, Any]) -> set[int]:
    used: set[int] = set()
    for record in registry["records"]:
        if isinstance(record, dict) and isinstance(record.get("content_id"), str):
            match = _CONTENT_ID.fullmatch(record["content_id"])
            if match:
                used.add(int(record["content_id"]))
    scan_paths: list[Path] = []
    if output_root.exists():
        scan_paths.extend(
            path
            for path in output_root.iterdir()
            if path.is_dir() and _CONTENT_PREFIX.match(path.name)
        )
        scan_paths.extend(output_root.glob("inbox_*/*"))
    if reviews_root.exists():
        scan_paths.extend(reviews_root.glob("*.txt"))
        scan_paths.extend(reviews_root.glob("inbox_*/*.txt"))
        scan_paths.extend((reviews_root / "production_registry").glob("*.txt"))
    for path in scan_paths:
        match = _CONTENT_PREFIX.match(path.name)
        if match:
            used.add(int(match.group(1)))
    return used


def _next_content_id(*, output_root: Path, reviews_root: Path, registry: dict[str, Any]) -> str:
    used = _used_content_ids(output_root=output_root, reviews_root=reviews_root, registry=registry)
    next_id = max(used, default=0) + 1
    if next_id > 999:
        raise IntakeViolation("CONTENT_ID_SPACE_EXHAUSTED")
    return f"{next_id:03d}"


def _material_identity(record: dict[str, Any]) -> dict[str, str]:
    return {
        "candidate_reference": _required_text(
            record, "candidate_id", "CANDIDATE_REFERENCE_MISSING"
        ),
        "inventory_id": _required_text(record, "inventory_id", "INVENTORY_ID_MISSING"),
        "review_article_id": _required_text(record, "review_id", "REVIEW_ARTICLE_ID_MISSING"),
        "product_order_number": _required_text(
            record, "order_id", "PRODUCT_ORDER_NUMBER_MISSING"
        ),
        "review_text_sha256": _sha256_text(
            _required_text(record, "review_text", "REVIEW_TEXT_MISSING")
        ),
    }


def _material_record_key(candidate_id: str) -> str:
    return f"material-bank::{candidate_id}"


def _candidate_policy_exclusion_reasons(record: dict[str, Any]) -> list[str]:
    product_name = str(record.get("product_name") or "")
    product_family = str(record.get("product_family") or "")
    product = re.sub(r"\s+", "", f"{product_family} {product_name}").casefold()
    reasons: list[str] = []
    if "abs도어" in product:
        reasons.append("ABS_DOOR")
    if "셀프실측" in product:
        reasons.append("SELF_MEASUREMENT")
    if any(token in product for token in ("셀프설치시공", "셀프설치", "셀프시공")):
        reasons.append("SELF_INSTALLATION")
    if any(token in product for token in ("배송상품", "택배배송", "배송전용")):
        reasons.append("DELIVERY_ONLY")
    return reasons


def _production_package_dirs(output_root: Path) -> list[Path]:
    if not output_root.is_dir():
        return []
    package_dirs: list[Path] = [
        path
        for path in output_root.iterdir()
        if path.is_dir() and _CONTENT_PREFIX.match(path.name)
    ]
    for collection in sorted(output_root.glob("inbox_*"), key=lambda path: path.name.casefold()):
        if collection.is_dir():
            package_dirs.extend(path for path in collection.iterdir() if path.is_dir())
    pilot = output_root / "pilot"
    if pilot.is_dir():
        package_dirs.extend(path for path in pilot.iterdir() if path.is_dir())
    unique = {str(path.resolve()).casefold(): path.resolve() for path in package_dirs}
    return sorted(unique.values(), key=lambda path: str(path).casefold())


def _token_present(text: str, token: str) -> bool:
    if not token:
        return False
    pattern = re.compile(r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])")
    return pattern.search(text) is not None


def _candidate_evidence_texts(package_dir: Path, reviews_root: Path) -> list[str]:
    texts: list[str] = []
    source_markers: list[str] = []
    for path in package_dir.rglob("*"):
        if (
            not path.is_file()
            or path.suffix.casefold() not in _CANDIDATE_EVIDENCE_EXTENSIONS
        ):
            continue
        try:
            if path.stat().st_size > _MAX_CANDIDATE_EVIDENCE_BYTES:
                continue
            value = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        texts.append(value)
        if path.name == ".source":
            source_markers.append(value.strip())

    prefix = _CONTENT_PREFIX.match(package_dir.name)
    source_candidates: list[Path] = []
    if prefix:
        content_id = prefix.group(1)
        source_candidates.extend(reviews_root.glob(f"inbox_*/{content_id}_*.txt"))
        source_candidates.extend((reviews_root / "production_registry").glob(f"{content_id}_*.txt"))
        source_candidates.extend((reviews_root / "pilot").glob(f"review_{content_id}.txt"))
    for marker in source_markers:
        if not marker:
            continue
        marker_path = Path(marker)
        if not marker_path.is_absolute():
            marker_path = REPOSITORY_ROOT / marker_path
        try:
            resolved = marker_path.resolve()
            resolved.relative_to(reviews_root.resolve())
        except (OSError, ValueError):
            continue
        source_candidates.append(resolved)
    for source_path in source_candidates:
        try:
            if source_path.is_file() and source_path.stat().st_size <= _MAX_CANDIDATE_EVIDENCE_BYTES:
                texts.append(source_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    return texts


def _candidate_package_matches(
    *,
    output_root: Path,
    reviews_root: Path,
    candidate_id: str,
    identity: dict[str, str],
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for package_dir in _production_package_dirs(output_root):
        match_types: set[str] = set()
        if package_dir.name == candidate_id or package_dir.name.startswith(f"{candidate_id}_"):
            match_types.add("candidate_reference")
        metadata: dict[str, Any] | None = None
        metadata_path = package_dir / METADATA_FILENAME
        if metadata_path.is_file():
            try:
                loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
                metadata = loaded if isinstance(loaded, dict) else None
            except (OSError, json.JSONDecodeError):
                metadata = None
        if metadata is not None:
            review_source = metadata.get("review_source")
            if isinstance(review_source, dict) and review_source.get("candidate_reference") == candidate_id:
                match_types.add("candidate_reference")
            package_identity = metadata.get("identity")
            if isinstance(package_identity, dict):
                if package_identity.get("review_article_id") == identity["review_article_id"]:
                    match_types.add("review_article_id")
                if package_identity.get("product_order_number") == identity["product_order_number"]:
                    match_types.add("product_order_number")
                if package_identity.get("review_text_sha256") == identity["review_text_sha256"]:
                    match_types.add("review_text_sha256")
        for text in _candidate_evidence_texts(package_dir, reviews_root):
            if _token_present(text, candidate_id):
                match_types.add("candidate_reference")
            if _token_present(text, identity["review_article_id"]):
                match_types.add("review_article_id")
            if _token_present(text, identity["product_order_number"]):
                match_types.add("product_order_number")
        if match_types:
            matches.append(
                {
                    "path": package_dir,
                    "relative_path": package_dir.relative_to(output_root).as_posix(),
                    "match_types": sorted(match_types),
                    "metadata": metadata,
                }
            )
    return matches


def _is_official_binding_package(match: dict[str, Any], binding: dict[str, Any]) -> bool:
    metadata = match.get("metadata")
    if not isinstance(metadata, dict):
        return False
    review_source = metadata.get("review_source")
    return (
        metadata.get("content_id") == binding.get("content_id")
        and isinstance(review_source, dict)
        and review_source.get("candidate_reference") == binding.get("candidate_reference")
    )


def _candidate_legacy_package_paths(output_root: Path, candidate_id: str) -> list[Path]:
    """Return pre-registry package directories that already used a candidate.

    Older packages were allowed to expose ``CAND-*`` in their directory name and
    were never imported into the newer source registry.  They remain immutable
    evidence, but must still prevent the same review from being allocated as a
    new numeric package.
    """

    if not _CANDIDATE_ID.fullmatch(candidate_id):
        raise IntakeViolation("CANDIDATE_REFERENCE_INVALID")
    if not output_root.is_dir():
        return []

    package_dirs: list[Path] = _production_package_dirs(output_root)
    package_dirs.extend(
        path
        for path in output_root.iterdir()
        if path.is_dir() and path.name.startswith(_CANDIDATE_PREFIX)
    )
    package_dirs = list(
        {str(path.resolve()).casefold(): path.resolve() for path in package_dirs}.values()
    )

    matches: dict[str, Path] = {}
    for package_dir in package_dirs:
        name_matches = package_dir.name == candidate_id or package_dir.name.startswith(
            f"{candidate_id}_"
        )
        metadata_matches = False
        metadata_path = package_dir / METADATA_FILENAME
        if metadata_path.is_file():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                metadata = None
            if isinstance(metadata, dict):
                review_source = metadata.get("review_source")
                metadata_matches = isinstance(review_source, dict) and (
                    review_source.get("candidate_reference") == candidate_id
                )
        evidence_mentions_candidate = False
        if not name_matches and not metadata_matches:
            candidate_bytes = candidate_id.encode("utf-8")
            candidate_token = re.compile(
                rb"(?<![A-Za-z0-9])" + re.escape(candidate_bytes) + rb"(?![A-Za-z0-9])"
            )
            for evidence_path in package_dir.rglob("*"):
                if (
                    not evidence_path.is_file()
                    or evidence_path.suffix.casefold() not in _CANDIDATE_EVIDENCE_EXTENSIONS
                ):
                    continue
                try:
                    if evidence_path.stat().st_size > _MAX_CANDIDATE_EVIDENCE_BYTES:
                        continue
                    if candidate_token.search(evidence_path.read_bytes()):
                        evidence_mentions_candidate = True
                        break
                except OSError:
                    continue
        if name_matches or metadata_matches or evidence_mentions_candidate:
            matches[str(package_dir.resolve()).casefold()] = package_dir.resolve()
    return sorted(matches.values(), key=lambda path: str(path).casefold())


def inspect_material_bank_candidate(
    *,
    output_root: str | Path,
    reviews_root: str | Path,
    material_bank_path: str | Path,
    candidate_id: str,
) -> dict[str, Any]:
    """Read-only eligibility check before selecting a material-bank candidate."""

    root = Path(output_root).resolve()
    local_reviews = Path(reviews_root).resolve()
    bank_path = Path(material_bank_path).resolve()
    selected = _read_jsonl_record(bank_path, candidate_id=candidate_id)
    identity = _material_identity(selected)
    exclusion_reasons = _candidate_policy_exclusion_reasons(selected)
    registry = _load_source_registry(root / POINTER_DIRECTORY / SOURCE_REGISTRY_FILENAME)
    official_matches = [
        record
        for record in registry["records"]
        if isinstance(record, dict) and record.get("candidate_reference") == candidate_id
    ]
    if len(official_matches) > 1:
        raise IntakeViolation("SOURCE_REGISTRY_RECORD_NOT_UNIQUE")
    legacy_paths = _candidate_legacy_package_paths(root, candidate_id)
    identity_matches = _candidate_package_matches(
        output_root=root,
        reviews_root=local_reviews,
        candidate_id=candidate_id,
        identity=identity,
    )
    binding = official_matches[0] if official_matches else None
    external_matches = [
        match
        for match in identity_matches
        if binding is None or not _is_official_binding_package(match, binding)
    ]
    review_matches = [
        match
        for match in external_matches
        if {"review_article_id", "review_text_sha256"}.intersection(match["match_types"])
    ]
    order_matches = [
        match
        for match in external_matches
        if "product_order_number" in match["match_types"]
        and match not in review_matches
    ]
    relative_legacy_paths = sorted(
        {
            path.relative_to(root).as_posix()
            for path in legacy_paths
        }
    )
    result: dict[str, Any] = {
        "workflow": "review_reel_production",
        "candidate_id": candidate_id,
        "inventory_id": identity["inventory_id"],
        "review_article_id": identity["review_article_id"],
        "eligible_for_new_package": False,
        "legacy_package_relative_paths": relative_legacy_paths,
    }
    if exclusion_reasons:
        result.update(
            {
                "status": "policy_excluded",
                "blocker_code": "CANDIDATE_PRODUCT_EXCLUDED",
                "exclusion_reason_codes": exclusion_reasons,
                "next_action": "select_a_non_excluded_candidate",
            }
        )
        return result
    if review_matches:
        result.update(
            {
                "status": "legacy_identity_present",
                "blocker_code": "REVIEW_ALREADY_USED",
                "legacy_package_relative_paths": sorted(
                    {match["relative_path"] for match in review_matches}
                ),
                "identity_match_types": sorted(
                    {kind for match in review_matches for kind in match["match_types"]}
                ),
                "next_action": "select_a_different_review",
            }
        )
        return result
    if order_matches:
        result.update(
            {
                "status": "related_review_hold",
                "blocker_code": "PRODUCT_ORDER_ALREADY_USED",
                "legacy_package_relative_paths": sorted(
                    {match["relative_path"] for match in order_matches}
                ),
                "identity_match_types": ["product_order_number"],
                "next_action": "request_related_review_resolution_or_select_another_candidate",
            }
        )
        return result
    if official_matches:
        binding = official_matches[0]
        if binding.get("identity") != identity:
            raise IntakeViolation("SOURCE_REGISTRY_IDENTITY_CONFLICT")
        result.update(
            {
                "status": "official_binding_exists",
                "existing_content_id": _required_text(
                    binding, "content_id", "CONTENT_ID_MISSING"
                ),
                "existing_content_slug": _safe_slug(
                    _required_text(binding, "content_slug", "CONTENT_SLUG_MISSING")
                ),
                "next_action": "reuse_existing_official_binding",
            }
        )
        return result
    if legacy_paths:
        result.update(
            {
                "status": "legacy_package_present",
                "blocker_code": "CANDIDATE_LEGACY_PACKAGE_PRESENT",
                "next_action": "select_a_different_candidate_or_request_legacy_resolution",
            }
        )
        return result
    result.update(
        {
            "status": "eligible",
            "eligible_for_new_package": True,
            "next_action": "confirm_candidate_and_content_slug_then_create",
            "create_command_template": (
                "python scripts/review_reel_intake.py create-from-material-bank "
                f'--output-root "{root}" --reviews-root "{local_reviews}" '
                f'--material-bank "{bank_path}" --candidate-id "{candidate_id}" '
                '--content-slug "<content-slug>"'
            ),
        }
    )
    return result


def _read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise IntakeViolation("MATERIAL_BANK_MISSING")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        with path.open("r", encoding="utf-8") as source:
            for raw_line in source:
                if not raw_line.strip():
                    continue
                record = json.loads(raw_line)
                if not isinstance(record, dict):
                    raise IntakeViolation("MATERIAL_BANK_INVALID")
                candidate_id = record.get("candidate_id")
                if not isinstance(candidate_id, str) or not _CANDIDATE_ID.fullmatch(candidate_id):
                    raise IntakeViolation("CANDIDATE_REFERENCE_INVALID")
                if candidate_id in seen:
                    raise IntakeViolation("MATERIAL_BANK_RECORD_NOT_UNIQUE")
                seen.add(candidate_id)
                records.append(record)
    except (OSError, json.JSONDecodeError) as error:
        raise IntakeViolation("MATERIAL_BANK_INVALID") from error
    return records


def shortlist_material_bank_candidates(
    *,
    output_root: str | Path,
    reviews_root: str | Path,
    material_bank_path: str | Path,
    limit: int = 10,
) -> dict[str, Any]:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 100:
        raise IntakeViolation("CANDIDATE_SHORTLIST_LIMIT_INVALID")
    root = Path(output_root).resolve()
    local_reviews = Path(reviews_root).resolve()
    bank_path = Path(material_bank_path).resolve()
    records = _read_jsonl_records(bank_path)
    ranked: list[tuple[int, int, dict[str, Any], dict[str, Any]]] = []
    for ordinal, record in enumerate(records, start=1):
        candidate_id = str(record["candidate_id"])
        inspection = inspect_material_bank_candidate(
            output_root=root,
            reviews_root=local_reviews,
            material_bank_path=bank_path,
            candidate_id=candidate_id,
        )
        rank_value = record.get("canonical_top60_rank")
        rank = rank_value if isinstance(rank_value, int) and not isinstance(rank_value, bool) else ordinal
        ranked.append((rank, ordinal, record, inspection))
    ranked.sort(key=lambda item: (item[0], item[1]))
    candidates: list[dict[str, Any]] = []
    for rank, _, record, inspection in ranked:
        candidates.append(
            {
                "rank": rank,
                "candidate_id": record["candidate_id"],
                "inventory_id": record.get("inventory_id"),
                "review_article_id": record.get("review_id"),
                "product_order_number": record.get("order_id"),
                "product_family": record.get("product_family"),
                "tier": record.get("tier"),
                "story_score_60": record.get("story_score_60"),
                "status": inspection["status"],
                "eligible_for_new_package": inspection["eligible_for_new_package"],
                "blocker_code": inspection.get("blocker_code"),
                "legacy_package_relative_paths": inspection.get(
                    "legacy_package_relative_paths", []
                ),
                "exclusion_reason_codes": inspection.get("exclusion_reason_codes", []),
            }
        )
    summary: dict[str, int] = {
        "evaluated": len(candidates),
        "eligible_for_new_package": sum(
            1 for candidate in candidates if candidate["eligible_for_new_package"]
        ),
    }
    for candidate in candidates:
        status = str(candidate["status"])
        summary[status] = summary.get(status, 0) + 1
    eligible_candidates = [
        candidate for candidate in candidates if candidate["eligible_for_new_package"]
    ][:limit]
    return {
        "workflow": "review_reel_production",
        "material_bank": str(bank_path),
        "summary": summary,
        "eligible_candidates": eligible_candidates,
        "candidates": candidates,
    }


def create_canonical_package_from_material_bank(
    *,
    output_root: str | Path,
    reviews_root: str | Path,
    material_bank_path: str | Path,
    candidate_id: str,
    content_slug: str,
    now: datetime | None = None,
) -> CanonicalPackage:
    """Register one selected material-bank record and create its canonical package.

    The local source registry, not the model, assigns the next unused numeric
    content ID. Repeating the same candidate reuses its first binding.
    """

    root = Path(output_root).resolve()
    local_reviews = Path(reviews_root).resolve()
    bank_path = Path(material_bank_path).resolve()
    selected = _read_jsonl_record(bank_path, candidate_id=candidate_id)
    identity = _material_identity(selected)
    if identity["candidate_reference"] != candidate_id:
        raise IntakeViolation("CANDIDATE_REFERENCE_INVALID")
    if _candidate_policy_exclusion_reasons(selected):
        raise IntakeViolation("CANDIDATE_PRODUCT_EXCLUDED")
    requested_slug = _safe_slug(content_slug)
    review_text = _required_text(selected, "review_text", "REVIEW_TEXT_MISSING")
    state_dir = root / POINTER_DIRECTORY
    source_registry_path = state_dir / SOURCE_REGISTRY_FILENAME
    inventory_path = state_dir / MATERIAL_BANK_INVENTORY_FILENAME

    with _exclusive_allocation_lock(state_dir):
        inspection = inspect_material_bank_candidate(
            output_root=root,
            reviews_root=local_reviews,
            material_bank_path=bank_path,
            candidate_id=candidate_id,
        )
        if inspection.get("status") not in {"eligible", "official_binding_exists"}:
            raise IntakeViolation(str(inspection.get("blocker_code") or "CANDIDATE_NOT_ELIGIBLE"))
        registry = _load_source_registry(source_registry_path)
        inventory = _load_material_bank_inventory(inventory_path)
        matches = [
            record
            for record in registry["records"]
            if isinstance(record, dict)
            and record.get("candidate_reference") == candidate_id
        ]
        if len(matches) > 1:
            raise IntakeViolation("SOURCE_REGISTRY_RECORD_NOT_UNIQUE")
        if matches:
            binding = dict(matches[0])
            if binding.get("identity") != identity:
                raise IntakeViolation("SOURCE_REGISTRY_IDENTITY_CONFLICT")
            content_id = _required_text(binding, "content_id", "CONTENT_ID_MISSING")
            bound_slug = _safe_slug(
                _required_text(binding, "content_slug", "CONTENT_SLUG_MISSING")
            )
        else:
            if _candidate_legacy_package_paths(root, candidate_id):
                raise IntakeViolation("CANDIDATE_LEGACY_PACKAGE_PRESENT")
            content_id = _next_content_id(
                output_root=root,
                reviews_root=local_reviews,
                registry=registry,
            )
            bound_slug = requested_slug
            binding = {
                "record_key": _material_record_key(candidate_id),
                "content_id": content_id,
                "content_slug": bound_slug,
                "candidate_reference": candidate_id,
                "identity": identity,
            }
            registry["records"].append(binding)

        source_path = local_reviews / "production_registry" / f"{content_id}_{bound_slug}.txt"
        if source_path.exists():
            try:
                existing_text = source_path.read_text(encoding="utf-8")
            except OSError as error:
                raise IntakeViolation("REVIEW_SOURCE_UNREADABLE") from error
            if existing_text != review_text:
                raise IntakeViolation("REVIEW_SOURCE_TEXT_MISMATCH")

        try:
            relative_source = source_path.resolve().relative_to(REPOSITORY_ROOT.resolve()).as_posix()
        except ValueError:
            relative_source = str(source_path.resolve())
        canonical_record = {
            "record_key": _material_record_key(candidate_id),
            "content_id": content_id,
            "content_slug": bound_slug,
            "review_source_path": relative_source,
            "review_text": review_text,
            "product_order_number": identity["product_order_number"],
            "review_article_id": identity["review_article_id"],
            "source_reference": (
                f"material-bank:{bank_path.name}#{identity['inventory_id']}"
            ),
            "candidate_reference": candidate_id,
        }
        inventory["records"] = [
            record
            for record in inventory["records"]
            if not (
                isinstance(record, dict)
                and record.get("record_key") == canonical_record["record_key"]
            )
        ]
        inventory["records"].append(canonical_record)
        inventory["records"].sort(key=lambda record: record["content_id"])
        registry["records"].sort(key=lambda record: record["content_id"])

        _atomic_write_json(source_registry_path, registry)
        if not source_path.exists():
            _atomic_write_text(source_path, review_text)
        _atomic_write_json(inventory_path, inventory)

    return create_canonical_package(
        output_root=root,
        inventory_path=inventory_path,
        record_key=canonical_record["record_key"],
        now=now,
    )


def quarantine_active_selection(
    *,
    output_root: str | Path,
    reviews_root: str | Path,
    expected_content_id: str,
    reason_code: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Recoverably quarantine one mistaken, empty pre-photo canonical selection."""

    if reason_code not in _SELECTION_QUARANTINE_REASON_CODES:
        raise IntakeViolation("ACTIVE_SELECTION_QUARANTINE_REASON_INVALID")
    root = Path(output_root).resolve()
    local_reviews = Path(reviews_root).resolve()
    package = resolve_active_package(root)
    _assert_expected_content_id(package, expected_content_id)
    if package.metadata.get("lifecycle_state") != "photo_intake_pending":
        raise IntakeViolation("ACTIVE_SELECTION_QUARANTINE_STATE_INVALID")
    approvals = package.metadata.get("approvals")
    if not isinstance(approvals, dict) or any(bool(value) for value in approvals.values()):
        raise IntakeViolation("ACTIVE_SELECTION_QUARANTINE_APPROVAL_PRESENT")
    if any(path.is_file() for path in package.image_dir.rglob("*")):
        raise IntakeViolation("ACTIVE_SELECTION_QUARANTINE_PHOTOS_PRESENT")
    allowed_files = {
        ".source",
        "APPROVAL_LOG.md",
        "CURRENT_ARTIFACTS.json",
        METADATA_FILENAME,
        "STATUS.md",
    }
    for child in package.package_dir.iterdir():
        if child == package.image_dir:
            continue
        if child.is_dir() or child.name not in allowed_files:
            raise IntakeViolation("ACTIVE_SELECTION_QUARANTINE_DOWNSTREAM_ARTIFACTS_PRESENT")

    review_source = package.metadata.get("review_source")
    if not isinstance(review_source, dict):
        raise IntakeViolation("ACTIVE_SELECTION_QUARANTINE_SOURCE_INVALID")
    candidate_id = review_source.get("candidate_reference")
    if not isinstance(candidate_id, str) or not _CANDIDATE_ID.fullmatch(candidate_id):
        raise IntakeViolation("ACTIVE_SELECTION_QUARANTINE_SOURCE_INVALID")
    source_value = review_source.get("path")
    if not isinstance(source_value, str) or not source_value.strip():
        raise IntakeViolation("ACTIVE_SELECTION_QUARANTINE_SOURCE_INVALID")
    source_path = Path(source_value)
    if not source_path.is_absolute():
        source_path = REPOSITORY_ROOT / source_path
    source_path = _inside(
        local_reviews / "production_registry",
        source_path,
        code="ACTIVE_SELECTION_QUARANTINE_SOURCE_OUTSIDE_REGISTRY",
    )
    if not source_path.is_file():
        raise IntakeViolation("ACTIVE_SELECTION_QUARANTINE_SOURCE_MISSING")

    state_dir = root / POINTER_DIRECTORY
    source_registry_path = state_dir / SOURCE_REGISTRY_FILENAME
    inventory_path = state_dir / MATERIAL_BANK_INVENTORY_FILENAME
    package_registry_path = state_dir / REGISTRY_FILENAME
    active_pointer_path = state_dir / ACTIVE_POINTER_FILENAME
    content_id = str(package.metadata.get("content_id") or "")
    content_slug = str(package.metadata.get("content_slug") or "")
    relative_package = package.package_dir.relative_to(root).as_posix()
    clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    timestamp = clock.strftime("%Y%m%dT%H%M%SZ")
    quarantine_root = state_dir / "quarantine" / timestamp / f"{content_id}_{content_slug}"

    with _exclusive_allocation_lock(state_dir):
        current = resolve_active_package(root)
        _assert_expected_content_id(current, expected_content_id)
        if current.package_dir != package.package_dir:
            raise IntakeViolation("ACTIVE_PACKAGE_CONTENT_ID_MISMATCH")
        source_registry = _load_source_registry(source_registry_path)
        inventory = _load_material_bank_inventory(inventory_path)
        package_registry = _load_package_registry(root)
        source_matches = [
            record
            for record in source_registry["records"]
            if isinstance(record, dict)
            and record.get("content_id") == content_id
            and record.get("candidate_reference") == candidate_id
        ]
        inventory_matches = [
            record
            for record in inventory["records"]
            if isinstance(record, dict)
            and record.get("content_id") == content_id
            and record.get("candidate_reference") == candidate_id
        ]
        if len(source_matches) != 1 or len(inventory_matches) != 1:
            raise IntakeViolation("ACTIVE_SELECTION_QUARANTINE_BINDING_INVALID")
        if quarantine_root.exists():
            raise IntakeViolation("ACTIVE_SELECTION_QUARANTINE_DESTINATION_EXISTS")

        before_dir = quarantine_root / "before"
        before_dir.mkdir(parents=True)
        state_paths = [
            active_pointer_path,
            package_registry_path,
            source_registry_path,
            inventory_path,
        ]
        for state_path in state_paths:
            if not state_path.is_file():
                raise IntakeViolation("ACTIVE_SELECTION_QUARANTINE_STATE_FILE_MISSING")
            shutil.copy2(state_path, before_dir / state_path.name)

        moved_package = quarantine_root / "output" / package.package_dir.name
        moved_source = (
            quarantine_root / "reviews" / "production_registry" / source_path.name
        )
        moved_package.parent.mkdir(parents=True)
        moved_source.parent.mkdir(parents=True)
        source_registry["records"] = [
            record for record in source_registry["records"] if record not in source_matches
        ]
        inventory["records"] = [
            record for record in inventory["records"] if record not in inventory_matches
        ]
        package_registry["packages"] = [
            record
            for record in package_registry["packages"]
            if not (
                isinstance(record, dict)
                and record.get("package_relative_path") == relative_package
            )
        ]
        package_registry["active_package_relative_path"] = None

        try:
            package.package_dir.rename(moved_package)
            source_path.rename(moved_source)
            _atomic_write_json(source_registry_path, source_registry)
            _atomic_write_json(inventory_path, inventory)
            _atomic_write_json(package_registry_path, package_registry)
            active_pointer_path.unlink()
            manifest = {
                "schema_version": "review-reel-selection-quarantine-v1",
                "workflow": "review_reel_production",
                "status": "quarantined",
                "reason_code": reason_code,
                "quarantined_at": clock.isoformat(),
                "content_id": content_id,
                "content_slug": content_slug,
                "candidate_reference": candidate_id,
                "identity": package.metadata.get("identity"),
                "original_paths": [str(package.package_dir), str(source_path)],
                "quarantine_paths": [str(moved_package), str(moved_source)],
                "registry_backups": [
                    {
                        "path": str(before_dir / state_path.name),
                        "bytes": (before_dir / state_path.name).stat().st_size,
                        "sha256": hashlib.sha256(
                            (before_dir / state_path.name).read_bytes()
                        ).hexdigest(),
                    }
                    for state_path in state_paths
                ],
                "restore_hint": (
                    "Move the quarantined package and source back to original_paths, "
                    "then restore all four files from registry_backups."
                ),
            }
            _atomic_write_json(quarantine_root / "manifest.json", manifest)
        except Exception as error:
            try:
                if moved_source.exists() and not source_path.exists():
                    source_path.parent.mkdir(parents=True, exist_ok=True)
                    moved_source.rename(source_path)
                if moved_package.exists() and not package.package_dir.exists():
                    package.package_dir.parent.mkdir(parents=True, exist_ok=True)
                    moved_package.rename(package.package_dir)
                for state_path in state_paths:
                    backup = before_dir / state_path.name
                    if backup.is_file():
                        shutil.copy2(backup, state_path)
                _atomic_write_json(
                    quarantine_root / "rollback.json",
                    {
                        "schema_version": "review-reel-selection-quarantine-rollback-v1",
                        "status": "rolled_back_after_failure",
                        "error_type": type(error).__name__,
                    },
                )
            except Exception as rollback_error:
                raise IntakeViolation("ACTIVE_SELECTION_QUARANTINE_ROLLBACK_FAILED") from rollback_error
            raise IntakeViolation("ACTIVE_SELECTION_QUARANTINE_FAILED") from error

    return {
        "workflow": "review_reel_production",
        "status": "quarantined",
        "content_id": content_id,
        "candidate_reference": candidate_id,
        "quarantine_root": str(quarantine_root.resolve()),
        "manifest": str((quarantine_root / "manifest.json").resolve()),
        "next_action": "run_candidate_shortlist_then_select_a_new_candidate",
    }


def _pointer_payload(output_root: Path, package: CanonicalPackage, *, updated_at: str) -> dict[str, Any]:
    relative_package = package.package_dir.resolve().relative_to(output_root.resolve()).as_posix()
    return {
        "schema_version": "review-reel-active-pointer-v1",
        "workflow": "review_reel_production",
        "package_relative_path": relative_package,
        "package_name": package.package_dir.name,
        "content_id": package.metadata["content_id"],
        "image_directory_name": package.image_dir.name,
        "metadata_sha256": hashlib.sha256(
            (package.package_dir / METADATA_FILENAME).read_bytes()
        ).hexdigest(),
        "updated_at": updated_at,
    }


def _load_package_registry(output_root: Path) -> dict[str, Any]:
    registry_path = output_root / POINTER_DIRECTORY / REGISTRY_FILENAME
    if not registry_path.exists():
        return {"schema_version": "review-reel-production-registry-v1", "packages": []}
    registry = _read_json(
        registry_path,
        missing="REGISTRY_MISSING",
        invalid="REGISTRY_INVALID",
    )
    if registry.get("schema_version") != "review-reel-production-registry-v1":
        raise IntakeViolation("REGISTRY_SCHEMA_INVALID")
    if not isinstance(registry.get("packages"), list):
        raise IntakeViolation("REGISTRY_PACKAGES_INVALID")
    return registry


def _set_active_package(output_root: Path, package: CanonicalPackage, *, updated_at: str) -> None:
    state_dir = output_root / POINTER_DIRECTORY
    registry_path = state_dir / REGISTRY_FILENAME
    registry = _load_package_registry(output_root)
    pointer = _pointer_payload(output_root, package, updated_at=updated_at)
    records = registry.get("packages")
    records = [record for record in records if isinstance(record, dict) and record.get("package_relative_path") != pointer["package_relative_path"]]
    records.append(
        {
            "package_relative_path": pointer["package_relative_path"],
            "package_name": pointer["package_name"],
            "content_id": pointer["content_id"],
            "updated_at": updated_at,
        }
    )
    _atomic_write_json(
        registry_path,
        {
            "schema_version": "review-reel-production-registry-v1",
            "active_package_relative_path": pointer["package_relative_path"],
            "packages": sorted(records, key=lambda record: (record["updated_at"], record["package_relative_path"])),
        },
    )
    _atomic_write_json(state_dir / ACTIVE_POINTER_FILENAME, pointer)


def create_canonical_package(
    *,
    output_root: str | Path,
    inventory_path: str | Path,
    record_key: str,
    now: datetime | None = None,
) -> CanonicalPackage:
    """Create one canonical pre-photo package from an explicit inventory record.

    Content IDs are never calculated.  The selected inventory record is the
    only authority that can provide the numeric ID and its source binding.
    """

    root = Path(output_root).resolve()
    inventory = Path(inventory_path).resolve()
    _load_package_registry(root)
    record, source_path = _resolve_inventory_record(inventory, record_key)
    identity = _identity(record)
    clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    timestamp = clock.strftime("%Y%m%d_%H%M%S")
    package_name = f"{record['content_id']}_{record['content_slug']}_{timestamp}"
    image_name = f"{record['content_id']}_{record['content_slug']}_이미지"
    if _CANDIDATE_PREFIX in package_name.upper() or _CANDIDATE_PREFIX in image_name.upper():
        raise IntakeViolation("CANDIDATE_NAME_EXPOSURE_FORBIDDEN")

    existing = _find_existing(root, identity)
    if existing is not None:
        _set_active_package(root, existing, updated_at=clock.isoformat())
        return existing

    collection = root
    package_dir = root / package_name
    if package_dir.exists():
        raise IntakeViolation("CANONICAL_PACKAGE_NAME_COLLISION")

    relative_package = package_dir.relative_to(root).as_posix()
    metadata = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "workflow": "review_reel_production",
        "lifecycle_state": "photo_intake_pending",
        "created_at": clock.isoformat(),
        "content_id": record["content_id"],
        "content_slug": record["content_slug"],
        "package_name": package_name,
        "package_relative_path": relative_package,
        "image_directory_name": image_name,
        "identity": identity,
        "review_source": {
            "path": str(source_path),
            "text": record["review_text"],
            "text_sha256": identity["review_text_sha256"],
            "product_order_number": record["product_order_number"],
            "review_article_id": record["review_article_id"],
            "source_reference": record["source_reference"],
            "candidate_reference": record.get("candidate_reference"),
        },
        "approvals": {
            "photo_checked": False,
            "pd_plan_approved": False,
            "html_scope_authorized": False,
            "mp4_scope_authorized": False,
        },
        "current_artifacts_contract": "review-reel-current-artifacts-v1",
    }

    collection.mkdir(parents=True, exist_ok=True)
    pending_dir = collection / f".{package_name}.pending-{uuid4().hex}"
    pending_dir.mkdir()
    image_dir = pending_dir / image_name
    image_dir.mkdir()
    _atomic_write_json(pending_dir / METADATA_FILENAME, metadata)
    from video_engine_v2.current_artifacts import CurrentArtifactsViolation, initialize_ledger

    try:
        initialize_ledger(pending_dir, now=clock, identity_dir=package_dir)
    except CurrentArtifactsViolation as error:
        raise IntakeViolation(str(error)) from error
    (pending_dir / ".source").write_text(_generation_source_key(source_path), encoding="utf-8")
    (pending_dir / "STATUS.md").write_text(
        "- photo_checked: false\n- pd_plan_approved: false\n- html_approved_by_user: false\n- mp4_allowed: false\n",
        encoding="utf-8",
    )
    (pending_dir / "APPROVAL_LOG.md").write_text(
        "- not_approved: photo review pending\n- not_approved: PD planning pending\n- not_approved: MP4 render pending\n",
        encoding="utf-8",
    )
    try:
        pending_dir.rename(package_dir)
    except FileExistsError as error:
        raise IntakeViolation("CANONICAL_PACKAGE_NAME_COLLISION") from error

    package = CanonicalPackage(package_dir.resolve(), (package_dir / image_name).resolve(), metadata, reused_existing=False)
    _set_active_package(root, package, updated_at=clock.isoformat())
    return package


def resolve_active_package(output_root: str | Path) -> CanonicalPackage:
    """Resolve the managed pointer without scanning arbitrary output packages."""

    root = Path(output_root).resolve()
    pointer_path = root / POINTER_DIRECTORY / ACTIVE_POINTER_FILENAME
    pointer = _read_json(pointer_path, missing="ACTIVE_PACKAGE_POINTER_MISSING", invalid="ACTIVE_PACKAGE_POINTER_INVALID")
    if pointer.get("schema_version") != "review-reel-active-pointer-v1":
        raise IntakeViolation("ACTIVE_PACKAGE_POINTER_SCHEMA_INVALID")
    relative_package = pointer.get("package_relative_path")
    if not isinstance(relative_package, str) or not relative_package.strip() or Path(relative_package).is_absolute():
        raise IntakeViolation("ACTIVE_PACKAGE_POINTER_PATH_INVALID")
    package_dir = _inside(root, root / relative_package, code="ACTIVE_PACKAGE_OUTSIDE_OUTPUT_ROOT")
    metadata = _read_metadata(package_dir, code_prefix="ACTIVE_PACKAGE")
    if metadata.get("package_name") != pointer.get("package_name"):
        raise IntakeViolation("ACTIVE_PACKAGE_IDENTITY_MISMATCH")
    if metadata.get("package_relative_path") != relative_package.replace("\\", "/"):
        raise IntakeViolation("ACTIVE_PACKAGE_PATH_MISMATCH")
    metadata_hash = hashlib.sha256((package_dir / METADATA_FILENAME).read_bytes()).hexdigest()
    if pointer.get("metadata_sha256") != metadata_hash:
        raise IntakeViolation("ACTIVE_PACKAGE_METADATA_HASH_MISMATCH")
    image_name = metadata.get("image_directory_name")
    if (
        not isinstance(image_name, str)
        or Path(image_name).is_absolute()
        or Path(image_name).name != image_name
        or _CANDIDATE_PREFIX in image_name.upper()
    ):
        raise IntakeViolation("ACTIVE_PACKAGE_IMAGE_DIRECTORY_INVALID")
    image_dir = _inside(package_dir, package_dir / image_name, code="ACTIVE_PACKAGE_IMAGE_OUTSIDE_PACKAGE")
    if not image_dir.is_dir():
        raise IntakeViolation("ACTIVE_PACKAGE_IMAGE_DIRECTORY_MISSING")
    if _CANDIDATE_PREFIX in package_dir.name.upper():
        raise IntakeViolation("CANDIDATE_NAME_EXPOSURE_FORBIDDEN")
    return CanonicalPackage(package_dir, image_dir, metadata, reused_existing=True)


def _assert_expected_content_id(package: CanonicalPackage, expected_content_id: str) -> None:
    expected = str(expected_content_id).strip()
    actual = str(package.metadata.get("content_id") or "").strip()
    if not expected or expected != actual:
        raise IntakeViolation("ACTIVE_PACKAGE_CONTENT_ID_MISMATCH")


def _evaluate_html_candidate(package: Path, html_path: Path) -> dict[str, Any]:
    from video_engine_v2.production_gate import inspect_html_preview_chain

    return inspect_html_preview_chain(package, html_path)


def _bound_html_review_receipt(package: Path, html_path: Path, artifact_path: Path) -> Path | None:
    from video_engine_v2.production_gate import find_current_html_manual_review

    receipt = find_current_html_manual_review(package, html_path)
    if receipt is None:
        return None
    if html_path.parent / "html_artifact_evidence.json" != artifact_path:
        return None
    return receipt


def _html_approval_bound(package: Path, html_path: Path, artifact_path: Path) -> bool:
    from video_engine_v2.production_gate import html_approval_is_current

    if html_path.parent / "html_artifact_evidence.json" != artifact_path:
        return False
    return html_approval_is_current(package, html_path)


def _mp4_approval_bound(package: Path, html_path: Path) -> bool:
    from video_engine_v2.production_gate import mp4_approval_is_current

    return mp4_approval_is_current(package, html_path)


def _ledger_pointer_path(package: Path, ledger: dict[str, Any], kind: str) -> Path | None:
    pointer = (ledger.get("pointers") or {}).get(kind)
    if not isinstance(pointer, dict) or not isinstance(pointer.get("relative_path"), str):
        return None
    return (package / pointer["relative_path"]).resolve()


def _select_current_html(package: Path) -> dict[str, Any]:
    from video_engine_v2.current_artifacts import (
        CurrentArtifactsViolation,
        package_uses_ledger,
        pointer_file,
        require_enabled_ledger,
    )

    ledger: dict[str, Any] | None = None
    if package_uses_ledger(package):
        try:
            ledger = require_enabled_ledger(package)
            html_pointer = pointer_file(package, "html")
        except CurrentArtifactsViolation as error:
            return {
                "status": "stale_html",
                "html_status": "stale_html",
                "stale_html_reason": str(error).lower(),
            }
        if html_pointer is None:
            return {"status": "absent"}
        expected_artifact = html_pointer.parent / "html_artifact_evidence.json"
        expected_qa = html_pointer.parent / "html_internal_qa_report.json"
        if (
            _ledger_pointer_path(package, ledger, "html_artifact_evidence") != expected_artifact
            or _ledger_pointer_path(package, ledger, "html_qa_report") != expected_qa
        ):
            return {
                "status": "stale_html",
                "html_status": "stale_html",
                "stale_html_reason": "html_ledger_chain_incomplete",
            }
        candidates = [_evaluate_html_candidate(package, html_pointer)]
    else:
        candidates = [
            _evaluate_html_candidate(package, html.resolve())
            for html in sorted(package.glob("*_html_preview_v2/index.html"))
        ]
    if not candidates:
        return {"status": "absent"}
    valid = [item for item in candidates if item.get("status") == "valid"]
    if not valid:
        return {
            "status": "stale_html",
            "html_status": "stale_html",
            "stale_html_reason": str(candidates[0].get("stale_html_reason") or "html_evidence_invalid"),
            "stale_html_reasons": [
                {
                    "html_relative_path": item.get("html_relative_path"),
                    "stale_html_reason": item.get("stale_html_reason"),
                }
                for item in candidates
            ],
        }
    approval_bound = [item for item in valid if _html_approval_bound(package, item["html"], item["artifact_path"])]
    review_bound = [
        item for item in valid if _bound_html_review_receipt(package, item["html"], item["artifact_path"]) is not None
    ]
    if len(approval_bound) > 1 or (not approval_bound and len(valid) > 1 and len(review_bound) != 1):
        return {
            "status": "stale_html",
            "html_status": "stale_html",
            "stale_html_reason": "ambiguous_html_candidates",
            "stale_html_reasons": [
                {"html_relative_path": item.get("html_relative_path"), "stale_html_reason": "ambiguous_html_candidates"}
                for item in valid
            ],
        }
    current = approval_bound[0] if len(approval_bound) == 1 else review_bound[0] if len(review_bound) == 1 else valid[0]
    review_path = _bound_html_review_receipt(package, current["html"], current["artifact_path"])
    html_approved = _html_approval_bound(package, current["html"], current["artifact_path"])
    mp4_approved = _mp4_approval_bound(package, current["html"])
    if ledger is not None:
        if _ledger_pointer_path(package, ledger, "html_manual_review") != review_path:
            review_path = None
        html_approval_path = _ledger_pointer_path(package, ledger, "html_approval")
        if html_approval_path != (package / "HTML_APPROVAL.json").resolve():
            html_approved = False
        mp4_approval_path = _ledger_pointer_path(package, ledger, "mp4_render_approval")
        if (
            not html_approved
            or mp4_approval_path != (package / "MP4_RENDER_APPROVAL.json").resolve()
        ):
            mp4_approved = False
    current.update(
        {
            "html_status": "valid",
            "manual_review_path": review_path,
            "html_approved": html_approved,
            "mp4_approved": mp4_approved,
        }
    )
    return current


def active_package_status(output_root: str | Path) -> dict[str, Any]:
    """Return the active canonical identity and its next safe production action."""

    package = resolve_active_package(output_root)
    lifecycle_state = str(package.metadata.get("lifecycle_state") or "unknown")
    from video_engine_v2.package_state import map_package_state

    evidence_state = map_package_state(package.package_dir)
    html_state = _select_current_html(package.package_dir)
    if evidence_state.get("final_delivery_complete") is True:
        next_action = "no_action_final_delivery_complete"
    elif evidence_state.get("render_complete") is True:
        next_action = "inspect_post_render_frames_then_run_render_review_record"
    elif evidence_state.get("render_artifact_present") is True:
        next_action = "inspect_render_job_then_run_post_render_qa"
    elif html_state.get("status") == "valid" and html_state.get("mp4_approved"):
        next_action = "start_or_check_durable_render_job"
    elif html_state.get("status") == "valid" and html_state.get("html_approved"):
        next_action = "wait_for_explicit_mp4_approval_then_record_it"
    elif lifecycle_state == "photo_intake_pending":
        next_action = "place_photos_then_run_photo_review"
    elif lifecycle_state == "photo_reviewed":
        next_action = "prepare_planning_script_tts"
    else:
        next_action = "inspect_package_state_before_mutation"
    return {
        "workflow": "review_reel_production",
        "content_id": str(package.metadata.get("content_id") or ""),
        "lifecycle_state": lifecycle_state,
        "package": str(package.package_dir),
        "image_directory": str(package.image_dir),
        "render_complete": evidence_state.get("render_complete", "unknown"),
        "qa_reviewed": evidence_state.get("qa_reviewed", "unknown"),
        "final_delivery_complete": evidence_state.get("final_delivery_complete", "unknown"),
        "next_action": next_action,
    }


def workflow_next(output_root: str | Path) -> dict[str, Any]:
    """Explain the next legal transition without fabricating missing inputs or approvals."""

    root = Path(output_root).resolve()
    status = dict(active_package_status(root))
    content_id = str(status.get("content_id") or "")
    package_value = status.get("package")
    package = Path(str(package_value)).resolve() if package_value else None
    action = str(status.get("next_action") or "")
    guidance: dict[str, Any] = {
        **status,
        "approval_required": False,
        "next_command": None,
        "required_inputs": [],
    }

    if action == "place_photos_then_run_photo_review":
        guidance["required_inputs"] = ["selection", "privacy_manifest"]
        guidance["command_template"] = (
            f'python scripts/review_reel_intake.py photo-review --output-root "{root}" '
            f'--expected-content-id "{content_id}" --selection "<selection.json>" '
            '--privacy-manifest "<privacy_asset_manifest.json>"'
        )
    elif action == "prepare_planning_script_tts":
        html_state = _select_current_html(package) if package else {"status": "absent"}
        if html_state.get("status") == "valid":
            html_path = Path(html_state["html"])
            guidance["html"] = str(html_path)
            guidance["html_status"] = "valid"
            if html_state.get("manual_review_path") is None:
                guidance["next_action"] = "inspect_html_frames_then_record_review"
                guidance["required_inputs"] = ["reviewer", "html_review_evidence"]
                guidance["command_template"] = (
                    f'python scripts/produce_review_v2.py html-review-record --package "{package}" '
                    f'--html "{html_path}" --reviewer "<reviewer>" --evidence-reference "<evidence>" '
                    '--check hook_sequence_reviewed --check meaning_sync_reviewed '
                    '--check caption_layout_reviewed --check privacy_reviewed '
                    '--check review_capture_reviewed --check review_underline_alignment_reviewed --check cta_reviewed'
                )
                return guidance
            if not html_state.get("html_approved"):
                guidance["next_action"] = "wait_for_explicit_html_approval_then_record_it"
                guidance["approval_required"] = True
                guidance["required_inputs"] = ["explicit_user_html_approval", "current_html"]
                return guidance
            if not html_state.get("mp4_approved"):
                guidance["next_action"] = "wait_for_explicit_mp4_approval_then_record_it"
                guidance["approval_required"] = True
                guidance["required_inputs"] = ["explicit_user_mp4_approval", "current_html"]
                return guidance
            guidance["next_action"] = "start_or_check_durable_render_job"
            guidance["required_inputs"] = ["current_hash_bound_artifact_paths"]
            return guidance
        if html_state.get("status") == "stale_html":
            guidance["next_action"] = "stale_html"
            guidance["html_status"] = "stale_html"
            guidance["stale_html_reason"] = html_state.get("stale_html_reason")
            guidance["stale_html_reasons"] = html_state.get("stale_html_reasons")
            guidance["required_inputs"] = ["current_html_artifact_evidence"]
            return guidance
        scaffold_root = package / "_work" / "recipe_scaffolds" if package else None
        revisions = sorted(scaffold_root.glob("revision_*")) if scaffold_root and scaffold_root.is_dir() else []
        if not revisions:
            guidance["next_action"] = "generate_recipe_scaffold"
            guidance["next_command"] = (
                f'python scripts/review_reel_intake.py recipe-scaffold --output-root "{root}" '
                f'--expected-content-id "{content_id}"'
            )
        else:
            revision = revisions[-1]
            planning_paths = sorted(revision.glob("*_planning_recipe_scaffold.json"))
            edit_paths = sorted(revision.glob("*_edit_recipe_scaffold.json"))
            if len(planning_paths) != 1 or len(edit_paths) != 1:
                guidance["next_action"] = "repair_recipe_scaffold_artifacts"
                guidance["required_inputs"] = ["one_planning_scaffold", "one_edit_scaffold"]
                return guidance
            planning_path, edit_path = planning_paths[0].resolve(), edit_paths[0].resolve()
            planning_payload = _read_json(
                planning_path,
                missing="RECIPE_SCAFFOLD_MISSING",
                invalid="RECIPE_SCAFFOLD_INVALID",
            )
            edit_payload = _read_json(
                edit_path,
                missing="RECIPE_SCAFFOLD_MISSING",
                invalid="RECIPE_SCAFFOLD_INVALID",
            )
            planning_state = planning_payload.get("scaffold") or {}
            edit_state = edit_payload.get("scaffold") or {}
            completed = all(
                state.get("status") == "complete" and state.get("pending_fields") == []
                for state in (planning_state, edit_state)
            )
            if not completed:
                guidance["next_action"] = "complete_scaffold_content_then_write_standard_script"
                guidance["required_inputs"] = ["review_grounded_content", "voice_timing", "standard_script"]
                guidance["planning"] = str(planning_path)
                guidance["edit"] = str(edit_path)
                return guidance

            from video_engine_v2.reels_qa import validate_review_reels_one_shot_contract

            source = edit_payload.get("source") or {}
            script_path = _inside(package, package / str(source.get("script") or ""), code="WORKFLOW_SCRIPT_PATH_INVALID")
            srt_path = _inside(package, package / str(source.get("srt") or ""), code="WORKFLOW_SRT_PATH_INVALID")
            voice_path = _inside(package, package / str(source.get("voice") or ""), code="WORKFLOW_VOICE_PATH_INVALID")
            tts_report_path = _inside(
                package,
                package / str(source.get("tts_generation_report") or ""),
                code="WORKFLOW_TTS_REPORT_PATH_INVALID",
            )
            scaffold_qa = validate_review_reels_one_shot_contract(planning_payload, edit_payload)
            blocking_issues = [
                issue for issue in scaffold_qa.get("issues") or []
                if isinstance(issue, dict) and issue.get("severity") == "fail"
            ]
            if not script_path.is_file():
                blocking_issues = [
                    issue for issue in blocking_issues
                    if issue.get("code") != "SCRIPT_REVIEW_BINDING_MISSING"
                ]
            if blocking_issues:
                issue_codes = [str(issue.get("code") or "") for issue in blocking_issues]
                if set(issue_codes) == {"SCRIPT_REVIEW_BINDING_MISSING"}:
                    guidance["next_action"] = "record_hash_bound_script_review"
                    guidance["required_inputs"] = ["script_reviewer", "review_evidence", "script_sha256"]
                    guidance["script"] = str(script_path)
                    guidance["planning"] = str(planning_path)
                    guidance["blocking_issue_codes"] = issue_codes
                    guidance["issues"] = blocking_issues
                    return guidance
                guidance["next_action"] = "repair_recipe_scaffold_qa_issues"
                guidance["blocking_issue_codes"] = issue_codes
                guidance["issues"] = blocking_issues
                guidance["explain_command_template"] = (
                    'python scripts/review_reel_intake.py explain-error --code "<issue-code>"'
                )
                return guidance

            from video_engine_v2.current_artifacts import package_uses_ledger, read_ledger

            ledger_mode = package_uses_ledger(package)
            ledger = read_ledger(package) if ledger_mode else None
            if not script_path.is_file():
                guidance["next_action"] = "write_standard_script_from_completed_scaffold"
                guidance["required_inputs"] = ["standard_script"]
                guidance["script"] = str(script_path)
                return guidance
            reviewed_script_sha256 = str((planning_payload.get("script_review") or {}).get("script_sha256") or "")
            current_script_sha256 = hashlib.sha256(script_path.read_bytes()).hexdigest()
            if reviewed_script_sha256 != current_script_sha256:
                guidance["next_action"] = "record_hash_bound_script_review"
                guidance["required_inputs"] = ["script_reviewer", "review_evidence", "script_sha256"]
                guidance["script"] = str(script_path)
                guidance["planning"] = str(planning_path)
                guidance["current_script_sha256"] = current_script_sha256
                guidance["blocking_issue_codes"] = ["SCRIPT_REVIEW_HASH_MISMATCH"]
                return guidance
            tts_paths = {
                "script": script_path,
                "captions": srt_path,
                "voice": voice_path,
                "tts_report": tts_report_path,
            }
            tts_current = all(
                _ledger_pointer_path(package, ledger, kind) == path
                for kind, path in tts_paths.items()
            ) if ledger is not None else all(path.is_file() for path in (srt_path, voice_path, tts_report_path))
            if not tts_current:
                guidance["next_action"] = "generate_official_one_shot_tts"
                guidance["next_command"] = (
                    f'python scripts/generate_one_shot_tts.py --package "{package}" '
                    f'--planning "{planning_path}" --edit "{edit_path}" --script "{script_path}"'
                )
                return guidance
            from video_engine_v2.production_gate import find_current_voice_manual_review

            current_voice_review = find_current_voice_manual_review(package, edit_payload)
            if ledger is not None and _ledger_pointer_path(package, ledger, "voice_manual_review") != current_voice_review:
                current_voice_review = None
            if current_voice_review is None:
                guidance["next_action"] = "listen_to_voice_then_record_review"
                guidance["required_inputs"] = ["reviewer", "voice_review_evidence"]
                guidance["command_template"] = (
                    f'python scripts/produce_review_v2.py voice-review-record --package "{package}" '
                    f'--voice "{voice_path}" --srt "{srt_path}" --tts-report "{tts_report_path}" '
                    '--reviewer "<reviewer>" --evidence-reference "<evidence>" '
                    '--check pronunciation_clear --check tone_approved --check caption_sync_approved'
                )
                return guidance
            photo_review = resolve_active_package(root).metadata.get("photo_review") or {}
            privacy_evidence = photo_review.get("privacy_manifest") or {}
            privacy_path = _inside(
                package,
                package / str(privacy_evidence.get("relative_path") or ""),
                code="WORKFLOW_PRIVACY_MANIFEST_PATH_INVALID",
            )
            if ledger is not None and _ledger_pointer_path(package, ledger, "privacy_manifest") != privacy_path:
                guidance["next_action"] = "stale_current_artifacts"
                guidance["stale_artifact_kind"] = "privacy_manifest"
                guidance["required_inputs"] = ["rerun_photo_review_with_current_privacy_manifest"]
                return guidance
            sync_pointer = _ledger_pointer_path(package, ledger, "sync_manifest") if ledger is not None else None
            sync_path = sync_pointer or package / "sync_manifest.json"
            if (ledger is not None and sync_pointer is None) or not sync_path.is_file():
                guidance["next_action"] = "run_one_shot_preflight"
                guidance["next_command"] = (
                    f'python scripts/produce_review_v2.py preflight --package "{package}" '
                    f'--planning "{planning_path}" --edit "{edit_path}" --privacy-manifest "{privacy_path}" '
                    f'--sync-manifest "{sync_path}" --one-shot-html'
                )
                return guidance
            if ledger_mode:
                promoted_recipes = {
                    "planning_recipe": planning_path,
                    "edit_recipe": edit_path,
                }
                for kind, expected_path in promoted_recipes.items():
                    if _ledger_pointer_path(package, ledger, kind) != expected_path:
                        guidance["next_action"] = "stale_current_artifacts"
                        guidance["stale_artifact_kind"] = kind
                        guidance["required_inputs"] = ["rerun_preflight_with_current_recipes"]
                        return guidance
                guidance["next_action"] = "build_one_shot_html"
                guidance["next_command"] = (
                    f'python scripts/produce_review_v2.py html --package "{package}" '
                    f'--planning "{planning_path}" --edit "{edit_path}" --privacy-manifest "{privacy_path}" '
                    f'--sync-manifest "{sync_path}" --one-shot-html'
                )
                return guidance
            html_paths = sorted(package.glob("*_html_preview_v2/index.html"))
            if not html_paths:
                guidance["next_action"] = "build_one_shot_html"
                guidance["next_command"] = (
                    f'python scripts/produce_review_v2.py html --package "{package}" '
                    f'--planning "{planning_path}" --edit "{edit_path}" --privacy-manifest "{privacy_path}" '
                    f'--sync-manifest "{sync_path}" --one-shot-html'
                )
                return guidance
            html_path = html_paths[-1].resolve()
            if not any(manual_reviews.glob("html_review_*.json")):
                guidance["next_action"] = "inspect_html_frames_then_record_review"
                guidance["required_inputs"] = ["reviewer", "html_review_evidence"]
                guidance["command_template"] = (
                    f'python scripts/produce_review_v2.py html-review-record --package "{package}" '
                    f'--html "{html_path}" --reviewer "<reviewer>" --evidence-reference "<evidence>" '
                    '--check hook_sequence_reviewed --check meaning_sync_reviewed '
                    '--check caption_layout_reviewed --check privacy_reviewed '
                    '--check review_capture_reviewed --check review_underline_alignment_reviewed --check cta_reviewed'
                )
                return guidance
            guidance["next_action"] = "wait_for_explicit_html_approval_then_record_it"
            guidance["approval_required"] = True
            guidance["required_inputs"] = ["explicit_user_html_approval", "current_html"]
            guidance["html"] = str(html_path)
    elif action == "wait_for_explicit_mp4_approval_then_record_it":
        guidance["approval_required"] = True
        guidance["required_inputs"] = ["explicit_user_mp4_approval", "current_html"]
    elif action == "no_action_final_delivery_complete":
        guidance["new_production_action"] = "select_then_check_material_bank_candidate"
        guidance["new_production_command_template"] = (
            f'python scripts/review_reel_intake.py candidate-check --output-root "{root}" '
            '--reviews-root "<reviews>" --material-bank "<candidate_top60_private.jsonl>" '
            '--candidate-id "<CAND-id>"'
        )
    elif action in {
        "start_or_check_durable_render_job",
        "inspect_render_job_then_run_post_render_qa",
        "inspect_post_render_frames_then_run_render_review_record",
    }:
        guidance["required_inputs"] = ["current_hash_bound_artifact_paths"]
    else:
        guidance["required_inputs"] = ["inspect_current_package_state"]
    return guidance


def write_recipe_scaffold(*, output_root: str | Path, expected_content_id: str) -> dict[str, Any]:
    """Write one non-overwriting recipe starting point from current photo-review evidence."""

    package = resolve_active_package(output_root)
    _assert_expected_content_id(package, expected_content_id)
    if package.metadata.get("lifecycle_state") != "photo_reviewed":
        raise IntakeViolation("RECIPE_SCAFFOLD_REQUIRES_PHOTO_REVIEW")
    photo_review = package.metadata.get("photo_review")
    if not isinstance(photo_review, dict):
        raise IntakeViolation("RECIPE_SCAFFOLD_PHOTO_REVIEW_EVIDENCE_MISSING")
    _validated_photo_review_evidence_paths(package_dir=package.package_dir, records=[photo_review])
    selection_evidence = photo_review.get("selection")
    if not isinstance(selection_evidence, dict):
        raise IntakeViolation("RECIPE_SCAFFOLD_PHOTO_REVIEW_EVIDENCE_MISSING")
    selection_relative = selection_evidence.get("relative_path")
    if not isinstance(selection_relative, str) or not selection_relative.strip():
        raise IntakeViolation("RECIPE_SCAFFOLD_PHOTO_REVIEW_EVIDENCE_MISSING")
    selection_path = _inside(
        package.package_dir,
        package.package_dir / selection_relative,
        code="RECIPE_SCAFFOLD_PHOTO_REVIEW_EVIDENCE_MISSING",
    )
    selection = _read_json(
        selection_path,
        missing="RECIPE_SCAFFOLD_PHOTO_REVIEW_EVIDENCE_MISSING",
        invalid="RECIPE_SCAFFOLD_PHOTO_REVIEW_EVIDENCE_INVALID",
    )
    selected_assets: list[dict[str, Any]] = []
    for decision in selection.get("decisions") or []:
        if not isinstance(decision, dict) or decision.get("decision") != "use":
            continue
        selected_relative = decision.get("selected_relative_path", decision.get("relative_path"))
        selected_assets.append(
            {
                "relative_path": selected_relative,
                "evidence_classes": list(decision.get("evidence_classes") or []),
                "visual_quality": dict(decision.get("visual_quality") or {}),
            }
        )
    try:
        planning, edit = build_recipe_scaffold(
            content_id=str(package.metadata.get("content_id") or ""),
            review_text=str((package.metadata.get("review_source") or {}).get("text") or ""),
            selected_assets=selected_assets,
        )
    except ValueError as error:
        raise IntakeViolation(str(error)) from error

    privacy_evidence = photo_review.get("privacy_manifest")
    if not isinstance(privacy_evidence, dict) or not isinstance(privacy_evidence.get("relative_path"), str):
        raise IntakeViolation("RECIPE_SCAFFOLD_PHOTO_REVIEW_EVIDENCE_MISSING")
    privacy_path = _inside(
        package.package_dir,
        package.package_dir / privacy_evidence["relative_path"],
        code="RECIPE_SCAFFOLD_PHOTO_REVIEW_EVIDENCE_MISSING",
    )
    privacy_manifest = _read_json(
        privacy_path,
        missing="RECIPE_SCAFFOLD_PHOTO_REVIEW_EVIDENCE_MISSING",
        invalid="RECIPE_SCAFFOLD_PHOTO_REVIEW_EVIDENCE_INVALID",
    )
    sanitization_report = privacy_manifest.get("sanitization_report")
    if not isinstance(sanitization_report, str) or not sanitization_report.strip():
        raise IntakeViolation("RECIPE_SCAFFOLD_PRIVACY_REPORT_MISSING")
    edit["source"]["privacy_sanitization_report"] = sanitization_report

    revision = photo_review.get("revision")
    if not isinstance(revision, int) or revision < 1:
        revision = 1
    scaffold_binding = {
        "source_photo_review_revision": revision,
        "source_selection_sha256": selection_evidence.get("sha256"),
    }
    planning["scaffold"].update(scaffold_binding)
    edit["scaffold"].update(scaffold_binding)
    parent = package.package_dir / "_work" / "recipe_scaffolds"
    revision_name = f"revision_{revision:03d}"
    target = parent / revision_name
    if target.exists():
        raise IntakeViolation("RECIPE_SCAFFOLD_ALREADY_EXISTS")
    pending = parent / f".{revision_name}.pending-{uuid4().hex}"
    pending.mkdir(parents=True)
    planning_path = pending / f"{package.metadata['content_id']}_planning_recipe_scaffold.json"
    edit_path = pending / f"{package.metadata['content_id']}_edit_recipe_scaffold.json"
    _atomic_write_json(planning_path, planning)
    _atomic_write_json(edit_path, edit)
    pending.rename(target)
    return {
        "workflow": "review_reel_production",
        "state": "recipe_scaffold_ready",
        "content_id": str(package.metadata.get("content_id") or ""),
        "planning": str((target / planning_path.name).resolve()),
        "edit": str((target / edit_path.name).resolve()),
        "next_action": "complete_scaffold_content_then_generate_one_shot_tts",
    }


def fork_active_recipe_for_voice_reuse(
    *,
    output_root: str | Path,
    expected_content_id: str,
    planning_path: str | Path,
    edit_path: str | Path,
) -> dict[str, Any]:
    """Fork one active package recipe without changing its current audio pointers."""

    from video_engine_v2.recipe_revision import (
        RecipeRevisionViolation,
        fork_recipe_for_voice_reuse,
    )

    package = resolve_active_package(output_root)
    _assert_expected_content_id(package, expected_content_id)
    try:
        result = fork_recipe_for_voice_reuse(
            package.package_dir,
            planning_path=planning_path,
            edit_path=edit_path,
        )
    except RecipeRevisionViolation as error:
        raise IntakeViolation(str(error)) from error
    result.update(
        {
            "workflow": "review_reel_production",
            "content_id": str(package.metadata.get("content_id") or ""),
            "package": str(package.package_dir),
        }
    )
    return result


def check_active_voice_reuse(
    *,
    output_root: str | Path,
    expected_content_id: str,
    edit_path: str | Path,
) -> dict[str, Any]:
    """Read-only voice-reuse verdict for the active canonical package."""

    from video_engine_v2.recipe_revision import RecipeRevisionViolation, check_voice_reuse_candidate

    package = resolve_active_package(output_root)
    _assert_expected_content_id(package, expected_content_id)
    try:
        result = check_voice_reuse_candidate(package.package_dir, edit_path)
    except RecipeRevisionViolation as error:
        raise IntakeViolation(str(error)) from error
    result.update(
        {
            "workflow": "review_reel_production",
            "content_id": str(package.metadata.get("content_id") or ""),
            "package": str(package.package_dir),
        }
    )
    return result


def _file_evidence(path: Path, *, relative_to: Path) -> dict[str, Any]:
    return {
        "relative_path": path.resolve().relative_to(relative_to.resolve()).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _validated_photo_review_evidence_paths(
    *, package_dir: Path, records: list[dict[str, Any]]
) -> set[str]:
    """Verify every accepted revision still matches its hash-bound evidence."""

    used_paths: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise IntakeViolation("PHOTO_REVIEW_HISTORY_INVALID")
        for field in ("selection", "privacy_manifest"):
            evidence = record.get(field)
            if not isinstance(evidence, dict):
                raise IntakeViolation("PHOTO_REVIEW_HISTORY_EVIDENCE_CHANGED")
            relative_path = evidence.get("relative_path")
            byte_count = evidence.get("bytes")
            digest = evidence.get("sha256")
            if (
                not isinstance(relative_path, str)
                or not relative_path.strip()
                or not isinstance(byte_count, int)
                or byte_count < 0
                or not isinstance(digest, str)
                or not _SHA256.fullmatch(digest)
            ):
                raise IntakeViolation("PHOTO_REVIEW_HISTORY_EVIDENCE_CHANGED")
            evidence_path = _inside(
                package_dir,
                package_dir / relative_path,
                code="PHOTO_REVIEW_HISTORY_EVIDENCE_CHANGED",
            )
            if (
                not evidence_path.is_file()
                or evidence_path.stat().st_size != byte_count
                or hashlib.sha256(evidence_path.read_bytes()).hexdigest() != digest
            ):
                raise IntakeViolation("PHOTO_REVIEW_HISTORY_EVIDENCE_CHANGED")
            used_paths.add(evidence_path.relative_to(package_dir).as_posix())
    return used_paths


def _photo_media_paths(package: CanonicalPackage) -> list[Path]:
    return sorted(
        (
            path.resolve()
            for path in package.image_dir.rglob("*")
            if path.is_file() and path.suffix.casefold() in _PHOTO_MEDIA_EXTENSIONS
        ),
        key=lambda path: path.relative_to(package.package_dir).as_posix().casefold(),
    )


def _validate_photo_decision_v2(decision: dict[str, Any]) -> None:
    action = decision.get("decision")
    privacy_status = decision.get("privacy_status")
    categories = decision.get("privacy_risk_categories")
    editorial_category = decision.get("editorial_category")
    evidence_classes = decision.get("evidence_classes")
    remediation = decision.get("remediation")

    if not isinstance(categories, list) or any(not isinstance(value, str) for value in categories):
        raise IntakeViolation("PHOTO_PRIVACY_CATEGORY_INVALID")
    if len(categories) != len(set(categories)) or not set(categories).issubset(PRIVACY_BLOCKING_CATEGORIES):
        raise IntakeViolation("PHOTO_PRIVACY_CATEGORY_INVALID")
    if editorial_category not in EDITORIAL_CATEGORIES:
        raise IntakeViolation("PHOTO_EDITORIAL_CATEGORY_INVALID")
    if (
        not isinstance(evidence_classes, list)
        or not evidence_classes
        or any(not isinstance(value, str) for value in evidence_classes)
        or len(evidence_classes) != len(set(evidence_classes))
        or not set(evidence_classes).issubset(EVIDENCE_CLASSES)
    ):
        raise IntakeViolation("PHOTO_EVIDENCE_CLASS_INVALID")
    if not isinstance(remediation, dict):
        raise IntakeViolation("PHOTO_REMEDIATION_INVALID")
    remediation_action = remediation.get("action")

    if privacy_status == "clear":
        if categories or remediation_action != "none":
            raise IntakeViolation("PHOTO_PRIVACY_STATE_INVALID")
    elif privacy_status == "needs_sanitization":
        candidate_actions = remediation.get("candidate_actions")
        if (
            not categories
            or action != "hold"
            or remediation_action != "pending"
            or not isinstance(candidate_actions, list)
            or not candidate_actions
            or any(not isinstance(value, str) for value in candidate_actions)
            or not set(candidate_actions).issubset(SANITIZING_ACTIONS)
        ):
            raise IntakeViolation("PHOTO_PRIVACY_STATE_INVALID")
    elif privacy_status == "sanitized":
        if not categories or remediation_action not in SANITIZING_ACTIONS or action != "use":
            raise IntakeViolation("PHOTO_PRIVACY_STATE_INVALID")
    elif privacy_status == "blocked":
        if not categories or action != "exclude":
            raise IntakeViolation("PHOTO_PRIVACY_STATE_INVALID")
        attempted = remediation.get("attempted_actions")
        if (
            remediation_action != "infeasible"
            or editorial_category != "privacy_unrecoverable"
            or not isinstance(attempted, list)
            or not attempted
            or not set(attempted).issubset(SANITIZING_ACTIONS)
            or remediation.get("infeasible_category") not in MASKING_INFEASIBLE_CATEGORIES
            or not isinstance(remediation.get("masking_infeasible_reason"), str)
            or not remediation["masking_infeasible_reason"].strip()
            or not isinstance(remediation.get("manual_review_reference"), str)
            or not remediation["manual_review_reference"].strip()
        ):
            raise IntakeViolation("MASKING_FIRST_NOT_APPLIED")

    if action == "use" and editorial_category != "selected_story_evidence":
        raise IntakeViolation("PHOTO_EDITORIAL_CATEGORY_INVALID")
    if action == "hold" and editorial_category not in {"alternate_held", "not_required_by_narrative"}:
        raise IntakeViolation("PHOTO_EDITORIAL_CATEGORY_INVALID")
    if action == "exclude" and not categories and editorial_category not in {
        "duplicate",
        "unusable_quality",
        "unrelated_to_review",
    }:
        raise IntakeViolation("PHOTO_EDITORIAL_CATEGORY_INVALID")
    visual_quality = decision.get("visual_quality")
    if visual_quality is not None and (
        not isinstance(visual_quality, dict)
        or any(not isinstance(value, bool) for value in visual_quality.values())
    ):
        raise IntakeViolation("PHOTO_VISUAL_QUALITY_INVALID")


def _validate_review_capture_integrity(
    *,
    decision: dict[str, Any],
    source_file: Path,
    selected_file: Path,
) -> None:
    """Prove that a selected review screenshot keeps the user's composition.

    Review screenshots are evidence, not generic B-roll.  Sanitization may only
    alter small, declared identifier regions; cropping, resizing, reframing, or
    changing pixels elsewhere would remove review context and is rejected.
    """

    if "review_capture" not in decision.get("evidence_classes", ()):
        return

    integrity = decision.get("review_capture_integrity")
    if not isinstance(integrity, dict):
        raise IntakeViolation("REVIEW_CAPTURE_INTEGRITY_MISSING")
    if integrity.get("composition_preserved") is not True:
        raise IntakeViolation("REVIEW_CAPTURE_COMPOSITION_CHANGED")
    if integrity.get("pre_masked_identifiers_preserved") is not True:
        raise IntakeViolation("REVIEW_CAPTURE_PREMASKED_ID_TOUCHED")

    remediation_action = decision.get("remediation", {}).get("action")
    if remediation_action not in {"none", "mask", "blur"}:
        raise IntakeViolation("REVIEW_CAPTURE_CROP_FORBIDDEN")

    regions = integrity.get("localized_mask_regions")
    if not isinstance(regions, list):
        raise IntakeViolation("REVIEW_CAPTURE_MASK_REGION_INVALID")
    if remediation_action == "none" and regions:
        raise IntakeViolation("REVIEW_CAPTURE_MASK_REGION_INVALID")
    if remediation_action in {"mask", "blur"} and not regions:
        raise IntakeViolation("REVIEW_CAPTURE_MASK_REGION_INVALID")

    try:
        with Image.open(source_file) as source_image, Image.open(selected_file) as selected_image:
            source_format = source_image.format
            selected_format = selected_image.format
            source = source_image.convert("RGB")
            selected = selected_image.convert("RGB")
    except (OSError, UnidentifiedImageError):
        raise IntakeViolation("REVIEW_CAPTURE_IMAGE_INVALID") from None

    if source.size != selected.size:
        raise IntakeViolation("REVIEW_CAPTURE_COMPOSITION_CHANGED")
    width, height = source.size
    image_area = width * height
    if image_area <= 0:
        raise IntakeViolation("REVIEW_CAPTURE_IMAGE_INVALID")

    allowed_categories = set(decision.get("privacy_risk_categories", ()))
    mask_rectangles: list[tuple[int, int, int, int]] = []
    declared_area = 0
    for region in regions:
        if not isinstance(region, dict) or region.get("category") not in allowed_categories:
            raise IntakeViolation("REVIEW_CAPTURE_MASK_REGION_INVALID")
        values = [region.get(key) for key in ("x_px", "y_px", "width_px", "height_px")]
        if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
            raise IntakeViolation("REVIEW_CAPTURE_MASK_REGION_INVALID")
        x, y, region_width, region_height = values
        if (
            x < 0
            or y < 0
            or region_width <= 0
            or region_height <= 0
            or x + region_width > width
            or y + region_height > height
        ):
            raise IntakeViolation("REVIEW_CAPTURE_MASK_REGION_INVALID")
        declared_area += region_width * region_height
        mask_rectangles.append((x, y, x + region_width - 1, y + region_height - 1))
    if declared_area / image_area > REVIEW_CAPTURE_MAX_MASK_AREA_RATIO:
        raise IntakeViolation("REVIEW_CAPTURE_MASK_NOT_MINIMAL")

    difference = ImageChops.difference(source, selected)
    difference_draw = ImageDraw.Draw(difference)
    for rectangle in mask_rectangles:
        difference_draw.rectangle(rectangle, fill=(0, 0, 0))

    if source_format == "PNG" and selected_format == "PNG":
        changed_outside_mask = difference.getbbox() is not None
    else:
        # Lossy source formats can move a few edge pixels during re-encoding.
        # Only a tiny amount of high-amplitude drift is tolerated outside the
        # declared masks; geometric changes are already rejected above.
        changed_pixels = sum(1 for pixel in difference.getdata() if max(pixel) > 24)
        changed_outside_mask = changed_pixels > max(4, int(image_area * 0.0005))
    if changed_outside_mask:
        raise IntakeViolation("REVIEW_CAPTURE_COMPOSITION_CHANGED")


def _record_photo_review(
    *,
    output_root: str | Path,
    selection_path: str | Path,
    privacy_manifest_path: str | Path,
    now: datetime | None = None,
) -> CanonicalPackage:
    """Bind a complete photo decision record to the active canonical package.

    This is the only supported transition from photo_intake_pending to
    photo_reviewed. It creates no script, voice, HTML, or MP4.
    """

    root = Path(output_root).resolve()
    package = resolve_active_package(root)
    package_dir = package.package_dir.resolve()
    if package.metadata.get("lifecycle_state") not in {"photo_intake_pending", "photo_reviewed"}:
        raise IntakeViolation("PHOTO_REVIEW_STATE_INVALID")

    selection_file = _inside(
        package_dir,
        Path(selection_path).resolve(),
        code="PHOTO_SELECTION_OUTSIDE_PACKAGE",
    )
    privacy_file = _inside(
        package_dir,
        Path(privacy_manifest_path).resolve(),
        code="PRIVACY_MANIFEST_OUTSIDE_PACKAGE",
    )
    selection = _read_json(
        selection_file,
        missing="PHOTO_SELECTION_MISSING",
        invalid="PHOTO_SELECTION_INVALID",
    )
    privacy = _read_json(
        privacy_file,
        missing="PRIVACY_MANIFEST_MISSING",
        invalid="PRIVACY_MANIFEST_INVALID",
    )

    metadata = dict(package.metadata)
    previous_review = metadata.get("photo_review")
    history_value = metadata.get("photo_review_history")
    if history_value is not None and not isinstance(history_value, list):
        raise IntakeViolation("PHOTO_REVIEW_HISTORY_INVALID")
    history = list(history_value or [])
    if isinstance(previous_review, dict):
        selection_relative = selection_file.relative_to(package_dir).as_posix()
        privacy_relative = privacy_file.relative_to(package_dir).as_posix()
        prior_evidence_paths = _validated_photo_review_evidence_paths(
            package_dir=package_dir,
            records=[*history, previous_review],
        )
        if selection_relative in prior_evidence_paths or privacy_relative in prior_evidence_paths:
            raise IntakeViolation("PHOTO_REVIEW_REVISION_EVIDENCE_REUSED")

    if selection.get("schema_version") != PHOTO_SELECTION_SCHEMA_VERSION:
        raise IntakeViolation("PHOTO_SELECTION_SCHEMA_INVALID")
    if selection.get("content_id") != package.metadata.get("content_id"):
        raise IntakeViolation("PHOTO_SELECTION_IDENTITY_MISMATCH")
    if isinstance(previous_review, dict):
        previous_revision = previous_review.get("revision")
        if not isinstance(previous_revision, int) or previous_revision < 1:
            previous_revision = 1
        expected_revision = previous_revision + 1
        expected_supersedes_revision: int | None = previous_revision
    else:
        previous_revision = 0
        expected_revision = 1
        expected_supersedes_revision = None
    selection_revision = selection.get("revision")
    selection_supersedes = selection.get("supersedes_revision")
    revision_reason = selection.get("revision_reason")
    revision_changes = selection.get("revision_changes")
    if (
        not isinstance(selection_revision, int)
        or selection_revision < 1
        or not isinstance(revision_reason, str)
        or not revision_reason.strip()
        or not isinstance(revision_changes, list)
        or not revision_changes
        or any(not isinstance(change, str) or not change.strip() for change in revision_changes)
    ):
        raise IntakeViolation("PHOTO_SELECTION_REVISION_CONTEXT_INVALID")
    if (
        selection_revision != expected_revision
        or selection_supersedes != expected_supersedes_revision
    ):
        raise IntakeViolation("PHOTO_SELECTION_REVISION_CONTEXT_MISMATCH")
    if selection.get("unresolved_items") != []:
        raise IntakeViolation("PHOTO_SELECTION_UNRESOLVED")
    decisions = selection.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise IntakeViolation("PHOTO_SELECTION_DECISIONS_MISSING")

    expected_media = {
        path.relative_to(package_dir).as_posix(): path for path in _photo_media_paths(package)
    }
    if not expected_media:
        raise IntakeViolation("PHOTO_MEDIA_MISSING")
    decision_paths: set[str] = set()
    selected_paths: set[str] = set()
    for decision in decisions:
        if not isinstance(decision, dict):
            raise IntakeViolation("PHOTO_SELECTION_DECISION_INVALID")
        relative_path = decision.get("relative_path")
        action = decision.get("decision")
        reason = decision.get("reason")
        privacy_status = decision.get("privacy_status")
        if (
            not isinstance(relative_path, str)
            or relative_path not in expected_media
            or relative_path in decision_paths
            or action not in {"use", "hold", "exclude"}
            or not isinstance(reason, str)
            or not reason.strip()
            or privacy_status not in {"clear", "needs_sanitization", "sanitized", "blocked"}
        ):
            raise IntakeViolation("PHOTO_SELECTION_DECISION_INVALID")
        _validate_photo_decision_v2(decision)
        decision_paths.add(relative_path)
        if action == "use":
            if privacy_status == "blocked":
                raise IntakeViolation("PHOTO_SELECTION_DECISION_INVALID")
            selected_relative = decision.get("selected_relative_path", relative_path)
            if (
                not isinstance(selected_relative, str)
                or not selected_relative.strip()
                or Path(selected_relative).is_absolute()
            ):
                raise IntakeViolation("PHOTO_SELECTION_DECISION_INVALID")
            selected_file = _inside(
                package_dir,
                package_dir / selected_relative,
                code="PHOTO_SELECTION_SELECTED_ASSET_OUTSIDE_PACKAGE",
            )
            if not selected_file.is_file():
                raise IntakeViolation("PHOTO_SELECTION_SELECTED_ASSET_MISSING")
            _validate_review_capture_integrity(
                decision=decision,
                source_file=expected_media[relative_path],
                selected_file=selected_file,
            )
            selected_paths.add(selected_file.relative_to(package_dir).as_posix())
    if decision_paths != set(expected_media):
        raise IntakeViolation("PHOTO_SELECTION_INCOMPLETE")
    if not selected_paths:
        raise IntakeViolation("PHOTO_SELECTION_HAS_NO_USED_ASSETS")

    if (
        not isinstance(privacy.get("schema_version"), str)
        or not privacy["schema_version"].strip()
        or privacy.get("checked") is not True
        or not isinstance(privacy.get("checked_at"), str)
        or not privacy["checked_at"].strip()
        or privacy.get("unresolved_risks") != []
    ):
        raise IntakeViolation("PRIVACY_MANIFEST_INVALID")
    manifest_assets = privacy.get("selected_assets")
    if not isinstance(manifest_assets, list) or not manifest_assets:
        raise IntakeViolation("PRIVACY_MANIFEST_INVALID")
    manifest_paths: set[str] = set()
    manifest_evidence: dict[str, tuple[int, str]] = {}
    for evidence in manifest_assets:
        if not isinstance(evidence, dict):
            raise IntakeViolation("PRIVACY_MANIFEST_INVALID")
        relative_path = evidence.get("relative_path")
        if (
            not isinstance(relative_path, str)
            or not relative_path.strip()
            or Path(relative_path).is_absolute()
            or relative_path in manifest_paths
        ):
            raise IntakeViolation("PRIVACY_MANIFEST_INVALID")
        asset = _inside(
            package_dir,
            package_dir / relative_path,
            code="PRIVACY_ASSET_OUTSIDE_PACKAGE",
        )
        if not asset.is_file():
            raise IntakeViolation("PRIVACY_ASSET_MISSING")
        actual = _file_evidence(asset, relative_to=package_dir)
        if (
            evidence.get("bytes") != actual["bytes"]
            or evidence.get("sha256") != actual["sha256"]
        ):
            raise IntakeViolation("PRIVACY_ASSET_HASH_MISMATCH")
        manifest_paths.add(actual["relative_path"])
        manifest_evidence[actual["relative_path"]] = (actual["bytes"], actual["sha256"])
    if manifest_paths != selected_paths:
        raise IntakeViolation("PHOTO_SELECTION_PRIVACY_ASSET_MISMATCH")
    report_value = privacy.get("sanitization_report")
    if (
        not isinstance(report_value, str)
        or not report_value.strip()
        or Path(report_value).is_absolute()
    ):
        raise IntakeViolation("PRIVACY_REPORT_INVALID")
    report_file = _inside(
        package_dir,
        package_dir / report_value,
        code="PRIVACY_REPORT_OUTSIDE_PACKAGE",
    )
    report = _read_json(
        report_file,
        missing="PRIVACY_REPORT_MISSING",
        invalid="PRIVACY_REPORT_INVALID",
    )
    checked_assets = report.get("checked_assets")
    categories = report.get("inspection_categories")
    if (
        report.get("checked") is not True
        or not isinstance(report.get("checked_at"), str)
        or not report["checked_at"].strip()
        or report.get("unresolved_risks") != []
        or not isinstance(categories, list)
        or not {"face", "vehicle_plate", "address", "family_photo"}.issubset(set(categories))
        or not isinstance(checked_assets, list)
    ):
        raise IntakeViolation("PRIVACY_REPORT_INVALID")
    report_evidence: dict[str, tuple[int, str]] = {}
    for evidence in checked_assets:
        if not isinstance(evidence, dict):
            raise IntakeViolation("PRIVACY_REPORT_INVALID")
        relative_path = evidence.get("relative_path")
        byte_count = evidence.get("bytes")
        digest = evidence.get("sha256")
        if (
            not isinstance(relative_path, str)
            or not isinstance(byte_count, int)
            or not isinstance(digest, str)
            or not _SHA256.fullmatch(digest)
            or relative_path in report_evidence
        ):
            raise IntakeViolation("PRIVACY_REPORT_INVALID")
        report_evidence[relative_path] = (byte_count, digest)
    if report_evidence != manifest_evidence:
        raise IntakeViolation("PRIVACY_REPORT_ASSET_MISMATCH")

    # Fail at photo-review, not later at HTML preflight, when a sanitized
    # output is undeclared or its pixels do not match the declared mask.
    from video_engine_v2.production_gate import GateViolation, _validate_sanitized_asset_pixels

    try:
        _validate_sanitized_asset_pixels(package_dir, privacy)
    except GateViolation as error:
        raise IntakeViolation(str(error)) from error

    clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if isinstance(previous_review, dict):
        previous_record = dict(previous_review)
        previous_record["revision"] = previous_revision
        history.append(previous_record)
    revision = expected_revision
    approvals = dict(metadata.get("approvals") or {})
    approvals.update(
        {
            "photo_checked": True,
            "pd_plan_approved": False,
            "html_scope_authorized": False,
            "mp4_scope_authorized": False,
        }
    )
    metadata["approvals"] = approvals
    metadata["lifecycle_state"] = "photo_reviewed"
    photo_review = {
        "revision": revision,
        "revision_reason": revision_reason.strip(),
        "revision_changes": [change.strip() for change in revision_changes],
        "checked_at": clock.isoformat(),
        "selection": _file_evidence(selection_file, relative_to=package_dir),
        "privacy_manifest": _file_evidence(privacy_file, relative_to=package_dir),
        "source_media_count": len(expected_media),
        "selected_asset_count": len(selected_paths),
    }
    if isinstance(previous_review, dict):
        photo_review["supersedes_revision"] = revision - 1
        metadata["photo_review_history"] = history
    metadata["photo_review"] = photo_review
    from video_engine_v2.current_artifacts import CurrentArtifactsViolation, record_current_artifacts

    try:
        record_current_artifacts(
            package_dir,
            producer="review_reel_intake.record_photo_review",
            artifacts={"privacy_manifest": privacy_file},
            revision_id=str(revision),
            now=clock,
        )
    except CurrentArtifactsViolation as error:
        raise IntakeViolation(str(error)) from error
    _atomic_write_json(package_dir / METADATA_FILENAME, metadata)
    _atomic_write_text(
        package_dir / "STATUS.md",
        "- photo_checked: true\n"
        "- pd_plan_approved: false\n"
        "- html_approved_by_user: false\n"
        "- mp4_allowed: false\n",
    )
    _atomic_write_text(
        package_dir / "APPROVAL_LOG.md",
        "- approved: photo review recorded by official intake gate\n"
        "- not_approved: PD planning pending\n"
        "- not_approved: HTML user review pending\n"
        "- not_approved: MP4 render pending\n",
    )
    reviewed = CanonicalPackage(package_dir, package.image_dir, metadata, reused_existing=True)
    _set_active_package(root, reviewed, updated_at=clock.isoformat())
    return reviewed


def _write_photo_review_rejection_receipt(
    *,
    output_root: Path,
    selection_path: str | Path,
    privacy_manifest_path: str | Path,
    violation: IntakeViolation,
    now: datetime | None,
) -> None:
    """Record a hash-only rejected attempt without mutating canonical state."""

    try:
        package = resolve_active_package(output_root)
        package_dir = package.package_dir.resolve()
        clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

        def evidence_if_safe(value: str | Path) -> dict[str, Any] | None:
            candidate = Path(value).resolve()
            try:
                candidate.relative_to(package_dir)
            except ValueError:
                return None
            if not candidate.is_file():
                return None
            return _file_evidence(candidate, relative_to=package_dir)

        receipt = {
            "schema_version": "review-reel-photo-review-rejection-v1",
            "attempted_at": clock.isoformat(),
            "content_id": package.metadata.get("content_id"),
            "package_name": package.package_dir.name,
            "active_lifecycle_state": package.metadata.get("lifecycle_state"),
            "active_metadata_sha256": hashlib.sha256(
                (package_dir / METADATA_FILENAME).read_bytes()
            ).hexdigest(),
            "error_code": violation.codes[0] if violation.codes else str(violation),
            "error_codes": list(violation.codes),
            "selection": evidence_if_safe(selection_path),
            "privacy_manifest": evidence_if_safe(privacy_manifest_path),
        }
        receipt_dir = package_dir / "_work" / "photo_review_rejections"
        receipt_name = (
            f"rejected_{clock.strftime('%Y%m%dT%H%M%S_%fZ')}_{uuid4().hex[:8]}.json"
        )
        _atomic_write_json(receipt_dir / receipt_name, receipt)
    except (IntakeViolation, OSError, ValueError):
        # Auditing must never replace the original gate error.
        return


def record_photo_review(
    *,
    output_root: str | Path,
    expected_content_id: str | None = None,
    selection_path: str | Path,
    privacy_manifest_path: str | Path,
    now: datetime | None = None,
) -> CanonicalPackage:
    """Record an accepted photo review or a hash-only rejected attempt receipt."""

    root = Path(output_root).resolve()
    try:
        if expected_content_id is not None:
            _assert_expected_content_id(resolve_active_package(root), expected_content_id)
        return _record_photo_review(
            output_root=root,
            selection_path=selection_path,
            privacy_manifest_path=privacy_manifest_path,
            now=now,
        )
    except IntakeViolation as violation:
        _write_photo_review_rejection_receipt(
            output_root=root,
            selection_path=selection_path,
            privacy_manifest_path=privacy_manifest_path,
            violation=violation,
            now=now,
        )
        raise


def _assert_one_shot_contract(planning_path: Path) -> None:
    planning = _read_json(planning_path, missing="PLANNING_RECIPE_MISSING", invalid="PLANNING_RECIPE_INVALID")
    contract = planning.get("workflow_contract")
    if not isinstance(contract, dict) or contract.get("name") != "review-reels-one-shot-v2":
        raise IntakeViolation("ONE_SHOT_CONTRACT_MISSING")
    if contract.get("html_scope_authorized") is not True:
        raise IntakeViolation("HTML_SCOPE_NOT_AUTHORIZED")
    if contract.get("mp4_scope_authorized") is not False:
        raise IntakeViolation("MP4_SCOPE_MUST_REMAIN_UNAUTHORIZED")


def build_one_shot_html_commands(
    *,
    output_root: str | Path,
    expected_content_id: str | None = None,
    planning_path: str | Path,
    edit_path: str | Path,
    privacy_manifest_path: str | Path,
) -> list[list[str]]:
    """Return the disposable layout check and two official MP4-free HTML commands."""

    package = resolve_active_package(output_root)
    if expected_content_id is not None:
        _assert_expected_content_id(package, expected_content_id)
    planning = Path(planning_path).resolve()
    _assert_one_shot_contract(planning)
    edit = Path(edit_path).resolve()
    privacy = Path(privacy_manifest_path).resolve()
    sync_manifest = package.package_dir / "sync_manifest.json"
    if sync_manifest.exists():
        revision_match = re.search(r"_v(?P<revision>\d+)_edit_recipe\.json$", edit.name)
        if revision_match is None:
            raise IntakeViolation("SYNC_MANIFEST_REVISION_REQUIRED")
        sync_manifest = package.package_dir / f"sync_manifest_v{revision_match.group('revision')}.json"
    shared = [
        "--package",
        str(package.package_dir),
        "--planning",
        str(planning),
        "--edit",
        str(edit),
        "--privacy-manifest",
        str(privacy),
        "--sync-manifest",
        str(sync_manifest),
        "--one-shot-html",
    ]
    official = str(REPOSITORY_ROOT / "scripts" / "produce_review_v2.py")
    return [
        [
            sys.executable,
            official,
            "layout-check",
            "--package",
            str(package.package_dir),
            "--edit",
            str(edit),
        ],
        [sys.executable, official, "preflight", *shared],
        [sys.executable, official, "html", *shared],
    ]


def run_one_shot_html(
    *,
    output_root: str | Path,
    expected_content_id: str | None = None,
    planning_path: str | Path,
    edit_path: str | Path,
    privacy_manifest_path: str | Path,
) -> int:
    """Run layout check, preflight, then HTML; never render an MP4."""

    for command in build_one_shot_html_commands(
        output_root=output_root,
        expected_content_id=expected_content_id,
        planning_path=planning_path,
        edit_path=edit_path,
        privacy_manifest_path=privacy_manifest_path,
    ):
        result = subprocess.run(command, cwd=REPOSITORY_ROOT, check=False)
        if result.returncode != 0:
            return result.returncode
    return 0
