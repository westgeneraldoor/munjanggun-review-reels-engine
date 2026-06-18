import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_engine_v2.review_analyzer import analyze_review
from video_engine_v2.timeline_planner import build_planning_recipe, captions_to_srt, planning_to_edit_recipe


REVIEW_005 = """리뷰번호: 4991620520
상품주문번호: 2026052855842211
내용:
집이 좁아 더 좁아보일까 설치 안했었어는데 해놓고보니 엄청 이쁘고 좋아요 겨울엔 보일러 안틀어도 지낼정도라 필요성을 못느꼈는데
여름엔 에어컨 풀로 틀어도 덥더라구요 어제 설치하고 에어컨트니 확실이 더 시원합니다 진즉할걸 후회합니다 설치기사님 넘 친절하셔서
기분이 더 좋습니다
"""


ASSETS = {
    "review_capture": "고객리뷰.jpg",
    "product_thumbnail": "상품 썸네일.jpg",
    "before_main": "시공전_1.jpg",
    "before_entry": "시공전_2.jpg",
    "after_main": "시공후_메인.jpg",
    "after_front": "시공후_1.jpg",
    "after_open": "시공후_2.jpg",
    "place_hallway": "현장_복도.jpg",
}


class VideoEngineV2Test(unittest.TestCase):
    def _write_minimal_005_package(self, package_dir: Path) -> Path:
        base_recipe = {
            "source": {
                "voice": "voice.mp3",
                "script": "script.md",
                "srt": "subtitle.srt",
                "image_dir": "005_여름에어컨",
            },
            "style_dna": {"font": "nelnasamchae.ttf"},
            "asset_roles": ASSETS,
            "audio_plan": {},
            "render_targets": {"preview": {"fps": 12, "resolution": [720, 1280]}},
        }
        (package_dir / "005_여름에어컨_edit_recipe_v2.json").write_text(
            json.dumps(base_recipe, ensure_ascii=False),
            encoding="utf-8",
        )
        review_path = package_dir / "005_여름에어컨.txt"
        review_path.write_text(REVIEW_005, encoding="utf-8")
        return review_path

    def test_analyzer_classifies_005_as_cooling_ad(self):
        analysis = analyze_review(REVIEW_005)

        self.assertEqual(analysis.video_type, "cooling_effect")
        self.assertEqual(analysis.content_purpose, "ad")
        self.assertTrue(any(quote.get("selected") for quote in analysis.strongest_review_quotes))
        self.assertIn("avoid_energy_bill_promise", analysis.risk_flags)

    def test_planning_recipe_uses_complete_hook_and_separate_cta(self):
        recipe = build_planning_recipe(
            review_id="005_여름에어컨",
            package_dir="output/test",
            image_dir="005_여름에어컨",
            review_text=REVIEW_005,
            voice="voice.mp3",
            existing_script="script.md",
            existing_srt="subtitle.srt",
            asset_roles=ASSETS,
        )

        self.assertEqual(recipe["strategy"]["target_duration_sec"], 23)
        self.assertEqual(recipe["selected_hook"]["text"], "에어컨 풀가동해도 거실이 덥다면?")
        self.assertEqual(recipe["scenes"][-1]["role"], "cta")
        self.assertEqual(recipe["review_proof"]["display_mode"], "blurred_capture_plus_large_quote")
        self.assertNotIn("완벽", json.dumps(recipe, ensure_ascii=False))

    def test_planning_recipe_tracks_review_source_for_claim_safety(self):
        recipe = build_planning_recipe(
            review_id="005_여름에어컨",
            package_dir="output/test",
            image_dir="005_여름에어컨",
            review_text=REVIEW_005,
            voice="voice.mp3",
            existing_script="script.md",
            existing_srt="subtitle.srt",
            asset_roles=ASSETS,
        )

        self.assertEqual(recipe["review_source"]["text"], REVIEW_005)
        self.assertIn("확실이 더 시원합니다", recipe["review_source"]["review_quote_for_proof"])
        self.assertEqual(recipe["review_source"]["inferred_fields"], [])
        self.assertEqual(recipe["review_source"]["unsupported_story_elements"], [])

    def test_planning_converts_to_current_edit_recipe_shape(self):
        planning = build_planning_recipe(
            review_id="005_여름에어컨",
            package_dir="output/test",
            image_dir="005_여름에어컨",
            review_text=REVIEW_005,
            voice="voice.mp3",
            existing_script="script.md",
            existing_srt="subtitle.srt",
            asset_roles=ASSETS,
        )
        base = {
            "source": {"voice": "voice.mp3", "image_dir": "005_여름에어컨"},
            "style_dna": {"font": "nelnasamchae.ttf"},
            "asset_roles": ASSETS,
            "audio_plan": {},
            "render_targets": {"preview": {"fps": 12, "resolution": [720, 1280]}},
        }

        edit = planning_to_edit_recipe(planning, base_edit_recipe=base, current_voice_duration_sec=26.93)

        self.assertEqual(edit["version"], "2.1")
        self.assertEqual(edit["beats"][0]["caption"], "에어컨 풀가동해도\n거실이 덥다면?")
        self.assertAlmostEqual(edit["beats"][-1]["time"][1], 26.93, places=2)
        self.assertEqual(edit["audio_plan"]["sync_policy"]["mode"], "current_voice_sync_safe")
        self.assertEqual(edit["audio_plan"]["sync_policy"]["final_voice_duration_sec"], 26.93)

    def test_planning_does_not_invent_final_voice_duration_when_unmeasured(self):
        planning = build_planning_recipe(
            review_id="005_여름에어컨",
            package_dir="output/test",
            image_dir="005_여름에어컨",
            review_text=REVIEW_005,
            voice="voice.mp3",
            existing_script="script.md",
            existing_srt="subtitle.srt",
            asset_roles=ASSETS,
        )
        base = {
            "source": {"voice": "voice.mp3", "image_dir": "005_여름에어컨"},
            "style_dna": {"font": "nelnasamchae.ttf"},
            "asset_roles": ASSETS,
            "audio_plan": {},
            "render_targets": {"preview": {"fps": 12, "resolution": [720, 1280]}},
        }

        edit = planning_to_edit_recipe(planning, base_edit_recipe=base, current_voice_duration_sec=None)

        self.assertNotIn("final_voice_duration_sec", edit["audio_plan"]["sync_policy"])
        self.assertEqual(edit["audio_plan"]["sync_policy"]["render_duration_sec"], 23.0)

    def test_005_pilot_rejects_unmeasured_existing_voice_duration(self):
        from video_engine_v2 import pilot_005

        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir)
            review_path = self._write_minimal_005_package(package_dir)

            with patch("video_engine_v2.pilot_005._audio_duration", return_value=None):
                with self.assertRaises(RuntimeError):
                    pilot_005.build_005_pilot(package_dir, review_path)

    def test_005_final_rejects_unmeasured_final_voice_duration(self):
        from video_engine_v2 import pilot_005

        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir)
            review_path = self._write_minimal_005_package(package_dir)

            with patch("video_engine_v2.pilot_005.generate.generate_voice", return_value=package_dir / "raw.mp3"):
                with patch("video_engine_v2.pilot_005._fit_audio_to_duration", return_value=None):
                    with patch("video_engine_v2.pilot_005._audio_duration", return_value=None):
                        with self.assertRaises(RuntimeError):
                            pilot_005.build_005_final_html_inputs(package_dir, review_path)

    def test_captions_to_srt_uses_planning_scene_times(self):
        planning = build_planning_recipe(
            review_id="005_여름에어컨",
            package_dir="output/test",
            image_dir="005_여름에어컨",
            review_text=REVIEW_005,
            voice="voice.mp3",
            existing_script="script.md",
            existing_srt="subtitle.srt",
            asset_roles=ASSETS,
        )

        srt = captions_to_srt(planning)

        self.assertIn("00:00:00,000 --> 00:00:02,000", srt)
        self.assertIn("무료 방문 실측 상담", srt)
        self.assertIn("00:00:20,300 --> 00:00:23,000", srt)

    def test_033_variant_is_registered_with_required_assets_and_valid_script(self):
        import generate
        from video_engine_v2.final_html_variants import CONFIGS

        config = CONFIGS["033"]

        self.assertEqual(config.video_type, "entry_noise_smell_design")
        self.assertEqual(config.content_purpose, "retargeting")
        self.assertEqual(config.asset_roles["review_capture"], "고객리뷰.jpg")
        self.assertEqual(config.asset_roles["product_thumbnail"], "상품 썸네일.jpg")
        self.assertEqual(config.asset_roles["before_main"], "시공전.jpg")
        self.assertEqual(config.scenes[0]["caption"]["text"], "현관에서\n소리랑 냄새가\n들어온다면?")
        self.assertNotIn("중문", config.scenes[0]["caption"]["text"])
        self.assertEqual(
            [],
            [issue for issue in generate.validate_script(config.script_text) if issue.startswith("[FAIL]")],
        )

    def test_033_variant_aligns_asset_caption_and_narration_meaning(self):
        from video_engine_v2.final_html_variants import CONFIGS

        scenes = CONFIGS["033"].scenes
        atmosphere_scene = scenes[1]
        smell_noise_scene = next(scene for scene in scenes if "냄새 차단" in scene["narration"])

        self.assertEqual(atmosphere_scene["visual_source"]["role"], "after_main")
        self.assertIn("집 분위기", atmosphere_scene["caption"]["text"])
        self.assertIn("집 분위기", atmosphere_scene["narration"])
        self.assertNotEqual(smell_noise_scene["visual_source"]["role"], "product_thumbnail")
        self.assertIn("소음", smell_noise_scene["caption"]["text"])

    def test_033_opening_caption_fits_phone_preview(self):
        from video_engine_v2.final_html_variants import CONFIGS

        hook_caption = CONFIGS["033"].scenes[0]["caption"]
        lines = hook_caption["text"].split("\n")

        self.assertNotEqual(hook_caption["size"], "large")
        self.assertLessEqual(max(len(line) for line in lines), 9)

    def test_033_all_caption_lines_fit_phone_preview(self):
        from video_engine_v2.final_html_variants import CONFIGS

        for scene in CONFIGS["033"].scenes:
            caption = scene["caption"]
            max_line = max(len(line) for line in caption["text"].split("\n"))
            with self.subTest(scene=scene["scene_id"], caption=caption["text"]):
                self.assertLessEqual(max_line, 9)
                if max_line > 7:
                    self.assertNotEqual(caption["size"], "large")


if __name__ == "__main__":
    unittest.main()
