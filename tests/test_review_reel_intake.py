import json
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
        self.assertEqual(
            route_user_command("리뷰 릴스 만들자 리뷰 콘텐츠 신규 만들어줘"),
            {
                "workflow": "review_reel_production",
                "state": "selection_required",
                "next_action": "select_inventory_record",
            },
        )
        self.assertEqual(
            route_user_command("리뷰 하나 골라 폴더 만들어줘")["state"],
            "canonical_package_create_requested",
        )
        self.assertEqual(
            route_user_command("사진 다 넣었어. HTML까지 가자")["state"],
            "one_shot_html_requested",
        )

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
