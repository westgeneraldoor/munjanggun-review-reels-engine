import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepoContractTest(unittest.TestCase):
    def test_agents_md_exists_with_reels_hard_gates(self):
        agents_path = ROOT / "AGENTS.md"

        self.assertTrue(agents_path.exists(), "루트 AGENTS.md가 필요합니다.")

        text = agents_path.read_text(encoding="utf-8")
        required_phrases = [
            "reviews/",
            "output/",
            "사진검수 전 script/SRT/TTS/HTML 생성 금지",
            "review_quote_for_proof",
            "reels_qa",
            "HTML 승인 전 MP4 렌더 금지",
        ]
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_github_actions_validate_workflow_exists(self):
        workflow_path = ROOT / ".github" / "workflows" / "validate.yml"

        self.assertTrue(workflow_path.exists(), "GitHub Actions validate.yml이 필요합니다.")

        text = workflow_path.read_text(encoding="utf-8")
        self.assertIn("python -m unittest discover -s tests", text)
        self.assertIn("npm run validate", text)

    def test_package_json_exposes_test_and_validate_scripts(self):
        package_path = ROOT / "package.json"
        package = json.loads(package_path.read_text(encoding="utf-8"))

        scripts = package.get("scripts") or {}
        self.assertEqual(scripts.get("test"), "python -m unittest discover -s tests")
        self.assertEqual(scripts.get("validate"), "python -m unittest discover -s tests")


if __name__ == "__main__":
    unittest.main()
