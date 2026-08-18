import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "produce_review_v2.py"


class ManualReviewEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.package = Path(self.tempdir.name) / "output" / "inbox_20300102" / "001_demo_20300102_030405"
        self.package.mkdir(parents=True)

    def run_command(self, *args):
        return subprocess.run(
            ["python", str(SCRIPT), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def prepare_html_review_fixture(self):
        preview = self.package / "preview"
        frame_dir = preview / "_qa_frames"
        hook_dir = frame_dir / "hook_sequence"
        hook_dir.mkdir(parents=True)
        html = preview / "index.html"
        artifact = preview / "html_artifact_evidence.json"
        report = preview / "html_internal_qa_report.json"
        beat_frame = frame_dir / "01_b01.png"
        hook_frame = hook_dir / "01_hook.png"
        html.write_text("<html></html>", encoding="utf-8")
        beat_frame.write_bytes(b"beat")
        hook_frame.write_bytes(b"hook")
        artifact.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "package_identity": {
                        "package_path": str(self.package.resolve()),
                        "package_name": self.package.name,
                    },
                    "html_relative_path": html.relative_to(self.package).as_posix(),
                    "html_sha256": hashlib.sha256(html.read_bytes()).hexdigest(),
                }
            ),
            encoding="utf-8",
        )
        report.write_text(
            json.dumps(
                {
                    "automatic_status": "pass",
                    "checks": [{"frame_relative_path": "_qa_frames/01_b01.png"}],
                    "hook_sequence_checks": [
                        {"frame_relative_path": "_qa_frames/hook_sequence/01_hook.png"}
                    ],
                }
            ),
            encoding="utf-8",
        )
        return html, artifact, report

    def test_voice_review_receipt_binds_voice_srt_and_tts_report(self):
        voice = self.package / "voice.mp3"
        srt = self.package / "captions.srt"
        tts_report = self.package / "_work" / "tts_generation_report.json"
        tts_report.parent.mkdir()
        voice.write_bytes(b"voice")
        srt.write_text("1\n00:00:00,000 --> 00:00:01,000\ncaption\n", encoding="utf-8")
        tts_report.write_text('{"provider":"fixture"}', encoding="utf-8")

        result = self.run_command(
            "voice-review-record",
            "--package", str(self.package),
            "--voice", str(voice),
            "--srt", str(srt),
            "--tts-report", str(tts_report),
            "--reviewer", "fixture-worker",
            "--evidence-reference", "fixture-task",
            "--check", "pronunciation_clear",
            "--check", "tone_approved",
            "--check", "caption_sync_approved",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        receipts = list((self.package / "_work" / "manual_reviews").glob("voice_review_*.json"))
        self.assertEqual(len(receipts), 1)
        receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
        self.assertEqual(receipt["review_kind"], "voice")
        self.assertEqual(receipt["target"]["sha256"], hashlib.sha256(voice.read_bytes()).hexdigest())
        self.assertEqual(receipt["srt"]["sha256"], hashlib.sha256(srt.read_bytes()).hexdigest())
        self.assertEqual(receipt["tts_report"]["sha256"], hashlib.sha256(tts_report.read_bytes()).hexdigest())

    def test_voice_review_receipt_is_not_written_when_a_required_check_is_missing(self):
        voice = self.package / "voice.mp3"
        srt = self.package / "captions.srt"
        tts_report = self.package / "tts.json"
        voice.write_bytes(b"voice")
        srt.write_text("caption", encoding="utf-8")
        tts_report.write_text("{}", encoding="utf-8")

        result = self.run_command(
            "voice-review-record",
            "--package", str(self.package),
            "--voice", str(voice),
            "--srt", str(srt),
            "--tts-report", str(tts_report),
            "--reviewer", "fixture-worker",
            "--evidence-reference", "fixture-task",
            "--check", "pronunciation_clear",
            "--check", "tone_approved",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MANUAL_REVIEW_CHECKS_INCOMPLETE", result.stderr)
        self.assertFalse((self.package / "_work" / "manual_reviews").exists())

    def test_html_review_receipt_binds_html_artifact_report_and_all_qa_frames(self):
        html, artifact, report = self.prepare_html_review_fixture()

        result = self.run_command(
            "html-review-record",
            "--package", str(self.package),
            "--html", str(html),
            "--reviewer", "fixture-worker",
            "--evidence-reference", "fixture-task",
            *sum((["--check", value] for value in (
                "hook_sequence_reviewed", "meaning_sync_reviewed", "caption_layout_reviewed",
                "privacy_reviewed", "review_capture_reviewed", "cta_reviewed",
            )), []),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        receipt_path = next((self.package / "_work" / "manual_reviews").glob("html_review_*.json"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["review_kind"], "html")
        self.assertEqual(len(receipt["qa_frames"]), 2)
        self.assertEqual(receipt["qa_report"]["sha256"], hashlib.sha256(report.read_bytes()).hexdigest())

    def test_html_approval_command_requires_current_manual_html_review(self):
        html, _, _ = self.prepare_html_review_fixture()

        result = self.run_command(
            "html-approval-record",
            "--package", str(self.package),
            "--html", str(html),
            "--approved-by", "user",
            "--evidence-reference", "user said HTML approved",
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("CURRENT_HTML_MANUAL_REVIEW_MISSING", result.stderr)
        self.assertFalse((self.package / "HTML_APPROVAL.json").exists())

    def test_official_approval_commands_bind_html_then_unlock_mp4_separately(self):
        html, artifact, _ = self.prepare_html_review_fixture()
        review = self.run_command(
            "html-review-record",
            "--package", str(self.package),
            "--html", str(html),
            "--reviewer", "fixture-worker",
            "--evidence-reference", "fixture-task",
            *sum((["--check", value] for value in (
                "hook_sequence_reviewed", "meaning_sync_reviewed", "caption_layout_reviewed",
                "privacy_reviewed", "review_capture_reviewed", "cta_reviewed",
            )), []),
        )
        self.assertEqual(review.returncode, 0, review.stderr)

        html_approval = self.run_command(
            "html-approval-record",
            "--package", str(self.package),
            "--html", str(html),
            "--approved-by", "user",
            "--evidence-reference", "user said HTML approved",
        )

        self.assertEqual(html_approval.returncode, 0, html_approval.stderr)
        approval = json.loads((self.package / "HTML_APPROVAL.json").read_text(encoding="utf-8"))
        self.assertEqual(approval["html_sha256"], hashlib.sha256(html.read_bytes()).hexdigest())
        self.assertEqual(
            approval["html_artifact_evidence_sha256"],
            hashlib.sha256(artifact.read_bytes()).hexdigest(),
        )
        status = (self.package / "STATUS.md").read_text(encoding="utf-8")
        log = (self.package / "APPROVAL_LOG.md").read_text(encoding="utf-8")
        self.assertIn("html_approved_by_user: true", status)
        self.assertIn("mp4_allowed: false", status)
        self.assertIn("approved_scope: HTML preview approved", log)
        self.assertIn("not_approved: MP4 render pending", log)

        render_approval = self.run_command(
            "render-approval-record",
            "--package", str(self.package),
            "--html", str(html),
            "--approved-by", "user",
            "--evidence-reference", "user said render it",
        )

        self.assertEqual(render_approval.returncode, 0, render_approval.stderr)
        render_receipt = json.loads(
            (self.package / "MP4_RENDER_APPROVAL.json").read_text(encoding="utf-8")
        )
        self.assertEqual(render_receipt["html_sha256"], approval["html_sha256"])
        self.assertEqual(
            render_receipt["html_approval_sha256"],
            hashlib.sha256((self.package / "HTML_APPROVAL.json").read_bytes()).hexdigest(),
        )
        status = (self.package / "STATUS.md").read_text(encoding="utf-8")
        log = (self.package / "APPROVAL_LOG.md").read_text(encoding="utf-8")
        self.assertIn("mp4_allowed: true", status)
        self.assertIn("approved_scope: MP4 render approved", log)
        self.assertNotIn("not_approved: MP4 render pending", log)

    def test_render_approval_command_cannot_replace_missing_html_approval(self):
        html, _, _ = self.prepare_html_review_fixture()

        result = self.run_command(
            "render-approval-record",
            "--package", str(self.package),
            "--html", str(html),
            "--approved-by", "user",
            "--evidence-reference", "user said render it",
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("CURRENT_HTML_APPROVAL_MISSING", result.stderr)
        self.assertFalse((self.package / "MP4_RENDER_APPROVAL.json").exists())

    def test_render_review_receipt_binds_the_mp4_post_qa_report_and_representative_frames(self):
        mp4 = self.package / "fixture_upload_10mbps.mp4"
        sync = self.package / "sync_manifest.json"
        report_dir = self.package / "_work" / "render_post_qa_fixture"
        frame = report_dir / "representative_frames" / "01_hook.jpg"
        report = report_dir / "render_post_qa_report.json"
        frame.parent.mkdir(parents=True)
        mp4.write_bytes(b"mp4")
        sync.write_text('{"ok":true}', encoding="utf-8")
        frame.write_bytes(b"frame")
        report.write_text(
            json.dumps(
                {
                    "auto_status": "pass",
                    "mp4_relative_path": mp4.relative_to(self.package).as_posix(),
                    "mp4_bytes": mp4.stat().st_size,
                    "mp4_sha256": hashlib.sha256(mp4.read_bytes()).hexdigest(),
                    "sync_manifest_relative_path": sync.relative_to(self.package).as_posix(),
                    "sync_manifest_bytes": sync.stat().st_size,
                    "sync_manifest_sha256": hashlib.sha256(sync.read_bytes()).hexdigest(),
                    "representative_frames": [{"path": str(frame)}],
                }
            ),
            encoding="utf-8",
        )

        result = self.run_command(
            "render-review-record",
            "--package", str(self.package),
            "--mp4", str(mp4),
            "--post-qa-report", str(report),
            "--reviewer", "fixture-worker",
            "--evidence-reference", "fixture-task",
            *sum((["--check", value] for value in (
                "caption_layout_reviewed", "privacy_reviewed", "review_capture_reviewed",
                "voice_caption_visual_sync_reviewed", "hook_and_cta_reviewed",
            )), []),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        receipt_path = next((self.package / "_work" / "manual_reviews").glob("render_review_*.json"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["review_kind"], "render")
        self.assertEqual(receipt["target"]["sha256"], hashlib.sha256(mp4.read_bytes()).hexdigest())
        self.assertEqual(len(receipt["qa_frames"]), 1)


if __name__ == "__main__":
    unittest.main()
