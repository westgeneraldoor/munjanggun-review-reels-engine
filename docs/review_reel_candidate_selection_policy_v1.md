# 리뷰 릴스 후보 선정 정책 v1

## 목적과 정본

이 문서는 리뷰 릴스용 material-bank 후보를 신규 package로 배정하기 전에 적용하는
공식 선정 정책이다. `candidate_top60_private.jsonl`은 후보 내용과 순위의 정본이고,
현재 `output/` package와 canonical registry는 실제 사용 이력의 정본이다.
후보 선정 이후의 HTML/MP4 production 진입점은 계속 `scripts/produce_review_v2.py`이며,
이 정책과 intake CLI는 내부 builder·renderer 직접 실행 권한을 만들지 않는다.

`reviews/inbox_*`에 원문이 있다는 사실만으로 사용 완료로 보지 않는다. 반대로 수동
장부에 없더라도 실제 package가 동일 리뷰 증거를 가지면 이미 사용한 리뷰다. 별도
가변 사용 이력 장부를 만들지 않고 `candidate-shortlist`와 `candidate-check`가 현재
파일에서 매번 판정을 계산한다.

## 상품 하드 제외

아래 상품은 리뷰 릴스 신규 후보로 배정하지 않는다.

- `ABS도어` product family 또는 상품명
- `셀프실측`
- `셀프설치`, `셀프설치시공`, `셀프시공`
- `배송상품`, `택배배송`, `배송전용`

하나라도 해당하면 `CANDIDATE_PRODUCT_EXCLUDED`이며 `eligible_for_new_package`는
`false`다. 점수, 티어, 사진 수가 높아도 예외가 생기지 않는다.

## 사용 이력과 관련 리뷰 판정

판정 우선순위는 다음과 같다.

1. 상품 하드 제외: `policy_excluded`
2. 다른 package의 동일 리뷰글번호 또는 동일 review-text SHA-256:
   `legacy_identity_present`, `REVIEW_ALREADY_USED`
3. 다른 리뷰글번호이지만 이미 사용한 package와 상품주문번호가 같음:
   `related_review_hold`, `PRODUCT_ORDER_ALREADY_USED`
4. official source binding 존재: 새 번호를 만들지 않고 기존 binding 재사용
5. 과거 `CAND-*` evidence 존재: `CANDIDATE_LEGACY_PACKAGE_PRESENT`
6. 위 조건이 모두 없음: `eligible`

동일 주문의 일반 리뷰와 한달사용 리뷰는 서로 다른 글이어도 같은 현장·사진을 다시
쓸 위험이 있다. 자동 eligible로 바꾸지 않으며, 별도 사건으로 제작할 근거와 owner의
명시 승인이 있는 경우에만 별도 resolution을 설계한다.

사용 이력 스캔 범위는 현재 숫자 package, `output/inbox_*`의 legacy package,
`output/pilot`이다. JSON/Markdown/TXT/source marker와 canonical metadata에서 exact
candidate, 리뷰글번호, 상품주문번호, review hash만 읽는다. 단어 유사도나 제목 추측은
사용 증거가 아니다. `output/.review_reel_production/quarantine`은 보존 증거이며 신규
선정 스캔 대상이 아니다.

## 공식 읽기 전용 선정

먼저 전체 material bank를 현재 정책으로 감사한다.

```powershell
python scripts/review_reel_intake.py candidate-shortlist `
  --output-root "output" `
  --reviews-root "reviews" `
  --material-bank "reviews/material_bank/2026-07-29/candidate_top60_private.jsonl" `
  --limit 10
```

`eligible_candidates`는 material bank의 canonical rank 순서를 보존한다. 선택할 후보는
다시 단건 확인하고, `eligible_for_new_package: true`일 때만 생성한다.

```powershell
python scripts/review_reel_intake.py candidate-check `
  --output-root "output" `
  --reviews-root "reviews" `
  --material-bank "reviews/material_bank/2026-07-29/candidate_top60_private.jsonl" `
  --candidate-id "CAND-YYYYMMDD-NNNN"
```

`create-from-material-bank`도 같은 정책과 identity scan을 lock 안에서 다시 실행한다.
따라서 읽기 전용 확인과 생성 사이에 새 package가 생겨도 중복을 배정하지 않는다.

## 잘못 선택한 pre-photo package의 복구 가능 격리

잘못 선택한 active package는 아래 조건을 모두 만족할 때만 공식 격리할 수 있다.

- canonical lifecycle이 `photo_intake_pending`
- 모든 approval이 false
- 이미지 폴더에 고객 사진이 없음
- script, SRT, voice, recipe, HTML, MP4 등 downstream artifact가 없음
- source registry, material-bank inventory, package registry, active pointer가 정확히 결속됨

```powershell
python scripts/review_reel_intake.py quarantine-active-selection `
  --output-root "output" `
  --reviews-root "reviews" `
  --expected-content-id "<status의 content_id>" `
  --reason-code duplicate_existing_review
```

허용 reason은 `duplicate_existing_review`, `policy_excluded`, `wrong_selection`이다.
명령은 삭제하지 않는다. package와 production source를
`output/.review_reel_production/quarantine/<timestamp>/`로 이동하고, 변경 전 registry
4개와 SHA-256 manifest를 보존한 뒤 active pointer를 해제한다. 사진이나 downstream
artifact가 하나라도 있으면 별도 media-preserving 복구 결정을 받아야 한다.
