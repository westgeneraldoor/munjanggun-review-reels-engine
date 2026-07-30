# 리뷰 릴스 one-shot HTML 계약 v2

## 목적과 범위

사용자가 사진 검수 완료 뒤 `사진 다 넣었어. HTML까지 가자`와 같은 명시적 요청을 하면,
리뷰 릴스의 사진 검수 결과를 바탕으로 HTML preflight와 HTML 프리뷰까지 진행할 수 있다.
이 계약은 일반 PD 기획 승인 절차를 HTML 단계에 한정해 대체한다.

이 계약은 MP4 렌더 권한을 포함하지 않으며, `generate.py`의 script/SRT/TTS 승인 게이트를
완화하지 않는다. 실제 고객 자료, 이미지, 음성, HTML, MP4 또는 approval record를 Git에
추가하지 않는다.

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

- package의 `photo_checked: true`, hash-bound privacy manifest 및 sanitization report
- 원문 review quote, 공개되지 않은 위험 소재/감정/강한 claim 차단
- 실제 고객 사진 첫 프레임, 실제 리뷰 캡처 증명, 이벤트부터 CTA까지의 8개 서사 역할
- planning/edit의 역할 연결, 직접 관련된 사진, 반복 filler 차단
- 1~2줄·32px 이상·안전영역·피사체 비가림 자막 근거
- 최종 TTS를 유일한 시간축으로 하는 raw/final duration, TTS hash, 화면 선행 차단

자동 QA가 통과해도 미묘한 개인정보 맥락, 피사체 가림, TTS 발음과 자연스러움은 수동
검토 대상이다.

## 유일한 실행 경로

직접 `reels_qa`, `build_html_preview_v2.py`, `render_html_preview_v2.js`를 실행해 gate를
우회하지 않는다. 동일 package와 recipe로 다음 두 명령을 순서대로 실행한다.

```powershell
python scripts/produce_review_v2.py preflight --package "<output review package>" --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --privacy-manifest "<privacy_asset_manifest.json>" --sync-manifest "<output review package>/sync_manifest.json" --one-shot-html
python scripts/produce_review_v2.py html --package "<output review package>" --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --privacy-manifest "<privacy_asset_manifest.json>" --sync-manifest "<output review package>/sync_manifest.json" --one-shot-html
```

sync manifest는 one-shot scope와 recipe/privacy/voice hashes를 함께 기록한다. 어느 하나가
바뀌거나 HTML 단계에서 flag가 누락되면 stale gate로 실패한다.

## MP4의 별도 권한

HTML 생성 뒤에는 기존 `HTML_APPROVAL.json`과 별도 명시적 MP4 승인이 모두 필요하다.
`scripts/produce_review_v2.py render`는 one-shot flag를 받지 않으며, 기존 render gate와
single-use receipt, non-overwrite 규칙을 그대로 적용한다.
