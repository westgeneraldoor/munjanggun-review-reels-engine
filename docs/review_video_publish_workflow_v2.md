# 문장군 리뷰 영상 신규 발행 워크플로 v2

> 앞단 routing은 먼저 `docs/review_reel_production_routing_v1.md`를 따른다.
> 이 문서는 canonical package가 선택·생성된 뒤의 제작 gate를 설명한다. dashboard,
> archive, generic review-content 문서는 package 선택이나 이름의 authority가 아니다.

신규 세션에서 바로 이어가기 위한 운영 기준입니다.

## 시작 명령

신규 세션에서는 이렇게 말하면 됩니다.

```text
리뷰 컨텐츠 신규 발행하자
```

또는 영상까지 염두에 두면 더 정확합니다.

```text
리뷰 영상 신규 발행하자
```

가장 짧은 실전 명령은 아래입니다.

```text
리뷰 릴스 만들자
```

Codex는 먼저 후보 리뷰를 고르거나, 사용자가 지정한 리뷰 번호를 받아 작업을 시작합니다.
이미 리뷰 번호/폴더가 지정되어 있으면 후보 제안보다 해당 폴더 상태 확인을 우선합니다.
단, 리뷰 번호를 지정한 것은 **제작 대상 승인**일 뿐이며 **HTML 제작 승인**이 아닙니다.
번호만 받은 신규 세션은 사진검수와 PD 기획안 제시에서 멈추고, 사용자의 명시적 승인 후에만 스크립트/SRT/TTS/HTML을 생성합니다.

## 핵심 순서

사진을 먼저 넣으려면 리뷰 패키지 폴더가 먼저 있어야 합니다. 따라서 순서는 아래가 맞습니다.

```text
1. 리뷰 선택
2. 리뷰 패키지 폴더 생성
3. 사용자가 사진을 해당 폴더에 넣음
4. Codex가 사진 파일명/내용을 확인하고 개인정보 위험을 검수
5. 영상 목적과 타입 결정
6. 리뷰 각색 작가가 writer brief 작성: 사건/감정/증거/훅/말맛 추출
7. 사진 역할 매핑 + 부족 컷/생성 B-roll 필요 여부 + 익명화 필요 여부 판단
8. PD 기획안 작성: 목적, 훅 후보, 타임라인, asset/caption/narration 의미 일치 계획
9. 사용자에게 기획 승인 요청
10. 승인 후 planning/edit recipe 작성
11. 승인 후 영상용 나레이션/SRT/음성 생성
12. 승인 후 HTML 프리뷰 생성
13. 사용자 HTML 검수
14. 승인된 HTML만 MP4 렌더
15. 폴더 정리 및 다음 세션 기록
16. 다음 후보군 보충 및 사진 투입 폴더 준비
```

## 패키지 상태 잠금 파일

v3 운영부터 각 리뷰 패키지 루트에는 아래 두 파일을 둡니다.

```text
STATUS.md
APPROVAL_LOG.md
```

`STATUS.md`는 현재 단계와 최신 산출물을 알려주는 단일 상태판입니다.
`APPROVAL_LOG.md`는 사용자가 무엇을 승인했고, 무엇을 승인하지 않았는지 남기는 기록입니다.

신규 세션은 리뷰 번호를 받으면 산출물을 만들기 전에 반드시 이 두 파일을 먼저 확인합니다.
두 파일이 없으면 먼저 생성하고, 기본값은 안전하게 아래처럼 둡니다.

```text
html_approved_by_user: false
mp4_allowed: false
```

즉, 리뷰 번호 지정은 여전히 대상 승인일 뿐이며 HTML/MP4 승인으로 해석하지 않습니다.

상태 파일은 package의 명시 기록으로 점검합니다. production preflight/HTML/render는
반드시 `scripts/produce_review_v2.py`를 사용하며, `video_engine_v2.reels_qa`는
내부 diagnostic 모듈일 뿐 직접 production 진입점이 아닙니다.

