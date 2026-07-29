import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from video_engine_v2.cleanup_dry_run import scan_cleanup_candidates


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cleanup_dry_run.py"


class CleanupDryRunTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name) / "테스트 공백 경로"
        self.package = self.root / "output" / "001_demo"
        self.package.mkdir(parents=True)
        (self.root / "scratch" / "frame_cache").mkdir(parents=True)
        (self.root / "reviews" / "source.txt").parent.mkdir(parents=True)
        (self.root / "reviews" / "source.txt").write_text("customer source", encoding="utf-8")

        self.write("001_final_render_20300102_upload_10mbps.mp4", b"final")
        self.write("001_v2_planning_recipe.json", b"planning")
        self.write("001_v2_edit_recipe.json", b"edit")
        self.write("sync_manifest.json", b"sync")
        self.write("001_script.md", b"script")
        self.write("captions.srt", b"captions")
        self.write("voice.mp3", b"voice")
        self.write("STATUS.md", b"status")
        self.write("APPROVAL_LOG.md", b"approval")
        self.write("privacy_asset_manifest.json", b"privacy")
        self.write("_work/render_post_qa/run/representative_frames/01_hook.jpg", b"evidence frame")

        self.write_scratch("frame_cache/one.jpg", b"same duplicate")
        self.write_scratch("frame_cache/two.jpg", b"same duplicate")
        self.write_scratch("scale_lock/preview.jpg", b"scale")
        self.write_scratch("1fps/frame.jpg", b"one fps")
        self.write_scratch("contact_sheet.jpg", b"contact")
        self.write_scratch("rejected/intermediate.mp4", b"rejected")
        (self.root / "cover.jpg").write_bytes(b"root media")

    def write(self, relative, data):
        path = self.package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def write_scratch(self, relative, data):
        path = self.root / "scratch" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def snapshot(self):
        return {
            path.relative_to(self.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.root.rglob("*")
            if path.is_file()
        }

    def test_scanner_reports_only_allowlisted_candidates_without_mutating_files(self):
        before = self.snapshot()
        report = scan_cleanup_candidates(self.root)

        categories = {item["category"] for item in report["candidates"]}
        protected_paths = {item["relative_path"] for item in report["protected_summary"]}
        self.assertEqual(report["mode"], "dry_run_only")
        self.assertEqual(before, self.snapshot())
        self.assertTrue({"frame_intermediate", "scale_lock", "one_fps", "contact_sheet", "rejected_intermediate"} <= categories)
        self.assertIn("output/001_demo/001_final_render_20300102_upload_10mbps.mp4", protected_paths)
        self.assertIn("output/001_demo/sync_manifest.json", protected_paths)
        self.assertIn("output/001_demo/_work/render_post_qa/run/representative_frames/01_hook.jpg", protected_paths)
        self.assertIn("cover.jpg", protected_paths)
        self.assertGreaterEqual(report["summary"]["duplicate_candidate_groups"], 1)
        self.assertEqual(report["summary"]["candidate_files"], len(report["candidates"]))

    def test_cli_refuses_report_write_inside_scanned_artifacts(self):
        before = self.snapshot()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root), "--report", str(self.package / "report.json")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("REPORT_PATH_INSIDE_SCANNED_ARTIFACTS", result.stderr)
        self.assertFalse((self.package / "report.json").exists())
        self.assertEqual(before, self.snapshot())

    def test_cli_can_write_a_report_outside_the_scanned_artifacts_without_changing_them(self):
        before = self.snapshot()
        report_path = Path(self.tempdir.name) / "cleanup-report.json"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root), "--report", str(report_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(report_path.is_file())
        self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["mode"], "dry_run_only")
        self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
