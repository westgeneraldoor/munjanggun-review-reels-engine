# 리뷰 릴스 one-shot HTML 계약 v2

## 사람 검수 영수증 (2026-08-14)

Gemini/Sulafat 음성 생성 뒤에는 발음·톤·자막 싱크를 실제로 듣고 `voice-review-record`를 실행해야 합니다. 현재 voice/SRT/TTS report와 해시가 맞는 영수증이 없으면 one-shot preflight가 실패합니다. HTML 자동 QA 뒤에는 모든 beat와 0.5초·첫 3개 훅 프레임을 직접 보고 `html-review-record`를 실행합니다. 이 HTML 영수증과 사용자 HTML 승인, 별도 MP4 승인은 서로 대체하지 않습니다.

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
- `writer_brief.story_spine`의 문제→행동→변화→증명→CTA 원문·사진·자막 결속,
  첫 갈등을 회수하는 CTA, 현재 script SHA-256에 결속된 `script_review` 승인
- planning/edit의 역할 연결, 직접 관련된 사진, 반복 filler 차단
- 1~2줄·32px 이상·안전영역·피사체 비가림 자막 근거
- Gemini TTS `Sulafat` 생성 보고서, 5.0~8.5자/초, 최종 TTS를 유일한
  시간축으로 하는 raw/final duration, TTS hash, 화면 선행 차단
- 실제 리뷰 캡처 1회, 한 장면 최대 6초, opening beat 최대 4초

자동 QA가 통과해도 미묘한 개인정보 맥락, 피사체 가림, TTS 발음과 자연스러움은 수동
검토 대상이다.

## 유일한 실행 경로

직접 `reels_qa`, `build_html_preview_v2.py`, `render_html_preview_v2.js`를 실행해 gate를
우회하지 않는다. 동일 package와 recipe로 다음 네 명령을 순서대로 실행한다.

```powershell
python scripts/generate_one_shot_tts.py --package "<output review package>" --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --script "<*_script.md>"
python scripts/produce_review_v2.py layout-check --package "<output review package>" --edit "<edit_recipe.json>"
python scripts/produce_review_v2.py preflight --package "<output review package>" --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --privacy-manifest "<privacy_asset_manifest.json>" --sync-manifest "<output review package>/sync_manifest.json" --one-shot-html
python scripts/produce_review_v2.py html --package "<output review package>" --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --privacy-manifest "<privacy_asset_manifest.json>" --sync-manifest "<output review package>/sync_manifest.json" --one-shot-html
```

첫 명령은 API를 호출하기 전에 canonical package의 `photo_reviewed` 상태와 review source
hash, one-shot contract, shot·hook·review proof·CTA·자막 chunk 등 authoring contract
전체, planning scene 내레이션과 표준 `*_script.md` 내레이션의 일치를 검사한다. 음성이
아직 없을 때는 silent placeholder로 실제 production 템플릿의 DOM layout probe까지
실행해 3줄·안전영역·overflow 실패를 TTS 전에 차단한다.
이 단계에서 `script_review.script_sha256`도 실제 script bytes와 대조한다. 훅 첫 3컷을
각 1.0초 이상 배치할 최소 3.0초가 없거나 실측 alignment 뒤 배치 가능 구간이 없으면
`HOOK_ALIGNMENT_INFEASIBLE`로 중단하며 음수 shot을 만들지 않는다.
기존 SRT/voice/report를 덮어쓰지 않으며 Gemini TTS `Sulafat`과 hash-bound 생성
보고서만 허용한다. Windows SAPI, 임의 MP3, 수동 SRT는 one-shot production 입력이
아니다. 같은 canonical narration hash로 API 생성에 성공한 시도가 이미 두 개면
세 번째 호출은 `TTS_ATTEMPT_BUDGET_EXCEEDED`로 중단한다. 이 명령은 HTML 또는 MP4
승인 상태를 바꾸지 않는다. API가 유효한 voice/report를 반환한 순간
`_work/tts_attempts/`에 영구 영수증을 남기므로 이후 retime 계약 실패로 voice/report가
정리되어도 시도 예산은 복구되지 않는다.

신규 authoring은 첫 훅 3.5초 이하, 리뷰 증거 5.4초 이하, 마지막 완성 결과 3.0초
이상을 목표로 한다. 이는 TTS 편차를 흡수하는 기획 안전 여유이며 production 하드 한계
4.0초/6.0초/2.5초를 바꾸지 않는다. Gemini 속도 보정 뒤 0.25초를 넘는 시작 무음은
발화를 자르지 않고 0.15초로 정규화한다. 정규화된 voice의 새 bytes/hash/최종 길이를
TTS report에 기록하며 무음만을 이유로 API를 다시 호출하지 않는다.

최종 음성 길이 또는 실측 alignment로 retime한 edit은 파일 저장, current-artifact ledger
기록, immutable lock 전에 duration-sensitive authoring 계약을 다시 검사한다. 실패하면
원래 edit bytes를 복구하고 SRT/voice/report 파생 산출물을 정리하며 ledger와 lock은
만들지 않는다.