v2 HTML 승인은 `index.html` 단독 승인이 아닙니다. HTML artifact evidence에 기록된
image/voice/repository font의 상대경로·bytes·SHA-256과 함께 승인되며, voice가 바뀌면
sync manifest와 HTML 승인 evidence가 stale입니다. legacy QA `auto_status: pass`는
과거 evidence이고, 현재 MP4 bytes/SHA-256까지 report와 일치한 경우만 package state의
`render_complete: true`입니다. hash 없는 legacy report, published, performance는 별도
증거가 없으면 `unknown`이며 기존 upload package의 삭제·migration·자동 재렌더 근거가 아닙니다.

## 자동 진행 한계

사용자가 아래처럼 리뷰 번호만 지정한 경우:

```text
033 리뷰 릴스 만들자
025 리뷰 릴스 만들어줘
98번 해보자
```

이 명령은 **대상 리뷰를 정한 것**이지, 최종 제작을 전부 승인한 것이 아닙니다.
신규 세션은 아래 단계까지만 자동 진행합니다.

```text
1. 필수 문서 읽기
2. 리뷰 원문 확인
3. 이미지 폴더/사진 수량/파일명 확인
4. 사진 역할 매핑
5. 부족 컷과 개인정보/주소/얼굴/차량번호 위험 요소 보고
6. 리뷰 각색 작가 브리프 작성
7. 훅 후보 3개 이상 제안
8. scene별 asset/caption/narration 의미 일치 계획표 작성
9. D-024/D-025/D-026 통과 가능성 사전 점검
10. 사용자에게 "이 기획으로 HTML 제작할까요?"라고 묻고 멈춤
```

아래와 같은 명시적 승인이 있어야 다음 단계로 넘어갑니다.

```text
승인
이 방향으로 가
HTML 만들어
프리뷰 제작해
진행해
```

금지:

```text
번호만 듣고 script/SRT/TTS/HTML 생성
사진 역할 매핑 없이 HTML 생성
analysis가 비어 있는 planning_recipe 생성
사용자 기획 승인 없이 MP4 렌더
STATUS.md / APPROVAL_LOG.md 확인 없이 산출물 생성
```

## 사용자와 Codex 역할

사용자:

- 리뷰 번호 또는 후보 선택
- 리뷰 현장 사진 업로드
- PD 기획안 승인 또는 방향 수정
- HTML 프리뷰 감성 검수
- MP4 최종 싱크 검수

Codex:

- 리뷰 패키지 폴더 생성
- 사진 폴더 경로 안내
- 리뷰 각색 작가 브리프 작성
- 사진 파일명/장면 역할 매핑
- 후킹/전개/CTA 기획
- 기획 승인 요청 후 HTML 프리뷰 제작
- HTML 승인 요청 후 MP4 렌더
- 폴더 정리 및 문서 기록

## 제작팀 역할

문장군 릴스 제작은 총괄 PD 혼자 즉흥적으로 만들지 않고, 아래 역할을 내부 팀으로 고정합니다.

| 역할 | 책임 | 필수 산출물 |
|---|---|---|
| 총괄 PD | 최종 방향, 전략, 승인 게이트, 사용자 보고 | PD 판단, 최종 보고 |
| 리뷰 분석가 | 원문 사실, 고객 불편, 제품/현장 키워드 추출 | 리뷰 요약, 소재 태그 |
| 리뷰 각색 작가 | 사건/감정/증거/훅/말맛 추출 | `*_writer_brief.md` 또는 `writer_brief` |
| 사진 큐레이터 | 사진 검수, 역할 매핑, 부족 컷 판단, 개인정보 위험 체크 | asset map, 부족컷 보고, privacy report |
| 편집 설계자 | beat 구성, 화면/자막/음성 의미 일치 설계 | planning/edit recipe |
| QA 감시자 | 싱크, 과장표현, 줄바꿈, 렌더 차이 검수 | QA report, sync manifest |

작가는 선택 사항이 아닙니다. 신규 릴스는
`docs/review_reels_content_standard_v1.md` 기준으로 writer brief를 먼저 만들고,
총괄 PD가 승인 가능한 훅과 방향인지 판단합니다.

