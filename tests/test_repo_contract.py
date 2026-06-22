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
            "총괄 PD 팀 운영 방식",
            "리뷰 각색 작가",
            "사진 큐레이터",
            "편집 설계자",
            "QA 감시자",
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
        self.assertEqual(scripts.get("test"), "node scripts/run-python-tests.cjs")
        self.assertEqual(scripts.get("validate"), "node scripts/run-python-tests.cjs")

    def test_python_test_runner_exists(self):
        runner_path = ROOT / "scripts" / "run-python-tests.cjs"

        self.assertTrue(runner_path.exists(), "npm validate용 Python 테스트 실행 래퍼가 필요합니다.")

        text = runner_path.read_text(encoding="utf-8")
        self.assertIn("unittest", text)
        self.assertIn("discover", text)

    def test_content_operating_principles_are_linked_from_agents(self):
        principles_path = ROOT / "docs" / "munjanggun_content_operating_principles_v1.md"
        agents_path = ROOT / "AGENTS.md"

        self.assertTrue(principles_path.exists(), "문장군 콘텐츠 운영 원칙 문서가 필요합니다.")

        principles = principles_path.read_text(encoding="utf-8")
        self.assertIn("고객의 문제와 사건을 보여주는 콘텐츠", principles)
        self.assertIn("20점 미만 콘텐츠는 발행하지 않습니다", principles)

        agents = agents_path.read_text(encoding="utf-8")
        self.assertIn("docs/munjanggun_content_operating_principles_v1.md", agents)


if __name__ == "__main__":
    unittest.main()
