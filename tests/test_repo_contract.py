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
        self.assertEqual(scripts.get("test"), "node scripts/run-python-tests.cjs")
        self.assertEqual(scripts.get("validate"), "node scripts/run-python-tests.cjs")

    def test_python_test_runner_exists(self):
        runner_path = ROOT / "scripts" / "run-python-tests.cjs"

        self.assertTrue(runner_path.exists(), "npm validate용 Python 테스트 실행 래퍼가 필요합니다.")

        text = runner_path.read_text(encoding="utf-8")
        self.assertIn("unittest", text)
        self.assertIn("discover", text)

    def test_official_hyperframes_adoption_is_documented(self):
        plan_path = ROOT / "docs" / "hyperframes_official_adoption_plan_v1.md"
        adapter_path = ROOT / "scripts" / "recipe-to-hyperframes-pilot.mjs"
        agents_path = ROOT / "AGENTS.md"
        readme_path = ROOT / "README.md"

        self.assertTrue(plan_path.exists(), "공식 HyperFrames 도입 계획 문서가 필요합니다.")
        self.assertTrue(adapter_path.exists(), "edit_recipe -> HyperFrames 파일럿 어댑터가 필요합니다.")

        plan = plan_path.read_text(encoding="utf-8")
        self.assertIn("Munjanggun engine = judgment and safety", plan)
        self.assertIn("HyperFrames = timeline UI", plan)
        self.assertIn("Never call the old local HTML preview \"official HyperFrames\"", plan)
        self.assertIn("Never call the Stage 1 adapter a production renderer", plan)
        self.assertIn("sync_manifest.ok: true", plan)

        adapter = adapter_path.read_text(encoding="utf-8")
        self.assertIn('HYPERFRAMES_VERSION = "0.6.121"', adapter)
        self.assertIn("validateApprovedRecipe", adapter)
        self.assertIn("data-composition-id", adapter)
        self.assertIn("npx --yes hyperframes", adapter)

        agents = agents_path.read_text(encoding="utf-8")
        self.assertIn("docs/hyperframes_official_adoption_plan_v1.md", agents)
        self.assertIn("recipe-to-hyperframes-pilot.mjs", agents)

        readme = readme_path.read_text(encoding="utf-8")
        self.assertIn("official HyperFrames Studio pilot", readme)
        self.assertIn("docs/hyperframes_official_adoption_plan_v1.md", readme)


if __name__ == "__main__":
    unittest.main()