## 사진 폴더 규칙

리뷰 패키지가 생성되면, 사용자는 아래처럼 리뷰 폴더 안의 이미지 폴더에 사진을 넣습니다.

```text
output/inbox_YYYYMMDD/리뷰번호_주제_YYYYMMDD_HHMMSS/리뷰번호_주제_이미지/
```

이미지 폴더 이름은 케이스에 따라 `이미지`, `script`, 또는 리뷰명 폴더가 될 수 있지만, v2부터는 가능하면 아래 규칙으로 통일합니다.

```text
리뷰번호_주제_이미지
```

권장 파일명:

```text
시공전_1.jpg
시공전_2.jpg
시공후_1.jpg
시공후_2.jpg
실측_1.jpg
상품 썸네일.jpg
고객리뷰.jpg
현장외관.jpg
계단.jpg
복도.jpg
```

사진이 부족하면 Codex가 부족한 장면을 말합니다. 필요한 경우 생성 B-roll을 제안할 수 있지만, 생성 이미지는 실제 시공 증거가 아니라 설명용 인서트로만 사용합니다.

## 사진 개인정보 검수 규칙

사진 역할 매핑 전에 `docs/reels_privacy_asset_qa_rules_v1.md` 기준으로 소재 개인정보 QA를 먼저 수행합니다.

아래 요소가 보이면 원본 그대로 HTML/MP4에 사용할 수 없습니다.

```text
얼굴 / 가족사진 / 반사된 얼굴 / 고객명 / 호수 / 전화번호 / 차량번호 / 택배 송장 / 도어락 번호
```

주소와 건물명과 **아파트 동 번호는 기본 허용**입니다. 개인 세대를 특정하는 **호수**만 차단합니다.
다가구주택·상가·외부 현장 컷은 공간 맥락을 보여주는 정보이므로 무조건 가리지 않습니다.
다만 주소가 고객명, 호수, 전화번호, 차량번호 등과 결합되어 개인 거주자가 특정되면 차단합니다.
불투명 유리 너머 실루엣처럼 개인을 식별할 수 없는 형체는 차단 대상이 아닙니다.

위 항목이 보인다고 사진을 먼저 빼지 않습니다. `docs/reels_privacy_asset_qa_rules_v1.md`의
마스킹 우선 원칙에 따라 위험 영역만 가리고 사용하며, 리뷰 캡처는 가릴 것만 가린 뒤
반드시 사용합니다.

얼굴은 수동 감으로 좌표를 찍지 않고, 먼저 Google Vision Face Detection 또는 동등 도구로 자동 검출합니다.

```powershell
python -m video_engine_v2.privacy_face_blur `
  --input-dir "<원본 이미지 폴더>" `
  --output-dir "<리뷰패키지>/_work/<review_id>_face_blur_review" `
  --report "<리뷰패키지>/_work/<review_id>_face_blur_report.json"
