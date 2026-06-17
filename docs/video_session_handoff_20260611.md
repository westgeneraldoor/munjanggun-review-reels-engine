# Video Engine v2 Session Handoff - 2026-06-11

This document is the quick-start handoff for a new Codex session.

## 2026-06-12 Approval Gate Update

When the user specifies only a review number, such as:

```text
033 리뷰 릴스 만들자
025번 해보자
```

that means the target review is chosen. It does **not** mean script/SRT/TTS/HTML are approved.

For number-only requests, stop after:

```text
review source check
photo folder check
photo role mapping
missing-shot/risk report
hook candidates
PD plan
scene-level asset/caption/narration meaning-match plan
```

Then ask for explicit planning approval.
Only after the user says `승인`, `이 방향으로 가`, `HTML 만들어`, `프리뷰 제작해`, or `진행해`, generate script/SRT/TTS/HTML.

Do not reuse `033_소음차단냄새먼지_entry_noise_smell_v2` as approved output. It passed TTS speed but failed scene meaning sync.

## 2026-06-11 Cleanup Update

Four MP4 renders now exist. The output folders were cleaned without deleting source material: old previews, duplicate renders, frame folders, and intermediate recipes were moved into each package's `_work/` folder.

Current final MP4s:

```text
output/inbox_20260609/005_여름에어컨_20260609_111335/005_여름에어컨_ad_v2_final_render_20260611.mp4
output/inbox_20260609/010_구축소음_20260609_095709/010_구축소음_old_building_noise_v2_final_render_20260611.mp4
output/inbox_20260609/004_어려운시공_20260609_102346/004_어려운시공_difficult_installation_v2_final_render_20260611.mp4
output/inbox_20260609/020_로봇청소구축리모델링_20260609_160414/020_로봇청소구축리모델링_living_flow_geninsert_v3_final_render_20260611.mp4
```

For new review publishing workflow, read:

```text
docs/review_video_publish_workflow_v2.md
```

For render QA rules, read:

```text
docs/render_qa_rules_v2.md
```

Important render fix:

```text
render_html_preview_v2.js now preserves the 390px HTML design layout and captures it with deviceScaleFactor.
Do not re-layout the stage at 1080px. That causes caption size/position drift between HTML and MP4.
```

005 was re-rendered after this fix:

```text
output/inbox_20260609/005_여름에어컨_20260609_111335/005_여름에어컨_ad_v2_final_render_20260611_scale_lock.mp4
```

The old 005 render with bad scale was moved to `_work/`.

## 2026-06-11 Scale-Lock Re-render Completion

The original MP4 renders had caption size/position drift because the renderer re-laid out the HTML stage at 1080px. The renderer now keeps the 390px preview design locked and captures it at high resolution through `deviceScaleFactor`.

Current approved scale-lock MP4s:

```text
output/inbox_20260609/005_여름에어컨_20260609_111335/005_여름에어컨_ad_v2_final_render_20260611_scale_lock.mp4
output/inbox_20260609/010_구축소음_20260609_095709/010_구축소음_old_building_noise_v2_final_render_20260611_scale_lock.mp4
output/inbox_20260609/004_어려운시공_20260609_102346/004_어려운시공_difficult_installation_v2_final_render_20260611_scale_lock.mp4
output/inbox_20260609/020_로봇청소구축리모델링_20260609_160414/020_로봇청소구축리모델링_living_flow_geninsert_v3_final_render_20260611_scale_lock.mp4
```

Representative frame contact sheets:

```text
output/inbox_20260609/005_여름에어컨_20260609_111335/_work/005_scale_lock_frame_check/contact_sheet.png
output/inbox_20260609/010_구축소음_20260609_095709/_work/010_scale_lock_frame_check/contact_sheet.png
output/inbox_20260609/004_어려운시공_20260609_102346/_work/004_scale_lock_frame_check/contact_sheet.png
output/inbox_20260609/020_로봇청소구축리모델링_20260609_160414/_work/020_scale_lock_frame_check/contact_sheet.png
```

Legacy bad-scale renders were moved to `_work/` with `legacy_bad_scale` in the filename.

Going forward, use only `*_scale_lock.mp4` as the current render output.

## One-Line Summary

Munjanggun review videos have moved from `review -> script/SRT/voice -> manual CapCut` toward a v2 system:

```text
review + photos
-> video purpose/type
-> planning recipe
-> narration/SRT/edit recipe
-> HTML preview
-> MP4 render
-> PD sync QA
```

The most important lesson is that a video is not approved until **voice, caption, and screen say the same thing at the same time**.

## Current Production Rule

Do not treat every review with one universal template.

Use at least these production types:

- `seasonal_ad`: broad pain + fast benefit, e.g. 005 summer aircon.
- `old_building_conversion`: old building discomfort + measurement + review proof, e.g. 010 old-building noise.
- `brand_expertise`: difficult-site trust proof, e.g. 004 difficult installation.
- `living_flow_threshold`: daily-life convenience, threshold, robot vacuum, child/living movement, e.g. 020.

## Hard-Won PD Rules

- First 2 seconds must be a complete viewer-facing hook.
- Scene count is useful only when each scene maps to a spoken idea.
- Product thumbnails must not be covered by center captions.
- Review capture is evidence; extract one quote as readable proof.
- Do not add floating chips/boxes/labels unless they truly improve the scene. Bad overlays are worse than no overlay.
- Generated images may be used only as short explanatory B-roll, never as fake proof.
- For generated B-roll, the visual requirement must be checked literally. Example: if the scene says `문턱 없이`, there must be no visible threshold, sill, rail, step, lip, or bump.

## Current Four HTML Previews

### 005 - 여름에어컨

- Type: `seasonal_ad`
- Purpose: ad test priority, seasonal cooling pain.
- HTML:
  `output/inbox_20260609/005_여름에어컨_20260609_111335/005_여름에어컨_ad_v2_final_html_preview_v2/index.html`
- Recipe:
  `output/inbox_20260609/005_여름에어컨_20260609_111335/005_여름에어컨_ad_v2_final_edit_recipe.json`
- User feedback: much improved, no major feedback.

### 010 - 구축소음

- Type: `old_building_noise`
- Purpose: conversion/retargeting for old villa/apartment noise and smell concern.
- HTML:
  `output/inbox_20260609/010_구축소음_20260609_095709/010_구축소음_old_building_noise_v2_final_html_preview_v2/index.html`
- Recipe:
  `output/inbox_20260609/010_구축소음_20260609_095709/010_구축소음_old_building_noise_v2_final_edit_recipe.json`
- User feedback: no issue.

### 004 - 어려운시공

- Type: `difficult_installation`
- Purpose: brand trust / difficult-site proof.
- HTML:
  `output/inbox_20260609/004_어려운시공_20260609_102346/004_어려운시공_difficult_installation_v2_final_html_preview_v2/index.html`
- Recipe:
  `output/inbox_20260609/004_어려운시공_20260609_102346/004_어려운시공_difficult_installation_v2_final_edit_recipe.json`
- User feedback: visually good, but audio/screen/caption sync still slightly off.

### 020 - 로봇청소구축리모델링

- Current approved direction: use generated B-roll only for missing daily-life scenes.
- Preferred preview is now the generated insert version, not the old plain version.
- Type: `living_flow_threshold_generated_insert`
- HTML:
  `output/inbox_20260609/020_로봇청소구축리모델링_20260609_160414/020_로봇청소구축리모델링_living_flow_geninsert_v3_html_preview_v2/index.html`
- Recipe:
  `output/inbox_20260609/020_로봇청소구축리모델링_20260609_160414/020_로봇청소구축리모델링_living_flow_geninsert_v3_edit_recipe.json`
- Generated assets:
  `output/inbox_20260609/020_로봇청소구축리모델링_20260609_160414/020_로봇청소구축리모델링_script/AI인서트_로봇청소기_문턱막힘.png`
  `output/inbox_20260609/020_로봇청소구축리모델링_20260609_160414/020_로봇청소구축리모델링_script/AI인서트_로봇청소기_문턱없음통과.png`
- Final timing adjustment:
  - product thumbnail starts at `11.0s`, not `12.2s`
  - result starts at `14.4s`
  - no-threshold robot-vacuum pass starts at `17.6s`
  - review starts at `21.0s`
  - CTA starts at `24.2s`

## 020 Sync Map

Current 020 geninsert v3 beat map:

```text
0.0-2.0   ai_robot_blocked     문턱에서 / 자꾸 막힌다면?
2.0-5.0   before_old_door      오래된 방문이 / 집 분위기를 눌렀습니다
5.0-8.1   before_room          문틀과 문턱까지 / 함께 봐야 했습니다
8.1-11.0  measure_width        문틀과 폭까지 / 먼저 실측
11.0-14.4 product_thumbnail    하루 만에 / 방문 교체
14.4-17.6 after_clean_1        집 분위기 / 확 밝아졌습니다
17.6-21.0 ai_robot_pass        문턱 없이 / 동선도 편하게
21.0-24.2 review_capture       "진작 교체할 걸"
24.2-27.0 after_main           문틀까지 봐야 할까? / 무료 실측으로 확인
```

## Rendering

The local MP4 renderer is:

```text
render_html_preview_v2.js
```

Recommended command shape:

```powershell
$env:NODE_PATH='C:\Users\hjh\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules;C:\Users\hjh\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\.pnpm\node_modules'
& "C:\Users\hjh\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" render_html_preview_v2.js `
  --html "<preview index.html>" `
  --out "<package output mp4>" `
  --fps 30 `
  --width 1080 `
  --height 1920
```

Render only after sync QA. Do not render a preview that the user has not approved or asked to render.

## Render Status After 2026-06-11 Attempt

The first full render attempt was too slow because it rendered 1080x1920 at 30fps for multiple videos in one run.

Completed MP4s:

```text
output/inbox_20260609/005_여름에어컨_20260609_111335/005_여름에어컨_ad_v2_final_render_20260611.mp4
duration: 22.98s, size: 4.35MB

output/inbox_20260609/010_구축소음_20260609_095709/010_구축소음_old_building_noise_v2_final_render_20260611.mp4
duration: 24.99s, size: 6.26MB

output/inbox_20260609/004_어려운시공_20260609_102346/004_어려운시공_difficult_installation_v2_final_render_20260611.mp4
duration: 26.98s, size: 9.28MB
```

Not completed:

```text
020 geninsert v3 MP4
```

The interrupted render left a partial frame directory:

```text
output/inbox_20260609/020_로봇청소구축리모델링_20260609_160414/020_로봇청소구축리모델링_living_flow_geninsert_v3_render_20260611_frames
partial frames: 126
```

Do not treat that folder as a completed render.

## Revised Render Plan

Do not render all four videos at final quality in one blocking run.

Use this sequence instead:

1. Render quick QA MP4s at `540x960`, `15fps`.
2. Watch/inspect those MP4s for audio/caption/screen sync.
3. Fix timeline issues in HTML/recipe.
4. Render only approved videos at `1080x1920`, `30fps`.
5. Render one video at a time.

Suggested quick QA command:

```powershell
$env:NODE_PATH='C:\Users\hjh\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules;C:\Users\hjh\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\.pnpm\node_modules'
& "C:\Users\hjh\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" render_html_preview_v2.js `
  --html "<preview index.html>" `
  --out "<package output qa mp4>" `
  --fps 15 `
  --width 540 `
  --height 960
```

For 020 specifically, quick QA should run before final render because it was the most sync-sensitive video.

## Current Code

- `video_engine_v2/final_html_variants.py`
  - Generates 004, 005, 010, 020, and `020-gen`.
  - `020-gen` is the current preferred 020 variant.
- `build_html_preview_v2.py`
  - Converts edit recipes into local HTML previews.
  - Uses only `nelnasamchae.ttf`.
- `render_html_preview_v2.js`
  - Captures HTML frames with Playwright and muxes audio with FFmpeg.

## Verification Commands

```powershell
& "C:\Users\hjh\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m py_compile build_html_preview_v2.py video_engine_v2\final_html_variants.py video_engine_v2\timeline_planner.py
& "C:\Users\hjh\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest discover -s tests
```

Last known result:

```text
Ran 31 tests ... OK
```

## Next Best Actions

1. Render 005, 010, 004, and 020-gen to MP4.
2. Watch the MP4s, not only the HTML previews.
3. Log sync issues by timestamp.
4. Convert repeated sync fixes into an explicit `audio_sync_engine`.
5. Add generated-B-roll planning as a formal phase:

```text
claim in narration
-> can real photos prove it?
-> if not, suggest generated B-roll
-> generate
-> literal visual QA
-> use only as short insert
```

## Current Caution

The system is promising, but not yet fully autonomous.

The remaining failure mode is not "bad design". It is:

```text
voice says A
caption says A-ish
screen proves B or arrives late
```

Every future automation step must defend against that failure.
