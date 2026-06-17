# 문장군 리뷰 릴스 엔진 고도화 감사 보고서

작성일: 2026-06-13  
목적: 리뷰 릴스 제작 업무를 분해하고, 반복 문제의 원인을 찾아 자동화 제작소를 더 강하게 만든다.

## 1. 총괄 판단

문장군 리뷰 릴스 엔진은 가능성이 있다. 이미 005, 010, 004, 020에서 “리뷰 원문 -> 생활 불편 -> 현장 증거 -> 변화 -> 리뷰 증명” 구조가 작동했다. 이후 025, 033, 034, 098, 114를 제작하며 더 분명해진 사실은 다음이다.

좋은 방향:

- 실제 현장 사진 기반이라 신뢰감이 있다.
- 고객 리뷰를 단순 요약하지 않고 생활 변화로 각색할 수 있다.
- HTML 프리뷰 기반이라 자막, 모션, 장면 구성을 빠르게 검수할 수 있다.
- 생성 이미지는 실제 증거가 아니라 부족한 이해 보조 인서트로 쓰면 효과가 있다.

위험한 방향:

- 총 영상 길이만 맞추면 음성, 자막, 화면이 맞는 것처럼 착각한다.
- 신규 세션은 현재 승인본, 폐기본, 테스트본을 구분하기 어렵다.
- 훅이 추상화되면 첫 1초가 바로 약해진다.
- 모든 리뷰가 `문제 -> 실측 -> 시공후 -> 리뷰 -> 무료 실측` 흐름으로 빨려 들어가면 금방 로봇처럼 보인다.

결론:

```text
문서 규정은 어느 정도 준비됐다.
다음 고도화는 "실행 전 자동 차단 게이트"와 "장면별 싱크 엔진"이다.
```

## 2. 현재 업무 분해

현재 리뷰 릴스 1건은 아래 업무로 쪼개진다.

```text
1. 리뷰 선택
2. 패키지/이미지 폴더 준비
3. 사진 압축 해제 및 역할 매핑
4. 리뷰 원문 해석
5. 콘텐츠 목적 결정
6. 훅 후보 생성
7. PD 기획안 작성
8. asset/caption/narration 의미 일치표 작성
9. 사용자 기획 승인
10. planning_recipe/edit_recipe 생성
11. script/SRT/TTS 생성
12. TTS 속도/압축률 검증
13. HTML 프리뷰 생성
14. 브라우저 시각 검수
15. 사용자 HTML 승인
16. MP4 렌더
17. MP4 대표 프레임/싱크 검수
18. 캡션/해시태그 점검
19. 폴더 정리
20. 대시보드/다음 후보 갱신
```

현재 가장 많이 깨지는 구간은 8, 12, 14, 16, 19다.

## 3. 반복 문제와 원인

### 3.1 음성보다 화면/자막이 먼저 감

원인:

- 현재 검증은 전체 CPS에 치우쳐 있다.
- `timeline_planner.py`는 전체 음성 길이에 맞춰 모든 장면을 비례 확대/축소할 수 있다.
- 장면별 내레이션이 실제 몇 초에 끝나는지는 검증하지 않는다.

해결:

```text
총 CPS 통과 = 참고값
scene CPS 통과 = 필수값
scene boundary sync = 최종값
```

도입해야 할 파일:

```text
sync_manifest.json
sync_qa.md
```

필수 필드:

```json
{
  "scene_id": "s03",
  "asset": "after_main",
  "caption": "설치 후 분위기",
  "narration": "설치하고 보니 집 분위기와 잘 어울렸다고 해요.",
  "planned_time": [8.2, 11.4],
  "narration_chars_no_space": 24,
  "scene_cps": 7.5,
  "meaning_match": true,
  "risk": "pass"
}
```

하드 게이트:

```text
scene CPS 8.5 초과: 수정 필요
scene CPS 9.0 초과: HTML 생성 금지
asset/caption/narration 의미 불일치: HTML 생성 금지
화면이 음성보다 0.5초 이상 앞섬: 렌더 금지
```

### 3.2 신규 세션이 바로 HTML까지 만들어버림

원인:

- 문서에는 “번호 지정은 제작 승인 아님”이라고 되어 있지만, 폴더 단위 상태 파일이 없다.
- 신규 세션은 현재 단계가 `사진검수`, `기획승인대기`, `HTML승인대기`, `렌더가능` 중 어디인지 즉시 알기 어렵다.

해결:

각 리뷰 패키지 루트에 `STATUS.md`와 `APPROVAL_LOG.md`를 둔다.

