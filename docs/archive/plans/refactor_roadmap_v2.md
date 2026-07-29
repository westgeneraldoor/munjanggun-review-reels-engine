# Munjanggun Video Engine v2 Refactor Roadmap

This roadmap moves the current v1 system into a planning-recipe-first v2 system without breaking existing review, script, SRT, HTML, or MP4 generation.

The rule is simple:

```text
Do not replace v1 yet.
Add v2 beside it.
Prove v2 with 005_여름에어컨 first.
Then expand to 010 and 004.
```

## Refactor Principles

- Keep all existing v1 outputs and file names intact.
- Write every v2 output with an explicit variant suffix such as `ad_v2`.
- Make the planning recipe the source of truth.
- Generate narration, subtitles, HTML, and MP4 from the planning recipe.
- Sync scenes and captions after measuring the actual voice length.
- Use `nelnasamchae.ttf` as the default video font.
- Avoid unsupported absolute claims such as `완벽 차단`, `무조건 절약`, or guaranteed outcomes.

---

# Phase 1. Current Structure Audit

## Work

- Map the current generation path from review input to final MP4.
- Identify which files currently create script, SRT, voice, edit recipe, HTML, and MP4.
- Record current assumptions about durations, asset naming, image role detection, caption placement, and render paths.
- Compare v1 artifacts for 005, 010, and 004 to list repeated visual patterns.
- Mark which parts are stable enough to reuse and which parts should stay experimental.

## Files To Review

- `generate.py`
- `build_html_preview_v2.py`
- `render_html_preview_v2.js`
- `VIDEO_DIRECTION_V2.md`
- `VIDEO_RECIPE_SCHEMA_V2.md`
- `docs/hyperframe_motion_rulebook_v1.2.md`
- `docs/hyperframe_scene_library_v1.yaml`
- `output/inbox_20260609/*/*_edit_recipe_v2.json`

## Files To Modify

- None in this phase.

## New Files

- Optional historical context: `../audits/current_video_pipeline_audit.md`

## Risks

- Some v1 behavior may live inside one-off scripts instead of reusable functions.
- Existing recipe files may mix planning decisions and render instructions.
- SRT duration may not match voice duration.

## Verification

- Produce a short audit table of current input and output paths.
- Confirm the three existing MP4s still render or are already present.
- Confirm no v1 files were overwritten.

## Done Criteria

- We know exactly where v1 decisions are made.
- We know which functions can be reused for v2.
- We know where v2 should be added without disturbing v1.

---

# Phase 2. Add Planning Recipe Schema

## Work

- Add a v2 planning recipe schema above the current edit recipe.
- Keep the existing `*_edit_recipe_v2.json` render recipe format for now.
- Define conversion from planning recipe to current edit recipe.
- Add validation rules for purpose, type, scenes, hooks, review proof, CTA, and audio sync.

## Files To Review

- `docs/video_recipe_schema_v2.md`
- `VIDEO_RECIPE_SCHEMA_V2.md`
- existing `*_edit_recipe_v2.json` files

## Files To Modify

- `build_html_preview_v2.py` only if it needs to read new metadata safely.

## New Files

- `src/video_engine_v2/recipe_schema.py`
- `src/video_engine_v2/recipe_validator.py`
- `tests/test_video_recipe_schema_v2.py`

If the project remains flat instead of adding `src/`, use:

- `video_engine_v2_recipe_schema.py`
- `video_engine_v2_recipe_validator.py`

## Risks

- Over-designing the schema before the 005 pilot can slow progress.
- Too many required fields will make manual testing painful.
- Render-only fields and planning fields may get mixed again.

## Verification

- Validate one hand-written planning recipe for 005.
- Convert it into a current edit recipe without rendering changes.
- Run existing tests.

## Done Criteria

- A planning recipe can be loaded and validated.
- A planning recipe can produce the current HTML preview recipe.
- Invalid missing fields fail clearly.

---

# Phase 3. Improve Review Analyzer

## Work

- Extract performance-useful signals from review text:
  - customer problem
  - before pain
  - after change
  - customer emotion
  - strongest review quote
  - proof phrases
  - CTA angle
  - risk flags
- Separate raw review quotes from edited display quotes.
- Prevent invented or exaggerated claims.

## Files To Review

- `generate.py`
- generated `script.md`
- generated `srt`
- review capture and review text sources in the three test packages

## Files To Modify

- `generate.py` only if the current analyzer is inside it and can be safely wrapped.

## New Files

