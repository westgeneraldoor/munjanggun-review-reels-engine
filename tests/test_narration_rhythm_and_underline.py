"""D-028 낭독 리듬 게이트와 리뷰 밑줄 정렬 계약 테스트.

120번 실전에서 자동 QA를 모두 통과했는데도 사람이 보자마자 두 가지가 걸렸다.

1. 모든 문장 길이가 균일해 낭독처럼 들렸다.
2. 인용문이 두 줄에 걸쳐 있는데 밑줄 segment가 하나뿐이라 엉뚱한 줄에 그어졌다.

두 결함 모두 기존 검사에는 걸리지 않았으므로 여기서 계약으로 고정한다.
"""

import json
import unittest
from pathlib import Path

from video_engine_v2.reels_qa import (
    validate_review_reels_one_shot_contract,
)


FIXTURE = Path(__file__).parent / "fixtures" / "review_reels_one_shot_valid.json"


def load_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def issue_codes(result):
    return {issue["code"] for issue in result["issues"]}


def set_narration(fixture, sentences_by_role):
    for beat in fixture["edit"]["beats"]:
        role = beat.get("narrative_role") or beat.get("phase")
        if role in sentences_by_role:
            beat["narration_ref"] = sentences_by_role[role]


class NarrationRhythmTest(unittest.TestCase):
    """D-028: 본문에 확 짧은 문장이 하나도 없으면 낭독이 된다."""

    # 120번이 실제로 만든 내레이션. 문장이 전부 17~27자로 균일하다.
    MONOTONE = {
        "event": "중문을 달고 나니, 설치 전과 비교해 외부 소음이 달라졌습니다.",
        "problem": "설치 전 현관은 이렇게 열려 있었습니다.",
        "resolution": "약속한 시간에 맞춰 방문해 깔끔하게 시공해 주셨습니다.",
        "felt_result": "중문을 설치한 뒤에는 외부 소음이 확실히 줄었다고 했습니다.",
        "review_proof": "외부 소음이 줄었다는 실제 후기입니다.",
    }

    # 118 골든. `여기는 달랐습니다.`라는 9자 문장이 리듬을 만든다.
    GOLDEN = {
        "event": "새 집에 놓을 첫 중문, 견적마다 비싼 것부터 권하더군요.",
        "problem": "리뷰를 하나하나 읽어가며 여러 곳을 찾았지만, 무조건 비싼 것만 추천했습니다.",
        "resolution": "여기는 달랐습니다. 직접 재보더니, 가격이 아니라 우리 집에 맞는 걸 권했습니다.",
        "felt_result": "소음 줄여달라는 부탁도 기꺼이 들어주셨고, 뒷정리까지 깔끔했습니다.",
        "review_proof": "그 자리에서 놀랐다는 말이, 리뷰에 그대로 남아 있습니다.",
    }

    def test_uniform_sentence_lengths_are_rejected_as_monotone_narration(self):
        fixture = load_fixture()
        set_narration(fixture, self.MONOTONE)

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("NARRATION_RHYTHM_MONOTONE", issue_codes(result))

    def test_golden_sample_rhythm_is_accepted(self):
        fixture = load_fixture()
        set_narration(fixture, self.GOLDEN)

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertNotIn("NARRATION_RHYTHM_MONOTONE", issue_codes(result))

    def test_the_fixed_cta_wording_cannot_rescue_a_monotone_body(self):
        """CTA는 고정 문구라 리듬 판정에서 제외한다."""
        fixture = load_fixture()
        set_narration(fixture, self.MONOTONE)
        set_narration(fixture, {"cta": "네."})

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("NARRATION_RHYTHM_MONOTONE", issue_codes(result))


class ReviewUnderlineAlignmentTest(unittest.TestCase):
    """인용문이 화면에서 몇 줄이든, 밑줄 segment가 그 줄을 그대로 받아써야 한다."""

    QUOTE = "외부 소음이 확실히 줄어들어 방음 효과를 체감하고 있습니다"

    def bind_quote(self, fixture):
        fixture["planning"]["review_source"]["text"] = (
            "중문을 설치한 후에는 " + self.QUOTE + ". 집 안이 한층 더 넓어졌습니다."
        )
        fixture["planning"]["review_source"]["review_quote_for_proof"] = self.QUOTE
        fixture["planning"]["writer_brief"]["review_quote_for_proof"] = self.QUOTE

    def emphasis(self, fixture, segments):
        review_beat = fixture["edit"]["beats"][6]
        review_beat["review_emphasis"] = {
            "quote": self.QUOTE,
            "start_sec": 24.05,
            "end_sec": 26.2,
            "draw_duration_sec": 0.15,
            "segments": segments,
        }

    def test_single_segment_cannot_cover_a_quote_that_wraps_onto_two_lines(self):
        """120번의 실제 결함. 두 줄짜리 인용문에 segment 하나만 줬다."""
        fixture = load_fixture()
        self.bind_quote(fixture)
        self.emphasis(fixture, [{"left_pct": 8.0, "top_pct": 58.0, "width_pct": 84.0}])

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("REVIEW_EMPHASIS_SEGMENT_TEXT_MISMATCH", issue_codes(result))

    def test_segments_that_spell_out_the_whole_quote_are_accepted(self):
        fixture = load_fixture()
        self.bind_quote(fixture)
        self.emphasis(fixture, [
            {"left_pct": 8.0, "top_pct": 61.0, "width_pct": 84.0, "line_text": "외부 소음이 확실히 줄어들어 방음 효과를"},
            {"left_pct": 8.0, "top_pct": 65.0, "width_pct": 40.0, "line_text": "체감하고 있습니다"},
        ])

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertNotIn("REVIEW_EMPHASIS_SEGMENT_TEXT_MISMATCH", issue_codes(result))
        self.assertNotIn("REVIEW_EMPHASIS_SEGMENT_ORDER_INVALID", issue_codes(result))

    def test_segments_must_run_down_the_capture_in_reading_order(self):
        fixture = load_fixture()
        self.bind_quote(fixture)
        self.emphasis(fixture, [
            {"left_pct": 8.0, "top_pct": 65.0, "width_pct": 84.0, "line_text": "외부 소음이 확실히 줄어들어 방음 효과를"},
            {"left_pct": 8.0, "top_pct": 61.0, "width_pct": 40.0, "line_text": "체감하고 있습니다"},
        ])

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("REVIEW_EMPHASIS_SEGMENT_ORDER_INVALID", issue_codes(result))

    def test_line_text_that_is_not_part_of_the_quote_is_rejected(self):
        fixture = load_fixture()
        self.bind_quote(fixture)
        self.emphasis(fixture, [
            {"left_pct": 8.0, "top_pct": 61.0, "width_pct": 84.0, "line_text": "설치기사님이 매우 친절하시고"},
            {"left_pct": 8.0, "top_pct": 65.0, "width_pct": 40.0, "line_text": "작업 하나하나 꼼꼼하게"},
        ])

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertIn("REVIEW_EMPHASIS_SEGMENT_TEXT_MISMATCH", issue_codes(result))


if __name__ == "__main__":
    unittest.main()
