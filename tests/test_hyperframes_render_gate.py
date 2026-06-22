import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hyperframes-render-gate.mjs"
SCRATCH = ROOT / "scratch" / f"_test_hyperframes_render_gate_{os.getpid()}"
OUTPUT = ROOT / "output" / f"_test_hyperframes_render_gate_{os.getpid()}"


class HyperFramesRenderGateTest(unittest.TestCase):
    def setUp(self):
        for path in [SCRATCH, OUTPUT]:
            if path.exists():
                shutil.rmtree(path)
        SCRATCH.mkdir(parents=True)
        OUTPUT.mkdir(parents=True)

        self.project_dir = SCRATCH / "hf-project"
        self.project_dir.mkdir()
        (self.project_dir / "index.html").write_text('<div data-composition-id="main"></div>', encoding="utf-8")
        (self.project_dir / "DESIGN.md").write_text("# fixture design\n", encoding="utf-8")
        (self.project_dir / "package.json").write_text(
            json.dumps(
                {
                    "scripts": {
                        "check": "npx --yes hyperframes@0.6.121 lint && npx --yes hyperframes@0.6.121 inspect",
                        "render": "node -e \"console.error('Use Munjanggun render gate from the repository root. Direct HyperFrames render is blocked.'); process.exit(2)\"",
                    }
                }
            ),
            encoding="utf-8",
        )

        self.package_dir = OUTPUT / "review-package"
        self.package_dir.mkdir()
        (self.package_dir / "STATUS.md").write_text(
            "- html_approved_by_user: true\n- mp4_allowed: true\n",
            encoding="utf-8",
        )
        (self.package_dir / "APPROVAL_LOG.md").write_text(
            "- approved_scope: HTML preview approved by user\n- approved_scope: MP4 render approved by user\n",
            encoding="utf-8",
        )
        self.sync_manifest = self.package_dir / "sync_manifest.json"
        self.sync_manifest.write_text(
            json.dumps(
                {
                    "ok": True,
                    "issues": [],
                    "audio": {"final_voice_duration_sec": 25.0, "total_voice_cps": 7.0},
                    "scenes": [{"meaning_match": True, "meaning_match_evidence": "planning_scene:s01"}],
                }
            ),
            encoding="utf-8",
        )
        self.output_mp4 = self.package_dir / "fixture_upload_10mbps.mp4"

    def tearDown(self):
        for path in [SCRATCH, OUTPUT]:
            if path.exists():
                shutil.rmtree(path)

    def run_gate(self, *extra_args):
        return subprocess.run(
            [
                "node",
                str(SCRIPT),
                "--project",
                str(self.project_dir),
                "--package",
                str(self.package_dir),
                "--sync-manifest",
                str(self.sync_manifest),
                "--out",
                str(self.output_mp4),
                *extra_args,
            ],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

    def test_dry_run_passes_without_rendering_mp4(self):
        result = self.run_gate()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dry-run mode", result.stdout)
        self.assertIn("--render-approved", result.stdout)
        self.assertFalse(self.output_mp4.exists())

    def test_rejects_without_mp4_approval_status(self):
        (self.package_dir / "STATUS.md").write_text(
            "- html_approved_by_user: true\n- mp4_allowed: false\n",
            encoding="utf-8",
        )

        result = self.run_gate()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mp4_allowed: true", result.stderr)
        self.assertFalse(self.output_mp4.exists())

    def test_rejects_without_explicit_mp4_approval_log(self):
        (self.package_dir / "APPROVAL_LOG.md").write_text(
            "- approved_scope: HTML preview approved only.\n- not_approved: MP4 render\n",
            encoding="utf-8",
        )

        result = self.run_gate()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("explicit MP4 render approval", result.stderr)
        self.assertFalse(self.output_mp4.exists())

    def test_rejects_non_mp4_render_approval_scope(self):
        (self.package_dir / "APPROVAL_LOG.md").write_text(
            "- approved_scope: HTML preview render approved by user\n",
            encoding="utf-8",
        )

        result = self.run_gate()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("explicit MP4 render approval", result.stderr)
        self.assertFalse(self.output_mp4.exists())

    def test_rejects_not_approved_mentions_as_approval_evidence(self):
        (self.package_dir / "APPROVAL_LOG.md").write_text(
            "- approved_scope: 없음\n- not_approved: script/SRT/TTS/HTML/MP4\n",
            encoding="utf-8",
        )

        result = self.run_gate()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("positive approved_scope", result.stderr)
        self.assertFalse(self.output_mp4.exists())

    def test_rejects_bad_sync_manifest(self):
        self.sync_manifest.write_text(
            json.dumps(
                {
                    "ok": False,
                    "issues": [{"code": "fixture"}],
                    "audio": {"final_voice_duration_sec": 25.0},
                    "scenes": [{"meaning_match": True, "meaning_match_evidence": "planning_scene:s01"}],
                }
            ),
            encoding="utf-8",
        )

        result = self.run_gate()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sync_manifest.ok must be true", result.stderr)
        self.assertFalse(self.output_mp4.exists())

    def test_rejects_sync_manifest_without_total_cps(self):
        self.sync_manifest.write_text(
            json.dumps(
                {
                    "ok": True,
                    "issues": [],
                    "audio": {"final_voice_duration_sec": 25.0},
                    "scenes": [{"meaning_match": True, "meaning_match_evidence": "planning_scene:s01"}],
                }
            ),
            encoding="utf-8",
        )

        result = self.run_gate()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("total_voice_cps", result.stderr)
        self.assertFalse(self.output_mp4.exists())

    def test_rejects_sync_manifest_without_meaning_match_evidence(self):
        self.sync_manifest.write_text(
            json.dumps(
                {
                    "ok": True,
                    "issues": [],
                    "audio": {"final_voice_duration_sec": 25.0, "total_voice_cps": 7.0},
                    "scenes": [{"meaning_match": True}],
                }
            ),
            encoding="utf-8",
        )

        result = self.run_gate()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("meaning_match evidence", result.stderr)
        self.assertFalse(self.output_mp4.exists())

    def test_rejects_sync_manifest_outside_package_folder(self):
        external_manifest = OUTPUT / "external_sync_manifest.json"
        external_manifest.write_text(self.sync_manifest.read_text(encoding="utf-8"), encoding="utf-8")
        self.sync_manifest = external_manifest

        result = self.run_gate()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("inside the approved review package folder", result.stderr)
        self.assertFalse(self.output_mp4.exists())

    def test_rejects_project_inside_tracked_repo_path(self):
        tracked_project = ROOT / "docs" / "_hf_render_gate_should_not_exist"
        if tracked_project.exists():
            shutil.rmtree(tracked_project)
        tracked_project.mkdir()
        try:
            self.project_dir = tracked_project
            result = self.run_gate()

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("scratch/ or output/", result.stderr)
        finally:
            shutil.rmtree(tracked_project)

    def test_rejects_output_outside_package_folder(self):
        self.output_mp4 = OUTPUT / "outside_package_upload_10mbps.mp4"

        result = self.run_gate()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("inside the approved review package folder", result.stderr)
        self.assertFalse(self.output_mp4.exists())

    def test_rejects_output_without_upload_10mbps_filename(self):
        self.output_mp4 = self.package_dir / "fixture_final.mp4"

        result = self.run_gate()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("upload_10mbps", result.stderr)
        self.assertFalse(self.output_mp4.exists())

    def test_rejects_project_that_allows_direct_render(self):
        package = json.loads((self.project_dir / "package.json").read_text(encoding="utf-8"))
        package["scripts"]["render"] = "npx --yes hyperframes@0.6.121 render"
        (self.project_dir / "package.json").write_text(json.dumps(package), encoding="utf-8")

        result = self.run_gate()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must block direct npm run render", result.stderr)
        self.assertFalse(self.output_mp4.exists())

    def test_rejects_stale_project_with_extra_direct_render_script(self):
        package = json.loads((self.project_dir / "package.json").read_text(encoding="utf-8"))
        package["scripts"]["render:hyperframes"] = "npx --yes hyperframes@0.6.121 render"
        (self.project_dir / "package.json").write_text(json.dumps(package), encoding="utf-8")

        result = self.run_gate()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must not expose direct render script", result.stderr)
        self.assertFalse(self.output_mp4.exists())


if __name__ == "__main__":
    unittest.main()
