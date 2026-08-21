# Review Reel Efficient Revisions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent visual-only review-reel revisions from regenerating Gemini TTS, catch authoring and DOM layout failures before expensive artifacts, and stop unbounded same-narration retries.

**Architecture:** Preserve the existing full-hash mutation guard in `production_gate.py`. Add an immutable bound-recipe lock plus an official revision fork that retains current voice/SRT/report references, then validate reuse semantically against the existing narration and caption-timeline gates. Add a read-only authoring phase before TTS and a disposable browser layout probe before official HTML evidence is created.

**Tech Stack:** Python 3.11, `unittest`, Node.js 24, Playwright, existing v2 review-reel production gate and current-artifact ledger.

**Spec:** `docs/review_reels_one_shot_contract_v2.md`

## Global Constraints

- Keep `production_gate.py`'s report-bound full edit SHA-256 mutation check.
- Never modify, migrate, or commit `output/`, `reviews/`, customer media, voice, HTML, or MP4 artifacts.
- A visual-only revision may reuse voice only when canonical narration, voice bytes, report provenance, and the complete caption timeline remain valid.
- A narration change requires new official Gemini/Sulafat TTS.
- A caption-chunk or measured-timeline change requires a valid `review-reel-voice-alignment-v1` receipt or new TTS; do not synthesize fake measured alignment.
- Official HTML and MP4 approval gates remain unchanged.
- All behavior changes follow red-green-refactor TDD.

---

### Task 1: Bound recipe lock and diagnostic split

**Files:**
- Create: `video_engine_v2/recipe_revision.py`
- Modify: `video_engine_v2/one_shot_tts.py`
- Modify: `video_engine_v2/production_gate.py`
- Modify: `video_engine_v2/qa_guidance.py`
- Test: `tests/test_recipe_revision.py`
- Test: `tests/test_production_gate.py`

**Interfaces:**
- Produces: `lock_bound_recipe(package_dir, edit_path, report_path) -> Path`
- Produces: `verify_bound_recipe_lock(package_dir, edit_path, report_path) -> dict[str, Any]`
- Produces: `BOUND_RECIPE_MODIFIED` when the TTS report's original edit bytes changed.

- [ ] **Step 1: Write failing tests for lock receipt, read-only mode, and the precise mutation error**

```python
lock_path = lock_bound_recipe(package, edit, report)
self.assertTrue(lock_path.is_file())
self.assertFalse(edit.stat().st_mode & stat.S_IWUSR)
edit.chmod(stat.S_IWRITE | stat.S_IREAD)
edit.write_text("changed", encoding="utf-8")
with self.assertRaisesRegex(GateViolation, "BOUND_RECIPE_MODIFIED"):
    validate_voice_reuse_candidate(package, candidate_edit)
```

- [ ] **Step 2: Run the focused tests and verify missing APIs/error code fail**

Run: `python -X utf8 -m unittest tests.test_recipe_revision tests.test_production_gate`

- [ ] **Step 3: Implement atomic lock receipts and lock recipes after successful TTS/current-ledger recording**

```python
payload = {
    "schema_version": "review-reel-bound-recipe-lock-v1",
    "edit_recipe_relative_path": edit.relative_to(package).as_posix(),
    "edit_recipe_bytes": edit.stat().st_size,
    "edit_recipe_sha256": sha256(edit),
    "tts_report_relative_path": report.relative_to(package).as_posix(),
    "tts_report_sha256": sha256(report),
}
```

- [ ] **Step 4: Split original-edit mutation from current caption-timeline staleness**

Change the report-bound edit mismatch to `BOUND_RECIPE_MODIFIED`; retain `VOICE_CAPTION_TIMELINE_STALE` for current caption timeline/SRT mismatch.

- [ ] **Step 5: Update safe error guidance and run focused tests green**

`BOUND_RECIPE_MODIFIED` must direct operators to an intact locked revision. `VOICE_CAPTION_TIMELINE_STALE` must first distinguish unchanged narration plus changed chunks from changed narration, and must not unconditionally say regenerate.

Run: `python -X utf8 -m unittest tests.test_recipe_revision tests.test_production_gate tests.test_recipe_scaffold`

### Task 2: Official visual-only revision fork and reuse check

**Files:**
- Modify: `video_engine_v2/recipe_revision.py`
- Modify: `video_engine_v2/review_reel_intake.py`
- Modify: `scripts/review_reel_intake.py`
- Test: `tests/test_recipe_revision.py`
- Test: `tests/test_review_reel_intake.py`

