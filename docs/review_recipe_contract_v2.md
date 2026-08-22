# 리뷰 릴스 recipe 계약 v2

## 화면 증거 계약 (2026-08-14)

edit recipe의 `asset_evidence`는 각 `asset_roles` 항목의 주 역할을 `evidence_class`로 선언합니다. 사용 화면에는 완성 결과(`installed_result`), 이전 상태(`before_state`), 리뷰 캡처(`review_capture`)가 모두 있어야 합니다. 훅의 완성 사진은 `installed_result`와 `full_product_visible: true`를 함께 만족해야 합니다.

실측(`measurement`)과 공정(`installation_process`)은 리뷰 원문이나 대본이 해당 사실을 주장할 때만 사용 증거가 필수입니다. 소스에 고가치 증거가 있지만 쓰지 않으면 `unused_reason`을 기록합니다. 이 계약을 어기면 `HOOK_RESULT_NOT_FULLY_VISIBLE`, `CLAIM_EVIDENCE_MISSING`, `UNUSED_HIGH_VALUE_EVIDENCE_REASON_MISSING`으로 실패합니다.

사진 shot이 8개 이상인 긴 편집은 사용 가능한 비리뷰 근거 자산 중 최소
`min(6, 사용 가능 자산 수, ceil(사진 shot 수 / 2))`개를 쓰는지 검사합니다. 부족하면
`PHOTO_VARIETY_LOW` 경고를 내지만, 이야기와 무관한 사진 사용을 강제하지는 않습니다.
narrative-safe 비리뷰 사진이 8장 이상이면 비리뷰 사진 shot 9개 이상을 권장하며,
부족하면 `SCENE_DENSITY_LOW` 경고를 냅니다. 사진 근거가 부족한 편집을 하드 실패시키거나
무관한 사진을 채우지는 않습니다.

```json
{"asset_evidence":{"after_main":{"evidence_class":"installed_result","visual_quality":{"full_product_visible":true}},"before_entry":{"evidence_class":"before_state"},"review_capture":{"evidence_class":"review_capture"},"measure_width":{"evidence_class":"measurement","unused_reason":"리뷰와 대본에 실측 주장이 없어 보조 소스로만 보존"}}}
```

production v2는 기획 의도를 담는 planning recipe와 실제 렌더 입력을 담는 edit recipe를
분리합니다. 이 문서는 두 JSON의 책임 경계만 정의하며, 정확한 검증 조건은
`video_engine_v2/production_gate.py`, `video_engine_v2/reels_qa.py`와 테스트가
최종 권위입니다.

## 1. 공통 원칙

- recipe는 canonical package 내부의 상대경로를 사용합니다.
- planning과 edit는 같은 리뷰·script·asset·voice를 가리켜야 합니다.
- 파일을 바꾸면 기존 sync/HTML 승인 증거는 stale이며 preflight부터 다시 실행합니다.
- production은 1080x1920, 30fps, H.264/yuv420p, AAC 44.1kHz stereo와 승인된 bitrate를 사용합니다.
- 720x1280, 24fps 예시와 standalone `caption.txt`/`narration.md`는 legacy 계약입니다.

## 2. planning recipe

planning recipe는 무엇을 왜 말하는지 기록합니다. 최소 책임은 다음과 같습니다.

- package/content identity와 channel/format
- `workflow_contract`
- 원문 결속 `review_source`
- writer brief 또는 이에 대응하는 `analysis`
- 훅 후보와 `selected_hook`
- `story_mode`, timeline/scenes, review proof, CTA
- 최종 narration과 화면 의미 계획
- privacy·claim·quality 확인 결과

HTML preflight에서 항상 확인하는 planning 필드는 아래와 같습니다. `hooks`는
`analysis` 내부가 아니라 top-level 배열입니다.

```json
{
  "analysis": {
    "customer_problem": "",
    "before_pain": "",
    "after_change": "",
    "customer_emotion": []
  },
  "hooks": [],
  "selected_hook": {"text": ""}
}
```

`analysis.customer_problem`, `analysis.before_pain`, `analysis.after_change`,
`analysis.customer_emotion`, top-level `hooks`가 비어 있으면 실패합니다. 과거 recipe의
top-level analysis 필드는 호환 입력으로 읽을 수 있지만 새 recipe는 중첩 `analysis`를
사용합니다. `selected_hook.text`는 `caption` 또는 `headline` 호환 필드로 읽을 수 있어도
새 recipe에서는 `text`를 사용합니다.

