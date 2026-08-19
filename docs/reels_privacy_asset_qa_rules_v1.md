# 문장군 리뷰릴스 소재 개인정보 QA 규칙 v1

## 사진 판정 v2 계약 (2026-08-14)

`photo_selection_private.json`은 `review-reel-photo-selection-v2`를 사용하며 개인정보 위험과 편집 판단을 분리합니다.

- 개인정보 위험은 얼굴·가족사진·고객명·전화번호·계정 식별자·아파트 호수·도어락/인터폰 식별정보·차량번호·송장/우편물·주문정보의 닫힌 어휘만 허용합니다. 맨발, 신발, 생활물품, 건물명, 아파트 동 번호는 개인정보 차단 사유가 아닙니다.
- 중복, 흔들림/저화질, 리뷰와 무관함, 현재 대본에 불필요함은 별도의 `editorial_category`로 기록합니다.
- 개인정보 때문에 `exclude`할 때만 마스킹·크롭·블러·교체를 실제로 시도한 기록과 `masking_infeasible_reason`, `manual_review_reference`가 필요합니다. 편집 제외에는 이를 요구하지 않습니다.
- 각 사진은 `evidence_classes`를 가지며 완성 결과·이전 상태·리뷰 캡처는 기본 증거입니다. 실측·공정은 리뷰나 대본이 이를 주장할 때만 사용 증거가 필수입니다.
- 편집 판단 전에 가려야 할 요소가 발견되면 `decision: hold`, `privacy_status: needs_sanitization`, `remediation.action: pending`으로 남긴다. 이 상태는 HTML asset으로 사용할 수 없지만, 사진 전체를 제외한 것도 아니다.

닫힌 어휘 위반은 `PHOTO_PRIVACY_CATEGORY_INVALID`, 마스킹 우선 위반은 `MASKING_FIRST_NOT_APPLIED`로 HTML 이전에 실패합니다.

### 리뷰 캡처 증거 구도 보존

리뷰 캡처는 일반 사진이 아니라 리뷰 원문과 출처 맥락을 함께 보여 주는 증거다.
**사용자가 제공한 전체 구도**와 해상도를 그대로 유지하며, 실제로 남아 있는 주문번호·
전화번호·호수 같은 식별 영역만 최소 마스킹한다. 작성자 아이디처럼 이미 `**`로 익명화된
문자열은 개인정보 위험으로 다시 판정하거나 덧가리지 않는다.

- `evidence_classes`에 `review_capture`가 있는 사용 asset은 `review_capture_integrity`를 필수로 기록한다.
- `composition_preserved: true`, `pre_masked_identifiers_preserved: true`와 실제 `localized_mask_regions`를 결속한다.
- 리뷰 캡처의 crop·resize·확대·본문만 재구성은 금지한다. 원본과 선택본의 실제 픽셀 크기가 같아야 한다.
- 선언한 작은 마스킹 영역 밖의 픽셀이 바뀌면 실패한다. 전체 마스킹 면적도 화면의 12%를 넘을 수 없다.
- 구도 훼손은 `REVIEW_CAPTURE_COMPOSITION_CHANGED`, crop·교체 시도는 `REVIEW_CAPTURE_CROP_FORBIDDEN`, 이미 익명화된 식별자를 보존하지 않았다는 판정은 `REVIEW_CAPTURE_PREMASKED_ID_TOUCHED`로 실패한다.

```json
{"evidence_classes":["review_capture"],"privacy_status":"sanitized","privacy_risk_categories":["order_information"],"remediation":{"action":"mask"},"review_capture_integrity":{"composition_preserved":true,"pre_masked_identifiers_preserved":true,"localized_mask_regions":[{"category":"order_information","x_px":78,"y_px":36,"width_px":156,"height_px":13}]}}
```

accepted selection은 파일 자체에 `revision`, `supersedes_revision`, `revision_reason`,
`revision_changes`를 기록합니다. revision은 현재 활성 검수에서 정확히 1씩 증가해야 하며,
사유와 변경 요약도 selection SHA-256에 함께 결속됩니다. 이미 승인된 selection 파일을
수정하거나 재사용해서 이 문맥을 보충하지 않고, 새 revision으로만 기록합니다.

