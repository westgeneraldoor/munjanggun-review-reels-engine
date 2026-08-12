import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from video_engine_v2.render_job import (
    RenderJobError,
    create_job_record,
    read_job,
    refresh_progress,
    sha256_file,
    update_job,
)


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


if __name__ == "__main__":
    unittest.main()
