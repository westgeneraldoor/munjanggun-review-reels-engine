import json
import hashlib
import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render-post-qa.mjs"


def good_ffprobe_payload():
    return {
        "format": {
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
            "duration": "25.493",
            "bit_rate": "11192000",
        },
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "pix_fmt": "yuv420p",
                        "width": 1080,
                        "height": 1920,
                "avg_frame_rate": "30/1",
                "bit_rate": "11000000",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "44100",
                "channels": 2,
                "bit_rate": "192000",
            },
        ],
    }


class RenderPostQaTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        temp_root = Path(self.tempdir.name) / "테스트 공백 경로"
        self.output_root = temp_root / "output"
        scratch_root = temp_root / "scratch"
        self.output_root.mkdir(parents=True)
        scratch_root.mkdir(parents=True)

        self.bin_dir = scratch_root / "bin"
        self.bin_dir.mkdir()
        self.write_fake_media_tools()

        self.package_dir = self.output_root / "review-package"
        self.package_dir.mkdir()
        self.mp4 = self.package_dir / "fixture_final_render_20260622_upload_10mbps.mp4"
        self.mp4.write_bytes(b"fake mp4")
        self.sync_manifest = self.package_dir / "sync_manifest.json"
        self.sync_manifest.write_text(
            json.dumps(
                {
                    "ok": True,
                    "issues": [],
                    "audio": {
                        "final_voice_duration_sec": 25.0,
                        "total_voice_cps": 7.0,
                    },
                    "scenes": [
                        {
                            "scene_id": "s01",
                            "meaning_match": True,
                            "meaning_match_evidence": "planning_scene:s01",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.report_dir = self.package_dir / "_work" / "render_post_qa_fixture"

    def write_fake_media_tools(self):
        ffprobe_js = self.bin_dir / "fake_ffprobe.cjs"
        ffprobe_js.write_text(
            textwrap.dedent(
                """
                const payload = process.env.FAKE_FFPROBE_JSON
                  ? JSON.parse(process.env.FAKE_FFPROBE_JSON)
                  : {
                      format: { format_name: 'mov,mp4', duration: '25.493', bit_rate: '11192000' },
                      streams: [
                        { codec_type: 'video', codec_name: 'h264', pix_fmt: 'yuv420p', width: 1080, height: 1920, avg_frame_rate: '30/1', bit_rate: '11000000' },
                        { codec_type: 'audio', codec_name: 'aac', sample_rate: '44100', channels: 2, bit_rate: '192000' },
                      ],
                    };
                process.stdout.write(JSON.stringify(payload));
                """
            ).strip(),
            encoding="utf-8",
        )
        ffmpeg_js = self.bin_dir / "fake_ffmpeg.cjs"
        ffmpeg_js.write_text(
            textwrap.dedent(
                """
                const fs = require('node:fs');
                const path = require('node:path');
                const out = process.argv.slice(2).reverse().find((arg) => /\\.(jpg|jpeg|png)$/i.test(String(arg).replace(/^['"]|['"]$/g, '')));
                if (!out) {
                  console.error(`No image output path found in args: ${process.argv.slice(2).join(' ')}`);
                  process.exit(2);
                }
                 const cleanOut = String(out).replace(/^['"]|['"]$/g, '');
                 fs.mkdirSync(path.dirname(cleanOut), { recursive: true });
                 fs.writeFileSync(cleanOut, 'fake frame');
                 if (process.env.FAKE_FFMPEG_MUTATE_MP4_PATH) {
                   fs.writeFileSync(process.env.FAKE_FFMPEG_MUTATE_MP4_PATH, 'changed after frame extraction');
                 }
                """
            ).strip(),
            encoding="utf-8",
        )

        for name, target in [("ffprobe", "fake_ffprobe.cjs"), ("ffmpeg", "fake_ffmpeg.cjs")]:
            shell_path = self.bin_dir / name
            shell_path.write_text(f"#!/usr/bin/env node\nrequire('./{target}');\n", encoding="utf-8")
            shell_path.chmod(shell_path.stat().st_mode | stat.S_IEXEC)
            cmd_path = self.bin_dir / f"{name}.cmd"
            cmd_path.write_text(f"@echo off\r\nnode \"%~dp0\\{target}\" %*\r\n", encoding="utf-8")

    def run_qa(
        self,
        *,
        ffprobe_payload=None,
        extra_args=None,
        extra_env=None,
        mp4=None,
        node_args=None,
        report_dir=None,
        sync_manifest=None,
    ):
        env = os.environ.copy()
        env["MUNJANGGUN_TEST_LOCAL_ROOT"] = str(self.output_root.parent)
        env["PATH"] = f"{self.bin_dir}{os.pathsep}{env.get('PATH', '')}"
        env["FFPROBE_BIN"] = "node"
        env["FFPROBE_ARGS_JSON"] = json.dumps([str(self.bin_dir / "fake_ffprobe.cjs")])
        env["FFMPEG_BIN"] = "node"
        env["FFMPEG_ARGS_JSON"] = json.dumps([str(self.bin_dir / "fake_ffmpeg.cjs")])
        if ffprobe_payload is not None:
            env["FAKE_FFPROBE_JSON"] = json.dumps(ffprobe_payload)
        if extra_env:
            env.update(extra_env)

        return subprocess.run(
            [
                "node",
                *(node_args or []),
                str(SCRIPT),
                "--mp4",
                str(mp4 or self.mp4),
                "--package",
                str(self.package_dir),
                "--sync-manifest",
                str(sync_manifest or self.sync_manifest),
                "--report-dir",
                str(report_dir or self.report_dir),
                *(extra_args or []),
            ],
            cwd=ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

    def test_generates_post_render_report_and_representative_frames(self):
        result = self.run_qa()

        self.assertEqual(result.returncode, 0, result.stderr)
        report_path = self.report_dir / "render_post_qa_report.json"
        markdown_path = self.report_dir / "render_post_qa_report.md"
        self.assertTrue(report_path.exists())
        self.assertTrue(markdown_path.exists())

        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["schema_version"], "1.2")
        self.assertEqual(report["package_identity"], {"package_path": str(self.package_dir.resolve()), "package_name": self.package_dir.name})
        self.assertEqual(report["mp4_relative_path"], self.mp4.name)
        self.assertEqual(report["mp4_bytes"], self.mp4.stat().st_size)
        self.assertEqual(report["mp4_sha256"], hashlib.sha256(self.mp4.read_bytes()).hexdigest())
        self.assertEqual(report["sync_manifest_relative_path"], "sync_manifest.json")
        self.assertEqual(report["sync_manifest_bytes"], self.sync_manifest.stat().st_size)
        self.assertEqual(report["sync_manifest_sha256"], hashlib.sha256(self.sync_manifest.read_bytes()).hexdigest())
        self.assertEqual(report["auto_status"], "pass")
        self.assertEqual(report["overall_status"], "manual_review_required")
        self.assertEqual(report["final_status"], "needs_human_review")
        self.assertEqual(report["manual_review"]["status"], "pending")
        self.assertEqual(len(report["representative_frames"]), 5)
        for frame in report["representative_frames"]:
            self.assertTrue(Path(frame["path"]).exists())

    def test_fails_when_mp4_changes_during_representative_frame_extraction(self):
        result = self.run_qa(extra_env={"FAKE_FFMPEG_MUTATE_MP4_PATH": str(self.mp4)})

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MP4 changed during representative frame extraction", result.stderr)
        self.assertFalse((self.report_dir / "render_post_qa_report.json").exists())

    def test_rejects_sync_manifest_bytes_that_differ_from_the_parsed_snapshot(self):
        valid_sync_text = self.sync_manifest.read_text(encoding="utf-8")
        stale_sync = json.loads(valid_sync_text)
        stale_sync["audio"]["total_voice_cps"] = 99.0
        self.sync_manifest.write_text(json.dumps(stale_sync), encoding="utf-8")
        preload = self.bin_dir / "swap_sync_read.cjs"
        preload.write_text(
            textwrap.dedent(
                """
                const fs = require('node:fs');
                const path = require('node:path');
                const originalReadFileSync = fs.readFileSync;
                const target = path.resolve(process.env.FAKE_SYNC_READ_TARGET);
                let targetReads = 0;
                fs.readFileSync = function(filePath, options) {
                  if (path.resolve(String(filePath)) === target) {
                    targetReads += 1;
                    if (targetReads > 1) {
                      const replacement = Buffer.from(process.env.FAKE_SYNC_SECOND_READ, 'utf8');
                      return typeof options === 'string' ? replacement.toString(options) : replacement;
                    }
                  }
                  return originalReadFileSync.apply(this, arguments);
                };
                """
            ).strip(),
            encoding="utf-8",
        )

        result = self.run_qa(
            node_args=["--require", str(preload)],
            extra_env={
                "FAKE_SYNC_READ_TARGET": str(self.sync_manifest),
                "FAKE_SYNC_SECOND_READ": valid_sync_text,
            },
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("total_voice_cps", result.stderr)
        self.assertFalse((self.report_dir / "render_post_qa_report.json").exists())

    def test_fails_on_wrong_render_spec_but_writes_report(self):
        payload = good_ffprobe_payload()
        payload["streams"][0]["width"] = 720

        result = self.run_qa(ffprobe_payload=payload)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("VIDEO_WIDTH", result.stderr)
        report = json.loads((self.report_dir / "render_post_qa_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["auto_status"], "fail")
        self.assertEqual(report["final_status"], "blocked")

    def test_rejects_report_dir_outside_package(self):
        outside_report_dir = self.output_root / "outside_report"

        result = self.run_qa(report_dir=outside_report_dir)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("inside the approved review package folder", result.stderr)
        self.assertFalse((outside_report_dir / "render_post_qa_report.json").exists())

    def test_rejects_non_upload_10mbps_filename(self):
        bad_mp4 = self.package_dir / "fixture_final_render.mp4"
        bad_mp4.write_bytes(b"fake mp4")

        result = self.run_qa(mp4=bad_mp4)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("upload_10mbps", result.stderr)

    def test_rejects_non_mp4_extension(self):
        bad_mp4 = self.package_dir / "fixture_upload_10mbps.mov"
        bad_mp4.write_bytes(b"fake mov")

        result = self.run_qa(mp4=bad_mp4)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must end with .mp4", result.stderr)

    def test_rejects_sync_manifest_not_ok(self):
        self.sync_manifest.write_text(
            json.dumps({"ok": False, "issues": [{"code": "fixture"}]}),
            encoding="utf-8",
        )

        result = self.run_qa()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sync_manifest.ok must be true", result.stderr)

    def test_rejects_sync_manifest_without_final_voice_duration(self):
        self.sync_manifest.write_text(
            json.dumps(
                {
                    "ok": True,
                    "issues": [],
                    "audio": {"total_voice_cps": 7.0},
                    "scenes": [{"meaning_match": True, "meaning_match_evidence": "planning_scene:s01"}],
                }
            ),
            encoding="utf-8",
        )

        result = self.run_qa()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("final_voice_duration_sec", result.stderr)

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

        result = self.run_qa()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("meaning_match evidence", result.stderr)

    def test_fails_on_wrong_video_codec(self):
        payload = good_ffprobe_payload()
        payload["streams"][0]["codec_name"] = "vp9"

        result = self.run_qa(ffprobe_payload=payload)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("VIDEO_CODEC", result.stderr)

    def test_fails_on_non_mp4_container(self):
        payload = good_ffprobe_payload()
        payload["format"]["format_name"] = "matroska,webm"

        result = self.run_qa(ffprobe_payload=payload)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MP4_CONTAINER", result.stderr)

    def test_fails_when_mp4_duration_is_too_long_for_voice(self):
        payload = good_ffprobe_payload()
        payload["format"]["duration"] = "60.000"

        result = self.run_qa(ffprobe_payload=payload)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("VOICE_DURATION_COMPATIBLE", result.stderr)


if __name__ == "__main__":
    unittest.main()