`needs_sanitization`의 `pending`은 사용 승인이나 영구 제외가 아니라 대본 확정 전 후보
보류입니다. 사용하려면 새 revision에서 실제 crop/blur/mask 결과를 결속해야 하고,
대본에서 쓰지 않기로 확정하면 새 revision에서 `not_required_by_narrative`로 닫습니다.

```json
{"relative_path":"images/after.jpg","decision":"use","reason":"완성 결과 훅","privacy_status":"clear","privacy_risk_categories":[],"editorial_category":"selected_story_evidence","evidence_classes":["installed_result"],"remediation":{"action":"none"},"visual_quality":{"full_product_visible":true}}
{"relative_path":"images/duplicate.jpg","decision":"exclude","reason":"같은 구도의 중복 컷","privacy_status":"clear","privacy_risk_categories":[],"editorial_category":"duplicate","evidence_classes":["installed_result"],"remediation":{"action":"none"}}
{"relative_path":"images/document.jpg","decision":"hold","reason":"대본 확정 뒤 사용 여부 결정","privacy_status":"needs_sanitization","privacy_risk_categories":["mail_document"],"editorial_category":"alternate_held","evidence_classes":["context"],"remediation":{"action":"pending","candidate_actions":["crop","blur"]}}
{"relative_path":"images/reflection.jpg","decision":"exclude","reason":"핵심 상품 전체에 얼굴이 겹침","privacy_status":"blocked","privacy_risk_categories":["reflected_identifiable_face"],"editorial_category":"privacy_unrecoverable","evidence_classes":["installed_result"],"remediation":{"action":"infeasible","attempted_actions":["crop","blur"],"infeasible_category":"risk_covers_essential_subject","masking_infeasible_reason":"상품 전체를 훼손하지 않고 식별 얼굴만 제거할 수 없음","manual_review_reference":"contact-sheet-review"}}
```

작성일: 2026-06-16

## 목적

리뷰릴스는 실제 고객 집, 외부 건물, 리뷰 캡처, 시공 사진을 사용한다.
따라서 영상 퀄리티보다 먼저 지켜야 하는 기준은 개인정보와 사생활 보호다.

004 어려운시공 재점검에서 아래 위험이 발견됐다.

```text
- 실내 시공전/시공중/시공후 컷에 가족사진 얼굴 노출
```

이후 모든 리뷰릴스는 HTML 생성 전에 소재 개인정보 QA를 통과해야 한다.

2026-06-16 운영 기준을 보정했다.

```text
- 주소/건물명은 다가구·상가·외부 현장 맥락을 설명하는 정보일 수 있으므로 기본 차단 대상이 아니다.
- 아파트 **동 번호는 차단 대상이 아니다**. 개인 세대를 특정하는 **호수**만 차단한다.
- 호수, 고객명, 전화번호, 차량번호, 도어락 번호, 택배 송장처럼 개인을 특정하는 정보는 차단한다.
- 얼굴은 가족사진/액자/거울/유리 반사/리뷰 캡처 안의 프로필 이미지까지 모두 차단한다.
  단, 불투명 유리 너머 실루엣처럼 **개인을 식별할 수 없는 형체는 차단 대상이 아니다**.
```

## 마스킹 우선 원칙

차단 대상이 있다고 해서 그 사진을 먼저 버리지 않는다. 그 컷이 이야기에 필요하면
**위험 요소만 가리고 사용하는 것이 기본**이다.

```text
- 차량번호: 번호판만 가리고 사진은 사용한다. 사진 자체를 제외하는 것이 기본이 아니다.
- 리뷰 캡처: 반드시 사용한다. 사용자 제공 구도는 유지하고, 아직 노출된 상품주문번호·식별 가능한 프로필 이미지 등 가릴 것만 가린다. 이미 `**` 처리된 작성자 아이디는 그대로 둔다.
- 호수 표식: 해당 영역만 가리거나 크롭한다.
```

리뷰 캡처는 원문 근거를 화면으로 증명하는 유일한 asset이므로 개인정보를 이유로
통째로 빼지 않는다.

