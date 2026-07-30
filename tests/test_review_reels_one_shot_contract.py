import json
import unittest
from pathlib import Path

from video_engine_v2.reels_qa import validate_html_preflight, validate_review_reels_one_shot_contract


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
