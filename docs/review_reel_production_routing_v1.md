# 리뷰 릴스 제작 앞단 라우팅과 canonical package intake v1

## 목적

짧은 사용자 명령이 후보은행·일반 리뷰 콘텐츠 흐름으로 새지 않고, 항상
`review_reel_production`으로 들어가도록 고정한다. 이 문서는 production v2의
앞단 계약만 정의한다. 기존 HTML 템플릿·렌더러·MP4 gate를 대체하지 않는다.

## 현재 authority 순서

신규 세션은 아래 순서로만 판단한다.

1. `AGENTS.md`의 하드 gate와 고객자료 로컬 전용 규칙
2. `docs/munjanggun_content_operating_principles_v1.md`의 콘텐츠 원칙
3. 이 문서의 `review_reel_production` routing/intake 계약
4. `docs/review_video_publish_workflow_v2.md`와 `docs/review_reels_one_shot_contract_v2.md`의 제작·one-shot gate
5. `scripts/produce_review_v2.py`의 실제 production gate

`docs/reels_operations_dashboard_v1.md`는 관측·참고용 dashboard이며 **not a routing authority**이다.
`docs/archive/`와 과거 handoff/intake 메모는 **not current routing authority**이다.
후보은행, AppSheet 요청, `CAND-*` 기록도 source evidence일 뿐 제작 시작 권한이 아니다.

## 세 가지 사용자 명령과 상태 전이

| 사용자 명령 | workflow | 상태 | 다음 행동 | 생성 금지 |
|---|---|---|---|---|
| `리뷰 릴스 만들자` | `review_reel_production` | `selection_required` | private material bank/registry에서 실제 record를 확인하고 선택을 받는다 | package, script, TTS, HTML, MP4 |
| `리뷰 하나 골라 폴더 만들어줘` | `review_reel_production` | `canonical_package_create_requested` | 선택된 material-bank record를 local registry에 등록하고 canonical package를 만든다 | script, SRT, TTS, HTML, MP4 |
| `사진 다 넣었어. HTML까지 가자` | `review_reel_production` | `one_shot_html_requested` | active pointer를 검증한 뒤 official one-shot HTML만 시도한다 | MP4, direct builder/renderer |

문장 안에 일반 `리뷰 콘텐츠` 표현이 같이 있어도 릴스 명령이 먼저다. generic
review-content/material-bank 라우터는 위 세 상태를 가로챌 수 없다.
띄어쓰기와 자연스러운 어미 차이도 같은 명령으로 본다. 예를 들어
`리뷰릴스 만들자`, `리뷰 릴스 제작하자`, `리뷰 하나 골라서 폴더 만들어줘`,
`리뷰 골라주고 폴더 만들어줘`, `사진 다 넣었어요 HTML까지 가자`는 각각 위 상태로
동일하게 라우팅되어야 한다.

## 실제 material bank 연결과 번호 배정

기본 production 앞단은 이미 존재하는 local-only
`reviews/material_bank/.../candidate_top60_private.jsonl`을 직접 읽는다. 이 파일의
실제 필드인 `candidate_id`, `inventory_id`, `order_id`, `review_id`, `review_text`를
공식 adapter가 canonical 필드로 바꾼다.

```powershell
python scripts/review_reel_intake.py create-from-material-bank `
  --output-root "output" `
  --reviews-root "reviews" `
  --material-bank "reviews/material_bank/2026-07-29/candidate_top60_private.jsonl" `
  --candidate-id "CAND-YYYYMMDD-NNNN" `
  --content-slug "사건중심짧은이름"