## 하드 게이트

아래 항목 중 하나라도 있으면 원본 그대로 HTML/MP4에 사용할 수 없다.

```text
1. 얼굴이 식별되는 사람, 가족사진, 액자, 거울/유리 반사
2. 고객명, 시공자 실명, 전화번호, 계정명
3. 호수, 현관 비밀번호, 도어락 번호, 인터폰 세부 정보
4. 차량번호, 택배 송장, 우편물, 관리비 고지서
5. 리뷰 캡처 안의 과도한 개인정보
6. 주소와 건물명과 아파트 동 번호는 기본 허용. 단, 개인 거주자가 특정될 수 있는 호수/성명/연락처와 결합되면 차단
```

위 항목은 **해당 영역**의 하드 게이트이지 사진 전체의 제외 사유가 아니다. 마스킹
우선 원칙에 따라 위험 영역만 처리한 뒤 사용한다.

## 작업 순서

```text
1. 사진/영상 입수
2. Google Vision Face Detection 또는 동등한 얼굴 탐지 도구로 얼굴 후보 자동 검출
3. 얼굴만 블러한 검수용 proposal asset과 contact sheet 생성
4. 사진 큐레이터가 contact sheet와 원본을 비교 검수
5. 대체 컷이 있으면 대체 컷 사용
6. 대체 컷이 없으면 원본 보존 후 승인된 sanitized asset 생성
7. edit_recipe.source.image_dir는 승인된 sanitized asset 폴더를 가리키게 변경
8. privacy manifest와 별도 privacy sanitization report를 기록
9. HTML 프리뷰 생성
10. 대표 프레임에서 실제로 가려졌는지 재확인
11. 통과 후에만 MP4 렌더
```

## 처리 방식

권장 우선순위:

```text
1. 크롭/줌으로 위험 영역 프레임 밖 처리
2. 블러/모자이크/무채색 패치 처리
3. 같은 의미의 안전한 컷으로 교체
4. 위험 요소를 가릴 수 없고 대체 컷도 없을 때만 컷 제외
5. 꼭 필요한 설명 컷이면 생성 인서트로 대체
```

컷 제외는 마지막 수단이다. 이야기에 필요한 컷을 개인정보를 이유로 먼저 버리면
사건 근거가 약해진다.

주의:

```text
- 원본 사진은 삭제하거나 덮어쓰지 않는다.
- sanitized asset은 `_work/*privacy_sanitized_assets/` 같은 별도 폴더에 만든다.
- 블러는 얼굴/주소가 복구 불가능할 정도로 충분히 강해야 한다.
- 가족사진은 Google Vision의 `fdBoundingPoly` 기준 얼굴만 최소 블러한다.
- 얼굴 좌표가 누락되면 수동 좌표로 바로 영상 제작하지 말고, proposal contact sheet에서 사용자 검수 후 승인된 좌표만 쓴다.
- 유리문/거울 반사에 다시 보이는 얼굴도 별도 위험으로 본다.

## Google Vision 얼굴 블러 도구

얼굴 전용 자동 블러는 아래 스크립트를 사용한다.

```powershell
$env:GOOGLE_CLOUD_VISION_API_KEY="..."

python -m video_engine_v2.privacy_face_blur `
  --input-dir "<원본 이미지 폴더>" `
  --output-dir "<리뷰패키지>/_work/<review_id>_face_blur_review" `
  --report "<리뷰패키지>/_work/<review_id>_face_blur_report.json"
```

출력:

```text
_work/<review_id>_face_blur_review/
  원본 파일명과 같은 블러 proposal 이미지
  _face_blur_contact_sheet.jpg
_work/<review_id>_face_blur_report.json
```

중요:

```text
- 이 출력물은 곧바로 최종 asset이 아니다.
- 사용자가 contact sheet 또는 주요 이미지를 확인한 뒤 승인해야 sanitized asset으로 승격한다.
- 주소/건물명은 기본적으로 가리지 않는다.
- 얼굴이 하나라도 남으면 HTML/렌더 금지.
```
```

## edit_recipe 필수 메타데이터

위험이 없는 경우:

```json
{
  "source": {
    "privacy_review": {
      "checked": true,
      "risk_items": [],
      "unresolved_risks": []
    }
  }
}
```

익명화 자산을 사용한 경우:

```json
{
  "source": {
    "image_dir": "_work/004_privacy_sanitized_assets",
    "privacy_sanitization_report": "_work/004_privacy_sanitization_report.json"
  }
}
```

## Production privacy evidence 계약

v2 production은 `privacy_asset_manifest.json`과 별도의 실제 sanitization
report를 함께 사용한다. manifest가 자기 자신을 `sanitization_report`로
가리키면 실패한다.

```json
{
  "schema_version": "1.0",
  "checked": true,
  "checked_at": "2026-07-28T00:00:00Z",
  "unresolved_risks": [],
  "inspection_categories": ["face", "vehicle_plate", "address", "family_photo"],
  "checked_assets": [
    {"relative_path": "assets/after.jpg", "bytes": 1234, "sha256": "..."}
  ]
}
```

report의 asset path/bytes/SHA-256은 manifest의 `selected_assets` 및
edit_recipe가 실제 사용하는 asset 집합과 정확히 같아야 한다. 빈 JSON, 누락된
report, unresolved risk, hash 불일치는 HTML/MP4 gate를 통과하지 못한다.

## QA 도구 기준

HTML 전 production preflight는 아래 공식 오케스트레이터를 사용한다.

```powershell
python scripts/produce_review_v2.py preflight `
  --package "<output review package>" `
  --planning "<planning_recipe.json>" `
  --edit "<edit_recipe.json>" `
  --privacy-manifest "<privacy_asset_manifest.json>" `
  --sync-manifest "<output review package>/sync_manifest.json"
```

`PRIVACY_REVIEW_MISSING` 또는 `PRIVACY_RISK_UNRESOLVED`가 나오면 HTML/MP4 제작 금지다.

## 004 보정 기록

004 어려운시공은 아래 파일을 기준으로 privacyfix v1을 만들었다.

```text
output/inbox_20260609/004_어려운시공_20260609_102346/_work/004_privacy_sanitized_assets/
output/inbox_20260609/004_어려운시공_20260609_102346/_work/004_privacy_sanitization_report.json
output/inbox_20260609/004_어려운시공_20260609_102346/004_difficult_installation_privacyfix_v1_edit_recipe.json
```

수정 대상:

```text
- 시공전_1.jpg: 가족사진 액자
- 시공중.jpg: 가족사진 액자
- 시공후_1.jpg: 가족사진 액자
- 시공후_2.jpg: 가족사진 액자
- 시공후_3.jpg: 가족사진 액자
```

## 마스킹 픽셀 검증 (2026-08-19)

파일 이름에 `_masked`를 붙이는 것은 증거가 아니다. sanitization report는 무엇을 어디에
가렸는지 적고, 게이트가 원본과 비교해 확인한다.

```json
"sanitized_assets": [
  {
    "relative_path": "_work/<id>_privacy_sanitized_assets/19_review_capture_order_number_masked.png",
    "source_relative_path": "<id>_이미지/19_review_capture_raw.png",
    "masked_regions": [
      {"left_pct": 25, "top_pct": 10.5, "width_pct": 42, "height_pct": 7, "reason": "order_information"}
    ]
  }
]
```

- 원본 사진 폴더 밖의 asset은 정의상 위생처리 산출물이므로 반드시 선언한다.
  빠뜨리면 `SANITIZED_ASSET_NOT_DECLARED`로 막힌다.
- 마스킹본은 원본과 **크기가 같아야** 한다. 자르거나 키우면 실패한다.
- 바뀐 픽셀은 **선언한 영역 안에만** 있어야 한다. 가리면서 사진 전체를 보정하면 실패한다.
- 가린 자리는 **국소 대비가 60% 이상 사라져야** 한다. 밝기만 옮기면 글자가 그대로
  읽히므로 `SANITIZED_REGION_STILL_LEGIBLE`로 막힌다.
- 원본은 패키지 안에 남긴다. 원본이 없으면 마스킹을 검증할 수 없다.