`STATUS.md` 예:

```markdown
# 114 상태

- review_id: 114
- current_variant: pet_noise_relief_v1
- photo_checked: true
- pd_plan_approved: true
- script_created: true
- tts_created: true
- html_created: true
- html_approved_by_user: true
- mp4_allowed: false
- current_html: 114_반려동물소음차단_pet_noise_relief_v1_html_preview_v2/index.html
- current_voice: 114_반려동물소음차단_pet_noise_relief_v1_voice.mp3
- current_recipe: 114_반려동물소음차단_pet_noise_relief_v1_edit_recipe.json
- blocked_reason:
```

`APPROVAL_LOG.md` 예:

```markdown
## 2026-06-13

- user_order: "114번 리뷰 릴스 제작하자"
- approved_scope: 대상 리뷰 지정
- not_approved: MP4 렌더

## 2026-06-13

- user_order: "굿!!!! 수고했어요"
- approved_scope: HTML 방향 승인
- next_allowed: 098/114 전체 승인 후 일괄 렌더 검토
```

### 3.3 훅이 약해짐

원인:

- 기획 훅을 화면용으로 압축할 때 주어, 상황, 변화가 빠진다.
- “진짜입니다”, “좋아졌습니다”, “설치한 집”처럼 대상 없는 결론어가 남는다.

훅 통과 기준:

```text
첫 화면 훅 = 대상 + 상황/불편 + 변화/궁금증
```

실패:

```text
한 달 뒤, 진짜입니다
강아지 때문에 설치한 집
만족도가 높았습니다
```

통과:

```text
중문 설치 한 달 뒤, 집 분위기가 달라졌습니다
복도 소리만 나면 짖던 강아지라면?
수평이 안 맞던 구축 현관, 그냥 설치하면 안 됩니다
```

도입 도구:

```text
hook_qa.py
```

검사 항목:

- 첫 훅 2줄 안에 핵심 명사가 있는가?
- `좋다`, `진짜`, `만족`, `해방`만 남지 않았는가?
- 첫 asset과 같은 말을 하는가?
- 최근 3개 릴스와 훅 유형이 다른가?

### 3.4 자막 줄바꿈/크기/가림

원인:

- 글자수 기반 검증은 실제 브라우저 렌더 폭을 보장하지 않는다.
- 상품 썸네일, 리뷰 캡처, 실측 사진 위에 중앙 자막이 덮이는 경우가 있다.

해결:

Playwright 기반 `caption_fit_qa.py`를 만든다.

검사:

```text
모든 beat 시작/중간/끝에서 caption bbox 추출
stage 밖으로 나가는지 확인
3줄 초과 확인
상품/리뷰 카드와 겹치는지 확인
첫 훅이 잘리는지 확인
```

### 3.5 파일이 지저분해짐

원인:

- v1/v2/v3, raw/final/voicefix/rejected가 루트에 섞인다.
- 최신 승인본이 무엇인지 파일명만으로 판단해야 한다.

해결:

패키지 폴더는 아래처럼 강제한다.

```text
리뷰패키지/
  STATUS.md
  APPROVAL_LOG.md
  asset_map.md
  sync_qa.md
  current/
    planning_recipe.json
    edit_recipe.json
    script.md
    subtitle.srt
    voice.mp3
    html_preview/
  render/
    final_upload_10mbps.mp4
    qa_frames/
  images/
  _work/
    archive/
    rejected/
    experiments/
```

## 4. 팀 구조

총괄 PD가 혼자 만들지 않고, 아래 팀 구조로 움직인다.

| 역할 | 책임 | 산출물 |
|---|---|---|
| 총괄 PD | 최종 방향, 승인 게이트, 사용자 보고 | PD 판단, 최종 보고 |
| 리뷰 해석 작가 | 원문에서 사건/감정/증거 추출 | review_brief.md |
| 사진 큐레이터 | 사진 역할 매핑, 부족 컷 판단 | asset_map.md |
| 훅/카피라이터 | 훅 후보, 자막 톤, CTA | hook_qa.md |
| 타임라인 에디터 | scene별 asset/caption/narration 구성 | planning_recipe.json |
| 싱크 감독 | 장면별 CPS, 음성 도착 시간, SRT | sync_qa.md |
| 모션 디자이너 | 장면별 전환/무빙 선택 | edit_recipe.json |
| 렌더 엔지니어 | HTML/MP4 렌더, 스펙 확인 | render_report.md |
| QA 검수관 | 허위 검증 방지, 대표 프레임 확인 | qa_report.md |
| 운영 매니저 | 대시보드, 폴더 정리, 다음 후보 준비 | STATUS.md, dashboard update |

