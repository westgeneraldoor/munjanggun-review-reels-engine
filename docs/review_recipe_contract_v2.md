# 리뷰 릴스 recipe 계약 v2

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

render 후 `render_post_qa_report.json`은 대상 MP4와 사용한 sync manifest의 상대경로,
bytes, SHA-256을 기록합니다. hash 없는 legacy QA pass는 `unknown`으로 남깁니다.

## 5. 공식 실행 경계

```powershell
python scripts/produce_review_v2.py preflight --package "<package>" --planning "<planning.json>" --edit "<edit.json>" --privacy-manifest "<privacy.json>" --sync-manifest "<package>/sync_manifest.json"
python scripts/produce_review_v2.py html --package "<package>" --planning "<planning.json>" --edit "<edit.json>" --privacy-manifest "<privacy.json>" --sync-manifest "<package>/sync_manifest.json"
python scripts/produce_review_v2.py render --package "<package>" --html "<preview>/index.html" --privacy-manifest "<privacy.json>" --sync-manifest "<package>/sync_manifest.json" --out "<package>/<id>_final_render_YYYYMMDD_upload_10mbps.mp4"
```

내부 `reels_qa`, HTML builder, renderer 직접 호출은 production 증거가 아닙니다.
기존 recipe, MP4, frame은 덮어쓰지 않습니다.
