import re
import subprocess
import unittest
from pathlib import Path

from video_engine_v2.reels_qa import (
    CALM_DISSOLVE_MS,
    CALM_SLIDE_MS,
    CALM_HORIZONTAL_TRAVEL_PX,
    CALM_SCALE_DELTA,
    CALM_VERTICAL_TRAVEL_PX,
    CAPTION_ACCENT_POP_MS,
    CAPTION_ACCENT_ONSET_EARLY_TOLERANCE_SEC,
    CAPTION_ACCENT_ONSET_LATE_TOLERANCE_SEC,
    CAPTION_CHUNK_POP_MS,
    CAPTION_SAFE_BOTTOM_PX,
    CAPTION_SAFE_TOP_PX,
    HARD_CPS_LIMIT,
    MAX_ONE_SHOT_TOTAL_SHOTS,
    MAX_VISUAL_LEAD_SEC,
    MIN_ONE_SHOT_FINAL_RESULT_SEC,
    MIN_ONE_SHOT_HOOK_SHOT_SEC,
    MIN_ONE_SHOT_CPS,
    MAX_CONTEXTUAL_CAPTION_CHUNKS,
    MIN_CONTEXTUAL_CAPTION_CHARS,
    ONE_SHOT_CALM_MOTIONS,
    ONE_SHOT_CALM_TRANSITIONS,
    SOFT_PAGE_TURN_MS,
    SOFT_CPS_LIMIT,
)
from video_engine_v2.manual_review import HTML_REVIEW_CHECKS, RENDER_REVIEW_CHECKS, VOICE_REVIEW_CHECKS
from video_engine_v2.review_reel_intake import PHOTO_SELECTION_SCHEMA_VERSION


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ENTRYPOINT_DOCUMENTS = [
    "AGENTS.md",
    "README.md",
    "docs/review_reel_production_routing_v1.md",
    "docs/review_reel_candidate_selection_policy_v1.md",
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

DURABLE_RENDER_DOCUMENTS = [
    "AGENTS.md",
    "README.md",
    "docs/review_reel_production_routing_v1.md",
    "docs/review_video_publish_workflow_v2.md",
    "docs/review_reels_one_shot_contract_v2.md",
    "docs/review_recipe_contract_v2.md",
    "docs/render_qa_rules_v2.md",
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
        "키워드 크기는 본문과 동일",
        "calm_dissolve",
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
    def test_live_render_authority_uses_durable_start_and_status_not_foreground_wait(self):
        for relative_path in DURABLE_RENDER_DOCUMENTS:
            with self.subTest(relative_path=relative_path):
                text = (ROOT / relative_path).read_text(encoding="utf-8")
                self.assertIn("render-start", text)
                self.assertIn("render-status", text)
                self.assertNotRegex(
                    text,
                    r"(?m)^python scripts/produce_review_v2\.py render --package",
                )

        render_rules = (ROOT / "docs/render_qa_rules_v2.md").read_text(encoding="utf-8")
        self.assertIn("DIRECT_RENDER_DISABLED_USE_RENDER_START", render_rules)
        self.assertIn("queued -> running -> succeeded|failed", render_rules)
        self.assertIn("rendered_frames / expected_frames", render_rules)
        self.assertIn("RETRY_REQUIRES_NEW_OUTPUT", render_rules)
        self.assertIn("post-render-qa", render_rules)

    def test_durable_render_implementation_has_detachment_and_evidence_anchors(self):
        orchestrator = (ROOT / "scripts/produce_review_v2.py").read_text(encoding="utf-8")
        worker = (ROOT / "scripts/render_review_v2_job.py").read_text(encoding="utf-8")
        model = (ROOT / "video_engine_v2/render_job.py").read_text(encoding="utf-8")

        for anchor in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "render_review_v2_job.py"):
            self.assertIn(anchor, orchestrator)
        for anchor in ("output_evidence", "sha256_file", "FRAME_COUNT_MISMATCH"):
            self.assertIn(anchor, worker)
        for anchor in ("NamedTemporaryFile", "os.replace", "bindings_sha256", "rendered_frames", "expected_frames"):
            self.assertIn(anchor, model)
        post_qa = (ROOT / "scripts/render-post-qa.mjs").read_text(encoding="utf-8")
        self.assertIn("render_job state must be succeeded", post_qa)
        self.assertIn("render_job output bytes/SHA-256", post_qa)

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
            self.assertIn("v3: discontinued", text)
            self.assertIn("v3.1: discontinued", text)
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

    def test_privacy_standard_allows_building_number_and_requires_masking_first(self):
        privacy = (ROOT / "docs/reels_privacy_asset_qa_rules_v1.md").read_text(encoding="utf-8")
        workflow = (ROOT / "docs/review_video_publish_workflow_v2.md").read_text(encoding="utf-8")
        render = (ROOT / "docs/render_qa_rules_v2.md").read_text(encoding="utf-8")

        # 아파트 동 번호는 허용, 개인 세대를 특정하는 호수만 차단이라는 사용자 확정 기준.
        self.assertIn("동 번호는 차단 대상이 아니다", privacy)
        self.assertIn("아파트 동 번호는 기본 허용", workflow)
        self.assertNotIn("주소/건물명/가족사진/얼굴/차량번호가 보이면 렌더 금지", render)
        self.assertIn("개인 세대를 특정하는 호수", render)
        for text in (privacy, workflow, render):
            self.assertNotIn("동호수", text)
            self.assertNotIn("동/호수", text)

        # 위험 요소가 있어도 컷 제외가 아니라 마스킹이 기본이다.
        self.assertIn("마스킹 우선 원칙", privacy)
        self.assertIn("컷 제외는 마지막 수단", privacy)
        self.assertIn("리뷰 캡처는", privacy)
        self.assertIn("반드시 사용", privacy)
        self.assertIn("번호판만 가리고 사진은 사용", privacy)

        # 불투명 유리 너머 실루엣처럼 식별 불가한 형체는 차단 대상이 아니다.
        for text in (privacy, workflow):
            self.assertIn("실루엣", text)

    def test_cold_test_recovery_contracts_are_live_and_match_code(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        privacy = (ROOT / "docs/reels_privacy_asset_qa_rules_v1.md").read_text(encoding="utf-8")
        recipe = (ROOT / "docs/review_recipe_contract_v2.md").read_text(encoding="utf-8")
        visual = (ROOT / "docs/review_reels_visual_edit_standard_v1.md").read_text(encoding="utf-8")
        render = (ROOT / "docs/render_qa_rules_v2.md").read_text(encoding="utf-8")

        self.assertIn(PHOTO_SELECTION_SCHEMA_VERSION, privacy)
        for anchor in ("맨발", "신발", "아파트 동 번호", "PHOTO_PRIVACY_CATEGORY_INVALID", "MASKING_FIRST_NOT_APPLIED"):
            self.assertIn(anchor, privacy)
        for anchor in (
            "사용자가 제공한 전체 구도",
            "이미 `**`로 익명화",
            "REVIEW_CAPTURE_CROP_FORBIDDEN",
            "REVIEW_CAPTURE_COMPOSITION_CHANGED",
            "REVIEW_CAPTURE_PREMASKED_ID_TOUCHED",
        ):
            self.assertIn(anchor, privacy)
        self.assertIn("리뷰 캡처의 사용자 제공 구도", agents)
        for anchor in ("asset_evidence", "full_product_visible: true", "CLAIM_EVIDENCE_MISSING"):
            self.assertIn(anchor, recipe)
        for anchor in ("0.5초", "첫 3개 훅", "voice-review-record", "html-review-record"):
            self.assertIn(anchor, visual)
        for anchor in ("edit_sha256", "review_proof", "render_complete", "qa_reviewed", "final_delivery_complete"):
            self.assertIn(anchor, render)

        command_checks = {
            "voice-review-record": VOICE_REVIEW_CHECKS,
            "html-review-record": HTML_REVIEW_CHECKS,
            "render-review-record": RENDER_REVIEW_CHECKS,
        }
        for command, checks in command_checks.items():
            self.assertIn(command, agents)
            for check in checks:
                self.assertIn(f"--check {check}", agents)

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
        self.assertIn("완성 결과 → 이전 상태 → 완성 결과", visual)
        self.assertIn("전체 12컷", visual)
        self.assertIn("정지 화면", visual)
        self.assertIn("실제 원문 인용", visual)
        self.assertIn("2px 이하", visual)
        self.assertIn("아이보리 화이트", visual)
        self.assertIn("민트", visual)
        self.assertIn(f"calm_dissolve {CALM_DISSOLVE_MS}ms", visual)
        self.assertIn(f"calm_slide {CALM_SLIDE_MS}ms", visual)
        self.assertIn(f"soft_page_turn {SOFT_PAGE_TURN_MS}ms", visual)
        self.assertIn(f"scale 차이 {CALM_SCALE_DELTA:.2f}", visual)
        self.assertIn(f"좌우 총 {CALM_HORIZONTAL_TRAVEL_PX}px", visual)
        self.assertIn(f"상하 총 {CALM_VERTICAL_TRAVEL_PX}px", visual)
        for motion in sorted(ONE_SHOT_CALM_MOTIONS):
            self.assertIn(f"`{motion}`", visual)
        for transition in sorted(ONE_SHOT_CALM_TRANSITIONS):
            self.assertIn(f"`{transition}`", visual)

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
            "hook_visual_contract",
            "result_asset_id",
            "before_asset_id",
            "motion_reason",
            "review_emphasis",
            "segments",
            "caption_layout.theme",
            "caption_accent.start_sec",
            "display_text",
            "draw_duration_sec",
        ):
            with self.subTest(field=field):
                self.assertIn(field, recipe)

        for anchor in (
            "본문은 `medium 46px`",
            "강조 단어의 실제 발화 예상 시점",
            "3연동중문",
            "0.20초 안에",
        ):
            self.assertIn(anchor, visual)

        self.assertIn("생성 asset은 조건부 필드", recipe)
        self.assertRegex(
            recipe,
            r"공식\s+production preflight는\s+`privacy_sanitization_report`를 요구",
        )

    def test_approved_calm_photo_contract_is_aligned_across_authority_documents(self):
        visual = (ROOT / "docs/review_reels_visual_edit_standard_v1.md").read_text(encoding="utf-8")
        recipe = (ROOT / "docs/review_recipe_contract_v2.md").read_text(encoding="utf-8")
        combined = visual + "\n" + recipe

        self.assertIn(f"전체 {MAX_ONE_SHOT_TOTAL_SHOTS}컷", combined)
        self.assertIn(f"각각 {MIN_ONE_SHOT_HOOK_SHOT_SEC:.1f}초 이상", combined)
        self.assertIn(f"최소 {MIN_ONE_SHOT_FINAL_RESULT_SEC:.1f}초", combined)
        self.assertIn("cut → calm_dissolve → calm_dissolve", combined)
        self.assertIn(f"calm_dissolve {CALM_DISSOLVE_MS}ms", combined)
        self.assertIn(f"calm_slide {CALM_SLIDE_MS}ms", combined)
        self.assertIn(f"soft_page_turn {SOFT_PAGE_TURN_MS}ms", combined)
        self.assertIn("medium 46px", combined)
        self.assertIn("hero-calm 58px", combined)
        self.assertIn("뒤로 갈수록 `small`로 축소하지 않습니다", combined)
        self.assertIn(f"scale 차이 {CALM_SCALE_DELTA:.2f}", combined)
        self.assertIn(f"좌우 총 {CALM_HORIZONTAL_TRAVEL_PX}px", combined)
        self.assertIn(f"상하 총 {CALM_VERTICAL_TRAVEL_PX}px", combined)
        self.assertIn("키워드 크기는 본문과 동일", combined)
        for value in sorted(ONE_SHOT_CALM_MOTIONS | ONE_SHOT_CALM_TRANSITIONS):
            with self.subTest(value=value):
                self.assertIn(f"`{value}`", combined)

    def test_caption_dead_zone_and_context_density_are_locked_to_live_standards(self):
        visual = (ROOT / "docs/review_reels_visual_edit_standard_v1.md").read_text(encoding="utf-8")
        recipe = (ROOT / "docs/review_recipe_contract_v2.md").read_text(encoding="utf-8")
        render = (ROOT / "docs/render_qa_rules_v2.md").read_text(encoding="utf-8")
        combined = visual + "\n" + recipe + "\n" + render

        self.assertIn(f"y={CAPTION_SAFE_TOP_PX}~{CAPTION_SAFE_BOTTOM_PX}", combined)
        self.assertIn(f"최대 {MAX_CONTEXTUAL_CAPTION_CHUNKS}개", combined)
        self.assertIn(f"최소 {MIN_CONTEXTUAL_CAPTION_CHARS}자", combined)
        self.assertIn("음성 전문", combined)
        self.assertIn("실제 DOM", combined)
        self.assertIn("3줄 이상", combined)
        self.assertIn("한 방향", combined)
        self.assertIn("일정 속도", combined)
        self.assertIn("투명도만", combined)
        self.assertIn(f"{CAPTION_ACCENT_ONSET_EARLY_TOLERANCE_SEC:.2f}초 이상 빠르", combined)
        self.assertIn(f"{CAPTION_ACCENT_ONSET_LATE_TOLERANCE_SEC:.2f}초 이상 늦", combined)
        self.assertIn(f"{CAPTION_ACCENT_POP_MS}ms", combined)
        self.assertIn(f"{CAPTION_CHUNK_POP_MS}ms", combined)
        self.assertIn("영상 시간", combined)

    def test_caption_story_arc_and_measured_onset_are_live_authority(self):
        content = (ROOT / "docs/review_reels_content_standard_v1.md").read_text(encoding="utf-8")
        visual = (ROOT / "docs/review_reels_visual_edit_standard_v1.md").read_text(encoding="utf-8")
        one_shot = (ROOT / "docs/review_reels_one_shot_contract_v2.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

        for anchor in (
            "첫 자막부터 후킹",
            "한 화면 한 생각",
            "CTA는 첫 갈등을 회수",
            "일반론 CTA",
        ):
            self.assertIn(anchor, content + "\n" + agents)
        self.assertIn("실측 발화 시작", one_shot + "\n" + visual)
        self.assertIn("CSS 실제 경과시간", visual)

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
        self.assertIn("실제 Terra 세션", routing)
        self.assertRegex(routing, r"자동 테스트는 모델의 재시도 횟수를\s+측정하지 않는다")
        self.assertIn("3회 이내", routing)
        self.assertIn("PR 본문", routing)


if __name__ == "__main__":
    unittest.main()


class NarrationRhythmAndUnderlineAuthorityTests(unittest.TestCase):
    """120번 실전에서 드러난 두 결함의 기준이 살아있는 문서에 남아 있어야 한다."""

    def test_content_standard_records_why_sentence_rhythm_is_not_gated(self):
        doc = (ROOT / "docs" / "review_reels_content_standard_v1.md").read_text(encoding="utf-8")

        self.assertIn("게이트로 만들지 않는다", doc)
        # 다시 자동화하려는 사람이 실패 사례를 그대로 볼 수 있어야 한다.
        self.assertIn("하나하나 꼼꼼했습니다", doc)
        self.assertIn("증상이지 원인이 아니며", doc)

    def test_visual_standard_requires_one_underline_segment_per_rendered_line(self):
        doc = (ROOT / "docs" / "review_reels_visual_edit_standard_v1.md").read_text(encoding="utf-8")

        self.assertIn("리뷰 밑줄 정렬 계약", doc)
        self.assertIn("line_text", doc)
        self.assertIn("review_underline_alignment_reviewed", doc)

    def test_recipe_contract_shows_a_copyable_multiline_segment_example(self):
        doc = (ROOT / "docs" / "review_recipe_contract_v2.md").read_text(encoding="utf-8")

        self.assertIn("line_text", doc)
        self.assertIn("REVIEW_EMPHASIS_SEGMENT_TEXT_MISMATCH", doc)

    def test_every_new_gate_code_carries_central_fix_guidance(self):
        from video_engine_v2.qa_guidance import explain_error

        for code in (
            "REVIEW_EMPHASIS_SEGMENT_TEXT_MISMATCH",
            "REVIEW_EMPHASIS_SEGMENT_ORDER_INVALID",
            "SHOT_MEANING_EVIDENCE_MISSING",
            "ONE_SHOT_TRANSITION_ROLE_INVALID",
            "ONE_SHOT_TRANSITION_USAGE_EXCESSIVE",
            "SCENE_DENSITY_LOW",
        ):
            with self.subTest(code=code):
                guidance = explain_error(code)
                self.assertTrue(guidance["known"])
                self.assertTrue(guidance["authority"])
                self.assertTrue(guidance["how_to_fix"])


class CapturePixelVerificationAuthorityTests(unittest.TestCase):
    """픽셀 검증 기준도 살아있는 문서에 남아 있어야 한다."""

    def test_privacy_standard_documents_the_masking_pixel_contract(self):
        doc = (ROOT / "docs" / "reels_privacy_asset_qa_rules_v1.md").read_text(encoding="utf-8")

        self.assertIn("sanitized_assets", doc)
        self.assertIn("source_relative_path", doc)
        self.assertIn("masked_regions", doc)
        self.assertIn("SANITIZED_REGION_STILL_LEGIBLE", doc)

    def test_visual_standard_documents_the_underline_pixel_contract(self):
        doc = (ROOT / "docs" / "review_reels_visual_edit_standard_v1.md").read_text(encoding="utf-8")

        self.assertIn("REVIEW_UNDERLINE_CROSSES_TEXT", doc)
        self.assertIn("REVIEW_UNDERLINE_LINES_NOT_CONSECUTIVE", doc)

    def test_every_pixel_gate_code_carries_central_fix_guidance(self):
        from video_engine_v2.qa_guidance import explain_error

        for code in (
            "REVIEW_UNDERLINE_CROSSES_TEXT",
            "REVIEW_UNDERLINE_NOT_UNDER_TEXT",
            "REVIEW_UNDERLINE_LINES_NOT_CONSECUTIVE",
            "SANITIZED_ASSET_NOT_DECLARED",
            "SANITIZED_ASSET_DECLARATION_INVALID",
            "SANITIZED_ASSET_UNCHANGED",
            "SANITIZED_ASSET_CHANGE_OUTSIDE_REGION",
            "SANITIZED_ASSET_GEOMETRY_CHANGED",
            "SANITIZED_REGION_NOT_APPLIED",
            "SANITIZED_REGION_STILL_LEGIBLE",
            "SANITIZED_SOURCE_MISSING",
        ):
            with self.subTest(code=code):
                guidance = explain_error(code)
                self.assertTrue(guidance["known"])
                self.assertTrue(guidance["authority"])
                self.assertTrue(guidance["how_to_fix"])
