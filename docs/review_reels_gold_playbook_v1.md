# 문장군 리뷰 릴스 골드 제작 기준 v1

## 기준 작품

현재 production의 창작 기준은 `004_어려운시공`과 `005_여름에어컨` 최종 승인본이다.
이 파일들은 Git에 넣는 fixture가 아니라 로컬 비교 기준이다. 신규 세션은 특정 영상의
문구나 장면을 복사하지 않고, 아래 편집 판단을 재현해야 한다.

## 핵심 판단

- 제품 설명보다 고객의 사건과 생활 변화를 먼저 보여준다.
- 첫 훅은 완성 문장이고 첫 4초 안에 문제 또는 반전을 전환한다.
- 기본 길이는 20~28초다. 원문과 사진에 충분한 사건이 있을 때만 더 길게 쓴다.
- 기본은 7~8개 major beat와 9~12개의 micro visual moment다.
- 음성, 자막, 화면은 같은 순간에 같은 의미를 말한다.
- 실제 리뷰 캡처는 원본을 한 번만 사용하고, 보통 3~5초 동안 마지막 증명으로 보여준다.
- 마지막은 고객 결론 다음 CTA다. 리뷰 화면이 길게 멈추거나 CTA가 늦게 따라오면 실패다.

## 이야기 모드

작가는 대본 전에 `writer_brief.story_mode`를 하나 선택한다.

- `problem_solution`: 불편과 해결이 선명한 후기
- `difficult_site`: 어려운 현장과 판단이 중심인 후기
- `time_lapse_review`: 설치 직후와 한 달 뒤처럼 시간 변화가 중심인 후기
- `human_service`: 기사·상담·배려 같은 사람이 중심인 후기
- `seasonal_comfort`: 여름·겨울 생활 변화가 중심인 후기
- `living_convenience`: 동선·반려동물·청소 같은 생활 편의 후기

공통 필수 역할은 `event → problem → resolution → felt_result → review_proof → cta`다.
`context`, `choice_turn`, 실측, 공정 설명은 원문과 사진에 실제 근거가 있을 때만 넣는다.
장면 수를 채우기 위한 실측·제품·외관 filler는 금지한다.

## 사진과 리뷰

- 사진 폴더의 모든 미디어를 먼저 보고 `use`, `hold`, `exclude`와 이유를 기록한다.
- 첫 화면은 실제 고객 사진이어야 하며, 훅의 사건을 가장 빨리 이해시키는 구도를 고른다.
- 모든 사진을 억지로 쓰지 않는다. 다만 사용하지 않은 사진도 판단 기록은 남긴다.
- 리뷰 캡처를 재가공 카드로 대체하지 않는다.
- 같은 리뷰의 앞부분과 뒷부분을 두 장면으로 반복해 시간을 채우지 않는다.
- 개인정보 위험은 crop, 최소 blur, 짧은 노출을 검토한 뒤 해결되지 않으면 제외한다.

## 대본과 TTS

- 표준 산출물은 `*_script.md`, `*.srt`, `*_voice.mp3`다.
- 공식 음성은 Gemini TTS `Sulafat`이다. Windows SAPI나 임시 로컬 음성은 production 금지다.
- 권장 속도는 공백 제외 6.5~7.5자/초, 허용 범위는 5.0~8.5자/초다.
- `generate.py`가 TTS 생성 보고서를 자동으로 남긴다. 모델, voice, 대본 hash,
  원본/최종 길이, 최종 voice hash가 edit recipe와 일치해야 한다.
- 자막은 1~2줄, 의미 단위 줄바꿈, 포인트 키워드 1~2개만 강조한다.
- `\n`, `/n` 문자열 노출, 글자 잘림, 피사체 가림은 실패다.

## HTML 완료의 정의

HTML 파일 생성은 완료가 아니다.

1. 공식 preflight 통과
2. 공식 HTML 생성
3. `html-preview-qa.mjs` 자동 대표 프레임 검사 통과
4. 작업자가 `_qa_frames` 전부 직접 확인
5. 훅, 의미 싱크, 자막, 리뷰 원본, CTA, 개인정보 수동 확인
6. 그 뒤에만 사용자에게 `HTML 검수 준비 완료`라고 보고

자동 검사가 통과해도 `html_internal_qa_report.json`의
`manual_review.status`는 `pending`이다. 작업자가 화면을 보지 못했다면
`HTML 생성, 내부 시각 QA 대기`라고 보고해야 하며 완료라고 말하면 안 된다.

## 117 회귀 방지

다음 조합은 실패 사례로 취급한다.

- canonical metadata는 `photo_intake_pending`인데 STATUS만 true
- Windows SAPI 또는 `Microsoft Heami Desktop`
- 5.0자/초 미만의 잠 오는 음성
- 첫 hook beat가 4초 초과
- 같은 실제 리뷰 캡처를 두 번 사용
- 리뷰 캡처 한 장을 6초 초과 유지
- `time_lapse_review`에 근거 없는 실측·공정 filler 삽입
- `*_narration.txt`를 표준 script로 보고
- 시각 검수 없이 HTML 완료 보고
