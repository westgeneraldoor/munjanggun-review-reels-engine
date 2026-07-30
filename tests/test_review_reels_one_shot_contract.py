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


if __name__ == "__main__":
    unittest.main()
