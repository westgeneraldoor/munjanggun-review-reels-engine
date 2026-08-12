import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from build_html_preview_v2 import render_preview_html


ROOT = Path(__file__).resolve().parents[1]


class HtmlPreviewQaTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
