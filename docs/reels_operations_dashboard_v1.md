# 문장군 리뷰 릴스 운영 대시보드 v1

> 범위: 이 문서는 관측 dashboard다. 신규 제작의 라우팅·후보 선택·package 이름은
> `docs/review_reel_production_routing_v1.md`와 `scripts/review_reel_intake.py`가
> 결정하며, 이 문서의 후보 표나 과거 메모는 이를 대체하지 않는다.

마지막 운영 원칙 갱신: 2026-07-28

이 문서는 신규 세션에서 `리뷰 릴스 만들자`라고 했을 때 가장 먼저 보는 릴스 운영 현황판입니다.
`PROJECT_DASHBOARD.md`가 전체 프로젝트 현황판이라면, 이 문서는 **인스타 릴스 제작/발행 관제판**입니다.

## 현재 운영 상태

| 항목 | 상태 |
|------|------|
| 운영 명령 | `리뷰 릴스 만들자` |
| 기준 워크플로 | `docs/review_video_publish_workflow_v2.md` |
| 최종 렌더 기준 | `docs/render_qa_rules_v2.md` |
| 캡션/해시태그 기준 | `docs/instagram_caption_hashtag_rules_v2.md` |
| 소재 개인정보 기준 | `docs/reels_privacy_asset_qa_rules_v1.md` |
| 작가 페르소나 | `docs/reels_writer_persona_v1.md` |
| HTML 전 공식 preflight | `python scripts/produce_review_v2.py preflight --package ... --planning ... --edit ... --privacy-manifest ... --sync-manifest ...` |
| 정식 리뷰 원본 | `reviews/inbox_20260609/` |
| live package state 원본 | `python -m video_engine_v2.package_state --output-root "<output root>" --report "<outside-output>/package-state.json"` |
| published / performance | 증거 장부가 없으면 `unknown`; 수동 숫자로 추정하지 않음 |
| 과거 사진 투입 기록 | `docs/archive/README.md` (현재 제작 상태로 사용 금지) |
| 최종 MP4 스펙 | 1080x1920 / 30fps / 약 9~10Mbps / AAC 44.1kHz stereo 192k |

## Live package state

### Routing boundary

This dashboard is an observation aid and **not a routing authority**. New
review-reel sessions must use `docs/review_reel_production_routing_v1.md` and
`scripts/review_reel_intake.py`; historic candidates, `CAND-*` identifiers, and
archive notes cannot select or name a new production package.

이 문서는 수동 완료 목록이나 발행·성과 숫자의 진실 원본이 아닙니다. 숫자 package,
upload MP4 artifact, render QA, published, performance는 매 세션 위
`package_state.py` read-only scan 결과로만 판단합니다. 2026-07-28 read-only
snapshot에서도 published와 performance는 증거 부족으로 `unknown`이며, 사용자가
약 12편 이상 게시했다고 기억해도 장부 없이 true/false로 바꾸지 않습니다.

scan summary의 `upload_mp4_package_count`와 `upload_mp4_artifact_count`는 파일 존재
숫자이고, `post_render_qa_pass_evidence_package_count`는 과거 `auto_status: pass`
기록 숫자입니다. `render_complete_true_count`는 현재 MP4의 package-relative path,
bytes, SHA-256까지 QA report와 일치한 경우만 셉니다. hash 없는 legacy QA pass는
`render_complete_unknown_count`와 `render_evidence_limitation_count`로 남으며, 기존
upload MP4 package를 삭제하거나 자동 재렌더 대상으로 해석하지 않습니다.

`video_engine_v2.reels_qa`는 internal diagnostic module이고, production
산출물 생성은 `scripts/produce_review_v2.py`만 사용합니다.

## 다음 제작 후보

아래 후보 표는 과거 기획 메모이며 package completion, published, performance의
live 원본이 아닙니다. 신규 세션은 package state scan과 리뷰 원문·사진 상태를
우선합니다.

