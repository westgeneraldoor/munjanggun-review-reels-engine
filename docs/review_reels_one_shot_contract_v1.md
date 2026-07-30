# 리뷰 릴스 신규 세션 one-shot 계약 v1

> 상태: 현재 권위. 이 문서는 기존 `docs/review_video_publish_workflow_v2.md`의 번호 선택 후 별도 PD/HTML 승인을 요구하던 구간을 **리뷰 릴스에 한해** 대체한다.

## 사용자 명령 해석

- 리뷰 번호는 제작 대상을 선택한다.
- `사진 다 넣었어. HTML까지 가자`, `사진 다 넣었으니 HTML까지 진행해`, 같은 의미의 명시는 사진 검수부터 HTML 프리뷰까지의 일괄 승인을 뜻한다.
- 이 일괄 승인은 MP4 권한을 절대 포함하지 않는다. MP4는 `렌더 승인`, `MP4 렌더 승인`처럼 별도의 명시 문구와 `STATUS.md`/`APPROVAL_LOG.md` 기록이 필요하다.
- 고객 원문 또는 사진 부재, 해결되지 않은 개인정보 위험, 실제 리뷰 캡처 부재처럼 사실상 진행할 수 없는 경우만 사용자에게 중단 사유를 보고한다. 훅·카피·컷 순서 같은 내부 PD 판단은 다시 묻지 않는다.

## 신규 세션 실행 경로

1. 루트 `AGENTS.md`와 이 문서를 읽고, 중앙 브랜드의 `README.md`, `BRAND_CONTEXT.md`, `FIELD_JUDGMENT_RULES.md`, `EVIDENCE_REGISTER.md`, `OPEN_QUESTIONS_REGISTER.md`를 우선 확인한다.
2. 패키지의 리뷰 원문과 사진을 읽고, 사진 역할/개인정보 QA를 대본보다 먼저 확정한다.
3. 내부 총괄 PD·리뷰 작가·사진 큐레이터·편집 설계자·QA 역할이 writer brief, 사건 중심 기획, planning/edit recipe를 만든다.
4. 최종 TTS를 만든 뒤 실제 최종 음성 길이를 측정하고 scene/SRT 시간을 정렬한다. 최종 음성이 유일한 시간축이다.
5. 아래 strict preflight를 통과한 경우에만 HTML을 만든다.

```powershell
python -m video_engine_v2.reels_qa `
  --planning "<planning_recipe.json>" `
  --edit "<edit_recipe.json>" `
  --sync-manifest-out "<sync_manifest.json>" `
  --require-one-shot-contract

python build_html_preview_v2.py `
  --planning "<planning_recipe.json>" `
  --recipe "<edit_recipe.json>"
```

6. HTML이 생성되면 대표 시점 DOM 시각 QA를 실행한다. 이 자동 결과는 수동 PD 검수를 대체하지 않는다.

```powershell
node scripts/html-preview-qa.mjs `
  --html "<package>/<html-preview>/index.html" `
  --out "<package>/_work/html_preview_qa.json"
```

## 구조 계약

새 planning recipe의 `workflow_contract.name`은 `review-reels-one-shot-v1`이어야 하며, `html_scope_authorized: true`, `mp4_scope_authorized: false`를 기록한다. `video_engine_v2.reels_qa.validate_review_reels_one_shot_contract`가 다음을 실패로 처리한다.

- 사건 → 문제 → 맥락 → 선택/전환 → 해결 → 체감 결과 → 실제 리뷰 증명 → 완성컷/CTA의 서로 다른 서사 역할 누락 또는 순서 반전
- 사진 QA, 첫 프레임 실제 고객 사진 근거, 작가 브리프, planning/edit 역할 연결 누락
- 실제 리뷰 캡처 대신 생성/가짜 리뷰 카드 사용, 리뷰 증명 뒤 CTA 부재
- 동일 사진을 3회 이상·8초 이상 반복하는 설명형 filler 또는 `visual_relevance: direct` 근거 부재
- literal `\n` 또는 `/n`, 1~2줄 위반, 최소 32px/안전영역/피사체 비가림 검수 누락, 장면당 강조어 1~2개 위반
- 자막/화면 시작이 나레이션보다 앞서는 경우, 실제 최종 TTS 길이·TTS 대본 일치 해시·raw/final TTS 근거 누락
- 원문 리뷰와 proof quote, 위험 소재, 감정, 강한 claim의 불일치

자동 검사는 레시피와 DOM 증거만 판단한다. 사진의 미묘한 가림, 말맛, 개인정보의 맥락 판단, 음성 발음/자연스러움은 `manual_review_required`로 남긴다.

## 렌더 권위

현재 기본 MP4 경로는 승인 게이트가 붙은 `render_html_preview_v2.js`다. 직접 실행은 기본 dry-run이며 다음 네 입력과 `--render-approved`가 모두 있어야 MP4를 만든다.

```powershell
node render_html_preview_v2.js `
  --html "<package>/<html-preview>/index.html" `
  --package "<package>" `
  --sync-manifest "<package>/sync_manifest.json" `
  --html-qa "<package>/_work/html_preview_qa.json" `
  --out "<package>/<review-id>_final_render_YYYYMMDD_upload_10mbps.mp4" `
  --render-approved
```

이 경로는 `STATUS.md`의 `html_approved_by_user: true`, `mp4_allowed: true`, 긍정 HTML/MP4 승인 로그, 성공 sync manifest, 성공 HTML QA, 비덮어쓰기 파일명을 모두 요구한다. 프레임 임시 파일은 고유 `_work/` 경로에 만들며, 성공 후에도 생성한 파일만 개별 삭제한다.

HyperFrames는 `docs/hyperframes_official_adoption_plan_v1.md`의 공식 Studio **pilot/검토 표면**이다. Stage 1/2 adapter를 현재 기본 production renderer라고 부르지 않는다. HyperFrames의 별도 render gate 역시 같은 MP4 승인 조건을 요구한다.
