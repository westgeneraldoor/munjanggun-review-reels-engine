import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "recipe-to-hyperframes-pilot.mjs"
SCRATCH = ROOT / "scratch" / "_test_hyperframes_adapter"


class HyperFramesAdapterTest(unittest.TestCase):
    def setUp(self):
        if SCRATCH.exists():
            shutil.rmtree(SCRATCH)
        (SCRATCH / "package" / "images").mkdir(parents=True)
        (SCRATCH / "package" / "images" / "after.jpg").write_bytes(b"fake image")
        (SCRATCH / "package" / "voice.mp3").write_bytes(b"fake audio")

    def tearDown(self):
        if SCRATCH.exists():
            shutil.rmtree(SCRATCH)

    def write_recipe(self, *, sync_ok=True, meaning_match=True):
        recipe = {
            "title": "fixture pilot",
            "source": {
                "package_dir": str(SCRATCH / "package"),
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
        recipe_path = SCRATCH / "package" / "fixture_edit_recipe.json"
        recipe_path.write_text(json.dumps(recipe, ensure_ascii=False), encoding="utf-8")
        return recipe_path

    def run_adapter(self, recipe_path, out_dir, *extra_args):
        return subprocess.run(
            ["node", str(SCRIPT), "--recipe", str(recipe_path), "--out", str(out_dir), *extra_args],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )

    def test_generates_hyperframes_pilot_from_qa_passed_recipe(self):
        recipe_path = self.write_recipe()
        out_dir = SCRATCH / "out"

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

    def test_can_generate_scene_subcompositions(self):
        recipe_path = self.write_recipe()
        out_dir = SCRATCH / "subcompositions"

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
        self.assertIn('data-composition-id="scene-01"', scene_html)
        self.assertIn('../assets/after_main.jpg', scene_html)
        self.assertIn('window.__timelines["scene-01"]', scene_html)

    def test_rejects_recipe_without_passing_sync_manifest(self):
        recipe_path = self.write_recipe(sync_ok=False)
        out_dir = SCRATCH / "bad-sync"

        result = self.run_adapter(recipe_path, out_dir)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sync_manifest.ok must be true", result.stderr)
        self.assertFalse((out_dir / "index.html").exists())

    def test_rejects_recipe_without_meaning_match(self):
        recipe_path = self.write_recipe(meaning_match=False)
        out_dir = SCRATCH / "bad-meaning"

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