```

이 단계의 결과물은 최종 asset이 아니라 **검수용 proposal**입니다.
사용자가 contact sheet를 확인하고 승인한 뒤에만 sanitized asset으로 승격합니다.

처리 순서:

```text
1. 위험 컷 제외
2. 안전한 대체 컷 사용
3. 크롭/줌으로 프레임 밖 처리
4. 얼굴 자동 블러 proposal/contact sheet 생성
5. 사용자 또는 사진 큐레이터 승인
6. 승인된 sanitized asset 생성 후 edit_recipe.source.image_dir 교체
7. `docs/review_recipe_contract_v2.md`에 따라 privacy metadata와 report 결속 기록
```

일반 QA에서는 아래 중 하나가 없으면 통과할 수 없습니다. 공식 production preflight는
두 번째 report와 privacy manifest의 동일 파일 결속을 추가로 요구합니다.

```text
source.privacy_review.checked: true
source.privacy_sanitization_report: "<report.json>"
```

## 부족/부적합 사진 처리 규칙

사진이 많아도 아래 경우에는 그대로 쓰지 않습니다.

```text
1. 음성/자막의 핵심 문장을 설명하지 못함
2. 피사체가 너무 흐리거나 어두움
3. 제품/공간이 무엇인지 알아보기 어려움
4. 자막을 얹으면 핵심 피사체가 가려짐
5. 장면의 감정이나 상황과 사진 분위기가 맞지 않음
```

이때 순서는 아래입니다.

```text
1. 실제 사진 중 대체 가능한 컷을 먼저 찾음
2. 컷 순서/크롭/줌/전환으로 해결 가능한지 확인
3. 그래도 핵심 의미가 안 보이면 사용자에게 부족 장면을 보고
4. 생성 B-roll 또는 이미지젠 인서트 필요 여부 제안
5. 사용자 승인 후 생성
6. 생성 이미지가 문장을 문자 그대로 만족하는지 검수
7. 통과한 생성 이미지만 짧은 인서트로 사용
```

생성 이미지를 쓸 수 있는 경우:

```text
생활 불편 설명
상황 재현
동선/문턱/소음/냄새 같은 보이지 않는 문제의 이해 보조
비포/애프터 사이 감정 전환 보조
```

생성 이미지를 쓰면 안 되는 경우:

```text
실제 시공 완료 증거
제품 마감/색상/유리/레일/댐퍼 디테일 증명
실측 증거
리뷰 캡처 대체
고객 집 실제 모습처럼 속이는 컷
```

생성 인서트 사용 시 planning/edit recipe에는 반드시 아래를 남깁니다.
정확한 필드 위치와 조건은 `docs/review_recipe_contract_v2.md`를 따릅니다.

```text
generated_asset: true
generated_reason:
not_real_proof: true
visual_claim:
literal_qa_result:
```

예:

```text
visual_claim: 문턱 없이 로봇청소기가 통과한다
literal_qa_result: 화면에 문턱/턱/레일/단차 없음. 통과.
```

## 제작 원칙

- 첫 2초는 반드시 완성형 후킹 문장이어야 합니다.
- 번호 지정은 HTML 제작 승인이 아닙니다. 리뷰 번호만 받은 경우 사진검수와 PD 기획안에서 멈춥니다.
- 첫 화면 훅은 `대상/상황 + 변화/궁금증`을 포함해야 합니다. `진짜입니다`, `달라졌습니다`, `좋았습니다`처럼 맥락 없는 추상 결론만 남으면 실패입니다.
- 기획안의 훅 문장을 HTML용 짧은 자막으로 줄일 때 핵심 명사와 변화 대상을 삭제하면 안 됩니다. 예: `중문은 설치 당일보다, 한 달 뒤가 더 진짜입니다`를 `한 달 뒤, 진짜입니다`로 줄이면 실패입니다.
- 훅 후보는 최소 3개를 만들고, 선택 전 아래 네 가지를 점수화합니다: 구체성, 자기관련성, 화면 첫 컷과의 일치, 이전 제작물과의 차별성.
- 영상 목적을 먼저 정합니다: 광고형, 전환형, 신뢰형, 생활불편 해결형.
- 나레이션, 자막, 화면은 같은 시간에 같은 말을 해야 합니다.
- 각 scene은 caption, narration, asset이 같은 의미를 말해야 합니다. 자막은 `브론즈 유리`인데 내레이션은 `댐퍼`를 말하거나, 화면은 `시공전`인데 내레이션은 `시공후 분위기`를 말하면 실패입니다.
- planning recipe의 필수 analysis와 top-level hooks는 `docs/review_recipe_contract_v2.md`를 따릅니다. 하나라도 비어 있으면 HTML을 만들지 않습니다.
- 작가 브리프 없이 HTML을 만들지 않습니다. `writer_brief.one_line_story`, `hook_candidates`, `recommended_hook`, `review_quote_for_proof`가 비어 있으면 실패입니다.
- D-024의 계산식과 현재 속도 경계는 `docs/review_reels_content_standard_v1.md`를 따릅니다. one-shot은 5.0~8.5자/초 밖이면 실패하고, 일반 v2는 전체 또는 scene CPS가 9.0자/초 이상이면 하드 실패입니다.
- 자막은 사진의 핵심 피사체를 가리면 안 됩니다.
- 자막은 의미 단위 1~2줄을 원칙으로 합니다. 긴 리뷰 문장을 단어 단위로 쪼개거나, 강조 span 때문에 `성능 / 과 / 마감`처럼 조사만 한 줄로 떨어지면 실패입니다.
- 좌상단 라벨, 의미 없는 칩, 작은 설명 박스는 기본 금지입니다.
- 리뷰 캡처는 증거로 쓰고, 핵심 문장 하나를 크게 뽑습니다.
- 최종 MP4는 HTML 승인 후에만 렌더합니다.
- 여러 영상을 한 번에 렌더하지 않습니다. 한 개씩 렌더합니다.
- 최종 렌더는 `docs/render_qa_rules_v2.md`의 업로드용 스펙을 따릅니다.
- 캡션/해시태그는 `*_script.md` 내부 `## 캡션`, `## 해시태그` 섹션까지 최종 점검합니다.
- 릴스 1건 완료 후에는 다음 후보군을 보충하고, 사진 투입 폴더를 준비합니다.

