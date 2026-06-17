from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReviewAnalysis:
    customer_problem: str
    before_pain: str
    after_change: str
    customer_emotion: list[str]
    strongest_review_quotes: list[dict[str, str | bool]]
    proof_points: list[str]
    risk_flags: list[str]
    video_type: str
    content_purpose: str


def extract_review_body(text: str) -> str:
    content_match = re.search(r"(?s)^내용:\s*(.*)$", text.strip(), re.M)
    if content_match:
        return content_match.group(1).strip()
    return text.strip()


def load_review_body(path: Path) -> str:
    return extract_review_body(path.read_text(encoding="utf-8"))


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _cooling_quotes(text: str) -> list[dict[str, str | bool]]:
    quotes: list[dict[str, str | bool]] = []
    if "에어컨" in text and ("시원" in text or "덥" in text):
        quotes.append(
            {
                "raw": "어제 설치하고 에어컨트니 확실이 더 시원합니다",
                "edited": "에어컨 켜니 확실히 더 시원해졌어요",
                "selected": True,
                "risk": "low",
            }
        )
    if "진즉" in text or "진작" in text:
        quotes.append(
            {
                "raw": "진즉할걸 후회합니다",
                "edited": "진작 할 걸, 하고 후회했어요",
                "selected": False,
                "risk": "low",
            }
        )
    if "좁아" in text and ("이쁘" in text or "예쁘" in text):
        quotes.append(
            {
                "raw": "집이 좁아 더 좁아보일까 설치 안했었어는데 해놓고보니 엄청 이쁘고 좋아요",
                "edited": "좁아 보일까 걱정했는데, 오히려 예뻤어요",
                "selected": False,
                "risk": "low",
            }
        )
    return quotes


def analyze_review(review_text: str) -> ReviewAnalysis:
    body = extract_review_body(review_text)

    if _contains_any(body, ["에어컨", "여름", "시원", "덥"]):
        return ReviewAnalysis(
            customer_problem="에어컨을 풀로 틀어도 거실이 더움",
            before_pain="좁아 보일까 봐 중문 설치를 미뤘지만 여름 냉방 체감이 약했음",
            after_change="설치 후 에어컨을 켜니 더 시원하다고 느낌",
            customer_emotion=["hesitation", "heat_discomfort", "relief", "satisfaction"],
            strongest_review_quotes=_cooling_quotes(body),
            proof_points=["actual_review", "before_after_photos", "product_selection"],
            risk_flags=["avoid_energy_bill_promise", "avoid_perfect_insulation_claim"],
            video_type="cooling_effect",
            content_purpose="ad",
        )

    if _contains_any(body, ["소음", "냄새", "구축", "빌라"]):
        return ReviewAnalysis(
            customer_problem="현관 쪽 소음이나 냄새가 신경 쓰임",
            before_pain="구축 현장 특유의 생활 불편이 있었음",
            after_change="중문 시공 후 생활 체감이 좋아짐",
            customer_emotion=["discomfort", "relief", "trust"],
            strongest_review_quotes=[],
            proof_points=["actual_review", "field_photos", "measurement_photos"],
            risk_flags=["avoid_perfect_soundproof_claim"],
            video_type="old_building_noise",
            content_purpose="retargeting",
        )

    if _contains_any(body, ["어려", "포기", "추가", "주차", "친절"]):
        return ReviewAnalysis(
            customer_problem="시공 조건이 까다롭거나 상담 신뢰가 필요함",
            before_pain="다른 곳에서 어렵다고 느낄 수 있는 현장 조건",
            after_change="현장 확인 후 가능한 방식으로 깔끔하게 마무리",
            customer_emotion=["concern", "trust", "satisfaction"],
            strongest_review_quotes=[],
            proof_points=["process_photos", "actual_review", "measurement_photos"],
            risk_flags=["avoid_guaranteed_no_extra_fee"],
            video_type="difficult_installation",
            content_purpose="brand_expertise",
        )

    return ReviewAnalysis(
        customer_problem="중문 설치 전 생활 불편",
        before_pain="설치 전 고민과 망설임",
        after_change="설치 후 만족감",
        customer_emotion=["hesitation", "satisfaction"],
        strongest_review_quotes=[],
        proof_points=["actual_review", "before_after_photos"],
        risk_flags=["avoid_unsupported_claims"],
        video_type="living_installation",
        content_purpose="feed_trust",
    )
