import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_engine_v2.output_layout import (
    OutputLayoutViolation,
    apply_flatten_plan,
    create_flatten_plan,
)


class OutputLayoutTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.base = Path(self.tempdir.name)
        self.output = self.base / "output"
        self.report = self.base / "flatten-plan.json"
        self.state = self.output / ".review_reel_production"
        self.state.mkdir(parents=True)

    def _package(self, relative: str, *, content_id: str = "119") -> Path:
        package = self.output / relative
        image_dir = package / f"{content_id}_fixture_이미지"
        image_dir.mkdir(parents=True)
        (image_dir / "after.jpg").write_bytes(b"fixture-image")
        metadata = {
            "schema_version": "review-reel-canonical-package-v1",
            "content_id": content_id,
            "package_name": package.name,
            "package_relative_path": relative.replace("\\", "/"),
            "image_directory_name": image_dir.name,
        }
        (package / "CANONICAL_PACKAGE_METADATA.json").write_text(
            json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
        )
        return package

    def _state_files(self, package: Path) -> None:
        relative = package.relative_to(self.output).as_posix()
        metadata_hash = hashlib.sha256(
            (package / "CANONICAL_PACKAGE_METADATA.json").read_bytes()
        ).hexdigest()
        (self.state / "active_package.json").write_text(
            json.dumps(
                {
                    "schema_version": "review-reel-active-pointer-v1",
                    "package_relative_path": relative,
                    "package_name": package.name,
                    "content_id": "119",
                    "image_directory_name": "119_fixture_이미지",
                    "metadata_sha256": metadata_hash,
                }
            ),
            encoding="utf-8",
        )
        (self.state / "registry.json").write_text(
            json.dumps(
                {
                    "schema_version": "review-reel-production-registry-v1",
                    "active_package_relative_path": relative,
                    "packages": [
                        {
                            "package_relative_path": relative,
                            "package_name": package.name,
                            "content_id": "119",
                            "updated_at": "2030-01-01T00:00:00Z",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_dry_run_selects_only_numeric_packages_under_inbox_directories(self):
        package = self._package("inbox_20300101/119_fixture_20300101_010203")
        (self.output / "inbox_20300101" / "CAND-legacy").mkdir()
        (self.output / "pilot" / "120_not-production").mkdir(parents=True)
        self._package("121_already-flat_20300101_010204", content_id="121")

        plan = create_flatten_plan(output_root=self.output, report_path=self.report)

        self.assertEqual(plan["move_count"], 1)
        self.assertEqual(plan["moves"][0]["source_relative_path"], package.relative_to(self.output).as_posix())
        self.assertEqual(plan["moves"][0]["destination_relative_path"], package.name)
        self.assertGreater(plan["moves"][0]["file_count"], 0)
        self.assertRegex(plan["moves"][0]["tree_sha256"], r"^[0-9a-f]{64}$")

    def test_dry_run_rejects_a_flat_name_collision(self):
        package = self._package("inbox_20300101/119_fixture_20300101_010203")
        (self.output / package.name).mkdir()

        with self.assertRaisesRegex(OutputLayoutViolation, "OUTPUT_FLAT_DESTINATION_COLLISION"):
            create_flatten_plan(output_root=self.output, report_path=self.report)

    def test_dry_run_rejects_two_inboxes_planning_the_same_flat_destination(self):
        self._package("inbox_20300101/119_fixture_20300101_010203")
        self._package("inbox_20300102/119_fixture_20300101_010203")

        with self.assertRaisesRegex(OutputLayoutViolation, "OUTPUT_FLAT_DESTINATION_COLLISION"):
            create_flatten_plan(output_root=self.output, report_path=self.report)

    def test_dry_run_protects_a_hash_verified_render_package_from_relocation(self):
        package = self._package("inbox_20300101/119_fixture_20300101_010203")

        with patch("video_engine_v2.output_layout.map_legacy_package", return_value={"render_complete": True}):
            plan = create_flatten_plan(output_root=self.output, report_path=self.report)

        self.assertEqual(plan["move_count"], 0)
        self.assertEqual(
            plan["protected_packages"],
            [
                {
                    "source_relative_path": package.relative_to(self.output).as_posix(),
                    "reason": "verified_render_evidence_path_bound",
                }
            ],
        )

    def test_apply_requires_the_exact_report_hash_and_confirmation(self):
        self._package("inbox_20300101/119_fixture_20300101_010203")
        create_flatten_plan(output_root=self.output, report_path=self.report)
        report_hash = hashlib.sha256(self.report.read_bytes()).hexdigest()

        with self.assertRaisesRegex(OutputLayoutViolation, "OUTPUT_FLATTEN_CONFIRMATION_REQUIRED"):
            apply_flatten_plan(
                output_root=self.output,
                report_path=self.report,
                report_sha256=report_hash,
                confirm="wrong",
            )
        with self.assertRaisesRegex(OutputLayoutViolation, "OUTPUT_FLATTEN_REPORT_HASH_MISMATCH"):
            apply_flatten_plan(
                output_root=self.output,
                report_path=self.report,
                report_sha256="0" * 64,
                confirm="FLATTEN_REVIEW_PACKAGES",
            )

    def test_apply_rechecks_verified_render_protection_after_the_plan_was_created(self):
        source = self._package("inbox_20300101/119_fixture_20300101_010203")
        create_flatten_plan(output_root=self.output, report_path=self.report)
        report_hash = hashlib.sha256(self.report.read_bytes()).hexdigest()

        with patch("video_engine_v2.output_layout.map_legacy_package", return_value={"render_complete": True}):
            with self.assertRaisesRegex(OutputLayoutViolation, "OUTPUT_FLATTEN_VERIFIED_RENDER_PROTECTED"):
                apply_flatten_plan(
                    output_root=self.output,
                    report_path=self.report,
                    report_sha256=report_hash,
                    confirm="FLATTEN_REVIEW_PACKAGES",
                )

        self.assertTrue(source.is_dir())
        self.assertFalse((self.output / source.name).exists())

    def test_apply_moves_package_and_rebinds_metadata_registry_and_active_pointer(self):
        source = self._package("inbox_20300101/119_fixture_20300101_010203")
        self._state_files(source)
        plan = create_flatten_plan(output_root=self.output, report_path=self.report)
        report_hash = hashlib.sha256(self.report.read_bytes()).hexdigest()

        receipt = apply_flatten_plan(
            output_root=self.output,
            report_path=self.report,
            report_sha256=report_hash,
            confirm="FLATTEN_REVIEW_PACKAGES",
        )

        destination = self.output / source.name
        self.assertFalse(source.exists())
        self.assertTrue(destination.is_dir())
        metadata_path = destination / "CANONICAL_PACKAGE_METADATA.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["package_relative_path"], destination.name)
        pointer = json.loads((self.state / "active_package.json").read_text(encoding="utf-8"))
        registry = json.loads((self.state / "registry.json").read_text(encoding="utf-8"))
        self.assertEqual(pointer["package_relative_path"], destination.name)
        self.assertEqual(pointer["metadata_sha256"], hashlib.sha256(metadata_path.read_bytes()).hexdigest())
        self.assertEqual(registry["active_package_relative_path"], destination.name)
        self.assertEqual(registry["packages"][0]["package_relative_path"], destination.name)
        self.assertEqual(receipt["status"], "applied")
        self.assertTrue((self.output / "inbox_20300101").is_dir())

    def test_apply_stops_if_a_package_changed_after_dry_run(self):
        source = self._package("inbox_20300101/119_fixture_20300101_010203")
        create_flatten_plan(output_root=self.output, report_path=self.report)
        report_hash = hashlib.sha256(self.report.read_bytes()).hexdigest()
        (source / "late.txt").write_text("changed", encoding="utf-8")

        with self.assertRaisesRegex(OutputLayoutViolation, "OUTPUT_FLATTEN_SOURCE_CHANGED"):
            apply_flatten_plan(
                output_root=self.output,
                report_path=self.report,
                report_sha256=report_hash,
                confirm="FLATTEN_REVIEW_PACKAGES",
            )

        self.assertTrue(source.is_dir())
        self.assertFalse((self.output / source.name).exists())

    def test_apply_rolls_completed_moves_back_if_state_rebinding_fails(self):
        source = self._package("inbox_20300101/119_fixture_20300101_010203")
        self._state_files(source)
        metadata_before = (source / "CANONICAL_PACKAGE_METADATA.json").read_bytes()
        pointer_before = (self.state / "active_package.json").read_bytes()
        create_flatten_plan(output_root=self.output, report_path=self.report)
        report_hash = hashlib.sha256(self.report.read_bytes()).hexdigest()

        with patch("video_engine_v2.output_layout._atomic_write_json", side_effect=OSError("fixture")):
            with self.assertRaisesRegex(OSError, "fixture"):
                apply_flatten_plan(
                    output_root=self.output,
                    report_path=self.report,
                    report_sha256=report_hash,
                    confirm="FLATTEN_REVIEW_PACKAGES",
                )

        self.assertTrue(source.is_dir())
        self.assertFalse((self.output / source.name).exists())
        self.assertEqual((source / "CANONICAL_PACKAGE_METADATA.json").read_bytes(), metadata_before)
        self.assertEqual((self.state / "active_package.json").read_bytes(), pointer_before)

    def test_apply_rolls_completed_moves_back_if_the_receipt_cannot_be_written(self):
        source = self._package("inbox_20300101/119_fixture_20300101_010203")
        self._state_files(source)
        metadata_before = (source / "CANONICAL_PACKAGE_METADATA.json").read_bytes()
        pointer_before = (self.state / "active_package.json").read_bytes()
        create_flatten_plan(output_root=self.output, report_path=self.report)
        report_hash = hashlib.sha256(self.report.read_bytes()).hexdigest()

        from video_engine_v2 import output_layout

        original_write = output_layout._atomic_write_json

        def fail_receipt(path, payload):
            if path.name == "flatten-plan.applied.json":
                raise OSError("receipt fixture")
            return original_write(path, payload)

        with patch("video_engine_v2.output_layout._atomic_write_json", side_effect=fail_receipt):
            with self.assertRaisesRegex(OSError, "receipt fixture"):
                apply_flatten_plan(
                    output_root=self.output,
                    report_path=self.report,
                    report_sha256=report_hash,
                    confirm="FLATTEN_REVIEW_PACKAGES",
                )

        self.assertTrue(source.is_dir())
        self.assertFalse((self.output / source.name).exists())
        self.assertEqual((source / "CANONICAL_PACKAGE_METADATA.json").read_bytes(), metadata_before)
        self.assertEqual((self.state / "active_package.json").read_bytes(), pointer_before)


if __name__ == "__main__":
    unittest.main()
