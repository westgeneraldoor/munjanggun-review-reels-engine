# 문장군 리뷰릴스 소재 개인정보 QA 규칙 v1

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
- 단, 동/호수, 고객명, 전화번호, 차량번호, 도어락 번호, 택배 송장처럼 개인을 특정하는 정보는 차단한다.
- 얼굴은 가족사진/액자/거울/유리 반사/리뷰 캡처 안의 프로필 이미지까지 모두 차단한다.
```

## 하드 게이트

아래 항목 중 하나라도 있으면 원본 그대로 HTML/MP4에 사용할 수 없다.

```text
1. 얼굴이 식별되는 사람, 가족사진, 액자, 거울/유리 반사
2. 고객명, 시공자 실명, 전화번호, 계정명
3. 동/호수, 현관 비밀번호, 도어락 번호, 인터폰 세부 정보
4. 차량번호, 택배 송장, 우편물, 관리비 고지서
5. 리뷰 캡처 안의 과도한 개인정보
6. 주소와 건물명은 기본 허용. 단, 개인 거주자가 특정될 수 있는 호수/성명/연락처와 결합되면 차단
```

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
1. 위험 컷 제외
2. 같은 의미의 안전한 컷으로 교체
3. 크롭/줌으로 위험 영역 프레임 밖 처리
4. 블러/모자이크/무채색 패치 처리
5. 꼭 필요한 설명 컷이면 생성 인서트로 대체
```

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