두 번째 명령은 실제 production HTML 템플릿을 임시 폴더에만 렌더해 모든 caption
chunk의 실제 줄수, 1080x1920 안전영역, overflow를 브라우저 DOM으로 측정한다. 공식
HTML, QA frame, gate receipt, approval evidence는 만들지 않으며 임시 probe는 명령 종료와
함께 폐기한다. 이 검사가 실패하면 caption/edit을 새 revision에서 고친 뒤 다시 검사한다.

한 production 세션의 자율 공식 HTML 빌드는 1회다. 공식 HTML 또는 대표 프레임 검수가
실패하면 재빌드 루프를 돌지 않고 중단해 앞단 원인을 수정한다. 사용자가 원인과 새
revision을 확인하고 재시도를 명시 승인한 경우에만 두 번째 공식 HTML을 허용한다.
package 전체를 영구 봉쇄해 사람 검수에서 찾은 품질 수정까지 막는 규칙으로 해석하지 않는다.

## 결속 후 revision과 음성 재사용

공식 TTS가 성공하면 사용한 edit recipe는 `_work/recipe_locks/`의 hash-bound 영수증과
읽기 전용 속성으로 잠긴다. 결속 뒤 제자리 수정은 `BOUND_RECIPE_MODIFIED`이며 기존
보고서나 994행의 변조 탐지 결속을 약화해서 해결하지 않는다.

- narration hash가 바뀜: 새 recipe revision에서 새 TTS를 생성한다.
- narration과 전체 caption timeline이 동일하고 시각/메타데이터만 바뀜:
  `recipe-fork-reuse-voice`로 다음 revision을 만들고 `voice-reuse-check` 통과 뒤 기존
  voice/SRT/report 증거를 직접 재사용한다.
- narration은 같지만 caption chunk 또는 timing이 바뀜: 실제 발화 경계를 기록한
  `review-reel-voice-alignment-v1`과 공식 calibration 경로를 사용한다. 측정값이 없으면
  추정 alignment를 만들지 말고 중단한다.

```powershell
python scripts/review_reel_intake.py recipe-fork-reuse-voice --output-root "output" --expected-content-id "<content-id>" --planning "<bound planning>" --edit "<bound edit>"
python scripts/review_reel_intake.py voice-reuse-check --output-root "output" --expected-content-id "<content-id>" --edit "<new edit>"
```

실제 청취에서 첫 음절 손실 또는 비례 배분 타임라인 오차가 확인되면 기존 산출물을
수정하지 않고 새 artifact stem으로 교정한다. 교정도 같은 공식 스크립트만 사용하며,
원본 Gemini/Sulafat voice와 report, 해시 결속된 `review-reel-voice-alignment-v1`
실측 파일을 함께 지정한다. 세 교정 입력은 일부만 사용할 수 없다.

```powershell
python scripts/generate_one_shot_tts.py --package "<package>" --planning "<planning>" --edit "<new edit>" --script "<new *_script.md>" --calibrate-from-voice "<approved source voice.mp3>" --calibrate-from-report "<source tts report.json>" --alignment "<measured alignment.json>" --lead-in-sec 0.4
```

교정 결과는 source voice hash, 실측 파일 hash, lead-in, 새 voice/SRT/edit hash를 새
TTS report에 기록한다. 각 자막은 **실측 발화 시작**에 맞춰 나타나고 다음 자막도 다음
실측 발화 시작에서 교체한다. 무음 중간점으로 다음 자막을 미리 띄우지 않는다. 강조
시점도 해당 자막 안의 강조 단어 위치에서 다시 계산한다. 교정 뒤에도
`voice-review-record`, preflight, HTML, `html-review-record`를 처음부터 다시 거친다.

sync manifest는 one-shot scope와 recipe/privacy/voice hashes를 함께 기록한다. 어느 하나가
바뀌거나 HTML 단계에서 flag가 누락되면 stale gate로 실패한다.

sync manifest의 `severity: fail` issue와 사진 다양성·장면 밀도 같은 미해결 품질 경고는
HTML을 계속 차단한다. 단, 현재 voice/SRT/report 해시에 결속된 `voice-review-record`가
이미 존재하는 one-shot에서 `SCENE_CPS_NEEDS_REVIEW`만 남은 경우에는 청취 검토가 끝난
soft warning으로 취급한다. 이 예외는 전체 CPS hard limit이나 다른 warning을 완화하지 않는다.

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

HTML 생성 뒤에는 `html-approval-record`가 만든 `HTML_APPROVAL.json`과,
`render-approval-record`가 만든 `MP4_RENDER_APPROVAL.json`이 모두 필요하다. 두 번째
영수증은 현재 HTML과 첫 번째 영수증의 SHA-256에 결속되며 상태 Markdown 수동 수정은
승인 증거가 아니다.
`scripts/produce_review_v2.py render-start`는 one-shot flag를 받지 않으며, 기존 render
gate와 single-use receipt, non-overwrite 규칙을 그대로 적용한다. 시작 명령이 반환한
job ID는 `scripts/produce_review_v2.py render-status`로 조회하며 `succeeded`와 MP4
bytes/SHA-256이 기록되기 전에는 렌더 완료가 아니다.
