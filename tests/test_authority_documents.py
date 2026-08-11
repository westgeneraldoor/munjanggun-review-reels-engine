import re
import subprocess
import unittest
from pathlib import Path

from video_engine_v2.reels_qa import (
    HARD_CPS_LIMIT,
    MAX_VISUAL_LEAD_SEC,
    MIN_ONE_SHOT_CPS,
    SOFT_CPS_LIMIT,
)


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ENTRYPOINT_DOCUMENTS = [
    "AGENTS.md",
    "README.md",
    "docs/review_reel_production_routing_v1.md",
    "docs/brand/PROJECT_BRAND_ADAPTER.md",
    "docs/reels_operations_dashboard_v1.md",
    "docs/review_video_publish_workflow_v2.md",
    "docs/review_reels_content_standard_v1.md",
    "docs/review_reels_visual_edit_standard_v1.md",
    "docs/review_recipe_contract_v2.md",
    "docs/render_qa_rules_v2.md",
    "docs/reels_privacy_asset_qa_rules_v1.md",
    "docs/github_pr_workflow.md",
]

COMPACT_STANDARDS = {
    "docs/review_reels_content_standard_v1.md": [
        "review_source",
        "problem_solution",
        "writer brief",
        "호기심 결핍",
        "20~28초",
        "Sulafat",
        "D-024 TTS 속도 하드 게이트",
        "total_voice_cps",
        "scene_cps",
        "D-025 훅 압축 하드 게이트",
        "대상`, `상황`, `변화",
        "한 달 뒤, 진짜입니다",
        "HTML 검수 준비 완료",
    ],
    "docs/review_reels_visual_edit_standard_v1.md": [
        "같은 순간에",
        "1.03~1.08",
        "1.03~1.10",
        "-16 LUFS",
        "1080x1920",
        "D-026 장면 의미 일치 하드 게이트",
        "meaning_match: true",
        "meaning_match_source",
        "meaning_match_evidence",
    ],
    "docs/review_recipe_contract_v2.md": [
        "planning recipe",
        "edit recipe",
        "review-reels-one-shot-v2",
        "html_artifact_evidence.json",
        "render_post_qa_report.json",
        "1080x1920, 30fps",
        "customer_problem",
        "before_pain",
        "after_change",
        "customer_emotion",
        "top-level `hooks`",
        "privacy_review",
        "privacy_sanitization_report",
        "image_dir",
        "generated_asset",
        "generated_reason",
        "not_real_proof",
        "visual_claim",
        "literal_qa_result",
    ],
    "docs/reels_posting_copy_standard_v2.md": [
        "6~9줄",
        "20~25개",
        "#문장군",
        "#문장군중문",
        "#문장군시공",
        "## 캡션",
        "## 해시태그",
    ],
}

LEGACY_LIVE_DOCUMENT_NAMES = [
    "GEMINI.md",
    "PROJECT_DASHBOARD.md",
    "PROJECT_TASKS.md",
    "CONTENT_QUALITY_STANDARD.md",
    "STORY_EXTRACTION_RULES.md",
    "reels_writer_persona_v1.md",
    "reels_hook_formula_v1.md",
    "review_reels_gold_playbook_v1.md",
    "VIDEO_DIRECTION_V1.md",
    "VIDEO_DIRECTION_V2.md",
    "video_pd_standard_v2.md",
    "munjanggun_motion_rule_v1.md",
    "video_templates_v2.md",
    "VIDEO_RECIPE_SCHEMA_V2.md",
    "video_recipe_schema_v2.md",
    "POSTING_COPY_STANDARD.md",
    "instagram_caption_hashtag_rules_v2.md",
]