## 최종 MP4 업로드 스펙

직원 편집본 기준에 맞춘 최종 업로드용 기본값입니다.

```text
해상도: 1080x1920
프레임: 30fps
영상 코덱: H.264
영상 목표 비트레이트: 11000k
실제 전체 비트레이트: 약 9~10Mbps
오디오: AAC / 44.1kHz / stereo / 192k
파일명: *_final_render_YYYYMMDD_upload_10mbps.mp4
```

렌더는 내부 renderer를 직접 호출하지 않고 공식 오케스트레이터를 사용합니다.

```powershell
python scripts/produce_review_v2.py render-start --package "<output review package>" --html "<html_preview>/index.html" --privacy-manifest "<privacy_asset_manifest.json>" --sync-manifest "<output review package>/sync_manifest.json" --out "<output review package>/<review-id>_final_render_YYYYMMDD_upload_10mbps.mp4"
python scripts/produce_review_v2.py render-status --package "<output review package>" --job-id "<job-id>"
```

`render-start`는 호출 세션과 분리된 작업 ID를 즉시 반환합니다. `render-status`가
`succeeded`와 현재 MP4 bytes/SHA-256을 함께 기록하기 전에는 렌더 완료로 보지 않습니다.
실패한 작업은 부분 frame과 receipt/log를 보존하며 새 출력 파일명으로 다시 시작합니다.

## TTS 속도 검수 하드 게이트

신규 세션은 음원 길이만 보고 통과 처리하면 안 됩니다. 아래 계산을 반드시 보고합니다.

```text
공백 제외 내레이션 글자수
실제 voice.mp3 길이
초당 글자수 = 공백 제외 글자수 / 실제 음성 길이
```

판정 기준:

```text
권장: 6.5~7.5자/초
허용: 5.0~8.5자/초
실패: 9.0자/초 이상
```

예시:

```text
280자 / 27.99초 = 10.0자/초 → 실패
```

실패 시 선택지는 둘 중 하나입니다.

```text
1. 내레이션을 줄여 같은 길이 안에서 다시 생성
2. 후기형 콘텐츠라면 영상 길이를 늘리고 사용자 승인을 다시 받음
```

HTML 프리뷰를 만들기 전에 이 검수를 통과해야 합니다.

## HTML 생성 전 preflight QA

HTML 프리뷰 생성 전에는 공식 orchestrator preflight를 실행합니다.

```powershell
python scripts/produce_review_v2.py preflight `
  --package "<output review package>" `
  --planning "<planning_recipe.json>" `
  --edit "<edit_recipe.json>" `
  --privacy-manifest "<privacy_asset_manifest.json>" `
  --sync-manifest "<output review package>/sync_manifest.json"
