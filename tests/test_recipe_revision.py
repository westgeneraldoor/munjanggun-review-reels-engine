import hashlib
import json
import stat
import tempfile
import unittest
from pathlib import Path

from video_engine_v2.recipe_revision import (
    RecipeRevisionViolation,
    check_voice_reuse_candidate,
    fork_recipe_for_voice_reuse,
    lock_bound_recipe,
    verify_bound_recipe_lock,
)
from video_engine_v2.reels_qa import canonical_tts_input_sha256
from video_engine_v2.one_shot_tts import _srt_from_timeline


class BoundRecipeLockTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.package = Path(self.tempdir.name).resolve() / "122_package"
        self.package.mkdir()
        self.edit = self.package / "122_story_one_shot_v1_edit_recipe.json"
        self.edit.write_text(json.dumps({"beats": [{"id": "b01"}]}), encoding="utf-8")
        self.report = self.package / "_work" / "122_story_one_shot_v1_tts_generation_report.json"
        self.report.parent.mkdir()
        self.report.write_text(
            json.dumps(
                {
                    "edit_recipe_relative_path": self.edit.name,
                    "edit_recipe_sha256": hashlib.sha256(self.edit.read_bytes()).hexdigest(),
                }
            ),
            encoding="utf-8",
        )

    def make_writable(self):
        self.edit.chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_lock_receipt_binds_edit_and_report_and_removes_owner_write_bit(self):
        self.addCleanup(self.make_writable)

        lock_path = lock_bound_recipe(self.package, self.edit, self.report)

        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "review-reel-bound-recipe-lock-v1")
        self.assertEqual(payload["edit_recipe_relative_path"], self.edit.name)
        self.assertEqual(payload["edit_recipe_sha256"], hashlib.sha256(self.edit.read_bytes()).hexdigest())
        self.assertEqual(
            payload["tts_report_relative_path"],
            self.report.relative_to(self.package).as_posix(),
        )
        self.assertFalse(self.edit.stat().st_mode & stat.S_IWUSR)
        self.assertEqual(verify_bound_recipe_lock(self.package, self.edit, self.report), payload)

    def test_lock_verification_rejects_an_edit_changed_after_binding(self):
        self.addCleanup(self.make_writable)
        lock_bound_recipe(self.package, self.edit, self.report)
        self.make_writable()
        self.edit.write_text(json.dumps({"beats": [{"id": "changed"}]}), encoding="utf-8")

        with self.assertRaisesRegex(RecipeRevisionViolation, "BOUND_RECIPE_MODIFIED"):
            verify_bound_recipe_lock(self.package, self.edit, self.report)


class VoiceReuseRevisionTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.package = Path(self.tempdir.name).resolve() / "122_package"
        self.package.mkdir()
        self.planning = self.package / "122_story_one_shot_v4_planning_recipe.json"
        self.planning.write_text(json.dumps({"content_id": "122"}), encoding="utf-8")
        self.edit = self.package / "122_story_one_shot_v4_edit_recipe.json"
        self.voice = self.package / "122_story_one_shot_v4_voice.mp3"
        self.voice.write_bytes(b"gemini-sulafat-v4")
        self.srt = self.package / "122_story_one_shot_v4.srt"
        self.report = self.package / "_work" / "122_story_one_shot_v4_tts_generation_report.json"
        self.report.parent.mkdir()
        timeline = [
            {
                "beat_id": "b01",
                "chunk_index": 1,
                "start_sec": 0.0,
                "end_sec": 3.0,
                "text": "현관이 달라졌습니다.",
                "display_text": "현관이 달라졌습니다.",
            }
        ]
        edit = {
            "source": {
                "script": "122_story_one_shot_v4_script.md",
                "srt": self.srt.name,
                "voice": self.voice.name,
                "tts_generation_report": self.report.relative_to(self.package).as_posix(),
            },
            "audio_plan": {
                "tts_text_sha256": "0" * 64,
                "final_voice_sha256": hashlib.sha256(self.voice.read_bytes()).hexdigest(),
                "sync_policy": {
                    "raw_tts_duration_sec": 3.2,
                    "final_voice_duration_sec": 3.0,
                },
            },
            "asset_evidence": {"after": {"evidence_class": "installed_result"}},
            "beats": [
                {
                    "id": "b01",
                    "narration_ref": "현관이 달라졌습니다.",
                    "caption_chunks": [
                        {
                            "text": "현관이 달라졌습니다.",
                            "display_text": "현관이 달라졌습니다.",
                            "start_sec": 0.0,
                            "end_sec": 3.0,
                        }
                    ],
                }
            ],
        }
        edit["audio_plan"]["tts_text_sha256"] = canonical_tts_input_sha256(edit)
        self.edit.write_text(json.dumps(edit, ensure_ascii=False), encoding="utf-8")
        (self.package / edit["source"]["script"]).write_text("fixture", encoding="utf-8")
        self.srt.write_text(_srt_from_timeline(timeline), encoding="utf-8")
        self.report.write_text(
            json.dumps(
                {
                    "schema_version": "review-reel-tts-generation-report-v1",
                    "provider": "google_gemini_tts",
                    "model": "gemini-3.1-flash-tts-preview",
                    "voice": "Sulafat",
                    "tts_text_sha256": edit["audio_plan"]["tts_text_sha256"],
                    "voice_relative_path": self.voice.name,
                    "voice_bytes": self.voice.stat().st_size,
                    "voice_sha256": hashlib.sha256(self.voice.read_bytes()).hexdigest(),
                    "raw_tts_duration_sec": 3.2,
                    "final_voice_duration_sec": 3.0,
                    "caption_timeline_schema": "review-reel-voice-caption-timeline-v1",
                    "caption_timeline": timeline,
                    "edit_recipe_relative_path": self.edit.name,
                    "edit_recipe_sha256": hashlib.sha256(self.edit.read_bytes()).hexdigest(),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.addCleanup(lambda: self.edit.chmod(stat.S_IREAD | stat.S_IWRITE))
        lock_bound_recipe(self.package, self.edit, self.report)

    def test_fork_creates_next_revision_without_changing_audio_evidence(self):
        result = fork_recipe_for_voice_reuse(
            self.package,
            planning_path=self.planning,
            edit_path=self.edit,
        )

        forked_planning = Path(result["planning"])
        forked_edit = Path(result["edit"])
        self.assertEqual(forked_planning.name, "122_story_one_shot_v5_planning_recipe.json")
        self.assertEqual(forked_edit.name, "122_story_one_shot_v5_edit_recipe.json")
        old = json.loads(self.edit.read_text(encoding="utf-8"))
        new = json.loads(forked_edit.read_text(encoding="utf-8"))
        self.assertEqual(new["source"], old["source"])
        self.assertEqual(new["audio_plan"], old["audio_plan"])
        self.assertTrue(Path(result["fork_receipt"]).is_file())
        self.assertTrue(check_voice_reuse_candidate(self.package, forked_edit)["eligible_for_voice_reuse"])

    def test_visual_metadata_change_remains_eligible_but_caption_change_does_not(self):
        result = fork_recipe_for_voice_reuse(self.package, planning_path=self.planning, edit_path=self.edit)
        forked_edit = Path(result["edit"])
        candidate = json.loads(forked_edit.read_text(encoding="utf-8"))
        candidate["asset_evidence"]["after"]["evidence_class"] = "installation_process"
        forked_edit.write_text(json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
        self.assertTrue(check_voice_reuse_candidate(self.package, forked_edit)["eligible_for_voice_reuse"])

        candidate["beats"][0]["caption_chunks"][0]["text"] = "청크가 달라졌습니다."
        forked_edit.write_text(json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(RecipeRevisionViolation, "VOICE_CAPTION_TIMELINE_STALE"):
            check_voice_reuse_candidate(self.package, forked_edit)

    def test_narration_change_requires_new_tts(self):
        result = fork_recipe_for_voice_reuse(self.package, planning_path=self.planning, edit_path=self.edit)
        forked_edit = Path(result["edit"])
        candidate = json.loads(forked_edit.read_text(encoding="utf-8"))
        candidate["beats"][0]["narration_ref"] = "나레이션이 달라졌습니다."
        forked_edit.write_text(json.dumps(candidate, ensure_ascii=False), encoding="utf-8")

        with self.assertRaisesRegex(RecipeRevisionViolation, "TTS_TEXT_HASH_MISMATCH"):
            check_voice_reuse_candidate(self.package, forked_edit)

    def test_refuses_to_fork_a_bound_recipe_that_was_modified(self):
        self.edit.chmod(stat.S_IREAD | stat.S_IWRITE)
        self.edit.write_text("{}", encoding="utf-8")

        with self.assertRaisesRegex(RecipeRevisionViolation, "BOUND_RECIPE_MODIFIED"):
            fork_recipe_for_voice_reuse(self.package, planning_path=self.planning, edit_path=self.edit)


if __name__ == "__main__":
    unittest.main()
