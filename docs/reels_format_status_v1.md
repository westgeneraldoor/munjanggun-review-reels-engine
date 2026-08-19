# 리뷰 릴스 포맷 상태 v1

> 기준일: 2026-07-28 (2026-08-19 갱신)
> 목적: production 포맷과 중단된 실험을 분리해 제작·승인 gate의 해석을 고정한다.

## 현재 분류

- v2: current production
- v3: discontinued (2026-08-19)
- v3.1: discontinued (2026-08-19)

Instagram과 Naver Clip은 모두 지원 대상 채널이다. 채널이 달라도 공통 안전·제작 엔진을 사용하고, 차이는 channel preset 또는 adapter로만 표현한다. 어느 채널도 v3 또는 v3.1을 요구하지 않는다.

| 포맷 | 상태 | 현재 역할 | 검증 상태 |
| --- | --- | --- | --- |
| v2 | current production | 승인된 리뷰 기반 HTML·MP4 제작 경로 | 공식 `produce_review_v2.py` hard gate 적용 |
| v3 | discontinued | 없음 | 성과 검증 전에 중단 |
| v3.1 | discontinued | 없음 | 성과 검증 전에 중단 |

## v3 / v3.1 중단 기록

v3은 1인칭 남성 정보형의 리듬·전문성 가설을, v3.1은 더 긴 사진 모션과 차분한 전개가 가독성에 주는 영향을 확인하려던 실험이었다.

두 실험 모두 **성과로 검증되기 전에 중단됐다.** 엔진 코드(`v3_html_preview.py`, `caption_splitter.py`, `v3_preview.html`, `v31_preview.html`, `build_074_v3.py`)는 한 번도 커밋되지 않은 채 임시 작업 폴더에만 있었고, 2026-08-19에 사용자 결정으로 폐기했다.

- 새 제작에서 v3 또는 v3.1을 요청하거나 복원하지 않는다.
- 이 문서가 이름을 남겨 두는 이유는 부활시키기 위해서가 아니라, 과거 패키지의 `v3` 표기를 읽을 수 있게 하고 같은 실험을 근거 없이 다시 시작하지 않기 위해서다.
- 다시 시도하려면 가설과 측정 방법을 먼저 정하고 사용자 결정을 받는다.
- v3.1이 확인하려던 차분한 전개는 이후 v2의 calm motion 어휘로 흡수됐다. `docs/review_reels_visual_edit_standard_v1.md`를 따른다.

## 안전 경계

- v2 production 규칙, 특히 기획·HTML·MP4 승인, privacy, review-source, sync, D-026 의미 일치 gate는 별도 사용자 결정 없이는 바꾸지 않는다.
- 중단된 포맷의 산출물은 production 오케스트레이터에 연결하지 않으며, production MP4로 렌더하거나 외부 발행으로 해석하지 않는다.
- 기존 v2/v3/v3.1 패키지와 비교 결과는 보존한다. 삭제·일괄 이름 변경·자동 migration은 하지 않는다.

## HyperFrames 현황

현재 저장소에는 recipe 기반 HyperFrames Studio 파일럿과 gate-protected render 도구가 있다. 이는 검수·실험 경로이며, v2 production renderer를 대체하거나 HyperFrames를 production으로 승격했다는 뜻이 아니다. 현재 production은 v2의 공식 오케스트레이터이고, HyperFrames의 변경은 별도 승인 대상이다.