```

internal `video_engine_v2.reels_qa` diagnostic 결과를 포함한 gate가 하나라도
실패하면 HTML을 만들지 않습니다. 생성된 manifest의 `ok`가 `false`이면 공식 CLI도
실패 exit code를 반환해야 합니다.

이 preflight는 최소 아래를 막습니다.

```text
analysis 필수 필드 비어 있음
훅 후보 비어 있음
첫 화면 훅이 추상 결론어만 남음
장면별 CPS 9.0 이상
최종 voice 길이 기준 전체 CPS 9.0 이상
narration_ref 누락
review_capture 2회 이상 사용
caption/narration 안의 ?? 또는 � 문자
생성 이미지 메타데이터 누락
```

`OK`가 나온 뒤에만 HTML 생성으로 넘어갑니다.

## HTML 브라우저 검수 규칙

Codex 인앱 브라우저는 `file://` HTML을 자동 조작하지 못할 수 있습니다. 이 경우 `file://` 우회 시도를 하지 말고, 프로젝트 루트에서 로컬 HTTP 서버를 띄운 뒤 `http://127.0.0.1:<port>/.../index.html`로 검수합니다.

```powershell
Start-Process -FilePath python -ArgumentList @('-m','http.server','8787','--bind','127.0.0.1') -WorkingDirectory 'C:\Users\hjh\안티그래비티\문장군 컨텐츠' -WindowStyle Hidden
```

HTML 프리뷰는 특정 장면 자동검수를 위해 `?t=<seconds>` 쿼리를 지원해야 합니다.

```text
index.html?t=0.4
index.html?t=21.8
```

검수 보고에는 최소 아래를 포함합니다.

```text
첫 장면 currentInfo
첫 장면 reviewCard opacity
마지막 리뷰 장면 currentInfo
마지막 리뷰 장면 reviewCard opacity
MP4 생성 수
```

첫 장면이 리뷰 캡처가 아닌데도 리뷰 카드가 보이면 실패입니다. 특히 CSS 전환 규칙은 `.stage.review_capture_scroll...`처럼 motion class로 scope를 걸어야 하며, `.transition-hit.t-pop .review-card`처럼 전역 pop 전환에 리뷰카드를 묶으면 실패입니다.

## sync_manifest 생성 규칙

v3 제작 루틴은 HTML 생성 전에 `sync_manifest.json`을 저장합니다.

`sync_manifest.json`은 각 scene에 아래 값을 남겨야 합니다.

audio 블록에는 아래 값을 반드시 남깁니다.

```text
raw_tts_duration_sec
final_voice_duration_sec
compression_ratio
total_narration_chars_no_space
total_voice_cps
```

`total_voice_cps = 전체 narration_ref 공백 제외 글자수 / final_voice_duration_sec`입니다.
이 값이 9.0 이상이면 장면별 CPS가 통과해도 HTML/MP4로 진행하지 않습니다.
`render_duration_sec`는 타임라인 길이일 뿐이므로 `final_voice_duration_sec` 대체값으로 쓰지 않습니다.

```text
scene_id
asset
caption
narration
planned_time
duration_sec
narration_chars_no_space
scene_cps
meaning_match
meaning_match_evidence
risk
```

`meaning_match: true`는 planning recipe의 scene에 명시 증거가 있을 때만 edit recipe로 옮깁니다.
문자열 유사도, asset 이름 추정, 분위기 추정만으로 true 처리하지 않습니다.

제작 루틴에서 edit recipe를 보강할 때는 아래 원칙을 따릅니다.

```text
planning scene에 meaning_match: true가 있고,
asset + caption + narration이 edit beat와 정확히 대응하면
edit beat에 meaning_match: true와 meaning_match_source를 추가한다.
```

증거가 없으면 `meaning_match`를 만들지 않습니다.
이 경우 preflight가 `MEANING_MATCH_UNVERIFIED`로 실패해야 정상입니다.

## TTS 압축률/목소리 품질 하드 게이트

신규 세션은 최종 `voice.mp3` 길이만 보고 통과 처리하면 안 됩니다.
원본 TTS와 최종 속도 보정본을 모두 확인하고 아래를 보고합니다.

