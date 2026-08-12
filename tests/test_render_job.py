import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest

from video_engine_v2.render_job import (
    RenderJobError,
    create_job_record,
    read_job,
    refresh_progress,
    sha256_file,
    update_job,
)
from scripts import produce_review_v2
from scripts import render_review_v2_job


class RenderJobRecordTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.package = Path(self.temporary.name) / "118_package"
        self.package.mkdir()
        receipt_dir = self.package / "_work" / "production_gates"
        receipt_dir.mkdir(parents=True)
        self.receipt = receipt_dir / "render_receipt.json"
        self.receipt.write_text('{"action":"render"}\n', encoding="utf-8")
        self.output = self.package / "118_demo_final_render_20260812_upload_10mbps.mp4"

    def create_job(self, *, job_id="20260812T010203000000Z-ab12cd34"):
        return create_job_record(
            package_dir=self.package,
            job_id=job_id,
            bindings={
                "html_path": str(self.package / "preview" / "index.html"),
                "html_sha256": "a" * 64,
                "sync_manifest_sha256": "b" * 64,
                "privacy_manifest_sha256": "c" * 64,
                "preset": {"fps": 30},
            },
            receipt_path=self.receipt,
            output_path=self.output,
            expected_frames=818,
        )

    def test_create_job_record_is_contained_and_complete(self):
        path = self.create_job()

        self.assertEqual(
            path,
            self.package / "_work" / "render_jobs" / "20260812T010203000000Z-ab12cd34" / "render_job.json",
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["state"], "queued")
        self.assertEqual(payload["expected_frames"], 818)
        self.assertEqual(payload["rendered_frames"], 0)
        self.assertEqual(payload["bindings"]["receipt_sha256"], sha256_file(self.receipt))
        self.assertEqual(payload["bindings"]["output_path"], str(self.output.resolve()))
        self.assertEqual(payload["output_evidence"], None)
        self.assertEqual(payload["failure"], None)

    def test_rejects_job_id_path_escape(self):
        with self.assertRaisesRegex(RenderJobError, "JOB_ID_INVALID"):
            self.create_job(job_id="../../escape")

    def test_rejects_output_outside_package(self):
        with self.assertRaisesRegex(RenderJobError, "OUTPUT_OUTSIDE_PACKAGE"):
            create_job_record(
                package_dir=self.package,
                job_id="20260812T010203000000Z-ab12cd34",
                bindings={},
                receipt_path=self.receipt,
                output_path=Path(self.temporary.name) / "outside.mp4",
                expected_frames=10,
            )

    def test_update_rejects_invalid_state_and_immutable_fields(self):
        path = self.create_job()

        with self.assertRaisesRegex(RenderJobError, "JOB_STATE_INVALID"):
            update_job(path, state="complete")
        with self.assertRaisesRegex(RenderJobError, "JOB_FIELD_IMMUTABLE"):
            update_job(path, bindings={})
        update_job(path, state="running")
        update_job(path, state="succeeded")
        with self.assertRaisesRegex(RenderJobError, "JOB_STATE_TRANSITION_INVALID"):
            update_job(path, state="running")

    def test_read_rejects_tampered_immutable_bindings(self):
        path = self.create_job()
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["bindings"]["output_path"] = str(self.package / "replacement.mp4")
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(RenderJobError, "JOB_BINDINGS_TAMPERED"):
            read_job(path)

    def test_refresh_progress_counts_only_numbered_png_frames_without_mutating_record(self):
        path = self.create_job()
        job = read_job(path)
        frame_dir = Path(job["frame_dir"])
        frame_dir.mkdir()
        (frame_dir / "frame_00001.png").write_bytes(b"1")
        (frame_dir / "frame_00002.png").write_bytes(b"2")
        (frame_dir / "other.png").write_bytes(b"x")

        refreshed = refresh_progress(path)

        self.assertEqual(refreshed["rendered_frames"], 2)
        self.assertEqual(refreshed["progress"], "2 / 818")
        self.assertEqual(read_job(path)["rendered_frames"], 0)

    def test_atomic_update_preserves_valid_json_and_sets_terminal_evidence(self):
        path = self.create_job()
        self.output.write_bytes(b"final mp4")
        update_job(path, state="running")

        updated = update_job(
            path,
            state="succeeded",
            completed_at="2026-08-12T01:02:03+00:00",
            rendered_frames=818,
            output_evidence={
                "path": str(self.output.resolve()),
                "bytes": self.output.stat().st_size,
                "sha256": sha256_file(self.output),
            },
            exit_code=0,
        )

        self.assertEqual(updated["state"], "succeeded")
        self.assertEqual(read_job(path)["output_evidence"]["sha256"], sha256_file(self.output))


class RenderJobWorkerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.package = Path(self.temporary.name) / "118_package"
        self.package.mkdir()
        self.html = self.package / "preview" / "index.html"
        self.html.parent.mkdir()
        self.html.write_text("<!doctype html>", encoding="utf-8")
        self.sync = self.package / "sync_manifest.json"
        self.sync.write_text('{"ok":true,"audio":{"final_voice_duration_sec":0.1}}', encoding="utf-8")
        self.privacy = self.package / "privacy_asset_manifest.json"
        self.privacy.write_text('{"unresolved_risks":[]}', encoding="utf-8")
        receipt_dir = self.package / "_work" / "production_gates"
        receipt_dir.mkdir(parents=True)
        self.receipt = receipt_dir / "render_receipt.json"
        self.receipt.write_text('{"action":"render"}\n', encoding="utf-8")
        self.output = self.package / "118_demo_final_render_20260812_upload_10mbps.mp4"

    def create_job(self, job_id="20260812T020304000000Z-1234abcd"):
        renderer = produce_review_v2.ROOT / "render_html_preview_v2.js"
        return create_job_record(
            package_dir=self.package,
            job_id=job_id,
            bindings={
                "html_path": str(self.html.resolve()),
                "html_sha256": sha256_file(self.html),
                "sync_manifest_path": str(self.sync.resolve()),
                "sync_manifest_sha256": sha256_file(self.sync),
                "privacy_manifest_path": str(self.privacy.resolve()),
                "privacy_manifest_sha256": sha256_file(self.privacy),
                "renderer_script_path": str(renderer.resolve()),
                "renderer_script_sha256": sha256_file(renderer),
                "preset": {"fps": 30},
            },
            receipt_path=self.receipt,
            output_path=self.output,
            expected_frames=3,
        )

    def test_background_process_survives_launcher_exit(self):
        marker = Path(self.temporary.name) / "child-finished.txt"
        child = Path(self.temporary.name) / "child.py"
        child.write_text(
            "import pathlib, sys, time\ntime.sleep(0.8)\npathlib.Path(sys.argv[1]).write_text('done', encoding='utf-8')\n",
            encoding="utf-8",
        )
        launcher = Path(self.temporary.name) / "launcher.py"
        launcher.write_text(
            "import sys\nsys.path.insert(0, sys.argv[1])\n"
            "from scripts.produce_review_v2 import spawn_background_process, ROOT\n"
            "spawn_background_process([sys.executable, sys.argv[2], sys.argv[3]], cwd=ROOT)\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, str(launcher), str(produce_review_v2.ROOT), str(child), str(marker)],
            cwd=produce_review_v2.ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=5,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        deadline = time.monotonic() + 4
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(marker.exists(), "detached child must finish after its launcher exits")

    def test_process_liveness_probe_does_not_terminate_the_probed_process(self):
        marker = Path(self.temporary.name) / "probe-survived.txt"
        probe = Path(self.temporary.name) / "probe.py"
        probe.write_text(
            "import os, pathlib, sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from scripts.produce_review_v2 import process_is_running\n"
            "assert process_is_running(os.getpid())\n"
            "pathlib.Path(sys.argv[2]).write_text('alive', encoding='utf-8')\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, str(probe), str(produce_review_v2.ROOT), str(marker)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=5,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(marker.exists())

    def test_worker_success_records_output_hash_and_progress(self):
        job_path = self.create_job()
        job = read_job(job_path)
        script = (
            "import pathlib, sys\n"
            "out=pathlib.Path(sys.argv[1]); frames=pathlib.Path(sys.argv[2]); frames.mkdir()\n"
            "[(frames / f'frame_{i:05d}.png').write_bytes(b'x') for i in range(1,4)]\n"
            "out.write_bytes(b'final mp4')\nprint('renderer complete')\n"
        )
        command = [sys.executable, "-c", script, str(self.output), job["frame_dir"]]

        result = render_review_v2_job.run_job(job_path, command_builder=lambda _: command)

        finished = read_job(job_path)
        self.assertEqual(result, 0)
        self.assertEqual(finished["state"], "succeeded")
        self.assertEqual(finished["rendered_frames"], 3)
        self.assertEqual(finished["output_evidence"]["bytes"], len(b"final mp4"))
        self.assertEqual(finished["output_evidence"]["sha256"], sha256_file(self.output))
        self.assertIn("renderer complete", Path(finished["log_path"]).read_text(encoding="utf-8"))

    def test_worker_failure_preserves_partial_frames_log_and_receipt(self):
        job_path = self.create_job()
        job = read_job(job_path)
        script = (
            "import pathlib, sys\n"
            "frames=pathlib.Path(sys.argv[1]); frames.mkdir(); (frames/'frame_00001.png').write_bytes(b'x')\n"
            "print('deliberate failure')\nsys.exit(7)\n"
        )
        command = [sys.executable, "-c", script, job["frame_dir"]]

        result = render_review_v2_job.run_job(job_path, command_builder=lambda _: command)

        failed = read_job(job_path)
        self.assertEqual(result, 7)
        self.assertEqual(failed["state"], "failed")
        self.assertEqual(failed["rendered_frames"], 1)
        self.assertEqual(failed["exit_code"], 7)
        self.assertTrue(Path(failed["frame_dir"]).is_dir())
        self.assertTrue(self.receipt.is_file())
        self.assertIn("deliberate failure", Path(failed["log_path"]).read_text(encoding="utf-8"))

    def test_worker_blocks_changed_bound_input_before_renderer_runs(self):
        job_path = self.create_job()
        marker = Path(self.temporary.name) / "should-not-run.txt"
        self.html.write_text("changed", encoding="utf-8")
        command = [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')"]

        result = render_review_v2_job.run_job(job_path, command_builder=lambda _: command)

        failed = read_job(job_path)
        self.assertEqual(result, 2)
        self.assertEqual(failed["state"], "failed")
        self.assertEqual(failed["failure"]["code"], "BOUND_INPUT_CHANGED")
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
