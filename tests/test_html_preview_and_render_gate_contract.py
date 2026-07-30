import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HtmlPreviewAndRenderGateContractTest(unittest.TestCase):
    def test_html_builder_requires_strict_preflight_with_a_planning_recipe(self):
        source = (ROOT / "build_html_preview_v2.py").read_text(encoding="utf-8")

        self.assertIn('parser.add_argument("--planning", required=True', source)
        self.assertIn("require_one_shot_contract=True", source)
        self.assertIn("HTML preflight failed", source)

    def test_legacy_html_renderer_is_a_non_destructive_approval_gate(self):
        source = (ROOT / "render_html_preview_v2.js").read_text(encoding="utf-8")

        self.assertIn("--package", source)
        self.assertIn("--sync-manifest", source)
        self.assertIn("--html-qa", source)
        self.assertIn("--render-approved", source)
        self.assertIn("html_approved_by_user", source)
        self.assertIn("mp4_allowed", source)
        self.assertIn("sync_manifest.ok must be true", source)
        self.assertNotIn("fs.rmSync", source)
        self.assertIn("fs.unlinkSync", source)

    def test_html_preview_qa_checks_representative_story_points(self):
        source = (ROOT / "scripts" / "html-preview-qa.mjs").read_text(encoding="utf-8")

        self.assertIn("first_hook", source)
        self.assertIn("review_proof", source)
        self.assertIn("final_cta", source)
        self.assertIn("review card appeared before its proof beat", source)
        self.assertIn("caption is clipped", source)

    def test_validation_runner_forces_utf8_and_rejects_hidden_thread_errors(self):
        source = (ROOT / "scripts" / "run-python-tests.cjs").read_text(encoding="utf-8")

        self.assertIn("PYTHONUTF8", source)
        self.assertIn("PYTHONIOENCODING", source)
        self.assertIn("UnicodeDecodeError", source)
        self.assertIn("Exception in thread", source)


if __name__ == "__main__":
    unittest.main()
