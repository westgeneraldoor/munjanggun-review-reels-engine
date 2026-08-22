import unittest
import hashlib
import json
import re
import sys
import tempfile
import types
from unittest import mock
from pathlib import Path

sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *args, **kwargs: None))
google_module = sys.modules.setdefault("google", types.ModuleType("google"))
google_module.genai = types.SimpleNamespace(Client=object)
sys.modules.setdefault("google.genai", google_module.genai)
google_module.genai.types = types.SimpleNamespace(
    GenerateContentConfig=object,
    SpeechConfig=object,
    VoiceConfig=object,
    PrebuiltVoiceConfig=object,
)
sys.modules.setdefault("google.genai.types", google_module.genai.types)
import generate
from generate import (
    apply_review_metadata,
    build_tts_prompt,
    count_script_narration_chars,
    extract_tts_text,
    generate_srt,
    get_source_key,
    get_reference_speed_target_seconds,
    get_artifact_stem,
    get_artifact_stem_from_script_path,
    normalize_tts_text,
    normalize_leading_silence_mp3,
    parse_review_record,
    prepare_tts_text,
    save_script,
    save_srt,
    split_atempo_filters,
    validate_script,
    write_tts_generation_report,
)


VALID_SCRIPT = """---
review_id: 일단 고양이 키
created: 2026-06-08
content_type: 사연극
---

# 택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님

## 스크립트

### [HOOK] 0~3초
택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님
> 내레이션: 택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님이 계세요.

### [SCENE] 3~7초
평화로운 오후, 벨이 울리고 택배가 도착했습니다
> 내레이션: 평화로운 어느 오후, 택배가 도착했다는 벨소리가 울렸어요.

### [CONFLICT] 7~12초
현관문을 여는 순간, 고양이가 순식간에 사라졌습니다
> 내레이션: 현관문을 열어 택배를 챙기려는데, 그 순간 고양이가 언제 나갔는지 모르게 사라져 버린 겁니다.

### [SOLUTION] 12~18초
다시는 이런 일이 없도록, 중문을 설치하고 마음 편한 일상이 시작됐습니다
> 내레이션: 다시는 이런 일이 없도록, 이 집사님은 중문을 설치하고 마음 편한 일상을 시작하셨어요.

### [TWIST] 18~25초
중문 설치 후 정수기 점검 오신 분이 너무 좋다며 어디서 했냐고 물어봤대요
> 내레이션: 그런데 중문 설치 후 정수기 점검 오신 분이 너무 좋다며 어디서 했냐고 물어보시더래요. 그래서 문장군을 홍보해 드렸다고 합니다.

### [CLOSE] 25~35초
중문이 있을 때와 없을 때의 차이는 써보신 분들은 느끼시리라 생각되네요.
> 내레이션: "중문이 있을 때와 없을 때의 차이는 써보신 분들은 느끼시리라 생각되네요.^^ 전 너무 만족하며 살고 있습니다." 문장군 리뷰에서 가져왔어요.

## 캡션
택배 하나 받으러 나갔다가 고양이를 잃어버릴 뻔한 집사님 이야기예요.
현관문이 열리는 몇 초 사이에 반려동물이 밖으로 나갈 뻔했다는 점이 이 사연의 핵심입니다.
설치 후에는 문 하나가 한 번 더 막아주니 집사님 마음이 훨씬 편해졌다고 해요.
정수기 점검 오신 분까지 어디서 했냐고 물어봤다는 반전도 있었고요.
반려동물과 함께 사는 집이라면 현관 구조를 한번 살펴볼 만합니다.
비슷한 걱정이 있다면 저장해두고, 무료 실측으로 우리 집 구조부터 확인해보세요.

## 해시태그
#문장군 #문장군중문 #문장군시공 #현관중문 #중문시공 #중문인테리어 #현관인테리어 #3연동중문 #슬라이딩중문 #아파트중문 #반려동물 #강아지있는집 #고양이있는집 #펫테리어 #소음차단 #냄새차단 #현관우풍 #중문추천 #무료실측 #인테리어 #아파트인테리어 #리모델링
"""


