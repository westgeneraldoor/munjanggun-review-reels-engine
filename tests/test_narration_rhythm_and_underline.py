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


class NarrationRhythmIsNotGatedTest(unittest.TestCase):
    """문장 리듬을 하드 게이트로 만들면 훅이 조각난다. 실제로 그렇게 됐다.

    최단/평균 비율을 차단 조건으로 걸었더니 작가 모델은 글이 아니라 비율을 고쳤고,
    가장 싸게 짧은 문장을 얻는 자리인 훅이 세 조각으로 쪼개졌다. 사장님 판정은
    차단된 쪽이 더 낫다는 것이었다. 다시 게이트로 만들지 않도록 여기 고정한다.
    """

    # 비율 0.77. 예전 게이트가 막았고, 사람은 이쪽이 낫다고 했다.
    BLOCKED_BUT_BETTER = {
        "event": "중문을 달고 나니, 설치 전과 비교해 외부 소음이 달라졌습니다.",
        "problem": "설치 전 현관은 이렇게 열려 있었습니다.",
        "resolution": "약속한 시간에 맞춰 방문해 깔끔하게 시공해 주셨습니다.",
        "felt_result": "중문을 설치한 뒤에는 외부 소음이 확실히 줄었다고 했습니다.",
        "review_proof": "외부 소음이 줄었다는 실제 후기입니다.",
    }

    # 비율 0.51. 예전 게이트를 통과했고, 훅이 무슨 말인지 알 수 없다.
    PASSED_BUT_WORSE = dict(
        BLOCKED_BUT_BETTER,
        event="하나하나 꼼꼼했습니다. 열려 있었습니다. 이렇게 달라졌습니다.",
    )

    def assert_no_rhythm_verdict(self, narration):
        fixture = load_fixture()
        set_narration(fixture, narration)

        result = validate_review_reels_one_shot_contract(fixture["planning"], fixture["edit"])

        self.assertFalse(
            any(code.startswith("NARRATION_RHYTHM") for code in issue_codes(result)),
            "문장 리듬은 자동 차단 대상이 아니다. docs/review_reels_content_standard_v1.md 참고.",
        )

    def test_uniform_sentence_lengths_are_not_blocked_by_the_engine(self):
        self.assert_no_rhythm_verdict(self.BLOCKED_BUT_BETTER)

    def test_a_shredded_hook_gains_nothing_from_the_engine_either(self):
        self.assert_no_rhythm_verdict(self.PASSED_BUT_WORSE)


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
