# 문장군 Motion Rule v1

작성일: 2026-06-15

## 목적

문장군 리뷰 릴스의 모션그래픽, 전환, 자막, 효과음은 "효과가 보이는 영상"이 아니라 "리뷰 내용이 더 잘 읽히는 영상"을 위해 사용한다.

이번 기준은 105번 pro effects 실험 실패와 Remotion/HyperFrames/GSAP 벤치마킹을 반영해 만든다.

## 핵심 결론

문장군 릴스의 우선순위는 아래 순서를 따른다.

```text
1. 음성/자막 싱크
2. 문맥에 맞는 사진 선택
3. 사진의 미세한 움직임
4. 절제된 자막 강조
5. 큰 단락 사이의 제한된 전환
6. 나레이션을 방해하지 않는 BGM/SFX
```

효과를 먼저 넣지 않는다. 효과는 위 1~4가 안정된 뒤 보조로만 사용한다.

## 허용 효과

### 1. Editorial Caption

자막은 한 번에 1~2줄만 사용한다. 강조어는 한 장면에 1개, 많아도 2개까지다.

허용:

- 핵심어 색상 강조
- 핵심어만 3~8% 크기 차이
- 핵심어만 0.08~0.15초 늦게 들어오는 soft pop
- 0.12~0.35초 늦게 들어오는 caption delay
- 짧은 opacity/y/scale 진입
- 후킹/결론 장면만 약한 scale pop

금지:

- 단어마다 튀는 TikTok식 과장
- 조사만 남는 줄바꿈
- 자막이 사진의 핵심 피사체나 리뷰 캡처를 가리는 것
- 컷마다 폰트, 색, 테두리가 바뀌는 것

### 1-1. Keyword Accent

키워드 강조는 문장군 Motion Rule v1의 기본 고도화로 채택한다. 단, 장식 컴포넌트가 아니라 자막 내부의 미세한 편집감으로만 사용한다.

기본값:

```text
한 장면 최대 2개
권장 1개
강조 크기 1.03~1.08배
강조 지연 80~150ms
효과음 없음
```

허용:

- 문제어: 냄새, 먼지, 소음, 한기
- 신뢰어: 꼼꼼, 친절, 현장 배려, 실제 리뷰
- 결과어: 깔끔, 만족, 추천, 분위기
- CTA어: 무료 실측, 상담

금지:

- 조사/어미 강조
- 3개 이상 강조
- 모든 줄의 모든 단어 강조
- 밑줄, 동그라미, 화살표를 기본 강조로 사용하는 것
- 강조 애니메이션 때문에 자막 싱크가 빨라 보이는 것

### 2. Photo Motion

사진은 정지시키지 말고 1.03~1.10배 범위에서 미세하게 움직인다.

허용:

- 현장 진입: 세로 pan 또는 약한 push-in
- 시공 전: 약한 어둡게 + 안정적인 push-in
- 작업/실측: 디테일 쪽으로 천천히 이동
- 시공 후: 밝게, 부드럽게, 넓게 보여주는 pan
- 리뷰 캡처: 원본은 흔들지 말고 안정적으로 노출

금지:

- 저해상도 사진 과확대
- 피사체가 잘리는 pan
- 모든 컷 같은 방향 이동
- 의미 없이 흔들리는 problem motion

### 3. Scene Transition

전환은 모든 컷에 넣지 않는다. 큰 단락 사이에만 사용한다.

허용:

- `smooth_slide`
- `smooth_cut`
- 약한 `caption_swap`
- 후킹/결과 장면의 제한된 `pop`
- Before/After가 명확할 때만 split reveal 계열

주의:

- transition은 타임라인을 앞서가게 만들면 실패다.
- 전환은 나레이션 문장 끝 또는 새 문장 시작에 맞춘다.

금지:

- 랜덤 전환
- 매 컷 flash/glow
- 필름 번, iris, clock wipe의 남발
- 말이 끝나기 전에 화면이 다음 의미로 넘어가는 것

### 4. Proof Overlay

리뷰 증명은 원본 캡처를 먼저 읽히게 하고, 핵심 문장만 보조로 뽑는다.

허용:

- 실제 리뷰 캡처
- 핵심 문장 1개 확대
- 리뷰 원본 위/아래의 작은 proof label
- 하단 CTA 카드

금지:

- 리뷰 본문을 가리는 카드
- "실제 리뷰" 배지가 너무 커지는 것
- 리뷰 캡처 위에 반짝이, 웨이브, 화살표를 얹는 것

### 5. Product/Detail Highlight

제품/디테일 설명은 실제 사진의 디테일을 더 잘 보이게 할 때만 사용한다.

허용:

- 문틀/댐퍼/레일 등 디테일 컷의 약한 scan
- frame line trace는 1회만
- magnifier는 실제 디테일을 가리지 않는 경우만

금지:

- 동그라미+화살표
- 손그림 스티커
- 사진 중앙을 가리는 큰 설명 카드
- 실제 근거 없는 기능 수치

## 금지 효과 목록

아래 효과는 문장군 릴스 기본 엔진에 넣지 않는다.

```text
손그림 화살표
움직이는 동그라미 포인터
랜덤 스티커
먼지/소음/냄새 웨이브 과장
전 화면 반짝이 남발
큰 카드형 장식 오버레이
모든 컷의 flash/glow
자막보다 튀는 효과음
출처 불명 BGM/SFX
```

## SFX/BGM 기준

오디오 우선순위:

```text
나레이션 > 필수 SFX > BGM
```

SFX는 80~300ms의 짧은 cue만 허용한다. 문장 첫 음절과 겹치지 않고, 컷 직전 80~120ms 또는 자막 등장 직후 0~80ms 안에서만 사용한다.

BGM은 나레이션을 가리면 실패다. 최종 믹스 기준은 아래를 초안으로 둔다.

```text
target loudness: -16 LUFS integrated
true peak: -1 dBTP 이하
ducking: 나레이션 구간 -12~-18dB
attack: 40~80ms
release: 350~700ms
```

라이선스 허용:

- CC0
- Pixabay
- Mixkit
- YouTube Audio Library 중 attribution 불필요 또는 조건 명확한 것

금지:

- CC BY-NC
- CC BY-ND
- 출처 불명 "No copyright music"
- 플랫폼 내부 전용 음원
- 상업 사용 조건이 불명확한 효과음

## 자동화 규칙

신규 릴스 생성 시 recipe는 아래 항목을 명시해야 한다.

```json
{
  "motion_rule_version": "munjanggun_motion_rule_v1",
  "caption_delay_sec": 0.0,
  "transition_reason": "sentence_end | phase_change | proof_reveal",
  "effect_intensity": "none | low | medium",
  "caption_protect": true,
  "review_capture_protect": true,
  "sfx_policy": "disabled | narration_safe"
}
```

검수 기준:

- 음성보다 화면/자막이 먼저 가면 실패
- 한 장면 CPS 9.0 초과 실패
- 자막 3줄 이상 기본 실패
- 리뷰 캡처를 가리는 효과 실패
- 효과가 기억나고 리뷰 내용이 기억나지 않으면 실패

## 105 파일럿 기준

105 테스트는 새 효과를 넣지 않는다. 기존 HTML을 복제하고 아래만 다듬는다.

- flash/glow 줄이기
- problem shake 줄이기
- caption delay를 안정적으로 적용
- 리뷰 캡처 장면의 자막을 위쪽/작게 정리
- 디테일 장면은 과한 오버레이보다 사진 자체를 더 잘 보이게 처리

목표는 "화려해졌다"가 아니라 "덜 조잡하고 더 편집자가 만진 것 같다"이다.
