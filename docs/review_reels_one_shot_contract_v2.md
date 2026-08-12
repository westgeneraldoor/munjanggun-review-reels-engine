# 리뷰 릴스 one-shot HTML 계약 v2

## 목적과 범위

사용자가 사진 검수 완료 뒤 `사진 다 넣었어. HTML까지 가자`와 같은 명시적 요청을 하면,
리뷰 릴스의 사진 검수 결과를 바탕으로 HTML preflight와 HTML 프리뷰까지 진행할 수 있다.
이 계약은 일반 PD 기획 승인 절차를 HTML 단계에 한정해 대체한다.

이 계약은 MP4 렌더 권한을 포함하지 않는다. 일반 `generate.py` 승인 게이트는 유지하며,
사진검수를 통과한 one-shot package의 SRT/TTS만 공식
`scripts/generate_one_shot_tts.py` 경로로 생성한다. 실제 고객 자료, 이미지, 음성,
HTML, MP4 또는 approval record를 Git에 추가하지 않는다.

## 계약 필드

planning recipe는 다음 필드를 모두 가져야 한다.

```json
{
  "workflow_contract": {
    "name": "review-reels-one-shot-v2",
    "html_scope_authorized": true,
    "mp4_scope_authorized": false
  }
}
```

`mp4_scope_authorized`가 `true`이거나 누락되면 실패한다. contract가 있어도
`--one-shot-html` 없이 공식 preflight를 실행하면 기존 PD 승인 게이트가 적용된다.

## 필수 품질·개인정보 검증

- canonical metadata의 `lifecycle_state: photo_reviewed`, `photo_checked: true`,
  모든 사진의 use/hold/exclude 결정, hash-bound privacy manifest 및 sanitization report
- 원문 review quote, 공개되지 않은 위험 소재/감정/강한 claim 차단
- `writer_brief.story_mode`, 실제 고객 사진 첫 프레임, 실제 리뷰 캡처 증명,
  사건부터 CTA까지의 핵심 서사 역할
- planning/edit의 역할 연결, 직접 관련된 사진, 반복 filler 차단
- 1~2줄·32px 이상·안전영역·피사체 비가림 자막 근거
- Gemini TTS `Sulafat` 생성 보고서, 5.0~8.5자/초, 최종 TTS를 유일한
  시간축으로 하는 raw/final duration, TTS hash, 화면 선행 차단
- 실제 리뷰 캡처 1회, 한 장면 최대 6초, opening beat 최대 4초

자동 QA가 통과해도 미묘한 개인정보 맥락, 피사체 가림, TTS 발음과 자연스러움은 수동
검토 대상이다.

## 유일한 실행 경로

직접 `reels_qa`, `build_html_preview_v2.py`, `render_html_preview_v2.js`를 실행해 gate를
우회하지 않는다. 동일 package와 recipe로 다음 세 명령을 순서대로 실행한다.

```powershell
python scripts/generate_one_shot_tts.py --package "<output review package>" --planning "<planning_recipe.json>" --script "<*_script.md>"
python scripts/produce_review_v2.py preflight --package "<output review package>" --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --privacy-manifest "<privacy_asset_manifest.json>" --sync-manifest "<output review package>/sync_manifest.json" --one-shot-html
python scripts/produce_review_v2.py html --package "<output review package>" --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --privacy-manifest "<privacy_asset_manifest.json>" --sync-manifest "<output review package>/sync_manifest.json" --one-shot-html
```

첫 명령은 canonical package의 `photo_reviewed` 상태와 review source hash, one-shot
contract, planning scene 내레이션과 표준 `*_script.md` 내레이션의 일치를 검사한다.
기존 SRT/voice/report를 덮어쓰지 않으며 Gemini TTS `Sulafat`과 hash-bound 생성
보고서만 허용한다. Windows SAPI, 임의 MP3, 수동 SRT는 one-shot production 입력이
아니다. 이 명령은 HTML 또는 MP4 승인 상태를 바꾸지 않는다.

sync manifest는 one-shot scope와 recipe/privacy/voice hashes를 함께 기록한다. 어느 하나가
바뀌거나 HTML 단계에서 flag가 누락되면 stale gate로 실패한다.

## TTS 해시와 시작 시점 결속

one-shot recipe의 `audio_plan.tts_text_sha256`와 `audio_plan.final_voice_sha256`는 모두 정확히 64자의 소문자 hexadecimal SHA-256 값이어야 한다. 빈 값, 대문자, 길이가 다른 값은 실패한다.

`tts_text_sha256`의 유일한 계산 기준은 edit recipe의 `beats` 순서이다. 각 beat의
`narration_ref`를 Unicode NFC로 정규화하고, 모든 공백 묶음을 ASCII 공백 하나로
바꾼 뒤 앞뒤 공백을 제거한다. 이 정규화된 beat들을 ASCII 공백 하나로 순서대로
결합한 UTF-8 바이트열의 SHA-256이 `tts_text_sha256`이다. 표준 `*_script.md`에서
Gemini TTS에 전달한 실제 발화문도 동일한 정규화 결과여야 한다.

`final_voice_sha256`은 `source.voice`가 가리키는 package 내부 최종 voice 파일의 현재 바이트 SHA-256이다. 공식 `scripts/produce_review_v2.py preflight --one-shot-html`는 두 선언값의 형식과 현재 값 일치를 모두 검사하며, stale text hash 또는 stale voice hash이면 sync manifest를 만들지 않고 실패한다.

각 one-shot beat의 visual 시작은 `time[0]`, narration 시작은 `narration_start_sec`이다. visual은 narration보다 0.05초를 초과해 먼저 시작할 수 없으며, 이 허용오차를 넘는 visual pre-roll은 hard fail이다. caption은 기존과 같이 narration보다 먼저 시작하면 즉시 hard fail이다.

HTML 생성 직후 공식 오케스트레이터는 `scripts/html-preview-qa.mjs`를 실행해 모든
beat의 대표 프레임을 `_qa_frames/`에 저장하고 `html_internal_qa_report.json`을
만든다. 자동 검사가 성공해도 수동 상태는 `pending`이다. 작업자가 대표 프레임을
직접 확인하지 못하면 HTML을 완료로 보고할 수 없다.

## MP4의 별도 권한

HTML 생성 뒤에는 기존 `HTML_APPROVAL.json`과 별도 명시적 MP4 승인이 모두 필요하다.
`scripts/produce_review_v2.py render-start`는 one-shot flag를 받지 않으며, 기존 render
gate와 single-use receipt, non-overwrite 규칙을 그대로 적용한다. 시작 명령이 반환한
job ID는 `scripts/produce_review_v2.py render-status`로 조회하며 `succeeded`와 MP4
bytes/SHA-256이 기록되기 전에는 렌더 완료가 아니다.