one-shot HTML이면 다음 범위가 명시되어야 합니다.

```json
{
  "workflow_contract": {
    "name": "review-reels-one-shot-v2",
    "html_scope_authorized": true,
    "mp4_scope_authorized": false
  }
}
```

원문 계약은 다음 네 필드를 포함합니다.

```json
{
  "review_source": {
    "text": "",
    "review_quote_for_proof": "",
    "inferred_fields": [],
    "unsupported_story_elements": []
  }
}
```

canonical one-shot에서는 metadata와 planning의 review identity/text hash가 일치해야
합니다. `unsupported_story_elements`가 있거나 proof quote가 원문에 없으면 실패합니다.

## 3. edit recipe

edit recipe는 무엇을 실제로 렌더할지 기록합니다. 최소 책임은 다음과 같습니다.

- `version`, package/content identity
- `source`: script, SRT, voice, privacy/sanitization evidence
- `style_dna`
- `asset_roles`: 실제 사용 이미지의 역할과 경로
- `beats`: 시간·narration·caption·visual source·meaning match
- `audio_plan`: narration, TTS provenance와 sync policy
- `render_targets`

`source`에는 최소한 실제 package-relative 입력과 privacy 결속을 기록합니다.

```json
{
  "source": {
    "script": "<script.md>",
    "srt": "<captions.srt>",
    "voice": "<voice.mp3>",
    "image_dir": "<approved sanitized asset directory>",
    "privacy_review": {
      "checked": true,
      "unresolved_risks": []
    },
    "privacy_sanitization_report": "<_work/report.json>"
  }
}
```

`image_dir`는 package 내부의 실제 디렉터리여야 하고 `asset_roles`의 모든 파일이 그
안에 있어야 합니다. 일반 QA는 `privacy_review.checked: true` 또는 비어 있지 않은
`privacy_sanitization_report` 중 하나를 privacy 검수 증거로 인정합니다. 그러나 공식
production preflight는 `privacy_sanitization_report`를 요구하며 privacy manifest의
`sanitization_report`와 같은 package 내부 파일에 결속합니다. unresolved risk가 남으면
어느 경우에도 실패합니다.

각 beat는 최소한 시작/끝, 내레이션, 자막, 시각 asset 역할을 서로 연결해야 합니다.
planning scene과 다른 의미를 말하거나 package 밖 asset을 암묵적으로 참조하면 안 됩니다.
`caption_layout.theme`은 `white`, `warning`, `proof`, `clear`, `cta`, `stamp` 중 하나만
사용합니다. 기본 production 팔레트인 `white`는 아이보리 본문과 민트 핵심어입니다.

one-shot의 모든 beat는 `shots`로 실제 사진 순서와 시간을 기록합니다. 같은 문장 안에서도
의미가 갈리고 해당 구절에 맞는 사진 근거가 있으면 별도 shot으로 나눕니다. 첫 세 shot은
`result_asset_id → before_asset_id → result_asset_id`, 전환은
`cut → calm_dissolve → calm_dissolve`, 체류는 각각 1.0초 이상이어야 합니다. 이후 shot도
hard cut을 사용하지 않고 마지막 shot은 `result_asset_id`를 최소 2.5초 유지합니다.
전체 12컷이 상한이며 최소 컷 수는 없습니다.

허용 모션은 `static_hold`, `calm_push_in`, `calm_pull_out`, `calm_glide_left`,
`calm_glide_right`, `calm_glide_up`, `review_capture_hold`, 허용 전환은 `cut`,
`calm_dissolve`, `calm_slide`, `soft_page_turn`입니다. `calm_slide`는 전체 최대 2회,
`soft_page_turn`은 최대 1회이고 리뷰 증거와 CTA는 `calm_dissolve`만 사용합니다.
비정지 motion에는 `motion_reason`이 필요하고 리뷰 증거는 한 장의
`review_capture_hold`여야 합니다. renderer 확정값은 `calm_dissolve 380ms`, 확대·축소
scale 차이 0.05, 좌우 총 24px, 상하 총 20px입니다.
한 beat에 shot이 여러 개면 모두 같은 motion을 써 카메라 방향을 유지합니다. calm 모션은
일정 속도이고 `calm_dissolve`는 이전 사진의 마지막 위치를 보존한 채 투명도만 바꿉니다.

