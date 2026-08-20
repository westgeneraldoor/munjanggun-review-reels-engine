"""캡처 픽셀 검증 테스트.

recipe에 적힌 숫자를 그대로 믿던 두 자리를 실제 이미지로 확인한다. 고객 자료를
쓰지 않도록 모든 이미지는 이 테스트가 직접 그린다.
"""

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from video_engine_v2.capture_verification import (
    detect_text_lines,
    verify_sanitized_asset,
    verify_underline_segments,
)


WIDTH = 300
HEIGHT = 400
LINE_HEIGHT = 12
LINE_PITCH = 30
FIRST_LINE_TOP = 40
LINE_COUNT = 10


def draw_review_capture(path: Path) -> None:
    """흰 배경에 검은 글자 줄 열 개를 그린 가짜 리뷰 캡처."""
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    canvas = ImageDraw.Draw(image)
    for index in range(LINE_COUNT):
        top = FIRST_LINE_TOP + index * LINE_PITCH
        canvas.rectangle([20, top, WIDTH - 25, top + LINE_HEIGHT], fill=(20, 20, 20))
    image.save(path)


def line_pct(index: int) -> tuple[float, float]:
    top = FIRST_LINE_TOP + index * LINE_PITCH
    return (top / HEIGHT * 100, (top + LINE_HEIGHT) / HEIGHT * 100)


def under(index: int) -> float:
    """`index` 번째 글자 줄 바로 아래 여백의 top_pct."""
    return (FIRST_LINE_TOP + index * LINE_PITCH + LINE_HEIGHT + 4) / HEIGHT * 100


class UnderlinePlacementTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.capture = self.tmp / "capture.png"
        draw_review_capture(self.capture)

    def test_every_drawn_line_is_detected(self):
        self.assertEqual(len(detect_text_lines(self.capture)), LINE_COUNT)

    def test_underline_sitting_below_consecutive_lines_passes(self):
        segments = [{"top_pct": under(4)}, {"top_pct": under(5)}]

        self.assertEqual(verify_underline_segments(self.capture, segments), [])

    def test_underline_drawn_through_the_middle_of_a_line_is_rejected(self):
        """120번의 실제 결함. top_pct가 글자 띠 한복판을 지났다."""
        top, bottom = line_pct(4)
        segments = [{"top_pct": (top + bottom) / 2}]

        self.assertIn("REVIEW_UNDERLINE_CROSSES_TEXT", verify_underline_segments(self.capture, segments))

    def test_underline_floating_in_empty_space_is_rejected(self):
        # 마지막 글자 줄보다 한참 아래, 아무 글자도 없는 자리.
        segments = [{"top_pct": 99.0}]

        self.assertIn("REVIEW_UNDERLINE_NOT_UNDER_TEXT", verify_underline_segments(self.capture, segments))

    def test_underlines_that_skip_a_line_are_rejected(self):
        segments = [{"top_pct": under(2)}, {"top_pct": under(4)}]

        self.assertIn(
            "REVIEW_UNDERLINE_LINES_NOT_CONSECUTIVE",
            verify_underline_segments(self.capture, segments),
        )

    def test_underlines_running_up_the_capture_are_rejected(self):
        segments = [{"top_pct": under(5)}, {"top_pct": under(4)}]

        self.assertIn(
            "REVIEW_UNDERLINE_LINES_NOT_CONSECUTIVE",
            verify_underline_segments(self.capture, segments),
        )

    def test_a_capture_without_readable_lines_is_not_judged(self):
        blank = self.tmp / "blank.png"
        Image.new("RGB", (WIDTH, HEIGHT), "white").save(blank)

        self.assertEqual(verify_underline_segments(blank, [{"top_pct": 50.0}]), [])


