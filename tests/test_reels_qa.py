import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from video_engine_v2.reels_qa import (
    apply_sync_evidence,
    build_approval_log_markdown,
    build_sync_manifest,
    build_status_markdown,
    run_reels_qa,
    validate_html_preflight,
    validate_sync,
    write_package_control_files,
    write_sync_manifest,
)


class ReelsQaTest(unittest.TestCase):
    def test_sync_qa_rejects_scene_cps_over_hard_limit(self):
        recipe = {
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 1.0],
                    "asset": "before_main",
                    "caption": "짧은 장면",
                    "narration_ref": "가나다라마바사아자차카타파하가나다라마",
                },
                {
                    "id": "b02",
                    "time": [1.0, 5.0],
                    "asset": "after_main",
                    "caption": "여유 장면",
                    "narration_ref": "시공 후 달라진 분위기를 보여줍니다.",
                },
            ]
        }

        result = validate_sync(recipe)

        self.assertFalse(result["ok"])
        self.assertTrue(any(issue["code"] == "SCENE_CPS_TOO_HIGH" for issue in result["issues"]))
        self.assertEqual(result["scenes"][0]["scene_cps"], 19.0)

    def test_sync_qa_rejects_missing_narration_ref(self):
        recipe = {
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 2.0],
                    "asset": "before_main",
                    "caption": "복도 소리",
                }
            ]
        }

        result = validate_sync(recipe)

        self.assertFalse(result["ok"])
        self.assertTrue(any(issue["code"] == "MISSING_NARRATION_REF" for issue in result["issues"]))

    def test_preflight_rejects_empty_analysis_and_hooks_before_html(self):
        planning = {
            "analysis": {
                "customer_problem": "",
                "before_pain": "",
                "after_change": "",
                "customer_emotion": [],
            },
            "hooks": [],
            "selected_hook": {"text": "좋아졌습니다"},
        }
        edit_recipe = {
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 2.5],
                    "asset": "after_main",
                    "caption": "좋아졌습니다",
                    "narration_ref": "중문 설치 후 집 분위기가 좋아졌습니다.",
                }
            ]
        }

        result = validate_html_preflight(planning, edit_recipe)

        self.assertFalse(result["ok"])
        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("PLANNING_ANALYSIS_EMPTY", codes)
        self.assertIn("HOOKS_EMPTY", codes)
        self.assertIn("WEAK_HOOK", codes)

    def test_preflight_rejects_duplicate_review_capture_and_corrupt_marker(self):
        planning = {
            "analysis": {
                "customer_problem": "복도 소음",
                "before_pain": "집 안까지 들림",
                "after_change": "덜 신경 쓰임",
                "customer_emotion": ["안심"],
            },
            "hooks": [{"text": "복도 소리만 나면 짖던 강아지라면?"}],
            "selected_hook": {"text": "복도 소리만 나면 짖던 강아지라면?"},
        }
        edit_recipe = {
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 3.0],
                    "asset": "before_main",
                    "caption": "복도 소리만 나면\n짖던 강아지라면?",
                    "narration_ref": "복도 소리만 나면 강아지가 짖던 집이라면,",
                },
                {
                    "id": "b02",
                    "time": [3.0, 6.0],
                    "asset": "review_capture",
                    "caption": "실제 리뷰",
                    "narration_ref": "리뷰에도 남았습니다.",
                },
                {
                    "id": "b03",
                    "time": [6.0, 9.0],
                    "asset": "review_capture",
                    "caption": "??",
                    "narration_ref": "다시 한 번 리뷰로 확인합니다.",
                },
            ]
        }

        result = validate_html_preflight(planning, edit_recipe)

        self.assertFalse(result["ok"])
        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("DUPLICATE_REVIEW_CAPTURE", codes)
        self.assertIn("CORRUPT_TEXT_MARKER", codes)

    def test_preflight_requires_explicit_meaning_match_evidence(self):
        planning = {
            "analysis": {
                "customer_problem": "복도 소음",
                "before_pain": "집 안까지 들림",
                "after_change": "덜 신경 쓰임",
                "customer_emotion": ["안심"],
            },
            "hooks": [{"text": "복도 소리만 나면 짖던 강아지라면?"}],
            "selected_hook": {"text": "복도 소리만 나면 짖던 강아지라면?"},
        }
        edit_recipe = {
            "source": {"privacy_review": {"checked": True, "risk_items": []}},
            "audio_plan": {"sync_policy": {"raw_tts_duration_sec": 3.0, "final_voice_duration_sec": 3.0, "render_duration_sec": 3.0}},
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 3.0],
                    "asset": "before_main",
                    "caption": "복도 소리만 나면\n짖던 강아지라면?",
                    "narration_ref": "복도 소리만 나면 강아지가 짖던 집이라면,",
                }
            ],
        }

        result = validate_html_preflight(planning, edit_recipe)

        self.assertFalse(result["ok"])
        self.assertTrue(any(issue["code"] == "MEANING_MATCH_UNVERIFIED" for issue in result["issues"]))

    def test_preflight_accepts_current_top_level_planning_schema(self):
        planning = {
            "customer_problem": "상담 일정이 걱정됨",
            "before_pain": "시공 일정이 밀릴까 불안함",
            "after_change": "실측 후 일정대로 시공됨",
            "customer_emotion": ["안심"],
            "hooks": [{"caption": "금요일 실측,\n수요일 시공까지"}],
            "selected_hook": {"caption": "금요일 실측,\n수요일 시공까지"},
        }
        edit_recipe = {
            "source": {"privacy_review": {"checked": True, "risk_items": [], "unresolved_risks": []}},
            "audio_plan": {"sync_policy": {"raw_tts_duration_sec": 3.0, "final_voice_duration_sec": 3.0, "render_duration_sec": 3.0}},
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 3.0],
                    "asset": "measure_width",
                    "caption": "금요일 실측,\n수요일 시공까지",
                    "narration_ref": "금요일 실측하고 수요일에 시공까지 이어진 집입니다.",
                    "meaning_match": True,
                    "meaning_match_source": "planning_scene:s01",
                }
            ],
        }

        result = validate_html_preflight(planning, edit_recipe)

        self.assertTrue(result["ok"], result["issues"])

    def test_preflight_rejects_missing_privacy_review(self):
        planning = {
            "customer_problem": "상담 일정이 걱정됨",
            "before_pain": "시공 일정이 밀릴까 불안함",
            "after_change": "실측 후 일정대로 시공됨",
            "customer_emotion": ["안심"],
            "hooks": [{"caption": "금요일 실측,\n수요일 시공까지"}],
            "selected_hook": {"caption": "금요일 실측,\n수요일 시공까지"},
        }
        edit_recipe = {
            "audio_plan": {"sync_policy": {"raw_tts_duration_sec": 3.0, "final_voice_duration_sec": 3.0, "render_duration_sec": 3.0}},
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 3.0],
                    "asset": "measure_width",
                    "caption": "금요일 실측,\n수요일 시공까지",
                    "narration_ref": "금요일 실측하고 수요일에 시공까지 이어진 집입니다.",
                    "meaning_match": True,
                    "meaning_match_source": "planning_scene:s01",
                }
            ],
        }

        result = validate_html_preflight(planning, edit_recipe)

        self.assertFalse(result["ok"])
        self.assertTrue(any(issue["code"] == "PRIVACY_REVIEW_MISSING" for issue in result["issues"]))

    def test_preflight_accepts_sanitization_report_as_privacy_evidence(self):
        planning = {
            "customer_problem": "상담 일정이 걱정됨",
            "before_pain": "시공 일정이 밀릴까 불안함",
            "after_change": "실측 후 일정대로 시공됨",
            "customer_emotion": ["안심"],
            "hooks": [{"caption": "금요일 실측,\n수요일 시공까지"}],
            "selected_hook": {"caption": "금요일 실측,\n수요일 시공까지"},
        }
        edit_recipe = {
            "source": {"privacy_sanitization_report": "_work/privacy_report.json"},
            "audio_plan": {"sync_policy": {"raw_tts_duration_sec": 3.0, "final_voice_duration_sec": 3.0, "render_duration_sec": 3.0}},
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 3.0],
                    "asset": "measure_width",
                    "caption": "금요일 실측,\n수요일 시공까지",
                    "narration_ref": "금요일 실측하고 수요일에 시공까지 이어진 집입니다.",
                    "meaning_match": True,
                    "meaning_match_source": "planning_scene:s01",
                }
            ],
        }

        result = validate_html_preflight(planning, edit_recipe)

        self.assertTrue(result["ok"], result["issues"])

    def test_preflight_rejects_overcompressed_audio_metadata(self):
        planning = {
            "analysis": {
                "customer_problem": "현관 소음",
                "before_pain": "집 안까지 들림",
                "after_change": "덜 신경 쓰임",
                "customer_emotion": ["안심"],
            },
            "hooks": [{"text": "복도 소리만 나면 짖던 강아지라면?"}],
            "selected_hook": {"text": "복도 소리만 나면 짖던 강아지라면?"},
        }
        edit_recipe = {
            "audio_plan": {
                "raw_tts_duration_sec": 39.49,
                "final_voice_duration_sec": 28.94,
                "sync_policy": {"render_duration_sec": 28.94},
            },
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 4.0],
                    "asset": "before_main",
                    "caption": "복도 소리만 나면\n짖던 강아지라면?",
                    "narration_ref": "복도 소리만 나면 강아지가 짖던 집이라면,",
                    "meaning_match": True,
                }
            ],
        }

        result = validate_html_preflight(planning, edit_recipe)

        self.assertFalse(result["ok"])
        self.assertTrue(any(issue["code"] == "VOICE_COMPRESSION_TOO_HIGH" for issue in result["issues"]))

    def test_preflight_rejects_unverified_meaning_match_string(self):
        planning = {
            "analysis": {
                "customer_problem": "현관 소음",
                "before_pain": "집 안까지 들림",
                "after_change": "덜 신경 쓰임",
                "customer_emotion": ["안심"],
            },
            "hooks": [{"text": "복도 소리만 나면 짖던 강아지라면?"}],
            "selected_hook": {"text": "복도 소리만 나면 짖던 강아지라면?"},
        }
        edit_recipe = {
            "audio_plan": {"sync_policy": {"raw_tts_duration_sec": 4.0, "final_voice_duration_sec": 4.0, "render_duration_sec": 4.0}},
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 4.0],
                    "asset": "before_main",
                    "caption": "복도 소리만 나면\n짖던 강아지라면?",
                    "narration_ref": "복도 소리만 나면 강아지가 짖던 집이라면,",
                    "meaning_match": "false",
                }
            ],
        }

        result = validate_html_preflight(planning, edit_recipe)

        self.assertFalse(result["ok"])
        self.assertTrue(any(issue["code"] == "MEANING_MATCH_UNVERIFIED" for issue in result["issues"]))

    def test_preflight_reads_audio_compression_from_sync_policy(self):
        planning = {
            "analysis": {
                "customer_problem": "현관 소음",
                "before_pain": "집 안까지 들림",
                "after_change": "덜 신경 쓰임",
                "customer_emotion": ["안심"],
            },
            "hooks": [{"text": "복도 소리만 나면 짖던 강아지라면?"}],
            "selected_hook": {"text": "복도 소리만 나면 짖던 강아지라면?"},
        }
        edit_recipe = {
            "audio_plan": {
                "sync_policy": {
                    "raw_tts_duration_sec": 39.49,
                    "final_voice_duration_sec": 28.94,
                    "render_duration_sec": 28.94,
                }
            },
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 4.0],
                    "asset": "before_main",
                    "caption": "복도 소리만 나면\n짖던 강아지라면?",
                    "narration_ref": "복도 소리만 나면 강아지가 짖던 집이라면,",
                    "meaning_match": True,
                }
            ],
        }

        result = validate_html_preflight(planning, edit_recipe)

        self.assertFalse(result["ok"])
        self.assertTrue(any(issue["code"] == "VOICE_COMPRESSION_TOO_HIGH" for issue in result["issues"]))

    def test_preflight_rejects_missing_raw_tts_duration(self):
        planning = {
            "analysis": {
                "customer_problem": "현관 소음",
                "before_pain": "집 안까지 들림",
                "after_change": "덜 신경 쓰임",
                "customer_emotion": ["안심"],
            },
            "hooks": [{"text": "복도 소리만 나면 짖던 강아지라면?"}],
            "selected_hook": {"text": "복도 소리만 나면 짖던 강아지라면?"},
        }
        edit_recipe = {
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0, "render_duration_sec": 4.0}},
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 4.0],
                    "asset": "before_main",
                    "caption": "복도 소리만 나면\n짖던 강아지라면?",
                    "narration_ref": "복도 소리만 나면 강아지가 짖던 집이라면,",
                    "meaning_match": True,
                }
            ],
        }

        result = validate_html_preflight(planning, edit_recipe)

        self.assertFalse(result["ok"])
        self.assertTrue(any(issue["code"] == "RAW_TTS_DURATION_UNVERIFIED" for issue in result["issues"]))

    def test_preflight_rejects_render_duration_without_final_voice_duration(self):
        planning = {
            "analysis": {
                "customer_problem": "현관 소음",
                "before_pain": "집 안까지 들림",
                "after_change": "덜 신경 쓰임",
                "customer_emotion": ["안심"],
            },
            "hooks": [{"text": "복도 소리만 나면 짖던 강아지라면?"}],
            "selected_hook": {"text": "복도 소리만 나면 짖던 강아지라면?"},
        }
        edit_recipe = {
            "audio_plan": {"sync_policy": {"raw_tts_duration_sec": 4.0, "render_duration_sec": 4.0}},
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 4.0],
                    "asset": "before_main",
                    "caption": "복도 소리만 나면\n짖던 강아지라면?",
                    "narration_ref": "복도 소리만 나면 강아지가 짖던 집이라면,",
                    "meaning_match": True,
                    "meaning_match_source": "planning_scene:s01",
                }
            ],
        }

        result = validate_html_preflight(planning, edit_recipe)

        self.assertFalse(result["ok"])
        self.assertTrue(any(issue["code"] == "VOICE_DURATION_UNVERIFIED" for issue in result["issues"]))

    def test_run_reels_qa_sync_manifest_rejects_render_duration_without_final_voice_duration(self):
        edit_recipe = {
            "audio_plan": {"sync_policy": {"raw_tts_duration_sec": 4.0, "render_duration_sec": 4.0}},
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 4.0],
                    "asset": "before_main",
                    "caption": "복도 소리",
                    "narration_ref": "복도 소리를 말합니다.",
                    "meaning_match": True,
                    "meaning_match_source": "planning_scene:s01",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            edit_path = Path(temp_dir) / "edit.json"
            manifest_path = Path(temp_dir) / "sync_manifest.json"
            edit_path.write_text(__import__("json").dumps(edit_recipe, ensure_ascii=False), encoding="utf-8")

            with redirect_stdout(StringIO()):
                exit_code = run_reels_qa(edit_path=edit_path, sync_manifest_out=manifest_path)

            self.assertEqual(exit_code, 1)
            self.assertIn("VOICE_DURATION_UNVERIFIED", manifest_path.read_text(encoding="utf-8"))

    def test_status_and_approval_files_make_scope_explicit(self):
        status = build_status_markdown(
            review_id="114",
            variant_id="pet_noise_relief_v1",
            current_html="114_html/index.html",
            current_voice="114_voice.mp3",
            current_recipe="114_edit_recipe.json",
            html_approved_by_user=True,
            mp4_allowed=False,
        )
        approval = build_approval_log_markdown(
            user_order="114번 리뷰 릴스 제작하자",
            approved_scope="대상 리뷰 지정",
            not_approved="MP4 렌더",
        )

        self.assertIn("mp4_allowed: false", status)
        self.assertIn("html_approved_by_user: true", status)
        self.assertIn("approved_scope: 대상 리뷰 지정", approval)
        self.assertIn("not_approved: MP4 렌더", approval)

    def test_write_package_control_files_does_not_overwrite_existing_logs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir)
            (package_dir / "APPROVAL_LOG.md").write_text("기존 승인 기록\n", encoding="utf-8")

            written = write_package_control_files(
                package_dir,
                review_id="114",
                variant_id="pet_noise_relief_v1",
                current_html="preview/index.html",
                current_voice="voice.mp3",
                current_recipe="edit.json",
            )

            self.assertTrue(written["status"].exists())
            self.assertTrue(written["approval_log"].exists())
            self.assertIn("기존 승인 기록", written["approval_log"].read_text(encoding="utf-8"))

    def test_write_package_control_files_does_not_overwrite_existing_status_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir)
            (package_dir / "STATUS.md").write_text("기존 상태\n", encoding="utf-8")

            written = write_package_control_files(
                package_dir,
                review_id="114",
                variant_id="pet_noise_relief_v1",
                current_html="preview/index.html",
                current_voice="voice.mp3",
                current_recipe="edit.json",
            )

            self.assertIn("기존 상태", written["status"].read_text(encoding="utf-8"))

    def test_build_sync_manifest_records_scene_evidence(self):
        edit_recipe = {
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 4.0],
                    "asset": "before_main",
                    "caption": "복도 소리만 나면\n짖던 강아지라면?",
                    "narration_ref": "복도 소리만 나면 강아지가 짖던 집이라면,",
                    "meaning_match": True,
                    "meaning_match_source": "pd_scene_plan:s01",
                }
            ]
        }

        manifest = build_sync_manifest(edit_recipe, raw_tts_duration_sec=4.2, final_voice_duration_sec=4.0)

        self.assertTrue(manifest["ok"])
        self.assertEqual(manifest["audio"]["compression_ratio"], 1.05)
        self.assertEqual(manifest["scenes"][0]["duration_sec"], 4.0)
        self.assertEqual(manifest["scenes"][0]["scene_cps"], 4.5)
        self.assertTrue(manifest["scenes"][0]["meaning_match"])
        self.assertEqual(manifest["scenes"][0]["meaning_match_evidence"], "pd_scene_plan:s01")
        self.assertEqual(manifest["scenes"][0]["meaning_match_source"], "pd_scene_plan:s01")

    def test_apply_sync_evidence_copies_explicit_planning_meaning_match(self):
        planning = {
            "scenes": [
                {
                    "scene_id": "s01",
                    "visual_source": {"role": "before_main"},
                    "caption": {"text": "복도 소리만 나면\n짖던 강아지라면?"},
                    "narration": "복도 소리만 나면 강아지가 짖던 집이라면,",
                    "meaning_match": True,
                }
            ]
        }
        edit_recipe = {
            "audio_plan": {},
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 4.0],
                    "asset": "before_main",
                    "caption": "복도 소리만 나면\n짖던 강아지라면?",
                    "narration_ref": "복도 소리만 나면 강아지가 짖던 집이라면,",
                }
            ],
        }

        enriched = apply_sync_evidence(
            planning,
            edit_recipe,
            raw_tts_duration_sec=4.2,
            final_voice_duration_sec=4.0,
        )

        beat = enriched["beats"][0]
        self.assertTrue(beat["meaning_match"])
        self.assertEqual(beat["meaning_match_source"], "planning_scene:s01")
        self.assertEqual(enriched["audio_plan"]["sync_policy"]["raw_tts_duration_sec"], 4.2)
        self.assertEqual(enriched["audio_plan"]["sync_policy"]["final_voice_duration_sec"], 4.0)
        self.assertIn("sync_manifest", enriched)

    def test_apply_sync_evidence_does_not_invent_meaning_match(self):
        planning = {
            "scenes": [
                {
                    "scene_id": "s01",
                    "visual_source": {"role": "before_main"},
                    "caption": {"text": "복도 소리"},
                    "narration": "복도 소리를 말합니다.",
                }
            ]
        }
        edit_recipe = {
            "audio_plan": {},
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 3.0],
                    "asset": "before_main",
                    "caption": "복도 소리",
                    "narration_ref": "복도 소리를 말합니다.",
                }
            ],
        }

        enriched = apply_sync_evidence(
            planning,
            edit_recipe,
            raw_tts_duration_sec=3.0,
            final_voice_duration_sec=3.0,
        )

        self.assertNotIn("meaning_match", enriched["beats"][0])
        self.assertFalse(enriched["sync_manifest"]["ok"])

    def test_write_sync_manifest_writes_json_file(self):
        edit_recipe = {
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 4.0],
                    "asset": "before_main",
                    "caption": "복도 소리",
                    "narration_ref": "복도 소리를 말합니다.",
                    "meaning_match": True,
                    "meaning_match_source": "planning_scene:s01",
                }
            ]
        }
        manifest = build_sync_manifest(edit_recipe, raw_tts_duration_sec=4.0, final_voice_duration_sec=4.0)
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "sync_manifest.json"

            written = write_sync_manifest(output_path, manifest)

            self.assertEqual(written, output_path)
            self.assertIn('"scene_id": "b01"', output_path.read_text(encoding="utf-8"))

    def test_preflight_rejects_meaning_match_true_without_evidence(self):
        planning = {
            "analysis": {
                "customer_problem": "현관 소음",
                "before_pain": "집 안까지 들림",
                "after_change": "덜 신경 쓰임",
                "customer_emotion": ["안심"],
            },
            "hooks": [{"text": "복도 소리만 나면 짖던 강아지라면?"}],
            "selected_hook": {"text": "복도 소리만 나면 짖던 강아지라면?"},
        }
        edit_recipe = {
            "audio_plan": {"sync_policy": {"raw_tts_duration_sec": 4.0, "final_voice_duration_sec": 4.0}},
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 4.0],
                    "asset": "before_main",
                    "caption": "복도 소리만 나면\n짖던 강아지라면?",
                    "narration_ref": "복도 소리만 나면 강아지가 짖던 집이라면,",
                    "meaning_match": True,
                }
            ],
        }

        result = validate_html_preflight(planning, edit_recipe)

        self.assertFalse(result["ok"])
        self.assertTrue(any(issue["code"] == "MEANING_MATCH_EVIDENCE_MISSING" for issue in result["issues"]))

    def test_build_sync_manifest_rejects_meaning_match_true_without_evidence(self):
        edit_recipe = {
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 4.0],
                    "asset": "before_main",
                    "caption": "복도 소리",
                    "narration_ref": "복도 소리를 말합니다.",
                    "meaning_match": True,
                }
            ]
        }

        manifest = build_sync_manifest(edit_recipe, raw_tts_duration_sec=4.0, final_voice_duration_sec=4.0)

        self.assertFalse(manifest["ok"])
        self.assertTrue(any(issue["code"] == "MEANING_MATCH_EVIDENCE_MISSING" for issue in manifest["issues"]))

    def test_build_sync_manifest_rejects_blank_meaning_match_evidence(self):
        edit_recipe = {
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 4.0],
                    "asset": "before_main",
                    "caption": "복도 소리",
                    "narration_ref": "복도 소리를 말합니다.",
                    "meaning_match": True,
                    "meaning_match_source": "   ",
                }
            ]
        }

        manifest = build_sync_manifest(edit_recipe, raw_tts_duration_sec=4.0, final_voice_duration_sec=4.0)

        self.assertFalse(manifest["ok"])
        self.assertTrue(any(issue["code"] == "MEANING_MATCH_EVIDENCE_MISSING" for issue in manifest["issues"]))

    def test_build_sync_manifest_rejects_non_positive_audio_duration(self):
        edit_recipe = {
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 4.0],
                    "asset": "before_main",
                    "caption": "복도 소리",
                    "narration_ref": "복도 소리를 말합니다.",
                    "meaning_match": True,
                    "meaning_match_source": "planning_scene:s01",
                }
            ]
        }

        manifest = build_sync_manifest(edit_recipe, raw_tts_duration_sec=-4.0, final_voice_duration_sec=0.0)

        self.assertFalse(manifest["ok"])
        codes = {issue["code"] for issue in manifest["issues"]}
        self.assertIn("RAW_TTS_DURATION_INVALID", codes)
        self.assertIn("VOICE_DURATION_INVALID", codes)

    def test_build_sync_manifest_rejects_total_voice_cps_over_hard_limit(self):
        fast_narration = "가" * 100
        edit_recipe = {
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 20.0],
                    "asset": "before_main",
                    "caption": "복도 소리",
                    "narration_ref": fast_narration,
                    "meaning_match": True,
                    "meaning_match_source": "planning_scene:s01",
                }
            ]
        }

        manifest = build_sync_manifest(edit_recipe, raw_tts_duration_sec=10.0, final_voice_duration_sec=10.0)

        self.assertFalse(manifest["ok"])
        self.assertEqual(manifest["audio"]["total_narration_chars_no_space"], 100)
        self.assertEqual(manifest["audio"]["total_voice_cps"], 10.0)
        self.assertTrue(any(issue["code"] == "TOTAL_VOICE_CPS_TOO_HIGH" for issue in manifest["issues"]))

    def test_preflight_rejects_total_voice_cps_over_hard_limit_even_when_scene_cps_passes(self):
        fast_narration = "가" * 100
        planning = {
            "analysis": {
                "customer_problem": "현관 소음",
                "before_pain": "집 안까지 들림",
                "after_change": "덜 신경 쓰임",
                "customer_emotion": ["안심"],
            },
            "hooks": [{"text": "복도 소리만 나면 짖던 강아지라면?"}],
            "selected_hook": {"text": "복도 소리만 나면 짖던 강아지라면?"},
        }
        edit_recipe = {
            "audio_plan": {
                "sync_policy": {
                    "raw_tts_duration_sec": 10.0,
                    "final_voice_duration_sec": 10.0,
                    "render_duration_sec": 20.0,
                }
            },
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 20.0],
                    "asset": "before_main",
                    "caption": "복도 소리만 나면\n짖던 강아지라면?",
                    "narration_ref": fast_narration,
                    "meaning_match": True,
                    "meaning_match_source": "planning_scene:s01",
                }
            ],
        }

        result = validate_html_preflight(planning, edit_recipe)

        self.assertFalse(result["ok"])
        self.assertTrue(any(issue["code"] == "TOTAL_VOICE_CPS_TOO_HIGH" for issue in result["issues"]))

    def test_preflight_rejects_explicit_zero_final_voice_duration_without_fallback(self):
        planning = {
            "analysis": {
                "customer_problem": "현관 소음",
                "before_pain": "집 안까지 들림",
                "after_change": "덜 신경 쓰임",
                "customer_emotion": ["안심"],
            },
            "hooks": [{"text": "복도 소리만 나면 짖던 강아지라면?"}],
            "selected_hook": {"text": "복도 소리만 나면 짖던 강아지라면?"},
        }
        edit_recipe = {
            "audio_plan": {
                "sync_policy": {
                    "raw_tts_duration_sec": 4.0,
                    "final_voice_duration_sec": 0.0,
                    "render_duration_sec": 4.0,
                }
            },
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 4.0],
                    "asset": "before_main",
                    "caption": "복도 소리만 나면\n짖던 강아지라면?",
                    "narration_ref": "복도 소리만 나면 강아지가 짖던 집이라면,",
                    "meaning_match": True,
                    "meaning_match_source": "planning_scene:s01",
                }
            ],
        }

        result = validate_html_preflight(planning, edit_recipe)

        self.assertFalse(result["ok"])
        self.assertTrue(any(issue["code"] == "VOICE_DURATION_INVALID" for issue in result["issues"]))

    def test_run_reels_qa_rejects_explicit_zero_final_voice_duration_without_fallback(self):
        edit_recipe = {
            "audio_plan": {
                "sync_policy": {
                    "raw_tts_duration_sec": 4.0,
                    "final_voice_duration_sec": 0.0,
                    "render_duration_sec": 4.0,
                }
            },
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 4.0],
                    "asset": "before_main",
                    "caption": "복도 소리",
                    "narration_ref": "복도 소리를 말합니다.",
                    "meaning_match": True,
                    "meaning_match_source": "planning_scene:s01",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            edit_path = Path(temp_dir) / "edit.json"
            manifest_path = Path(temp_dir) / "sync_manifest.json"
            edit_path.write_text(__import__("json").dumps(edit_recipe, ensure_ascii=False), encoding="utf-8")

            with redirect_stdout(StringIO()):
                exit_code = run_reels_qa(edit_path=edit_path, sync_manifest_out=manifest_path)

            self.assertEqual(exit_code, 1)
            self.assertIn("VOICE_DURATION_INVALID", manifest_path.read_text(encoding="utf-8"))

    def test_apply_sync_evidence_handles_zero_final_voice_duration_without_crashing(self):
        planning = {
            "scenes": [
                {
                    "scene_id": "s01",
                    "visual_source": {"role": "before_main"},
                    "caption": {"text": "복도 소리"},
                    "narration": "복도 소리를 말합니다.",
                    "meaning_match": True,
                }
            ]
        }
        edit_recipe = {
            "audio_plan": {},
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 4.0],
                    "asset": "before_main",
                    "caption": "복도 소리",
                    "narration_ref": "복도 소리를 말합니다.",
                }
            ],
        }

        enriched = apply_sync_evidence(
            planning,
            edit_recipe,
            raw_tts_duration_sec=4.0,
            final_voice_duration_sec=0.0,
        )

        self.assertFalse(enriched["sync_manifest"]["ok"])
        self.assertTrue(any(issue["code"] == "VOICE_DURATION_INVALID" for issue in enriched["sync_manifest"]["issues"]))

    def test_run_reels_qa_writes_sync_manifest_output(self):
        edit_recipe = {
            "audio_plan": {"sync_policy": {"raw_tts_duration_sec": 4.0, "final_voice_duration_sec": 4.0}},
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 4.0],
                    "asset": "before_main",
                    "caption": "복도 소리",
                    "narration_ref": "복도 소리를 말합니다.",
                    "meaning_match": True,
                    "meaning_match_source": "planning_scene:s01",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            edit_path = Path(temp_dir) / "edit.json"
            manifest_path = Path(temp_dir) / "sync_manifest.json"
            edit_path.write_text(__import__("json").dumps(edit_recipe, ensure_ascii=False), encoding="utf-8")

            with redirect_stdout(StringIO()):
                exit_code = run_reels_qa(edit_path=edit_path, sync_manifest_out=manifest_path)

            self.assertEqual(exit_code, 0)
            self.assertTrue(manifest_path.exists())
            self.assertIn('"compression_ratio": 1.0', manifest_path.read_text(encoding="utf-8"))

    def test_run_reels_qa_fails_when_written_sync_manifest_is_not_ok(self):
        edit_recipe = {
            "audio_plan": {"sync_policy": {"final_voice_duration_sec": 4.0}},
            "beats": [
                {
                    "id": "b01",
                    "time": [0.0, 4.0],
                    "asset": "before_main",
                    "caption": "복도 소리",
                    "narration_ref": "복도 소리를 말합니다.",
                    "meaning_match": True,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            edit_path = Path(temp_dir) / "edit.json"
            manifest_path = Path(temp_dir) / "sync_manifest.json"
            edit_path.write_text(__import__("json").dumps(edit_recipe, ensure_ascii=False), encoding="utf-8")

            with redirect_stdout(StringIO()):
                exit_code = run_reels_qa(edit_path=edit_path, sync_manifest_out=manifest_path)

            self.assertEqual(exit_code, 1)
            self.assertIn('"ok": false', manifest_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