각 beat의 `caption_emphasis`는 정확히 한 단어/구절이고 `caption_accent.enabled: true`,
`caption_layout.theme: white`를 사용합니다. 키워드 크기는 본문과 동일합니다. 첫 훅은
`hero-calm 58px`, 이후 본문·proof·CTA는 모두 `medium 46px`입니다.
`caption_accent.start_sec`는 강조 단어가 포함된 chunk 안의 절대 영상 시각이며 단어 위치로
산정한 발화 예상 시점에 결속합니다. chunk 시작 고정 delay는 production 증거가 아닙니다.
pop 길이는 160ms이며 브라우저 실제 시간이 아니라 영상 시간에 결속됩니다.
모든 one-shot beat는 내레이션 음성 전문을 연속으로 덮는 `caption_chunks` 1~4개를
가집니다. 최대 4개이며, 여러 chunk를 쓸 때 각 문구는 공백·문장부호 제외 최소 7자이고
합친 문구는 narration과 같아야 합니다. 시간은 beat를 빈틈·겹침 없이 덮고 최종 음성의
실제 문장 경계에 맞춥니다. 문장 종결부호 뒤에 다음 문장 조각을 같은 chunk로 붙이지
않습니다. 자막 DOM은 1080x1920 기준 `y=220~1470` 안에 있어야 하며
명시·자동 줄바꿈을 합친 실제 화면 줄 수가 3줄 이상이면 실패합니다.
TTS 발음을 위한 `text`와 공식 제품 표기가 다를 때만 `display_text`를 사용합니다. 숫자와
띄어쓰기를 정규화한 결과가 같아야 하며, 예를 들어 음성 `초슬림 삼 연동 중문`은 화면에
`초슬림 3연동중문`으로 표시할 수 있습니다.

```json
{
  "hook_visual_contract": {
    "result_asset_id": "after_result",
    "before_asset_id": "before_entry"
  },
  "beats": [{
    "shots": [{
      "asset_id": "after_result",
      "motion": "calm_push_in",
      "motion_reason": "완성 결과를 먼저 차분하게 보여줌",
      "transition_in": "cut",
      "start_sec": 0.0,
      "end_sec": 1.3
    }],
    "caption_layout": {"size": "hero-calm", "theme": "white"},
    "caption_chunks": [{
      "text": "완성 결과를 먼저 보여드립니다.",
      "display_text": "완성 결과를 먼저 보여드립니다.",
      "start_sec": 0.0,
      "end_sec": 1.3
    }],
    "caption_emphasis": ["완성 결과"],
    "caption_accent": {"enabled": true, "start_sec": 0.05}
  }]
}
```

설치 결과 훅의 첫 3개 shot은 `caption_chunks`와 1:1 대응할 필요가 없습니다. 한 완결된
문장이 여러 사진을 가로지를 수 있지만 모든 shot의
`meaning_match_source`에는 `asset_evidence:<asset_id>`와
`narration_fragment:<해당 문맥>`을 함께 기록합니다. 이 결속이 없으면 사진 순서는
맞아도 음성 의미가 다른 화면 위로 넘어갈 수 있으므로 preflight에서 실패합니다.

`review_proof` beat의 밑줄은 원본 이미지를 바꾸지 않는 overlay입니다. `quote`는
planning의 `review_source.text`에 실제 포함되어야 하고 시간은 해당 beat 안에, 최대
3개의 `segments` 좌표는 캡처 내부에 있어야 합니다.

```json
{
  "review_emphasis": {
    "quote": "원문에 실제 있는 인용",
    "start_sec": 18.3,
    "end_sec": 20.3,
    "draw_duration_sec": 0.15,
    "segments": [{"left_pct": 12, "top_pct": 54, "width_pct": 70}]
  }
}
```

one-shot edit의 audio plan에는 공식 TTS 입력과 최종 voice hash, 실제 측정 길이가
결속되어야 합니다. 임의 MP3나 Windows SAPI는 production provenance가 아닙니다.