- `src/video_engine_v2/review_analyzer.py`
- `tests/test_review_analyzer_v2.py`

## Risks

- Review text may be available only as image capture in some packages.
- OCR or manual extraction may be needed later.
- The analyzer may create attractive but unsupported claims if not constrained.

## Verification

- Run analyzer against 005, 010, and 004.
- Confirm it extracts different strategic angles:
  - 005: cooling effect / seasonal ad
  - 010: old building noise / conversion
  - 004: difficult installation / trust
- Confirm all display quotes are grounded in source meaning.

## Done Criteria

- Each test review produces usable analysis fields.
- Risk flags are present for claims that should be softened.
- Review capture and review quote roles are separated.

---

# Phase 4. Add Template Selector

## Work

- Add purpose selection:
  - `ad`
  - `feed_trust`
  - `retargeting`
  - `brand_expertise`
  - `story_highlight`
- Add video type classification:
  - `cooling_effect`
  - `old_building_noise`
  - `difficult_installation`
  - `living_installation`
  - `cost_concern`
- Select length, CTA strength, energy curve, caption tone, and review proof mode from purpose + type.

## Files To Review

- `docs/video_templates_v2.md`
- `docs/hyperframe_scene_library_v1.yaml`
- current image naming conventions in `output/inbox_20260609`

## Files To Modify

- None unless integrating with `generate.py`.

## New Files

- `src/video_engine_v2/purpose_selector.py`
- `src/video_engine_v2/video_type_classifier.py`
- `src/video_engine_v2/templates.py`
- `tests/test_template_selector_v2.py`

## Risks

- The same review may fit multiple types.
- Asset names may be inconsistent across future folders.
- Forcing a template too early can make videos feel repetitive.

## Verification

- 005 selects `ad + cooling_effect`.
- 010 selects `retargeting/ad + old_building_noise`.
- 004 selects `brand_expertise + difficult_installation`.
- Selector returns at least one fallback template when confidence is low.

## Done Criteria

- Template selection is explainable.
- Purpose changes the output length and CTA behavior.
- Video type changes the scene order and visual grammar.

---

# Phase 5. Add Timeline Planner

## Work

- Build scenes before narration and SRT.
- Generate hook candidates, select one, and allocate time ranges.
- Assign scene roles:
  - `hook`
  - `problem`
  - `context`
  - `solution`
  - `process`
  - `before_after`
  - `review_proof`
  - `cta`
- Map images to scene roles using file names and package context.
- Add scene-specific transition and motion intent.

## Files To Review

- `docs/video_templates_v2.md`
- `docs/video_recipe_schema_v2.md`
- `build_html_preview_v2.py`
- current recipes for 005, 010, 004

## Files To Modify

- `build_html_preview_v2.py` only after the planner output is stable.

## New Files

- `src/video_engine_v2/hook_generator.py`
- `src/video_engine_v2/timeline_planner.py`
- `src/video_engine_v2/scene_allocator.py`
- `tests/test_timeline_planner_v2.py`

## Risks

- Timeline may become mechanically correct but creatively flat.
- Too many short scenes can cause sync drift and viewer fatigue.
- First two seconds can become over-designed and unclear.

## Verification

- 005 ad timeline is 20-23 seconds.
- Hook is a complete sentence.
- Review proof appears before CTA.
- CTA has a protected final 1.5-3 seconds.
- No scene has an unreadable caption.

## Done Criteria

- Planner produces a complete planning recipe.
- Scene order differs by video type.
- The 005 plan is clearly stronger than the v1 sequence on paper.

---

# Phase 6. Add Audio-Based Sync Realignment

## Work

- Measure generated voice duration.
- Compare planned timeline duration with actual audio duration.
- Adjust scene boundaries while preserving:
  - hook
  - review proof
  - CTA
- Regenerate subtitle timings from adjusted scene timings.
- Prevent captions and visual transitions from running ahead of narration.

## Files To Review

- `generate.py`
- SRT generation code
- `render_html_preview_v2.js`
- current 005 sync fixes

## Files To Modify

- SRT generation code in `generate.py` or a new wrapper.
- `build_html_preview_v2.py` if it needs to consume adjusted timing metadata.

## New Files

- `src/video_engine_v2/audio_sync_engine.py`
- `src/video_engine_v2/subtitle_recipe_generator.py`
- `tests/test_audio_sync_engine_v2.py`

## Risks

- Voice duration may differ every regeneration.
- SRT may still exist for compatibility, but must not become the source of truth.
- CTA may be cut by `-shortest` if visual duration exceeds audio duration.

