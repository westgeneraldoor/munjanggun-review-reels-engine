# 리뷰 릴스 포맷 상태 v1

> 기준일: 2026-07-28
> 목적: production 포맷과 검증 전 실험을 분리해 제작·승인 gate의 해석을 고정한다.

## 현재 분류

- v2: current production
- v3: experimental
- v3.1: experimental

Instagram과 Naver Clip은 모두 지원 대상 채널이다. 채널이 달라도 공통 안전·제작 엔진을 사용하고, 차이는 channel preset 또는 adapter로만 표현한다. 어느 채널도 v3 또는 v3.1을 자동으로 요구하지 않는다.

| 포맷 | 상태 | 현재 역할 | 검증 상태 |
| --- | --- | --- | --- |
| v2 | current production | 승인된 리뷰 기반 HTML·MP4 제작 경로 | 공식 `produce_review_v2.py` hard gate 적용 |
| v3 | experimental | 남성 1인칭 정보형의 리듬·전문성 가설 검증 | 성과 검증 전, production 대체 아님 |
| v3.1 | experimental | 잔잔한 사진형의 체류·가독성 가설 검증 | 성과 검증 전, production 대체 아님 |

## 실험 가설

- v3은 1인칭 남성 정보형, 짧은 자막, 빠른 컷이 검색·비교 맥락에서 이해와 시청 유지에 어떤 영향을 주는지 확인하는 실험이다.
- v3.1은 사진을 너무 자주 교체할 때 생기는 점멸을 줄이고, 더 긴 사진 모션과 차분한 전개가 가독성과 시각적 피로에 어떤 영향을 주는지 확인하는 별도 실험이다.
- 두 포맷 모두 실제 게시·성과 기록이 개별 근거로 연결되기 전에는 우열이나 전환 효과를 주장할 수 없다.

## 안전 경계

- v2 production 규칙, 특히 기획·HTML·MP4 승인, privacy, review-source, sync, D-026 의미 일치 gate는 별도 사용자 결정 없이는 바꾸지 않는다.
- experimental 산출물은 production 오케스트레이터에 연결하지 않으며, production MP4로 렌더하거나 외부 발행으로 해석하지 않는다.
- 실험에서 발견한 개선 후보는 근거·QA·사용자 결정을 거친 뒤에만 v2 규칙 변경안으로 제안할 수 있다.
- 기존 v2/v3/v3.1 패키지와 비교 결과는 보존한다. 삭제·일괄 이름 변경·자동 migration은 하지 않는다.

## HyperFrames 현황

현재 저장소에는 recipe 기반 HyperFrames Studio 파일럿과 gate-protected render 도구가 있다. 이는 검수·실험 경로이며, v2 production renderer를 대체하거나 HyperFrames를 production으로 승격했다는 뜻이 아니다. 현재 production은 v2의 공식 오케스트레이터이고, HyperFrames의 변경은 별도 승인 대상이다.