class SanitizedAssetTest(unittest.TestCase):
    REGION = [{"left_pct": 15.0, "top_pct": 15.0, "width_pct": 50.0, "height_pct": 30.0}]

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.source = self.tmp / "source.png"
        # 마스킹 여부를 재려면 원본에 실제 디테일이 있어야 한다. 두 가지 색만 쓰면
        # 밝기를 옮겨도 분산이 그대로라 판정 자체가 성립하지 않으므로 계조를 넓게 깐다.
        image = Image.new("L", (200, 200))
        image.putdata([(x * 7 + y * 13) % 256 for y in range(200) for x in range(200)])
        image.convert("RGB").save(self.source)

    def box(self):
        return (40, 40, 120, 80)

    def test_a_solid_block_over_the_declared_region_passes(self):
        masked = self.tmp / "blackbox.png"
        image = Image.open(self.source).convert("RGB")
        ImageDraw.Draw(image).rectangle(self.box(), fill=(0, 0, 0))
        image.save(masked)

        self.assertEqual(verify_sanitized_asset(self.source, masked, self.REGION), [])

    def test_a_real_blur_over_the_declared_region_passes(self):
        masked = self.tmp / "blur.png"
        image = Image.open(self.source).convert("RGB")
        left, top, right, bottom = self.box()
        image.paste(image.crop(self.box()).filter(ImageFilter.GaussianBlur(6)), (left, top))
        image.save(masked)

        self.assertEqual(verify_sanitized_asset(self.source, masked, self.REGION), [])

    def test_an_untouched_file_presented_as_sanitized_is_rejected(self):
        self.assertIn(
            "SANITIZED_ASSET_UNCHANGED",
            verify_sanitized_asset(self.source, self.source, self.REGION),
        )

    def test_a_cosmetic_change_that_leaves_the_content_readable_is_rejected(self):
        masked = self.tmp / "cosmetic.png"
        image = Image.open(self.source).convert("RGB")
        left, top, right, bottom = self.box()
        # 밝기만 살짝 올린다. 파일은 달라지지만 가려진 것은 없다.
        lifted = image.crop(self.box()).point(lambda value: min(255, value + 40))
        image.paste(lifted, (left, top))
        image.save(masked)

        self.assertIn(
            "SANITIZED_REGION_STILL_LEGIBLE",
            verify_sanitized_asset(self.source, masked, self.REGION),
        )

    def test_changes_outside_the_declared_region_are_rejected(self):
        masked = self.tmp / "extra.png"
        image = Image.open(self.source).convert("RGB")
        ImageDraw.Draw(image).rectangle(self.box(), fill=(0, 0, 0))
        ImageDraw.Draw(image).rectangle((150, 150, 190, 190), fill=(0, 0, 0))
        image.save(masked)

        self.assertIn(
            "SANITIZED_ASSET_CHANGE_OUTSIDE_REGION",
            verify_sanitized_asset(self.source, masked, self.REGION),
        )

    def test_a_declared_region_that_was_never_touched_is_rejected(self):
        masked = self.tmp / "partial.png"
        image = Image.open(self.source).convert("RGB")
        ImageDraw.Draw(image).rectangle(self.box(), fill=(0, 0, 0))
        image.save(masked)
        regions = self.REGION + [
            {"left_pct": 70.0, "top_pct": 70.0, "width_pct": 20.0, "height_pct": 20.0}
        ]

        self.assertIn(
            "SANITIZED_REGION_NOT_APPLIED",
            verify_sanitized_asset(self.source, masked, regions),
        )

    def test_jpeg_re_encoding_noise_is_not_mistaken_for_masking(self):
        """JPEG를 다시 저장하면 전체 픽셀이 조금씩 흔들린다.

        그 흔들림을 `변경`으로 세면 마스크 영역이 이미지 전체로 번져, 제대로 가린
        사진까지 `선언 영역 밖을 건드렸다`고 막게 된다.
        """
        source_jpeg = self.tmp / "source.jpg"
        Image.open(self.source).convert("RGB").save(source_jpeg, quality=92)
        masked = self.tmp / "masked.jpg"
        image = Image.open(source_jpeg).convert("RGB")
        ImageDraw.Draw(image).rectangle(self.box(), fill=(0, 0, 0))
        image.save(masked, quality=92)

        self.assertEqual(verify_sanitized_asset(source_jpeg, masked, self.REGION), [])

    def test_a_resized_or_recropped_capture_is_rejected(self):
        masked = self.tmp / "resized.png"
        Image.open(self.source).convert("RGB").resize((180, 180)).save(masked)

        self.assertEqual(
            verify_sanitized_asset(self.source, masked, self.REGION),
            ["SANITIZED_ASSET_GEOMETRY_CHANGED"],
        )



class GateAdapterTest(unittest.TestCase):
    """게이트가 픽셀 검증을 실제로 호출하고, 위반을 삼키지 않는지 확인한다.

    전체 preflight 경로는 이 검사와 무관한 결속(해시, 승인, 음성)을 잔뜩 요구하므로
    여기서는 게이트가 recipe/manifest에서 경로를 찾아 검증까지 연결하는 어댑터만 본다.
    """

    def setUp(self):
        from video_engine_v2 import production_gate

        self.gate = production_gate
        self.tmp = Path(tempfile.mkdtemp())
        self.package = self.tmp / "120_demo"
        (self.package / "images").mkdir(parents=True)
        (self.package / "_work").mkdir()
        (self.package / "CANONICAL_PACKAGE_METADATA.json").write_text(
            '{"content_id": "120", "image_directory_name": "images"}', encoding="utf-8"
        )
        draw_review_capture(self.package / "images" / "review.png")

    def edit_recipe(self, top_pct):
        return {
            "source": {"image_dir": "images"},
            "asset_roles": {"review_capture": "review.png"},
            "beats": [
                {
                    "narrative_role": "review_proof",
                    "asset_id": "review_capture",
                    "review_emphasis": {
                        "quote": "fixture quote",
                        "segments": [{"left_pct": 10.0, "top_pct": top_pct, "width_pct": 70.0}],
                    },
                }
            ],
        }

    def test_gate_raises_when_the_underline_is_drawn_through_the_text(self):
        top, bottom = line_pct(4)

        with self.assertRaises(self.gate.GateViolation) as blocked:
            self.gate._validate_review_underline_pixels(
                self.package, self.edit_recipe((top + bottom) / 2)
            )

        self.assertIn("REVIEW_UNDERLINE_CROSSES_TEXT", str(blocked.exception))

    def test_gate_accepts_an_underline_resting_below_the_text(self):
        self.gate._validate_review_underline_pixels(self.package, self.edit_recipe(under(4)))

    def test_gate_raises_when_a_sanitization_output_is_not_declared(self):
        sanitized = self.package / "_work" / "review_masked.png"
        draw_review_capture(sanitized)
        report = self.package / "_work" / "report.json"
        report.write_text(
            '{"checked_assets": [{"relative_path": "_work/review_masked.png"}]}', encoding="utf-8"
        )

        with self.assertRaises(self.gate.GateViolation) as blocked:
            self.gate._validate_sanitized_asset_pixels(
                self.package, {"sanitization_report": "_work/report.json"}
            )

        self.assertIn("SANITIZED_ASSET_NOT_DECLARED", str(blocked.exception))

    def test_gate_does_not_demand_a_declaration_for_untouched_originals(self):
        report = self.package / "_work" / "report.json"
        report.write_text(
            '{"checked_assets": [{"relative_path": "images/review.png"}]}', encoding="utf-8"
        )

        self.gate._validate_sanitized_asset_pixels(
            self.package, {"sanitization_report": "_work/report.json"}
        )

if __name__ == "__main__":
    unittest.main()
