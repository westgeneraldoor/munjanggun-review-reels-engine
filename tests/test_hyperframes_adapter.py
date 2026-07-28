import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "recipe-to-hyperframes-pilot.mjs"


class HyperFramesAdapterTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.local_root = Path(self.tempdir.name) / "테스트 공백 경로"
        self.scratch = self.local_root / "scratch"
        (self.scratch / "package" / "images").mkdir(parents=True)
        (self.scratch / "package" / "images" / "after.jpg").write_bytes(b"fake image")
        (self.scratch / "package" / "voice.mp3").write_bytes(b"fake audio")

    def write_recipe(self, *, sync_ok=True, meaning_match=True):
        recipe = {
            "title": "fixture pilot",
            "source": {
                "package_dir": str(self.scratch / "package"),
                "image_dir": "images",
                "voice": "voice.mp3",
            },
            "asset_roles": {
                "after_main": "after.jpg",
            },
            "beats": [
                {
                    "id": "b01",
                    "phase": "hook",
                    "time": [0.0, 1.2],
                    "asset": "after_main",
                    "caption": "테스트 자막",
                    "caption_layout": {"position": "center"},
                    "meaning_match": meaning_match,
                }
            ],
            "audio_plan": {
                "sync_policy": {
                    "final_voice_duration_sec": 1.2,
                }
            },
            "sync_manifest": {
                "ok": sync_ok,
                "issues": [] if sync_ok else [{"code": "fixture_fail"}],
            },
        }
        recipe_path = self.scratch / "package" / "fixture_edit_recipe.json"
        recipe_path.write_text(json.dumps(recipe, ensure_ascii=False), encoding="utf-8")
        return recipe_path

    def run_adapter(self, recipe_path, out_dir, *extra_args):
        env = os.environ.copy()
        env["MUNJANGGUN_TEST_LOCAL_ROOT"] = str(self.local_root)
        return subprocess.run(
            ["node", str(SCRIPT), "--recipe", str(recipe_path), "--out", str(out_dir), *extra_args],
            cwd=ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

    def test_generates_hyperframes_pilot_from_qa_passed_recipe(self):
        recipe_path = self.write_recipe()
        out_dir = self.scratch / "out"

        result = self.run_adapter(recipe_path, out_dir)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((out_dir / "index.html").exists())
        self.assertTrue((out_dir / "DESIGN.md").exists())
        self.assertTrue((out_dir / "assets" / "after_main.jpg").exists())
        self.assertTrue((out_dir / "assets" / "voice.mp3").exists())

        html = (out_dir / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-composition-id="main"', html)
        self.assertIn('data-track-index="0"', html)

        package = json.loads((out_dir / "package.json").read_text(encoding="utf-8"))
        self.assertIn("hyperframes@0.6.121", package["scripts"]["check"])
        self.assertIn("Direct HyperFrames render is blocked", package["scripts"]["render"])
        self.assertNotIn("render:hyperframes", package["scripts"])

    def test_can_generate_scene_subcompositions(self):
        recipe_path = self.write_recipe()
        out_dir = self.scratch / "subcompositions"

        result = self.run_adapter(recipe_path, out_dir, "--subcompositions")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((out_dir / "index.html").exists())
        self.assertTrue((out_dir / "compositions" / "scene-01.html").exists())
        self.assertTrue((out_dir / "assets" / "after_main.jpg").exists())

        index_html = (out_dir / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-composition-src="compositions/scene-01.html"', index_html)
        self.assertIn('data-composition-id="main"', index_html)

        scene_html = (out_dir / "compositions" / "scene-01.html").read_text(encoding="utf-8")
        self.assertIn('<template id="scene-01-template">', scene_html)
        self.assertIn('<div id="scene-01" data-composition-id="scene-01" data-start="0" data-width="1080" data-height="1920">', scene_html)
        self.assertIn('../assets/after_main.jpg', scene_html)
        head_html = scene_html.split("</head>", 1)[0]
        template_html = scene_html.split('<template id="scene-01-template">', 1)[1].split("</template>", 1)[0]
        self.assertNotIn("gsap.min.js", head_html)
        self.assertIn('src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"', template_html)
        self.assertIn('window.__timelines["scene-01"]', scene_html)
        self.assertIn('class="photo-frame" data-studio-editable="photo-frame"', scene_html)
        self.assertIn('class="photo-motion"', scene_html)
        self.assertIn('data-studio-editable="caption-layout"', scene_html)
        self.assertIn('class="caption-motion"', scene_html)
        self.assertIn('tl.fromTo(".photo-motion"', scene_html)
        self.assertIn('tl.from(".caption-motion .line"', scene_html)
        self.assertNotIn('tl.fromTo(".photo"', scene_html)
        self.assertNotIn('tl.from(".caption .line"', scene_html)
        self.assertNotIn('tl.from(".caption",', scene_html)

    def test_rejects_recipe_without_passing_sync_manifest(self):
        recipe_path = self.write_recipe(sync_ok=False)
        out_dir = self.scratch / "bad-sync"

        result = self.run_adapter(recipe_path, out_dir)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sync_manifest.ok must be true", result.stderr)
        self.assertFalse((out_dir / "index.html").exists())

    def test_rejects_recipe_without_meaning_match(self):
        recipe_path = self.write_recipe(meaning_match=False)
        out_dir = self.scratch / "bad-meaning"

        result = self.run_adapter(recipe_path, out_dir)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("meaning_match must be true", result.stderr)
        self.assertFalse((out_dir / "index.html").exists())

    def test_rejects_tracked_repo_output_path(self):
        recipe_path = self.write_recipe()
        out_dir = ROOT / "docs" / "_hf_adapter_should_not_exist"

        result = self.run_adapter(recipe_path, out_dir)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Use --out under scratch/ or output/", result.stderr)
        self.assertFalse(out_dir.exists())


if __name__ == "__main__":
    unittest.main()
