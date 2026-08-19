import json
import hashlib
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from video_engine_v2.reels_qa import validate_review_reels_one_shot_contract
from video_engine_v2.review_reel_intake import (
    IntakeViolation,
    active_package_status,
    build_one_shot_html_commands,
    create_canonical_package,
    create_canonical_package_from_material_bank,
    record_photo_review,
    resolve_active_package,
    route_user_command,
    run_one_shot_html,
    workflow_next,
    write_recipe_scaffold,
)


class ReviewReelIntakeTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.output_root = self.root / "output"
        self.review_path = self.root / "reviews" / "004_fixture.txt"
        self.review_path.parent.mkdir(parents=True)
        self.review_text = "Fixture review: the entrance was difficult before installation."
        self.review_path.write_text(self.review_text, encoding="utf-8")
        self.inventory_path = self.root / "private_review_reel_inventory.json"
        self._write_inventory()
        self.now = datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    def _write_inventory(self, *, content_id="004", candidate_reference="CAND-20300102-0004"):
        self.inventory_path.write_text(
            json.dumps(
                {
                    "schema_version": "review-reel-inventory-v1",
                    "records": [
                        {
                            "record_key": "fixture-review-004",
                            "content_id": content_id,
                            "content_slug": "어려운시공",
                            "review_source_path": str(self.review_path),
                            "review_text": self.review_text,
                            "product_order_number": "ORDER-004-FIXTURE",
                            "review_article_id": "REVIEW-004-FIXTURE",
                            "source_reference": "fixture:review-inventory/004",
                            "candidate_reference": candidate_reference,
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def create(self):
        return create_canonical_package(
            output_root=self.output_root,
            inventory_path=self.inventory_path,
            record_key="fixture-review-004",
            now=self.now,
        )

    def test_reel_phrases_route_to_review_reel_production_before_generic_review_content(self):
        cases = {
            "리뷰 릴스 만들자 리뷰 콘텐츠 신규 만들어줘": "selection_required",
            "리뷰릴스 만들자": "selection_required",
            "리뷰 릴스 제작하자": "selection_required",
            "017번 리뷰 릴스 만들자": "selection_required",
            "리뷰 하나 골라 폴더 만들어줘": "canonical_package_create_requested",
            "리뷰 하나 골라서 폴더 만들어줘": "canonical_package_create_requested",
            "리뷰 골라주고 폴더 만들어줘": "canonical_package_create_requested",
            "사진 다 넣었어. HTML까지 가자": "one_shot_html_requested",
            "사진 다 넣었어요 HTML까지 가자": "one_shot_html_requested",
            # `리뷰`가 `릴스`에 붙어 있지 않거나 아예 없는 자연스러운 어미도 같은 명령이다.
            "이 리뷰로 릴스 만들어보자": "selection_required",
            "이걸로 릴스 해보자": "selection_required",
            "릴스 하나 시작하자": "selection_required",
            "이번 건 릴스로 가자": "selection_required",
        }
        for command, expected_state in cases.items():
            with self.subTest(command=command):
                routed = route_user_command(command)
                self.assertEqual(routed["workflow"], "review_reel_production")
                self.assertEqual(routed["state"], expected_state)

    def test_exact_fresh_session_phrases_route_to_review_reel_production(self):
        cases = {
            "이 리뷰와 사진들로 신규 리뷰 숏폼 만들자. 사진 검수부터 HTML까지 진행해.": "selection_required",
            "이 리뷰로 쇼츠 만들자": "selection_required",
            "리뷰 영상 만들자": "selection_required",
            "HTML 승인. MP4 렌더도 진행해.": "html_approval_and_mp4_render_intent_requested",
        }

        for command, expected_state in cases.items():
            with self.subTest(command=command):
                routed = route_user_command(command)
                self.assertEqual(routed["workflow"], "review_reel_production")
                self.assertEqual(routed["state"], expected_state)

        approval_intent = route_user_command("HTML 승인. MP4 렌더도 진행해.")
        self.assertEqual(
            approval_intent["next_action"],
            "resolve_active_package_then_record_hash_bound_approvals",
        )
        self.assertNotIn("approved", approval_intent)

    def test_generic_review_content_phrases_without_reel_intent_stay_generic(self):
        for command in ("리뷰 컨텐츠 만들어줘", "리뷰 콘텐츠 신규 발행하자", "리뷰 원문 정리해줘"):
            with self.subTest(command=command):
                routed = route_user_command(command)
                self.assertEqual(routed["workflow"], "generic_review_content")

    def test_create_uses_inventory_content_id_and_never_exposes_candidate_in_user_facing_names(self):
        result = self.create()

        self.assertEqual(result.package_dir.name, "004_어려운시공_20300102_030405")
        self.assertEqual(result.image_dir.name, "004_어려운시공_이미지")
        self.assertNotIn("CAND-", result.package_dir.name)
        self.assertNotIn("CAND-", result.image_dir.name)
        self.assertTrue(result.package_dir.is_dir())
        self.assertEqual(result.package_dir.parent, self.output_root.resolve())
        self.assertEqual(result.metadata["package_relative_path"], result.package_dir.name)
        self.assertTrue(result.image_dir.is_dir())
        self.assertFalse(any(result.package_dir.glob("*_script.md")))
        self.assertFalse(any(result.package_dir.glob("*_voice.mp3")))
        self.assertFalse(any(result.package_dir.glob("*_html_preview_v2")))

    def test_canonical_metadata_binds_review_text_order_article_and_candidate_source_references(self):
        result = self.create()
        metadata = json.loads((result.package_dir / "CANONICAL_PACKAGE_METADATA.json").read_text(encoding="utf-8"))

        self.assertEqual(metadata["content_id"], "004")
        self.assertEqual(metadata["review_source"]["text"], self.review_text)
        self.assertEqual(metadata["review_source"]["product_order_number"], "ORDER-004-FIXTURE")
        self.assertEqual(metadata["review_source"]["review_article_id"], "REVIEW-004-FIXTURE")
        self.assertEqual(metadata["review_source"]["candidate_reference"], "CAND-20300102-0004")
        self.assertEqual(metadata["review_source"]["source_reference"], "fixture:review-inventory/004")
        self.assertEqual((result.package_dir / ".source").read_text(encoding="utf-8"), str(self.review_path.resolve()))

    def test_source_marker_uses_the_generation_gate_relative_key_when_source_is_in_the_repository(self):
        with patch("video_engine_v2.review_reel_intake.REPOSITORY_ROOT", self.root):
            result = self.create()

        self.assertEqual((result.package_dir / ".source").read_text(encoding="utf-8"), str(Path("reviews") / "004_fixture.txt"))

    def test_repository_relative_review_source_path_resolves_from_repository_root(self):
        inventory = json.loads(self.inventory_path.read_text(encoding="utf-8"))
        inventory["records"][0]["review_source_path"] = "reviews/004_fixture.txt"
        self.inventory_path.write_text(json.dumps(inventory, ensure_ascii=False), encoding="utf-8")

        with patch("video_engine_v2.review_reel_intake.REPOSITORY_ROOT", self.root):
            result = self.create()

        self.assertEqual(result.metadata["review_source"]["path"], str(self.review_path.resolve()))

    def test_material_bank_adapter_assigns_stable_internal_ids_and_creates_canonical_packages(self):
        material_bank = self.root / "candidate_top60_private.jsonl"
        records = [
            {
                "inventory_id": "INV-FIXTURE-1",
                "review_id": "REVIEW-FIXTURE-1",
                "order_id": "ORDER-FIXTURE-1",
                "product_name": "Fixture product",
                "review_text": "First material-bank fixture review.",
                "candidate_id": "CAND-20300102-0001",
            },
            {
                "inventory_id": "INV-FIXTURE-2",
                "review_id": "REVIEW-FIXTURE-2",
                "order_id": "ORDER-FIXTURE-2",
                "product_name": "Fixture product",
                "review_text": "Second material-bank fixture review.",
                "candidate_id": "CAND-20300102-0002",
            },
        ]
        material_bank.write_text(
            "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
            encoding="utf-8",
        )
        reviews_root = self.root / "reviews"
        (reviews_root / "005_existing.txt").write_text("existing", encoding="utf-8")
        existing_package = self.output_root / "inbox_20291231" / "004_existing_20291231_235959"
        existing_package.mkdir(parents=True)
        (existing_package / "999_customer_photo.jpg").write_bytes(b"fixture")

        with patch("video_engine_v2.review_reel_intake.REPOSITORY_ROOT", self.root):
            first = create_canonical_package_from_material_bank(
                output_root=self.output_root,
                reviews_root=reviews_root,
                material_bank_path=material_bank,
                candidate_id="CAND-20300102-0001",
                content_slug="첫번째후기",
                now=self.now,
            )
            repeated = create_canonical_package_from_material_bank(
                output_root=self.output_root,
                reviews_root=reviews_root,
                material_bank_path=material_bank,
                candidate_id="CAND-20300102-0001",
                content_slug="바뀌어도기존슬러그유지",
                now=self.now,
            )
            second = create_canonical_package_from_material_bank(
                output_root=self.output_root,
                reviews_root=reviews_root,
                material_bank_path=material_bank,
                candidate_id="CAND-20300102-0002",
                content_slug="두번째후기",
                now=self.now,
            )

        self.assertEqual(first.metadata["content_id"], "006")
        self.assertEqual(repeated.package_dir, first.package_dir)
        self.assertTrue(repeated.reused_existing)
        self.assertEqual(second.metadata["content_id"], "007")
        self.assertNotIn("CAND-", first.package_dir.name)
        self.assertEqual(
            Path(first.metadata["review_source"]["path"]).read_text(encoding="utf-8"),
            records[0]["review_text"],
        )
        registry = json.loads(
            (self.output_root / ".review_reel_production" / "source_registry_private.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual([record["content_id"] for record in registry["records"]], ["006", "007"])

    def test_invalid_material_bank_registry_is_not_silently_replaced(self):
        material_bank = self.root / "candidate_top60_private.jsonl"
        material_bank.write_text(
            json.dumps(
                {
                    "inventory_id": "INV-FIXTURE-1",
                    "review_id": "REVIEW-FIXTURE-1",
                    "order_id": "ORDER-FIXTURE-1",
                    "review_text": "Fixture review.",
                    "candidate_id": "CAND-20300102-0001",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        registry = self.output_root / ".review_reel_production" / "source_registry_private.json"
        registry.parent.mkdir(parents=True)
        registry.write_text("{broken", encoding="utf-8")

        with self.assertRaisesRegex(IntakeViolation, "SOURCE_REGISTRY_INVALID"):
            create_canonical_package_from_material_bank(
                output_root=self.output_root,
                reviews_root=self.root / "reviews",
                material_bank_path=material_bank,
                candidate_id="CAND-20300102-0001",
                content_slug="후기",
                now=self.now,
            )

        self.assertEqual(registry.read_text(encoding="utf-8"), "{broken")

    def test_duplicate_source_registry_ids_are_rejected_without_reallocation(self):
        material_bank = self.root / "candidate_top60_private.jsonl"
        material_bank.write_text(
            json.dumps(
                {
                    "inventory_id": "INV-FIXTURE-3",
                    "review_id": "REVIEW-FIXTURE-3",
                    "order_id": "ORDER-FIXTURE-3",
                    "review_text": "Third fixture review.",
                    "candidate_id": "CAND-20300102-0003",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        registry = self.output_root / ".review_reel_production" / "source_registry_private.json"
        registry.parent.mkdir(parents=True)
        payload = {
            "schema_version": "review-reel-source-registry-v1",
            "records": [
                {
                    "record_key": "material-bank::CAND-20300102-0001",
                    "content_id": "006",
                    "content_slug": "첫번째",
                    "candidate_reference": "CAND-20300102-0001",
                    "identity": {
                        "candidate_reference": "CAND-20300102-0001",
                        "inventory_id": "INV-FIXTURE-1",
                        "review_article_id": "REVIEW-FIXTURE-1",
                        "product_order_number": "ORDER-FIXTURE-1",
                        "review_text_sha256": "a" * 64,
                    },
                },
                {
                    "record_key": "material-bank::CAND-20300102-0002",
                    "content_id": "006",
                    "content_slug": "두번째",
                    "candidate_reference": "CAND-20300102-0002",
                    "identity": {
                        "candidate_reference": "CAND-20300102-0002",
                        "inventory_id": "INV-FIXTURE-2",
                        "review_article_id": "REVIEW-FIXTURE-2",
                        "product_order_number": "ORDER-FIXTURE-2",
                        "review_text_sha256": "b" * 64,
                    },
                },
            ],
        }
        registry.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        before = registry.read_bytes()

        with self.assertRaisesRegex(IntakeViolation, "SOURCE_REGISTRY_CONTENT_ID_DUPLICATE"):
            create_canonical_package_from_material_bank(
                output_root=self.output_root,
                reviews_root=self.root / "reviews",
                material_bank_path=material_bank,
                candidate_id="CAND-20300102-0003",
                content_slug="세번째",
                now=self.now,
            )

        self.assertEqual(registry.read_bytes(), before)

    def test_invalid_package_registry_is_not_silently_replaced(self):
        registry = self.output_root / ".review_reel_production" / "registry.json"
        registry.parent.mkdir(parents=True)
        registry.write_text("{broken", encoding="utf-8")

        with self.assertRaisesRegex(IntakeViolation, "REGISTRY_INVALID"):
            self.create()

        self.assertEqual(registry.read_text(encoding="utf-8"), "{broken")
        self.assertFalse(any(self.output_root.glob("inbox_*")))

    def test_create_is_idempotent_for_the_same_inventory_record(self):
        first = self.create()
        second = self.create()

        self.assertFalse(first.reused_existing)
        self.assertTrue(second.reused_existing)
        self.assertEqual(first.package_dir, second.package_dir)
        packages = [
            path
            for path in self.output_root.iterdir()
            if path.is_dir() and path.name[:3].isdigit()
        ]
        self.assertEqual([path.name for path in packages if path.is_dir()], [first.package_dir.name])

    def test_create_remains_read_compatible_with_a_legacy_inbox_package(self):
        first = self.create()
        legacy_parent = self.output_root / "inbox_20300102"
        legacy_parent.mkdir()
        legacy_package = legacy_parent / first.package_dir.name
        first.package_dir.rename(legacy_package)
        metadata_path = legacy_package / "CANONICAL_PACKAGE_METADATA.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["package_relative_path"] = f"inbox_20300102/{legacy_package.name}"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        registry_path = self.output_root / ".review_reel_production" / "registry.json"
        registry_path.write_text(
            json.dumps(
                {
                    "schema_version": "review-reel-production-registry-v1",
                    "packages": [],
                }
            ),
            encoding="utf-8",
        )

        reused = self.create()

        self.assertTrue(reused.reused_existing)
        self.assertEqual(reused.package_dir, legacy_package.resolve())
        self.assertEqual(resolve_active_package(self.output_root).package_dir, legacy_package.resolve())

    def test_create_rejects_rebinding_an_existing_content_id_to_a_different_review(self):
        self.create()
        second_source = self.root / "reviews" / "004_other_fixture.txt"
        second_source.write_text("A different fixture review.", encoding="utf-8")
        inventory = json.loads(self.inventory_path.read_text(encoding="utf-8"))
        record = inventory["records"][0]
        record["review_source_path"] = str(second_source)
        record["review_text"] = "A different fixture review."
        record["product_order_number"] = "ORDER-004-OTHER"
        record["review_article_id"] = "REVIEW-004-OTHER"
        self.inventory_path.write_text(json.dumps(inventory), encoding="utf-8")

        with self.assertRaisesRegex(IntakeViolation, "CONTENT_ID_ALREADY_BOUND"):
            self.create()

        packages = [
            path
            for path in self.output_root.iterdir()
            if path.is_dir() and path.name[:3].isdigit()
        ]
        self.assertEqual(len([path for path in packages if path.is_dir()]), 1)

    def test_create_rejects_candidate_identifier_as_content_id_instead_of_inventing_a_number(self):
        self._write_inventory(content_id="CAND-20300102-0004")

        with self.assertRaisesRegex(IntakeViolation, "CONTENT_ID_INVALID"):
            self.create()

        self.assertFalse(self.output_root.exists())

    def test_create_rejects_a_review_source_that_does_not_match_the_inventory_text(self):
        self.review_path.write_text("different source", encoding="utf-8")

        with self.assertRaisesRegex(IntakeViolation, "REVIEW_SOURCE_TEXT_MISMATCH"):
            self.create()

        self.assertFalse(self.output_root.exists())

    def test_active_pointer_resolves_only_the_canonical_package_created_by_the_intake(self):
        result = self.create()

        resolved = resolve_active_package(self.output_root)

        self.assertEqual(resolved.package_dir, result.package_dir)
        self.assertEqual(resolved.image_dir, result.image_dir)

    def test_active_pointer_rejects_a_tampered_or_noncanonical_candidate_package(self):
        self.create()
        pointer_path = self.output_root / ".review_reel_production" / "active_package.json"
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        pointer["package_relative_path"] = "inbox_20300102/CAND-20300102-0004_photo_intake"
        pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

        with self.assertRaisesRegex(IntakeViolation, "ACTIVE_PACKAGE_METADATA_MISSING"):
            resolve_active_package(self.output_root)

    def _write_photo_review_evidence(
        self,
        package,
        *,
        suffix="",
        selected_name="after.jpg",
        revision=None,
        supersedes_revision=None,
        revision_reason=None,
        revision_changes=None,
    ):
        if revision is None:
            match = re.search(r"_revision_(\d+)", suffix)
            revision = int(match.group(1)) if match else 1
        if supersedes_revision is None and revision > 1:
            supersedes_revision = revision - 1
        if revision_reason is None:
            revision_reason = (
                "Initial photo review."
                if revision == 1
                else "Correct the accepted photo-review evidence."
            )
        if revision_changes is None:
            revision_changes = [
                "Initial evidence mapping."
                if revision == 1
                else "Activate a new hash-bound evidence set."
            ]
        first = package.image_dir / "after.jpg"
        second = package.image_dir / "detail.jpg"
        first.write_bytes(b"after")
        second.write_bytes(b"detail")
        selected = first if selected_name == "after.jpg" else second
        held = second if selected_name == "after.jpg" else first
        selected_relative = selected.relative_to(package.package_dir).as_posix()
        selection = package.package_dir / "_work" / f"photo_selection_private{suffix}.json"
        selection.parent.mkdir(exist_ok=True)
        selection.write_text(
            json.dumps(
                {
                    "schema_version": "review-reel-photo-selection-v2",
                    "content_id": "004",
                    "checked_at": "2030-01-02T03:04:05Z",
                    "revision": revision,
                    "supersedes_revision": supersedes_revision,
                    "revision_reason": revision_reason,
                    "revision_changes": revision_changes,
                    "unresolved_items": [],
                    "decisions": [
                        {
                            "relative_path": selected_relative,
                            "decision": "use",
                            "reason": "Clear finished installation view.",
                            "privacy_status": "clear",
                            "privacy_risk_categories": [],
                            "editorial_category": "selected_story_evidence",
                            "evidence_classes": ["installed_result"],
                            "remediation": {"action": "none"},
                            "visual_quality": {"full_product_visible": True},
                        },
                        {
                            "relative_path": held.relative_to(package.package_dir).as_posix(),
                            "decision": "hold",
                            "reason": "Redundant detail view.",
                            "privacy_status": "clear",
                            "privacy_risk_categories": [],
                            "editorial_category": "alternate_held",
                            "evidence_classes": ["detail"],
                            "remediation": {"action": "none"},
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        privacy = package.package_dir / f"privacy_asset_manifest{suffix}.json"
        privacy_report = package.package_dir / "_work" / f"privacy_sanitization_report{suffix}.json"
        privacy_report.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "checked": True,
                    "checked_at": "2030-01-02T03:04:05Z",
                    "unresolved_risks": [],
                    "inspection_categories": ["face", "vehicle_plate", "address", "family_photo"],
                    "checked_assets": [
                        {
                            "relative_path": selected_relative,
                            "bytes": selected.stat().st_size,
                            "sha256": hashlib.sha256(selected.read_bytes()).hexdigest(),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        privacy.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "checked": True,
                    "checked_at": "2030-01-02T03:04:05Z",
                    "unresolved_risks": [],
                    "selected_assets": [
                        {
                            "relative_path": selected_relative,
                            "bytes": selected.stat().st_size,
                            "sha256": hashlib.sha256(selected.read_bytes()).hexdigest(),
                        }
                    ],
                    "sanitization_report": privacy_report.relative_to(package.package_dir).as_posix(),
                }
            ),
            encoding="utf-8",
        )
        return selection, privacy

    def _add_sanitized_review_capture(
        self,
        package,
        selection,
        privacy,
        *,
        remediation_action="mask",
        composition_preserved=True,
        pre_masked_identifiers_preserved=True,
        selected_size=(100, 100),
        changed_outside_mask=False,
    ):
        source = package.image_dir / "review_capture.png"
        selected = package.package_dir / "_work" / "review_capture_masked.png"
        image = Image.new("RGB", (100, 100), "white")
        ImageDraw.Draw(image).rectangle((5, 5, 94, 94), outline="black", width=2)
        image.save(source)
        sanitized = image.resize(selected_size)
        draw = ImageDraw.Draw(sanitized)
        draw.rectangle((10, 10, 29, 19), fill="black")
        if changed_outside_mask:
            draw.rectangle((70, 70, 79, 79), fill="red")
        sanitized.save(selected)

        selection_payload = json.loads(selection.read_text(encoding="utf-8"))
        selection_payload["decisions"].append(
            {
                "relative_path": source.relative_to(package.package_dir).as_posix(),
                "decision": "use",
                "reason": "Preserve the supplied review capture and mask only the order number.",
                "privacy_status": "sanitized",
                "privacy_risk_categories": ["order_information"],
                "editorial_category": "selected_story_evidence",
                "evidence_classes": ["review_capture"],
                "remediation": {"action": remediation_action},
                "selected_relative_path": selected.relative_to(package.package_dir).as_posix(),
                "review_capture_integrity": {
                    "composition_preserved": composition_preserved,
                    "pre_masked_identifiers_preserved": pre_masked_identifiers_preserved,
                    "localized_mask_regions": [
                        {
                            "category": "order_information",
                            "x_px": 10,
                            "y_px": 10,
                            "width_px": 20,
                            "height_px": 10,
                        }
                    ],
                },
            }
        )
        selection.write_text(json.dumps(selection_payload), encoding="utf-8")

        evidence = {
            "relative_path": selected.relative_to(package.package_dir).as_posix(),
            "bytes": selected.stat().st_size,
            "sha256": hashlib.sha256(selected.read_bytes()).hexdigest(),
        }
        privacy_payload = json.loads(privacy.read_text(encoding="utf-8"))
        privacy_payload["selected_assets"].append(evidence)
        privacy.write_text(json.dumps(privacy_payload), encoding="utf-8")
        report = package.package_dir / privacy_payload["sanitization_report"]
        report_payload = json.loads(report.read_text(encoding="utf-8"))
        report_payload["checked_assets"].append(evidence)
        report.write_text(json.dumps(report_payload), encoding="utf-8")

    def test_recipe_scaffold_writes_complete_revisioned_json_after_photo_review(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package, suffix="_revision_001")
        selection_payload = json.loads(selection.read_text(encoding="utf-8"))
        before = selection_payload["decisions"][1]
        before["decision"] = "use"
        before["reason"] = "Clear before-state evidence."
        before["editorial_category"] = "selected_story_evidence"
        before["evidence_classes"] = ["before_state"]
        before_path = package.package_dir / before["relative_path"]
        privacy_payload = json.loads(privacy.read_text(encoding="utf-8"))
        before_evidence = {
            "relative_path": before["relative_path"],
            "bytes": before_path.stat().st_size,
            "sha256": hashlib.sha256(before_path.read_bytes()).hexdigest(),
        }
        privacy_payload["selected_assets"].append(before_evidence)
        privacy.write_text(json.dumps(privacy_payload), encoding="utf-8")
        report = package.package_dir / privacy_payload["sanitization_report"]
        report_payload = json.loads(report.read_text(encoding="utf-8"))
        report_payload["checked_assets"].append(before_evidence)
        report.write_text(json.dumps(report_payload), encoding="utf-8")
        selection.write_text(json.dumps(selection_payload), encoding="utf-8")
        self._add_sanitized_review_capture(package, selection, privacy)
        record_photo_review(
            output_root=self.output_root,
            expected_content_id="004",
            selection_path=selection,
            privacy_manifest_path=privacy,
            now=self.now,
        )

        result = write_recipe_scaffold(output_root=self.output_root, expected_content_id="004")

        planning_path = Path(result["planning"])
        edit_path = Path(result["edit"])
        self.assertTrue(planning_path.is_file())
        self.assertTrue(edit_path.is_file())
        self.assertEqual(planning_path.parent.name, "revision_001")
        self.assertEqual(result["next_action"], "complete_scaffold_content_then_generate_one_shot_tts")
        planning = json.loads(planning_path.read_text(encoding="utf-8"))
        edit = json.loads(edit_path.read_text(encoding="utf-8"))
        self.assertEqual(planning["scaffold"]["source_photo_review_revision"], 1)
        self.assertEqual(
            edit["source"]["privacy_sanitization_report"],
            "_work/privacy_sanitization_report_revision_001.json",
        )
        self.assertEqual(
            {issue["code"] for issue in validate_review_reels_one_shot_contract(planning, edit)["issues"]},
            {"RECIPE_SCAFFOLD_INCOMPLETE"},
        )

        for payload, path in ((planning, planning_path), (edit, edit_path)):
            payload["scaffold"]["status"] = "complete"
            payload["scaffold"]["pending_fields"] = []
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        guidance = workflow_next(self.output_root)
        self.assertEqual(guidance["next_action"], "repair_recipe_scaffold_qa_issues")
        self.assertIn("RECIPE_SCAFFOLD_PLACEHOLDER_REMAINS", guidance["blocking_issue_codes"])

        planning["analysis"] = {
            "customer_problem": "현관 사용 불편",
            "before_pain": "현관 동선 불편",
            "after_change": "설치 후 동선 개선",
            "customer_emotion": ["편안함"],
        }
        planning["writer_brief"]["one_line_story"] = "현관 동선이 설치 후 편해진 리뷰 이야기"
        for scene in planning["scenes"]:
            scene["meaning_match_evidence"] = "review_source.text and selected photo evidence"
        edit["audio_plan"]["tts_text_sha256"] = "a" * 64
        edit["audio_plan"]["final_voice_sha256"] = "b" * 64
        planning_path.write_text(json.dumps(planning, ensure_ascii=False), encoding="utf-8")
        edit_path.write_text(json.dumps(edit, ensure_ascii=False), encoding="utf-8")
        guidance = workflow_next(self.output_root)
        self.assertEqual(guidance["next_action"], "write_standard_script_from_completed_scaffold")

        source = edit["source"]
        script = package.package_dir / source["script"]
        script.write_text("# fixture script\n", encoding="utf-8")
        guidance = workflow_next(self.output_root)
        self.assertEqual(guidance["next_action"], "generate_official_one_shot_tts")
        self.assertIn("generate_one_shot_tts.py", guidance["next_command"])

        for relative_path, content in (
            (source["srt"], "1\n00:00:00,000 --> 00:00:01,000\nfixture\n"),
            (source["voice"], "fixture voice"),
            (source["tts_generation_report"], "{}"),
        ):
            target = package.package_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        guidance = workflow_next(self.output_root)
        self.assertEqual(guidance["next_action"], "listen_to_voice_then_record_review")
        self.assertIsNone(guidance["next_command"])

        manual_reviews = package.package_dir / "_work" / "manual_reviews"
        manual_reviews.mkdir(parents=True)
        (manual_reviews / "voice_review_fixture.json").write_text("{}", encoding="utf-8")
        guidance = workflow_next(self.output_root)
        self.assertEqual(guidance["next_action"], "run_one_shot_preflight")
        self.assertIn("--one-shot-html", guidance["next_command"])

        (package.package_dir / "sync_manifest.json").write_text("{}", encoding="utf-8")
        guidance = workflow_next(self.output_root)
        self.assertEqual(guidance["next_action"], "build_one_shot_html")

        html = package.package_dir / "004_fixture_html_preview_v2" / "index.html"
        html.parent.mkdir()
        html.write_text("<!doctype html>", encoding="utf-8")
        guidance = workflow_next(self.output_root)
        self.assertEqual(guidance["next_action"], "inspect_html_frames_then_record_review")

        (manual_reviews / "html_review_fixture.json").write_text("{}", encoding="utf-8")
        guidance = workflow_next(self.output_root)
        self.assertEqual(guidance["next_action"], "wait_for_explicit_html_approval_then_record_it")
        self.assertTrue(guidance["approval_required"])
        self.assertIsNone(guidance["next_command"])

    def test_photo_review_accepts_a_full_composition_review_capture_with_only_a_local_mask(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)
        self._add_sanitized_review_capture(package, selection, privacy)

        reviewed = record_photo_review(
            output_root=self.output_root,
            selection_path=selection,
            privacy_manifest_path=privacy,
            now=self.now,
        )

        self.assertEqual(reviewed.metadata["photo_review"]["selected_asset_count"], 2)

    def test_photo_review_rejects_cropping_a_user_supplied_review_capture(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)
        self._add_sanitized_review_capture(package, selection, privacy, remediation_action="crop")

        with self.assertRaisesRegex(IntakeViolation, "REVIEW_CAPTURE_CROP_FORBIDDEN"):
            record_photo_review(
                output_root=self.output_root,
                selection_path=selection,
                privacy_manifest_path=privacy,
                now=self.now,
            )

    def test_photo_review_rejects_resizing_or_reframing_a_review_capture(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)
        self._add_sanitized_review_capture(package, selection, privacy, selected_size=(80, 100))

        with self.assertRaisesRegex(IntakeViolation, "REVIEW_CAPTURE_COMPOSITION_CHANGED"):
            record_photo_review(
                output_root=self.output_root,
                selection_path=selection,
                privacy_manifest_path=privacy,
                now=self.now,
            )

    def test_photo_review_rejects_pixel_changes_outside_the_declared_review_mask(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)
        self._add_sanitized_review_capture(package, selection, privacy, changed_outside_mask=True)

        with self.assertRaisesRegex(IntakeViolation, "REVIEW_CAPTURE_COMPOSITION_CHANGED"):
            record_photo_review(
                output_root=self.output_root,
                selection_path=selection,
                privacy_manifest_path=privacy,
                now=self.now,
            )

    def test_photo_review_requires_pre_masked_review_identifiers_to_remain_untouched(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)
        self._add_sanitized_review_capture(
            package,
            selection,
            privacy,
            pre_masked_identifiers_preserved=False,
        )

        with self.assertRaisesRegex(IntakeViolation, "REVIEW_CAPTURE_PREMASKED_ID_TOUCHED"):
            record_photo_review(
                output_root=self.output_root,
                selection_path=selection,
                privacy_manifest_path=privacy,
                now=self.now,
            )

    def test_photo_review_requires_review_capture_integrity_metadata(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)
        self._add_sanitized_review_capture(package, selection, privacy)
        payload = json.loads(selection.read_text(encoding="utf-8"))
        payload["decisions"][-1].pop("review_capture_integrity")
        selection.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(IntakeViolation, "REVIEW_CAPTURE_INTEGRITY_MISSING"):
            record_photo_review(
                output_root=self.output_root,
                selection_path=selection,
                privacy_manifest_path=privacy,
                now=self.now,
            )

    def test_photo_review_rejects_a_nonminimal_review_capture_mask(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)
        self._add_sanitized_review_capture(package, selection, privacy)
        payload = json.loads(selection.read_text(encoding="utf-8"))
        region = payload["decisions"][-1]["review_capture_integrity"]["localized_mask_regions"][0]
        region.update({"x_px": 0, "y_px": 0, "width_px": 80, "height_px": 80})
        selection.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(IntakeViolation, "REVIEW_CAPTURE_MASK_NOT_MINIMAL"):
            record_photo_review(
                output_root=self.output_root,
                selection_path=selection,
                privacy_manifest_path=privacy,
                now=self.now,
            )

    def test_photo_review_is_the_only_evidence_bound_transition_to_photo_reviewed(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)

        reviewed = record_photo_review(
            output_root=self.output_root,
            selection_path=selection,
            privacy_manifest_path=privacy,
            now=self.now,
        )

        self.assertEqual(reviewed.metadata["lifecycle_state"], "photo_reviewed")
        self.assertTrue(reviewed.metadata["approvals"]["photo_checked"])
        self.assertFalse(reviewed.metadata["approvals"]["html_scope_authorized"])
        self.assertFalse(reviewed.metadata["approvals"]["mp4_scope_authorized"])
        self.assertEqual(reviewed.metadata["photo_review"]["source_media_count"], 2)
        self.assertEqual(reviewed.metadata["photo_review"]["selected_asset_count"], 1)
        self.assertEqual(reviewed.metadata["photo_review"]["revision"], 1)
        self.assertNotIn("photo_review_history", reviewed.metadata)
        self.assertIn("photo_checked: true", (package.package_dir / "STATUS.md").read_text(encoding="utf-8"))
        resolved = resolve_active_package(self.output_root)
        self.assertEqual(resolved.metadata["lifecycle_state"], "photo_reviewed")

    def test_photo_review_revision_preserves_the_previous_evidence_and_activates_new_files(self):
        package = self.create()
        selection_v1, privacy_v1 = self._write_photo_review_evidence(package)
        first = record_photo_review(
            output_root=self.output_root,
            selection_path=selection_v1,
            privacy_manifest_path=privacy_v1,
            now=self.now,
        )
        first_review = dict(first.metadata["photo_review"])
        selection_v1_bytes = selection_v1.read_bytes()
        privacy_v1_bytes = privacy_v1.read_bytes()
        selection_v2, privacy_v2 = self._write_photo_review_evidence(
            package,
            suffix="_revision_002",
            selected_name="detail.jpg",
        )

        revised = record_photo_review(
            output_root=self.output_root,
            selection_path=selection_v2,
            privacy_manifest_path=privacy_v2,
            now=self.now.replace(second=6),
        )

        self.assertEqual(revised.metadata["photo_review"]["revision"], 2)
        self.assertEqual(revised.metadata["photo_review"]["supersedes_revision"], 1)
        self.assertEqual(
            revised.metadata["photo_review"]["revision_reason"],
            "Correct the accepted photo-review evidence.",
        )
        self.assertEqual(
            revised.metadata["photo_review"]["revision_changes"],
            ["Activate a new hash-bound evidence set."],
        )
        self.assertEqual(revised.metadata["photo_review"]["selection"]["relative_path"], "_work/photo_selection_private_revision_002.json")
        self.assertEqual(revised.metadata["photo_review_history"], [first_review])
        self.assertEqual(selection_v1.read_bytes(), selection_v1_bytes)
        self.assertEqual(privacy_v1.read_bytes(), privacy_v1_bytes)

    def test_photo_review_revision_rejects_reusing_the_active_evidence_paths(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)
        first = record_photo_review(
            output_root=self.output_root,
            selection_path=selection,
            privacy_manifest_path=privacy,
            now=self.now,
        )
        metadata_before = (package.package_dir / "CANONICAL_PACKAGE_METADATA.json").read_bytes()

        with self.assertRaisesRegex(IntakeViolation, "PHOTO_REVIEW_REVISION_EVIDENCE_REUSED"):
            record_photo_review(
                output_root=self.output_root,
                selection_path=selection,
                privacy_manifest_path=privacy,
                now=self.now.replace(second=6),
            )

        self.assertEqual((package.package_dir / "CANONICAL_PACKAGE_METADATA.json").read_bytes(), metadata_before)
        self.assertEqual(resolve_active_package(self.output_root).metadata["photo_review"], first.metadata["photo_review"])

    def test_photo_review_requires_hash_bound_revision_context_in_the_selection_file(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)
        value = json.loads(selection.read_text(encoding="utf-8"))
        for field in ("revision", "supersedes_revision", "revision_reason", "revision_changes"):
            value.pop(field, None)
        selection.write_text(json.dumps(value), encoding="utf-8")

        with self.assertRaisesRegex(IntakeViolation, "PHOTO_SELECTION_REVISION_CONTEXT_INVALID"):
            record_photo_review(
                output_root=self.output_root,
                selection_path=selection,
                privacy_manifest_path=privacy,
                now=self.now,
            )

    def test_photo_review_revision_context_must_match_the_active_revision(self):
        package = self.create()
        selection_v1, privacy_v1 = self._write_photo_review_evidence(package)
        record_photo_review(
            output_root=self.output_root,
            selection_path=selection_v1,
            privacy_manifest_path=privacy_v1,
            now=self.now,
        )
        selection_v2, privacy_v2 = self._write_photo_review_evidence(
            package,
            suffix="_revision_002",
            selected_name="detail.jpg",
            revision=3,
            supersedes_revision=2,
            revision_reason="Invalid skipped revision.",
            revision_changes=["Skip revision two."],
        )

        with self.assertRaisesRegex(IntakeViolation, "PHOTO_SELECTION_REVISION_CONTEXT_MISMATCH"):
            record_photo_review(
                output_root=self.output_root,
                selection_path=selection_v2,
                privacy_manifest_path=privacy_v2,
                now=self.now.replace(second=6),
            )

    def test_photo_review_revision_rejects_reusing_any_historical_evidence_path(self):
        package = self.create()
        selection_v1, privacy_v1 = self._write_photo_review_evidence(package)
        record_photo_review(
            output_root=self.output_root,
            selection_path=selection_v1,
            privacy_manifest_path=privacy_v1,
            now=self.now,
        )
        selection_v2, privacy_v2 = self._write_photo_review_evidence(
            package, suffix="_revision_002", selected_name="detail.jpg"
        )
        record_photo_review(
            output_root=self.output_root,
            selection_path=selection_v2,
            privacy_manifest_path=privacy_v2,
            now=self.now.replace(second=6),
        )
        metadata_before = (package.package_dir / "CANONICAL_PACKAGE_METADATA.json").read_bytes()

        with self.assertRaisesRegex(IntakeViolation, "PHOTO_REVIEW_REVISION_EVIDENCE_REUSED"):
            record_photo_review(
                output_root=self.output_root,
                selection_path=selection_v1,
                privacy_manifest_path=privacy_v1,
                now=self.now.replace(second=7),
            )

        self.assertEqual((package.package_dir / "CANONICAL_PACKAGE_METADATA.json").read_bytes(), metadata_before)

    def test_photo_review_revision_rejects_changed_historical_evidence_before_accepting_new_files(self):
        package = self.create()
        selection_v1, privacy_v1 = self._write_photo_review_evidence(package)
        record_photo_review(
            output_root=self.output_root,
            selection_path=selection_v1,
            privacy_manifest_path=privacy_v1,
            now=self.now,
        )
        selection_v2, privacy_v2 = self._write_photo_review_evidence(
            package, suffix="_revision_002", selected_name="detail.jpg"
        )
        record_photo_review(
            output_root=self.output_root,
            selection_path=selection_v2,
            privacy_manifest_path=privacy_v2,
            now=self.now.replace(second=6),
        )
        selection_v1.write_text("{}", encoding="utf-8")
        selection_v3, privacy_v3 = self._write_photo_review_evidence(
            package, suffix="_revision_003", selected_name="after.jpg"
        )
        metadata_before = (package.package_dir / "CANONICAL_PACKAGE_METADATA.json").read_bytes()

        with self.assertRaisesRegex(IntakeViolation, "PHOTO_REVIEW_HISTORY_EVIDENCE_CHANGED"):
            record_photo_review(
                output_root=self.output_root,
                selection_path=selection_v3,
                privacy_manifest_path=privacy_v3,
                now=self.now.replace(second=7),
            )

        self.assertEqual((package.package_dir / "CANONICAL_PACKAGE_METADATA.json").read_bytes(), metadata_before)

    def test_rejected_photo_review_attempt_writes_an_audit_receipt_without_changing_active_metadata(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)
        record_photo_review(
            output_root=self.output_root,
            selection_path=selection,
            privacy_manifest_path=privacy,
            now=self.now,
        )
        metadata_before = (package.package_dir / "CANONICAL_PACKAGE_METADATA.json").read_bytes()
        bad_selection, bad_privacy = self._write_photo_review_evidence(
            package,
            suffix="_revision_002",
            selected_name="detail.jpg",
        )
        payload = json.loads(bad_selection.read_text(encoding="utf-8"))
        payload["decisions"][1].update(
            {
                "decision": "exclude",
                "privacy_status": "blocked",
                "privacy_risk_categories": ["bare_foot"],
                "editorial_category": "privacy_unrecoverable",
                "remediation": {
                    "action": "infeasible",
                    "attempted_actions": ["crop"],
                    "infeasible_category": "risk_covers_essential_subject",
                    "masking_infeasible_reason": "Fixture.",
                    "manual_review_reference": "fixture",
                },
            }
        )
        bad_selection.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(IntakeViolation, "PHOTO_PRIVACY_CATEGORY_INVALID"):
            record_photo_review(
                output_root=self.output_root,
                selection_path=bad_selection,
                privacy_manifest_path=bad_privacy,
                now=self.now.replace(second=7),
            )

        self.assertEqual((package.package_dir / "CANONICAL_PACKAGE_METADATA.json").read_bytes(), metadata_before)
        receipts = list((package.package_dir / "_work" / "photo_review_rejections").glob("*.json"))
        self.assertEqual(len(receipts), 1)
        receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
        self.assertEqual(receipt["error_code"], "PHOTO_PRIVACY_CATEGORY_INVALID")
        self.assertEqual(receipt["selection"]["relative_path"], "_work/photo_selection_private_revision_002.json")

    def test_photo_review_rejects_an_incomplete_photo_decision_record(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)
        payload = json.loads(selection.read_text(encoding="utf-8"))
        payload["decisions"].pop()
        selection.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(IntakeViolation, "PHOTO_SELECTION_INCOMPLETE"):
            record_photo_review(
                output_root=self.output_root,
                selection_path=selection,
                privacy_manifest_path=privacy,
                now=self.now,
            )

        self.assertEqual(resolve_active_package(self.output_root).metadata["lifecycle_state"], "photo_intake_pending")

    def test_photo_review_rejects_non_privacy_observations_as_blocking_categories(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)
        payload = json.loads(selection.read_text(encoding="utf-8"))
        decision = payload["decisions"][1]
        decision.update(
            {
                "decision": "exclude",
                "privacy_status": "blocked",
                "privacy_risk_categories": ["bare_foot"],
                "editorial_category": "privacy_unrecoverable",
                "remediation": {
                    "action": "infeasible",
                    "attempted_actions": ["crop", "blur"],
                    "infeasible_category": "risk_covers_essential_subject",
                    "masking_infeasible_reason": "Fixture reason.",
                    "manual_review_reference": "fixture-review",
                },
            }
        )
        selection.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(IntakeViolation, "PHOTO_PRIVACY_CATEGORY_INVALID"):
            record_photo_review(
                output_root=self.output_root,
                selection_path=selection,
                privacy_manifest_path=privacy,
                now=self.now,
            )

    def test_photo_review_requires_masking_evidence_before_privacy_exclusion(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)
        payload = json.loads(selection.read_text(encoding="utf-8"))
        decision = payload["decisions"][1]
        decision.update(
            {
                "decision": "exclude",
                "privacy_status": "blocked",
                "privacy_risk_categories": ["reflected_identifiable_face"],
                "editorial_category": "privacy_unrecoverable",
                "remediation": {"action": "none"},
            }
        )
        selection.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(IntakeViolation, "MASKING_FIRST_NOT_APPLIED"):
            record_photo_review(
                output_root=self.output_root,
                selection_path=selection,
                privacy_manifest_path=privacy,
                now=self.now,
            )

    def test_photo_review_allows_editorial_exclusion_without_a_masking_reason(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)
        payload = json.loads(selection.read_text(encoding="utf-8"))
        payload["decisions"][1].update(
            {
                "decision": "exclude",
                "privacy_status": "clear",
                "privacy_risk_categories": [],
                "editorial_category": "duplicate",
                "remediation": {"action": "none"},
            }
        )
        selection.write_text(json.dumps(payload), encoding="utf-8")

        reviewed = record_photo_review(
            output_root=self.output_root,
            selection_path=selection,
            privacy_manifest_path=privacy,
            now=self.now,
        )

        self.assertEqual(reviewed.metadata["photo_review"]["selected_asset_count"], 1)

    def test_photo_review_can_hold_a_recoverable_privacy_risk_until_the_narrative_is_decided(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)
        payload = json.loads(selection.read_text(encoding="utf-8"))
        payload["decisions"][1].update(
            {
                "decision": "hold",
                "privacy_status": "needs_sanitization",
                "privacy_risk_categories": ["delivery_label"],
                "editorial_category": "alternate_held",
                "remediation": {
                    "action": "pending",
                    "candidate_actions": ["crop", "blur"],
                },
            }
        )
        selection.write_text(json.dumps(payload), encoding="utf-8")

        reviewed = record_photo_review(
            output_root=self.output_root,
            selection_path=selection,
            privacy_manifest_path=privacy,
            now=self.now,
        )

        self.assertEqual(reviewed.metadata["photo_review"]["selected_asset_count"], 1)

    def test_photo_review_cannot_use_an_asset_that_still_needs_sanitization(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)
        payload = json.loads(selection.read_text(encoding="utf-8"))
        payload["decisions"][0].update(
            {
                "privacy_status": "needs_sanitization",
                "privacy_risk_categories": ["delivery_label"],
                "remediation": {
                    "action": "pending",
                    "candidate_actions": ["crop", "blur"],
                },
            }
        )
        selection.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(IntakeViolation, "PHOTO_PRIVACY_STATE_INVALID"):
            record_photo_review(
                output_root=self.output_root,
                selection_path=selection,
                privacy_manifest_path=privacy,
                now=self.now,
            )

    def test_photo_review_accepts_a_manually_reviewed_unrecoverable_privacy_exclusion(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)
        payload = json.loads(selection.read_text(encoding="utf-8"))
        payload["decisions"][1].update(
            {
                "decision": "exclude",
                "privacy_status": "blocked",
                "privacy_risk_categories": ["reflected_identifiable_face"],
                "editorial_category": "privacy_unrecoverable",
                "remediation": {
                    "action": "infeasible",
                    "attempted_actions": ["crop", "blur"],
                    "infeasible_category": "risk_covers_essential_subject",
                    "masking_infeasible_reason": "Masking would cover the only product evidence.",
                    "manual_review_reference": "fixture-review",
                },
            }
        )
        selection.write_text(json.dumps(payload), encoding="utf-8")

        reviewed = record_photo_review(
            output_root=self.output_root,
            selection_path=selection,
            privacy_manifest_path=privacy,
            now=self.now,
        )

        self.assertEqual(reviewed.metadata["photo_review"]["selected_asset_count"], 1)

    def test_one_shot_html_commands_resolve_the_active_package_and_never_include_render(self):
        result = self.create()
        planning = self.root / "planning.json"
        planning.write_text(
            json.dumps(
                {
                    "workflow_contract": {
                        "name": "review-reels-one-shot-v2",
                        "html_scope_authorized": True,
                        "mp4_scope_authorized": False,
                    }
                }
            ),
            encoding="utf-8",
        )
        edit = self.root / "edit.json"
        privacy = self.root / "privacy.json"
        edit.write_text("{}", encoding="utf-8")
        privacy.write_text("{}", encoding="utf-8")

        commands = build_one_shot_html_commands(
            output_root=self.output_root,
            planning_path=planning,
            edit_path=edit,
            privacy_manifest_path=privacy,
        )

        self.assertEqual([command[2] for command in commands], ["preflight", "html"])
        self.assertEqual(commands[0][commands[0].index("--package") + 1], str(result.package_dir))
        self.assertTrue(all("--one-shot-html" in command for command in commands))
        self.assertTrue(all("render" not in command for command in commands))
        self.assertTrue(all("--out" not in command for command in commands))

    def test_one_shot_html_rejects_any_mp4_scope_before_running_production_commands(self):
        self.create()
        planning = self.root / "planning.json"
        planning.write_text(
            json.dumps(
                {
                    "workflow_contract": {
                        "name": "review-reels-one-shot-v2",
                        "html_scope_authorized": True,
                        "mp4_scope_authorized": True,
                    }
                }
            ),
            encoding="utf-8",
        )
        edit = self.root / "edit.json"
        privacy = self.root / "privacy.json"
        edit.write_text("{}", encoding="utf-8")
        privacy.write_text("{}", encoding="utf-8")

        with patch("video_engine_v2.review_reel_intake.subprocess.run") as runner:
            with self.assertRaisesRegex(IntakeViolation, "MP4_SCOPE_MUST_REMAIN_UNAUTHORIZED"):
                run_one_shot_html(
                    output_root=self.output_root,
                    planning_path=planning,
                    edit_path=edit,
                    privacy_manifest_path=privacy,
                )
        runner.assert_not_called()

    def test_cli_route_has_a_machine_readable_state_transition(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "review_reel_intake.py"
        result = subprocess.run(
            [sys.executable, str(script), "route", "--user-command", "리뷰 릴스 만들자"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["workflow"], "review_reel_production")

    def test_cli_status_exposes_active_identity_and_next_safe_action(self):
        package = self.create()
        script = Path(__file__).resolve().parents[1] / "scripts" / "review_reel_intake.py"

        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "status",
                "--output-root",
                str(self.output_root),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        status = json.loads(result.stdout)
        self.assertEqual(status["workflow"], "review_reel_production")
        self.assertEqual(status["content_id"], "004")
        self.assertEqual(status["lifecycle_state"], "photo_intake_pending")
        self.assertEqual(Path(status["package"]), package.package_dir)
        self.assertEqual(status["next_action"], "place_photos_then_run_photo_review")

    def test_active_status_never_sends_a_completed_package_back_to_tts(self):
        self.create()
        completed_state = {
            "render_artifact_present": True,
            "render_complete": True,
            "qa_reviewed": True,
            "final_delivery_complete": True,
            "html_approved": True,
            "mp4_render_approved": True,
        }

        with patch("video_engine_v2.package_state.map_legacy_package", return_value=completed_state):
            status = active_package_status(self.output_root)

        self.assertEqual(status["render_complete"], True)
        self.assertEqual(status["qa_reviewed"], True)
        self.assertEqual(status["final_delivery_complete"], True)
        self.assertEqual(status["next_action"], "no_action_final_delivery_complete")

    def test_workflow_next_centralizes_safe_commands_without_crossing_approval_gates(self):
        package = self.create()

        pending = workflow_next(self.output_root)

        self.assertEqual(pending["next_action"], "place_photos_then_run_photo_review")
        self.assertIsNone(pending["next_command"])
        self.assertEqual(pending["required_inputs"], ["selection", "privacy_manifest"])
        self.assertFalse(pending["approval_required"])

        photo_reviewed_status = {
            "workflow": "review_reel_production",
            "content_id": "004",
            "lifecycle_state": "photo_reviewed",
            "package": str(package.package_dir),
            "next_action": "prepare_planning_script_tts",
        }
        with patch(
            "video_engine_v2.review_reel_intake.active_package_status",
            return_value=photo_reviewed_status,
        ):
            scaffold = workflow_next(self.output_root)
        self.assertEqual(scaffold["next_action"], "generate_recipe_scaffold")
        self.assertEqual(
            scaffold["next_command"],
            f'python scripts/review_reel_intake.py recipe-scaffold --output-root "{self.output_root.resolve()}" --expected-content-id "004"',
        )

        completed_status = {
            **photo_reviewed_status,
            "final_delivery_complete": True,
            "next_action": "no_action_final_delivery_complete",
        }
        with patch(
            "video_engine_v2.review_reel_intake.active_package_status",
            return_value=completed_status,
        ):
            completed = workflow_next(self.output_root)
        self.assertIsNone(completed["next_command"])
        self.assertEqual(completed["new_production_action"], "select_material_bank_candidate_then_create")
        self.assertIn("create-from-material-bank", completed["new_production_command_template"])

        approval_status = {
            **photo_reviewed_status,
            "next_action": "wait_for_explicit_mp4_approval_then_record_it",
        }
        with patch(
            "video_engine_v2.review_reel_intake.active_package_status",
            return_value=approval_status,
        ):
            approval = workflow_next(self.output_root)
        self.assertTrue(approval["approval_required"])
        self.assertIsNone(approval["next_command"])

    def test_photo_review_cli_rejects_stale_active_identity_before_reading_evidence(self):
        self.create()
        script = Path(__file__).resolve().parents[1] / "scripts" / "review_reel_intake.py"

        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "photo-review",
                "--output-root",
                str(self.output_root),
                "--expected-content-id",
                "999",
                "--selection",
                str(self.root / "missing-selection.json"),
                "--privacy-manifest",
                str(self.root / "missing-privacy.json"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("ACTIVE_PACKAGE_CONTENT_ID_MISMATCH", result.stderr)
        self.assertNotIn("PHOTO_SELECTION_MISSING", result.stderr)

    def test_one_shot_cli_rejects_stale_active_identity_before_reading_recipes(self):
        self.create()
        script = Path(__file__).resolve().parents[1] / "scripts" / "review_reel_intake.py"

        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "one-shot-html",
                "--output-root",
                str(self.output_root),
                "--expected-content-id",
                "999",
                "--planning",
                str(self.root / "missing-planning.json"),
                "--edit",
                str(self.root / "missing-edit.json"),
                "--privacy-manifest",
                str(self.root / "missing-privacy.json"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("ACTIVE_PACKAGE_CONTENT_ID_MISMATCH", result.stderr)
        self.assertNotIn("PLANNING_RECIPE_MISSING", result.stderr)


if __name__ == "__main__":
    unittest.main()
