# 리뷰 릴스 현재 산출물 ledger v1

> 기준일: 2026-08-19
> 목적: 신규 canonical 패키지에서 현재 artifact 포인터를 파일명 추측 없이 고정한다.

## 권위 분리

- `CANONICAL_PACKAGE_METADATA.json`: 패키지 정체성. `current_artifacts_contract: review-reel-current-artifacts-v1`가 있으면 ledger-enabled.
- `CURRENT_ARTIFACTS.json`: 현재 artifact와 receipt의 포인터. 승인 여부를 저장하지 않는다.
- HTML/MP4 approval receipt: 사용자 승인 권위.
- voice/HTML/render manual-review receipt: 작업자 검수 권위.
- post-render QA report: 자동 기술검사 증거.
- artifact bytes와 SHA-256: 내용 증거.

ledger는 승인을 만들거나, receipt를 대체하거나, mtime·glob·가장 큰 `vN`으로 current를 고르지 않는다. 완료 상태는 ledger가 가리킨 파일을 공식 validator가 다시 통과시킨 뒤에만 참이다.

## 신규와 legacy

신규 official intake가 만드는 패키지는 빈 v1 ledger를 함께 만든다. ledger가 없거나 깨지면 filename scan으로 숨기지 않고 fail closed 한다.

ledger 계약이 없는 기존 패키지는 파일을 바꾸지 않는다. 자동 backfill·migration을 하지 않으며 1A evidence-bound resolver로만 읽는다. 120을 포함한 기존 산출물은 이 범주다.

## Writer

성공한 공식 writer만 pointer를 원자적으로 갱신한다. 한 명령의 pointer 묶음은 한 revision이다. writer 실패나 gate 차단은 revision을 바꾸지 않는다. ledger update가 실패하면 명령은 실패하고 이전 pointer를 유지한다.

연결된 writer: canonical create, photo-review, one-shot TTS, voice/HTML/render review,
preflight/sync, HTML 생성, HTML/MP4 approval, render-start job, 성공 upload MP4,
post-render QA. `recipe-scaffold`는 미완성 골격이므로 pointer를 만들지 않고,
planning/edit은 preflight 통과 시 현재 항목으로 승격한다.

같은 경로의 privacy/approval revision은 해당 kind만 교체 가능한 잠금 transaction으로
갱신하며, 교체 대상이 아닌 다른 pointer의 해시 불일치는 계속 차단한다. 운영 중 내용이
바뀌는 `render_job.json` 자체는 pointer로 사용하지 않고 queued/failed/succeeded 시점의
불변 snapshot을 current evidence로 기록한다.

## Reader

ledger-enabled 패키지의 `package_state`, `status`, `workflow-next`는 ledger pointer만 현재 항목으로 본다. ledger가 가리키지 않은 TTS, review, approval 파일은 경로와 해시가 유효해도 current가 아니다. retry 파일명의 `v3`는 포맷을 바꾸지 않는다.