ARCHIVED_DOCUMENT_MOVES = {
    "PRD_v1.0.md": "docs/archive/plans/PRD_v1.0.md",
    "PROJECT_BRIEF.md": "docs/archive/plans/PROJECT_BRIEF.md",
    "PROJECT_TASKS.md": "docs/archive/plans/PROJECT_TASKS.md",
    "PROJECT_DASHBOARD.md": "docs/archive/plans/PROJECT_DASHBOARD_20260612.md",
    "VIDEO_DIRECTION_V1.md": "docs/archive/plans/VIDEO_DIRECTION_V1.md",
    "BRAND_CONTEXT.md": "docs/archive/brand/BRAND_CONTEXT_snapshot_20260508.md",
    "DECISION_LOG.md": "docs/archive/decisions/DECISION_LOG.md",
    "docs/brand/BRAND_SYNC_AUDIT_2026-07-28.md": "docs/archive/audits/BRAND_SYNC_AUDIT_2026-07-28.md",
    "docs/GPT 장면씬 정리.md": "docs/archive/plans/GPT 장면씬 정리.md",
    "docs/video_engine_v2_design.md": "docs/archive/plans/video_engine_v2_design.md",
    "CONTENT_QUALITY_STANDARD.md": "docs/archive/standards/content/CONTENT_QUALITY_STANDARD.md",
    "STORY_EXTRACTION_RULES.md": "docs/archive/standards/content/STORY_EXTRACTION_RULES.md",
    "docs/reels_writer_persona_v1.md": "docs/archive/standards/content/reels_writer_persona_v1.md",
    "docs/reels_hook_formula_v1.md": "docs/archive/standards/content/reels_hook_formula_v1.md",
    "docs/review_reels_gold_playbook_v1.md": "docs/archive/standards/content/review_reels_gold_playbook_v1.md",
    "VIDEO_DIRECTION_V2.md": "docs/archive/standards/visual/VIDEO_DIRECTION_V2.md",
    "docs/video_pd_standard_v2.md": "docs/archive/standards/visual/video_pd_standard_v2.md",
    "docs/munjanggun_motion_rule_v1.md": "docs/archive/standards/visual/munjanggun_motion_rule_v1.md",
    "docs/video_templates_v2.md": "docs/archive/standards/visual/video_templates_v2.md",
    "VIDEO_RECIPE_SCHEMA_V2.md": "docs/archive/standards/recipe/edit_recipe_schema_v2_legacy.md",
    "docs/video_recipe_schema_v2.md": "docs/archive/standards/recipe/planning_recipe_schema_v2_legacy.md",
    "POSTING_COPY_STANDARD.md": "docs/archive/standards/posting/POSTING_COPY_STANDARD.md",
    "docs/instagram_caption_hashtag_rules_v2.md": "docs/archive/standards/posting/instagram_caption_hashtag_rules_v2.md",
}