| 우선순위 | ID | 리뷰 파일 | 점수 | 추천 목적 | 예상 훅 방향 | 필요한 사진 |
|----------|----|-----------|------|-----------|--------------|-------------|
| 1 | 033 | `033_소음차단냄새먼지.txt` | 12 | 전환형 / 문제해결형 | 소음·냄새·먼지까지 들어오는 현관이라면? | 시공전, 시공후, 현관/복도, 리뷰캡처, 상품썸네일 |
| 2 | 114 | `114_반려동물소음차단.txt` | 11 | 공감/신뢰형 | 반려동물 있는 집, 현관 소리까지 신경 쓰였다면? | 반려동물 맥락 사진 가능하면 좋음, 시공전후, 리뷰캡처 |
| 3 | 098 | `098_소음차단냄새먼지.txt` | 12 | 구축/전환형 | 구축 현관, 소음보다 냄새가 더 힘들었다면? | 구축 현장감, 시공전후, 실측, 리뷰캡처 |
| 4 | 034 | `034_친절상담깔끔시공.txt` | 12 | 신뢰형 | 상담부터 시공까지 마음 놓였던 이유 | 상담/실측/시공 디테일, 리뷰캡처 |
| 5 | 025 | `025_소음차단구축리모델링.txt` | 11 | 구축 전환형 | 오래된 집 현관 소리, 중문으로 달라질까? | 구축 현장, 시공전후, 실측, 리뷰캡처 |
| 6 | 105 | `105_냄새먼지친절상담.txt` | 11 | 신뢰/배려형 | 먼지 날릴까 봐 유아차까지 옮겨준 시공팀 | 시공전후, 현관 짐/유아차 맥락, 시공 디테일, 리뷰캡처 |

## 2026-06-15 보충 후보 5개

| 우선순위 | ID | 리뷰 파일 | 점수 | 추천 목적 | 예상 훅 방향 | 사진 폴더 |
|---:|---|---|---:|---|---|---|
| 1 | 100 | `100_층간소음구축리모델링.txt` | 9 | 전문성/난이도 | 중문 두 곳에 방문 교체까지, 쉬운 현장이 아니었습니다 | HTML 완료: `100_층간소음구축리모델링_difficult_three_openings_v1_html_preview_v2/` |
| 2 | 115 | `115_구축리모델링이사중문.txt` | 9 | 구축/현장제약 | 벽도 천장도 반듯하지 않은 구축집, 가벽까지 세워 맞췄습니다 | HTML 완료: `115_구축리모델링이사중문_crooked_gapwall_v1_html_preview_v2/` |
| 3 | 116 | `116_친절상담기사칭찬.txt` | 10 | 가격비교/마감신뢰 | 저렴한 곳보다, 결국 마감이 중요했습니다 | HTML 완료: `116_친절상담기사칭찬_top_finish_trust_v1_html_preview_v2/` |
| 4 | 036 | `036_냄새먼지깔끔시공.txt` | 11 | 방문교체/생활불편 | 물에 불어버린 욕실문, 그냥 둘 수 없었습니다 | HTML 완료: `036_냄새먼지깔끔시공_damp_bathroom_door_v1_html_preview_v2/` |
| 5 | 088 | `088_소음차단냄새먼지.txt` | 11 | 종합 전환형 | 답답한 중문은 싫고, 냉기와 소음은 막고 싶다면? | HTML 완료: `088_소음차단냄새먼지_open_privacy_noise_cold_v1_html_preview_v2/` |

## 릴스 제작 칸반

칸반의 현재 대상·완료 표시는 수동 상태를 유지하지 않습니다. 신규 세션은 live
package state scan으로 package를 확인한 뒤 사진/승인/QA 증거에 따라 다음 액션을
결정합니다.

## 신규 세션에서 Codex가 먼저 할 일

`리뷰 릴스 만들자` 요청을 받으면:

1. 이 문서와 `docs/review_video_publish_workflow_v2.md`를 읽습니다.
2. live package state scan에서 같은 review ID의 package와 증거를 확인해 중복 제작을 막습니다.
3. 다음 후보 033, 114, 098을 먼저 제안합니다.
4. 사용자가 특정 리뷰 번호를 말하면 후보 제안보다 해당 리뷰 확인을 우선합니다. 단, 번호 지정은 HTML 제작 승인이 아닙니다.
5. 리뷰 패키지의 `STATUS.md`와 `APPROVAL_LOG.md`를 먼저 확인합니다. 없으면 생성하고 `mp4_allowed: false`로 둡니다.
6. 리뷰 패키지 폴더와 이미지 폴더를 먼저 만들고, 사용자가 사진을 넣을 경로를 안내합니다.
7. 사진이 들어오기 전에는 HTML/MP4 제작을 시작하지 않습니다.
8. 사진이 들어오면 사진검수/역할매핑/부족 컷/개인정보 위험 분석을 합니다.
9. `docs/reels_writer_persona_v1.md` 기준으로 작가 브리프를 작성합니다.
10. 훅 후보/PD 기획안/scene 의미 일치 계획표까지만 먼저 작성합니다.
11. 사용자 기획 승인 전에는 script/SRT/TTS/HTML을 생성하지 않습니다.
12. HTML 생성 전 `scripts/produce_review_v2.py preflight`를 통과해야 합니다. privacy report/manifest/asset hash 결속이 없으면 실패입니다.
13. HTML 승인 전에는 최종 MP4를 렌더하지 않습니다.
14. 최종 MP4는 `*_upload_10mbps.mp4` 스펙과 현재 MP4·sync manifest 모두에 결속된
    post-render QA evidence가 함께 있을 때만 `render_complete`로 처리합니다. 과거 QA
    pass와 upload MP4 존재는 별도 상태입니다.
