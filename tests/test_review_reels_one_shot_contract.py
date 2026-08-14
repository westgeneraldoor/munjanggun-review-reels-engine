import json
import hashlib
import unittest
from pathlib import Path

from video_engine_v2.reels_qa import (
    canonical_tts_input_narration,
    validate_html_preflight,
    validate_review_reels_one_shot_contract,
)


FIXTURE = Path(__file__).parent / "fixtures" / "review_reels_one_shot_valid.json"


def load_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class ReviewReelsOneShotContractTest(unittest.TestCase):
    def apply_calm_c_visual_language(self, fixture):
        motion_rows = (
            ("calm_push_in", "calm_push_in", "calm_push_in"),
            ("calm_glide_up",),
            ("calm_glide_left",),
            ("calm_push_in",),
            ("review_capture_hold",),
            ("calm_glide_up",),
            ("review_capture_hold",),
            ("calm_push_in",),
        )
        for beat_index, beat in enumerate(fixture["edit"]["beats"]):
            row = motion_rows[beat_index]
            beat["motion"] = row[0]
            for shot_index, shot in enumerate(beat["shots"]):
                shot["motion"] = row[min(shot_index, len(row) - 1)]
                shot["transition_in"] = "cut" if beat_index == 0 and shot_index == 0 else "calm_dissolve"

    def add_result_first_hook(self, fixture):
        fixture["edit"]["asset_roles"].update({
            "after_result": "after.jpg",
            "before_entry": "before.jpg",
        })
        fixture["edit"]["hook_visual_contract"] = {
            "result_asset_id": "after_result",
            "before_asset_id": "before_entry",
        }
        fixture["edit"]["asset_evidence"].update({
            "after_result": {"evidence_class": "installed_result", "visual_quality": {"full_product_visible": True}},
            "before_entry": {"evidence_class": "before_state"},
        })
        fixture["edit"]["beats"][0]["shots"] = [
            {"asset_id": "after_result", "motion": "calm_push_in", "motion_reason": "Show the result first.", "transition_in": "cut", "start_sec": 0.0, "end_sec": 1.3},
            {"asset_id": "before_entry", "motion": "calm_push_in", "motion_reason": "Show the before state without reversing the camera.", "transition_in": "calm_dissolve", "start_sec": 1.3, "end_sec": 2.6},
            {"asset_id": "after_result", "motion": "calm_push_in", "motion_reason": "Return to the result.", "transition_in": "calm_dissolve", "start_sec": 2.6, "end_sec": 4.0},
        ]

    def add_review_emphasis(self, fixture, *, quote=None):
        review_beat = fixture["edit"]["beats"][6]
        review_beat["review_emphasis"] = {
            "quote": quote or fixture["planning"]["review_source"]["review_quote_for_proof"],
            "start_sec": 24.05,
            "end_sec": 26.2,
            "draw_duration_sec": 0.15,
            "segments": [{"left_pct": 12.0, "top_pct": 54.0, "width_pct": 70.0}],
        }

    def test_anonymized_contract_passes_the_strict_html_preflight(self):
        fixture = load_fixture()

        result = validate_html_preflight(
            fixture["planning"],
            fixture["edit"],
            require_one_shot_contract=True,
        )

        self.assertTrue(result["ok"], result["issues"])

    def test_contract_accepts_the_user_selected_calm_c_visual_language(self):
        fixture = load_fixture()
        self.apply_calm_c_visual_language(fixture)

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertTrue(result["ok"], result["issues"])

    def test_contract_rejects_camera_direction_changes_inside_one_beat(self):
        fixture = load_fixture()
        fixture["edit"]["beats"][0]["shots"][0]["motion"] = "calm_push_in"
        fixture["edit"]["beats"][0]["shots"][1]["motion"] = "calm_pull_out"
        fixture["edit"]["beats"][0]["shots"][2]["motion"] = "calm_push_in"

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("SHOT_MOTION_PATH_DISCONTINUITY", {issue["code"] for issue in result["issues"]})

    def test_contract_rejects_the_superseded_micro_motion_and_soft_dissolve_language(self):
        fixture = load_fixture()
        fixture["edit"]["beats"][1]["motion"] = "micro_push_in"
        fixture["edit"]["beats"][1]["shots"][0]["motion"] = "micro_push_in"
        fixture["edit"]["beats"][1]["shots"][0]["transition_in"] = "soft_dissolve"

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("ONE_SHOT_MOTION_NOT_CALM", codes)
        self.assertIn("ONE_SHOT_TRANSITION_NOT_CALM", codes)

    def test_contract_never_grants_mp4_scope(self):
        fixture = load_fixture()
        fixture["planning"]["workflow_contract"]["mp4_scope_authorized"] = True

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertFalse(result["ok"])
        self.assertIn("MP4_SCOPE_MUST_REMAIN_UNAUTHORIZED", {issue["code"] for issue in result["issues"]})

    def test_contract_requires_result_first_hook_metadata(self):
        fixture = load_fixture()
        fixture["edit"].pop("hook_visual_contract")

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("RESULT_FIRST_HOOK_MISSING", {issue["code"] for issue in result["issues"]})

    def test_contract_rejects_a_hook_that_does_not_return_to_the_result(self):
        fixture = load_fixture()
        self.add_result_first_hook(fixture)
        fixture["edit"]["beats"][0]["shots"][2]["asset_id"] = "before_entry"

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("RESULT_FIRST_HOOK_SEQUENCE_INVALID", {issue["code"] for issue in result["issues"]})

    def test_contract_rejects_a_result_hook_that_does_not_show_the_full_product(self):
        fixture = load_fixture()
        fixture["edit"]["asset_evidence"]["after_main"]["visual_quality"]["full_product_visible"] = False

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("HOOK_RESULT_NOT_FULLY_VISIBLE", {issue["code"] for issue in result["issues"]})

    def test_contract_requires_measurement_evidence_only_when_the_review_story_claims_measurement(self):
        fixture = load_fixture()
        fixture["planning"]["review_source"]["text"] += " 현장에서 직접 실측했습니다."
        fixture["edit"]["beats"][3]["narration_ref"] = "현장에서 직접 실측했습니다."
        fixture["edit"]["beats"][3]["asset"] = "site_context"
        fixture["edit"]["beats"][3]["shots"][0]["asset_id"] = "site_context"
        fixture["edit"]["asset_evidence"]["measure"]["unused_reason"] = "Fixture intentionally omits the measurement cut."

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("CLAIM_EVIDENCE_MISSING", {issue["code"] for issue in result["issues"]})

    def test_contract_allows_unused_measurement_evidence_when_the_story_makes_no_measurement_claim(self):
        fixture = load_fixture()
        fixture["edit"]["beats"][3]["asset"] = "site_context"
        fixture["edit"]["beats"][3]["shots"][0]["asset_id"] = "site_context"
        fixture["edit"]["asset_evidence"]["measure"]["unused_reason"] = "The source review makes no measurement claim."

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertNotIn("CLAIM_EVIDENCE_MISSING", {issue["code"] for issue in result["issues"]})
        self.assertNotIn("UNUSED_HIGH_VALUE_EVIDENCE_REASON_MISSING", {issue["code"] for issue in result["issues"]})

    def test_contract_requires_a_reason_when_high_value_evidence_is_not_used(self):
        fixture = load_fixture()
        fixture["edit"]["beats"][3]["asset"] = "site_context"
        fixture["edit"]["beats"][3]["shots"][0]["asset_id"] = "site_context"

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("UNUSED_HIGH_VALUE_EVIDENCE_REASON_MISSING", {issue["code"] for issue in result["issues"]})

    def test_contract_rejects_more_than_twelve_shots(self):
        fixture = load_fixture()
        self.add_result_first_hook(fixture)
        beat = fixture["edit"]["beats"][1]
        beat["shots"] = [
            {
                "asset_id": "before_entry",
                "motion": "static_hold",
                "transition_in": "cut",
                "start_sec": 4.0 + index * 0.25,
                "end_sec": 4.0 + (index + 1) * 0.25,
            }
            for index in range(10)
        ]

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("SHOT_DENSITY_EXCESSIVE", {issue["code"] for issue in result["issues"]})

    def test_contract_requires_explicit_shots_for_every_one_shot_beat(self):
        fixture = load_fixture()
        fixture["edit"]["beats"][1].pop("shots")

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("ONE_SHOT_SHOTS_REQUIRED", {issue["code"] for issue in result["issues"]})

    def test_contract_requires_contextual_caption_chunks_for_every_one_shot_beat(self):
        fixture = load_fixture()
        fixture["edit"]["beats"][1].pop("caption_chunks")

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("ONE_SHOT_CAPTION_CHUNKS_REQUIRED", {issue["code"] for issue in result["issues"]})

    def test_contract_rejects_aggressive_one_shot_photo_motion(self):
        fixture = load_fixture()
        fixture["edit"]["beats"][1]["shots"][0].update(
            {"motion": "problem_shake", "motion_reason": "Make the problem feel urgent."}
        )

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("ONE_SHOT_MOTION_NOT_CALM", {issue["code"] for issue in result["issues"]})

    def test_contract_rejects_abrupt_or_effect_transitions_after_the_first_frame(self):
        for transition in ("cut", "flash_glow"):
            with self.subTest(transition=transition):
                fixture = load_fixture()
                fixture["edit"]["beats"][1]["shots"][0]["transition_in"] = transition

                result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

                self.assertIn("ONE_SHOT_TRANSITION_NOT_CALM", {issue["code"] for issue in result["issues"]})

    def test_contract_locks_the_result_before_result_hook_timing_and_transitions(self):
        fixture = load_fixture()
        fixture["edit"]["beats"][0]["shots"][0]["end_sec"] = 0.8
        fixture["edit"]["beats"][0]["shots"][1]["start_sec"] = 0.8
        fixture["edit"]["beats"][0]["shots"][2]["transition_in"] = "soft_dissolve"

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])
        codes = {issue["code"] for issue in result["issues"]}

        self.assertIn("HOOK_SHOT_TOO_SHORT", codes)
        self.assertIn("HOOK_TRANSITION_SEQUENCE_INVALID", codes)

    def test_contract_keeps_review_proof_still(self):
        fixture = load_fixture()
        review = fixture["edit"]["beats"][6]
        review["motion"] = "review_capture_scroll"
        review["shots"][0].update(
            {"motion": "review_capture_scroll", "motion_reason": "Scroll the review."}
        )

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("REVIEW_PROOF_MUST_HOLD_STILL", {issue["code"] for issue in result["issues"]})

    def test_contract_locks_the_calm_caption_hierarchy_and_single_keyword(self):
        cases = (
            (0, "caption_layout", "size", "large", "HOOK_CAPTION_SIZE_INVALID"),
            (1, "caption_layout", "theme", "proof", "ONE_SHOT_CAPTION_THEME_INVALID"),
            (1, "caption_accent", "enabled", False, "CAPTION_ACCENT_REQUIRED"),
        )
        for beat_index, container, field, value, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                fixture = load_fixture()
                fixture["edit"]["beats"][beat_index][container][field] = value

                result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

                self.assertIn(expected_code, {issue["code"] for issue in result["issues"]})

        fixture = load_fixture()
        fixture["edit"]["beats"][1]["caption_emphasis"] = ["Daily", "obstruction"]

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("CAPTION_EMPHASIS_DENSITY_INVALID", {issue["code"] for issue in result["issues"]})

    def test_contract_rejects_small_non_hook_captions_that_shrink_during_the_story(self):
        fixture = load_fixture()
        fixture["edit"]["beats"][1]["caption_layout"].update({"size": "small", "min_font_px": 36})

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("ONE_SHOT_BODY_CAPTION_SIZE_INCONSISTENT", {issue["code"] for issue in result["issues"]})

    def test_contract_rejects_an_accent_that_starts_before_the_spoken_keyword(self):
        fixture = load_fixture()
        beat = fixture["edit"]["beats"][1]
        beat["caption_emphasis"] = ["attention"]
        beat["caption_accent"] = {"enabled": True, "style": "event", "start_sec": 4.2}

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("CAPTION_ACCENT_VOICE_SYNC_INVALID", {issue["code"] for issue in result["issues"]})

    def test_contract_allows_numeric_product_display_text_only_when_it_matches_the_spoken_words(self):
        fixture = load_fixture()
        chunk = fixture["edit"]["beats"][0]["caption_chunks"][0]
        chunk["text"] = "초슬림 삼 연동 중문"
        chunk["display_text"] = "초슬림 3연동중문"
        fixture["edit"]["beats"][0]["narration_ref"] = "초슬림 삼 연동 중문"

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertNotIn("CAPTION_DISPLAY_TEXT_MISMATCH", {issue["code"] for issue in result["issues"]})

        chunk["display_text"] = "초슬림 4연동중문"
        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])
        self.assertIn("CAPTION_DISPLAY_TEXT_MISMATCH", {issue["code"] for issue in result["issues"]})

    def test_contract_keeps_the_completed_result_visible_at_the_end(self):
        fixture = load_fixture()
        final_shot = fixture["edit"]["beats"][-1]["shots"][-1]
        final_shot["asset_id"] = "after_wide"
        final_shot["start_sec"] = 30.0

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("FINAL_RESULT_DWELL_INVALID", {issue["code"] for issue in result["issues"]})

    def test_contract_requires_review_emphasis_evidence(self):
        fixture = load_fixture()
        self.add_result_first_hook(fixture)
        fixture["edit"]["beats"][6].pop("review_emphasis")

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("REVIEW_EMPHASIS_MISSING", {issue["code"] for issue in result["issues"]})

    def test_contract_rejects_review_emphasis_quote_missing_from_source(self):
        fixture = load_fixture()
        self.add_result_first_hook(fixture)
        self.add_review_emphasis(fixture, quote="A recommendation the customer never wrote")

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("REVIEW_EMPHASIS_QUOTE_NOT_IN_SOURCE", {issue["code"] for issue in result["issues"]})

    def test_contract_rejects_review_emphasis_outside_the_review_beat(self):
        fixture = load_fixture()
        self.add_result_first_hook(fixture)
        self.add_review_emphasis(fixture)
        fixture["edit"]["beats"][6]["review_emphasis"]["end_sec"] = 40.0

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("REVIEW_EMPHASIS_TIME_INVALID", {issue["code"] for issue in result["issues"]})

    def test_contract_rejects_review_emphasis_outside_the_capture(self):
        fixture = load_fixture()
        self.add_result_first_hook(fixture)
        self.add_review_emphasis(fixture)
        fixture["edit"]["beats"][6]["review_emphasis"]["segments"][0]["width_pct"] = 120.0

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("REVIEW_EMPHASIS_SEGMENT_INVALID", {issue["code"] for issue in result["issues"]})

    def test_contract_requires_the_review_underline_to_draw_immediately(self):
        fixture = load_fixture()
        review = fixture["edit"]["beats"][6]
        review["review_emphasis"].update({"start_sec": 25.0, "draw_duration_sec": 1.5})

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("REVIEW_EMPHASIS_NOT_IMMEDIATE", {issue["code"] for issue in result["issues"]})

    def test_contract_rejects_an_unknown_caption_theme(self):
        fixture = load_fixture()
        fixture["edit"]["beats"][0]["caption_layout"]["theme"] = "banana"

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("CAPTION_THEME_UNSUPPORTED", {issue["code"] for issue in result["issues"]})

    def test_fixture_tts_hash_matches_canonical_narration(self):
        fixture = load_fixture()

        canonical_narration = canonical_tts_input_narration(fixture["edit"])
        actual_hash = hashlib.sha256(canonical_narration.encode("utf-8")).hexdigest()

        self.assertEqual(actual_hash, fixture["edit"]["audio_plan"]["tts_text_sha256"])

    def test_contract_rejects_malformed_tts_evidence_hashes(self):
        for field in ("tts_text_sha256", "final_voice_sha256"):
            with self.subTest(field=field):
                fixture = load_fixture()
                fixture["edit"]["audio_plan"][field] = "A" * 64

                result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

                self.assertFalse(result["ok"])
                self.assertIn("TTS_EVIDENCE_HASH_INVALID", {issue["code"] for issue in result["issues"]})

    def test_contract_rejects_visual_preroll_before_narration(self):
        fixture = load_fixture()
        beat = fixture["edit"]["beats"][1]
        beat["time"][0] = beat["narration_start_sec"] - 0.051

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertFalse(result["ok"])
        self.assertIn("VISUAL_AHEAD_OF_VOICE", {issue["code"] for issue in result["issues"]})

    def test_contract_rejects_caption_preroll_before_narration(self):
        fixture = load_fixture()
        beat = fixture["edit"]["beats"][1]
        beat["caption_start_sec"] = beat["narration_start_sec"] - 0.01

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertFalse(result["ok"])
        self.assertIn("CAPTION_AHEAD_OF_VOICE", {issue["code"] for issue in result["issues"]})

    def test_contract_rejects_fake_review_proof_and_repeated_filler(self):
        fixture = load_fixture()
        fixture["edit"]["beats"][6]["proof_asset_type"] = "generated_review_card"
        for beat in fixture["edit"]["beats"][1:4]:
            beat["asset_id"] = "photo_before_01"
            beat["asset"] = "before_entry"
            beat["time"] = [beat["time"][0], beat["time"][1] + 4]

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertFalse(result["ok"])
        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("REVIEW_PROOF_NOT_ACTUAL_CAPTURE", codes)
        self.assertIn("REPEATED_PHOTO_FILLER", codes)

    def test_preflight_rejects_slow_sleepy_voice_below_the_documented_floor(self):
        fixture = load_fixture()
        fixture["edit"]["audio_plan"]["sync_policy"]["raw_tts_duration_sec"] = 70.0
        fixture["edit"]["audio_plan"]["sync_policy"]["final_voice_duration_sec"] = 70.0

        result = validate_html_preflight(
            fixture["planning"],
            fixture["edit"],
            require_one_shot_contract=True,
        )

        self.assertFalse(result["ok"])
        self.assertIn("TOTAL_VOICE_CPS_TOO_LOW", {issue["code"] for issue in result["issues"]})

    def test_preflight_rejects_voice_above_the_one_shot_speed_ceiling(self):
        fixture = load_fixture()
        fixture["edit"]["audio_plan"]["sync_policy"]["raw_tts_duration_sec"] = 12.0
        fixture["edit"]["audio_plan"]["sync_policy"]["final_voice_duration_sec"] = 12.0

        result = validate_html_preflight(
            fixture["planning"],
            fixture["edit"],
            require_one_shot_contract=True,
        )

        self.assertFalse(result["ok"])
        self.assertIn("TOTAL_VOICE_CPS_TOO_HIGH", {issue["code"] for issue in result["issues"]})

    def test_preflight_counts_all_actual_review_captures_not_only_the_literal_asset_name(self):
        fixture = load_fixture()
        fixture["planning"]["scenes"][1]["visual_source"]["source_kind"] = "actual_review_capture"
        fixture["edit"]["beats"][1]["source_kind"] = "actual_review_capture"
        fixture["edit"]["beats"][1]["asset"] = "review_initial_capture"
        fixture["edit"]["beats"][1]["asset_id"] = "review_initial_capture_01"

        result = validate_html_preflight(
            fixture["planning"],
            fixture["edit"],
            require_one_shot_contract=True,
        )

        self.assertFalse(result["ok"])
        self.assertIn("DUPLICATE_REVIEW_CAPTURE", {issue["code"] for issue in result["issues"]})

    def test_contract_rejects_an_overlong_review_capture_scene(self):
        fixture = load_fixture()
        review_beat = fixture["edit"]["beats"][6]
        review_beat["time"] = [24.0, 31.0]

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertFalse(result["ok"])
        self.assertIn("REVIEW_PROOF_DWELL_TOO_LONG", {issue["code"] for issue in result["issues"]})

    def test_contract_requires_standard_script_srt_and_tts_provenance_artifacts(self):
        cases = (
            ("script", "narration.txt", "SCRIPT_ARTIFACT_INVALID"),
            ("srt", "captions.txt", "SRT_ARTIFACT_INVALID"),
            ("tts_generation_report", "", "TTS_PROVENANCE_MISSING"),
        )
        for field, value, expected_code in cases:
            with self.subTest(field=field):
                fixture = load_fixture()
                fixture["edit"]["source"][field] = value

                result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

                self.assertFalse(result["ok"])
                self.assertIn(expected_code, {issue["code"] for issue in result["issues"]})

    def test_contract_does_not_force_context_or_measurement_filler_for_a_time_lapse_review(self):
        fixture = load_fixture()
        fixture["planning"]["writer_brief"]["story_mode"] = "time_lapse_review"
        fixture["planning"]["scenes"] = [
            scene
            for scene in fixture["planning"]["scenes"]
            if scene["narrative_role"] not in {"context", "choice_turn"}
        ]
        fixture["edit"]["beats"] = [
            beat
            for beat in fixture["edit"]["beats"]
            if beat["narrative_role"] not in {"context", "choice_turn"}
        ]
        fixture["edit"]["asset_evidence"]["measure"]["unused_reason"] = (
            "The time-lapse review makes no measurement claim."
        )

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertTrue(result["ok"], result["issues"])

    def test_contract_rejects_an_opening_that_waits_too_long_to_turn(self):
        fixture = load_fixture()
        fixture["edit"]["beats"][0]["time"] = [0.0, 4.25]

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertFalse(result["ok"])
        self.assertIn("OPENING_BEAT_TOO_LONG", {issue["code"] for issue in result["issues"]})

    def test_117_style_regression_is_blocked_before_html(self):
        fixture = load_fixture()
        fixture["planning"]["writer_brief"]["story_mode"] = "time_lapse_review"
        fixture["edit"]["beats"][0]["time"] = [0.0, 4.25]
        fixture["planning"]["scenes"][1]["visual_source"]["source_kind"] = "actual_review_capture"
        fixture["edit"]["beats"][1]["source_kind"] = "actual_review_capture"
        fixture["edit"]["beats"][1]["asset"] = "review_initial_capture"
        fixture["edit"]["beats"][1]["asset_id"] = "review_initial_capture_01"
        fixture["edit"]["beats"][6]["time"] = [24.0, 33.3]
        fixture["edit"]["audio_plan"]["sync_policy"]["raw_tts_duration_sec"] = 70.0
        fixture["edit"]["audio_plan"]["sync_policy"]["final_voice_duration_sec"] = 70.0

        result = validate_html_preflight(
            fixture["planning"],
            fixture["edit"],
            require_one_shot_contract=True,
        )
        codes = {issue["code"] for issue in result["issues"]}

        self.assertFalse(result["ok"])
        self.assertTrue(
            {
                "OPENING_BEAT_TOO_LONG",
                "DUPLICATE_REVIEW_CAPTURE",
                "REVIEW_PROOF_DWELL_TOO_LONG",
                "TOTAL_VOICE_CPS_TOO_LOW",
            }.issubset(codes),
            result["issues"],
        )


if __name__ == "__main__":
    unittest.main()
