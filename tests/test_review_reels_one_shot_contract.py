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
    def test_anonymized_contract_passes_the_strict_html_preflight(self):
        fixture = load_fixture()

        result = validate_html_preflight(
            fixture["planning"],
            fixture["edit"],
            require_one_shot_contract=True,
        )

        self.assertTrue(result["ok"], result["issues"])

    def test_contract_never_grants_mp4_scope(self):
        fixture = load_fixture()
        fixture["planning"]["workflow_contract"]["mp4_scope_authorized"] = True

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertFalse(result["ok"])
        self.assertIn("MP4_SCOPE_MUST_REMAIN_UNAUTHORIZED", {issue["code"] for issue in result["issues"]})

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
