import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cleanup_apply.py"
CONFIRMATION = "DELETE_GENERATED_INTERMEDIATES"


class CleanupApplyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.artifact_root = self.base / "project"
        self.artifact_root.mkdir()
        self.report_path = self.base / "cleanup-report.json"

    def write_artifact(self, relative_path: str, content: bytes) -> dict:
        path = self.artifact_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return {
            "relative_path": relative_path,
            "bytes": len(content),
            "category": "frame_intermediate",
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    def write_report(self, candidates: list[dict]) -> None:
        self.report_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "mode": "dry_run_only",
                    "root": str(self.artifact_root.resolve()),
                    "candidates": candidates,
                }
            ),
            encoding="utf-8",
        )

    def run_apply(self, *categories: str) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(self.artifact_root),
            "--report",
            str(self.report_path),
            "--confirm",
            CONFIRMATION,
        ]
        for category in categories:
            command.extend(["--category", category])
        return subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )

    def test_deletes_only_explicitly_selected_safe_category(self):
        frame = self.write_artifact("scratch/demo_frames/frame_0001.png", b"frame")
        scale = self.write_artifact("output/demo_scale_lock.mp4", b"scale")
        scale["category"] = "scale_lock"
        self.write_report([frame, scale])

        result = self.run_apply("frame_intermediate")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.artifact_root / frame["relative_path"]).exists())
        self.assertTrue((self.artifact_root / scale["relative_path"]).is_file())
        summary = json.loads(result.stdout)
        self.assertEqual(summary["deleted_files"], 1)
        self.assertEqual(summary["deleted_bytes"], 5)

    def test_hash_change_aborts_before_deleting_any_candidate(self):
        first = self.write_artifact("scratch/run_frames/frame_0001.png", b"first")
        second = self.write_artifact("scratch/run_frames/frame_0002.png", b"second")
        self.write_report([first, second])
        (self.artifact_root / second["relative_path"]).write_bytes(b"changed")

        result = self.run_apply("frame_intermediate")

        self.assertEqual(result.returncode, 2)
        self.assertIn("CLEANUP_APPLY_BLOCKED: candidate changed", result.stderr)
        self.assertTrue((self.artifact_root / first["relative_path"]).is_file())
        self.assertTrue((self.artifact_root / second["relative_path"]).is_file())

    def test_scale_lock_category_is_never_executable(self):
        scale = self.write_artifact("output/demo_scale_lock.mp4", b"scale")
        scale["category"] = "scale_lock"
        self.write_report([scale])

        result = self.run_apply("scale_lock")

        self.assertEqual(result.returncode, 2)
        self.assertIn("CLEANUP_APPLY_BLOCKED: unsupported category", result.stderr)
        self.assertTrue((self.artifact_root / scale["relative_path"]).is_file())

    def test_rejects_a_report_that_did_not_come_from_dry_run_scanner(self):
        frame = self.write_artifact("scratch/demo_frames/frame_0001.png", b"frame")
        self.write_report([frame])
        report = json.loads(self.report_path.read_text(encoding="utf-8"))
        report["mode"] = "not-a-dry-run"
        self.report_path.write_text(json.dumps(report), encoding="utf-8")

        result = self.run_apply("frame_intermediate")

        self.assertEqual(result.returncode, 2)
        self.assertIn("CLEANUP_APPLY_BLOCKED: invalid report", result.stderr)
        self.assertTrue((self.artifact_root / frame["relative_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
