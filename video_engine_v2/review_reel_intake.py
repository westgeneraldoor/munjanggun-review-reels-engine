"""Canonical, local-only intake for the review-reel production workflow.

This module deliberately creates only the pre-photo package boundary.  It does
not create a script, voice, HTML, or MP4.  HTML may be requested later through
the existing production orchestrator after its independent gates pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import uuid4


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
METADATA_FILENAME = "CANONICAL_PACKAGE_METADATA.json"
POINTER_DIRECTORY = ".review_reel_production"
ACTIVE_POINTER_FILENAME = "active_package.json"
REGISTRY_FILENAME = "registry.json"
INVENTORY_SCHEMA_VERSION = "review-reel-inventory-v1"
PACKAGE_SCHEMA_VERSION = "review-reel-canonical-package-v1"
_CONTENT_ID = re.compile(r"^\d{3}$")
_WINDOWS_UNSAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_CANDIDATE_PREFIX = "CAND-"


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


def route_user_command(command: str) -> dict[str, str]:
    """Map a short Korean request to exactly one workflow state transition.

    Reel-specific phrases are checked before generic review-content phrases so a
    mixed message can never fall back to a material-bank flow.
    """

    normalised = _normalise_command(command)
    if "사진 다 넣었어" in normalised and "html까지 가자" in normalised:
        return {
            "workflow": "review_reel_production",
            "state": "one_shot_html_requested",
            "next_action": "resolve_active_canonical_package",
        }
    if "리뷰 하나 골라 폴더 만들어줘" in normalised:
        return {
            "workflow": "review_reel_production",
            "state": "canonical_package_create_requested",
            "next_action": "select_inventory_record",
        }
    if "리뷰 릴스 만들자" in normalised:
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
        if not isinstance(candidate_reference, str) or not candidate_reference.startswith(_CANDIDATE_PREFIX):
            raise IntakeViolation("CANDIDATE_REFERENCE_INVALID")
        record["candidate_reference"] = candidate_reference

    source_value = _required_text(record, "review_source_path", "REVIEW_SOURCE_PATH_MISSING")
    source_path = Path(source_value)
    if not source_path.is_absolute():
        source_path = inventory_path.parent / source_path
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


def _find_existing(output_root: Path, identity: dict[str, str]) -> CanonicalPackage | None:
    if not output_root.is_dir():
        return None
    for metadata_path in output_root.glob(f"inbox_*/*/{METADATA_FILENAME}"):
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


def _set_active_package(output_root: Path, package: CanonicalPackage, *, updated_at: str) -> None:
    state_dir = output_root / POINTER_DIRECTORY
    pointer = _pointer_payload(output_root, package, updated_at=updated_at)
    _atomic_write_json(state_dir / ACTIVE_POINTER_FILENAME, pointer)
    registry_path = state_dir / REGISTRY_FILENAME
    try:
        registry = _read_json(registry_path, missing="REGISTRY_MISSING", invalid="REGISTRY_INVALID")
    except IntakeViolation:
        registry = {"schema_version": "review-reel-production-registry-v1", "packages": []}
    records = registry.get("packages")
    if not isinstance(records, list):
        records = []
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

    collection = root / f"inbox_{clock.strftime('%Y%m%d')}"
    package_dir = collection / package_name
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
    }

    collection.mkdir(parents=True, exist_ok=True)
    pending_dir = collection / f".{package_name}.pending-{uuid4().hex}"
    pending_dir.mkdir()
    image_dir = pending_dir / image_name
    image_dir.mkdir()
    _atomic_write_json(pending_dir / METADATA_FILENAME, metadata)
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
    planning_path: str | Path,
    edit_path: str | Path,
    privacy_manifest_path: str | Path,
) -> list[list[str]]:
    """Return only the two official, MP4-free one-shot production commands."""

    planning = Path(planning_path).resolve()
    _assert_one_shot_contract(planning)
    package = resolve_active_package(output_root)
    edit = Path(edit_path).resolve()
    privacy = Path(privacy_manifest_path).resolve()
    sync_manifest = package.package_dir / "sync_manifest.json"
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
        [sys.executable, official, "preflight", *shared],
        [sys.executable, official, "html", *shared],
    ]


def run_one_shot_html(
    *,
    output_root: str | Path,
    planning_path: str | Path,
    edit_path: str | Path,
    privacy_manifest_path: str | Path,
) -> int:
    """Run the preflight then HTML official entry points; never render an MP4."""

    for command in build_one_shot_html_commands(
        output_root=output_root,
        planning_path=planning_path,
        edit_path=edit_path,
        privacy_manifest_path=privacy_manifest_path,
    ):
        result = subprocess.run(command, cwd=REPOSITORY_ROOT, check=False)
        if result.returncode != 0:
            return result.returncode
    return 0
