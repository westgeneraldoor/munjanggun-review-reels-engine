import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_DOCUMENTS = [
    "AGENTS.md",
    "README.md",
    "docs/brand/PROJECT_BRAND_ADAPTER.md",
    "docs/reels_operations_dashboard_v1.md",
    "docs/review_video_publish_workflow_v2.md",
    "docs/render_qa_rules_v2.md",
    "docs/reels_privacy_asset_qa_rules_v1.md",
    "docs/github_pr_workflow.md",
]


class AuthorityDocumentsTest(unittest.TestCase):
    def test_authority_documents_name_the_v2_orchestrator_and_not_direct_production_commands(self):
        for relative_path in AUTHORITY_DOCUMENTS:
            with self.subTest(relative_path=relative_path):
                text = (ROOT / relative_path).read_text(encoding="utf-8")
                self.assertIn("scripts/produce_review_v2.py", text)
                self.assertNotRegex(text, r"(?m)^python -m video_engine_v2\.reels_qa\b")
                self.assertNotRegex(text, r"(?m)^(?:node )?render_html_preview_v2\.js\b")

    def test_dashboard_uses_live_package_state_instead_of_manual_completion_totals(self):
        text = (ROOT / "docs/reels_operations_dashboard_v1.md").read_text(encoding="utf-8")

        self.assertIn("package_state.py", text)
        self.assertNotIn("현재 제작 완료 릴스 | 9개", text)
        self.assertNotIn("제작 완료 릴스 4개", text)
        self.assertNotIn("현재 전체 목록", text)

    def test_format_status_and_channel_boundary_remain_consistent(self):
        texts = {
            relative_path: (ROOT / relative_path).read_text(encoding="utf-8")
            for relative_path in ["AGENTS.md", "README.md", "docs/brand/PROJECT_BRAND_ADAPTER.md"]
        }

        for text in texts.values():
            self.assertIn("v2: current production", text)
            self.assertIn("v3: experimental", text)
            self.assertIn("v3.1: experimental", text)
        self.assertIn("Instagram과 Naver Clip", texts["AGENTS.md"])
        self.assertIn("HyperFrames", texts["README.md"])


if __name__ == "__main__":
    unittest.main()
