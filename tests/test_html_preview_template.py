import json
import re
import unittest

from build_html_preview_v2 import TEMPLATE_PATH, render_preview_html


class HtmlPreviewTemplateTests(unittest.TestCase):
    def test_template_is_external_and_recipe_json_cannot_terminate_its_script_tag(self):
        recipe = {
            "title": "테스트",
            "beats": [],
            "caption": "</script><p>injected</p>",
            "narration": "한글과 \"따옴표\"를 보존합니다.",
        }

        html = render_preview_html(
            recipe=recipe,
            asset_urls={"voice": "voice.mp3", "font_body": "font.ttf"},
            preview_title="테스트",
            preview_description="설명",
        )

        self.assertTrue(TEMPLATE_PATH.is_file())
        match = re.search(r"const recipe = (?P<payload>\{.*?\});", html, re.DOTALL)
        self.assertIsNotNone(match)
        payload = match.group("payload")
        self.assertNotIn("</script>", payload.lower())
        self.assertIn("\\u003c/script\\u003e", payload.lower())
        self.assertEqual(json.loads(payload), recipe)


if __name__ == "__main__":
    unittest.main()
