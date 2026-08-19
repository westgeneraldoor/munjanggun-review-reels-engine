# PROJECT_BRAND_ADAPTER - 리뷰 릴스 엔진 브랜드 적용 방식

> 작성일: 2026-06-25 / 동기화: 2026-07-28
> 적용 프로젝트: 문장군 리뷰 릴스 엔진
> 중앙 원본: `C:\Users\hjh\안티그래비티\문장군_브랜드`

## 1. 이 프로젝트의 역할

문장군 리뷰 릴스 엔진은 네이버 고객 리뷰와 현장 사진을 바탕으로 Instagram과 Naver Clip용 기획, 대본, SRT, TTS, HTML 프리뷰, MP4 렌더를 만드는 로컬 자동화 프로젝트다. 두 채널은 공통 안전·제작 엔진을 공유하고, 차이는 channel preset 또는 adapter에만 둔다.

중앙 브랜드 원본은 문장군이 무엇을 말해야 하는지 정한다.

이 어댑터는 리뷰 릴스에서 그것을 어떻게 말하고, 어떤 검수 절차를 통과해야 하는지 정한다.

## 2. 중앙 원본 적용 방식

| 중앙 기준 | 리뷰 릴스 적용 |
|---|---|
| 고객은 제품명보다 자기 문제를 먼저 떠올린다 | 첫 1~3초 훅은 제품명이 아니라 고객 문제, 생활 사건, 현장 상황으로 시작한다 |
| 무료 방문실측은 핵심 브랜드 경험이다 | CTA와 캡션에서 "무료 방문실측으로 우리 집 구조를 확인"하는 방향을 유지한다 |
| 가격은 숨기지 않되 단일 확정가처럼 말하지 않는다 | 릴스 본문에서 구체 가격을 단정하지 않고, 필요 시 조건/실측 전제를 붙인다 |
| 직접 제작·전속 시공·A/S는 신뢰 근거다 | 제품 자랑이 아니라 문제 해결 후반부의 신뢰 근거로 짧게 사용한다 |
| 리뷰 수는 변동 claim | 발행 전 중앙 `EVIDENCE_REGISTER.md`의 최신 기준일·상태를 확인한다. 이 어댑터에 고정 숫자를 복사하지 않는다 |
| 따뜻한 주거 전문가 + 시스템형 전문 브랜드 | 너무 전단지 같거나 AI 감성문구 같은 톤을 피하고, 실제 후기와 현장감 중심으로 만든다 |

## 3. 프로젝트 전용 출력 방식

- v2: current production
- v3: discontinued (2026-08-19)
- v3.1: discontinued (2026-08-19)

현재 production 출력은 v2다. `v3`과 `v3.1`은 성과 검증 전에 중단됐고 production 산출물·승인 경로를 대체한 적이 없다. 중단 사유는 `docs/reels_format_status_v1.md`에서 관리한다.

리뷰 릴스 1건의 표준 산출물은 아래 구조를 따른다.

```text
planning_recipe.json
edit_recipe.json
sync_manifest.json
*_script.md
*.srt
*_voice.mp3
*_html_preview_v2/index.html
*_final_render_YYYYMMDD_upload_10mbps.mp4
```

단, MP4는 사용자 HTML 승인 후 명시적 렌더 승인까지 받아야 생성한다.

최종 `*_script.md`에는 반드시 아래 섹션이 포함되어야 한다.

```markdown
## 캡션
...

## 해시태그
...
```

`caption.txt`, `hashtag.txt`, `hashtags.txt` 같은 별도 파일은 만들지 않는다.

## 4. 리뷰 릴스 콘텐츠 공식

리뷰 릴스는 중앙 브랜드 원본의 제품/현장 기준을 따르되, 구성은 이 프로젝트의 릴스 문법을 따른다.

```text
사건
-> 문제 확대
-> 반전
-> 해결
-> 고객 반응
-> 리뷰 증명 또는 CTA
```

좋은 리뷰는 만족도가 높은 리뷰가 아니라 릴스 사건이 되는 리뷰다.

리뷰에서 우선 찾는 것:

- 갈등
- 불편
- 후회
- 고민
- 놀람
- 감동
- 생활 변화

## 5. 리뷰 원문 왜곡 금지

중앙 브랜드 원본이 있어도, 리뷰 릴스는 원본 리뷰를 배신하면 안 된다.

HTML 생성 전 planning recipe에는 아래가 있어야 한다.

```json
{
  "review_source": {
    "text": "",
    "review_quote_for_proof": "",
    "inferred_fields": [],
    "unsupported_story_elements": []
  }
}
```

하드 실패:

- `review_quote_for_proof`가 원문 리뷰에 실제 포함되어 있지 않음
- 원문에 없는 소음, 냄새, 먼지, 반려동물, 아이, 공사난이도 소재를 실제 사건처럼 사용
- 원문에 없는 감정을 고객의 실제 감정처럼 사용
- 원문에 없는 성능 수치, 가격, 보장 표현 사용
- `unsupported_story_elements`가 비어 있지 않음
- 추론이 필요한데 `inferred_fields`에 표시하지 않음

## 6. 프로젝트 전용 금지사항

아래는 중앙 브랜드 원본과 별개로 리뷰 릴스 엔진에서 금지한다.