class ValidateScriptTest(unittest.TestCase):
    def test_accepts_script_ready_for_srt_and_tts(self):
        self.assertEqual(validate_script(VALID_SCRIPT), [])

    def test_rejects_missing_posting_caption_section(self):
        script = re.sub(r"(?s)\n## 캡션\n.*?\n## 해시태그", "\n## 해시태그", VALID_SCRIPT)

        issues = validate_script(script)

        self.assertTrue(any("## 캡션" in issue for issue in issues))

    def test_rejects_missing_posting_hashtag_section(self):
        script = re.sub(r"\n## 해시태그\n.*\Z", "\n", VALID_SCRIPT, flags=re.S)

        issues = validate_script(script)

        self.assertTrue(any("## 해시태그" in issue for issue in issues))

    def test_rejects_thin_posting_caption(self):
        script = re.sub(
            r"(?s)## 캡션\n.*?\n## 해시태그",
            "## 캡션\n이 리뷰를 참고해보세요!\n\n## 해시태그",
            VALID_SCRIPT,
        )

        issues = validate_script(script)

        self.assertTrue(any("최소 5줄" in issue for issue in issues))
        self.assertTrue(any("얕은 요약" in issue for issue in issues))

    def test_rejects_placeholder_caption_text(self):
        script = VALID_SCRIPT.replace(
            "### [HOOK] 0~3초\n택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님",
            "### [HOOK] 0~3초\n[자막 텍스트]",
            1,
        )

        issues = validate_script(script)

        self.assertTrue(any("[자막 텍스트]" in issue for issue in issues))

    def test_rejects_bracket_wrapped_caption_text(self):
        script = VALID_SCRIPT.replace(
            "### [HOOK] 0~3초\n택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님",
            "### [HOOK] 0~3초\n[택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님]",
            1,
        )

        issues = validate_script(script)

        self.assertTrue(any("대괄호" in issue for issue in issues))

    def test_rejects_missing_narration_marker_in_each_section(self):
        script = VALID_SCRIPT.replace("> 내레이션:", "> 나레이션:", 1)

        issues = validate_script(script)

        self.assertTrue(any("[HOOK]" in issue and "내레이션" in issue for issue in issues))

    def test_rejects_brand_term_in_hook_title_and_caption(self):
        script = VALID_SCRIPT.replace(
            "# 택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님",
            "# 문장군 중문 설치 후기",
        ).replace(
            "택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님",
            "문장군 중문 설치 후기",
            1,
        )

        issues = validate_script(script)

        self.assertTrue(any("HOOK" in issue and "브랜드명" in issue for issue in issues))

    def test_allows_review_event_hook_that_names_the_product(self):
        script = VALID_SCRIPT.replace(
            "# 택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님",
            "# 중문 설치 한 달 뒤, 집 분위기가 달라졌습니다",
        ).replace(
            "택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님",
            "중문 설치 한 달 뒤, 집 분위기가 달라졌습니다",
            1,
        ).replace(
            "택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님이 계세요.",
            "중문 설치 한 달 뒤, 집 분위기가 달라졌습니다.",
            1,
        )

        issues = validate_script(script)

        self.assertFalse(any("HOOK" in issue and "금지어" in issue for issue in issues), issues)

    def test_allows_product_term_in_hook_when_it_is_part_of_choice_conflict(self):
        script = VALID_SCRIPT.replace(
            "# 택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님",
            "# 방묘문 고민하던 집, 중문으로 바꾼 이유",
        ).replace(
            "택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님",
            "방묘문 고민하던 집, 중문으로 바꾼 이유",
            1,
        ).replace(
            "택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님이 계세요.",
            "방묘문을 고민하던 집이 중문으로 바꾼 이유가 있습니다.",
            1,
        )

        issues = validate_script(script)

        self.assertFalse(any("HOOK" in issue and "상품명" in issue for issue in issues), issues)

    def test_rejects_product_type_explainer_hook(self):
        script = self._replace_hook("중문 종류 3가지 비교해드립니다")

        issues = validate_script(script)

        self.assertTrue(any("제품 설명형" in issue for issue in issues), issues)

    def test_rejects_product_price_explainer_hook(self):
        script = self._replace_hook("중문 가격 얼마인지 알려드립니다")

        issues = validate_script(script)

        self.assertTrue(any("제품 설명형" in issue for issue in issues), issues)

    def test_rejects_product_benefit_explainer_hook(self):
        script = self._replace_hook("중문 장점 세 가지를 정리해드립니다")

        issues = validate_script(script)

        self.assertTrue(any("제품 설명형" in issue for issue in issues), issues)

    def test_allows_price_to_be_part_of_a_customer_event_hook(self):
        script = self._replace_hook("중문 가격이 걱정됐던 집, 설치 뒤 생각이 달라졌습니다")

        issues = validate_script(script)

        self.assertFalse(any("제품 설명형" in issue for issue in issues), issues)

    def test_rejects_hook_empathy_question_ad_pattern(self):
        script = VALID_SCRIPT.replace(
            "택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님이 계세요.",
            "오래된 구축 빌라에 사시는 분들, 현관 소음 때문에 고통받으셨죠?",
            1,
        )

        issues = validate_script(script)

        self.assertTrue(any("공감 질문형" in issue for issue in issues))

    @staticmethod
    def _replace_hook(hook: str) -> str:
        return VALID_SCRIPT.replace(
            "# 택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님",
            f"# {hook}",
        ).replace(
            "택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님",
            hook,
            1,
        ).replace(
            "택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님이 계세요.",
            hook,
            1,
        )

    def test_warns_hook_empathy_ad_phrase(self):
        script = VALID_SCRIPT.replace(
            "택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님이 계세요.",
            "현관문을 열 때마다 불안한 마음, 많은 분들이 겪습니다.",
            1,
        )

        issues = validate_script(script)

        self.assertTrue(any("[WARN]" in issue and "공감형 광고 표현" in issue for issue in issues))

    def test_rejects_invalid_metadata(self):
        script = VALID_SCRIPT.replace("created: 2026-06-08", "created: 2026/06/08").replace(
            "content_type: 사연극",
            "content_type: FAQ형",
        )

        issues = validate_script(script)

        self.assertTrue(any("created" in issue for issue in issues))
        self.assertTrue(any("content_type" in issue for issue in issues))

    def test_save_script_keeps_caption_and_hashtag_inside_script_md_only(self):
        original_output_dir = generate.OUTPUT_DIR
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                generate.OUTPUT_DIR = Path(temp_dir)

                saved_path = save_script(VALID_SCRIPT + "\n## 캡션\n본문\n\n## 해시태그\n#문장군", "review_999.txt")

                self.assertTrue(saved_path.exists())
                self.assertFalse((saved_path.parent / "caption.txt").exists())
                self.assertFalse((saved_path.parent / "hashtag.txt").exists())
        finally:
            generate.OUTPUT_DIR = original_output_dir

    def test_output_files_use_short_title_type_filenames(self):
        original_output_dir = generate.OUTPUT_DIR
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                generate.OUTPUT_DIR = Path(temp_dir)

                saved_path = save_script(VALID_SCRIPT, "review_999.txt")
                srt_path = save_srt(saved_path, VALID_SCRIPT)
                artifact_stem = "999_택배고양이"

                self.assertEqual(saved_path.name, f"{artifact_stem}_script.md")
                self.assertEqual(srt_path.name, f"{artifact_stem}_subtitle.srt")
                self.assertEqual(get_artifact_stem_from_script_path(saved_path), artifact_stem)
                self.assertFalse((saved_path.parent / "script.md").exists())
                self.assertFalse((saved_path.parent / "subtitle.srt").exists())
        finally:
            generate.OUTPUT_DIR = original_output_dir

    def test_output_uses_review_collection_folder(self):
        original_output_dir = generate.OUTPUT_DIR
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                generate.OUTPUT_DIR = Path(temp_dir)
                record = parse_review_record(
                    """리뷰번호: 4993664075
상품주문번호: 202605303542118
내용: 상담이 편했고 설치도 깔끔해서 만족스럽습니다.
""",
                    generate.BASE_DIR / "reviews" / "inbox_20260609" / "001_상담설치.txt",
                )

                saved_path = save_script(apply_review_metadata(VALID_SCRIPT, record), str(record.source_path), record)

                self.assertEqual(saved_path.parent.parent.name, "inbox_20260609")
                self.assertEqual(saved_path.name, "001_상담설치_script.md")
                self.assertEqual((saved_path.parent / ".source").read_text(encoding="utf-8"), get_source_key(record))
        finally:
            generate.OUTPUT_DIR = original_output_dir

    def test_parse_structured_review_record_keeps_trace_ids(self):
        text = """리뷰번호: 4993664075
상품주문번호: 202605303542118
내용: 상담이 편했고 설치도 깔끔해서 만족스럽습니다.
"""

        record = parse_review_record(text, Path("001_상담설치.txt"))

        self.assertEqual(record.sequence, "001")
        self.assertEqual(record.input_label, "상담설치")
        self.assertEqual(record.review_number, "4993664075")
        self.assertEqual(record.product_order_number, "202605303542118")
        self.assertEqual(record.content, "상담이 편했고 설치도 깔끔해서 만족스럽습니다.")

    def test_parse_structured_review_record_keeps_multiline_content(self):
        text = """리뷰번호: 4926794192
상품주문번호: 2026012634098431
내용:
수리가 되지 않았던 집으로 이사를 오고나서 오래된 방문을 볼 때마다 집 분위기가 신경 쓰였습니다.
문턱제거를 통해 아기 키우는 집이나 로봇청소기 사용에 더 최적화된 집이 되었습니다.
하루만에 집 전체 방문을 교체하고 나니 진작 교체를 할걸 하는 생각도 들었어요.
"""

        record = parse_review_record(text, Path("020_로봇청소구축리모델링.txt"))

        self.assertIn("오래된 방문", record.content)
        self.assertIn("문턱제거", record.content)
        self.assertIn("로봇청소기", record.content)
        self.assertIn("진작 교체", record.content)

    def test_apply_review_metadata_adds_review_and_order_numbers_to_script(self):
        record = parse_review_record(
            """리뷰번호: 4993664075
상품주문번호: 202605303542118
내용: 상담이 편했고 설치도 깔끔해서 만족스럽습니다.
""",
            Path("001_상담설치.txt"),
        )

        script = apply_review_metadata(VALID_SCRIPT, record)

        self.assertIn("review_id: 4993664075", script)
        self.assertIn("review_number: 4993664075", script)
        self.assertIn("product_order_number: 202605303542118", script)
        self.assertIn("source_file: 001_상담설치.txt", script)
        self.assertIn("review_sequence: 001", script)

    def test_generate_srt_uses_caption_text_not_narration(self):
        srt_text = generate_srt(VALID_SCRIPT)

        self.assertIn("택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님", srt_text)
        self.assertIn("평화로운 오후, 벨이 울리고 택배가 도착했습니다", srt_text)
        self.assertNotIn("> 내레이션:", srt_text)
        self.assertNotIn("평화로운 어느 오후, 택배가 도착했다는 벨소리가 울렸어요", srt_text)

    def test_generate_srt_has_six_ordered_entries_under_40_seconds(self):
        srt_text = generate_srt(VALID_SCRIPT)
        entries = [entry for entry in srt_text.strip().split("\n\n") if entry.strip()]

        self.assertEqual(len(entries), 6)
        self.assertTrue(entries[0].startswith("1\n00:00:00,000 --> "))
        self.assertIn("6\n", entries[-1])
        self.assertIn("--> 00:00:", entries[-1])
        self.assertNotIn("00:00:40,", entries[-1])

    def test_extract_tts_text_uses_narration_not_caption(self):
        tts_text = extract_tts_text(VALID_SCRIPT)

        self.assertIn("평화로운 어느 오후, 택배가 도착했다는 벨소리가 울렸어요.", tts_text)
        self.assertIn("문장군 리뷰에서 가져왔어요.", tts_text)
        self.assertNotIn("평화로운 오후, 벨이 울리고 택배가 도착했습니다", tts_text)
        self.assertNotIn("> 내레이션:", tts_text)

    def test_normalize_tts_text_makes_review_quotes_speakable(self):
        text = '중문없이 어찌 살았나 싶을정도로... "전 너무 만족하며 살고 있습니다."'

        normalized = normalize_tts_text(text)

        self.assertIn("중문 없이", normalized)
        self.assertNotIn("...", normalized)
        self.assertNotIn('"', normalized)

    def test_build_tts_prompt_includes_persona_and_normalized_text(self):
        prompt = build_tts_prompt("중문 없이 만족했다고 해요.", "30대 후반 여성. 광고 내레이션처럼 읽지 않는다.")

        self.assertIn("30대 후반 여성", prompt)
        self.assertIn("광고 내레이션처럼 읽지 않는다", prompt)
        self.assertIn("중문 없이 만족했다고 해요.", prompt)
        self.assertIn("그대로 읽어주세요", prompt)

    def test_prepare_tts_text_keeps_full_narration_without_summarizing(self):
        prepared = prepare_tts_text(VALID_SCRIPT)

        self.assertIn("택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님이 계세요.", prepared)
        self.assertIn("평화로운 어느 오후, 택배가 도착했다는 벨소리가 울렸어요.", prepared)
        self.assertIn("문장군 리뷰에서 가져왔어요", prepared)
        self.assertNotIn("> 내레이션:", prepared)

    def test_validate_script_allows_longer_narration_when_content_needs_it(self):
        long_script = VALID_SCRIPT.replace(
            '택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님이 계세요.',
            '택배 가지러 나갔다가 고양이를 잃어버릴 뻔한 집사님이 계세요. 현관문을 열 때마다 불안해서 매번 고양이가 어디 있는지 확인해야 했고, 그 짧은 순간이 계속 신경 쓰였다고 합니다.',
        )

        issues = validate_script(long_script)

        self.assertFalse(any(issue.startswith("[FAIL]") for issue in issues))

    def test_reference_script_narration_length_is_measured(self):
        self.assertEqual(count_script_narration_chars(VALID_SCRIPT), 244)

    def test_reference_speed_target_seconds_scales_with_narration_length(self):
        reference_seconds = get_reference_speed_target_seconds("가" * 244)
        longer_seconds = get_reference_speed_target_seconds("가" * 350)

        self.assertAlmostEqual(reference_seconds, 35.01, places=1)
        self.assertGreater(longer_seconds, reference_seconds)

    def test_split_atempo_filters_keeps_each_filter_in_ffmpeg_safe_range(self):
        filters = split_atempo_filters(2.4)

        self.assertEqual(filters, [2.0, 1.2])

    def test_speed_adjust_mp3_slows_down_audio_when_raw_tts_is_shorter_than_target(self):
        with mock.patch("generate.get_audio_duration_seconds", return_value=22.0), mock.patch(
            "imageio_ffmpeg.get_ffmpeg_exe", return_value="ffmpeg"
        ), mock.patch("generate.subprocess.run") as run:
            generate.speed_adjust_mp3(Path("raw.mp3"), Path("final.mp3"), target_seconds=26.0)

        command = run.call_args.args[0]
        filter_arg = command[command.index("-filter:a") + 1]
        self.assertEqual(filter_arg, "atempo=0.846")

    def test_leading_silence_normalization_trims_excess_without_regenerating_speech(self):
        import imageio_ffmpeg

        with tempfile.TemporaryDirectory() as tempdir:
            voice = Path(tempdir) / "voice.mp3"
            subprocess_result = generate.subprocess.run(
                [
                    imageio_ffmpeg.get_ffmpeg_exe(),
                    "-y",
                    "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono:d=0.5",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=24000:duration=1.0",
                    "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1",
                    "-codec:a", "libmp3lame",
                    "-q:a", "2",
                    str(voice),
                ],
                capture_output=True,
            )
            self.assertEqual(subprocess_result.returncode, 0, subprocess_result.stderr)
            before_duration = generate.get_audio_duration_seconds(voice)

            result = normalize_leading_silence_mp3(voice)
            after_duration = generate.get_audio_duration_seconds(voice)

        self.assertTrue(result["applied"])
        self.assertGreaterEqual(result["detected_leading_silence_sec"], 0.45)
        self.assertGreaterEqual(result["normalized_leading_silence_sec"], 0.10)
        self.assertLessEqual(result["normalized_leading_silence_sec"], 0.25)
        self.assertGreater(before_duration - after_duration, 0.20)
        self.assertLess(before_duration - after_duration, 0.45)

    def test_tts_generation_report_binds_gemini_voice_text_duration_and_file_hashes(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output = Path(tempdir)
            voice = output / "fixture_voice.mp3"
            voice.write_bytes(b"approved-gemini-voice")

            report_path = write_tts_generation_report(
                output_folder=output,
                artifact_stem="fixture",
                tts_text="  같은   대본을  읽습니다. ",
                raw_tts_duration_sec=31.2344,
                final_voice_path=voice,
                final_voice_duration_sec=27.8916,
                leading_silence_normalization={
                    "applied": True,
                    "detected_leading_silence_sec": 0.489,
                    "normalized_leading_silence_sec": 0.152,
                    "target_leading_silence_sec": 0.15,
                    "trimmed_sec": 0.339,
                },
            )
            payload = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["provider"], "google_gemini_tts")
        self.assertEqual(payload["voice"], "Sulafat")
        self.assertEqual(payload["voice_relative_path"], "fixture_voice.mp3")
        self.assertEqual(payload["raw_tts_duration_sec"], 31.234)
        self.assertEqual(payload["final_voice_duration_sec"], 27.892)
        self.assertEqual(payload["leading_silence_normalization"]["normalized_leading_silence_sec"], 0.152)
        self.assertEqual(
            payload["tts_text_sha256"],
            hashlib.sha256("같은 대본을 읽습니다.".encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            payload["voice_sha256"],
            hashlib.sha256(b"approved-gemini-voice").hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
