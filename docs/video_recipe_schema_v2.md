# Munjanggun Video Recipe Schema v2

This schema defines the planning-level recipe for performance-oriented short-form videos.

It sits above the current `*_edit_recipe_v2.json`.

```text
planning recipe v2
-> render/edit recipe
-> HTML preview
-> MP4
```

## v3 신규 리뷰 릴스 one-shot 확장 (현재)

`docs/review_reels_one_shot_contract_v1.md`를 따르는 신규 recipe는 아래 필드를 추가한다. 과거 v2 recipe는 읽을 수 있지만, 신규 HTML 생성은 이 계약을 생략할 수 없다.

```json
{
  "workflow_contract": {
    "name": "review-reels-one-shot-v1",
    "html_scope_authorized": true,
    "mp4_scope_authorized": false
  },
  "photo_qa": {
    "checked": true,
    "asset_count": 8,
    "first_frame_asset_id": "photo_before_01",
    "privacy_status": "passed"
  },
  "writer_brief": {
    "one_line_story": "비식별 사건 요약",
    "hook_candidates": [{"text": "...", "triggers": ["target_callout"], "source_evidence": "review"}],
    "recommended_hook": "...",
    "review_quote_for_proof": "..."
  },
  "audio_sync": {
    "mode": "voice_aligned",
    "sync_checks": {"screen_ahead_of_voice": false}
  }
}
```

`scenes`와 edit `beats`는 `event`, `problem`, `context`, `choice_turn`, `resolution`, `felt_result`, `review_proof`, `cta` 역할을 같은 순서로 가진다. edit beat에는 `planning_scene_id`, `visual_relevance: "direct"`, `caption_start_sec`, `narration_start_sec`, `caption_layout`, `caption_focus_keywords`가 필요하다. `review_proof`는 `actual_review_capture`만 사용할 수 있다.

## Top-Level Shape

```json
{
  "schema_version": "2.0",
  "project": {},
  "source": {},
  "strategy": {},
  "analysis": {},
  "hooks": [],
  "selected_hook": {},
  "timeline": {},
  "scenes": [],
  "review_proof": {},
  "cta": {},
  "narration": {},
  "audio_sync": {},
  "render_recipe": {},
  "outputs": {},
  "quality_checks": {}
}
```

## project

```json
{
  "review_id": "005_여름에어컨",
  "variant_id": "ad_v2",
  "title": "005 여름에어컨 광고용 v2",
  "created_at": "2026-06-11",
  "status": "draft"
}
```

## source

```json
{
  "review_text_path": "reviews/inbox_20260609/005_여름에어컨.txt",
  "package_dir": "output/inbox_20260609/005_여름에어컨_20260609_111335",
  "image_dir": "005_여름에어컨",
  "existing_script": "005_여름에어컨_script.md",
  "existing_voice": "005_여름에어컨_voice.mp3",
  "existing_srt": "005_여름에어컨_subtitle.srt",
  "v1_reference_mp4": "005_여름에어컨_render_v1.mp4"
}
```

## strategy

```json
{
  "content_purpose": "ad",
  "video_type": "cooling_effect",
  "target_duration_sec": 23,
  "platform": "instagram_reels",
  "audience": "summer cooling concern homeowners",
  "primary_goal": "lead",
  "cta_strength": "medium",
  "tone": "practical, sensory, not overhyped"
}
```

Allowed `content_purpose`:

```text
ad
feed_trust
retargeting
brand_expertise
story_highlight
```

Allowed initial `video_type`:

```text
cooling_effect
old_building_noise
difficult_installation
living_installation
cost_concern
```

## analysis

```json
{
  "customer_problem": "에어컨을 켜도 거실이 더움",
  "before_pain": "현관 쪽 공기 흐름과 더위가 신경 쓰임",
  "after_change": "설치 후 에어컨을 켜니 더 시원하게 느껴짐",
  "customer_emotion": ["hesitation", "relief", "satisfaction"],
  "strongest_review_quotes": [
    {
      "raw": "어제 설치하고 에어컨을 트니 확실히 시원해졌어요",
      "edited": "에어컨 켜니 확실히 더 시원해졌어요",
      "risk": "low"
    }
  ],
  "proof_points": ["actual review", "before/after photos", "product selection"],
  "risk_flags": ["avoid energy bill promise", "avoid perfect insulation claim"]
}
```

## hooks

Generate at least three.

```json
[
  {
    "id": "hook_problem_1",
    "style": "problem_empathy",
    "text": "에어컨 풀가동해도 거실이 덥다면?",
    "score": 9.2,
    "reason": "seasonal pain and direct self-relevance"
  },
  {
    "id": "hook_curiosity_1",
    "style": "curiosity",
    "text": "중문 하나로 냉방 체감이 달라질 수 있을까?",
    "score": 8.4,
    "reason": "good curiosity but slightly slower"
  },
  {
    "id": "hook_change_1",
    "style": "change",
    "text": "더운 공기 들어오던 현관, 이렇게 바뀌었습니다",
    "score": 8.1,
    "reason": "visual but less immediate than the problem hook"
  }
]
```

## selected_hook

```json
{
  "hook_id": "hook_problem_1",
  "text": "에어컨 풀가동해도 거실이 덥다면?",
  "selection_reason": "best ad hook for summer seasonality"
}
```

## timeline