자동화가 늘어도 최종 책임은 총괄 PD에게 둔다.

## 5. 리뷰 유형별 템플릿 분화

한 가지 템플릿을 반복하지 않는다. 판단 기준은 같게, 장면 순서는 다르게 간다.

| 유형 | 핵심 리듬 | 추천 훅 |
|---|---|---|
| 계절/냉방형 | 더위 증상 -> 현관 공기 흐름 -> 설치 -> 체감 | 에어컨 풀가동해도 거실이 덥다면? |
| 구축 소음/냄새형 | 복도/외관 -> 유입 문제 -> 실측 -> 변화 | 복도 소리 다 들리는 구축 빌라라면? |
| 어려운 현장형 | 장애물 먼저 -> 왜 어려운지 -> 판단 -> 해결 | 다른 업체가 포기한 현장, 진짜 안 될까? |
| 한 달 후기형 | 결과 먼저 -> 사용 후 남은 만족 -> 디테일 | 중문 설치 한 달 뒤, 집 분위기가 달라졌습니다 |
| 반려동물/아이형 | 생활 루틴 -> 불편 반응 -> 변화된 생활감 | 복도 소리만 나면 짖던 강아지라면? |
| 로봇청소/동선형 | 막히는 동선 -> 원인 -> 해결된 흐름 | 로봇청소기가 문턱에서 멈춘다면? |
| 상담/일정 신뢰형 | 일정 불안 -> 실측/약속 -> 완료 -> 리뷰 | 금요일 실측, 수요일 시공까지 가능했던 이유 |
| 디자인 만족형 | 소재/빛/유리감 -> 공간 변화 -> 후기 | 집 분위기와 어울리는 중문을 찾는다면? |
| 비용/옵션 고민형 | 가격 불안 -> 현장별 안내 -> 납득 | 중문 가격, 결국 현장 조건이 중요합니다 |

## 6. 생성 이미지 사용 규칙

생성 이미지는 쓸 수 있다. 단, 증거가 아니라 설명용 인서트다.

허용:

- 소리, 냄새, 열기, 찬바람 같은 보이지 않는 문제 설명
- 로봇청소기 문턱 통과 같은 생활 동선 이해 보조
- 실제 사진으로 설명이 부족한 짧은 B-roll

금지:

- 실제 시공 완료 증거 대체
- 제품 마감/색상/유리/댐퍼 디테일 증명
- 고객 리뷰 캡처 대체
- 실제 고객 집처럼 오해될 수 있는 장면

생성 이미지는 recipe에 반드시 기록한다.

```json
{
  "generated_asset": true,
  "not_real_proof": true,
  "generated_reason": "문턱 없는 로봇청소기 통과 장면 설명",
  "visual_claim": "문턱/단차 없이 로봇청소기가 통과한다",
  "literal_qa_result": "문턱, 턱, 레일, 단차가 보이지 않음"
}
```

## 7. 외부 벤치마킹

외부 자동 영상 도구들의 공통점은 “예쁜 편집”보다 “타임라인 데이터 구조”가 먼저라는 점이다.

- Remotion은 React 기반으로 재사용 가능한 영상 템플릿과 props 기반 렌더링을 강조한다. 서버 렌더링의 `renderMedia()`처럼 코드에서 composition, codec, outputLocation을 명시해 렌더한다. 참고: https://www.remotion.dev/docs/renderer/render-media
- Remotion의 dataset render 문서는 JSON 데이터셋을 여러 영상으로 배치 렌더하는 흐름을 보여준다. 문장군도 `review_id -> recipe -> render` 구조를 더 엄격히 가져갈 수 있다. 참고: https://www.remotion.dev/docs/dataset-render
- Shotstack은 트랙, 클립, 자산, 전환, 텍스트를 JSON edit schema로 구성해 렌더 API에 보낸다. 문장군의 `edit_recipe.json`도 이 수준으로 명확한 계약이 필요하다. 참고: https://shotstack.io/docs/api/
- Creatomate는 RenderScript라는 JSON 기반 포맷으로 영상/이미지 생성 정보를 담는다. 이 관점은 `planning_recipe`와 `edit_recipe`를 분리하는 데 유용하다. 참고: https://creatomate.com/docs/api/render-script/json-structure
- Editly는 Node.js와 FFmpeg 기반 선언형 NLE 도구로, clips/images/audio/titles/transitions를 코드로 만든다. 문장군의 로컬 HTML/FFmpeg 방식과 가까운 오픈소스 참고점이다. 참고: https://github.com/mifi/editly
- MoviePy는 Python 기반 자동 편집 라이브러리로, 빠른 프로토타입에는 좋지만 문장군처럼 자막/브라우저 모션/검수 UI가 중요한 경우 단독 주력보다는 보조 도구에 가깝다. 참고: https://zulko.github.io/moviepy/
- FFmpeg는 최종 인코딩과 필터 처리의 핵심 도구다. 문장군은 이미 Playwright 캡처 후 FFmpeg 인코딩 구조를 쓰므로, 여기서는 스펙 고정과 재현성이 핵심이다. 참고: https://ffmpeg.org/ffmpeg.html
- WhisperX는 forced alignment로 음성 transcription과 오디오를 단어 단위에 가깝게 맞추는 방향을 제공한다. 한국어 TTS에 바로 완벽 적용된다고 단정할 수는 없지만, “장면별 발화 도착 시간”을 잡는 방향성은 중요하다. 참고: https://github.com/m-bain/whisperX

