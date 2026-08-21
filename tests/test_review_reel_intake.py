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

from video_engine_v2.manual_review import (
    HTML_REVIEW_CHECKS,
    VOICE_REVIEW_CHECKS,
    record_html_review,
    record_voice_review,
)
from video_engine_v2.qa_guidance import explain_error
from video_engine_v2.reels_qa import validate_review_reels_one_shot_contract
import video_engine_v2.review_reel_intake as review_intake
from video_engine_v2.review_reel_intake import (
    IntakeViolation,
    active_package_status,
    build_one_shot_html_commands,
    create_canonical_package,
    create_canonical_package_from_material_bank,
    inspect_material_bank_candidate,
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

    def test_korean_render_intent_requires_active_package_or_html_approval_context(self):
        with_package = route_user_command("진행해 그리고 렌더까지 해", active_review_reel_package=True)
        self.assertEqual(with_package["workflow"], "review_reel_production")
        self.assertEqual(with_package["state"], "mp4_render_intent_requested")
        self.assertEqual(
            with_package["next_action"],
            "resolve_active_package_then_record_hash_bound_approvals",
        )
        self.assertNotIn("approved", with_package)

        without_context = route_user_command("진행해 그리고 렌더까지 해")
        self.assertEqual(without_context["workflow"], "generic_review_content")
        self.assertNotEqual(without_context["state"], "mp4_render_intent_requested")

        html_context = route_user_command("HTML 승인. 렌더까지 해")
        self.assertEqual(html_context["workflow"], "review_reel_production")
        self.assertEqual(html_context["state"], "html_approval_and_mp4_render_intent_requested")
        self.assertNotIn("approved", html_context)

        generic_render = route_user_command("하이퍼프레임 렌더까지 해")
        self.assertEqual(generic_render["workflow"], "generic_review_content")

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

    def test_material_bank_candidate_with_legacy_output_is_not_reported_or_allocated_as_new(self):
        material_bank = self.root / "candidate_top60_private.jsonl"
        candidate_id = "CAND-20300102-0001"
        material_bank.write_text(
            json.dumps(
                {
                    "inventory_id": "INV-FIXTURE-1",
                    "review_id": "REVIEW-FIXTURE-1",
                    "order_id": "ORDER-FIXTURE-1",
                    "review_text": "Legacy fixture review.",
                    "candidate_id": candidate_id,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        legacy_package = (
            self.output_root
            / "inbox_20291231"
            / f"{candidate_id}_legacy_html_20291231_235959"
        )
        legacy_package.mkdir(parents=True)

        inspection = inspect_material_bank_candidate(
            output_root=self.output_root,
            reviews_root=self.root / "reviews",
            material_bank_path=material_bank,
            candidate_id=candidate_id,
        )

        self.assertFalse(inspection["eligible_for_new_package"])
        self.assertEqual(inspection["status"], "legacy_package_present")
        self.assertEqual(inspection["blocker_code"], "CANDIDATE_LEGACY_PACKAGE_PRESENT")
        self.assertEqual(
            inspection["legacy_package_relative_paths"],
            [f"inbox_20291231/{legacy_package.name}"],
        )

        with self.assertRaisesRegex(IntakeViolation, "CANDIDATE_LEGACY_PACKAGE_PRESENT"):
            create_canonical_package_from_material_bank(
                output_root=self.output_root,
                reviews_root=self.root / "reviews",
                material_bank_path=material_bank,
                candidate_id=candidate_id,
                content_slug="중복금지",
                now=self.now,
            )

        state_dir = self.output_root / ".review_reel_production"
        self.assertFalse((state_dir / "source_registry_private.json").exists())
        self.assertFalse((state_dir / "material_bank_inventory_private.json").exists())
        self.assertFalse(any(self.output_root.glob("[0-9][0-9][0-9]_*")))

    def test_material_bank_candidate_with_official_binding_reuses_it_even_if_legacy_output_exists(self):
        material_bank = self.root / "candidate_top60_private.jsonl"
        candidate_id = "CAND-20300102-0001"
        material_bank.write_text(
            json.dumps(
                {
                    "inventory_id": "INV-FIXTURE-1",
                    "review_id": "REVIEW-FIXTURE-1",
                    "order_id": "ORDER-FIXTURE-1",
                    "review_text": "Official fixture review.",
                    "candidate_id": candidate_id,
                }
            )
            + "\n",
            encoding="utf-8",
        )

        first = create_canonical_package_from_material_bank(
            output_root=self.output_root,
            reviews_root=self.root / "reviews",
            material_bank_path=material_bank,
            candidate_id=candidate_id,
            content_slug="공식패키지",
            now=self.now,
        )
        (self.output_root / "inbox_legacy" / f"{candidate_id}_old").mkdir(parents=True)

        inspection = inspect_material_bank_candidate(
            output_root=self.output_root,
            reviews_root=self.root / "reviews",
            material_bank_path=material_bank,
            candidate_id=candidate_id,
        )
        repeated = create_canonical_package_from_material_bank(
            output_root=self.output_root,
            reviews_root=self.root / "reviews",
            material_bank_path=material_bank,
            candidate_id=candidate_id,
            content_slug="다른이름",
            now=self.now,
        )

        self.assertFalse(inspection["eligible_for_new_package"])
        self.assertEqual(inspection["status"], "official_binding_exists")
        self.assertEqual(inspection["existing_content_id"], first.metadata["content_id"])
        self.assertEqual(repeated.package_dir, first.package_dir)
        self.assertTrue(repeated.reused_existing)

    def test_material_bank_candidate_used_as_legacy_related_review_is_also_blocked(self):
        material_bank = self.root / "candidate_top60_private.jsonl"
        related_candidate = "CAND-20300102-0002"
        material_bank.write_text(
            json.dumps(
                {
                    "inventory_id": "INV-FIXTURE-2",
                    "review_id": "REVIEW-FIXTURE-2",
                    "order_id": "ORDER-FIXTURE-1",
                    "review_text": "Related follow-up fixture review.",
                    "candidate_id": related_candidate,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        legacy_package = (
            self.output_root
            / "inbox_20291231"
            / "CAND-20300102-0001_primary_legacy"
        )
        legacy_package.mkdir(parents=True)
        (legacy_package / "planning_recipe.json").write_text(
            json.dumps(
                {
                    "review_source": {
                        "source_reference": (
                            "material-bank#CAND-20300102-0001; "
                            f"same-order follow-up #{related_candidate}"
                        )
                    }
                }
            ),
            encoding="utf-8",
        )

        inspection = inspect_material_bank_candidate(
            output_root=self.output_root,
            reviews_root=self.root / "reviews",
            material_bank_path=material_bank,
            candidate_id=related_candidate,
        )

        self.assertFalse(inspection["eligible_for_new_package"])
        self.assertEqual(inspection["status"], "legacy_package_present")
        self.assertEqual(
            inspection["legacy_package_relative_paths"],
            [f"inbox_20291231/{legacy_package.name}"],
        )

    def test_candidate_identity_requires_exact_shape_and_legacy_scan_uses_token_boundaries(self):
        material_bank = self.root / "candidate_top60_private.jsonl"
        candidate_id = "CAND-20300102-0001"
        material_bank.write_text(
            json.dumps(
                {
                    "inventory_id": "INV-FIXTURE-1",
                    "review_id": "REVIEW-FIXTURE-1",
                    "order_id": "ORDER-FIXTURE-1",
                    "review_text": "Boundary fixture review.",
                    "candidate_id": candidate_id,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        legacy_package = self.output_root / "inbox_20291231" / "999_other_legacy"
        legacy_package.mkdir(parents=True)
        evidence = legacy_package / "planning_recipe.json"
        evidence.write_text(
            json.dumps({"source_reference": f"{candidate_id}9"}),
            encoding="utf-8",
        )

        inspection = inspect_material_bank_candidate(
            output_root=self.output_root,
            reviews_root=self.root / "reviews",
            material_bank_path=material_bank,
            candidate_id=candidate_id,
        )
        self.assertTrue(inspection["eligible_for_new_package"])

        evidence.write_text(
            json.dumps({"source_reference": f"material-bank#{candidate_id}; follow-up"}),
            encoding="utf-8",
        )
        exact_inspection = inspect_material_bank_candidate(
            output_root=self.output_root,
            reviews_root=self.root / "reviews",
            material_bank_path=material_bank,
            candidate_id=candidate_id,
        )
        self.assertEqual(exact_inspection["status"], "legacy_package_present")

        malformed_bank = self.root / "malformed_candidate.jsonl"
        malformed_id = "CAND-20300102-001"
        malformed_bank.write_text(
            json.dumps(
                {
                    "inventory_id": "INV-BAD",
                    "review_id": "REVIEW-BAD",
                    "order_id": "ORDER-BAD",
                    "review_text": "Malformed candidate fixture.",
                    "candidate_id": malformed_id,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(IntakeViolation, "CANDIDATE_REFERENCE_INVALID"):
            inspect_material_bank_candidate(
                output_root=self.output_root,
                reviews_root=self.root / "reviews",
                material_bank_path=malformed_bank,
                candidate_id=malformed_id,
            )

    def test_exact_candidate_provenance_inside_pilot_package_blocks_reuse(self):
        material_bank = self.root / "candidate_top60_private.jsonl"
        candidate_id = "CAND-20300102-0009"
        material_bank.write_text(
            json.dumps(
                {
                    "inventory_id": "INV-PILOT-9",
                    "review_id": "REVIEW-PILOT-9",
                    "order_id": "ORDER-PILOT-9",
                    "product_name": "현관중문 시공설치",
                    "product_family": "중문",
                    "review_text": "Pilot provenance fixture.",
                    "candidate_id": candidate_id,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        pilot_package = self.output_root / "pilot" / "002_old_pilot"
        (pilot_package / "_work").mkdir(parents=True)
        (pilot_package / "_work" / "source.json").write_text(
            json.dumps({"candidate_reference": candidate_id}),
            encoding="utf-8",
        )

        inspection = inspect_material_bank_candidate(
            output_root=self.output_root,
            reviews_root=self.root / "reviews",
            material_bank_path=material_bank,
            candidate_id=candidate_id,
        )

        self.assertEqual(inspection["status"], "legacy_package_present")
        self.assertEqual(inspection["blocker_code"], "CANDIDATE_LEGACY_PACKAGE_PRESENT")
        self.assertEqual(inspection["legacy_package_relative_paths"], ["pilot/002_old_pilot"])

    def test_candidate_policy_blocks_abs_door_before_package_allocation(self):
        material_bank = self.root / "candidate_top60_private.jsonl"
        candidate_id = "CAND-20300102-0001"
        material_bank.write_text(
            json.dumps(
                {
                    "inventory_id": "INV-ABS-1",
                    "review_id": "REVIEW-ABS-1",
                    "order_id": "ORDER-ABS-1",
                    "product_name": "셀프실측 방문교체 ABS도어 배송상품",
                    "product_family": "ABS도어",
                    "review_text": "Excluded ABS door fixture.",
                    "candidate_id": candidate_id,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        inspection = inspect_material_bank_candidate(
            output_root=self.output_root,
            reviews_root=self.root / "reviews",
            material_bank_path=material_bank,
            candidate_id=candidate_id,
        )

        self.assertFalse(inspection["eligible_for_new_package"])
        self.assertEqual(inspection["status"], "policy_excluded")
        self.assertEqual(inspection["blocker_code"], "CANDIDATE_PRODUCT_EXCLUDED")
        self.assertEqual(
            inspection["exclusion_reason_codes"],
            ["ABS_DOOR", "SELF_MEASUREMENT", "DELIVERY_ONLY"],
        )
        self.assertTrue(explain_error("CANDIDATE_PRODUCT_EXCLUDED")["known"])
        with self.assertRaisesRegex(IntakeViolation, "CANDIDATE_PRODUCT_EXCLUDED"):
            create_canonical_package_from_material_bank(
                output_root=self.output_root,
                reviews_root=self.root / "reviews",
                material_bank_path=material_bank,
                candidate_id=candidate_id,
                content_slug="제외후보",
                now=self.now,
            )
        self.assertFalse((self.output_root / ".review_reel_production").exists())

    def test_candidate_with_same_review_identity_under_different_candidate_is_blocked(self):
        material_bank = self.root / "candidate_top60_private.jsonl"
        candidate_id = "CAND-20300102-0002"
        material_bank.write_text(
            json.dumps(
                {
                    "inventory_id": "INV-DUP-2",
                    "review_id": "4985538473",
                    "order_id": "2026052161335791",
                    "product_name": "현관중문 시공설치",
                    "product_family": "중문",
                    "review_text": "Exact duplicate fixture review.",
                    "candidate_id": candidate_id,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        legacy_package = self.output_root / "017_부모님반전"
        (legacy_package / "_work").mkdir(parents=True)
        (legacy_package / "_work" / "017_script.md").write_text(
            "---\nreview_id: 4985538473\nproduct_order_number: 2026052161335791\n---\n",
            encoding="utf-8",
        )

        inspection = inspect_material_bank_candidate(
            output_root=self.output_root,
            reviews_root=self.root / "reviews",
            material_bank_path=material_bank,
            candidate_id=candidate_id,
        )

        self.assertEqual(inspection["status"], "legacy_identity_present")
        self.assertEqual(inspection["blocker_code"], "REVIEW_ALREADY_USED")
        self.assertTrue(explain_error("REVIEW_ALREADY_USED")["known"])
        self.assertEqual(inspection["legacy_package_relative_paths"], [legacy_package.name])
        with self.assertRaisesRegex(IntakeViolation, "REVIEW_ALREADY_USED"):
            create_canonical_package_from_material_bank(
                output_root=self.output_root,
                reviews_root=self.root / "reviews",
                material_bank_path=material_bank,
                candidate_id=candidate_id,
                content_slug="중복후보",
                now=self.now,
            )

    def test_candidate_with_same_order_but_different_review_is_held_for_resolution(self):
        material_bank = self.root / "candidate_top60_private.jsonl"
        candidate_id = "CAND-20300102-0003"
        material_bank.write_text(
            json.dumps(
                {
                    "inventory_id": "INV-FOLLOWUP-3",
                    "review_id": "4985905386",
                    "order_id": "2026033070992071",
                    "product_name": "현관중문 시공설치",
                    "product_family": "중문",
                    "review_text": "One month follow-up fixture.",
                    "candidate_id": candidate_id,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        legacy_package = self.output_root / "077_반려동물에어컨효율_legacy"
        legacy_package.mkdir(parents=True)
        (legacy_package / "077_script.md").write_text(
            "---\nreview_id: 4948039850\nproduct_order_number: 2026033070992071\n---\n",
            encoding="utf-8",
        )

        inspection = inspect_material_bank_candidate(
            output_root=self.output_root,
            reviews_root=self.root / "reviews",
            material_bank_path=material_bank,
            candidate_id=candidate_id,
        )

        self.assertFalse(inspection["eligible_for_new_package"])
        self.assertEqual(inspection["status"], "related_review_hold")
        self.assertEqual(inspection["blocker_code"], "PRODUCT_ORDER_ALREADY_USED")
        self.assertTrue(explain_error("PRODUCT_ORDER_ALREADY_USED")["known"])
        self.assertEqual(inspection["legacy_package_relative_paths"], [legacy_package.name])

    def test_official_binding_does_not_hide_an_older_package_with_the_same_review(self):
        material_bank = self.root / "candidate_top60_private.jsonl"
        candidate_id = "CAND-20300102-0004"
        material_bank.write_text(
            json.dumps(
                {
                    "inventory_id": "INV-OFFICIAL-4",
                    "review_id": "4988296656",
                    "order_id": "2026051963784331",
                    "product_name": "현관중문 시공설치",
                    "product_family": "중문",
                    "review_text": "Official duplicate fixture.",
                    "candidate_id": candidate_id,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        created = create_canonical_package_from_material_bank(
            output_root=self.output_root,
            reviews_root=self.root / "reviews",
            material_bank_path=material_bank,
            candidate_id=candidate_id,
            content_slug="공식중복",
            now=self.now,
        )
        legacy_package = self.output_root / "010_구축소음_legacy"
        legacy_package.mkdir()
        (legacy_package / "010_script.md").write_text(
            "---\nreview_id: 4988296656\nproduct_order_number: 2026051963784331\n---\n",
            encoding="utf-8",
        )

        inspection = inspect_material_bank_candidate(
            output_root=self.output_root,
            reviews_root=self.root / "reviews",
            material_bank_path=material_bank,
            candidate_id=candidate_id,
        )

        self.assertEqual(inspection["status"], "legacy_identity_present")
        self.assertEqual(inspection["blocker_code"], "REVIEW_ALREADY_USED")
        self.assertIn(legacy_package.name, inspection["legacy_package_relative_paths"])
        self.assertNotIn(created.package_dir.name, inspection["legacy_package_relative_paths"])

    def test_candidate_shortlist_applies_policy_identity_and_order_holds_in_rank_order(self):
        material_bank = self.root / "candidate_top60_private.jsonl"
        rows = [
            {
                "inventory_id": "INV-1",
                "review_id": "REVIEW-1",
                "order_id": "ORDER-1",
                "product_name": "ABS도어 배송상품",
                "product_family": "ABS도어",
                "review_text": "Excluded.",
                "candidate_id": "CAND-20300102-0001",
                "canonical_top60_rank": 1,
                "tier": "A",
                "story_score_60": 60,
            },
            {
                "inventory_id": "INV-2",
                "review_id": "REVIEW-2",
                "order_id": "ORDER-2",
                "product_name": "현관중문 시공설치",
                "product_family": "중문",
                "review_text": "Eligible.",
                "candidate_id": "CAND-20300102-0002",
                "canonical_top60_rank": 2,
                "tier": "A",
                "story_score_60": 55,
            },
            {
                "inventory_id": "INV-3",
                "review_id": "REVIEW-3-NEW",
                "order_id": "ORDER-3",
                "product_name": "현관중문 시공설치",
                "product_family": "중문",
                "review_text": "Follow-up.",
                "candidate_id": "CAND-20300102-0003",
                "canonical_top60_rank": 3,
                "tier": "A",
                "story_score_60": 50,
            },
        ]
        material_bank.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )
        legacy_package = self.output_root / "003_existing"
        legacy_package.mkdir(parents=True)
        (legacy_package / "script.md").write_text(
            "review_id: REVIEW-3-OLD\nproduct_order_number: ORDER-3\n",
            encoding="utf-8",
        )

        shortlist = review_intake.shortlist_material_bank_candidates(
            output_root=self.output_root,
            reviews_root=self.root / "reviews",
            material_bank_path=material_bank,
            limit=10,
        )

        self.assertEqual(shortlist["summary"]["evaluated"], 3)
        self.assertEqual(shortlist["summary"]["eligible"], 1)
        self.assertEqual(shortlist["summary"]["policy_excluded"], 1)
        self.assertEqual(shortlist["summary"]["related_review_hold"], 1)
        self.assertEqual(
            [row["candidate_id"] for row in shortlist["eligible_candidates"]],
            ["CAND-20300102-0002"],
        )
        self.assertEqual(
            [row["candidate_id"] for row in shortlist["candidates"]],
            ["CAND-20300102-0001", "CAND-20300102-0002", "CAND-20300102-0003"],
        )

    def test_pre_photo_active_selection_can_be_quarantined_without_deleting_evidence(self):
        material_bank = self.root / "candidate_top60_private.jsonl"
        candidate_id = "CAND-20300102-0005"
        material_bank.write_text(
            json.dumps(
                {
                    "inventory_id": "INV-QUARANTINE-5",
                    "review_id": "REVIEW-QUARANTINE-5",
                    "order_id": "ORDER-QUARANTINE-5",
                    "product_name": "현관중문 시공설치",
                    "product_family": "중문",
                    "review_text": "Quarantine fixture.",
                    "candidate_id": candidate_id,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        created = create_canonical_package_from_material_bank(
            output_root=self.output_root,
            reviews_root=self.root / "reviews",
            material_bank_path=material_bank,
            candidate_id=candidate_id,
            content_slug="잘못선택",
            now=self.now,
        )
        source_path = Path(created.metadata["review_source"]["path"])

        result = review_intake.quarantine_active_selection(
            output_root=self.output_root,
            reviews_root=self.root / "reviews",
            expected_content_id=created.metadata["content_id"],
            reason_code="duplicate_existing_review",
            now=self.now,
        )

        quarantine_root = Path(result["quarantine_root"])
        moved_package = quarantine_root / "output" / created.package_dir.name
        moved_source = quarantine_root / "reviews" / "production_registry" / source_path.name
        self.assertEqual(result["status"], "quarantined")
        self.assertFalse(created.package_dir.exists())
        self.assertFalse(source_path.exists())
        self.assertTrue(moved_package.is_dir())
        self.assertTrue(moved_source.is_file())
        self.assertTrue((quarantine_root / "manifest.json").is_file())
        self.assertFalse(
            (self.output_root / ".review_reel_production" / "active_package.json").exists()
        )
        source_registry = json.loads(
            (
                self.output_root
                / ".review_reel_production"
                / "source_registry_private.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(source_registry["records"], [])
        with self.assertRaisesRegex(IntakeViolation, "ACTIVE_PACKAGE_POINTER_MISSING"):
            resolve_active_package(self.output_root)

    def test_active_selection_quarantine_refuses_any_customer_photo(self):
        created = self.create()
        (created.image_dir / "customer.jpg").write_bytes(b"customer-media-fixture")

        with self.assertRaisesRegex(IntakeViolation, "ACTIVE_SELECTION_QUARANTINE_PHOTOS_PRESENT"):
            review_intake.quarantine_active_selection(
                output_root=self.output_root,
                reviews_root=self.root / "reviews",
                expected_content_id=created.metadata["content_id"],
                reason_code="wrong_selection",
                now=self.now,
            )

        self.assertTrue(created.package_dir.is_dir())
        self.assertTrue(resolve_active_package(self.output_root).package_dir.is_dir())

    def test_candidate_shortlist_and_quarantine_commands_are_exposed_by_official_cli(self):
        material_bank = self.root / "candidate_top60_private.jsonl"
        candidate_id = "CAND-20300102-0006"
        material_bank.write_text(
            json.dumps(
                {
                    "inventory_id": "INV-CLI-6",
                    "review_id": "REVIEW-CLI-6",
                    "order_id": "ORDER-CLI-6",
                    "product_name": "현관중문 시공설치",
                    "product_family": "중문",
                    "review_text": "CLI fixture.",
                    "candidate_id": candidate_id,
                    "canonical_top60_rank": 1,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        script = Path(__file__).resolve().parents[1] / "scripts" / "review_reel_intake.py"
        shortlist_result = subprocess.run(
            [
                sys.executable,
                str(script),
                "candidate-shortlist",
                "--output-root",
                str(self.output_root),
                "--reviews-root",
                str(self.root / "reviews"),
                "--material-bank",
                str(material_bank),
                "--limit",
                "5",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(shortlist_result.returncode, 0, shortlist_result.stderr)
        self.assertEqual(
            json.loads(shortlist_result.stdout)["eligible_candidates"][0]["candidate_id"],
            candidate_id,
        )

        created = create_canonical_package_from_material_bank(
            output_root=self.output_root,
            reviews_root=self.root / "reviews",
            material_bank_path=material_bank,
            candidate_id=candidate_id,
            content_slug="CLI격리",
            now=self.now,
        )
        quarantine_result = subprocess.run(
            [
                sys.executable,
                str(script),
                "quarantine-active-selection",
                "--output-root",
                str(self.output_root),
                "--reviews-root",
                str(self.root / "reviews"),
                "--expected-content-id",
                created.metadata["content_id"],
                "--reason-code",
                "wrong_selection",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(quarantine_result.returncode, 0, quarantine_result.stderr)
        self.assertEqual(json.loads(quarantine_result.stdout)["status"], "quarantined")

    def test_candidate_check_cli_and_error_guidance_explain_legacy_blocker(self):
        material_bank = self.root / "candidate_top60_private.jsonl"
        candidate_id = "CAND-20300102-0001"
        material_bank.write_text(
            json.dumps(
                {
                    "inventory_id": "INV-FIXTURE-1",
                    "review_id": "REVIEW-FIXTURE-1",
                    "order_id": "ORDER-FIXTURE-1",
                    "review_text": "Legacy fixture review.",
                    "candidate_id": candidate_id,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (self.output_root / "inbox_20291231" / f"{candidate_id}_old").mkdir(parents=True)
        script = Path(__file__).resolve().parents[1] / "scripts" / "review_reel_intake.py"

        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "candidate-check",
                "--output-root",
                str(self.output_root),
                "--reviews-root",
                str(self.root / "reviews"),
                "--material-bank",
                str(material_bank),
                "--candidate-id",
                candidate_id,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["blocker_code"], "CANDIDATE_LEGACY_PACKAGE_PRESENT")
        guidance = explain_error("CANDIDATE_LEGACY_PACKAGE_PRESENT")
        self.assertTrue(guidance["known"])
        self.assertIn("legacy", guidance["how_to_fix"].lower())

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
        report_payload.setdefault("sanitized_assets", []).append(
            {
                "relative_path": evidence["relative_path"],
                "source_relative_path": source.relative_to(package.package_dir).as_posix(),
                "masked_regions": [
                    {"left_pct": 10, "top_pct": 10, "width_pct": 20, "height_pct": 10}
                ],
            }
        )
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
        hook_text = "중문 설치 한 달 뒤, 집 분위기가 달라졌습니다."
        planning["hooks"] = [{"text": hook_text}]
        planning["selected_hook"] = {"text": hook_text}
        planning["writer_brief"]["one_line_story"] = "현관 동선이 설치 후 편해진 리뷰 이야기"
        planning["writer_brief"]["hook_candidates"] = [{"text": hook_text}]
        planning["writer_brief"]["recommended_hook"] = hook_text
        planning["scenes"][0]["caption"] = {"text": hook_text}
        planning["scenes"][0]["narration"] = hook_text
        for scene in planning["scenes"]:
            scene["meaning_match_evidence"] = "review_source.text and selected photo evidence"
        first_beat = edit["beats"][0]
        first_beat["caption"] = hook_text
        first_beat["narration_ref"] = hook_text
        first_beat["caption_chunks"] = [{"text": hook_text, "start_sec": 0.0, "end_sec": 4.0}]
        first_beat["caption_focus_keywords"] = ["중문"]
        first_beat["caption_emphasis"] = ["중문"]
        first_beat["caption_accent"]["start_sec"] = 0.05
        for shot in first_beat["shots"]:
            shot["meaning_match_source"] = f"asset_evidence:{shot['asset_id']}; narration_fragment:{hook_text}"
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
        from video_engine_v2.current_artifacts import record_current_artifacts

        record_current_artifacts(
            package.package_dir,
            producer="tests.fixture_tts",
            artifacts={
                "script": script,
                "captions": package.package_dir / source["srt"],
                "voice": package.package_dir / source["voice"],
                "tts_report": package.package_dir / source["tts_generation_report"],
            },
        )
        guidance = workflow_next(self.output_root)
        self.assertEqual(guidance["next_action"], "listen_to_voice_then_record_review")
        self.assertIsNone(guidance["next_command"])

        record_voice_review(
            package_dir=package.package_dir,
            voice_path=package.package_dir / source["voice"],
            srt_path=package.package_dir / source["srt"],
            tts_report_path=package.package_dir / source["tts_generation_report"],
            reviewer="fixture-reviewer",
            evidence_reference="fixture-voice-review",
            checks=VOICE_REVIEW_CHECKS,
        )
        ledger_path = package.package_dir / "CURRENT_ARTIFACTS.json"
        ledger_payload = json.loads(ledger_path.read_text(encoding="utf-8"))
        del ledger_payload["pointers"]["voice_manual_review"]
        ledger_path.write_text(json.dumps(ledger_payload), encoding="utf-8")
        guidance = workflow_next(self.output_root)
        self.assertEqual(guidance["next_action"], "listen_to_voice_then_record_review")
        record_voice_review(
            package_dir=package.package_dir,
            voice_path=package.package_dir / source["voice"],
            srt_path=package.package_dir / source["srt"],
            tts_report_path=package.package_dir / source["tts_generation_report"],
            reviewer="fixture-reviewer",
            evidence_reference="fixture-voice-review-rebound",
            checks=VOICE_REVIEW_CHECKS,
        )
        guidance = workflow_next(self.output_root)
        self.assertEqual(guidance["next_action"], "run_one_shot_preflight")
        self.assertIn("--one-shot-html", guidance["next_command"])

        (package.package_dir / "sync_manifest.json").write_text("{}", encoding="utf-8")
        guidance = workflow_next(self.output_root)
        self.assertEqual(guidance["next_action"], "run_one_shot_preflight")
        record_current_artifacts(
            package.package_dir,
            producer="tests.fixture_preflight",
            artifacts={
                "sync_manifest": package.package_dir / "sync_manifest.json",
                "planning_recipe": planning_path,
                "edit_recipe": edit_path,
            },
        )
        ledger_payload = json.loads(ledger_path.read_text(encoding="utf-8"))
        del ledger_payload["pointers"]["planning_recipe"]
        ledger_path.write_text(json.dumps(ledger_payload), encoding="utf-8")
        guidance = workflow_next(self.output_root)
        self.assertEqual(guidance["next_action"], "stale_current_artifacts")
        self.assertEqual(guidance["stale_artifact_kind"], "planning_recipe")
        record_current_artifacts(
            package.package_dir,
            producer="tests.fixture_preflight_rebound",
            artifacts={"planning_recipe": planning_path},
        )
        guidance = workflow_next(self.output_root)
        self.assertEqual(guidance["next_action"], "build_one_shot_html")

        html = package.package_dir / "004_fixture_html_preview_v2" / "index.html"
        html.parent.mkdir()
        html.write_text("<!doctype html>", encoding="utf-8")
        guidance = workflow_next(self.output_root)
        self.assertEqual(guidance["next_action"], "build_one_shot_html")
        self.assertFalse(guidance["approval_required"])

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

    def test_photo_review_rejects_an_undeclared_sanitized_output_before_lifecycle_change(self):
        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)
        self._add_sanitized_review_capture(package, selection, privacy)
        manifest = json.loads(privacy.read_text(encoding="utf-8"))
        report_path = package.package_dir / manifest["sanitization_report"]
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report.pop("sanitized_assets")
        report_path.write_text(json.dumps(report), encoding="utf-8")

        with self.assertRaisesRegex(IntakeViolation, "SANITIZED_ASSET_NOT_DECLARED"):
            record_photo_review(
                output_root=self.output_root,
                selection_path=selection,
                privacy_manifest_path=privacy,
                now=self.now,
            )
        metadata = json.loads(
            (package.package_dir / "CANONICAL_PACKAGE_METADATA.json").read_text(encoding="utf-8")
        )
        self.assertEqual(metadata["lifecycle_state"], "photo_intake_pending")

    def test_photo_review_ledger_failure_does_not_advance_canonical_lifecycle(self):
        from video_engine_v2.current_artifacts import CurrentArtifactsViolation

        package = self.create()
        selection, privacy = self._write_photo_review_evidence(package)
        self._add_sanitized_review_capture(package, selection, privacy)

        with patch(
            "video_engine_v2.current_artifacts.record_current_artifacts",
            side_effect=CurrentArtifactsViolation("CURRENT_ARTIFACTS_LOCK_TIMEOUT"),
        ):
            with self.assertRaisesRegex(IntakeViolation, "CURRENT_ARTIFACTS_LOCK_TIMEOUT"):
                record_photo_review(
                    output_root=self.output_root,
                    selection_path=selection,
                    privacy_manifest_path=privacy,
                    now=self.now,
                )

        metadata = json.loads(
            (package.package_dir / "CANONICAL_PACKAGE_METADATA.json").read_text(encoding="utf-8")
        )
        self.assertEqual(metadata["lifecycle_state"], "photo_intake_pending")
        self.assertFalse(metadata["approvals"]["photo_checked"])

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

        with patch("video_engine_v2.package_state.map_package_state", return_value=completed_state):
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
        self.assertEqual(completed["new_production_action"], "select_then_check_material_bank_candidate")
        self.assertIn("candidate-check", completed["new_production_command_template"])
        self.assertNotIn("create-from-material-bank", completed["new_production_command_template"])

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

    def _photo_reviewed_status(self, package):
        return {
            "workflow": "review_reel_production",
            "content_id": "004",
            "lifecycle_state": "photo_reviewed",
            "package": str(package.package_dir),
            "next_action": "prepare_planning_script_tts",
        }

    def _write_incomplete_scaffold(self, package):
        root = package.package_dir / "_work" / "recipe_scaffolds" / "revision_001"
        root.mkdir(parents=True, exist_ok=True)
        planning = {"scaffold": {"status": "incomplete", "pending_fields": ["analysis"]}}
        edit = {"scaffold": {"status": "incomplete", "pending_fields": ["voice-bound timing and hashes"]}}
        (root / "004_planning_recipe_scaffold.json").write_text(json.dumps(planning), encoding="utf-8")
        (root / "004_edit_recipe_scaffold.json").write_text(json.dumps(edit), encoding="utf-8")

    def _file_evidence(self, package, path: Path):
        return {
            "relative_path": path.relative_to(package.package_dir).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def _write_valid_html_chain(self, package, *, folder="004_valid_html_preview_v2", record_ledger=True):
        preview = package.package_dir / folder
        preview.mkdir(parents=True, exist_ok=True)
        image = package.package_dir / "images" / "after.jpg"
        image.parent.mkdir(parents=True, exist_ok=True)
        if not image.is_file():
            image.write_bytes(b"dummy-image")
        voice = package.package_dir / "voice.mp3"
        if not voice.is_file():
            voice.write_bytes(b"dummy-voice")
        font = package.package_dir / "_work" / "dummy_font.ttf"
        font.parent.mkdir(parents=True, exist_ok=True)
        if not font.is_file():
            font.write_bytes(b"dummy-font")
        recipe = package.package_dir / f"{folder}_edit_recipe.json"
        if not recipe.is_file():
            recipe.write_text(json.dumps({"schema_version": "review-reel-edit-v2", "fixture": folder}), encoding="utf-8")
        sync = package.package_dir / "sync_manifest_v6.json"
        if not sync.is_file():
            sync.write_text(json.dumps({"ok": True, "fixture": "bound-sync"}), encoding="utf-8")
        html = preview / "index.html"
        html.write_text("<!doctype html><html></html>", encoding="utf-8")
        receipt = package.package_dir / "_work" / "production_gates" / f"{folder}_html_gate.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "action": "html",
                    "package_path": str(package.package_dir.resolve()),
                    "recipe_path": str(recipe.resolve()),
                    "recipe_sha256": hashlib.sha256(recipe.read_bytes()).hexdigest(),
                    "sync_manifest_path": str(sync.resolve()),
                    "sync_manifest_sha256": hashlib.sha256(sync.read_bytes()).hexdigest(),
                    "one_shot_html_contract": True,
                    "issued_at": "2030-01-02T03:04:05+00:00",
                }
            ),
            encoding="utf-8",
        )
        evidence = {
            "schema_version": "1.0",
            "package_identity": {
                "package_path": str(package.package_dir.resolve()),
                "package_name": package.package_dir.name,
            },
            "html_relative_path": html.relative_to(package.package_dir).as_posix(),
            "html_sha256": hashlib.sha256(html.read_bytes()).hexdigest(),
            "html_gate_receipt_path": receipt.relative_to(package.package_dir).as_posix(),
            "html_gate_receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
            "render_dependencies": [
                {"kind": "image", "scope": "package", **self._file_evidence(package, image)},
                {"kind": "voice", "scope": "package", **self._file_evidence(package, voice)},
                {"kind": "font", "scope": "package", **self._file_evidence(package, font)},
            ],
        }
        artifact_path = preview / "html_artifact_evidence.json"
        artifact_path.write_text(json.dumps(evidence), encoding="utf-8")
        frame = preview / "_qa_frames" / "hook.jpg"
        frame.parent.mkdir(parents=True, exist_ok=True)
        frame.write_bytes(b"dummy-frame")
        qa_report = preview / "html_internal_qa_report.json"
        qa_report.write_text(
            json.dumps(
                {
                    "automatic_status": "pass",
                    "checks": [{"frame_relative_path": "_qa_frames/hook.jpg"}],
                    "hook_sequence_checks": [],
                }
            ),
            encoding="utf-8",
        )
        if record_ledger:
            from video_engine_v2.current_artifacts import record_current_artifacts

            record_current_artifacts(
                package.package_dir,
                producer="tests.write_valid_html_chain",
                artifacts={
                    "html": html,
                    "html_artifact_evidence": artifact_path,
                    "html_qa_report": qa_report,
                },
            )
        return html

    def _write_bound_html_review(self, package, html: Path, *, name="html_review_20300102T030405000000Z.json"):
        del name
        preview = html.parent
        qa_report = preview / "html_internal_qa_report.json"
        frame = preview / "_qa_frames" / "hook.jpg"
        frame.parent.mkdir(parents=True, exist_ok=True)
        frame.write_bytes(b"dummy-frame")
        qa_report.write_text(
            json.dumps(
                {
                    "automatic_status": "pass",
                    "checks": [{"frame_relative_path": "_qa_frames/hook.jpg"}],
                    "hook_sequence_checks": [],
                }
            ),
            encoding="utf-8",
        )
        return record_html_review(
            package_dir=package.package_dir,
            html_path=html,
            reviewer="fixture-reviewer",
            evidence_reference="fixture-html-review",
            checks=HTML_REVIEW_CHECKS,
        )

    def _guidance_for_photo_reviewed(self, package):
        with patch(
            "video_engine_v2.review_reel_intake.active_package_status",
            return_value=self._photo_reviewed_status(package),
        ):
            return workflow_next(self.output_root)

    def test_workflow_next_prefers_valid_html_over_incomplete_scaffold(self):
        package = self.create()
        self._write_incomplete_scaffold(package)
        html = self._write_valid_html_chain(package)

        guidance = self._guidance_for_photo_reviewed(package)

        self.assertEqual(guidance["next_action"], "inspect_html_frames_then_record_review")
        self.assertEqual(guidance["html_status"], "valid")
        self.assertEqual(guidance["html"], str(html.resolve()))
        self.assertFalse(guidance["approval_required"])

    def test_workflow_next_marks_bare_html_stale_instead_of_approval_wait(self):
        package = self.create()
        self._write_incomplete_scaffold(package)
        html = package.package_dir / "004_bare_html_preview_v2" / "index.html"
        html.parent.mkdir(parents=True)
        html.write_text("<!doctype html>", encoding="utf-8")
        from video_engine_v2.current_artifacts import record_current_artifacts

        record_current_artifacts(
            package.package_dir,
            producer="tests.bare_html",
            artifacts={"html": html},
        )

        guidance = self._guidance_for_photo_reviewed(package)

        self.assertEqual(guidance["next_action"], "stale_html")
        self.assertEqual(guidance["html_status"], "stale_html")
        self.assertEqual(guidance["stale_html_reason"], "html_ledger_chain_incomplete")
        self.assertFalse(guidance["approval_required"])

    def test_workflow_next_marks_html_sha_mismatch_stale(self):
        package = self.create()
        self._write_incomplete_scaffold(package)
        html = self._write_valid_html_chain(package)
        html.write_text("<!doctype html><html>changed</html>", encoding="utf-8")

        guidance = self._guidance_for_photo_reviewed(package)

        self.assertEqual(guidance["next_action"], "stale_html")
        self.assertIn(
            guidance["stale_html_reason"],
            {
                "html_sha256_mismatch",
                "current_artifacts_hash_mismatch",
                "current_artifacts_bytes_mismatch",
            },
        )
        self.assertFalse(guidance["approval_required"])

    def test_workflow_next_ignores_html_review_bound_to_a_different_html(self):
        package = self.create()
        self._write_incomplete_scaffold(package)
        current = self._write_valid_html_chain(package, folder="004_current_html_preview_v2")
        previous = self._write_valid_html_chain(
            package, folder="004_previous_html_preview_v2", record_ledger=False
        )
        previous.write_text("<!doctype html><html>old</html>", encoding="utf-8")
        self._write_bound_html_review(package, previous, name="html_review_old.json")

        guidance = self._guidance_for_photo_reviewed(package)

        self.assertEqual(guidance["next_action"], "inspect_html_frames_then_record_review")
        self.assertEqual(guidance["html"], str(current.resolve()))
        self.assertFalse(guidance["approval_required"])

    def test_workflow_next_waits_for_html_approval_after_bound_manual_review(self):
        package = self.create()
        self._write_incomplete_scaffold(package)
        html = self._write_valid_html_chain(package)
        self._write_bound_html_review(package, html)

        guidance = self._guidance_for_photo_reviewed(package)

        self.assertEqual(guidance["next_action"], "wait_for_explicit_html_approval_then_record_it")
        self.assertTrue(guidance["approval_required"])
        self.assertIsNone(guidance["next_command"])

    def test_workflow_next_does_not_use_unpointed_valid_html_review_or_approval(self):
        from video_engine_v2.approval_evidence import record_html_approval

        package = self.create()
        self._write_incomplete_scaffold(package)
        html = self._write_valid_html_chain(package)
        self._write_bound_html_review(package, html)
        ledger_path = package.package_dir / "CURRENT_ARTIFACTS.json"
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        del ledger["pointers"]["html_manual_review"]
        ledger_path.write_text(json.dumps(ledger), encoding="utf-8")

        guidance = self._guidance_for_photo_reviewed(package)
        self.assertEqual(guidance["next_action"], "inspect_html_frames_then_record_review")

        self._write_bound_html_review(package, html)
        record_html_approval(
            package_dir=package.package_dir,
            html_path=html,
            approved_by="fixture-user",
            evidence_reference="fixture-html-approval",
        )
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        del ledger["pointers"]["html_approval"]
        ledger_path.write_text(json.dumps(ledger), encoding="utf-8")

        guidance = self._guidance_for_photo_reviewed(package)
        self.assertEqual(guidance["next_action"], "wait_for_explicit_html_approval_then_record_it")

    def test_workflow_next_uses_scaffold_flow_when_html_is_absent(self):
        package = self.create()
        self._write_incomplete_scaffold(package)

        guidance = self._guidance_for_photo_reviewed(package)

        self.assertEqual(guidance["next_action"], "complete_scaffold_content_then_write_standard_script")
        self.assertNotIn("html_status", guidance)

    def test_workflow_next_marks_html_stale_when_bound_sync_changes(self):
        package = self.create()
        self._write_incomplete_scaffold(package)
        self._write_valid_html_chain(package)
        (package.package_dir / "sync_manifest_v6.json").write_text(
            json.dumps({"ok": True, "fixture": "changed"}),
            encoding="utf-8",
        )

        guidance = self._guidance_for_photo_reviewed(package)

        self.assertEqual(guidance["next_action"], "stale_html")
        self.assertEqual(guidance["stale_html_reason"], "html_gate_sync_mismatch")

    def test_workflow_next_marks_html_stale_when_bound_recipe_changes(self):
        package = self.create()
        self._write_incomplete_scaffold(package)
        html = self._write_valid_html_chain(package)
        recipe = package.package_dir / f"{html.parent.name}_edit_recipe.json"
        recipe.write_text(json.dumps({"schema_version": "review-reel-edit-v2", "fixture": "changed"}), encoding="utf-8")

        guidance = self._guidance_for_photo_reviewed(package)

        self.assertEqual(guidance["next_action"], "stale_html")
        self.assertEqual(guidance["stale_html_reason"], "html_gate_recipe_mismatch")

    def test_workflow_next_marks_html_stale_when_gate_package_path_is_wrong(self):
        package = self.create()
        self._write_incomplete_scaffold(package)
        html = self._write_valid_html_chain(package)
        receipt = package.package_dir / "_work" / "production_gates" / f"{html.parent.name}_html_gate.json"
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload["package_path"] = str(self.root / "other-package")
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        evidence_path = html.parent / "html_artifact_evidence.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence["html_gate_receipt_sha256"] = hashlib.sha256(receipt.read_bytes()).hexdigest()
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        from video_engine_v2.current_artifacts import record_current_artifacts

        record_current_artifacts(
            package.package_dir,
            producer="tests.refresh_invalid_artifact",
            artifacts={"html_artifact_evidence": evidence_path},
        )

        guidance = self._guidance_for_photo_reviewed(package)

        self.assertEqual(guidance["next_action"], "stale_html")
        self.assertEqual(guidance["stale_html_reason"], "html_gate_package_mismatch")

    def test_workflow_next_ignores_html_review_from_another_package_identity(self):
        package = self.create()
        self._write_incomplete_scaffold(package)
        html = self._write_valid_html_chain(package)
        preview = html.parent
        qa_report = preview / "html_internal_qa_report.json"
        frame = preview / "_qa_frames" / "hook.jpg"
        frame.parent.mkdir(parents=True, exist_ok=True)
        frame.write_bytes(b"dummy-frame")
        qa_report.write_text(
            json.dumps(
                {
                    "automatic_status": "pass",
                    "checks": [{"frame_relative_path": "_qa_frames/hook.jpg"}],
                    "hook_sequence_checks": [],
                }
            ),
            encoding="utf-8",
        )
        receipt_dir = package.package_dir / "_work" / "manual_reviews"
        receipt_dir.mkdir(parents=True, exist_ok=True)
        (receipt_dir / "html_review_foreign.json").write_text(
            json.dumps(
                {
                    "schema_version": "review-reel-manual-review-v1",
                    "review_kind": "html",
                    "status": "passed",
                    "package_identity": {
                        "package_path": str(self.root / "other-package"),
                        "package_name": "other-package",
                    },
                    "reviewed_by": "fixture-reviewer",
                    "evidence_reference": "foreign",
                    "checks": sorted(HTML_REVIEW_CHECKS),
                    "target": self._file_evidence(package, html),
                    "artifact_evidence": self._file_evidence(package, preview / "html_artifact_evidence.json"),
                    "qa_report": self._file_evidence(package, qa_report),
                    "qa_frames": [self._file_evidence(package, frame)],
                }
            ),
            encoding="utf-8",
        )

        guidance = self._guidance_for_photo_reviewed(package)

        self.assertEqual(guidance["next_action"], "inspect_html_frames_then_record_review")
        self.assertFalse(guidance["approval_required"])

    def test_workflow_next_ignores_html_review_missing_required_checks(self):
        package = self.create()
        self._write_incomplete_scaffold(package)
        html = self._write_valid_html_chain(package)
        preview = html.parent
        qa_report = preview / "html_internal_qa_report.json"
        frame = preview / "_qa_frames" / "hook.jpg"
        frame.parent.mkdir(parents=True, exist_ok=True)
        frame.write_bytes(b"dummy-frame")
        qa_report.write_text(
            json.dumps(
                {
                    "automatic_status": "pass",
                    "checks": [{"frame_relative_path": "_qa_frames/hook.jpg"}],
                    "hook_sequence_checks": [],
                }
            ),
            encoding="utf-8",
        )
        receipt_dir = package.package_dir / "_work" / "manual_reviews"
        receipt_dir.mkdir(parents=True, exist_ok=True)
        (receipt_dir / "html_review_incomplete.json").write_text(
            json.dumps(
                {
                    "schema_version": "review-reel-manual-review-v1",
                    "review_kind": "html",
                    "status": "passed",
                    "package_identity": {
                        "package_path": str(package.package_dir.resolve()),
                        "package_name": package.package_dir.name,
                    },
                    "reviewed_by": "fixture-reviewer",
                    "evidence_reference": "incomplete",
                    "checks": ["hook_sequence_reviewed"],
                    "target": self._file_evidence(package, html),
                    "artifact_evidence": self._file_evidence(package, preview / "html_artifact_evidence.json"),
                    "qa_report": self._file_evidence(package, qa_report),
                    "qa_frames": [self._file_evidence(package, frame)],
                }
            ),
            encoding="utf-8",
        )

        guidance = self._guidance_for_photo_reviewed(package)

        self.assertEqual(guidance["next_action"], "inspect_html_frames_then_record_review")
        self.assertFalse(guidance["approval_required"])

    def test_workflow_next_ignores_html_review_when_qa_frame_changes(self):
        package = self.create()
        self._write_incomplete_scaffold(package)
        html = self._write_valid_html_chain(package)
        self._write_bound_html_review(package, html)
        (html.parent / "_qa_frames" / "hook.jpg").write_bytes(b"changed-frame")

        guidance = self._guidance_for_photo_reviewed(package)

        self.assertEqual(guidance["next_action"], "inspect_html_frames_then_record_review")
        self.assertFalse(guidance["approval_required"])

    def test_invalid_html_approval_does_not_unlock_render_via_mp4_approval_hash(self):
        package = self.create()
        self._write_incomplete_scaffold(package)
        html = self._write_valid_html_chain(package)
        self._write_bound_html_review(package, html)
        approval = {
            "schema_version": "1.0",
            "package_identity": {
                "package_path": str(package.package_dir.resolve()),
                "package_name": package.package_dir.name,
            },
            "html_relative_path": html.relative_to(package.package_dir).as_posix(),
            "html_sha256": "0" * 64,
            "html_artifact_evidence_sha256": hashlib.sha256(
                (html.parent / "html_artifact_evidence.json").read_bytes()
            ).hexdigest(),
            "approved_by_user": True,
            "approved_at": "2030-01-02T03:06:05+00:00",
            "approved_by": "fixture-user",
            "approval_evidence_reference": "invalid-html-approval",
        }
        approval_path = package.package_dir / "HTML_APPROVAL.json"
        approval_path.write_text(json.dumps(approval), encoding="utf-8")
        (package.package_dir / "MP4_RENDER_APPROVAL.json").write_text(
            json.dumps(
                {
                    "schema_version": "review-reel-mp4-render-approval-v1",
                    "package_identity": {
                        "package_path": str(package.package_dir.resolve()),
                        "package_name": package.package_dir.name,
                    },
                    "html_relative_path": html.relative_to(package.package_dir).as_posix(),
                    "html_sha256": hashlib.sha256(html.read_bytes()).hexdigest(),
                    "html_approval_relative_path": "HTML_APPROVAL.json",
                    "html_approval_sha256": hashlib.sha256(approval_path.read_bytes()).hexdigest(),
                    "approved_by_user": True,
                    "approved_at": "2030-01-02T03:07:05+00:00",
                    "approved_by": "fixture-user",
                    "approval_evidence_reference": "hash-bound-to-invalid-html",
                }
            ),
            encoding="utf-8",
        )

        guidance = self._guidance_for_photo_reviewed(package)

        self.assertEqual(guidance["next_action"], "wait_for_explicit_html_approval_then_record_it")
        self.assertNotEqual(guidance["next_action"], "start_or_check_durable_render_job")

    def test_valid_html_review_and_approvals_follow_required_order(self):
        from video_engine_v2.approval_evidence import record_html_approval, record_render_approval

        package = self.create()
        self._write_incomplete_scaffold(package)
        html = self._write_valid_html_chain(package)
        self.assertEqual(
            self._guidance_for_photo_reviewed(package)["next_action"],
            "inspect_html_frames_then_record_review",
        )
        self._write_bound_html_review(package, html)
        self.assertEqual(
            self._guidance_for_photo_reviewed(package)["next_action"],
            "wait_for_explicit_html_approval_then_record_it",
        )
        record_html_approval(
            package_dir=package.package_dir,
            html_path=html,
            approved_by="fixture-user",
            evidence_reference="explicit-html-approval",
        )
        self.assertEqual(
            self._guidance_for_photo_reviewed(package)["next_action"],
            "wait_for_explicit_mp4_approval_then_record_it",
        )
        record_render_approval(
            package_dir=package.package_dir,
            html_path=html,
            approved_by="fixture-user",
            evidence_reference="explicit-mp4-approval",
        )
        self.assertEqual(
            self._guidance_for_photo_reviewed(package)["next_action"],
            "start_or_check_durable_render_job",
        )

    def test_route_cli_uses_output_root_to_detect_active_review_reel_package(self):
        self.create()
        script = Path(__file__).resolve().parents[1] / "scripts" / "review_reel_intake.py"
        with_package = subprocess.run(
            [
                sys.executable,
                str(script),
                "route",
                "--user-command",
                "진행해 그리고 렌더까지 해",
                "--output-root",
                str(self.output_root),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        without_root = subprocess.run(
            [
                sys.executable,
                str(script),
                "route",
                "--user-command",
                "하이퍼프레임 렌더까지 해",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(with_package.returncode, 0)
        self.assertEqual(json.loads(with_package.stdout)["state"], "mp4_render_intent_requested")
        self.assertNotIn("approved", json.loads(with_package.stdout))
        self.assertEqual(without_root.returncode, 0)
        self.assertEqual(json.loads(without_root.stdout)["workflow"], "generic_review_content")


if __name__ == "__main__":
    unittest.main()
