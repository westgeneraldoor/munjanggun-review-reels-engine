import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_engine_v2.one_shot_tts import OneShotTTSViolation, generate_one_shot_tts


SCRIPT = """---
review_id: 4997754305
review_number: 4997754305
product_order_number: 2026050936782031
source_file: 117_한달사용후변화.txt
review_sequence: 117
created: 2026-07-31
content_type: 사연극
status: html_preview_only
---

# 같은 고객님이 한 달 뒤 남긴 두 번째 후기

## 스크립트

### [HOOK] 0~3초
한 달 뒤 또 남긴 별 다섯
> 내레이션: 같은 고객님이 한 달 뒤, 별 다섯 개를 또 남겼습니다.

### [SCENE] 3~7초
처음부터 달라진 집 분위기
> 내레이션: 처음에는 집 분위기가 달라졌다고 했고요.

### [CONFLICT] 7~11초
진짜 평가는 한 달 뒤
> 내레이션: 진짜 궁금한 건 한 달을 써본 뒤였습니다.

### [SOLUTION] 11~16초
여전히 부드러운 슬라이딩
> 내레이션: 슬라이딩은 여전히 부드럽고 소음도 적었습니다.

### [TWIST] 16~21초
채광까지 밝아진 현관
> 내레이션: 채광이 좋아 실내도 한층 밝아졌습니다.

### [CLOSE] 21~25초
한 달 뒤에도 이어진 만족
> 내레이션: 한 달 뒤에도 만족은 그대로였습니다. 문장군 리뷰에서 가져왔어요.

## 캡션
중문은 설치 직후보다 한 달을 직접 써본 뒤의 평가가 더 궁금합니다.
이번 고객님은 설치 직후 달라진 집 분위기와 은은한 브론즈 유리를 먼저 이야기했습니다.
그리고 한 달 뒤에도 슬라이딩이 부드럽고 소음이 적어 만족스럽다는 후기를 다시 남겼습니다.
강화유리는 튼튼하게 느껴졌고 채광이 좋아 실내도 한층 밝아졌다고 했습니다.
설치 직후의 첫인상과 한 달 뒤의 생활 만족이 함께 이어진 실제 후기였습니다.
비슷한 현관을 고민하고 있다면 저장해 두고 무료 실측으로 우리 집 조건부터 확인해 보세요.

## 해시태그
#문장군 #문장군중문 #문장군시공 #현관중문 #중문시공 #3연동중문 #브론즈유리 #한달사용후기 #무료실측 #방문실측
"""


class OneShotTTSTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.package = Path(self.tempdir.name) / "117_한달사용후변화_20260731_040457"
        self.package.mkdir()
        self.source_text = "한 달 정도 사용해 보니 슬라이딩이 부드럽고 소음이 적어 만족스럽습니다."
        source_hash = hashlib.sha256(self.source_text.encode("utf-8")).hexdigest()
        (self.package / "CANONICAL_PACKAGE_METADATA.json").write_text(
            json.dumps(
                {
                    "schema_version": "review-reel-canonical-package-v1",
                    "workflow": "review_reel_production",
                    "content_id": "117",
                    "lifecycle_state": "photo_reviewed",
                    "approvals": {
                        "photo_checked": True,
                        "pd_plan_approved": False,
                        "html_scope_authorized": False,
                        "mp4_scope_authorized": False,
                    },
                    "identity": {
                        "content_id": "117",
                        "review_text_sha256": source_hash,
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.planning = self.package / "117_gold_planning_recipe.json"
        self.planning.write_text(
            json.dumps(
                {
                    "content_id": "117",
                    "workflow_contract": {
                        "name": "review-reels-one-shot-v2",
                        "html_scope_authorized": True,
                        "mp4_scope_authorized": False,
                    },
                    "review_source": {
                        "canonical_text_sha256": source_hash,
                    },
                    "scenes": [
                        {"narration": "같은 고객님이 한 달 뒤, 별 다섯 개를 또 남겼습니다."},
                        {"narration": "처음에는 집 분위기가 달라졌다고 했고요."},
                        {"narration": "진짜 궁금한 건 한 달을 써본 뒤였습니다."},
                        {"narration": "슬라이딩은 여전히 부드럽고 소음도 적었습니다."},
                        {"narration": "채광이 좋아 실내도 한층 밝아졌습니다."},
                        {"narration": "한 달 뒤에도 만족은 그대로였습니다. 문장군 리뷰에서 가져왔어요."},
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.script = self.package / "117_month_later_gold_v2_script.md"
        self.script.write_text(SCRIPT, encoding="utf-8")

    def fake_voice(self, script_text: str, output_folder: Path, artifact_stem: str) -> Path:
        import generate

        voice = output_folder / f"{artifact_stem}_voice.mp3"
        voice.write_bytes(b"gemini-sulafat")
        report_dir = output_folder / "_work"
        report_dir.mkdir(exist_ok=True)
        report = {
            "schema_version": "review-reel-tts-generation-report-v1",
            "provider": "google_gemini_tts",
            "model": "gemini-3.1-flash-tts-preview",
            "voice": "Sulafat",
            "tts_text_sha256": hashlib.sha256(
                generate.prepare_tts_text(script_text).encode("utf-8")
            ).hexdigest(),
            "voice_relative_path": voice.relative_to(output_folder).as_posix(),
            "voice_bytes": voice.stat().st_size,
            "voice_sha256": hashlib.sha256(voice.read_bytes()).hexdigest(),
            "raw_tts_duration_sec": 27.0,
            "final_voice_duration_sec": 25.0,
        }
        (report_dir / f"{artifact_stem}_tts_generation_report.json").write_text(
            json.dumps(report),
            encoding="utf-8",
        )
        return voice

    def test_generates_standard_srt_and_gemini_voice_without_granting_mp4(self):
        with patch("video_engine_v2.one_shot_tts.generate.generate_voice", side_effect=self.fake_voice):
            result = generate_one_shot_tts(
                package_dir=self.package,
                planning_path=self.planning,
                script_path=self.script,
            )

        self.assertEqual(result["voice"].name, "117_month_later_gold_v2_voice.mp3")
        self.assertEqual(result["srt"].name, "117_month_later_gold_v2.srt")
        self.assertTrue(result["tts_report"].is_file())
        metadata = json.loads(
            (self.package / "CANONICAL_PACKAGE_METADATA.json").read_text(encoding="utf-8")
        )
        self.assertFalse(metadata["approvals"]["html_scope_authorized"])
        self.assertFalse(metadata["approvals"]["mp4_scope_authorized"])

    def test_rejects_a_package_that_has_not_passed_official_photo_review(self):
        metadata_path = self.package / "CANONICAL_PACKAGE_METADATA.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["lifecycle_state"] = "photo_intake_pending"
        metadata["approvals"]["photo_checked"] = False
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        with self.assertRaisesRegex(OneShotTTSViolation, "PHOTO_REVIEW_MISSING"):
            generate_one_shot_tts(
                package_dir=self.package,
                planning_path=self.planning,
                script_path=self.script,
            )

    def test_rejects_planning_narration_that_differs_from_the_script(self):
        planning = json.loads(self.planning.read_text(encoding="utf-8"))
        planning["scenes"][2]["narration"] = "대본에 없는 말입니다."
        self.planning.write_text(json.dumps(planning), encoding="utf-8")

        with self.assertRaisesRegex(OneShotTTSViolation, "SCRIPT_PLANNING_NARRATION_MISMATCH"):
            generate_one_shot_tts(
                package_dir=self.package,
                planning_path=self.planning,
                script_path=self.script,
            )

    def test_never_overwrites_existing_voice_or_srt(self):
        existing = self.package / "117_month_later_gold_v2_voice.mp3"
        existing.write_bytes(b"keep")

        with self.assertRaisesRegex(OneShotTTSViolation, "TTS_ARTIFACT_ALREADY_EXISTS"):
            generate_one_shot_tts(
                package_dir=self.package,
                planning_path=self.planning,
                script_path=self.script,
            )

        self.assertEqual(existing.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
