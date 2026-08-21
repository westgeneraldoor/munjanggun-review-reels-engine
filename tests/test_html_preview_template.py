import json
from pathlib import Path
import re
import subprocess
import tempfile
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

    def test_cross_dissolve_keeps_the_outgoing_photo_visible_during_the_transition(self):
        recipe = {
            "title": "dissolve test",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "asset_roles": {"before": "before.jpg", "after": "after.jpg"},
            "beats": [
                {
                    "id": "b01",
                    "phase": "result",
                    "time": [0.0, 4.0],
                    "asset": "before",
                    "motion": "space_anxiety_pull",
                    "transition_in": "cut",
                    "transition_out": "none",
                    "caption": "before and after",
                    "shots": [
                        {
                            "asset_id": "before",
                            "motion": "space_anxiety_pull",
                            "transition_in": "cut",
                            "start_sec": 0.0,
                            "end_sec": 2.0,
                        },
                        {
                            "asset_id": "after",
                            "motion": "clean_room_pan",
                            "transition_in": "cross_dissolve",
                            "start_sec": 2.0,
                            "end_sec": 4.0,
                        },
                    ],
                }
            ],
        }
        before = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E%23before"
        after = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E%23after"
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"before": before, "after": after, "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="dissolve test",
            preview_description="browser behavior test",
        )
        browser_check = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(process.argv[1] + '?t=2.5');
  const state = await page.evaluate(() => {
    const previous = document.querySelector('#previousAsset');
    const current = document.querySelector('#mainAsset');
    return {
      previousSrc: previous && previous.src,
      currentSrc: current && current.src,
      previousAnimation: previous && getComputedStyle(previous).animationName,
      currentAnimation: current && getComputedStyle(current).animationName,
    };
  });
  await browser.close();
  if (!state.previousSrc.includes('%23before') || !state.currentSrc.includes('%23after')) process.exit(2);
  if (state.previousAnimation !== 'crossDissolveOut' || state.currentAnimation !== 'crossDissolveIn') process.exit(3);
})().catch(error => { console.error(error); process.exit(1); });
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "preview.html"
            html_path.write_text(html, encoding="utf-8")
            result = subprocess.run(
                ["node", "-e", browser_check, html_path.as_uri()],
                cwd=TEMPLATE_PATH.parent.parent.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_review_capture_hold_keeps_the_review_card_stable_while_reading(self):
        recipe = {
            "title": "review hold test",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "asset_roles": {"review_capture": "review.png"},
            "beats": [
                {
                    "id": "b01",
                    "phase": "review_proof",
                    "time": [0.0, 4.0],
                    "asset": "review_capture",
                    "motion": "review_capture_hold",
                    "transition_in": "cut",
                    "transition_out": "none",
                    "caption": "review proof",
                }
            ],
        }
        review = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E%23review"
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"review_capture": review, "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="review hold test",
            preview_description="browser behavior test",
        )
        browser_check = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(process.argv[1] + '?t=1');
  const state = await page.evaluate(() => {
    const card = document.querySelector('#reviewCard');
    const first = { opacity: card.style.opacity, transform: card.style.transform, opacityTransition: getComputedStyle(card).transitionDuration };
    renderAt(3);
    return { first, second: { opacity: card.style.opacity, transform: card.style.transform } };
  });
  await browser.close();
  if (state.first.opacity !== '1' || state.second.opacity !== '1') process.exit(2);
  if (state.first.transform !== 'translate(-50%, -50%) scale(1)' || state.second.transform !== state.first.transform) process.exit(3);
  if (state.first.opacityTransition !== '0.26s') process.exit(4);
})().catch(error => { console.error(error); process.exit(1); });
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "preview.html"
            html_path.write_text(html, encoding="utf-8")
            result = subprocess.run(
                ["node", "-e", browser_check, html_path.as_uri()],
                cwd=TEMPLATE_PATH.parent.parent.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_static_hold_keeps_the_photo_transform_unchanged(self):
        recipe = {
            "title": "static hold test",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "asset_roles": {"hero": "hero.jpg"},
            "beats": [
                {
                    "id": "b01",
                    "phase": "event",
                    "time": [0.0, 4.0],
                    "asset": "hero",
                    "motion": "static_hold",
                    "transition_in": "cut",
                    "transition_out": "none",
                    "caption": "finished door",
                }
            ],
        }
        hero = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E%23hero"
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"hero": hero, "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="static hold test",
            preview_description="browser behavior test",
        )
        browser_check = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(process.argv[1] + '?t=1');
  const state = await page.evaluate(() => {
    const image = document.querySelector('#mainAsset');
    const first = image.style.transform;
    renderAt(3);
    return { first, second: image.style.transform };
  });
  await browser.close();
  if (state.first !== 'scale(1.02)' || state.second !== state.first) process.exit(2);
})().catch(error => { console.error(error); process.exit(1); });
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "preview.html"
            html_path.write_text(html, encoding="utf-8")
            result = subprocess.run(
                ["node", "-e", browser_check, html_path.as_uri()],
                cwd=TEMPLATE_PATH.parent.parent.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_micro_motion_changes_scale_by_only_two_percent_without_translation(self):
        recipe = {
            "title": "micro motion test",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 8.0}},
            "asset_roles": {"push": "push.jpg", "pull": "pull.jpg"},
            "beats": [
                {"id": "b01", "phase": "result", "time": [0.0, 4.0], "asset": "push", "motion": "micro_push_in", "transition_in": "cut", "caption": "push"},
                {"id": "b02", "phase": "problem", "time": [4.0, 8.0], "asset": "pull", "motion": "micro_pull_out", "transition_in": "cut", "caption": "pull"},
            ],
        }
        image = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E"
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"push": image + "%23push", "pull": image + "%23pull", "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="micro motion test",
            preview_description="browser behavior test",
        )
        browser_check = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(process.argv[1] + '?t=0');
  const state = await page.evaluate(() => {
    renderAt(0); const pushStart = mainAsset.style.transform;
    renderAt(3.999); const pushEnd = mainAsset.style.transform;
    renderAt(4); const pullStart = mainAsset.style.transform;
    renderAt(7.999); const pullEnd = mainAsset.style.transform;
    return {pushStart, pushEnd, pullStart, pullEnd};
  });
  await browser.close();
  if (state.pushStart !== 'scale(1.015)' || state.pushEnd !== 'scale(1.035)') process.exit(2);
  if (state.pullStart !== 'scale(1.035)' || state.pullEnd !== 'scale(1.015)') process.exit(3);
  if (Object.values(state).some(value => value.includes('translate') || value.includes('rotate'))) process.exit(4);
})().catch(error => { console.error(error); process.exit(1); });
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "preview.html"
            html_path.write_text(html, encoding="utf-8")
            result = subprocess.run(
                ["node", "-e", browser_check, html_path.as_uri()],
                cwd=TEMPLATE_PATH.parent.parent.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_soft_transitions_have_bounded_short_durations(self):
        recipe = {
            "title": "soft transition test",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 6.0}},
            "asset_roles": {"one": "one.jpg", "two": "two.jpg", "three": "three.jpg"},
            "beats": [{
                "id": "b01", "phase": "result", "time": [0.0, 6.0], "asset": "one", "motion": "micro_push_in", "transition_in": "cut", "caption": "soft",
                "shots": [
                    {"asset_id": "one", "motion": "micro_push_in", "transition_in": "cut", "start_sec": 0.0, "end_sec": 2.0},
                    {"asset_id": "two", "motion": "micro_pull_out", "transition_in": "soft_cut", "start_sec": 2.0, "end_sec": 4.0},
                    {"asset_id": "three", "motion": "micro_push_in", "transition_in": "soft_dissolve", "start_sec": 4.0, "end_sec": 6.0},
                ],
            }],
        }
        image = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E"
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"one": image + "%23one", "two": image + "%23two", "three": image + "%23three", "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="soft transition test",
            preview_description="browser behavior test",
        )
        browser_check = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(process.argv[1] + '?t=0');
  const state = await page.evaluate(() => {
    renderAt(2.001);
    const softCut = {duration: getComputedStyle(mainAsset).animationDuration, previous: previousAsset.src, current: mainAsset.src};
    renderAt(4.001);
    const softDissolve = {duration: getComputedStyle(mainAsset).animationDuration, previous: previousAsset.src, current: mainAsset.src};
    return {softCut, softDissolve};
  });
  await browser.close();
  if (state.softCut.duration !== '0.16s') process.exit(2);
  if (state.softDissolve.duration !== '0.26s') process.exit(3);
  if (!state.softCut.previous.includes('%23one') || !state.softCut.current.includes('%23two')) process.exit(4);
  if (!state.softDissolve.previous.includes('%23two') || !state.softDissolve.current.includes('%23three')) process.exit(5);
})().catch(error => { console.error(error); process.exit(1); });
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "preview.html"
            html_path.write_text(html, encoding="utf-8")
            result = subprocess.run(
                ["node", "-e", browser_check, html_path.as_uri()],
                cwd=TEMPLATE_PATH.parent.parent.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_soft_transition_preserves_the_outgoing_photo_across_beat_boundaries(self):
        recipe = {
            "title": "beat boundary transition test",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "asset_roles": {"first": "first.jpg", "second": "second.jpg"},
            "beats": [
                {"id": "b01", "phase": "result", "time": [0.0, 2.0], "asset": "first", "motion": "micro_push_in", "transition_in": "cut", "caption": "first", "shots": [{"asset_id": "first", "motion": "micro_push_in", "transition_in": "cut", "start_sec": 0.0, "end_sec": 2.0}]},
                {"id": "b02", "phase": "problem", "time": [2.0, 4.0], "asset": "second", "motion": "micro_pull_out", "transition_in": "soft_dissolve", "caption": "second", "shots": [{"asset_id": "second", "motion": "micro_pull_out", "transition_in": "soft_dissolve", "start_sec": 2.0, "end_sec": 4.0}]},
            ],
        }
        image = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E"
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"first": image + "%23first", "second": image + "%23second", "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="beat boundary transition test",
            preview_description="browser behavior test",
        )
        browser_check = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(process.argv[1] + '?t=0');
  const state = await page.evaluate(() => {
    renderAt(1.9);
    renderAt(2.001);
    return {previous: previousAsset.src, current: mainAsset.src, duration: getComputedStyle(mainAsset).animationDuration};
  });
  await browser.close();
  if (!state.previous.includes('%23first') || !state.current.includes('%23second')) process.exit(2);
  if (state.duration !== '0.26s') process.exit(3);
})().catch(error => { console.error(error); process.exit(1); });
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "preview.html"
            html_path.write_text(html, encoding="utf-8")
            result = subprocess.run(
                ["node", "-e", browser_check, html_path.as_uri()],
                cwd=TEMPLATE_PATH.parent.parent.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_review_hold_hides_the_transition_copy_after_the_soft_entry_finishes(self):
        recipe = {
            "title": "review soft entry test",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "asset_roles": {"photo": "photo.jpg", "review_capture": "review.png"},
            "beats": [
                {"id": "b01", "phase": "result", "time": [0.0, 2.0], "asset": "photo", "motion": "micro_push_in", "transition_in": "cut", "caption": "photo", "shots": [{"asset_id": "photo", "motion": "micro_push_in", "transition_in": "cut", "start_sec": 0.0, "end_sec": 2.0}]},
                {"id": "b02", "phase": "review_proof", "time": [2.0, 4.0], "asset": "review_capture", "motion": "review_capture_hold", "transition_in": "soft_dissolve", "caption": "review", "shots": [{"asset_id": "review_capture", "motion": "review_capture_hold", "transition_in": "soft_dissolve", "start_sec": 2.0, "end_sec": 4.0}]},
            ],
        }
        image = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E"
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"photo": image + "%23photo", "review_capture": image + "%23review", "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="review soft entry test",
            preview_description="browser behavior test",
        )
        browser_check = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(process.argv[1] + '?t=0');
  await page.evaluate(() => { renderAt(1.9); renderAt(2.001); });
  await page.waitForTimeout(320);
  const state = await page.evaluate(() => ({
    transitionCopyOpacity: getComputedStyle(mainAsset).opacity,
    reviewOpacity: getComputedStyle(reviewCard).opacity,
    reviewTransform: reviewCard.style.transform,
  }));
  await browser.close();
  if (state.transitionCopyOpacity !== '0') process.exit(2);
  if (state.reviewOpacity !== '1' || state.reviewTransform !== 'translate(-50%, -50%) scale(1)') process.exit(3);
})().catch(error => { console.error(error); process.exit(1); });
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "preview.html"
            html_path.write_text(html, encoding="utf-8")
            result = subprocess.run(
                ["node", "-e", browser_check, html_path.as_uri()],
                cwd=TEMPLATE_PATH.parent.parent.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_review_emphasis_draws_the_exact_underline_only_during_its_timing(self):
        recipe = {
            "title": "review underline test",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "asset_roles": {"review_capture": "review.png"},
            "beats": [
                {
                    "id": "b01",
                    "phase": "review_proof",
                    "time": [0.0, 4.0],
                    "asset": "review_capture",
                    "motion": "review_capture_hold",
                    "transition_in": "cut",
                    "transition_out": "none",
                    "caption": "the review says so",
                    "review_emphasis": {
                        "quote": "recommended a style that suited our home",
                        "start_sec": 1.0,
                        "end_sec": 3.0,
                        "draw_duration_sec": 0.15,
                        "segments": [{"left_pct": 10.0, "top_pct": 54.0, "width_pct": 70.0}],
                    },
                }
            ],
        }
        review = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E%23review"
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"review_capture": review, "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="review underline test",
            preview_description="browser behavior test",
        )
        browser_check = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(process.argv[1] + '?t=0.5');
  const state = await page.evaluate(() => {
    const line = document.querySelector('.review-underline');
    const before = line && line.style.transform;
    const lineHeight = line && getComputedStyle(line).height;
    const lineShadow = line && getComputedStyle(line).boxShadow;
    renderAt(1.075);
    const during = line && line.style.transform;
    renderAt(1.3);
    return {
      before,
      during,
      after: line && line.style.transform,
      quote: document.querySelector('#reviewUnderlineLayer')?.getAttribute('aria-label'),
      lineHeight,
      lineShadow,
    };
  });
  await browser.close();
  if (state.before !== 'scaleX(0)' || state.during !== 'scaleX(0.5)' || state.after !== 'scaleX(1)') process.exit(2);
  if (state.quote !== 'recommended a style that suited our home') process.exit(3);
  if (state.lineHeight !== '2px' || state.lineShadow !== 'none') process.exit(4);
})().catch(error => { console.error(error); process.exit(1); });
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "preview.html"
            html_path.write_text(html, encoding="utf-8")
            result = subprocess.run(
                ["node", "-e", browser_check, html_path.as_uri()],
                cwd=TEMPLATE_PATH.parent.parent.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_white_caption_theme_uses_ivory_with_mint_keyword(self):
        recipe = {
            "title": "caption palette test",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "asset_roles": {"hero": "hero.jpg"},
            "beats": [
                {
                    "id": "b01",
                    "phase": "result",
                    "time": [0.0, 4.0],
                    "asset": "hero",
                    "motion": "static_hold",
                    "transition_in": "cut",
                    "caption": "finished door",
                    "caption_layout": {"theme": "white"},
                    "caption_emphasis": ["door"],
                    "caption_accent": {"enabled": True, "style": "result"},
                }
            ],
        }
        hero = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E%23hero"
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"hero": hero, "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="caption palette test",
            preview_description="browser behavior test",
        )
        browser_check = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(process.argv[1] + '?t=1');
  const state = await page.evaluate(() => ({
    base: getComputedStyle(document.querySelector('#caption')).color,
    keyword: getComputedStyle(document.querySelector('#caption .em')).color,
  }));
  await browser.close();
  if (state.base !== 'rgb(247, 244, 236)') process.exit(2);
  if (state.keyword !== 'rgb(121, 229, 208)') process.exit(3);
})().catch(error => { console.error(error); process.exit(1); });
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "preview.html"
            html_path.write_text(html, encoding="utf-8")
            result = subprocess.run(
                ["node", "-e", browser_check, html_path.as_uri()],
                cwd=TEMPLATE_PATH.parent.parent.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_keyword_accent_waits_for_scene_settle_and_follows_video_time(self):
        recipe = {
            "title": "delayed keyword accent test",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "asset_roles": {"hero": "hero.jpg"},
            "beats": [{
                "id": "b01", "phase": "result", "time": [0.0, 4.0],
                "asset": "hero", "motion": "calm_push_in", "transition_in": "calm_dissolve",
                "caption": "finished door",
                "caption_chunks": [{"text": "finished door", "start_sec": 0.0, "end_sec": 4.0}],
                "caption_layout": {"size": "hero-calm", "theme": "white"},
                "caption_emphasis": ["door"],
                "caption_accent": {"enabled": True, "style": "result", "start_sec": 1.5},
            }],
        }
        hero = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E%23hero"
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"hero": hero, "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="delayed keyword accent test",
            preview_description="browser behavior test",
        )
        browser_check = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(process.argv[1] + '?t=0');
  const sample = async (time) => page.evaluate((t) => {
    renderAt(t);
    const keyword = document.querySelector('#caption .em');
    return {opacity: keyword.style.opacity, transform: keyword.style.transform};
  }, time);
  const before = await sample(1.40);
  const peak = await sample(1.731);
  const settled = await sample(2.00);
  await page.waitForTimeout(600);
  const sameVideoTimeAfterWallClockWait = await sample(1.40);
  await browser.close();
  if (before.opacity !== '0.78' || before.transform !== 'translateY(4px) scale(0.94)') process.exit(2);
  if (peak.opacity !== '1' || peak.transform !== 'translateY(-5px) scale(1.1)') process.exit(3);
  if (settled.opacity !== '1' || settled.transform !== 'translateY(0px) scale(1)') process.exit(4);
  if (JSON.stringify(sameVideoTimeAfterWallClockWait) !== JSON.stringify(before)) process.exit(5);
})().catch(error => { console.error(error); process.exit(1); });
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "preview.html"
            html_path.write_text(html, encoding="utf-8")
            result = subprocess.run(
                ["node", "-e", browser_check, html_path.as_uri()],
                cwd=TEMPLATE_PATH.parent.parent.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_caption_chunk_renders_canonical_display_text_without_changing_spoken_text(self):
        recipe = {
            "title": "display text test",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "asset_roles": {"hero": "hero.jpg"},
            "beats": [{
                "id": "b01", "phase": "result", "time": [0.0, 4.0],
                "asset": "hero", "motion": "calm_push_in", "transition_in": "cut",
                "caption": "초슬림 3연동중문",
                "caption_chunks": [{
                    "text": "초슬림 삼 연동 중문",
                    "display_text": "초슬림 3연동중문",
                    "start_sec": 0.0,
                    "end_sec": 4.0,
                }],
            }],
        }
        hero = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E%23hero"
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"hero": hero, "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="display text test",
            preview_description="display text test",
        )
        browser_check = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(process.argv[1] + '?t=1');
  const text = await page.locator('#caption').innerText();
  await browser.close();
  if (text !== '초슬림 3연동중문') process.exit(2);
})().catch(error => { console.error(error); process.exit(1); });
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "preview.html"
            html_path.write_text(html, encoding="utf-8")
            result = subprocess.run(
                ["node", "-e", browser_check, html_path.as_uri()],
                cwd=TEMPLATE_PATH.parent.parent.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_reduced_caption_hierarchy_keeps_photos_visually_primary(self):
        recipe = {
            "title": "hero calm caption test",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "asset_roles": {"hero": "hero.jpg"},
            "beats": [{
                "id": "b01", "phase": "result", "time": [0.0, 4.0], "asset": "hero", "motion": "micro_push_in", "transition_in": "cut", "caption": "finished door",
                "caption_layout": {"size": "hero-calm", "theme": "white"},
            }],
        }
        hero = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E%23hero"
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"hero": hero, "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="hero calm caption test",
            preview_description="browser behavior test",
        )
        browser_check = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({viewport: {width: 1200, height: 2100}});
  await page.goto(process.argv[1] + '?t=1');
  const sizes = await page.evaluate(() => {
    const result = {};
    for (const size of ['small', 'medium', 'large', 'hero-calm']) {
      caption.className = `caption size-${size} theme-white accent-keyword accent-result`;
      caption.innerHTML = '<span class="em">keyword</span>';
      result[size] = getComputedStyle(caption).fontSize;
      result[`${size}-keyword`] = getComputedStyle(caption.querySelector('.em')).fontSize;
    }
    return result;
  });
  await browser.close();
  if (sizes.small !== '36px') process.exit(2);
  if (sizes.medium !== '46px') process.exit(3);
  if (sizes.large !== '62px') process.exit(4);
  if (sizes['hero-calm'] !== '58px') process.exit(5);
  if (sizes['medium-keyword'] !== sizes.medium || sizes['hero-calm-keyword'] !== sizes['hero-calm']) process.exit(6);
})().catch(error => { console.error(error); process.exit(1); });
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "preview.html"
            html_path.write_text(html, encoding="utf-8")
            result = subprocess.run(
                ["node", "-e", browser_check, html_path.as_uri()],
                cwd=TEMPLATE_PATH.parent.parent.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_calm_c_motion_and_transition_runtime_matches_the_selected_audition(self):
        recipe = {
            "title": "calm c runtime",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "asset_roles": {"hero": "hero.jpg"},
            "beats": [{
                "id": "b01", "phase": "result", "time": [0.0, 4.0], "asset": "hero",
                "motion": "calm_push_in", "transition_in": "cut", "caption": "finished door",
            }],
        }
        hero = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E%23hero"
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"hero": hero, "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="calm c runtime",
            preview_description="browser behavior test",
        )
        browser_check = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({viewport: {width: 1200, height: 2100}});
  await page.goto(process.argv[1] + '?t=0');
  const state = await page.evaluate(() => {
    const sample = (motion, time) => {
      recipe.beats[0].motion = motion;
      activeBeatId = null;
      renderAt(time);
      return mainAsset.style.transform;
    };
    const pushStart = sample('calm_push_in', 0);
    const pushEnd = sample('calm_push_in', 4);
    const leftStart = sample('calm_glide_left', 0);
    const leftEnd = sample('calm_glide_left', 4);
    stage.className = 'stage calm_glide_left t-calm_dissolve transition-hit';
    const duration = getComputedStyle(mainAsset).animationDuration;
    return {pushStart, pushEnd, leftStart, leftEnd, duration};
  });
  await browser.close();
  if (state.pushStart !== 'scale(1.01)' || state.pushEnd !== 'scale(1.06)') process.exit(2);
  if (state.leftStart !== 'scale(1.045) translateX(12px)' || state.leftEnd !== 'scale(1.045) translateX(-12px)') process.exit(3);
  if (state.duration !== '0.38s') process.exit(4);
})().catch(error => { console.error(error); process.exit(1); });
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "preview.html"
            html_path.write_text(html, encoding="utf-8")
            result = subprocess.run(
                ["node", "-e", browser_check, html_path.as_uri()],
                cwd=TEMPLATE_PATH.parent.parent.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_calm_motion_uses_constant_progress_instead_of_stopping_at_each_shot_edge(self):
        recipe = {
            "title": "constant calm motion",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "asset_roles": {"hero": "hero.jpg"},
            "beats": [{
                "id": "b01", "phase": "result", "time": [0.0, 4.0], "asset": "hero",
                "motion": "calm_push_in", "transition_in": "cut", "caption": "finished door",
            }],
        }
        hero = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E%23hero"
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"hero": hero, "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="constant calm motion",
            preview_description="browser behavior test",
        )
        browser_check = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({viewport: {width: 1200, height: 2100}});
  await page.goto(process.argv[1]);
  const scales = await page.evaluate(() => [0, 1, 2, 3, 4].map(time => {
    activeBeatId = null;
    renderAt(time);
    return Number(new DOMMatrixReadOnly(mainAsset.style.transform).a.toFixed(4));
  }));
  await browser.close();
  const expected = [1.01, 1.0225, 1.035, 1.0475, 1.06];
  if (JSON.stringify(scales) !== JSON.stringify(expected)) {
    console.error(JSON.stringify({scales, expected}));
    process.exit(2);
  }
})().catch(error => { console.error(error); process.exit(1); });
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "preview.html"
            html_path.write_text(html, encoding="utf-8")
            result = subprocess.run(
                ["node", "-e", browser_check, html_path.as_uri()],
                cwd=TEMPLATE_PATH.parent.parent.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_calm_dissolve_preserves_the_outgoing_camera_position_without_transform_override(self):
        recipe = {
            "title": "continuous dissolve",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "asset_roles": {"first": "first.jpg", "second": "second.jpg"},
            "beats": [{
                "id": "b01", "phase": "result", "time": [0.0, 4.0], "asset": "first",
                "motion": "calm_push_in", "transition_in": "cut", "caption": "finished door",
                "shots": [
                    {"asset_id": "first", "motion": "calm_push_in", "transition_in": "cut", "start_sec": 0.0, "end_sec": 2.0},
                    {"asset_id": "second", "motion": "calm_push_in", "transition_in": "calm_dissolve", "start_sec": 2.0, "end_sec": 4.0},
                ],
            }],
        }
        first = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E%23first"
        second = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E%23second"
        html = render_preview_html(
            recipe=recipe,
            asset_urls={"first": first, "second": second, "voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"},
            preview_title="continuous dissolve",
            preview_description="browser behavior test",
        )
        browser_check = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({viewport: {width: 1200, height: 2100}});
  await page.goto(process.argv[1]);
  const state = await page.evaluate(async () => {
    renderAt(1.99);
    const outgoingTransform = mainAsset.style.transform;
    renderAt(2.01);
    const incomingTransform = mainAsset.style.transform;
    await new Promise(resolve => setTimeout(resolve, 70));
    const computedIncomingScale = Number(new DOMMatrixReadOnly(getComputedStyle(mainAsset).transform).a.toFixed(4));
    return {
      outgoingTransform,
      incomingTransform,
      previousTransform: previousAsset.style.transform,
      computedIncomingScale,
    };
  });
  await browser.close();
  const expectedIncomingScale = Number(state.incomingTransform.match(/scale\(([^)]+)/)[1]);
  if (state.previousTransform !== state.outgoingTransform) process.exit(2);
  if (Math.abs(state.computedIncomingScale - expectedIncomingScale) > 0.002) {
    console.error(JSON.stringify({state, expectedIncomingScale}));
    process.exit(3);
  }
})().catch(error => { console.error(error); process.exit(1); });
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "preview.html"
            html_path.write_text(html, encoding="utf-8")
            result = subprocess.run(
                ["node", "-e", browser_check, html_path.as_uri()],
                cwd=TEMPLATE_PATH.parent.parent.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_bounded_scene_transitions_render_with_outgoing_photo_context(self):
        recipe = {
            "title": "bounded transitions",
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 6.0}},
            "asset_roles": {"first": "first.jpg", "second": "second.jpg", "third": "third.jpg"},
            "beats": [{
                "id": "b01", "phase": "result", "time": [0.0, 6.0], "asset": "first",
                "motion": "calm_push_in", "transition_in": "cut", "caption": "finished door",
                "shots": [
                    {"asset_id": "first", "motion": "calm_push_in", "transition_in": "cut", "start_sec": 0.0, "end_sec": 2.0},
                    {"asset_id": "second", "motion": "calm_push_in", "transition_in": "calm_slide", "start_sec": 2.0, "end_sec": 4.0},
                    {"asset_id": "third", "motion": "calm_push_in", "transition_in": "soft_page_turn", "start_sec": 4.0, "end_sec": 6.0},
                ],
            }],
        }
        assets = {
            key: f"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E%23{key}"
            for key in ("first", "second", "third")
        }
        assets.update({"voice": "data:audio/mp3;base64,", "font_body": "data:font/woff2;base64,"})
        html = render_preview_html(
            recipe=recipe,
            asset_urls=assets,
            preview_title="bounded transitions",
            preview_description="browser behavior test",
        )
        browser_check = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({viewport: {width: 1200, height: 2100}});
  await page.goto(process.argv[1]);
  const states = await page.evaluate(() => {
    renderAt(1.99);
    renderAt(2.01);
    const slide = {
      className: stage.className,
      animationName: getComputedStyle(mainAsset).animationName,
      previousSrc: previousAsset.getAttribute('src') || '',
    };
    renderAt(3.99);
    renderAt(4.01);
    const pageTurn = {
      className: stage.className,
      animationName: getComputedStyle(mainAsset).animationName,
      previousSrc: previousAsset.getAttribute('src') || '',
    };
    return {slide, pageTurn};
  });
  await browser.close();
  if (!states.slide.className.includes('t-calm_slide')) process.exit(2);
  if (states.slide.animationName !== 'calmSlideRevealIn') process.exit(3);
  if (!states.slide.previousSrc.includes('first')) process.exit(4);
  if (!states.pageTurn.className.includes('t-soft_page_turn')) process.exit(5);
  if (states.pageTurn.animationName !== 'softPageTurnIn') process.exit(6);
  if (!states.pageTurn.previousSrc.includes('second')) process.exit(7);
})().catch(error => { console.error(error); process.exit(1); });
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            html_path = Path(temp_dir) / "preview.html"
            html_path.write_text(html, encoding="utf-8")
            result = subprocess.run(
                ["node", "-e", browser_check, html_path.as_uri()],
                cwd=TEMPLATE_PATH.parent.parent.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
