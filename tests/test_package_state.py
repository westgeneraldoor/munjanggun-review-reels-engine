import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from video_engine_v2.package_state import UNKNOWN, scan_legacy_output


class PackageStateTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.output_root = Path(self.tempdir.name) / "output"
        self.package = self.output_root / "inbox_20300102" / "001_demo_20300102_030405"
        self.package.mkdir(parents=True)

    def write(self, relative_path: str, content: str | bytes):
        path = self.package / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path

    def write_hash_bound_post_render_report(self, mp4: Path, **overrides):
        sync_manifest = self.write("sync_manifest.json", json.dumps({"ok": True, "fixture": "bound"}))
        report = {
            "schema_version": "1.2",
            "generated_at": "2030-01-02T03:04:05Z",
            "package_identity": {"package_path": str(self.package.resolve()), "package_name": self.package.name},
            "mp4_relative_path": mp4.relative_to(self.package).as_posix(),
            "mp4_bytes": mp4.stat().st_size,
            "mp4_sha256": hashlib.sha256(mp4.read_bytes()).hexdigest(),
            "sync_manifest_relative_path": sync_manifest.relative_to(self.package).as_posix(),
            "sync_manifest_bytes": sync_manifest.stat().st_size,
            "sync_manifest_sha256": hashlib.sha256(sync_manifest.read_bytes()).hexdigest(),
            "auto_status": "pass",
            "manual_review": {"status": "pending"},
        }
        report.update(overrides)
        return self.write("render_post_qa_report.json", json.dumps(report))

    def test_scanner_maps_retained_mp4_without_inventing_publication_or_qa(self):
        mp4 = self.write("001_demo_final_render_upload_10mbps.mp4", b"mp4-data")
        self.write("001_demo_v2_planning_recipe.json", "{}")
        self.write("001_demo_v2_edit_recipe.json", "{}")
        self.write("sync_manifest.json", json.dumps({"ok": True, "audio": {"final_voice_duration_sec": 31.2}}))
        self.write(
            "STATUS.md",
            "- photo_checked: true\n- pd_plan_approved: true\n- html_approved_by_user: true\n- mp4_allowed: true\n",
        )
        self.write(
            "APPROVAL_LOG.md",
            "- approved_scope: HTML preview approved\n- approved_scope: MP4 render approved\n",
        )
        before = self.package_snapshot()

        report = scan_legacy_output(self.output_root)

        self.assertEqual(self.package_snapshot(), before)
        self.assertEqual(report["summary"]["package_count"], 1)
        self.assertEqual(report["summary"]["distinct_review_count"], 1)
        self.assertEqual(report["summary"]["upload_mp4_package_count"], 1)
        self.assertEqual(report["summary"]["upload_mp4_artifact_count"], 1)
        self.assertEqual(report["summary"]["render_complete_true_count"], 0)
        self.assertEqual(report["summary"]["render_complete_unknown_count"], 1)
        self.assertEqual(report["summary"]["published_known_true_count"], 0)
        self.assertEqual(report["summary"]["published_known_false_count"], 0)
        self.assertEqual(report["summary"]["published_unknown_count"], 1)
        self.assertEqual(report["summary"]["performance_known_true_count"], 0)
        self.assertEqual(report["summary"]["performance_known_false_count"], 0)
        self.assertEqual(report["summary"]["performance_unknown_count"], 1)
        self.assertNotIn("published_count", report["summary"])
        self.assertNotIn("performance_observed_count", report["summary"])
        state = report["packages"][0]
        self.assertEqual(state["schema_version"], "1.0")
        self.assertEqual(state["review_id"], "001")
        self.assertEqual(state["format_version"], "v2")
        self.assertEqual(state["format_status"], "production")
        self.assertIs(state["render_artifact_present"], True)
        self.assertEqual(state["render_complete"], UNKNOWN)
        self.assertEqual(state["qa_reviewed"], UNKNOWN)
        self.assertEqual(state["published"], UNKNOWN)
        self.assertEqual(state["performance_observed"], UNKNOWN)
        self.assertIs(state["planning_approved"], True)
        self.assertIs(state["html_approved"], True)
        self.assertIs(state["mp4_render_approved"], True)
        self.assertIs(state["privacy_checked"], True)
        self.assertIs(state["sync_ok"], True)
        upload = next(artifact for artifact in state["artifacts"] if artifact["kind"] == "upload_mp4")
        self.assertEqual(upload["sha256"], hashlib.sha256(mp4.read_bytes()).hexdigest())
        self.assertEqual(upload["relative_path"], mp4.name)

    def test_scanner_marks_only_hash_bound_current_upload_mp4_as_render_complete(self):
        mp4 = self.write("001_demo_final_render_upload_10mbps.mp4", b"mp4-data")
        self.write_hash_bound_post_render_report(mp4)
        before = self.package_snapshot()

        report = scan_legacy_output(self.output_root)

        self.assertEqual(self.package_snapshot(), before)
        state = report["packages"][0]
        self.assertIs(state["post_render_qa_pass_evidence_present"], True)
        self.assertIs(state["render_complete"], True)
        self.assertEqual(state["render_evidence_limitations"], [])
        self.assertEqual(report["summary"]["post_render_qa_pass_evidence_package_count"], 1)
        self.assertEqual(report["summary"]["render_complete_true_count"], 1)
        self.assertEqual(report["summary"]["render_evidence_limitation_count"], 0)

    def test_scanner_rejects_hash_bound_report_without_sync_manifest_binding(self):
        mp4 = self.write("001_demo_final_render_upload_10mbps.mp4", b"mp4-data")
        self.write_hash_bound_post_render_report(
            mp4,
            sync_manifest_relative_path=None,
            sync_manifest_bytes=None,
            sync_manifest_sha256=None,
        )

        state = scan_legacy_output(self.output_root)["packages"][0]

        self.assertEqual(state["render_complete"], UNKNOWN)
        self.assertIn("post_render_qa_sync_manifest_binding_missing", state["render_evidence_limitations"])

    def test_scanner_rejects_hash_bound_report_when_current_sync_manifest_changes(self):
        mp4 = self.write("001_demo_final_render_upload_10mbps.mp4", b"mp4-data")
        self.write_hash_bound_post_render_report(mp4)
        self.write("sync_manifest.json", json.dumps({"ok": True, "fixture": "other"}))

        state = scan_legacy_output(self.output_root)["packages"][0]

        self.assertEqual(state["render_complete"], UNKNOWN)
        self.assertIn("post_render_qa_sync_manifest_hash_mismatch", state["render_evidence_limitations"])

    def test_scanner_rejects_post_render_pass_when_current_mp4_hash_differs(self):
        mp4 = self.write("001_demo_final_render_upload_10mbps.mp4", b"mp4-data")
        self.write_hash_bound_post_render_report(mp4, mp4_sha256="0" * 64)

        state = scan_legacy_output(self.output_root)["packages"][0]

        self.assertIs(state["post_render_qa_pass_evidence_present"], True)
        self.assertEqual(state["render_complete"], UNKNOWN)
        self.assertIn("post_render_qa_mp4_hash_mismatch", state["render_evidence_limitations"])

    def test_scanner_rejects_post_render_pass_when_current_mp4_bytes_differ(self):
        mp4 = self.write("001_demo_final_render_upload_10mbps.mp4", b"mp4-data")
        self.write_hash_bound_post_render_report(mp4, mp4_bytes=999)

        state = scan_legacy_output(self.output_root)["packages"][0]

        self.assertEqual(state["render_complete"], UNKNOWN)
        self.assertIn("post_render_qa_mp4_bytes_mismatch", state["render_evidence_limitations"])

    def test_scanner_rejects_post_render_pass_when_report_mp4_is_missing(self):
        mp4 = self.write("001_demo_final_render_upload_10mbps.mp4", b"mp4-data")
        self.write_hash_bound_post_render_report(mp4, mp4_relative_path="missing_upload_10mbps.mp4")

        state = scan_legacy_output(self.output_root)["packages"][0]

        self.assertEqual(state["render_complete"], UNKNOWN)
        self.assertIn("post_render_qa_mp4_missing", state["render_evidence_limitations"])

    def test_scanner_rejects_post_render_pass_when_report_points_outside_its_package(self):
        mp4 = self.write("001_demo_final_render_upload_10mbps.mp4", b"mp4-data")
        other = self.output_root / "manual" / "002_demo_20300102_030405"
        other.mkdir(parents=True)
        other_mp4 = other / "002_demo_final_render_upload_10mbps.mp4"
        other_mp4.write_bytes(b"other-mp4")
        self.write_hash_bound_post_render_report(
            mp4,
            mp4_relative_path="../manual/002_demo_20300102_030405/002_demo_final_render_upload_10mbps.mp4",
            mp4_bytes=other_mp4.stat().st_size,
            mp4_sha256=hashlib.sha256(other_mp4.read_bytes()).hexdigest(),
        )

        state = scan_legacy_output(self.output_root)["packages"][0]

        self.assertEqual(state["render_complete"], UNKNOWN)
        self.assertIn("post_render_qa_mp4_outside_package", state["render_evidence_limitations"])

    def test_scanner_rejects_post_render_pass_for_non_upload_mp4(self):
        mp4 = self.write("001_demo_rendered.mp4", b"mp4-data")
        self.write_hash_bound_post_render_report(mp4)

        state = scan_legacy_output(self.output_root)["packages"][0]

        self.assertEqual(state["render_complete"], UNKNOWN)
        self.assertIn("post_render_qa_mp4_not_upload_artifact", state["render_evidence_limitations"])

    def test_scanner_keeps_auto_status_fail_out_of_render_completion(self):
        mp4 = self.write("001_demo_final_render_upload_10mbps.mp4", b"mp4-data")
        self.write_hash_bound_post_render_report(mp4, auto_status="fail")

        state = scan_legacy_output(self.output_root)["packages"][0]

        self.assertEqual(state["post_render_qa_pass_evidence_present"], UNKNOWN)
        self.assertEqual(state["render_complete"], UNKNOWN)

    def test_scanner_classifies_hashless_legacy_pass_as_historical_evidence_only(self):
        self.write("001_demo_final_render_upload_10mbps.mp4", b"mp4-data")
        self.write("render_post_qa_report.json", json.dumps({"auto_status": "pass", "mp4_path": str(self.package / "001_demo_final_render_upload_10mbps.mp4")}))

        report = scan_legacy_output(self.output_root)
        state = report["packages"][0]

        self.assertIs(state["post_render_qa_pass_evidence_present"], True)
        self.assertEqual(state["render_complete"], UNKNOWN)
        self.assertIn("legacy_report_missing_mp4_hash", state["render_evidence_limitations"])
        self.assertEqual(report["summary"]["post_render_qa_pass_evidence_package_count"], 1)
        self.assertEqual(report["summary"]["render_complete_true_count"], 0)
        self.assertEqual(report["summary"]["render_evidence_limitation_count"], 1)

    def test_scanner_uses_only_the_exact_hash_bound_mp4_when_package_has_multiple_uploads(self):
        bound = self.write("001_demo_final_render_a_upload_10mbps.mp4", b"mp4-a")
        self.write("001_demo_final_render_b_upload_10mbps.mp4", b"mp4-b")
        self.write_hash_bound_post_render_report(bound)

        state = scan_legacy_output(self.output_root)["packages"][0]

        self.assertIs(state["render_complete"], True)
        self.assertEqual(state["render_complete_mp4_relative_path"], bound.name)

    def test_scanner_uses_unknown_when_no_retained_evidence_can_prove_a_state(self):
        self.write(".source", "reviews/inbox/review_002.txt")
        self.write("002_pending_script.md", "# pending")
        nested_numeric_dir = self.package / "_work" / "123"
        nested_numeric_dir.mkdir(parents=True)
        (nested_numeric_dir / ".source").write_text("temporary render artifact", encoding="utf-8")
        (nested_numeric_dir / "frame.jpg").write_bytes(b"frame")

        report = scan_legacy_output(self.output_root)

        self.assertEqual(report["summary"]["package_count"], 1)
        state = report["packages"][0]
        self.assertEqual(state["render_complete"], UNKNOWN)
        self.assertEqual(state["qa_reviewed"], UNKNOWN)
        self.assertEqual(state["published"], UNKNOWN)
        self.assertEqual(state["performance_observed"], UNKNOWN)
        self.assertEqual(state["planning_approved"], UNKNOWN)
        self.assertEqual(state["privacy_checked"], UNKNOWN)
        self.assertEqual(state["sync_ok"], UNKNOWN)

    def test_summary_keeps_known_false_and_unknown_publication_states_separate(self):
        self.write("STATUS.md", "- published: false\n- performance_observed: false\n")
        unknown_package = self.output_root / "manual" / "002_demo_20300102_030405"
        unknown_package.mkdir(parents=True)
        (unknown_package / ".source").write_text("reviews/inbox/review_002.txt", encoding="utf-8")

        summary = scan_legacy_output(self.output_root)["summary"]

        self.assertEqual(summary["package_count"], 2)
        self.assertEqual(summary["published_known_true_count"], 0)
        self.assertEqual(summary["published_known_false_count"], 1)
        self.assertEqual(summary["published_unknown_count"], 1)
        self.assertEqual(summary["performance_known_true_count"], 0)
        self.assertEqual(summary["performance_known_false_count"], 1)
        self.assertEqual(summary["performance_unknown_count"], 1)

    def test_summary_counts_multiple_upload_artifacts_once_per_package(self):
        self.write("001_demo_final_render_a_upload_10mbps.mp4", b"mp4-a")
        self.write("001_demo_final_render_b_upload_10mbps.mp4", b"mp4-b")
        self.write("001_demo_final_render_c_upload_10mbps.mp4", b"mp4-c")

        summary = scan_legacy_output(self.output_root)["summary"]

        self.assertEqual(summary["package_count"], 1)
        self.assertEqual(summary["upload_mp4_package_count"], 1)
        self.assertEqual(summary["upload_mp4_artifact_count"], 3)
        self.assertEqual(summary["render_complete_true_count"], 0)
        self.assertEqual(summary["render_complete_unknown_count"], 1)

    def test_explicit_approval_log_conflict_is_recorded_and_wins_over_status(self):
        self.write("001_demo_v3_edit_recipe.json", "{}")
        self.write("STATUS.md", "- html_approved_by_user: true\n- mp4_allowed: true\n")
        self.write(
            "APPROVAL_LOG.md",
            "- approved_scope: HTML preview approved\n- not_approved: MP4 render\n",
        )

        state = scan_legacy_output(self.output_root)["packages"][0]

        self.assertEqual(state["format_version"], "v3")
        self.assertEqual(state["format_status"], "experimental")
        self.assertIs(state["html_approved"], True)
        self.assertIs(state["mp4_render_approved"], False)
        conflict = next(item for item in state["conflicts"] if item["field"] == "mp4_render_approved")
        self.assertEqual(conflict["selected_evidence"], "APPROVAL_LOG.md")

    def test_run_ids_remain_distinct_when_legacy_package_names_repeat(self):
        self.write(".source", "reviews/inbox/review_001.txt")
        other_package = self.output_root / "manual" / self.package.name
        other_package.mkdir(parents=True)
        (other_package / ".source").write_text("reviews/manual/review_001.txt", encoding="utf-8")

        states = scan_legacy_output(self.output_root)["packages"]

        self.assertEqual(len(states), 2)
        self.assertEqual(len({state["run_id"] for state in states}), 2)

    def package_snapshot(self):
        return {
            path.relative_to(self.package).as_posix(): path.read_bytes()
            for path in sorted(self.package.rglob("*"))
            if path.is_file()
        }


if __name__ == "__main__":
    unittest.main()