```

- 세 자리 `content_id`는 AI가 쓰거나 추정하지 않는다.
- `output/.review_reel_production/source_registry_private.json`이 기존 `reviews/`와
  `output/`의 번호를 스캔한 뒤 다음 미사용 번호를 배정한다.
- 같은 candidate를 다시 실행하면 최초 번호·slug·source를 그대로 재사용한다.
- registry JSON이 깨졌거나 같은 candidate의 원문/주문/리뷰 ID가 바뀌면 덮어쓰지
  않고 하드 실패한다.
- 원문은 `reviews/production_registry/<ID>_<slug>.txt`에 local-only로 고정되고,
  adapter가 만든 private canonical inventory와 함께 Git에서 계속 제외된다.

## canonical inventory와 이름 규칙

`create-from-material-bank`가 만든 private canonical inventory 또는 이미 검증된 별도
inventory를 `scripts/review_reel_intake.py create`로 사용할 수 있다. 선택 record는
다음 필드를 모두 보관해야 한다.

```json
{
  "schema_version": "review-reel-inventory-v1",
  "records": [{
    "record_key": "exact-private-record-key",
    "content_id": "004",
    "content_slug": "어려운시공",
    "review_source_path": "reviews/inbox_YYYYMMDD/004_어려운시공.txt",
    "review_text": "원문 리뷰 전체",
    "product_order_number": "private-order-id",
    "review_article_id": "private-review-id",
    "source_reference": "private-source-record",
    "candidate_reference": "CAND-YYYYMMDD-NNNN"
  }]
}
```

- `content_id`는 local registry가 배정했거나 별도 inventory에 이미 있는 정확한 세 자리
  ID만 쓴다. AI가 계산·추정하거나 `CAND-*`로 바꾸지 않는다.
- CLI는 `review_source_path`의 실제 UTF-8 원문과 `review_text`가 같은지 확인한다.
  `reviews/...` 상대경로는 inventory 파일 위치가 아니라 repository root를 기준으로
  해석한다.
  따라서 리뷰 원문, 상품주문번호, 리뷰글번호, source reference, candidate reference가
  `CANONICAL_PACKAGE_METADATA.json`에 함께 결속된다.
- `CAND-*`는 `candidate_reference` 안에서만 보존한다. package 이름, 이미지 폴더 이름,
  user-facing 보고에 쓸 수 없다.
- 모든 inventory/metadata/pointer는 고객자료를 포함할 수 있으므로 GitHub에 commit하지
  않는다. `reviews/`와 `output/`은 계속 local-only다.

성공한 intake의 이름은 기존 004·005 계열과 호환된다.

```text
output/inbox_YYYYMMDD/004_어려운시공_YYYYMMDD_HHMMSS/
  004_어려운시공_이미지/
  CANONICAL_PACKAGE_METADATA.json
  .source
  STATUS.md
  APPROVAL_LOG.md
```

intake 직후 `STATUS.md`는 photo/PD/HTML/MP4를 모두 false로 시작한다. 사진 전에는
script, SRT, TTS, HTML, MP4가 생기지 않아야 한다.

## 공식 CLI

라우팅 확인은 파일을 만들지 않는다.

```powershell
python scripts/review_reel_intake.py route --user-command "리뷰 릴스 만들자"
```

기존 별도 inventory를 쓰는 경우에만 아래 저수준 명령을 사용한다.
PowerShell `mkdir`이나 임의 output 경로 생성은 사용하지 않는다.

```powershell
python scripts/review_reel_intake.py create --output-root "output" --inventory "<private inventory json>" --record-key "<selected record_key>"
```

같은 record의 리뷰 원문 hash·상품주문번호·리뷰글번호·content ID가 같으면 기존 package를
되돌려 중복 package를 만들지 않는다. 새 package가 만들어지거나 재선택되면
`output/.review_reel_production/active_package.json`과 registry가 갱신된다.
`one-shot-html`은 이 pointer만 신뢰하고, 임의로 최신 output 폴더나 과거 `CAND-*`
폴더를 훑어 선택하지 않는다. pointer와 metadata hash·package path·이미지 폴더가
일치하지 않으면 중단한다.

## 사진 후 one-shot HTML 연결

사진 검수와 privacy/원문/실제 리뷰 캡처/TTS·sync/one-shot 구조 QA의 준비가 된 뒤에만
다음을 사용한다. 이 명령은 active package를 내부적으로 해석하고
`scripts/produce_review_v2.py`의 `preflight`와 `html` 두 단계에 모두
`--one-shot-html`을 붙인다.

```powershell
python scripts/review_reel_intake.py one-shot-html --output-root "output" --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --privacy-manifest "<privacy_asset_manifest.json>"
```

planning contract는 반드시 `review-reels-one-shot-v2`, `html_scope_authorized: true`,
`mp4_scope_authorized: false`여야 한다. 이 CLI는 render/`--out` 옵션이 없으며,
MP4는 HTML approval과 별도 사용자 렌더 승인이 기록된 뒤에만 기존
`scripts/produce_review_v2.py render` gate로 진행한다.
