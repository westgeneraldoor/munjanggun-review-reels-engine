from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import produce_review_v2
from video_engine_v2.render_job import create_job_record


class ProduceReviewV2SubprocessTest(unittest.TestCase):
    def test_parser_exposes_background_start_and_status_commands(self):
        parser = produce_review_v2.build_parser()
        start = parser.parse_args(
            [
                "render-start",
                "--package", "package",
                "--html", "index.html",
                "--privacy-manifest", "privacy.json",
                "--sync-manifest", "sync.json",
                "--out", "final.mp4",
            ]
        )
        status = parser.parse_args(["render-status", "--package", "package", "--job-id", "job-id"])

        self.assertEqual(start.command, "render-start")
        self.assertEqual(status.command, "render-status")

    def test_render_start_returns_job_id_without_waiting_for_worker(self):
        with TemporaryDirectory() as temporary:
            package = Path(temporary) / "118_package"
            package.mkdir()
            html = package / "preview" / "index.html"
            html.parent.mkdir()
            html.write_text("<!doctype html>", encoding="utf-8")
            sync = package / "sync_manifest.json"
            sync.write_text('{"audio":{"final_voice_duration_sec":27.26}}', encoding="utf-8")
            privacy = package / "privacy.json"
            privacy.write_text("{}", encoding="utf-8")
            output = package / "118_demo_final_render_20260812_upload_10mbps.mp4"
            receipt = {
                "action": "render",
                "package_path": str(package.resolve()),
                "html_path": str(html.resolve()),
                "html_sha256": "a" * 64,
                "sync_manifest_path": str(sync.resolve()),
                "sync_manifest_sha256": "b" * 64,
                "privacy_manifest_path": str(privacy.resolve()),
                "privacy_manifest_sha256": "c" * 64,
                "output_path": str(output.resolve()),
                "preset": dict(produce_review_v2.FINAL_RENDER_PRESET),
                "render_dependencies": [],
            }
            stdout = io.StringIO()
            argv = [
                "render-start",
                "--package", str(package),
                "--html", str(html),
                "--privacy-manifest", str(privacy),
                "--sync-manifest", str(sync),
                "--out", str(output),
            ]

            with (
                patch.object(produce_review_v2, "validate_render_gate", return_value=receipt),
                patch.object(produce_review_v2, "spawn_background_process", return_value=4321),
                redirect_stdout(stdout),
            ):
                result = produce_review_v2.main(argv)

            response = json.loads(stdout.getvalue())
            job = json.loads(Path(response["status_path"]).read_text(encoding="utf-8"))
            self.assertEqual(result, 0)
            self.assertEqual(response["state"], "queued")
            self.assertEqual(response["worker_pid"], 4321)
            self.assertEqual(job["expected_frames"], 818)
            self.assertEqual(job["state"], "queued")

    def test_render_start_requires_a_new_output_name_when_partial_frames_exist(self):
        with TemporaryDirectory() as temporary:
            package = Path(temporary) / "118_package"
            package.mkdir()
            html = package / "index.html"
            html.write_text("<!doctype html>", encoding="utf-8")
            sync = package / "sync.json"
            sync.write_text('{"audio":{"final_voice_duration_sec":1.0}}', encoding="utf-8")
            privacy = package / "privacy.json"
            privacy.write_text("{}", encoding="utf-8")
            output = package / "118_demo_final_render_20260812_upload_10mbps.mp4"
            (package / f"{output.stem}_frames").mkdir()
            receipt = {
                "action": "render",
                "package_path": str(package.resolve()),
                "html_path": str(html.resolve()),
                "html_sha256": "a" * 64,
                "sync_manifest_path": str(sync.resolve()),
                "sync_manifest_sha256": "b" * 64,
                "privacy_manifest_path": str(privacy.resolve()),
                "privacy_manifest_sha256": "c" * 64,
                "output_path": str(output.resolve()),
                "preset": dict(produce_review_v2.FINAL_RENDER_PRESET),
                "render_dependencies": [],
            }
            worker = patch.object(produce_review_v2, "spawn_background_process", return_value=4321)
            with (
                patch.object(produce_review_v2, "validate_render_gate", return_value=receipt),
                worker as spawn,
                redirect_stdout(io.StringIO()),
            ):
                result = produce_review_v2.main(
                    [
                        "render-start",
                        "--package", str(package),
                        "--html", str(html),
                        "--privacy-manifest", str(privacy),
                        "--sync-manifest", str(sync),
                        "--out", str(output),
                    ]
                )

            self.assertEqual(result, 2)
            spawn.assert_not_called()
            self.assertFalse((package / "_work" / "render_jobs").exists())
            self.assertFalse((package / "_work" / "production_gates").exists())

    def test_render_status_rejects_job_id_path_traversal(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            requested_package = root / "requested"
            requested_package.mkdir()
            actual_package = root / "actual"
            actual_package.mkdir()
            receipt = actual_package / "receipt.json"
            receipt.write_text("{}", encoding="utf-8")
            output = actual_package / "118_demo_final_render_20260812_upload_10mbps.mp4"
            job_id = "20260812T010203000000Z-ab12cd34"
            create_job_record(
                package_dir=actual_package,
                job_id=job_id,
                bindings={},
                receipt_path=receipt,
                output_path=output,
                expected_frames=1,
            )
            traversal = f"../../../actual/_work/render_jobs/{job_id}"

            result = produce_review_v2.main(
                ["render-status", "--package", str(requested_package), "--job-id", traversal]
            )

            self.assertEqual(result, 2)

    def test_render_status_marks_a_stale_unstarted_job_failed(self):
        with TemporaryDirectory() as temporary:
            package = Path(temporary) / "118_package"
            package.mkdir()
            receipt = package / "receipt.json"
            receipt.write_text("{}", encoding="utf-8")
            output = package / "118_demo_final_render_20260812_upload_10mbps.mp4"
            job_id = "20260812T010203000000Z-ab12cd34"
            job_path = create_job_record(
                package_dir=package,
                job_id=job_id,
                bindings={},
                receipt_path=receipt,
                output_path=output,
                expected_frames=1,
            )
            payload = json.loads(job_path.read_text(encoding="utf-8"))
            payload["created_at"] = "2000-01-01T00:00:00+00:00"
            job_path.write_text(json.dumps(payload), encoding="utf-8")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                result = produce_review_v2.main(
                    ["render-status", "--package", str(package), "--job-id", job_id]
                )

            status = json.loads(stdout.getvalue())
            self.assertEqual(result, 0)
            self.assertEqual(status["state"], "failed")
            self.assertEqual(status["failure"]["code"], "WORKER_DID_NOT_START")

    def test_utf8_child_runner_preserves_korean_output_paths(self):
        runner = getattr(produce_review_v2, "run_utf8_capture", None)
        self.assertIsNotNone(runner, "official HTML orchestration needs a UTF-8 child-process boundary")
        if runner is None:
            return

        expected = "C:/작업/문장군/118_견적/index.html"
        result = runner([sys.executable, "-c", f"print({expected!r})"], cwd=produce_review_v2.ROOT)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), expected)


if __name__ == "__main__":
    unittest.main()