생성 asset은 조건부 필드입니다. beat에서 `generated_asset: true`이면 아래 네 증거를
모두 추가해야 하며 빈 문자열이나 `not_real_proof: false`는 실패합니다.

```json
{
  "generated_asset": true,
  "generated_reason": "실제 사진만으로 보이지 않는 생활 불편을 설명",
  "not_real_proof": true,
  "visual_claim": "화면이 문자 그대로 주장하는 내용",
  "literal_qa_result": "그 주장이 화면에 실제 보이는지 검수한 결과"
}
```

생성 asset은 실제 시공·제품 마감·실측·리뷰 캡처의 증거 역할을 가질 수 없습니다.

## 4. sync manifest와 증거

`scripts/produce_review_v2.py preflight`가 planning/edit/privacy를 검증하고
`sync_manifest.json`을 만듭니다. sync manifest는 다음을 증명합니다.

- planning/edit/privacy 파일 경로·bytes·SHA-256
- voice 상대경로·bytes·SHA-256
- `raw_tts_duration_sec`, `final_voice_duration_sec`, total voice CPS
- beat별 시간과 `meaning_match: true`
- 적용된 one-shot 범위

HTML 생성 후 `html_artifact_evidence.json`은 index.html과 실제 image/voice/font 입력,
gate receipt의 hash를 기록합니다. `HTML_APPROVAL.json`은 그 HTML과 artifact evidence에
결속되어야 하며 legacy boolean만으로 render를 승인하지 않습니다.
`MP4_RENDER_APPROVAL.json`은 별도 사용자 렌더 승인을 현재 HTML과 HTML approval
SHA-256에 결속합니다.

render 후 `render_post_qa_report.json`은 대상 MP4와 사용한 sync manifest의 상대경로,
bytes, SHA-256을 기록합니다. hash 없는 legacy QA pass는 `unknown`으로 남깁니다.

## 5. 공식 실행 경계

```powershell
python scripts/produce_review_v2.py preflight --package "<package>" --planning "<planning.json>" --edit "<edit.json>" --privacy-manifest "<privacy.json>" --sync-manifest "<package>/sync_manifest.json"
python scripts/produce_review_v2.py html --package "<package>" --planning "<planning.json>" --edit "<edit.json>" --privacy-manifest "<privacy.json>" --sync-manifest "<package>/sync_manifest.json"
python scripts/produce_review_v2.py html-approval-record --package "<package>" --html "<preview>/index.html" --approved-by "<user>" --evidence-reference "<explicit HTML approval>"
python scripts/produce_review_v2.py render-approval-record --package "<package>" --html "<preview>/index.html" --approved-by "<user>" --evidence-reference "<explicit MP4 approval>"
python scripts/produce_review_v2.py render-start --package "<package>" --html "<preview>/index.html" --privacy-manifest "<privacy.json>" --sync-manifest "<package>/sync_manifest.json" --out "<package>/<id>_final_render_YYYYMMDD_upload_10mbps.mp4"
python scripts/produce_review_v2.py render-status --package "<package>" --job-id "<job-id>"
python scripts/produce_review_v2.py post-render-qa --package "<package>" --job-id "<job-id>"
```

내부 `reels_qa`, HTML builder, renderer 직접 호출은 production 증거가 아닙니다.
기존 recipe, MP4, frame은 덮어쓰지 않습니다.
렌더 작업은 `_work/render_jobs/<job-id>/render_job.json`에 결속되며 `succeeded`와
MP4 bytes/SHA-256이 함께 있어야 후속 post-render QA로 넘어갑니다.

## 6. review_emphasis segment

```json
{
  "review_emphasis": {
    "quote": "외부 소음이 확실히 줄어들어 방음 효과를 체감하고 있습니다",
    "segments": [
      {"left_pct": 8, "top_pct": 61, "width_pct": 84, "line_text": "외부 소음이 확실히 줄어들어 방음 효과를"},
      {"left_pct": 8, "top_pct": 65, "width_pct": 40, "line_text": "체감하고 있습니다"}
    ]
  }
}
```

`line_text`를 모두 이은 결과가 `quote`와 다르면 `REVIEW_EMPHASIS_SEGMENT_TEXT_MISMATCH`로
실패합니다. 상세 기준은 `docs/review_reels_visual_edit_standard_v1.md`를 따릅니다.
