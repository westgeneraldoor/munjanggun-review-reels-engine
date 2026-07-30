import copy
import json
import unittest
from pathlib import Path

from video_engine_v2.reels_qa import build_status_markdown, validate_html_preflight, validate_review_reels_one_shot_contract


FIXTURE = Path(__file__).parent / "fixtures" / "review_reels_one_shot_valid.json"


def load_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class ReviewReelsOneShotContractTest(unittest.TestCase):
    def test_anonymized_gold_structure_passes_the_one_shot_contract(self):
        fixture = load_fixture()

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertTrue(result["ok"], result["issues"])

    def test_rejects_missing_story_roles_and_a_cta_after_review_proof(self):
        fixture = load_fixture()
        fixture["planning"]["scenes"] = fixture["planning"]["scenes"][:-2]
        fixture["edit"]["beats"] = fixture["edit"]["beats"][:-2]

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("NARRATIVE_ROLE_MISSING", codes)
        self.assertIn("CTA_AFTER_REVIEW_PROOF_MISSING", codes)

    def test_rejects_a_fake_review_card_repeated_photo_filler_and_literal_newline_text(self):
        fixture = load_fixture()
        fixture["edit"]["beats"][6]["proof_asset_type"] = "generated_review_card"
        fixture["edit"]["beats"][0]["caption"] = "현관 동선\\n계속 걸렸다면?"
        for beat in fixture["edit"]["beats"][1:4]:
            beat["asset_id"] = "photo_before_01"
            beat["asset"] = "before_entry"
            beat["time"] = [beat["time"][0], beat["time"][1] + 4]

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("REVIEW_PROOF_NOT_ACTUAL_CAPTURE", codes)
        self.assertIn("REPEATED_PHOTO_FILLER", codes)
        self.assertIn("CAPTION_LITERAL_NEWLINE", codes)

    def test_rejects_caption_ahead_of_voice_or_without_readability_evidence(self):
        fixture = load_fixture()
        fixture["edit"]["beats"][0]["caption_start_sec"] = 0
        fixture["edit"]["beats"][0]["narration_start_sec"] = 0.2
        fixture["edit"]["beats"][1].pop("caption_layout")

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("CAPTION_AHEAD_OF_VOICE", codes)
        self.assertIn("CAPTION_LAYOUT_EVIDENCE_MISSING", codes)

    def test_strict_preflight_uses_the_contract_and_status_records_html_only_scope(self):
        fixture = load_fixture()

        result = validate_html_preflight(fixture["planning"], fixture["edit"], require_one_shot_contract=True)
        status = build_status_markdown(
            review_id="fixture-001",
            variant_id="one-shot-v1",
            photo_checked=True,
            one_shot_html_scope_authorized=True,
            mp4_allowed=False,
        )

        self.assertTrue(result["ok"], result["issues"])
        self.assertIn("one_shot_html_scope_authorized: true", status)
        self.assertIn("mp4_allowed: false", status)


if __name__ == "__main__":
    unittest.main()
