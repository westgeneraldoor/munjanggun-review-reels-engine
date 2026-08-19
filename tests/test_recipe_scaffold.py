import unittest

from scripts import review_reel_intake as intake_cli
from video_engine_v2 import review_reel_intake
from video_engine_v2.reels_qa import validate_html_preflight, validate_review_reels_one_shot_contract


class RecipeScaffoldTests(unittest.TestCase):
    def test_fresh_session_contract_routes_and_reaches_html_preflight_shape_after_required_inputs(self):
        routed = review_reel_intake.route_user_command(
            "이 리뷰와 사진들로 신규 리뷰 숏폼 만들자. 사진 검수부터 HTML까지 진행해."
        )
        self.assertEqual(routed["workflow"], "review_reel_production")

        planning, edit = review_reel_intake.build_recipe_scaffold(
            content_id="120",
            review_text="현관 사용이 불편했는데 설치 후 동선이 편해졌습니다.",
            selected_assets=[
                {"relative_path": "after.jpg", "evidence_classes": ["installed_result"], "visual_quality": {"full_product_visible": True}},
                {"relative_path": "before.jpg", "evidence_classes": ["before_state"], "visual_quality": {}},
                {"relative_path": "review.png", "evidence_classes": ["review_capture"], "visual_quality": {}},
            ],
        )
        initial_validation = validate_html_preflight(planning, edit)
        self.assertEqual(
            {issue["code"] for issue in initial_validation["issues"]},
            {"RECIPE_SCAFFOLD_INCOMPLETE"},
        )

        for recipe in (planning, edit):
            recipe["scaffold"]["status"] = "complete"
            recipe["scaffold"]["pending_fields"] = []
        planning["analysis"] = {
            "customer_problem": "현관 사용이 불편함",
            "before_pain": "현관 동선이 불편함",
            "after_change": "설치 후 동선이 편해짐",
            "customer_emotion": ["편안함"],
        }
        planning["writer_brief"]["one_line_story"] = "불편했던 현관 동선이 설치 후 편해진 리뷰 이야기"
        for scene in planning["scenes"]:
            scene["meaning_match_evidence"] = "review_source.text and selected photo evidence"
        edit["audio_plan"]["tts_text_sha256"] = "a" * 64
        edit["audio_plan"]["final_voice_sha256"] = "b" * 64
        completed_validation = validate_html_preflight(planning, edit)
        self.assertTrue(completed_validation["ok"], completed_validation["issues"])

    def test_scaffold_cannot_be_marked_complete_while_placeholders_remain(self):
        planning, edit = review_reel_intake.build_recipe_scaffold(
            content_id="120",
            review_text="현관 사용이 불편했는데 설치 후 동선이 편해졌습니다.",
            selected_assets=[
                {"relative_path": "after.jpg", "evidence_classes": ["installed_result"], "visual_quality": {"full_product_visible": True}},
                {"relative_path": "before.jpg", "evidence_classes": ["before_state"], "visual_quality": {}},
                {"relative_path": "review.png", "evidence_classes": ["review_capture"], "visual_quality": {}},
            ],
        )
        for recipe in (planning, edit):
            recipe["scaffold"]["status"] = "complete"
            recipe["scaffold"]["pending_fields"] = []

        result = validate_review_reels_one_shot_contract(planning, edit)

        self.assertIn("RECIPE_SCAFFOLD_PLACEHOLDER_REMAINS", {issue["code"] for issue in result["issues"]})

    def test_known_gate_issue_exposes_central_fix_guidance(self):
        planning, edit = review_reel_intake.build_recipe_scaffold(
            content_id="120",
            review_text="현관 사용이 불편했는데 설치 후 동선이 편해졌습니다.",
            selected_assets=[
                {"relative_path": "after.jpg", "evidence_classes": ["installed_result"], "visual_quality": {"full_product_visible": True}},
                {"relative_path": "before.jpg", "evidence_classes": ["before_state"], "visual_quality": {}},
                {"relative_path": "review.png", "evidence_classes": ["review_capture"], "visual_quality": {}},
            ],
        )

        issue = validate_review_reels_one_shot_contract(planning, edit)["issues"][0]

        self.assertEqual(issue["code"], "RECIPE_SCAFFOLD_INCOMPLETE")
        self.assertEqual(issue["guidance"]["authority"], "docs/review_recipe_contract_v2.md")
        self.assertIn("pending_fields", issue["guidance"]["how_to_fix"])

    def test_official_intake_cli_exposes_error_explainer(self):
        args = intake_cli.build_parser().parse_args(
            ["explain-error", "--code", "HOOK_SHOT_CAPTION_ALIGNMENT_INVALID"]
        )

        self.assertEqual(args.command, "explain-error")
        self.assertEqual(args.code, "HOOK_SHOT_CAPTION_ALIGNMENT_INVALID")

    def test_official_intake_cli_exposes_recipe_scaffold_with_identity_guard(self):
        args = intake_cli.build_parser().parse_args(
            [
                "recipe-scaffold",
                "--output-root",
                "output",
                "--expected-content-id",
                "120",
            ]
        )

        self.assertEqual(args.command, "recipe-scaffold")
        self.assertEqual(args.expected_content_id, "120")

    def test_official_intake_cli_exposes_central_workflow_next_command(self):
        args = intake_cli.build_parser().parse_args(
            ["workflow-next", "--output-root", "output"]
        )

        self.assertEqual(args.command, "workflow-next")

    def test_scaffold_matches_current_one_shot_structure_and_only_fails_as_unfilled_content(self):
        builder = getattr(review_reel_intake, "build_recipe_scaffold", None)
        self.assertTrue(callable(builder), "fresh sessions need an executable recipe scaffold builder")
        if not callable(builder):
            return

        planning, edit = builder(
            content_id="120",
            review_text="현관 사용이 불편했는데 설치 후 동선이 편해졌습니다.",
            selected_assets=[
                {
                    "relative_path": "120_fixture_images/after.jpg",
                    "evidence_classes": ["installed_result"],
                    "visual_quality": {"full_product_visible": True},
                },
                {
                    "relative_path": "120_fixture_images/before.jpg",
                    "evidence_classes": ["before_state"],
                    "visual_quality": {},
                },
                {
                    "relative_path": "_work/review_capture_masked.png",
                    "evidence_classes": ["review_capture"],
                    "visual_quality": {},
                },
            ],
        )

        result = validate_review_reels_one_shot_contract(planning, edit)

        self.assertFalse(result["ok"])
        self.assertEqual(
            {issue["code"] for issue in result["issues"]},
            {"RECIPE_SCAFFOLD_INCOMPLETE"},
            result["issues"],
        )
        self.assertEqual(planning["content_id"], "120")
        self.assertEqual(edit["hook_visual_contract"]["result_asset_id"], "installed_result")
        self.assertEqual(edit["hook_visual_contract"]["before_asset_id"], "before_state")
        self.assertNotIn("118", str(planning))
        self.assertNotIn("119", str(edit))


if __name__ == "__main__":
    unittest.main()
