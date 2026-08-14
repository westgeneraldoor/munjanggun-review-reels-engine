import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from video_engine_v2.review_reel_intake import (
    IntakeViolation,
    build_one_shot_html_commands,
    create_canonical_package,
    create_canonical_package_from_material_bank,
    record_photo_review,
    resolve_active_package,
    route_user_command,
    run_one_shot_html,
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
        packages = list(self.output_root.glob("inbox_*/*"))
        self.assertEqual([path.name for path in packages if path.is_dir()], [first.package_dir.name])

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

        packages = list(self.output_root.glob("inbox_*/*"))
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

    def _write_photo_review_evidence(self, package):
        first = package.image_dir / "after.jpg"
        second = package.image_dir / "detail.jpg"
        first.write_bytes(b"after")
        second.write_bytes(b"detail")
        selected_relative = first.relative_to(package.package_dir).as_posix()
        selection = package.package_dir / "_work" / "photo_selection_private.json"
        selection.parent.mkdir()
        selection.write_text(
            json.dumps(
                {
                    "schema_version": "review-reel-photo-selection-v2",
                    "content_id": "004",
                    "checked_at": "2030-01-02T03:04:05Z",
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
                            "relative_path": second.relative_to(package.package_dir).as_posix(),
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
        privacy = package.package_dir / "privacy_asset_manifest.json"
        privacy_report = package.package_dir / "_work" / "privacy_sanitization_report.json"
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
                            "bytes": first.stat().st_size,
                            "sha256": hashlib.sha256(first.read_bytes()).hexdigest(),
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
                            "bytes": first.stat().st_size,
                            "sha256": hashlib.sha256(first.read_bytes()).hexdigest(),
                        }
                    ],
                    "sanitization_report": "_work/privacy_sanitization_report.json",
                }
            ),
            encoding="utf-8",
        )
        return selection, privacy

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
        self.assertIn("photo_checked: true", (package.package_dir / "STATUS.md").read_text(encoding="utf-8"))
        resolved = resolve_active_package(self.output_root)
        self.assertEqual(resolved.metadata["lifecycle_state"], "photo_reviewed")

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


if __name__ == "__main__":
    unittest.main()