벤치마킹 결론:

```text
문장군은 CapCut형 수동 편집이 아니라
Remotion/Shotstack/Creatomate류의 "recipe-first 제작소"로 가야 한다.
단, 현재 HTML/Hyperframe 기반 자산은 살리고,
부족한 것은 render보다 QA 계약이다.
```

## 8. 우선 실행 로드맵

### Phase 1. 사고 방지 잠금장치

기간: 즉시

- `STATUS.md` 템플릿 추가
- `APPROVAL_LOG.md` 템플릿 추가
- `asset_map.md` 템플릿 추가
- HTML 생성 전 `preflight_html_qa.py` 도입
- MP4 렌더 전 `preflight_render_qa.py` 도입

목표:

```text
승인 전 HTML 생성
승인 전 MP4 렌더
analysis/hooks 비어 있는 recipe
scene CPS 초과 recipe
```

위 네 가지를 자동으로 막는다.

### Phase 2. 싱크 엔진

기간: 다음 개발 라운드

- `sync_manifest.json` 생성
- 장면별 CPS 계산
- 장면별 asset/caption/narration 의미 일치표 생성
- SRT를 planning time이 아니라 sync manifest에서 생성

목표:

```text
총 길이만 맞는 영상 금지
화면이 음성보다 먼저 가는 영상 금지
```

### Phase 3. 브라우저 기반 시각 QA

기간: 싱크 엔진 이후

- Playwright로 beat별 대표 프레임 자동 캡처
- caption bbox 수집
- 상품 썸네일/리뷰 캡처 가림 검사
- `??`, `�`, 잘린 훅 자동 검사

목표:

```text
HTML에서 봤을 때 괜찮아 보였는데 MP4에서 자막 크기/위치가 깨지는 사고 방지
```

### Phase 4. 템플릿 분화

기간: 안정화 이후

- 리뷰 유형별 scene grammar 분리
- 훅 유형 라이브러리 도입
- motion/effect taxonomy를 recipe에서 선택하게 개선
- 최근 3개 릴스와 훅/장면 리듬 중복 검사

목표:

```text
양산하지만 같은 영상처럼 보이지 않게 만들기
```

### Phase 5. 운영 대시보드 자동화

기간: 이후

- `PROJECT_DASHBOARD.md`, `reels_operations_dashboard_v1.md` 자동 갱신
- 완료/대기/사진대기/HTML대기/렌더대기 상태 자동 집계
- 다음 후보 3개 미만이면 자동 보충

목표:

```text
신규 세션에서도 현재 상태를 30초 안에 파악
```

## 9. 다음에 바로 할 일

가장 먼저 할 개발 과제는 아래 3개다.

```text
1. 패키지 상태 파일 템플릿 도입
2. sync_qa.py 도입
3. preflight_html_qa.py 도입
```

이 3개가 생기면, 신규 세션이 “033 리뷰 릴스 만들자”를 듣고 바로 HTML까지 만드는 사고를 줄일 수 있고, 화면/자막이 음성보다 앞서는 고질병도 HTML 전 단계에서 잡을 수 있다.

최종 판단:

```text
문장군 리뷰 릴스 엔진은 제작 가능 단계에서
운영 가능한 제작소 단계로 넘어가야 한다.

핵심은 더 화려한 효과가 아니라,
좋은 PD 판단을 자동 검수 게이트로 잠그는 것이다.
```