## Verification

- For 005, visual/caption progress should not outrun the voice.
- Final MP4 duration matches voice safely.
- CTA is visible before the video ends.
- Subtitle timing is generated from scene timing, not guessed independently.

## Done Criteria

- Audio sync pass can adjust scene times deterministically.
- Sync corrections are visible in recipe metadata.
- 005 no longer needs manual timing patching.

---

# Phase 7. 005_여름에어컨 v2 Pilot

## Work

- Create one isolated ad v2 variant for 005.
- Target 20-23 seconds.
- Use stronger hook:

```text
에어컨 풀가동해도 거실이 덥다면?
```

- Use review capture as evidence and extract one large readable quote.
- Add a final CTA:

```text
우리 집도 가능할까?
무료 방문 실측 상담
```

- Render HTML and MP4 with new v2 file names.

## Files To Review

- `output/inbox_20260609/005_여름에어컨_20260609_111335`
- `docs/video_templates_v2.md`
- `docs/video_recipe_schema_v2.md`

## Files To Modify

- Only v2 generator files and new 005 output files.
- Do not overwrite existing 005 v1 HTML or MP4.

## New Files

Recommended existing-package paths:

- `output/inbox_20260609/005_여름에어컨_20260609_111335/005_여름에어컨_ad_v2_planning_recipe.json`
- `output/inbox_20260609/005_여름에어컨_20260609_111335/005_여름에어컨_ad_v2_edit_recipe.json`
- `output/inbox_20260609/005_여름에어컨_20260609_111335/005_여름에어컨_ad_v2_narration.md`
- `output/inbox_20260609/005_여름에어컨_20260609_111335/005_여름에어컨_ad_v2.srt`
- `output/inbox_20260609/005_여름에어컨_20260609_111335/005_여름에어컨_ad_v2_html/index.html`
- `output/inbox_20260609/005_여름에어컨_20260609_111335/005_여름에어컨_ad_v2.mp4`

## Risks

- Existing voice may be too long for a true 20-23 second ad.
- Reusing v1 audio may limit how far the v2 pacing can improve.
- If review text is only in an image, quote extraction may need manual confirmation.

## Verification

- MP4 duration is 20-23 seconds if new voice is generated.
- If reusing v1 voice, clearly mark it as a sync-limited pilot.
- First frame communicates the problem instantly.
- Review quote is readable on mobile.
- CTA is visible for at least 1.5 seconds.

## Done Criteria

- 005 ad v2 exists as separate files.
- The video feels meaningfully different from the 010/004 v1 style.
- The result can be reviewed as an ad candidate, not just a case-study video.

---

# Phase 8. Re-render 010 and 004 by Purpose

## Work

- After 005 is approved, create purpose-specific v2 variants for 010 and 004.
- Do not simply copy the 005 structure.
- Use each case's natural strength:
  - 010: old building noise, smell, corridor discomfort, conversion.
  - 004: difficult installation, expertise, trust, retargeting/profile credibility.

## Files To Review

- `output/inbox_20260609/010_구축소음_20260609_095709`
- `output/inbox_20260609/004_어려운시공_20260609_102346`
- staff reference video for 010
- existing 004 v1 MP4 and recipe

## Files To Modify

- Only v2 generator files and new output variants.

## New Files

- `010_구축소음_ad_v2_*`
- `010_구축소음_retargeting_v2_*`
- `004_어려운시공_brand_expertise_v2_*`
- `004_어려운시공_retargeting_v2_*`

## Risks

- 010 may overclaim noise/smell blocking if copy is too aggressive.
- 004 may become too slow if it leans only on trust and process.
- If all templates share the same motion system, they may again feel too similar.

## Verification

- 010 opens with pain empathy, not instant solution.
- 004 opens with the "other company gave up" tension clearly.
- Both use different motion grammar from 005.
- Both preserve audio/caption/visual sync.

## Done Criteria

- 010 and 004 have at least one v2 variant each.
- The three v2 outputs have distinct strategic purposes.
- The system can now produce reusable v2 templates from real cases.

---

# Recommended Immediate Next Action

Do not refactor the whole project at once.

The best next step is:

```text
Phase 1 audit briefly
-> Phase 2 minimal planning recipe
-> Phase 7 005_여름에어컨 ad v2 pilot
```

005 is the right first pilot because it has the broadest seasonal pain, the clearest ad angle, and the easiest before/after promise to communicate without overclaiming.

Once 005 works, the system should expand to 010 and 004 as different purpose templates, not as clones.
