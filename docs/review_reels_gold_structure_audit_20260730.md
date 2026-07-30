# 리뷰 릴스 골드 구조 감사 (비식별)

> 범위: 로컬 골드 MP4·edit recipe·final script의 읽기 전용 구조 분석. 고객 원문, 고객 사진, 리뷰 문구, 식별정보는 이 문서에 복제하지 않는다.

## 관찰 사실

| 표본 | MP4/recipe 구조 | 관찰된 편집 역할 |
| --- | --- | --- |
| Gold A | 26.983초, 8 beats, 8개의 고유 asset role, review capture 1회 | 사건 시각 증거에서 시작해 현장 판단·시공·완성 결과·리뷰 증명·CTA로 이동 |
| Gold B | 22.997초, 7 beats, 7개의 고유 asset role, review capture 1회 | 생활 불편 훅 뒤 맥락·전환·결과를 짧게 연결하고 리뷰 증명 뒤 완성컷으로 착지 |
| 설명형 비교 A/B | 각 6 beats, 각 5개의 고유 asset role, review capture 1회 | 동일 asset 재사용과 설명 비중이 상대적으로 높아 사건/전환 역할을 구조적으로 명시할 필요가 있음 |

두 gold final script는 모두 `HOOK → SCENE → CONFLICT → SOLUTION → TWIST → CLOSE` 여섯 단계를 갖고, 캡션·해시태그 섹션을 script 안에 포함한다. 두 gold MP4는 H.264 1080x1920 30fps 영상과 AAC 음성을 가진다.

## 구현 반영

이 감사는 개별 문구나 사진을 복제하지 않고 아래 구조 계약으로만 반영했다.

- 8개 서사 역할: event, problem, context, choice_turn, resolution, felt_result, review_proof, cta
- 첫 훅의 실제 고객 사진 근거와 사진 QA
- 같은 사진의 장기 반복 filler 차단
- 가짜 카드 대신 `actual_review_capture` 한 번의 리뷰 증명
- 리뷰 증명 이후 완성컷/CTA
- 최종 음성 중심의 timing/hash 증거와 자막이 음성보다 앞서지 않는 검사
- 1~2줄 자막, 안전영역·피사체 가림·강조어 밀도 증거

이 값들은 새 코드 fixture의 비식별 예시로만 회귀 테스트한다. gold 고객 파일을 Git에 복사하거나 test fixture로 쓰지 않는다.
