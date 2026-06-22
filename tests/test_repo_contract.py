import json
import subprocess
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

    def test_official_hyperframes_adoption_is_documented(self):
        plan_path = ROOT / "docs" / "hyperframes_official_adoption_plan_v1.md"
        adapter_path = ROOT / "scripts" / "recipe-to-hyperframes-pilot.mjs"
        render_gate_path = ROOT / "scripts" / "hyperframes-render-gate.mjs"
        post_render_qa_path = ROOT / "scripts" / "render-post-qa.mjs"
        agents_path = ROOT / "AGENTS.md"
        readme_path = ROOT / "README.md"
        render_qa_path = ROOT / "docs" / "render_qa_rules_v2.md"

        self.assertTrue(plan_path.exists(), "공식 HyperFrames 도입 계획 문서가 필요합니다.")
        self.assertTrue(adapter_path.exists(), "edit_recipe -> HyperFrames 파일럿 어댑터가 필요합니다.")
        self.assertTrue(render_gate_path.exists(), "공식 HyperFrames 렌더 승인 게이트가 필요합니다.")
        self.assertTrue(post_render_qa_path.exists(), "렌더 후 QA 증거 생성 스크립트가 필요합니다.")

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
        self.assertIn("Direct HyperFrames render is blocked", adapter)

        render_gate = render_gate_path.read_text(encoding="utf-8")
        self.assertIn("html_approved_by_user", render_gate)
        self.assertIn("mp4_allowed", render_gate)
        self.assertIn("sync_manifest.ok must be true", render_gate)
        self.assertIn("HYPERFRAMES_VERSION", render_gate)
        self.assertIn("positive approved_scope", render_gate)

        post_render_qa = post_render_qa_path.read_text(encoding="utf-8")
        self.assertIn("ffprobe", post_render_qa)
        self.assertIn("representative_frames", post_render_qa)
        self.assertIn("manual_review_required", post_render_qa)
        self.assertIn("upload_10mbps", post_render_qa)

        agents = agents_path.read_text(encoding="utf-8")
        self.assertIn("docs/hyperframes_official_adoption_plan_v1.md", agents)
        self.assertIn("recipe-to-hyperframes-pilot.mjs", agents)
        self.assertIn("scripts/render-post-qa.mjs", agents)

        readme = readme_path.read_text(encoding="utf-8")
        self.assertIn("official HyperFrames Studio pilot", readme)
        self.assertIn("docs/hyperframes_official_adoption_plan_v1.md", readme)
        self.assertIn("scripts/render-post-qa.mjs", readme)

        render_qa = render_qa_path.read_text(encoding="utf-8")
        self.assertIn("scripts/render-post-qa.mjs", render_qa)
        self.assertIn("overall_status: manual_review_required", render_qa)

    def test_content_operating_principles_are_linked_from_agents(self):
        principles_path = ROOT / "docs" / "munjanggun_content_operating_principles_v1.md"
        agents_path = ROOT / "AGENTS.md"

        self.assertTrue(principles_path.exists(), "문장군 콘텐츠 운영 원칙 문서가 필요합니다.")

        principles = principles_path.read_text(encoding="utf-8")
        self.assertIn("고객의 문제와 사건을 보여주는 콘텐츠", principles)
        self.assertIn("20점 미만 콘텐츠는 발행하지 않습니다", principles)

        agents = agents_path.read_text(encoding="utf-8")
        self.assertIn("docs/munjanggun_content_operating_principles_v1.md", agents)

    def test_git_does_not_track_customer_or_generated_assets(self):
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=True,
        )

        forbidden_prefixes = ("reviews/", "output/", "scratch/", ".codex_deps/", "node_modules/")
        forbidden_suffixes = (
            ".mp4",
            ".mov",
            ".avi",
            ".mkv",
            ".mp3",
            ".wav",
            ".m4a",
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".zip",
            ".7z",
            ".rar",
            ".ttf",
            ".otf",
        )
        tracked = [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]
        forbidden = [
            file_path
            for file_path in tracked
            if file_path != ".env.example"
            and (file_path.startswith(forbidden_prefixes) or file_path == ".env" or file_path.startswith(".env.") or file_path.lower().endswith(forbidden_suffixes))
        ]

        self.assertEqual(forbidden, [], "GitHub에 고객자료/산출물/미디어/폰트가 추적되면 안 됩니다.")

    def test_gitignore_keeps_customer_and_generated_assets_ignored(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        required_patterns = [
            ".env",
            "output/",
            "reviews/",
            "scratch/",
            "node_modules/",
            ".codex_deps/",
            "*.mp4",
            "*.mp3",
            "*.wav",
            "*.jpg",
            "*.jpeg",
            "*.png",
            "*.zip",
            "*.ttf",
            "*.otf",
        ]

        for pattern in required_patterns:
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, gitignore)


if __name__ == "__main__":
    unittest.main()