```text
원본 TTS 길이
최종 voice.mp3 길이
압축률 = 원본 TTS 길이 / 최종 voice.mp3 길이
사용 voice name
사용 persona/prompt
```

판정 기준:

```text
권장: 1.00~1.12
주의: 1.13~1.18
실패: 1.20 이상
렌더 금지: 1.25 이상
```

예시:

```text
39.49초 / 28.94초 = 1.36배 → 실패. 발음 뭉개짐 위험으로 렌더 금지.
```

수치가 통과해도 아래는 실패입니다.

```text
기존 문장군 음성과 다른 목소리
지나치게 차분한 낭독톤
낮고 처지는 톤
받침/조사 발음이 뭉개짐
카페에서 후기 읽어주는 느낌이 아니라 오디오북처럼 들림
```

실패 시에는 기존 voice를 덮어쓰지 말고 `voicefix_*` 후보를 별도로 만들고, 사용자가 음성을 확인한 뒤 승인본만 HTML/MP4에 연결합니다.

## 훅 검수 하드 게이트

신규 세션은 기획안의 훅 후보를 그대로 승인본으로 쓰면 안 됩니다.
HTML 첫 화면에 실제로 들어가는 최종 훅을 별도로 검수합니다.

좋은 훅의 조건:

```text
1. 무엇에 대한 이야기인지 1초 안에 보인다.
2. 시청자의 집/상황과 연결된다.
3. 첫 화면 이미지와 같은 말을 한다.
4. 이전 제작물과 다른 관점이 있다.
5. 너무 추상적인 결론어만 남지 않는다.
6. `docs/review_reels_content_standard_v1.md`의 후킹 트리거가 최소 1개 이상 있다.
```

권장 트리거:

```text
호기심 결핍
구체적 숫자
타깃 호명
통념 반박
손실 회피
결과 약속
```

문장군 우선 조합:

```text
현장 문제 + 통념 반박
손실 회피 + 호기심
타깃 호명 + 문제
```

실패 예:

```text
한 달 뒤, 진짜입니다
좋아졌습니다
드디어 해방
만족도가 높습니다
```

통과 예:

```text
중문 설치 한 달 뒤, 집 분위기가 달라졌습니다
복도 소리 다 들리던 구축 빌라라면?
에어컨 풀가동해도 거실이 덥다면?
다른 업체가 포기한 현장, 문장군은 시공했습니다
```

훅 검수 보고에는 반드시 아래를 포함합니다.

```text
최종 훅:
첫 화면 asset:
시청자가 1초 안에 이해하는 대상:
이전 유사 영상과의 차별점:
폐기한 훅과 폐기 사유:
```

## 장면 의미 일치 하드 게이트

HTML 프리뷰 생성 전, 모든 beat/scene에 대해 아래를 확인합니다.

```text
scene_id:
asset:
caption:
narration:
의미 일치 여부:
```

실패 예:

```text
asset: 시공전
caption: 시공 전엔 공간이 열려 있었습니다
narration: 설치 후 집 분위기가 확 달라졌다는 이야기입니다
판정: 실패. 화면/자막은 Before인데 내레이션은 After를 말함.
```

```text
caption: 브론즈 유리라 답답함보다 은은함
narration: 3연동 문은 부드럽고 댐퍼 덕분에 조용했다고 해요
판정: 실패. 자막은 유리/디자인, 내레이션은 문 구동/댐퍼를 말함.
```

하나라도 실패하면 HTML 생성 전 planning/edit recipe를 다시 작성합니다.

## 현재 정리된 파일 구조

각 리뷰 출력 폴더는 아래처럼 유지합니다.

```text
리뷰패키지/
  현재_HTML_preview/
  현재_final_render_YYYYMMDD.mp4
  현재_HTML이_참조하는_voice.mp3
  원본_script.md
  원본_subtitle.srt
  원본_voice.mp3
  이미지폴더/
  _work/
```

