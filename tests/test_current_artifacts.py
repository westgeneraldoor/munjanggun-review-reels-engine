import hashlib
import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

from video_engine_v2.current_artifacts import (
    SCHEMA_VERSION,
    CurrentArtifactsViolation,
    empty_ledger,
    file_pointer,
    initialize_ledger,
    package_uses_ledger,
    read_ledger,
    record_current_artifacts,
    update_pointers,
)
from video_engine_v2.manual_review import (
    HTML_REVIEW_CHECKS,
    RENDER_REVIEW_CHECKS,
    VOICE_REVIEW_CHECKS,
    record_html_review,
    record_render_review,
    record_voice_review,
)
from video_engine_v2.render_job import create_job_record, publish_job_snapshot, update_job
from video_engine_v2.review_reel_intake import create_canonical_package


class CurrentArtifactsLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.output_root = self.root / "output"
        self.review_path = self.root / "reviews" / "004_fixture.txt"
        self.review_path.parent.mkdir(parents=True)
        self.review_text = "Fixture review: the entrance was difficult before installation."
        self.review_path.write_text(self.review_text, encoding="utf-8")
        self.inventory_path = self.root / "inventory.json"
        self.inventory_path.write_text(
            json.dumps(
                {
                    "schema_version": "review-reel-inventory-v1",
                    "records": [
                        {
                            "record_key": "fixture-review-004",
                            "content_id": "004",
                            "content_slug": "어려운시공",
                            "review_source_path": str(self.review_path),
                            "review_text": self.review_text,
                            "product_order_number": "ORDER-004-FIXTURE",
                            "review_article_id": "REVIEW-004-FIXTURE",
                            "source_reference": "fixture:review-inventory/004",
                            "candidate_reference": "CAND-20300102-0004",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.now = datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    def create(self):
        return create_canonical_package(
            output_root=self.output_root,
            inventory_path=self.inventory_path,
            record_key="fixture-review-004",
            now=self.now,
        )

    def test_new_canonical_package_gets_empty_ledger(self):
        package = self.create()
        ledger = read_ledger(package.package_dir)

        self.assertTrue(package_uses_ledger(package.package_dir))
        self.assertEqual(package.metadata["current_artifacts_contract"], SCHEMA_VERSION)
        self.assertEqual(ledger["revision"], 0)
        self.assertEqual(ledger["pointers"], {})
        self.assertEqual(ledger["package_identity"]["package_name"], package.package_dir.name)

    def test_legacy_package_does_not_receive_a_ledger(self):
        legacy = self.output_root / "001_legacy_20300102_030405"
        legacy.mkdir(parents=True)
        (legacy / "CANONICAL_PACKAGE_METADATA.json").write_text(
            json.dumps({"schema_version": "review-reel-canonical-package-v1", "content_id": "001"}),
            encoding="utf-8",
        )
        voice = legacy / "voice.mp3"
        voice.write_bytes(b"voice")

        self.assertFalse(package_uses_ledger(legacy))
        self.assertIsNone(
            record_current_artifacts(
                legacy,
                producer="tests.legacy",
                artifacts={"voice": voice},
            )
        )
        self.assertFalse((legacy / "CURRENT_ARTIFACTS.json").exists())

    def test_schema_and_identity_and_path_errors_are_rejected(self):
        package = self.create()
        path = package.package_dir / "CURRENT_ARTIFACTS.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["schema_version"] = "wrong"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(CurrentArtifactsViolation) as raised:
            read_ledger(package.package_dir)
        self.assertEqual(raised.exception.code, "CURRENT_ARTIFACTS_SCHEMA_INVALID")

        payload = empty_ledger(package.package_dir)
        payload["package_identity"]["package_name"] = "other"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(CurrentArtifactsViolation) as raised:
            read_ledger(package.package_dir)
        self.assertEqual(raised.exception.code, "CURRENT_ARTIFACTS_PACKAGE_MISMATCH")

        outside = self.root / "outside.txt"
        outside.write_text("nope", encoding="utf-8")
        with self.assertRaises(CurrentArtifactsViolation) as raised:
            file_pointer(package.package_dir, outside, kind="script", producer="tests")
        self.assertEqual(raised.exception.code, "CURRENT_ARTIFACTS_PATH_OUTSIDE_PACKAGE")

    def test_bytes_and_hash_mismatch_and_malformed_overwrite_are_rejected(self):
        package = self.create()
        voice = package.package_dir / "voice.mp3"
        voice.write_bytes(b"voice")
        record_current_artifacts(
            package.package_dir,
            producer="tests",
            artifacts={"voice": voice},
        )
        voice.write_bytes(b"xxxxx")
        with self.assertRaises(CurrentArtifactsViolation) as raised:
            read_ledger(package.package_dir)
        self.assertEqual(raised.exception.code, "CURRENT_ARTIFACTS_HASH_MISMATCH")

        path = package.package_dir / "CURRENT_ARTIFACTS.json"
        before = path.read_bytes()
        path.write_text("{not-json", encoding="utf-8")
        with self.assertRaises(CurrentArtifactsViolation):
            read_ledger(package.package_dir)
        self.assertNotEqual(path.read_bytes(), before)
        path.write_bytes(before)

    def test_revision_is_monotonic_and_batch_update_is_atomic(self):
        package = self.create()
        first = package.package_dir / "a.txt"
        second = package.package_dir / "b.txt"
        first.write_text("a", encoding="utf-8")
        second.write_text("b", encoding="utf-8")
        record_current_artifacts(
            package.package_dir,
            producer="tests",
            artifacts={"script": first, "captions": second},
        )
        ledger = read_ledger(package.package_dir)
        self.assertEqual(ledger["revision"], 1)
        self.assertEqual(set(ledger["pointers"]), {"script", "captions"})

    def test_failed_update_keeps_previous_revision(self):
        package = self.create()
        voice = package.package_dir / "voice.mp3"
        voice.write_bytes(b"voice")
        record_current_artifacts(package.package_dir, producer="tests", artifacts={"voice": voice})
        before = read_ledger(package.package_dir)
        with self.assertRaises(CurrentArtifactsViolation):
            update_pointers(
                package.package_dir,
                {
                    "script": {
                        "relative_path": "../outside.txt",
                        "bytes": 1,
                        "sha256": "0" * 64,
                        "artifact_kind": "script",
                        "producer": "tests",
                        "recorded_at": "2030-01-02T03:04:05+00:00",
                    }
                },
            )
        after = read_ledger(package.package_dir)
        self.assertEqual(after["revision"], before["revision"])
        self.assertEqual(after["pointers"], before["pointers"])

    def test_same_path_revision_can_replace_only_its_stale_pointer(self):
        package = self.create()
        privacy = package.package_dir / "privacy.json"
        privacy.write_text('{"revision":1}', encoding="utf-8")
        record_current_artifacts(
            package.package_dir,
            producer="tests.revision.one",
            artifacts={"privacy_manifest": privacy},
        )
        privacy.write_text('{"revision":2}', encoding="utf-8")

        record_current_artifacts(
            package.package_dir,
            producer="tests.revision.two",
            artifacts={"privacy_manifest": privacy},
        )

        ledger = read_ledger(package.package_dir)
        self.assertEqual(ledger["revision"], 2)
        self.assertEqual(
            ledger["pointers"]["privacy_manifest"]["sha256"],
            hashlib.sha256(privacy.read_bytes()).hexdigest(),
        )

    def test_replacing_one_kind_does_not_hide_an_unrelated_stale_pointer(self):
        package = self.create()
        privacy = package.package_dir / "privacy.json"
        voice = package.package_dir / "voice.mp3"
        privacy.write_text("privacy-one", encoding="utf-8")
        voice.write_bytes(b"voice-one")
        record_current_artifacts(
            package.package_dir,
            producer="tests.initial",
            artifacts={"privacy_manifest": privacy, "voice": voice},
        )
        privacy.write_text("privacy-two", encoding="utf-8")
        voice.write_bytes(b"voice-tampered")

        with self.assertRaises(CurrentArtifactsViolation) as raised:
            record_current_artifacts(
                package.package_dir,
                producer="tests.revision",
                artifacts={"privacy_manifest": privacy},
            )

        self.assertEqual(raised.exception.code, "CURRENT_ARTIFACTS_BYTES_MISMATCH")

    def test_concurrent_updates_do_not_lose_pointers(self):
        package = self.create()
        left = package.package_dir / "left.txt"
        right = package.package_dir / "right.txt"
        left.write_text("left", encoding="utf-8")
        right.write_text("right", encoding="utf-8")
        errors: list[BaseException] = []

        def write(kind: str, path: Path):
            try:
                record_current_artifacts(
                    package.package_dir,
                    producer="tests.concurrent",
                    artifacts={kind: path},
                )
            except BaseException as error:  # pragma: no cover - failure collected below
                errors.append(error)

        workers = [
            threading.Thread(target=write, args=("script", left)),
            threading.Thread(target=write, args=("captions", right)),
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(errors, [])
        ledger = read_ledger(package.package_dir)
        self.assertEqual(ledger["revision"], 2)
        self.assertEqual(set(ledger["pointers"]), {"script", "captions"})


class CurrentArtifactsWriterCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.output_root = self.root / "output"
        self.review_path = self.root / "reviews" / "004_fixture.txt"
        self.review_path.parent.mkdir(parents=True)
        self.review_text = "Fixture review: the entrance was difficult before installation."
        self.review_path.write_text(self.review_text, encoding="utf-8")
        self.inventory_path = self.root / "inventory.json"
        self.inventory_path.write_text(
            json.dumps(
                {
                    "schema_version": "review-reel-inventory-v1",
                    "records": [
                        {
                            "record_key": "fixture-review-004",
                            "content_id": "004",
                            "content_slug": "어려운시공",
                            "review_source_path": str(self.review_path),
                            "review_text": self.review_text,
                            "product_order_number": "ORDER-004-FIXTURE",
                            "review_article_id": "REVIEW-004-FIXTURE",
                            "source_reference": "fixture:review-inventory/004",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def create(self):
        return create_canonical_package(
            output_root=self.output_root,
            inventory_path=self.inventory_path,
            record_key="fixture-review-004",
            now=datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        )

    def test_manual_review_and_approval_writers_update_ledger_and_failures_do_not(self):
        from video_engine_v2.approval_evidence import record_html_approval, record_render_approval

        package = self.create()
        voice = package.package_dir / "voice.mp3"
        srt = package.package_dir / "captions.srt"
        report = package.package_dir / "_work" / "tts.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        voice.write_bytes(b"voice")
        srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nfixture\n", encoding="utf-8")
        report.write_text("{}", encoding="utf-8")
        before = read_ledger(package.package_dir)["revision"]
        with self.assertRaises(Exception):
            record_voice_review(
                package_dir=package.package_dir,
                voice_path=package.package_dir / "missing.mp3",
                srt_path=srt,
                tts_report_path=report,
                reviewer="r",
                evidence_reference="e",
                checks=VOICE_REVIEW_CHECKS,
            )
        self.assertEqual(read_ledger(package.package_dir)["revision"], before)
        record_voice_review(
            package_dir=package.package_dir,
            voice_path=voice,
            srt_path=srt,
            tts_report_path=report,
            reviewer="r",
            evidence_reference="e",
            checks=VOICE_REVIEW_CHECKS,
        )
        self.assertIn("voice_manual_review", read_ledger(package.package_dir)["pointers"])

        preview = package.package_dir / "004_html_preview_v2"
        preview.mkdir()
        html = preview / "index.html"
        html.write_text("<html></html>", encoding="utf-8")
        artifact = preview / "html_artifact_evidence.json"
        artifact.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "package_identity": {
                        "package_path": str(package.package_dir.resolve()),
                        "package_name": package.package_dir.name,
                    },
                    "html_relative_path": html.relative_to(package.package_dir).as_posix(),
                    "html_sha256": hashlib.sha256(html.read_bytes()).hexdigest(),
                }
            ),
            encoding="utf-8",
        )
        frame = preview / "_qa_frames" / "01.png"
        frame.parent.mkdir()
        frame.write_bytes(b"frame")
        (preview / "html_internal_qa_report.json").write_text(
            json.dumps(
                {
                    "automatic_status": "pass",
                    "checks": [{"frame_relative_path": "_qa_frames/01.png"}],
                    "hook_sequence_checks": [],
                }
            ),
            encoding="utf-8",
        )
        record_html_review(
            package_dir=package.package_dir,
            html_path=html,
            reviewer="r",
            evidence_reference="e",
            checks=HTML_REVIEW_CHECKS,
        )
        record_html_approval(
            package_dir=package.package_dir,
            html_path=html,
            approved_by="user",
            evidence_reference="html-ok",
        )
        record_render_approval(
            package_dir=package.package_dir,
            html_path=html,
            approved_by="user",
            evidence_reference="mp4-ok",
        )
        pointers = read_ledger(package.package_dir)["pointers"]
        self.assertIn("html_manual_review", pointers)
        self.assertIn("html_approval", pointers)
        self.assertIn("mp4_render_approval", pointers)
        mp4 = package.package_dir / "004_final_render_20300102_upload_10mbps.mp4"
        qa_report = package.package_dir / "render_post_qa_report.json"
        review_receipt = package.package_dir / "_work" / "manual_reviews" / "render_review_fixture.json"
        mp4.write_bytes(b"dummy-mp4")
        qa_report.write_text("{}", encoding="utf-8")
        review_receipt.parent.mkdir(parents=True, exist_ok=True)
        review_receipt.write_text("{}", encoding="utf-8")
        record_current_artifacts(
            package.package_dir,
            producer="produce_review_v2.post_render_qa",
            artifacts={
                "upload_mp4": mp4,
                "post_render_qa": qa_report,
                "render_manual_review": review_receipt,
            },
        )
        self.assertIn("upload_mp4", read_ledger(package.package_dir)["pointers"])
        self.assertIn("post_render_qa", read_ledger(package.package_dir)["pointers"])
        self.assertIn("render_manual_review", read_ledger(package.package_dir)["pointers"])

    def test_render_job_writer_updates_render_job_pointer(self):
        package = self.create()
        receipt = package.package_dir / "_work" / "production_gates" / "render.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_text("{}", encoding="utf-8")
        job_path = create_job_record(
            package_dir=package.package_dir,
            job_id="20300102T030405000000Z-abcd1234",
            bindings={"preset": {}},
            receipt_path=receipt,
            output_path=package.package_dir / "004_final_render_20300102_upload_10mbps.mp4",
            expected_frames=10,
        )
        initial = read_ledger(package.package_dir)
        self.assertIn("render_job", initial["pointers"])
        self.assertTrue(initial["pointers"]["render_job"]["relative_path"].endswith("render_job_queued.json"))

        update_job(
            job_path,
            state="running",
            worker_pid=123,
            started_at="2030-01-02T03:04:06+00:00",
        )
        self.assertEqual(read_ledger(package.package_dir)["revision"], initial["revision"])

        update_job(
            job_path,
            state="succeeded",
            completed_at="2030-01-02T03:04:07+00:00",
            rendered_frames=10,
            output_evidence={"path": "fixture", "bytes": 1, "sha256": "0" * 64},
            failure=None,
            exit_code=0,
        )
        upload = package.package_dir / "004_final_render_20300102_upload_10mbps.mp4"
        upload.write_bytes(b"mp4")
        publish_job_snapshot(
            job_path,
            producer="tests.render.succeeded",
            extra_artifacts={"upload_mp4": upload},
        )
        completed = read_ledger(package.package_dir)
        self.assertTrue(completed["pointers"]["render_job"]["relative_path"].endswith("render_job_succeeded.json"))
        self.assertEqual(completed["pointers"]["upload_mp4"]["relative_path"], upload.name)

    def test_ledger_ignores_unpointed_higher_version_and_newer_mtime_files(self):
        from video_engine_v2.package_state import map_package_state

        package = self.create()
        current = package.package_dir / "sync_manifest_v6.json"
        decoy = package.package_dir / "sync_manifest_v7.json"
        current.write_text(json.dumps({"ok": True, "fixture": "current"}), encoding="utf-8")
        decoy.write_text(json.dumps({"ok": True, "fixture": "decoy"}), encoding="utf-8")
        record_current_artifacts(
            package.package_dir,
            producer="tests",
            artifacts={"sync_manifest": current},
        )
        decoy.write_text(json.dumps({"ok": True, "fixture": "newer"}), encoding="utf-8")
        state = map_package_state(package.package_dir)
        self.assertEqual(state["state_source"], "current_artifacts_ledger")
        self.assertEqual(state["sync_ok"], True)
        self.assertEqual(
            state["artifacts"][0]["relative_path"],
            "sync_manifest_v6.json",
        )

    def test_remaining_official_pointer_kinds_can_be_recorded_in_one_revision(self):
        package = self.create()
        files = {}
        for kind in (
            "script",
            "planning_recipe",
            "edit_recipe",
            "captions",
            "voice",
            "tts_report",
            "privacy_manifest",
            "html",
            "html_artifact_evidence",
            "html_qa_report",
        ):
            path = package.package_dir / f"{kind}.dat"
            path.write_bytes(kind.encode("ascii"))
            files[kind] = path
        record_current_artifacts(
            package.package_dir,
            producer="tests.writer_matrix",
            artifacts=files,
        )
        ledger = read_ledger(package.package_dir)
        self.assertEqual(ledger["revision"], 1)
        self.assertEqual(set(ledger["pointers"]), set(files))

    def test_missing_ledger_on_enabled_package_does_not_filename_scan(self):
        from video_engine_v2.package_state import map_package_state

        package = self.create()
        (package.package_dir / "CURRENT_ARTIFACTS.json").unlink()
        (package.package_dir / "001_demo_final_render_20300102_upload_10mbps.mp4").write_bytes(b"mp4")
        state = map_package_state(package.package_dir)
        self.assertEqual(state["render_complete"], "unknown")
        self.assertIn("CURRENT_ARTIFACTS_MISSING", state["render_evidence_limitations"])


if __name__ == "__main__":
    unittest.main()
