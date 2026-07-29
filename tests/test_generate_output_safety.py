import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import generate
from video_engine_v2.production_gate import GateViolation


class FixedDateTime:
    @classmethod
    def now(cls):
        return datetime(2030, 1, 2, 3, 4, 5)


class GenerateOutputSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.base_dir = Path(self.tempdir.name)
        self.output_dir = self.base_dir / "output"
        self.reviews_dir = self.base_dir / "reviews" / "pilot"
        self.reviews_dir.mkdir(parents=True)
        self.base_patch = patch.object(generate, "BASE_DIR", self.base_dir)
        self.output_patch = patch.object(generate, "OUTPUT_DIR", self.output_dir)
        self.datetime_patch = patch.object(generate, "datetime", FixedDateTime)
        self.base_patch.start()
        self.output_patch.start()
        self.datetime_patch.start()
        self.addCleanup(self.datetime_patch.stop)
        self.addCleanup(self.output_patch.stop)
        self.addCleanup(self.base_patch.stop)

    def write_review(self, name: str) -> generate.ReviewRecord:
        path = self.reviews_dir / name
        path.write_text("리뷰 원문", encoding="utf-8")
        return generate.load_review_record(str(path))

    def save(self, review_record: generate.ReviewRecord, body: str = "first") -> Path:
        return generate.save_script(f"# 같은 제목\n{body}\n", str(review_record.source_path), review_record)

    def write_generation_approval(
        self,
        review_record: generate.ReviewRecord,
        *,
        photo_checked: bool = True,
        pd_approved: bool = True,
        source_key: str | None = None,
        package_suffix: str = "",
    ) -> Path:
        approval_package = self.base_dir / "approval" / f"{review_record.source_stem}{package_suffix}"
        approval_package.mkdir(parents=True)
        (approval_package / ".source").write_text(
            source_key or generate.get_source_key(review_record),
            encoding="utf-8",
        )
        (approval_package / "STATUS.md").write_text(
            f"- photo_checked: {str(photo_checked).lower()}\n"
            f"- pd_plan_approved: {str(pd_approved).lower()}\n",
            encoding="utf-8",
        )
        (approval_package / "APPROVAL_LOG.md").write_text(
            "- approved_scope: PD planning approved\n" if pd_approved else "- not_approved: PD planning pending\n",
            encoding="utf-8",
        )
        return approval_package

    def test_regeneration_preserves_first_run_and_protected_artifact(self):
        review_record = self.write_review("review_001.txt")
        first_script = self.save(review_record)
        protected_file = first_script.parent / "protected_final_upload.mp4"
        protected_file.write_bytes(b"must remain")

        second_script = self.save(review_record, body="second")

        self.assertNotEqual(first_script.parent, second_script.parent)
        self.assertEqual(first_script.read_text(encoding="utf-8"), "# 같은 제목\nfirst\n")
        self.assertEqual(protected_file.read_bytes(), b"must remain")
        self.assertEqual(second_script.read_text(encoding="utf-8"), "# 같은 제목\nsecond\n")

    def test_regeneration_uses_a_versioned_run_when_the_timestamp_matches(self):
        review_record = self.write_review("review_001.txt")
        first_script = self.save(review_record)
        second_script = self.save(review_record, body="second")

        self.assertTrue(first_script.parent.name.endswith("_20300102_030405"))
        self.assertTrue(second_script.parent.name.endswith("_20300102_030405_001"))

    def test_regeneration_does_not_touch_a_package_for_a_different_source(self):
        first_review = self.write_review("review_001.txt")
        other_review = self.write_review("review_002.txt")
        first_script = self.save(first_review)
        protected_file = first_script.parent / "protected.txt"
        protected_file.write_text("other source must stay", encoding="utf-8")

        self.save(other_review, body="other source")

        self.assertEqual(first_script.read_text(encoding="utf-8"), "# 같은 제목\nfirst\n")
        self.assertEqual(protected_file.read_text(encoding="utf-8"), "other source must stay")

    def test_existing_path_collision_never_overwrites_existing_package(self):
        review_record = self.write_review("review_001.txt")
        collection = self.output_dir / "pilot"
        collision = collection / "001_같제목_20300102_030405"
        collision.mkdir(parents=True)
        existing_script = collision / "001_같제목_script.md"
        existing_script.write_text("existing package", encoding="utf-8")

        saved_script = self.save(review_record)

        self.assertNotEqual(saved_script.parent, collision)
        self.assertEqual(existing_script.read_text(encoding="utf-8"), "existing package")
        self.assertEqual(saved_script.parent.name, "001_같제목_20300102_030405_001")

    def test_generation_gate_accepts_only_matching_source_with_photo_and_pd_approval(self):
        from video_engine_v2 import production_gate

        validator = getattr(production_gate, "validate_generation_gate", None)
        self.assertIsNotNone(validator, "generate.py needs a pre-API approval gate")
        review_record = self.write_review("review_001.txt")
        approval_package = self.write_generation_approval(review_record)

        validator(approval_package, generate.get_source_key(review_record))

        with self.assertRaises(GateViolation) as raised:
            validator(approval_package, "reviews/pilot/review_999.txt")
        self.assertIn("GENERATION_SOURCE_MISMATCH", str(raised.exception))

    def test_generation_gate_rejects_missing_photo_or_pd_approval(self):
        from video_engine_v2 import production_gate

        validator = getattr(production_gate, "validate_generation_gate", None)
        self.assertIsNotNone(validator, "generate.py needs a pre-API approval gate")
        review_record = self.write_review("review_001.txt")
        cases = [
            (False, True, "PHOTO_REVIEW_MISSING"),
            (True, False, "PD_APPROVAL_MISSING"),
        ]

        for index, (photo_checked, pd_approved, expected_code) in enumerate(cases):
            with self.subTest(expected_code=expected_code):
                approval_package = self.write_generation_approval(
                    review_record,
                    photo_checked=photo_checked,
                    pd_approved=pd_approved,
                    package_suffix=f"_{index}",
                )
                with self.assertRaises(GateViolation) as raised:
                    validator(approval_package, generate.get_source_key(review_record))
                self.assertIn(expected_code, str(raised.exception))

    def test_generate_cli_blocks_before_model_or_output_without_photo_approval(self):
        review_record = self.write_review("review_001.txt")
        approval_package = self.write_generation_approval(
            review_record,
            photo_checked=False,
            source_key=str(review_record.source_path),
        )
        before = list(self.output_dir.rglob("*")) if self.output_dir.exists() else []

        result = subprocess.run(
            [
                sys.executable,
                str(Path(generate.__file__).resolve()),
                "--input",
                str(review_record.source_path),
                "--approval-package",
                str(approval_package),
            ],
            cwd=Path(generate.__file__).resolve().parent,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("GATE_BLOCKED: PHOTO_REVIEW_MISSING", result.stderr)
        self.assertEqual(list(self.output_dir.rglob("*")) if self.output_dir.exists() else [], before)


if __name__ == "__main__":
    unittest.main()
