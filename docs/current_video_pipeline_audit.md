# Current Video Pipeline Audit

Date: 2026-06-11

This audit records the current v1 pipeline before the v2 planning-recipe implementation expands further.

## Current Project Shape

The project is currently a Python-first local automation project.

Main files:

- `generate.py`: review text to `script.md`, SRT, and MP3 voice.
- `build_html_preview_v2.py`: current edit recipe JSON to local HTML preview.
- `render_html_preview_v2.js`: local HTML preview to MP4 with Playwright screenshots and FFmpeg.
- `VIDEO_DIRECTION_V2.md`: staff-edit DNA and early video direction.
- `VIDEO_RECIPE_SCHEMA_V2.md`: early render/edit recipe idea.
- `docs/video_*_v2.md`: new planning-recipe-first v2 design docs.

Current generated review packages live under:

```text
output/inbox_20260609/{review_id}_{timestamp}/
```

## v1 Flow

```text
reviews/inbox_20260609/NNN_label.txt
-> generate.py
-> output package
   -> NNN_label_script.md
   -> NNN_label_subtitle.srt
   -> NNN_label_voice.mp3
-> manually or semi-manually created edit_recipe_v2.json
-> build_html_preview_v2.py
-> html_preview_v2/index.html
-> render_html_preview_v2.js
-> MP4
```

## Confirmed v1 Artifacts

### 005_여름에어컨

- Review: `reviews/inbox_20260609/005_여름에어컨.txt`
- Script: `output/inbox_20260609/005_여름에어컨_20260609_111335/005_여름에어컨_script.md`
- SRT: `output/inbox_20260609/005_여름에어컨_20260609_111335/005_여름에어컨_subtitle.srt`
- Voice: `output/inbox_20260609/005_여름에어컨_20260609_111335/005_여름에어컨_voice.mp3`
- Edit recipe: `output/inbox_20260609/005_여름에어컨_20260609_111335/005_여름에어컨_edit_recipe_v2.json`
- HTML preview: `output/inbox_20260609/005_여름에어컨_20260609_111335/005_여름에어컨_html_preview_v2/index.html`
- MP4: `output/inbox_20260609/005_여름에어컨_20260609_111335/005_여름에어컨_render_v1.mp4`

### 010_구축소음

- Staff reference: `output/inbox_20260609/010_구축소음_20260609_095709/010_구축소음_직원편집.mp4`
- Edit recipe: `output/inbox_20260609/010_구축소음_20260609_095709/010_구축소음_edit_recipe_v2.json`
- MP4: `output/inbox_20260609/010_구축소음_20260609_095709/010_구축소음_render_v1.mp4`

### 004_어려운시공

- Edit recipe: `output/inbox_20260609/004_어려운시공_20260609_102346/004_어려운시공_edit_recipe_v2.json`
- HTML preview: `output/inbox_20260609/004_어려운시공_20260609_102346/004_어려운시공_html_preview_v2/index.html`
- MP4: `output/inbox_20260609/004_어려운시공_20260609_102346/004_어려운시공_render_v1.mp4`

## What Works

- Review text parsing and trace metadata are stable enough.
- Script validation has unit tests.
- SRT generation works from `script.md` sections.
- TTS speed adjustment is already aware of target duration.
- HTML preview can render recipe-based photo/caption/motion sequences.
- MP4 rendering works locally through Playwright frames and FFmpeg.
- The project already supports Korean file paths.

## Main Limitations

### 1. Script-first order

The current flow generates script, SRT, and voice before the video is strategically planned. This makes the visual timeline react to narration instead of designing the hook, proof, CTA, and pacing first.

### 2. Edit recipe is doing too much

Current `*_edit_recipe_v2.json` mixes:

- strategy
- asset role mapping
- scene timing
- caption design
- motion choice
- render settings

v2 needs a planning recipe above it.

### 3. Similar visual grammar

005, 010, and 004 improved through manual tuning, but they still share too much of the same photo/caption/motion language. Future v2 templates must change scene grammar by content purpose and video type.

### 4. Review proof is late and dense

The review capture is useful evidence but difficult to read on mobile. v2 must use:

```text
review capture = evidence
review quote = readable copy
```

### 5. Audio sync is not yet a first-class pass

Generated SRT can target 35 seconds while voice may end near 27-30 seconds. The v2 engine must measure actual voice and adjust the visual recipe.

## Safe Reuse Points

- `generate.py` review parsing and output path conventions.
- Existing package folder convention.
- Existing image role naming from the three test packages.
- Existing HTML preview renderer once it receives compatible edit recipes.
- Existing MP4 renderer after HTML generation.

## v2 Attachment Point

The safest integration point is:

```text
planning_recipe_v2.json
-> edit_recipe.json compatible with build_html_preview_v2.py
-> existing HTML/MP4 render flow
```

This avoids breaking the current script/SRT/voice pipeline while allowing planning-first video variants.

## First Pilot Decision

005_여름에어컨 remains the best first v2 pilot.

Reasons:

- Seasonal pain is broad and easy to understand.
- The first two-second hook can be much stronger.
- Review has a grounded quote about cooling feeling.
- CTA can be consultative without overclaiming.

The first implementation should produce:

- `005_여름에어컨_ad_v2_planning_recipe.json`
- `005_여름에어컨_ad_v2_edit_recipe.json`
- `005_여름에어컨_ad_v2_narration.md`
- `005_여름에어컨_ad_v2.srt`
- `005_여름에어컨_ad_v2_html_preview_v2/index.html`

The first render can use the existing voice as a sync-safe bridge. A true 20-23 second ad should use newly generated voice from the v2 narration.
