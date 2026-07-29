import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from urllib.parse import quote

from video_engine_v2.production_gate import (
    FINAL_RENDER_PRESET,
    GateViolation,
    create_sync_manifest,
    validate_html_gate,
    validate_render_gate,
)


ROOT = Path(__file__).resolve().parents[1]


class ProductionGateTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(dir=ROOT, prefix=".test-production-gate-")
        self.addCleanup(self.assert_temporary_directory_removed, Path(self.tempdir.name))
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name) / "테스트 공백 경로"
        self.font_tempdir = tempfile.TemporaryDirectory(dir=ROOT, prefix=".test-font-")
        self.addCleanup(self.assert_temporary_directory_removed, Path(self.font_tempdir.name))
        self.addCleanup(self.font_tempdir.cleanup)
        self.engine_root = Path(self.font_tempdir.name)
        self.engine_font = self.engine_root / "fixture-font.ttf"
        self.engine_font.write_bytes(b"fixture-font")
        from video_engine_v2 import production_gate

        repository_patch = patch.object(production_gate, "REPOSITORY_ROOT", self.engine_root)
        font_patch = patch.object(production_gate, "ENGINE_FONT_PATH", self.engine_font)
        repository_patch.start()
        font_patch.start()
        self.addCleanup(font_patch.stop)
        self.addCleanup(repository_patch.stop)
        self.package = self.root / "output" / "inbox_20300102" / "001_demo_20300102_030405"
        self.package.mkdir(parents=True)
        self.planning = self.package / "001_demo_v2_planning_recipe.json"
        self.edit = self.package / "001_demo_v2_edit_recipe.json"
        self.privacy = self.package / "privacy_asset_manifest.json"
        self.privacy_report = self.package / "_work" / "privacy_sanitization_report.json"
        self.sync = self.package / "sync_manifest.json"
        self.html = self.package / "001_demo_v2_html_preview_v2" / "index.html"
        self.output = self.package / "001_demo_final_render_20300102_upload_10mbps.mp4"
        self.write_valid_package()

    def assert_temporary_directory_removed(self, path: Path):
        self.assertFalse(path.exists(), f"Temporary test directory was retained: {path}")

    def test_fixture_package_and_font_temporaries_share_the_repository_root(self):
        self.assertEqual(Path(self.tempdir.name).parent, ROOT)
        self.assertEqual(Path(self.font_tempdir.name).parent, ROOT)
        self.assertNotEqual(self.tempdir.name, self.font_tempdir.name)

    def write_valid_package(self):
        assets = self.package / "assets"
        assets.mkdir()
        asset = assets / "main.jpg"
        asset.write_bytes(b"asset")
        voice = self.package / "voice.mp3"
        voice.write_bytes(b"voice")
        self.planning.write_text(
            json.dumps(
                {
                    "analysis": {
                        "customer_problem": "설치 마감이 걱정됨",
                        "before_pain": "선택 기준이 복잡함",
                        "after_change": "깔끔한 설치를 확인함",
                        "customer_emotion": ["만족"],
                    },
                    "review_source": {
                        "text": "설치가 깔끔해서 만족합니다.",
                        "review_quote_for_proof": "설치가 깔끔해서 만족합니다",
                        "inferred_fields": [],
                        "unsupported_story_elements": [],
                    },
                    "hooks": [{"text": "비싼 중문이 좋은 중문은 아닙니다"}],
                    "selected_hook": {"text": "비싼 중문이 좋은 중문은 아닙니다"},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.edit.write_text(
            json.dumps(
                {
                    "title": "demo",
                    "source": {
                        "image_dir": "assets",
                        "voice": "voice.mp3",
                        "privacy_review": {"checked": True, "risk_items": [], "unresolved_risks": []},
                        "privacy_sanitization_report": "_work/privacy_sanitization_report.json",
                    },
                    "asset_roles": {"after_main": "main.jpg"},
                    "audio_plan": {
                        "sync_policy": {
                            "raw_tts_duration_sec": 4.0,
                            "final_voice_duration_sec": 4.0,
                            "render_duration_sec": 4.0,
                        }
                    },
                    "beats": [
                        {
                            "id": "b01",
                            "time": [0.0, 4.0],
                            "asset": "after_main",
                            "caption": "깔끔한 설치를 확인했습니다",
                            "narration_ref": "설치가 깔끔해서 만족했다는 리뷰입니다.",
                            "meaning_match": True,
                            "meaning_match_source": "planning_scene:s01",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.privacy.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "checked": True,
                    "checked_at": "2030-01-02T03:04:05Z",
                    "unresolved_risks": [],
                    "selected_assets": [
                        {
                            "relative_path": "assets/main.jpg",
                            "bytes": asset.stat().st_size,
                            "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
                        }
                    ],
                    "sanitization_report": "_work/privacy_sanitization_report.json",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.privacy_report.parent.mkdir(parents=True, exist_ok=True)
        self.privacy_report.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "checked": True,
                    "checked_at": "2030-01-02T03:04:05Z",
                    "unresolved_risks": [],
                    "inspection_categories": ["face", "vehicle_plate", "address", "family_photo"],
                    "checked_assets": [
                        {
                            "relative_path": "assets/main.jpg",
                            "bytes": asset.stat().st_size,
                            "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.package / "STATUS.md").write_text(
            "- photo_checked: true\n- pd_plan_approved: true\n- html_approved_by_user: true\n- mp4_allowed: true\n",
            encoding="utf-8",
        )
        (self.package / "APPROVAL_LOG.md").write_text(
            "- approved_scope: PD planning approved\n- approved_scope: HTML preview approved\n- approved_scope: MP4 render approved\n",
            encoding="utf-8",
        )

    def snapshot(self):
        return {
            path.relative_to(self.package).as_posix(): path.read_bytes()
            for path in self.package.rglob("*")
            if path.is_file()
        }

    def create_valid_sync(self):
        return create_sync_manifest(
            package_dir=self.package,
            planning_path=self.planning,
            edit_path=self.edit,
            privacy_manifest_path=self.privacy,
            sync_manifest_path=self.sync,
        )

    def write_bound_html_approval(
        self,
        *,
        approval_package: Path | None = None,
        include_hash: bool = True,
        font_path: Path | None = None,
        repository_root: Path | None = None,
    ):
        self.create_valid_sync()
        self.html.parent.mkdir()
        font_path = font_path or self.engine_font
        repository_root = repository_root or self.engine_root
        asset_urls = {
            "after_main": quote(Path(os.path.relpath(self.package / "assets" / "main.jpg", self.html.parent)).as_posix(), safe="/._-()"),
            "voice": quote(Path(os.path.relpath(self.package / "voice.mp3", self.html.parent)).as_posix(), safe="/._-()"),
            "font_body": quote(Path(os.path.relpath(font_path, self.html.parent)).as_posix(), safe="/._-()"),
        }
        self.html.write_text(f"<!doctype html><script>const assetUrls = {json.dumps(asset_urls)};</script>", encoding="utf-8")
        html_receipt = validate_html_gate(
            package_dir=self.package,
            planning_path=self.planning,
            edit_path=self.edit,
            privacy_manifest_path=self.privacy,
            sync_manifest_path=self.sync,
        )
        receipt_path = self.package / "_work" / "production_gates" / "html_gate_fixture.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(html_receipt), encoding="utf-8")
        identity_package = approval_package or self.package
        html_relative_path = self.html.relative_to(self.package).as_posix()
        html_hash = hashlib.sha256(self.html.read_bytes()).hexdigest()
        render_dependencies = [
            {
                "kind": "image",
                "scope": "package",
                "relative_path": "assets/main.jpg",
                "bytes": (self.package / "assets" / "main.jpg").stat().st_size,
                "sha256": hashlib.sha256((self.package / "assets" / "main.jpg").read_bytes()).hexdigest(),
            },
            {
                "kind": "voice",
                "scope": "package",
                "relative_path": "voice.mp3",
                "bytes": (self.package / "voice.mp3").stat().st_size,
                "sha256": hashlib.sha256((self.package / "voice.mp3").read_bytes()).hexdigest(),
            },
            {
                "kind": "font",
                "scope": "repository",
                "relative_path": font_path.relative_to(repository_root).as_posix(),
                "bytes": font_path.stat().st_size,
                "sha256": hashlib.sha256(font_path.read_bytes()).hexdigest(),
            },
        ]
        artifact = {
            "schema_version": "1.0",
            "package_identity": {"package_path": str(self.package), "package_name": self.package.name},
            "html_relative_path": html_relative_path,
            "html_sha256": html_hash,
            "html_gate_receipt_path": receipt_path.relative_to(self.package).as_posix(),
            "html_gate_receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            "render_dependencies": render_dependencies,
            "generated_at": "2030-01-02T03:05:05Z",
        }
        artifact_path = self.html.parent / "html_artifact_evidence.json"
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
        approval = {
            "schema_version": "1.0",
            "package_identity": {"package_path": str(identity_package), "package_name": identity_package.name},
            "html_relative_path": html_relative_path,
            "html_sha256": html_hash,
            "html_artifact_evidence_sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            "approved_by_user": True,
            "approved_at": "2030-01-02T03:06:05Z",
            "approval_evidence_reference": "fixture-user-approval",
        }
        if not include_hash:
            approval.pop("html_sha256")
        approval_path = self.package / "HTML_APPROVAL.json"
        approval_path.write_text(json.dumps(approval), encoding="utf-8")
        return artifact_path, approval_path

    def refresh_approval_artifact_hash(self, artifact_path: Path, approval_path: Path):
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        approval["html_artifact_evidence_sha256"] = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        approval_path.write_text(json.dumps(approval), encoding="utf-8")

    def render_dependencies(self):
        artifact_path = self.html.parent / "html_artifact_evidence.json"
        return json.loads(artifact_path.read_text(encoding="utf-8"))["render_dependencies"]

    def write_renderer_receipt(self, dependencies):
        self.html.parent.mkdir(exist_ok=True)
        self.html.write_text("<!doctype html>", encoding="utf-8")
        receipt_path = self.package / "_work" / "production_gates" / "render_gate_fixture.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(
                {
                    "action": "render",
                    "package_path": str(self.package),
                    "html_path": str(self.html),
                    "html_sha256": hashlib.sha256(self.html.read_bytes()).hexdigest(),
                    "output_path": str(self.output),
                    "preset": FINAL_RENDER_PRESET,
                    "render_dependencies": dependencies,
                    "issued_at": "2030-01-02T03:07:05+00:00",
                }
            ),
            encoding="utf-8",
        )
        return receipt_path

    def render_gate(self):
        return validate_render_gate(
            package_dir=self.package,
            html_path=self.html,
            output_path=self.output,
            sync_manifest_path=self.sync,
            privacy_manifest_path=self.privacy,
            preset=FINAL_RENDER_PRESET,
        )

    def assert_no_render_artifacts(self):
        self.assertFalse(self.output.exists())
        self.assertFalse((self.package / f"{self.output.stem}_frames").exists())

    def test_preflight_rejects_missing_planning_without_writing_sync_manifest(self):
        before = self.snapshot()
        with self.assertRaises(GateViolation) as raised:
            create_sync_manifest(
                package_dir=self.package,
                planning_path=self.package / "missing.json",
                edit_path=self.edit,
                privacy_manifest_path=self.privacy,
                sync_manifest_path=self.sync,
            )
        self.assertIn("PLANNING_MISSING", str(raised.exception))
        self.assertEqual(self.snapshot(), before)

    def test_preflight_rejects_missing_edit_pd_approval_and_privacy_evidence(self):
        before = self.snapshot()
        with self.assertRaises(GateViolation) as missing_edit:
            create_sync_manifest(
                package_dir=self.package,
                planning_path=self.planning,
                edit_path=self.package / "missing.json",
                privacy_manifest_path=self.privacy,
                sync_manifest_path=self.sync,
            )
        self.assertIn("EDIT_MISSING", str(missing_edit.exception))

        (self.package / "STATUS.md").write_text("- photo_checked: true\n", encoding="utf-8")
        with self.assertRaises(GateViolation) as missing_pd:
            create_sync_manifest(
                package_dir=self.package,
                planning_path=self.planning,
                edit_path=self.edit,
                privacy_manifest_path=self.privacy,
                sync_manifest_path=self.sync,
            )
        self.assertIn("PD_APPROVAL_MISSING", str(missing_pd.exception))

        (self.package / "STATUS.md").write_text(
            "- photo_checked: true\n- pd_plan_approved: true\n", encoding="utf-8"
        )
        self.privacy.unlink()
        with self.assertRaises(GateViolation) as missing_privacy:
            create_sync_manifest(
                package_dir=self.package,
                planning_path=self.planning,
                edit_path=self.edit,
                privacy_manifest_path=self.privacy,
                sync_manifest_path=self.sync,
            )
        self.assertIn("PRIVACY_EVIDENCE_MISSING", str(missing_privacy.exception))
        self.assertFalse(self.sync.exists())
        self.assertNotEqual(self.snapshot(), before)

    def test_preflight_rejects_assets_that_were_not_in_the_privacy_manifest(self):
        extra_asset = self.package / "assets" / "extra.jpg"
        extra_asset.write_bytes(b"unreviewed")
        edit = json.loads(self.edit.read_text(encoding="utf-8"))
        edit["asset_roles"]["extra"] = "extra.jpg"
        self.edit.write_text(json.dumps(edit, ensure_ascii=False), encoding="utf-8")

        with self.assertRaises(GateViolation) as raised:
            self.create_valid_sync()

        self.assertIn("PRIVACY_ASSET_SET_MISMATCH", str(raised.exception))
        self.assertFalse(self.sync.exists())

    def test_preflight_rejects_a_privacy_manifest_when_the_selected_asset_hash_changes(self):
        (self.package / "assets" / "main.jpg").write_bytes(b"changed after review")

        with self.assertRaises(GateViolation) as raised:
            self.create_valid_sync()

        self.assertIn("PRIVACY_ASSET_EVIDENCE_MISMATCH", str(raised.exception))
        self.assertFalse(self.sync.exists())

    def test_preflight_rejects_a_self_referential_privacy_manifest(self):
        manifest = json.loads(self.privacy.read_text(encoding="utf-8"))
        manifest["sanitization_report"] = self.privacy.name
        self.privacy.write_text(json.dumps(manifest), encoding="utf-8")

        with self.assertRaises(GateViolation) as raised:
            self.create_valid_sync()

        self.assertIn("PRIVACY_REPORT_SELF_REFERENCE", str(raised.exception))
        self.assertFalse(self.sync.exists())

    def test_preflight_rejects_missing_privacy_report_with_a_specific_code(self):
        manifest = json.loads(self.privacy.read_text(encoding="utf-8"))
        manifest["sanitization_report"] = "_work/missing_privacy_report.json"
        self.privacy.write_text(json.dumps(manifest), encoding="utf-8")

        with self.assertRaises(GateViolation) as raised:
            self.create_valid_sync()

        self.assertIn("PRIVACY_REPORT_MISSING", str(raised.exception))

    def test_preflight_rejects_an_empty_privacy_report(self):
        self.privacy_report.write_text("{}", encoding="utf-8")

        with self.assertRaises(GateViolation) as raised:
            self.create_valid_sync()

        self.assertIn("PRIVACY_REPORT_INVALID", str(raised.exception))

    def test_preflight_rejects_privacy_report_asset_hash_mismatch(self):
        report = json.loads(self.privacy_report.read_text(encoding="utf-8"))
        report["checked_assets"][0]["sha256"] = "0" * 64
        self.privacy_report.write_text(json.dumps(report), encoding="utf-8")

        with self.assertRaises(GateViolation) as raised:
            self.create_valid_sync()

        self.assertIn("PRIVACY_REPORT_ASSET_MISMATCH", str(raised.exception))

    def test_preflight_rejects_privacy_report_with_unresolved_risks(self):
        report = json.loads(self.privacy_report.read_text(encoding="utf-8"))
        report["unresolved_risks"] = ["face"]
        self.privacy_report.write_text(json.dumps(report), encoding="utf-8")

        with self.assertRaises(GateViolation) as raised:
            self.create_valid_sync()

        self.assertIn("PRIVACY_RISK_UNRESOLVED", str(raised.exception))

    def test_html_gate_rejects_missing_or_failed_sync_manifest_before_preview_creation(self):
        with self.assertRaises(GateViolation) as missing_sync:
            validate_html_gate(
                package_dir=self.package,
                planning_path=self.planning,
                edit_path=self.edit,
                privacy_manifest_path=self.privacy,
                sync_manifest_path=self.sync,
            )
        self.assertIn("SYNC_MANIFEST_MISSING", str(missing_sync.exception))
        self.assertFalse(self.html.parent.exists())

        self.sync.write_text("{\"ok\": false}", encoding="utf-8")
        with self.assertRaises(GateViolation) as failed_sync:
            validate_html_gate(
                package_dir=self.package,
                planning_path=self.planning,
                edit_path=self.edit,
                privacy_manifest_path=self.privacy,
                sync_manifest_path=self.sync,
            )
        self.assertIn("SYNC_MANIFEST_NOT_OK", str(failed_sync.exception))
        self.assertFalse(self.html.parent.exists())

    def test_render_gate_rejects_missing_html_or_mp4_approval_without_creating_output(self):
        self.create_valid_sync()
        self.html.parent.mkdir()
        self.html.write_text("<!doctype html>", encoding="utf-8")
        (self.package / "STATUS.md").write_text(
            "- photo_checked: true\n- pd_plan_approved: true\n- html_approved_by_user: false\n- mp4_allowed: true\n",
            encoding="utf-8",
        )
        with self.assertRaises(GateViolation) as missing_html_approval:
            validate_render_gate(
                package_dir=self.package,
                html_path=self.html,
                output_path=self.output,
                sync_manifest_path=self.sync,
                privacy_manifest_path=self.privacy,
                preset=FINAL_RENDER_PRESET,
            )
        self.assertIn("HTML_APPROVAL_MISSING", str(missing_html_approval.exception))
        self.assertFalse(self.output.exists())
        self.assertFalse((self.package / f"{self.output.stem}_frames").exists())

        (self.package / "STATUS.md").write_text(
            "- photo_checked: true\n- pd_plan_approved: true\n- html_approved_by_user: true\n- mp4_allowed: false\n",
            encoding="utf-8",
        )
        with self.assertRaises(GateViolation) as missing_mp4_approval:
            validate_render_gate(
                package_dir=self.package,
                html_path=self.html,
                output_path=self.output,
                sync_manifest_path=self.sync,
                privacy_manifest_path=self.privacy,
                preset=FINAL_RENDER_PRESET,
            )
        self.assertIn("MP4_APPROVAL_MISSING", str(missing_mp4_approval.exception))
        self.assertFalse(self.output.exists())

    def test_render_gate_rejects_external_path_wrong_preset_and_wrong_filename_before_frame_creation(self):
        self.create_valid_sync()
        self.html.parent.mkdir()
        self.html.write_text("<!doctype html>", encoding="utf-8")
        cases = [
            (self.root / "outside_upload_10mbps.mp4", FINAL_RENDER_PRESET, "OUTPUT_OUTSIDE_PACKAGE"),
            (self.package / "wrong-name.mp4", FINAL_RENDER_PRESET, "FINAL_FILENAME_INVALID"),
            (self.output, {**FINAL_RENDER_PRESET, "width": 720}, "FINAL_PRESET_INVALID"),
            (self.output, {**FINAL_RENDER_PRESET, "fps": 24}, "FINAL_PRESET_INVALID"),
        ]
        for output_path, preset, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(GateViolation) as raised:
                    validate_render_gate(
                        package_dir=self.package,
                        html_path=self.html,
                        output_path=output_path,
                        sync_manifest_path=self.sync,
                        privacy_manifest_path=self.privacy,
                        preset=preset,
                    )
                self.assertIn(expected_code, str(raised.exception))
                self.assertFalse(output_path.exists())
                self.assertFalse((self.package / f"{self.output.stem}_frames").exists())

    def test_render_gate_rejects_privacy_evidence_changed_after_preflight(self):
        self.write_bound_html_approval()
        privacy = json.loads(self.privacy.read_text(encoding="utf-8"))
        privacy["checked_at"] = "2030-01-02T04:04:05Z"
        self.privacy.write_text(json.dumps(privacy, ensure_ascii=False), encoding="utf-8")

        with self.assertRaises(GateViolation) as raised:
            validate_render_gate(
                package_dir=self.package,
                html_path=self.html,
                output_path=self.output,
                sync_manifest_path=self.sync,
                privacy_manifest_path=self.privacy,
                preset=FINAL_RENDER_PRESET,
            )

        self.assertIn("SYNC_MANIFEST_STALE_OR_UNVERIFIED", str(raised.exception))
        self.assertFalse(self.output.exists())

    def test_render_gate_accepts_exactly_bound_html_approval(self):
        _, approval_path = self.write_bound_html_approval()

        receipt = self.render_gate()

        self.assertEqual(receipt["html_sha256"], hashlib.sha256(self.html.read_bytes()).hexdigest())
        self.assertEqual(receipt["html_approval_path"], str(approval_path.resolve()))

    def test_render_gate_accepts_the_same_package_identity_with_a_different_path_spelling(self):
        artifact_path, approval_path = self.write_bound_html_approval()
        same_package_with_dot_segment = os.path.join(str(self.package.parent), ".", self.package.name)
        self.assertNotEqual(same_package_with_dot_segment, str(self.package.resolve()))
        self.assertTrue(os.path.samefile(same_package_with_dot_segment, self.package))
        for path in (artifact_path, approval_path):
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["package_identity"]["package_path"] = same_package_with_dot_segment
            path.write_text(json.dumps(payload), encoding="utf-8")
        self.refresh_approval_artifact_hash(artifact_path, approval_path)

        receipt = self.render_gate()

        self.assertEqual(receipt["html_sha256"], hashlib.sha256(self.html.read_bytes()).hexdigest())
        self.assertEqual(
            {(item["kind"], item["scope"], item["relative_path"]) for item in receipt.get("render_dependencies", [])},
            {
                ("image", "package", "assets/main.jpg"),
                ("voice", "package", "voice.mp3"),
                ("font", "repository", "fixture-font.ttf"),
            },
        )
        self.assert_no_render_artifacts()

    def test_sync_manifest_binds_current_voice_bytes_and_hash(self):
        self.create_valid_sync()

        manifest = json.loads(self.sync.read_text(encoding="utf-8"))
        voice = manifest["gate_inputs"].get("voice")

        self.assertEqual(
            voice,
            {
                "kind": "voice",
                "scope": "package",
                "relative_path": "voice.mp3",
                "bytes": 5,
                "sha256": hashlib.sha256(b"voice").hexdigest(),
            },
        )

    def test_sync_manifest_rejects_same_size_voice_replacement(self):
        self.create_valid_sync()
        (self.package / "voice.mp3").write_bytes(b"other")

        with self.assertRaises(GateViolation) as raised:
            validate_html_gate(
                package_dir=self.package,
                planning_path=self.planning,
                edit_path=self.edit,
                privacy_manifest_path=self.privacy,
                sync_manifest_path=self.sync,
            )

        self.assertIn("SYNC_MANIFEST_STALE_OR_UNVERIFIED", str(raised.exception))
        self.assertFalse(self.html.parent.exists())

    def test_render_gate_rejects_same_size_voice_replacement_after_html_approval(self):
        self.write_bound_html_approval()
        (self.package / "voice.mp3").write_bytes(b"other")

        with self.assertRaises(GateViolation) as raised:
            self.render_gate()

        self.assertIn("SYNC_MANIFEST_STALE_OR_UNVERIFIED", str(raised.exception))
        self.assert_no_render_artifacts()

    def test_render_gate_rejects_missing_dependency_evidence(self):
        artifact_path, approval_path = self.write_bound_html_approval()
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        artifact["render_dependencies"] = artifact["render_dependencies"][:-1]
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
        self.refresh_approval_artifact_hash(artifact_path, approval_path)

        with self.assertRaises(GateViolation) as raised:
            self.render_gate()

        self.assertIn("RENDER_DEPENDENCY", str(raised.exception))
        self.assert_no_render_artifacts()

    def test_render_gate_rejects_duplicate_dependency_evidence(self):
        artifact_path, approval_path = self.write_bound_html_approval()
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        artifact["render_dependencies"].append(dict(artifact["render_dependencies"][0]))
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
        self.refresh_approval_artifact_hash(artifact_path, approval_path)

        with self.assertRaises(GateViolation) as raised:
            self.render_gate()

        self.assertIn("RENDER_DEPENDENCY", str(raised.exception))
        self.assert_no_render_artifacts()

    def test_render_gate_rejects_dependency_package_escape(self):
        artifact_path, approval_path = self.write_bound_html_approval()
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        artifact["render_dependencies"][1]["relative_path"] = "../outside.mp3"
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
        self.refresh_approval_artifact_hash(artifact_path, approval_path)

        with self.assertRaises(GateViolation) as raised:
            self.render_gate()

        self.assertIn("RENDER_DEPENDENCY", str(raised.exception))
        self.assert_no_render_artifacts()

    def test_render_gate_rejects_dependency_repository_escape(self):
        artifact_path, approval_path = self.write_bound_html_approval()
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        artifact["render_dependencies"][2]["relative_path"] = "../outside.ttf"
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
        self.refresh_approval_artifact_hash(artifact_path, approval_path)

        with self.assertRaises(GateViolation) as raised:
            self.render_gate()

        self.assertIn("RENDER_DEPENDENCY", str(raised.exception))
        self.assert_no_render_artifacts()

    def test_render_gate_rejects_tampered_font_dependency_hash(self):
        artifact_path, approval_path = self.write_bound_html_approval()
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        artifact["render_dependencies"][2]["sha256"] = "0" * 64
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
        self.refresh_approval_artifact_hash(artifact_path, approval_path)

        with self.assertRaises(GateViolation) as raised:
            self.render_gate()

        self.assertIn("RENDER_DEPENDENCY_MISMATCH", str(raised.exception))
        self.assert_no_render_artifacts()

    def test_render_gate_rejects_font_changed_after_html_approval(self):
        self.engine_font.write_bytes(b"font-a")
        self.write_bound_html_approval()
        self.engine_font.write_bytes(b"font-b")

        with self.assertRaises(GateViolation) as raised:
            self.render_gate()

        self.assertIn("RENDER_DEPENDENCY_MISMATCH", str(raised.exception))
        self.assert_no_render_artifacts()

    def test_render_gate_rejects_html_changed_after_bound_approval_before_render_artifacts(self):
        self.write_bound_html_approval()
        self.html.write_text("<!doctype html><title>changed</title>", encoding="utf-8")

        with self.assertRaises(GateViolation) as raised:
            self.render_gate()

        self.assertIn("HTML_HASH_MISMATCH", str(raised.exception))
        self.assert_no_render_artifacts()

    def test_render_gate_rejects_same_path_html_replacement_before_render_artifacts(self):
        self.write_bound_html_approval()
        self.html.write_text("<!doctype html><title>replacement</title>", encoding="utf-8")

        with self.assertRaises(GateViolation) as raised:
            self.render_gate()

        self.assertIn("HTML_HASH_MISMATCH", str(raised.exception))
        self.assert_no_render_artifacts()

    def test_render_gate_rejects_html_approval_evidence_without_hash(self):
        self.write_bound_html_approval(include_hash=False)

        with self.assertRaises(GateViolation) as raised:
            self.render_gate()

        self.assertIn("HTML_APPROVAL_EVIDENCE_INVALID", str(raised.exception))
        self.assert_no_render_artifacts()

    def test_render_gate_rejects_html_approval_evidence_from_another_package(self):
        other_package = self.root / "output" / "other" / self.package.name
        other_package.mkdir(parents=True)
        self.write_bound_html_approval(approval_package=other_package)

        with self.assertRaises(GateViolation) as raised:
            self.render_gate()

        self.assertIn("HTML_APPROVAL_PACKAGE_MISMATCH", str(raised.exception))
        self.assert_no_render_artifacts()

    def test_render_gate_rechecks_privacy_asset_hash_immediately_before_render(self):
        self.write_bound_html_approval()
        (self.package / "assets" / "main.jpg").write_bytes(b"changed after approval")

        with self.assertRaises(GateViolation) as raised:
            self.render_gate()

        self.assertIn("PRIVACY_ASSET_EVIDENCE_MISMATCH", str(raised.exception))
        self.assert_no_render_artifacts()

    def test_official_render_command_returns_nonzero_before_writing_for_missing_sync_manifest(self):
        self.html.parent.mkdir()
        self.html.write_text("<!doctype html>", encoding="utf-8")
        command = [
            sys.executable,
            "scripts/produce_review_v2.py",
            "render",
            "--package",
            str(self.package),
            "--html",
            str(self.html),
            "--sync-manifest",
            str(self.sync),
            "--privacy-manifest",
            str(self.privacy),
            "--out",
            str(self.output),
        ]
        result = subprocess.run(
            command, cwd=Path(__file__).parents[1], capture_output=True, text=True, encoding="utf-8", errors="strict"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())
        self.assertFalse((self.package / f"{self.output.stem}_frames").exists())

    def test_internal_builder_and_renderer_require_a_gate_receipt_before_creating_artifacts(self):
        environment = os.environ.copy()
        environment.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        builder = subprocess.run(
            [sys.executable, "build_html_preview_v2.py", "--recipe", str(self.edit)],
            cwd=Path(__file__).parents[1],
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )
        self.assertNotEqual(builder.returncode, 0)
        self.assertIn("--gate-receipt", builder.stderr)
        self.assertFalse(self.html.parent.exists())

        self.html.parent.mkdir()
        self.html.write_text("<!doctype html>", encoding="utf-8")
        renderer = subprocess.run(
            ["node", "render_html_preview_v2.js", "--html", str(self.html), "--out", str(self.output)],
            cwd=Path(__file__).parents[1],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )
        self.assertNotEqual(renderer.returncode, 0)
        self.assertIn("Missing --gate-receipt", renderer.stderr)
        self.assertFalse(self.output.exists())
        self.assertFalse((self.package / f"{self.output.stem}_frames").exists())

    def test_internal_renderer_rejects_a_stale_html_hash_before_output_creation(self):
        self.html.parent.mkdir()
        self.html.write_text("<!doctype html>", encoding="utf-8")
        receipt_path = self.package / "_work" / "production_gates" / "stale_html_render_gate.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(
                {
                    "action": "render",
                    "package_path": str(self.package),
                    "html_path": str(self.html),
                    "html_sha256": "0" * 64,
                    "output_path": str(self.output),
                    "preset": FINAL_RENDER_PRESET,
                    "issued_at": "2030-01-02T03:07:05+00:00",
                }
            ),
            encoding="utf-8",
        )

        renderer = subprocess.run(
            [
                "node",
                "render_html_preview_v2.js",
                "--html",
                str(self.html),
                "--out",
                str(self.output),
                "--gate-receipt",
                str(receipt_path),
                "--width",
                "720",
            ],
            cwd=Path(__file__).parents[1],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )

        self.assertNotEqual(renderer.returncode, 0)
        self.assertIn("HTML hash", renderer.stderr)
        self.assert_no_render_artifacts()

    def test_internal_renderer_rejects_stale_voice_before_frame_creation(self):
        self.write_bound_html_approval()
        receipt_path = self.write_renderer_receipt(self.render_dependencies())
        (self.package / "voice.mp3").write_bytes(b"other")

        renderer = subprocess.run(
            [
                "node",
                "render_html_preview_v2.js",
                "--html",
                str(self.html),
                "--out",
                str(self.output),
                "--gate-receipt",
                str(receipt_path),
                "--width",
                "720",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )

        self.assertNotEqual(renderer.returncode, 0)
        self.assertIn("dependency", renderer.stderr.lower())
        self.assert_no_render_artifacts()

    def test_internal_renderer_rejects_stale_font_before_frame_creation(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix=".d1-font-") as temp_dir:
            font_path = Path(temp_dir) / "fixture-font.ttf"
            font_path.write_bytes(b"font-a")
            self.html.parent.mkdir()
            dependencies = [
                {
                    "kind": "image",
                    "scope": "package",
                    "relative_path": "assets/main.jpg",
                    "bytes": 5,
                    "sha256": hashlib.sha256(b"asset").hexdigest(),
                },
                {
                    "kind": "voice",
                    "scope": "package",
                    "relative_path": "voice.mp3",
                    "bytes": 5,
                    "sha256": hashlib.sha256(b"voice").hexdigest(),
                },
                {
                    "kind": "font",
                    "scope": "repository",
                    "relative_path": font_path.relative_to(ROOT).as_posix(),
                    "bytes": 6,
                    "sha256": hashlib.sha256(b"font-a").hexdigest(),
                },
            ]
            receipt_path = self.write_renderer_receipt(dependencies)
            font_path.write_bytes(b"font-b")

            renderer = subprocess.run(
                [
                    "node",
                    "render_html_preview_v2.js",
                    "--html",
                    str(self.html),
                    "--out",
                    str(self.output),
                    "--gate-receipt",
                    str(receipt_path),
                    "--width",
                    "720",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
            )

        self.assertNotEqual(renderer.returncode, 0)
        self.assertIn("dependency", renderer.stderr.lower())
        self.assert_no_render_artifacts()

    def test_official_preflight_then_html_creates_a_preview_after_the_gate_passes(self):
        environment = os.environ.copy()
        environment.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        preflight = subprocess.run(
            [
                sys.executable,
                "scripts/produce_review_v2.py",
                "preflight",
                "--package",
                str(self.package),
                "--planning",
                str(self.planning),
                "--edit",
                str(self.edit),
                "--privacy-manifest",
                str(self.privacy),
                "--sync-manifest",
                str(self.sync),
            ],
            cwd=Path(__file__).parents[1],
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )
        self.assertEqual(preflight.returncode, 0, preflight.stderr)
        self.assertTrue(self.sync.exists())

        html = subprocess.run(
            [
                sys.executable,
                "scripts/produce_review_v2.py",
                "html",
                "--package",
                str(self.package),
                "--planning",
                str(self.planning),
                "--edit",
                str(self.edit),
                "--privacy-manifest",
                str(self.privacy),
                "--sync-manifest",
                str(self.sync),
                "--engine-font",
                self.engine_font.relative_to(ROOT).as_posix(),
            ],
            cwd=Path(__file__).parents[1],
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )
        self.assertEqual(html.returncode, 0, html.stderr)
        self.assertTrue(self.html.exists())
        self.assertTrue(list((self.package / "_work" / "production_gates").glob("html_*.json")))
        artifact_path = self.html.parent / "html_artifact_evidence.json"
        self.assertTrue(artifact_path.is_file())
        self.assertEqual(
            json.loads(artifact_path.read_text(encoding="utf-8"))["html_sha256"],
            hashlib.sha256(self.html.read_bytes()).hexdigest(),
        )

    def test_official_preflight_prints_korean_path_when_parent_stdout_is_cp1252(self):
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "cp1252"
        result = subprocess.run(
            [
                sys.executable,
                "scripts/produce_review_v2.py",
                "preflight",
                "--package",
                str(self.package),
                "--planning",
                str(self.planning),
                "--edit",
                str(self.edit),
                "--privacy-manifest",
                str(self.privacy),
                "--sync-manifest",
                str(self.sync),
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("테스트 공백 경로", result.stdout)

    def test_production_default_font_name_remains_nelnasamchae(self):
        from video_engine_v2 import production_gate

        self.assertEqual(production_gate.DEFAULT_ENGINE_FONT_RELATIVE_PATH, "nelnasamchae.ttf")
        self.assertEqual(production_gate.ENGINE_FONT_PATH, self.engine_font)

    def test_internal_builder_refuses_to_overwrite_an_existing_preview(self):
        self.create_valid_sync()
        receipt = validate_html_gate(
            package_dir=self.package,
            planning_path=self.planning,
            edit_path=self.edit,
            privacy_manifest_path=self.privacy,
            sync_manifest_path=self.sync,
        )
        receipt_path = self.package / "_work" / "production_gates" / "html_gate_fixture.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps({**receipt, "issued_at": "2030-01-02T03:07:05+00:00"}),
            encoding="utf-8",
        )
        self.html.parent.mkdir()
        self.html.write_text("preserve this preview", encoding="utf-8")
        environment = os.environ.copy()
        environment.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})

        result = subprocess.run(
            [
                sys.executable,
                "build_html_preview_v2.py",
                "--recipe",
                str(self.edit),
                "--gate-receipt",
                str(receipt_path),
            ],
            cwd=Path(__file__).parents[1],
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.html.read_text(encoding="utf-8"), "preserve this preview")

    def test_html_receipt_outside_official_directory_is_rejected(self):
        from video_engine_v2.production_gate import validate_html_receipt

        self.create_valid_sync()
        receipt = validate_html_gate(
            package_dir=self.package,
            planning_path=self.planning,
            edit_path=self.edit,
            privacy_manifest_path=self.privacy,
            sync_manifest_path=self.sync,
        )
        receipt_path = self.package / "copied_html_gate_receipt.json"
        receipt_path.write_text(
            json.dumps({**receipt, "issued_at": "2030-01-02T03:07:05+00:00"}),
            encoding="utf-8",
        )

        with self.assertRaises(GateViolation) as raised:
            validate_html_receipt(receipt_path, self.edit)

        self.assertIn("GATE_RECEIPT_OUTSIDE_OFFICIAL_DIR", str(raised.exception))

    def test_python_gate_receipt_consumption_is_hash_bound_and_single_use(self):
        from video_engine_v2 import production_gate

        consume = getattr(production_gate, "consume_gate_receipt", None)
        self.assertIsNotNone(consume, "production receipts need an atomic consumption boundary")
        self.create_valid_sync()
        receipt = validate_html_gate(
            package_dir=self.package,
            planning_path=self.planning,
            edit_path=self.edit,
            privacy_manifest_path=self.privacy,
            sync_manifest_path=self.sync,
        )
        receipt_path = production_gate.write_gate_receipt(self.package, receipt)

        marker_path = consume(receipt_path, self.package, expected_action="html")
        copied_path = receipt_path.with_name("copied_" + receipt_path.name)
        copied_path.write_bytes(receipt_path.read_bytes())

        self.assertTrue(marker_path.is_file())
        with self.assertRaises(GateViolation) as raised:
            consume(copied_path, self.package, expected_action="html")
        self.assertIn("GATE_RECEIPT_ALREADY_CONSUMED", str(raised.exception))

    def test_internal_builder_rejects_an_already_consumed_receipt_before_preview_creation(self):
        from video_engine_v2 import production_gate

        consume = getattr(production_gate, "consume_gate_receipt", None)
        self.assertIsNotNone(consume, "production receipts need an atomic consumption boundary")
        self.create_valid_sync()
        receipt = validate_html_gate(
            package_dir=self.package,
            planning_path=self.planning,
            edit_path=self.edit,
            privacy_manifest_path=self.privacy,
            sync_manifest_path=self.sync,
        )
        receipt_path = production_gate.write_gate_receipt(self.package, receipt)
        consume(receipt_path, self.package, expected_action="html")
        environment = os.environ.copy()
        environment.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})

        result = subprocess.run(
            [
                sys.executable,
                "build_html_preview_v2.py",
                "--recipe",
                str(self.edit),
                "--gate-receipt",
                str(receipt_path),
                "--engine-font",
                self.engine_font.relative_to(ROOT).as_posix(),
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GATE_RECEIPT_ALREADY_CONSUMED", result.stderr)
        self.assertFalse(self.html.parent.exists())

    def test_node_renderer_consumes_an_official_receipt_once(self):
        self.write_bound_html_approval()
        receipt_path = self.write_renderer_receipt(self.render_dependencies())
        node_script = (
            "const fs=require('fs');"
            "const gate=require('./render_html_preview_v2.js');"
            "const p=process.argv[1];"
            "gate.consumeGateReceipt(p,JSON.parse(fs.readFileSync(p,'utf8')));"
        )

        first = subprocess.run(
            ["node", "-e", node_script, str(receipt_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )
        second = subprocess.run(
            ["node", "-e", node_script, str(receipt_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("GATE_RECEIPT_ALREADY_CONSUMED", second.stderr)

    def test_internal_renderer_rejects_a_consumed_receipt_before_frame_creation(self):
        self.write_bound_html_approval()
        receipt_path = self.write_renderer_receipt(self.render_dependencies())
        receipt_hash = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        consumed_dir = receipt_path.parent / "consumed"
        consumed_dir.mkdir()
        (consumed_dir / f"{receipt_hash}.json").write_text("{}", encoding="utf-8")

        renderer = subprocess.run(
            [
                "node",
                "render_html_preview_v2.js",
                "--html",
                str(self.html),
                "--out",
                str(self.output),
                "--gate-receipt",
                str(receipt_path),
                "--width",
                "720",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )

        self.assertNotEqual(renderer.returncode, 0)
        self.assertIn("GATE_RECEIPT_ALREADY_CONSUMED", renderer.stderr)
        self.assert_no_render_artifacts()


if __name__ == "__main__":
    unittest.main()