```json
{
  "target_duration_sec": 23,
  "structure": [
    {"role": "hook", "range": [0, 2]},
    {"role": "problem", "range": [2, 6]},
    {"role": "solution", "range": [6, 10]},
    {"role": "before_after", "range": [10, 16]},
    {"role": "review_proof", "range": [16, 20]},
    {"role": "cta", "range": [20, 23]}
  ],
  "energy_curve": [
    [0, "high"],
    [2, "medium_high"],
    [10, "medium"],
    [16, "high"],
    [20, "high_cta"]
  ]
}
```

## scenes

Each scene is the planning source of truth.

```json
{
  "scene_id": "s01",
  "role": "hook",
  "time": [0, 2],
  "visual_source": {
    "role": "before_main",
    "file": "시공전_1.jpg"
  },
  "visual_instruction": "heat discomfort, slight push-in, no early after reveal",
  "caption": {
    "text": "에어컨 풀가동해도\n거실이 덥다면?",
    "emphasis": ["덥다면?"],
    "position": "center",
    "theme": "cooling_hook"
  },
  "narration": "에어컨을 세게 틀어도 거실이 덥다면,",
  "energy_level": "high",
  "scene_library_ref": "field_problem_hit",
  "transition_in": "hard_cut",
  "transition_out": "air_wipe",
  "sfx": "soft_hit",
  "constraints": {
    "must_not_reveal": ["after_result", "review_quote"]
  }
}
```

Scene roles:

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

## review_proof

```json
{
  "source_capture_role": "review_capture",
  "source_capture_file": "고객리뷰.jpg",
  "quote_candidates": [
    {
      "raw": "설치 후 에어컨을 트니 확실히 더 시원해졌습니다",
      "edited": "에어컨 켜니 확실히 더 시원해졌어요",
      "selected": true,
      "risk": "low"
    }
  ],
  "display_mode": "blurred_capture_plus_large_quote",
  "time": [16, 20]
}
```

Rules:

- Original capture is used as proof.
- Quote must be readable in 1-2 seconds.
- Quote must not invent unsupported claims.

## cta

```json
{
  "time": [20, 23],
  "primary_text": "우리 집도 가능할까?",
  "secondary_text": "무료 방문 실측 상담",
  "tone": "consultative",
  "visual_source": "after_main",
  "avoid": ["fake urgency", "guaranteed outcome"]
}
```

## narration

```json
{
  "draft_text": "에어컨을 세게 틀어도 거실이 덥다면, 현관 쪽 공기 흐름부터 확인해볼 필요가 있습니다...",
  "target_duration_sec": 23,
  "voice_style": "friendly practical",
  "rules": [
    "support the visuals",
    "do not over-explain what is already visible",
    "do not reveal conclusion before scene"
  ]
}
```

## audio_sync

Before voice generation:

```json
{
  "mode": "planned",
  "planned_duration_sec": 23,
  "protected_ranges": {
    "hook": [0, 2],
    "cta": [20, 23]
  }
}
```

After voice generation:

```json
{
  "mode": "voice_aligned",
  "actual_audio_duration_sec": 22.84,
  "alignment_method": "duration_measurement_plus_scene_scaling",
  "scene_adjustments": [
    {
      "scene_id": "s03",
      "old_time": [6, 10],
      "new_time": [5.8, 9.6],
      "reason": "voice reached solution earlier"
    }
  ],
  "sync_checks": {
    "screen_ahead_of_voice": false,
    "cta_visible_min_sec": 2.0,
    "review_quote_visible_min_sec": 2.5
  }
}
```

## render_recipe

This section maps planning scenes to the current HTML renderer.

```json
{
  "renderer": "html_preview_v2",
  "output_format": "html_and_mp4",
  "resolution": [720, 1280],
  "fps": 24,
  "font": "nelnasamchae.ttf",
  "derived_edit_recipe_path": "005_여름에어컨_ad_v2_edit_recipe.json"
}
```

## outputs

```json
{
  "planning_recipe": "005_여름에어컨_ad_v2_recipe.json",
  "narration": "005_여름에어컨_ad_v2_narration.md",
  "subtitle": "005_여름에어컨_ad_v2.srt",
  "html": "005_여름에어컨_ad_v2.html",
  "mp4": "005_여름에어컨_ad_v2.mp4"
}
```

## quality_checks

```json
{
  "hook_complete_sentence": true,
  "target_duration_met": true,
  "review_quote_separated": true,
  "cta_present": true,
  "caption_readability": "pass",
  "overclaim_risk": "low",
  "screen_not_ahead_of_voice": true,
  "mobile_safe_area": "pass"
}
```

## File Naming

Do not overwrite v1 files.

Use:

```text
{review_id}_{purpose}_v2_recipe.json
{review_id}_{purpose}_v2_narration.md
{review_id}_{purpose}_v2_edit_recipe.json
{review_id}_{purpose}_v2.html
{review_id}_{purpose}_v2.mp4
```

Example:

```text
005_여름에어컨_ad_v2_recipe.json
005_여름에어컨_ad_v2_narration.md
005_여름에어컨_ad_v2_edit_recipe.json
005_여름에어컨_ad_v2.html
005_여름에어컨_ad_v2.mp4
```

## Relationship To Existing `edit_recipe_v2`

Existing `*_edit_recipe_v2.json` remains useful as the renderer-level contract.

New planning recipe:

```text
strategy + hooks + scenes + narration + CTA + sync
```

Existing edit recipe:

```text
asset_roles + beats + caption layout + motion + transitions
```

The bridge is a future `render_recipe_generator`.