15. 마지막에 `*_script.md`의 캡션/해시태그까지 점검합니다.
16. 릴스 1건이 완료되면 package evidence를 남기고 다음 세션에서 live package state scan으로 다시 확인합니다.
17. 다음 후보군이 3개 미만으로 줄면 새 후보를 보충하고, 필요 시 사진 투입 폴더까지 미리 생성합니다.

## 사용자가 결정하는 지점

| 시점 | 사용자가 결정 | Codex가 제공 |
|------|---------------|--------------|
| 시작 | 리뷰 번호 선택 또는 후보 추천 요청 | 후보 3개와 추천 이유 |
| 사진 전 | 해당 리뷰 사진 준비 가능 여부 | 사진 넣을 폴더 경로 |
| 사진 후 | 부족 사진 추가 여부 | 사진 역할/부족 컷 분석 |
| 기획 | 훅/톤/목적/scene 의미 일치 계획 승인 | PD 기획안, 훅 후보, 사진 역할 매핑표 |
| HTML 후 | 수정 요청 또는 렌더 승인 | HTML 프리뷰 |
| 렌더 후 | 최종 피드백/발행 여부 | MP4 스펙, contact sheet, 캡션/해시태그 |

## 콘텐츠 계획 메모

초기 릴스 4개는 서로 다른 목적을 검증했습니다.

| 목적 | 대표 영상 | 향후 확장 |
|------|-----------|-----------|
| 계절/광고형 | 005 여름에어컨 | 여름 냉방, 겨울 우풍, 단열 |
| 구축 전환형 | 010 구축소음 | 소음, 냄새, 먼지, 복도식 |
| 신뢰/전문성 | 004 어려운시공 | 다른 업체 포기, 실측 난이도, 현장 대응 |
| 생활동선형 | 020 로봇청소 | 방문교체, 문턱, 아이/반려동물 동선 |

다음 5개는 같은 템플릿 복붙이 아니라 목적별 문법을 달리해야 합니다.

## 완료 기준

리뷰 릴스 1건은 아래가 모두 있어야 완료입니다.

- HTML 프리뷰
- 업로드용 MP4 `*_upload_10mbps.mp4`
- script.md
- SRT
- voice.mp3
- planning/edit recipe
- contact sheet
- 캡션/해시태그
- package evidence 및 다음 후보 판단 기록
- 다음 후보군 보충 여부 확인

## 완료 후 자동 운영 규칙

릴스 1건이 끝나면 Codex는 아래를 같은 턴에 처리해야 합니다.

1. 수동 완료 표나 수동 발행·성과 숫자를 이 문서에 추가하지 않습니다.
2. package의 approval/privacy/sync/post-render evidence를 보존하고 다음 세션에서 package state scan으로 다시 확인합니다.
3. 후보가 3개 미만이면 `PROJECT_DASHBOARD.md`와 점수표에서 미제작 A/B권 후보를 보충합니다.
4. 새 후보군이 확정되면 사용자가 바로 사진을 넣을 수 있도록 output 패키지 폴더와 `*_이미지` 폴더를 준비합니다.
5. 새 사진 폴더 안내 문서를 만들거나 기존 `docs/reels_photo_intake_YYYYMMDD.md`를 갱신합니다.
6. 완료·발행·성과 상태는 `_context.md` 같은 수기 세션 기록에 쓰지 않고 live package state를 다시 스캔합니다.

이 규칙 때문에 `리뷰 릴스 만들자` 워크플로는 한 건 제작 후에도 다음 제작 대기열이 끊기지 않아야 합니다.