- 리뷰 번호 지정만으로 script/SRT/TTS/HTML 생성
- 사진검수 없이 영상 기획
- 작가 브리프 없이 PD 기획안 작성
- PD 기획안 승인 없이 HTML 생성
- HTML 승인 없이 MP4 렌더
- MP4 렌더 여러 개를 한 번에 처리
- 리뷰 캡처를 과도하게 오래 보여주거나, 읽기 어려운 전체 리뷰를 그대로 노출
- 사진 위 좌상단 의미 없는 라벨, 작은 설명 칩 남발
- 자막이 사진의 핵심 피사체를 가리는 배치
- 음성, 자막, 화면이 서로 다른 의미를 말하는 타임라인
- 생성 이미지를 실제 시공 증거처럼 사용하는 것

## 7. 프로젝트 전용 QA 기준

리뷰 릴스는 아래 QA를 통과해야 한다.

| 단계 | 기준 문서/명령 |
|---|---|
| 브랜드/현장 기준 | 중앙 `BRAND_CONTEXT.md`, `FIELD_JUDGMENT_RULES.md`, `DESIGN.md` |
| 콘텐츠·작가·훅 | `docs/review_reels_content_standard_v1.md` |
| 화면·모션·오디오 | `docs/review_reels_visual_edit_standard_v1.md` |
| recipe 계약 | `docs/review_recipe_contract_v2.md` |
| 사진/얼굴/개인정보 | `docs/reels_privacy_asset_qa_rules_v1.md` |
| HTML 전 preflight | `python scripts/produce_review_v2.py preflight --package ... --planning ... --edit ... --privacy-manifest ... --sync-manifest ...` |
| 렌더 QA | `docs/render_qa_rules_v2.md` |
| 캡션/해시태그 | `docs/reels_posting_copy_standard_v2.md` |

## 8. 디자인 적용과 영상 예외

중앙 `DESIGN.md` v5.1의 Editorial Showroom 방향을 기본으로 한다. 정보 위계의 중심은 Ink, 상담·도움·선택 상태의 보조색은 Forest다. 큰 한글 제목은 Tmoney RoundWind ExtraBold, 본문/UI는 Pretendard Variable을 기본 후보로 삼는다. 실제 주거 공간 사진과 절제된 신뢰 표현을 우선하고, 중앙 웹 화면을 영상에 그대로 복제하지 않는다.

영상 전용 예외는 아래처럼 좁게 관리한다.

- 9:16 자막은 웹 본문보다 훨씬 크게 쓴다. 모바일 가독성, caption-safe-area, 음성/자막/화면 싱크가 토큰의 픽셀값보다 우선한다.
- 짧은 강조 모션은 허용하지만 사진의 핵심 피사체와 리뷰 증거를 가리면 안 된다.
- v2 legacy preview의 노랑 자막, 로컬 `nelnasamchae.ttf`, 기존 모션은 이미 승인된 v2 패키지를 소급 변경하는 근거가 아니다. 새 v2 production도 별도 디자인 변경 승인 없이는 현 상태를 유지한다.
- 차세대 포맷은 Tmoney RoundWind ExtraBold/Pretendard Variable과 Ink/Forest를 후보로 검토할 수 있다. 다만 contrast, 자막 가림, 실제 사진, privacy, meaning-match QA를 통과하기 전에는 production으로 승격하지 않는다.
- 가격·리뷰 수·A/S·일정·서비스 지역·이벤트처럼 변동 claim을 화면이나 음성에 넣기 전에는 중앙 `EVIDENCE_REGISTER.md`와 `OPEN_QUESTIONS_REGISTER.md`를 확인한다. 확인되지 않은 claim은 발행 문구에서 제외한다.

중앙 기준과 프로젝트 예외가 충돌하면 중앙 디자인을 먼저 검토한다. 릴스의 자막 크기·타임라인 모션·TTS 싱크처럼 채널에만 해당하는 값은 이 어댑터가 결정하되, production v2 규칙 변경은 별도 사용자 결정이 필요하다.

## 9. 생성 이미지/B-roll 적용

실제 현장 사진이 최우선이다.

생성 이미지는 아래에 한해 쓸 수 있다.

- 생활 불편 설명
- 보이지 않는 문제를 이해시키는 짧은 인서트
- 문턱, 동선, 소음, 냄새처럼 실제 사진만으로 설명이 어려운 상황 보조

생성 이미지는 실제 시공 완료, 제품 마감, 실측, 유리 색상, 리뷰 증거를 대체할 수 없다.

생성 이미지를 쓰면 recipe에 아래를 남긴다.

```text
generated_asset: true
generated_reason:
not_real_proof: true
visual_claim:
literal_qa_result:
```

## 10. 중앙 원본과 섞으면 안 되는 것

아래는 중앙 브랜드 원본에 넣지 않고 이 프로젝트 어댑터와 운영 문서에 둔다.

- 리뷰 릴스 작가 페르소나
- TTS voice/persona/속도 기준
- HTML 프리뷰 폴더 구조
- MP4 렌더 스펙과 대표 프레임 QA
- 리뷰 원문 왜곡 방지 JSON 계약
- output/reviews/scratch 폴더 운영
- GitHub에 고객자료를 커밋하지 않는 로컬 산출물 정책
- 인스타그램 캡션/해시태그 파일 포함 규칙

중앙 원본은 브랜드 기준을 관리하고, 이 프로젝트는 리뷰 릴스 제작 시스템을 관리한다.
