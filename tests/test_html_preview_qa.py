import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from build_html_preview_v2 import build_layout_probe, render_preview_html
from video_engine_v2.reels_qa import CAPTION_SAFE_BOTTOM_PX, CAPTION_SAFE_TOP_PX


ROOT = Path(__file__).resolve().parents[1]


class HtmlPreviewQaTests(unittest.TestCase):
    def test_layout_probe_uses_silent_audio_before_voice_exists(self):
        recipe = {
            "title": "pre tts layout",
            "source": {"image_dir": "images", "voice": "voice_not_created_yet.mp3"},
            "asset_roles": {"photo": "photo.jpg"},
            "beats": [{
                "id": "b01",
                "time": [0.0, 3.5],
                "asset": "photo",
                "caption": "음성 생성 전 레이아웃",
                "caption_chunks": [{"text": "음성 생성 전 레이아웃", "start_sec": 0.0, "end_sec": 3.5}],
            }],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            edit = temp / "edit.json"
            edit.write_text(json.dumps(recipe, ensure_ascii=False), encoding="utf-8")

            html_path = build_layout_probe(edit, temp / "probe")
            html = html_path.read_text(encoding="utf-8")

            self.assertTrue((temp / "probe" / "engine_font.ttf").is_file())
            self.assertIn("engine_font.ttf", html)

        self.assertIn("data:audio/mpeg;base64,", html)

    def test_layout_precheck_accepts_two_wrapped_lines_with_visible_caption_effects(self):
        recipe = {
            "title": "layout precheck valid",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "asset_roles": {"photo": "photo.jpg"},
            "beats": [{
                "id": "b01", "narrative_role": "event", "phase": "event",
                "time": [0.0, 4.0], "asset": "photo", "motion": "calm_push_in",
                "transition_in": "cut", "caption": "거실이 바로 보이던 현관,",
                "caption_layout": {"position": "bottom", "size": "medium", "theme": "white"},
                "caption_chunks": [{
                    "text": "거실이 바로 보이던 현관,",
                    "start_sec": 0.0, "end_sec": 4.0,
                }],
                "shots": [{"asset_id": "photo", "motion": "calm_push_in", "transition_in": "cut", "start_sec": 0.0, "end_sec": 4.0}],
            }],
        }
        pixel = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"photo": pixel, "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="layout precheck valid",
            preview_description="layout precheck valid",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            html_path = temp / "index.html"
            edit_path = temp / "edit.json"
            html_path.write_text(html, encoding="utf-8")
            edit_path.write_text(json.dumps(recipe), encoding="utf-8")
            result = subprocess.run(
                ["node", "scripts/html-layout-precheck.mjs", "--html", str(html_path), "--edit", str(edit_path)],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
            )

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["checks"][0]["issues"], [])

    def test_layout_precheck_rejects_three_lines_without_writing_qa_artifacts(self):
        recipe = {
            "title": "layout precheck",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "asset_roles": {"photo": "photo.jpg"},
            "beats": [{
                "id": "b01", "narrative_role": "event", "phase": "event",
                "time": [0.0, 4.0], "asset": "photo", "motion": "calm_push_in",
                "transition_in": "cut", "caption": "아주 긴 자막",
                "caption_layout": {"position": "bottom", "size": "large", "theme": "white"},
                "caption_chunks": [{
                    "text": "리뷰를 하나하나 읽어가며 여러 업체의 견적과 추천 내용을 아주 꼼꼼하게 비교해 보았습니다",
                    "start_sec": 0.0, "end_sec": 4.0,
                }],
                "shots": [{"asset_id": "photo", "motion": "calm_push_in", "transition_in": "cut", "start_sec": 0.0, "end_sec": 4.0}],
            }],
        }
        pixel = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"photo": pixel, "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="layout precheck",
            preview_description="layout precheck",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            html_path = temp / "index.html"
            edit_path = temp / "edit.json"
            html_path.write_text(html, encoding="utf-8")
            edit_path.write_text(json.dumps(recipe), encoding="utf-8")
            result = subprocess.run(
                ["node", "scripts/html-layout-precheck.mjs", "--html", str(html_path), "--edit", str(edit_path)],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            remaining = sorted(path.name for path in temp.iterdir())

        self.assertEqual(result.returncode, 2, result.stderr or result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "fail")
        self.assertIn("CAPTION_LINE_COUNT_EXCESSIVE", report["checks"][0]["issues"])
        self.assertEqual(remaining, ["edit.json", "index.html"])

    def test_hook_qa_captures_half_second_and_each_of_the_first_three_shots(self):
        recipe = {
            "title": "hook evidence test",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "asset_roles": {"result": "result.jpg", "before": "before.jpg"},
            "beats": [{
                "id": "b01", "narrative_role": "event", "phase": "event",
                "time": [0.0, 4.0], "asset": "result", "motion": "calm_push_in",
                "transition_in": "cut", "caption": "완성 결과",
                "shots": [
                    {"asset_id": "result", "motion": "calm_push_in", "transition_in": "cut", "start_sec": 0.0, "end_sec": 1.3},
                    {"asset_id": "before", "motion": "calm_push_in", "transition_in": "calm_dissolve", "start_sec": 1.3, "end_sec": 2.6},
                    {"asset_id": "result", "motion": "calm_push_in", "transition_in": "calm_dissolve", "start_sec": 2.6, "end_sec": 4.0},
                ],
            }],
        }
        pixel = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"result": pixel, "before": pixel, "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="hook evidence test",
            preview_description="hook evidence test",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            html_path = temp / "index.html"
            edit_path = temp / "edit.json"
            html_path.write_text(html, encoding="utf-8")
            edit_path.write_text(json.dumps(recipe), encoding="utf-8")
            result = subprocess.run(
                ["node", "scripts/html-preview-qa.mjs", "--html", str(html_path), "--edit", str(edit_path)],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            report = json.loads((temp / "html_internal_qa_report.json").read_text(encoding="utf-8"))
            hook_frames = list((temp / "_qa_frames" / "hook_sequence").glob("*.png"))

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertEqual([item["sample_time_sec"] for item in report["hook_sequence_checks"]], [0.5, 0.65, 1.95, 3.3])
        self.assertEqual([item["expected_asset_id"] for item in report["hook_sequence_checks"]], ["result", "result", "before", "result"])
        self.assertEqual(len(hook_frames), 4)

    def test_representative_frame_waits_until_calm_transition_copy_is_gone(self):
        recipe = {
            "title": "qa settle test",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "asset_roles": {"first": "first.jpg", "second": "second.jpg"},
            "beats": [
                {
                    "id": "b01", "narrative_role": "event", "phase": "event",
                    "time": [0.0, 2.0], "asset": "first", "motion": "calm_push_in",
                    "transition_in": "cut", "caption": "first",
                    "shots": [{"asset_id": "first", "motion": "calm_push_in", "transition_in": "cut", "start_sec": 0.0, "end_sec": 2.0}],
                },
                {
                    "id": "b02", "narrative_role": "result", "phase": "result",
                    "time": [2.0, 4.0], "asset": "second", "motion": "calm_glide_left",
                    "transition_in": "calm_dissolve", "caption": "second",
                    "shots": [{"asset_id": "second", "motion": "calm_glide_left", "transition_in": "calm_dissolve", "start_sec": 2.0, "end_sec": 4.0}],
                },
            ],
        }
        pixel = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        first = pixel + "#first"
        second = pixel + "#second"
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"first": first, "second": second, "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="qa settle test",
            preview_description="qa settle test",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            html_path = temp / "index.html"
            edit_path = temp / "edit.json"
            html_path.write_text(html, encoding="utf-8")
            edit_path.write_text(json.dumps(recipe), encoding="utf-8")
            result = subprocess.run(
                ["node", "scripts/html-preview-qa.mjs", "--html", str(html_path), "--edit", str(edit_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            report = json.loads((temp / "html_internal_qa_report.json").read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        second_ids = {image["id"] for image in report["checks"][1]["visible_images"]}
        self.assertNotIn("previousAsset", second_ids)
        self.assertGreaterEqual(report["frame_settle_wait_ms"], 380)

    def test_bottom_caption_chunks_are_measured_against_the_1080x1920_dead_zone(self):
        recipe = {
            "title": "dead-zone test",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "asset_roles": {"photo": "photo.jpg"},
            "beats": [
                {
                    "id": "b01", "narrative_role": "event", "phase": "event",
                    "time": [0.0, 4.0], "asset": "photo", "motion": "calm_push_in",
                    "transition_in": "cut", "caption": "첫 문맥 자막",
                    "caption_layout": {"position": "bottom", "size": "large", "theme": "white"},
                    "caption_emphasis": ["문맥"],
                    "caption_accent": {"enabled": True, "style": "result", "start_sec": 0.6},
                    "caption_chunks": [
                        {"text": "첫 문맥 자막", "start_sec": 0.0, "end_sec": 2.0},
                        {"text": "두 번째 문맥\n함께 봅니다", "start_sec": 2.0, "end_sec": 4.0},
                    ],
                    "shots": [{"asset_id": "photo", "motion": "calm_push_in", "transition_in": "cut", "start_sec": 0.0, "end_sec": 4.0}],
                },
            ],
        }
        pixel = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"photo": pixel, "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="dead-zone test",
            preview_description="dead-zone test",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            html_path = temp / "index.html"
            edit_path = temp / "edit.json"
            html_path.write_text(html, encoding="utf-8")
            edit_path.write_text(json.dumps(recipe), encoding="utf-8")
            result = subprocess.run(
                ["node", "scripts/html-preview-qa.mjs", "--html", str(html_path), "--edit", str(edit_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            report = json.loads((temp / "html_internal_qa_report.json").read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, f"{result.stderr or result.stdout}\n{report}")
        self.assertEqual(
            report["caption_safe_area_1080x1920"],
            {"top": CAPTION_SAFE_TOP_PX, "bottom": CAPTION_SAFE_BOTTOM_PX},
        )
        samples = report["checks"][0]["caption_samples"]
        self.assertEqual(len(samples), 2)
        self.assertTrue(all(sample["safe"] for sample in samples), samples)
        self.assertTrue(
            all(sample["top_1080x1920"] >= CAPTION_SAFE_TOP_PX for sample in samples),
            samples,
        )
        self.assertTrue(
            all(sample["bottom_1080x1920"] <= CAPTION_SAFE_BOTTOM_PX for sample in samples),
            samples,
        )
        self.assertTrue(all(sample["line_count"] <= 2 for sample in samples), samples)
        accent_samples = [sample for sample in samples if sample.get("accent_start_sec") is not None]
        self.assertEqual([sample["accent_start_sec"] for sample in accent_samples], [0.6, 0.6])
        self.assertTrue(all(sample.get("accent_pop_duration_ms") == 420 for sample in accent_samples), samples)

    def test_actual_three_line_caption_is_rejected(self):
        recipe = {
            "title": "line-count test",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "asset_roles": {"photo": "photo.jpg"},
            "beats": [{
                "id": "b01", "narrative_role": "event", "phase": "event",
                "time": [0.0, 4.0], "asset": "photo", "motion": "calm_push_in",
                "transition_in": "cut", "caption": "아주 긴 자막",
                "caption_layout": {"position": "bottom", "size": "large", "theme": "white"},
                "caption_chunks": [{
                    "text": "리뷰를 하나하나 읽어가며 여러 업체의 견적과 추천 내용을 아주 꼼꼼하게 비교해 보았습니다",
                    "start_sec": 0.0, "end_sec": 4.0,
                }],
                "shots": [{"asset_id": "photo", "motion": "calm_push_in", "transition_in": "cut", "start_sec": 0.0, "end_sec": 4.0}],
            }],
        }
        pixel = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"photo": pixel, "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="line-count test",
            preview_description="line-count test",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            html_path = temp / "index.html"
            edit_path = temp / "edit.json"
            html_path.write_text(html, encoding="utf-8")
            edit_path.write_text(json.dumps(recipe), encoding="utf-8")
            result = subprocess.run(
                ["node", "scripts/html-preview-qa.mjs", "--html", str(html_path), "--edit", str(edit_path)],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            report = json.loads((temp / "html_internal_qa_report.json").read_text(encoding="utf-8"))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CAPTION_LINE_COUNT_EXCESSIVE", report["checks"][0]["issues"])
        self.assertGreater(report["checks"][0]["caption_samples"][0]["line_count"], 2)


if __name__ == "__main__":
    unittest.main()
