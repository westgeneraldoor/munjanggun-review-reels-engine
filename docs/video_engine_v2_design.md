# Munjanggun Video Engine v2 Design

## 1. Core Definition

v1 proved that the review engine can turn a Naver customer review into a script, voice file, subtitles, HTML preview, and MP4 render.

v2 changes the product definition.

```text
v1: Make a video from a review.
v2: Extract performance-oriented short-form ad assets from a review.
```

The important shift is that SRT is no longer the center. The center is the video planning recipe.

```text
Review text
-> content purpose
-> video type
-> hook
-> timeline
-> asset roles
-> narration
-> voice
-> audio-based sync
-> subtitle/render recipe
-> HTML/MP4
```

## 2. Current v1 Structure

The current project is a Python-first experiment with separate video tooling:

- `generate.py`: review intake, script, caption, SRT, and voice generation.
- `output/inbox_*/`: per-review generated packages.
- `build_html_preview_v2.py`: recipe JSON to HTML preview.
- `render_html_preview_v2.js`: HTML preview to MP4 using Playwright frames and FFmpeg.
- `VIDEO_DIRECTION_V2.md`: early video direction from staff-edit analysis.
- `VIDEO_RECIPE_SCHEMA_V2.md`: first edit-recipe schema.
- `docs/hyperframe_motion_rulebook_v1.2.md`: motion, story, audio, and color rules.
- `docs/hyperframe_scene_library_v1.yaml`: large scene metadata library.

This is enough for v1 experimentation, but not enough for scalable performance creative.

## 3. v1 Limits

### Script-First Order

The current flow creates narration and SRT too early.

```text
review -> script -> voice -> SRT -> video
```

This makes the video follow the words instead of designing the first two seconds, pacing, proof, and CTA first.

### Weak Purpose Awareness

The same review can produce different outputs:

- ad test creative
- feed trust content
- retargeting proof
- brand expertise content

v1 does not choose this purpose early enough.

### Similar Visual Grammar

010, 005, and 004 became visually closer than they should be because they shared the same basic mechanism:

```text
photo + big caption + zoom/pan + flash + review ending
```

v2 needs type-specific scene grammar.

### Review Proof Is Not Separated

Current review capture is evidence, but mobile viewers cannot read the full review fast enough.

v2 must separate:

```text
review capture = evidence
review quote = readable selling copy
```

### Audio Sync Is Reactive

Existing SRT durations may not match the generated voice length. v2 needs an audio sync pass after voice generation.

## 4. v2 Data Flow

```text
1. Review Analyzer
   Extract problem, emotion, before state, after change, proof phrases, CTA angle.

2. Content Purpose Selector
   Choose ad / feed trust / retargeting / brand expertise / story.

3. Video Type Classifier
   Choose cooling effect / old building noise / difficult installation / living installation / cost concern.

4. Hook Generator
   Generate at least three hooks:
   problem empathy, curiosity, reversal/expertise.

4-1. Hook Screen Fit QA
   Convert the selected planning hook into the first-screen caption and verify it still names the subject, viewer situation, and change.

5. Timeline Planner
   Build a 20-35s scene timeline before narration.

6. Scene Allocator
   Map images to scene roles.

7. Narration Writer
   Write narration to support the planned scene rhythm.

8. Voice Generator
   Generate voice only after the timeline and narration exist.

9. Audio Sync Engine
   Measure actual voice length and adjust scene timing.

10. Subtitle Recipe Generator
    Generate readable captions from the video recipe, not raw SRT.

11. Render Recipe Generator
    Produce final JSON for HTML/MP4 rendering.
```

## 5. Module Design

### Review Analyzer

Inputs:

- review text
- optional generated script
- product metadata when present

Outputs:

- customer problem
- customer emotion
- before pain
- after change
- strongest review quote
- usable ad copy
- proof copy
- CTA angle
- risk flags for overclaiming

### Content Purpose Selector

Purpose options:

| Purpose | Length | Tempo | CTA Strength | Best Use |
|---|---:|---|---|---|
| `ad` | 20-25s | fast | medium-high | cold/warm ad testing |
| `feed_trust` | 25-35s | medium | low-medium | profile credibility |
| `retargeting` | 20-30s | medium-fast | high | users already interested |
| `brand_expertise` | 25-35s | medium | medium | difficult/technical cases |
| `story_highlight` | 15-25s | fast | low | Instagram story/archive |

### Video Type Classifier

Minimum v2 types:

- `cooling_effect`
- `old_building_noise`
- `difficult_installation`
- `living_installation`
- `cost_concern`

The classifier should consider review text and available image roles. For example, `시공중.jpg` and multiple measurement images strongly support `difficult_installation`.

### Hook Generator

Rules:

- Hook must be a complete thought, not a keyword fragment.
- Hook must fit first two seconds.
- Hook must include problem, self-relevance, or curiosity.
- Hook must survive screen-caption compression. If the shortened version removes the subject or change, it fails.
- Abstract payoff words such as `진짜입니다`, `좋아졌습니다`, `만족`, `해방` are not hooks unless paired with a concrete subject and viewer situation.

Bad:

```text
에어컨 풀가동
```

Better:

```text
에어컨 풀가동해도 거실이 덥다면?
```

Bad compression:

```text
중문은 설치 당일보다, 한 달 뒤가 더 진짜입니다
-> 한 달 뒤, 진짜입니다
```

Better screen hook:

```text
중문 설치 한 달 뒤,
집 분위기가 달라졌습니다
```

### Timeline Planner

Each scene must define:

```text
scene_id
start_time
end_time
scene_role
visual_source
visual_instruction
caption
narration
energy_level
transition
```

Allowed scene roles:

```text
hook
problem
context
solution
process
before_after
review_proof
cta
```

### Scene Library

The old Hyperframe scene library is useful, but it should be converted into Munjanggun-specific scenes:

| Existing Idea | Munjanggun Scene |
|---|---|
| `pain_text_hit` | `field_problem_hit` |
| `before_after_split` | `install_before_after` |
| `review_quote_card` | `review_quote_proof` |
| `process_steps` | `measurement_process` |
| `precision_edge_macro` | `install_detail_probe` |
| `chaos_to_order` | `difficult_site_to_clear_result` |

### Audio Sync Engine

The sync engine must run after voice creation.

Required behavior:

- measure actual audio length
- compare planned timeline with voice length
- protect first two-second hook
- protect final CTA duration
- stretch or compress middle scenes
- prevent screen/caption from revealing a conclusion before narration reaches it

### Subtitle Recipe Generator

Caption rules:

- one screen should be readable in one second
- first hook is large and complete
- problem captions are short and sharp
- review quote is separate from review capture
- CTA has its own scene
- avoid overclaiming

### Render Recipe Generator

Final render recipe includes:

```text
content purpose
video type
selected hook
target duration
scene list
asset assignments
caption plan
narration plan
review proof plan
CTA
motion/energy curve
color theme
render target
```

## 6. Hyperframe Docs Integration

### Story Engine

Use it to map video type to narrative arc:

```text
cooling_effect: hook -> problem -> solution -> before_after -> review_proof -> cta
old_building_noise: hook -> pain -> context -> solution -> proof -> cta
difficult_installation: hook -> obstacle -> process -> mission_clear -> review_proof -> cta
```

### Scene Library

The old 100-scene library should not be copied directly. It should become a source for a new Munjanggun scene library.

### Audio Sync Engine

The existing document uses metadata/BPM logic. For Munjanggun, the more important source is narration timing. BPM can help later when BGM is introduced, but voice sync comes first.

### Energy Curve

Use a per-purpose curve:

```text
ad: high -> medium-high -> high -> CTA
feed_trust: medium -> medium -> low proof -> soft CTA
brand_expertise: high obstacle -> medium process -> high clear
```

### Color Emotion

Use type-specific caption themes:

- cooling: yellow/white/cool glow
- noise/dust: yellow with controlled warning accents
- difficult installation: red warning, cyan proof, green/clear result
- cost concern: trust blue/white, avoid aggressive red

## 7. Current File Structure Recommendation

Do not jump directly into a full `src/engine` rewrite. The current project is not yet organized as a TypeScript app.

Recommended staged structure:

```text
docs/
  video_engine_v2_design.md
  video_templates_v2.md
  video_recipe_schema_v2.md
  archive/plans/refactor_roadmap_v2.md

v2/
  recipes/
  pilots/
  templates/
  scene_library/

output/
  inbox_*/
    *_ad_v2_recipe.json
    *_ad_v2_narration.md
    *_ad_v2.html
    *_ad_v2.mp4
```

Later, after the 005 pilot succeeds:

```text
src/
  review/
  engine/
  templates/
  render/
  utils/
```

## 8. First Pilot

Use `005_여름에어컨` as the v2 ad pilot.

Target:

```text
content_purpose: ad
video_type: cooling_effect
target_duration: 20-23s
hook: 에어컨 풀가동해도 거실이 덥다면?
review_proof: capture as evidence + quote as readable copy
CTA: 우리 집도 가능할까? 무료 방문 실측 상담
```

Recommended timeline:

```text
0-2s   Hook
2-6s   Problem
6-10s  Solution
10-16s Before/After
16-20s Review proof quote
20-23s CTA
```

## 9. Design Decision

v2 should preserve all v1 outputs. Do not delete or overwrite existing v1 files.

The safe path is:

```text
document -> 005 ad_v2 pilot -> review -> expand to 010/004 -> modularize
```

This keeps the current working engine alive while making the next system sharper.