**Interfaces:**
- Produces: `fork_recipe_for_voice_reuse(output_root, expected_content_id, planning_path, edit_path) -> dict[str, Any]`
- Produces: `check_voice_reuse(output_root, expected_content_id, edit_path) -> dict[str, Any]`
- CLI: `recipe-fork-reuse-voice`
- CLI: `voice-reuse-check`

- [ ] **Step 1: Write failing behavior tests**

```python
forked = fork_recipe_for_voice_reuse(...)
self.assertRegex(Path(forked["edit"]).name, r"_v\d+_edit_recipe\.json$")
self.assertEqual(new_edit["source"], old_edit["source"])
self.assertEqual(new_edit["audio_plan"], old_edit["audio_plan"])
self.assertTrue(check_voice_reuse(...)["eligible_for_voice_reuse"])
```

Tests must also reject stale source recipes, narration changes, caption-timeline changes, collisions, paths outside the package, and active content-ID mismatch.

- [ ] **Step 2: Run tests red**

Run: `python -X utf8 -m unittest tests.test_recipe_revision tests.test_review_reel_intake`

- [ ] **Step 3: Implement immutable `vN -> vN+1` planning/edit copies**

The fork uses exclusive creation, keeps source audio evidence references unchanged, writes a hash-bound fork receipt under `_work/recipe_forks/`, and does not move current-artifact pointers.

- [ ] **Step 4: Implement read-only semantic reuse validation**

Validation calls the existing canonical narration, final voice, report provenance, exact caption timeline/SRT, lock receipt, and current-ledger checks. It writes nothing.

- [ ] **Step 5: Wire both official CLI commands and run tests green**

Run: `python -X utf8 -m unittest tests.test_recipe_revision tests.test_review_reel_intake tests.test_recipe_scaffold`

### Task 3: Pre-TTS authoring gate and retry circuit breaker

**Files:**
- Modify: `video_engine_v2/reels_qa.py`
- Modify: `video_engine_v2/one_shot_tts.py`
- Modify: `video_engine_v2/review_reel_intake.py`
- Modify: `scripts/review_reel_intake.py`
- Test: `tests/test_review_reels_one_shot_contract.py`
- Test: `tests/test_one_shot_tts.py`
- Test: `tests/test_review_reel_intake.py`

**Interfaces:**
- Produces: `validate_review_reels_one_shot_authoring(planning, edit) -> dict[str, Any]`
- CLI: `authoring-check`
- Error: `AUTHORING_CHECK_FAILED:<comma-separated-codes>` before any TTS API call.
- Error: `TTS_ATTEMPT_BUDGET_EXCEEDED` before a third official API generation for the same canonical narration hash.

- [ ] **Step 1: Write failing authoring-phase tests**

The authoring result must report narrative-role, shot-count, hook-duration, proof-dwell, claim-evidence, caption-line metadata, and thin-context failures together while deferring voice-byte/provenance/compression checks.

- [ ] **Step 2: Verify red**

Run: `python -X utf8 -m unittest tests.test_review_reels_one_shot_contract tests.test_one_shot_tts`

- [ ] **Step 3: Implement the filtered authoring phase and invoke it before `generate.generate_voice`**

The TTS test patches `generate.generate_voice` and asserts it was never called when authoring is invalid.

- [ ] **Step 4: Write and verify a failing third-attempt test**

Create two valid non-derived TTS reports with the same `tts_text_sha256`; assert the third attempt raises before the external generator is called. Different narration hashes and alignment-derived reports do not consume this API budget.

- [ ] **Step 5: Implement attempt counting and CLI authoring-check**

Run: `python -X utf8 -m unittest tests.test_review_reels_one_shot_contract tests.test_one_shot_tts tests.test_review_reel_intake`

### Task 4: Disposable DOM caption layout precheck

**Files:**
- Create: `scripts/html-layout-precheck.mjs`
- Modify: `build_html_preview_v2.py`
- Modify: `scripts/produce_review_v2.py`
- Modify: `video_engine_v2/review_reel_intake.py`
- Modify: `scripts/review_reel_intake.py`
- Test: `tests/test_html_layout_precheck.py`
- Test: `tests/test_produce_review_v2.py`

