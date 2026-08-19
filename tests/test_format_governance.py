import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FormatGovernanceTests(unittest.TestCase):
    def test_production_and_experiment_status_is_consistent_across_entry_docs(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        status = (ROOT / "docs" / "reels_format_status_v1.md").read_text(encoding="utf-8")

        for document in (readme, agents, status):
            self.assertIn("v2: current production", document)
            # v3/v3.1은 성과 검증 전에 중단됐고 엔진 코드도 폐기됐다. 이름만 남겨
            # 과거 패키지 표기를 읽을 수 있게 하고, 근거 없이 되살아나지 않게 한다.
            self.assertIn("v3: discontinued", document)
            self.assertIn("v3.1: discontinued", document)
            self.assertNotIn("v3: experimental", document)
        self.assertIn("Instagram", status)
        self.assertIn("Naver Clip", status)
        self.assertIn("공통 안전·제작 엔진", status)

    def test_committed_format_status_preserves_v2_and_does_not_change_d026(self):
        status = (ROOT / "docs" / "reels_format_status_v1.md").read_text(encoding="utf-8")

        self.assertIn("v3 / v3.1 중단 기록", status)
        self.assertIn("한 번도 커밋되지 않은 채", status)
        self.assertIn("v2 production 규칙", status)
        self.assertIn("D-026 의미 일치 gate", status)

    def test_project_brand_adapter_distinguishes_central_design_from_video_exceptions(self):
        adapter = (ROOT / "docs" / "brand" / "PROJECT_BRAND_ADAPTER.md").read_text(encoding="utf-8")

        self.assertIn("Editorial Showroom", adapter)
        self.assertIn("Ink", adapter)
        self.assertIn("Forest", adapter)
        self.assertIn("Tmoney RoundWind ExtraBold", adapter)
        self.assertIn("Pretendard Variable", adapter)
        self.assertIn("v2 legacy", adapter)
        self.assertIn("변동 claim", adapter)
        self.assertIn("EVIDENCE_REGISTER.md", adapter)


if __name__ == "__main__":
    unittest.main()