class AuthorityDocumentsTest(unittest.TestCase):
    def test_production_entrypoint_documents_name_the_v2_orchestrator_and_not_direct_commands(self):
        for relative_path in PRODUCTION_ENTRYPOINT_DOCUMENTS:
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

    def test_removed_gemini_constitution_cannot_return_as_a_live_authority(self):
        self.assertFalse((ROOT / "GEMINI.md").exists())

        tracked = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.md"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8", errors="strict").split("\0")
        offenders = []

        for relative_path in tracked:
            if not relative_path:
                continue
            if relative_path.startswith("docs/archive/"):
                continue
            text = (ROOT / relative_path).read_text(encoding="utf-8")
            for line_number, line in enumerate(text.splitlines(), start=1):
                if re.search(r"(?<![A-Z_])GEMINI\.md", line):
                    offenders.append(f"{relative_path}:{line_number}")

        self.assertEqual(offenders, [], f"GEMINI.md는 삭제된 문서다: {offenders}")

    def test_compact_standards_preserve_unique_operating_rules(self):
        for relative_path, anchors in COMPACT_STANDARDS.items():
            with self.subTest(relative_path=relative_path):
                text = (ROOT / relative_path).read_text(encoding="utf-8")
                for anchor in anchors:
                    self.assertIn(anchor, text)

    def test_live_locked_gates_and_code_enforced_recipe_fields_are_defined(self):
        content = (ROOT / "docs/review_reels_content_standard_v1.md").read_text(encoding="utf-8")
        visual = (ROOT / "docs/review_reels_visual_edit_standard_v1.md").read_text(encoding="utf-8")
        recipe = (ROOT / "docs/review_recipe_contract_v2.md").read_text(encoding="utf-8")

        self.assertIn("D-024 TTS 속도 하드 게이트", content)
        self.assertIn(
            f"one-shot 허용: {MIN_ONE_SHOT_CPS:.1f}~{SOFT_CPS_LIMIT:.1f}자/초",
            content,
        )
        self.assertIn(f"일반 v2 주의: {SOFT_CPS_LIMIT:.1f}자/초 초과", content)
        self.assertIn(
            f"일반 v2 하드 실패: 전체 또는 scene CPS가 {HARD_CPS_LIMIT:.1f}자/초 이상",
            content,
        )
        self.assertIn("D-025 훅 압축 하드 게이트", content)
        self.assertIn("D-026 장면 의미 일치 하드 게이트", visual)
        self.assertIn(f"{MAX_VISUAL_LEAD_SEC:.2f}초를 초과", visual)

        for field in (
            "customer_problem",
            "before_pain",
            "after_change",
            "customer_emotion",
            "hooks",
            "privacy_review",
            "privacy_sanitization_report",
            "image_dir",
            "generated_asset",
            "generated_reason",
            "not_real_proof",
            "visual_claim",
            "literal_qa_result",
        ):
            with self.subTest(field=field):
                self.assertIn(field, recipe)

        self.assertIn("생성 asset은 조건부 필드", recipe)
        self.assertRegex(
            recipe,
            r"공식\s+production preflight는\s+`privacy_sanitization_report`를 요구",
        )

    def test_legacy_documents_are_archived_and_cannot_be_live_authority(self):
        for old_path, archive_path in ARCHIVED_DOCUMENT_MOVES.items():
            with self.subTest(old_path=old_path):
                self.assertFalse((ROOT / old_path).exists())
                self.assertTrue((ROOT / archive_path).is_file())

        candidates = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "*.md"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8", errors="strict").split("\0")
        offenders = []
        for relative_path in candidates:
            if not relative_path:
                continue
            relative_path = Path(relative_path).as_posix()
            if relative_path.startswith("docs/archive/"):
                continue
            path = ROOT / relative_path
            text = path.read_text(encoding="utf-8")
            for legacy_name in LEGACY_LIVE_DOCUMENT_NAMES:
                if legacy_name in text or path.name == legacy_name:
                    offenders.append(f"{relative_path}:{legacy_name}")

        self.assertEqual(offenders, [], f"구형 문서가 살아있는 권위로 남음: {offenders}")

    def test_agents_is_the_only_general_reading_list_and_all_core_paths_exist(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        match = re.search(r"(?ms)^## 핵심 문서\s*(.*?)^## ", agents)
        self.assertIsNotNone(match)
        core_paths = re.findall(r"^- `([^`]+)`", match.group(1), flags=re.MULTILINE)
        self.assertGreaterEqual(len(core_paths), 8)
        for relative_path in core_paths:
            with self.subTest(relative_path=relative_path):
                self.assertTrue((ROOT / relative_path).is_file())

        command = (ROOT / "REVIEW_CONTENT_COMMAND.md").read_text(encoding="utf-8")
        brand_source = (ROOT / "docs/brand/BRAND_SOURCE.md").read_text(encoding="utf-8")
        self.assertIn("`AGENTS.md`의 `핵심 문서`", command)
        self.assertIn("이 명령에만 추가", command)
        self.assertNotIn("## 프로젝트 문서 우선순위", brand_source)

    def test_reel_routing_authority_prevents_dashboard_or_archive_candidate_takeover(self):
        routing = (ROOT / "docs/review_reel_production_routing_v1.md").read_text(encoding="utf-8")
        command = (ROOT / "REVIEW_CONTENT_COMMAND.md").read_text(encoding="utf-8")
        dashboard = (ROOT / "docs/reels_operations_dashboard_v1.md").read_text(encoding="utf-8")

        self.assertIn("review_reel_production", routing)
        self.assertIn("scripts/review_reel_intake.py", routing)
        self.assertIn("CAND-*", routing)
        self.assertIn("not a routing authority", routing)
        self.assertIn("not current routing authority", routing)
        self.assertIn("review_reel_production", command)
        self.assertIn("not a routing authority", dashboard)


if __name__ == "__main__":
    unittest.main()