**Interfaces:**
- Produces: `build_layout_probe(recipe_path, output_dir, engine_font_path=None) -> Path`
- CLI: `produce_review_v2.py layout-check --package ... --edit ...`
- CLI: `review_reel_intake.py layout-check --output-root ... --expected-content-id ... --edit ...`
- Error: `CAPTION_DOM_LINE_COUNT_EXCESSIVE` with every failing beat/chunk.

- [ ] **Step 1: Write a failing Playwright integration test**

Use the real v2 template and a long Korean caption that wraps to three lines despite `caption_layout.line_count = 1`. Assert nonzero exit, the exact beat/chunk, and no package HTML/frames/QA evidence.

- [ ] **Step 2: Run the focused test red**

Run: `python -X utf8 -m unittest tests.test_html_layout_precheck`

- [ ] **Step 3: Implement a temporary preview with the production template**

The probe resolves package assets and the production font but writes only inside `TemporaryDirectory`; it never creates a gate receipt, official preview directory, artifact evidence, frames, or ledger pointers.

- [ ] **Step 4: Implement the low-cost browser sampler**

For every caption chunk, scrub the real template, calculate rendered `.caption-line` height divided by computed line-height, and return all chunks whose line count exceeds two or crosses the caption safe area.

- [ ] **Step 5: Wire the official commands and run green**

Run: `python -X utf8 -m unittest tests.test_html_layout_precheck tests.test_html_preview_qa tests.test_produce_review_v2 tests.test_review_reel_intake`

### Task 5: Operating contract and workflow routing

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/review_reels_one_shot_contract_v2.md`
- Modify: `docs/review_reels_visual_edit_standard_v1.md`
- Modify: `tests/test_authority_documents.py`
- Modify: `video_engine_v2/review_reel_intake.py`

**Interfaces:**
- `workflow-next` returns authoring check, layout check, reuse/fork, or explicit stop commands at the correct stage.

- [ ] **Step 1: Add failing workflow behavior tests**

Assert that a completed scaffold without voice routes to `authoring-check`, a visual-only post-voice revision routes to `voice-reuse-check`, and two same-narration API reports route to an explicit stop instead of another TTS command.

- [ ] **Step 2: Verify red**

Run: `python -X utf8 -m unittest tests.test_review_reel_intake tests.test_authority_documents`

- [ ] **Step 3: Update workflow routing and authority docs**

Document the three-way decision:

```text
narration changed -> new official TTS
narration unchanged + caption timeline unchanged -> fork and reuse exact evidence
narration unchanged + caption timeline changed -> measured alignment/calibration or explicit stop
```

State that bound recipes are immutable/read-only, authoring-check precedes TTS, layout-check precedes official preflight/HTML, and a third same-narration API attempt is blocked.

- [ ] **Step 4: Run focused documentation and workflow tests green**

Run: `python -X utf8 -m unittest tests.test_review_reel_intake tests.test_authority_documents tests.test_recipe_scaffold`

### Task 6: Full verification and delivery

**Files:**
- Verify all files above.

**Interfaces:**
- Produces a tested engine-only commit; no local customer artifact mutations.

- [ ] **Step 1: Run all Python tests**

Run: `python -X utf8 -m unittest discover -s tests`
Expected: all tests pass, zero failures.

- [ ] **Step 2: Run repository validation**

Run: `npm run validate`
Expected: exit 0.

- [ ] **Step 3: Inspect diff and protected paths**

Run: `git status --short && git diff --check && git diff --stat`
Expected: only engine code, docs, tests, and this plan; no `output/`, `reviews/`, media, secrets, or generated browser evidence.

- [ ] **Step 4: Commit the feature branch, merge to main, rerun validation, and push**

Use a non-force push. Verify `HEAD == origin/main` afterward.

- [ ] **Step 5: Verify original package 122 remains valid and approval-gated**

Run from the original project root:

```powershell
python -X utf8 scripts/review_reel_intake.py workflow-next --output-root output
```

Expected: content ID `122`, valid HTML, waiting for explicit HTML approval; no MP4 authority inferred.

## Self-review

- Spec coverage: immutable evidence, safe reuse, pre-TTS authoring, pre-HTML DOM layout, retry stop, documentation, and protected artifact boundaries are assigned to Tasks 1-6.
- Deliberate exclusion: no automatic alignment generator is included because the repository has no approved forced-aligner dependency and no production alignment examples. The existing measured-alignment/calibration path remains authoritative.
- Placeholder scan: no implementation placeholder or future-code stub is required by this plan.
- Type consistency: fork/check/lock functions and CLI names are defined once and consumed consistently.
