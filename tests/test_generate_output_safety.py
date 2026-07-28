import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import generate


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


if __name__ == "__main__":
    unittest.main()