`_work/`에는 예전 테스트본, 중간 recipe, duplicate render, 프레임 폴더를 둡니다.
승인·privacy·render QA·대표 프레임 같은 증거는 보존합니다. 재생성 가능한 프레임,
contact sheet, rejected intermediate는 `scripts/cleanup_dry_run.py`가 후보로 확인하고
사용자가 범위를 승인한 경우에만 정리할 수 있습니다.

## 신규 세션 체크리스트

새 세션에서 먼저 읽을 문서 목록은 `AGENTS.md`의 `핵심 문서` 절 하나만 따릅니다.
이 문서는 별도 읽기 목록을 유지하지 않습니다.

과거 세션 인수인계는 `docs/archive/README.md`에서 찾을 수 있지만 신규 세션의
운영 권한 문서로 사용하지 않습니다.

신규 세션 첫 응답에서 해야 할 일:

```text
1. 최신 상태 확인
2. 작업할 리뷰 번호 확인
3. 리뷰 패키지 폴더가 없으면 먼저 생성
4. STATUS.md / APPROVAL_LOG.md 확인 또는 생성
5. 사용자에게 사진 넣을 정확한 폴더 경로 안내
6. 사진이 들어오면 사진검수/역할매핑부터 시작
7. 리뷰 각색 작가 브리프를 작성
8. PD 기획안과 scene 의미 일치 계획표를 제시하고 사용자 승인 요청
9. 사용자 승인 전 script/SRT/TTS/HTML 생성 금지
10. HTML 생성 전 reels_qa preflight 통과 확인
```

## 완료 후 다음 후보 준비

릴스 1건이 완료되면 Codex는 작업을 끝내기 전에 반드시 아래를 확인합니다.

```text
1. 완료 릴스 목록 갱신
2. 칸반 상태 갱신
3. 다음 제작 후보에서 완료 리뷰 제거
4. 후보군이 3개 미만이면 미제작 A/B권 후보 보충
5. 새 후보의 output 패키지 폴더와 이미지 폴더 생성
6. 사진 투입 안내 문서 갱신
7. live package state 재스캔
```

즉, 완료 보고에는 항상 아래 문장이 포함되어야 합니다.

```text
다음 후보군과 사진 투입 폴더까지 준비해두었습니다.
```

## 신규 세션 첫 응답 예시

사용자가 `리뷰 릴스 만들자`라고만 말하면 이렇게 시작합니다.

```text
좋습니다. 최신 운영 문서를 기준으로 리뷰 릴스 신규 발행 흐름으로 진행하겠습니다.
먼저 후보 리뷰 3개를 고르거나, 원하시는 리뷰 번호가 있으면 그 번호로 패키지 폴더를 만들겠습니다.
사진을 넣을 폴더를 먼저 만들어드리는 순서로 가겠습니다.
```

사용자가 `033 리뷰 릴스 만들자`처럼 번호까지 지정하면 이렇게 시작합니다.

```text
좋습니다. 033번을 대상으로 진행하겠습니다.
먼저 원문 리뷰와 사진 폴더를 확인해서 사진 역할 매핑, 훅 후보, 장면별 화면/자막/음성 일치 계획까지 만들겠습니다.
이 단계는 기획 검수 단계라서, 승인 전에는 script/SRT/TTS/HTML을 생성하지 않겠습니다.
```

## 번호 지정 작업의 완료 보고 기준

번호만 지정된 작업의 1차 완료 보고는 HTML 링크가 아니라 아래 항목이어야 합니다.

```text
1. 리뷰 원문 요약
2. 사진 수량과 역할 매핑
3. 부족 컷/위험 요소
4. 작가 브리프: 사건/감정/증거/말맛
5. 콘텐츠 목적 태그
6. 훅 후보 3개와 추천 1개
7. scene별 asset/caption/narration 의미 일치 계획표
8. D-024 TTS 속도 예상
9. D-025 훅 압축 검수
10. D-026 의미 일치 검수
11. 사용자 승인 질문
```

이 단계에서 HTML 링크, voice.mp3, SRT, script.md가 이미 생성되어 있으면 워크플로 위반입니다.
