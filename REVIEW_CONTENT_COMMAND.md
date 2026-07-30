# REVIEW_CONTENT_COMMAND.md — 리뷰 콘텐츠 신규 제작 트리거

## 현재 라우팅 경계

이 문서는 일반 review-content 흐름을 위한 문서다. `리뷰 릴스 만들자`,
`리뷰릴스 제작하자`, `리뷰 하나 골라서 폴더 만들어줘`,
`사진 다 넣었어요 HTML까지 가자`처럼 띄어쓰기·어미가 달라도 항상
`review_reel_production`으로 라우팅한다. 이 문서의 dashboard 후보를 임의 제작
package로 사용하지 않으며, 선택된 material-bank record는 반드시 공식 adapter로
등록한다. 현재 권한과 공식 CLI는
`docs/review_reel_production_routing_v1.md`의 `scripts/review_reel_intake.py`를 따른다.
`CAND-*`는 source metadata에서만 보존하며 user-facing package/이미지 폴더 이름이 될 수 없다.

이 문서는 신규 세션에서 한 줄 명령으로 리뷰 콘텐츠 제작 워크플로우를 시작하기 위한 운영 규칙이다.

## 한 줄 명령

사용자는 아래 중 하나만 입력해도 된다.

```text
리뷰컨텐츠 신규 만들어줘
```

```text
리뷰패키지 새로 만들어줘
```

```text
신규 리뷰 콘텐츠 골라서 만들어줘
```

영상/릴스까지 만들겠다는 의미의 아래 명령은 `docs/review_video_publish_workflow_v2.md`를 우선 따른다.

```text
리뷰 릴스 만들자
```

```text
리뷰 영상 신규 발행하자
```

```text
리뷰 릴스 신규 발행하자
```

## AI 작업자 행동

이 명령을 받으면 바로 생성하지 않는다.
먼저 후보를 보고, 사장님이 선택할 수 있게 제안한다.

## 반드시 먼저 읽을 파일

1. `GEMINI.md`
2. `docs/reels_operations_dashboard_v1.md`
3. `PROJECT_DASHBOARD.md`
4. `REVIEW_INTAKE_CHECKLIST.md`
5. `CONTENT_QUALITY_STANDARD.md`
6. `POSTING_COPY_STANDARD.md`
7. `reviews/pilot/README.md`
8. 최신 운영 리뷰 묶음의 `README.md`
   - 예: `reviews/inbox_20260609/README.md`

## 리뷰 추가 요청을 받았을 때

사용자가 리뷰 묶음을 주면 `REVIEW_INTAKE_CHECKLIST.md`를 따른다.

리뷰 추가 작업의 완료 기준은 아래 전체가 끝나는 것이다.

```text
원문 파싱
중복 검사
1리뷰 1파일 저장
읽기 좋은 줄바꿈 정리
1차 채점
상위 후보 선별
배치 기록
PROJECT_DASHBOARD.md 갱신
live package state 재스캔
PROJECT_TASKS.md 갱신
무결성 검증
```

파일만 나누고 끝내면 미완료다.

## 기본 후보 폴더

가장 최근 운영 리뷰 묶음을 우선 본다.

예:

```text
reviews/inbox_20260609/
```

`reviews/pilot/`은 레퍼런스/파일럿용이다.
정식 운영 콘텐츠 후보는 최신 `reviews/inbox_*` 폴더에서 고른다.

## 1단계 — 후보 선별

최신 운영 리뷰 폴더의 `.txt` 파일을 읽고, 사연성이 좋은 후보 3개를 고른다.

평가 기준:

- 사건이 있는가
- 불편/갈등이 체감되는가
- 전후 변화가 선명한가
- 반전 포인트가 있는가
- 사진 매칭 가치가 있는가
- 릴스 첫 3초 HOOK이 나오는가

## 2단계 — 사용자에게 선택 요청

아래 형식으로만 먼저 보고한다.

```text
리뷰 후보 3개 골라봤습니다.

1. 010_구축소음
   - 방향: 구축 빌라 현관 소음/냄새 탈출 사연
   - HOOK 후보: "구축 빌라 현관 소음 지옥, 드디어 해방됐습니다"
   - 강점: 불편이 선명하고 전후 변화가 큼

2. 005_여름에어컨
   - 방향: 좁아 보일까 망설였는데 여름 냉방 때문에 후회한 사연
   - HOOK 후보: "좁아 보일까 미뤘는데, 여름에 바로 후회했습니다"
   - 강점: 계절 공감과 후회 포인트가 좋음

3. 003_자동중문
   - 방향: 자동 중문 처음 써보고 손님마다 놀란 사연
   - HOOK 후보: "손님들이 처음 본다며 놀란 자동 중문"
   - 강점: 반응/반전 포인트가 있음

어떤 걸로 만들까요?
번호로 골라주세요.
```

사용자의 리뷰 선택만으로는 `generate.py`를 실행하지 않는다. 사진검수와 PD 기획안
승인이 끝나고, 현재 리뷰에 결속된 로컬 approval package가 준비되어야 한다.

## 사진 완료 후 one-shot HTML 요청

사용자가 사진 검수 완료 뒤 `사진 다 넣었어. HTML까지 가자` 또는 같은 뜻의 명시적
문구를 말하면, 리뷰 릴스의 **HTML preflight와 HTML 프리뷰**에는 별도 PD 기획 승인 대신
one-shot 계약을 사용할 수 있다. 이 문구는 MP4 승인이나 `generate.py`의 script/SRT/TTS
승인을 뜻하지 않는다.

진행 전 `docs/review_reels_one_shot_contract_v2.md`를 읽고, planning recipe에
`review-reels-one-shot-v2`, `html_scope_authorized: true`,
`mp4_scope_authorized: false`를 기록한다. 사진/개인정보/원문 근거/실제 리뷰 캡처/음성
동기화/자막 QA가 모두 통과한 경우에만 아래 공식 진입점을 사용한다.

```powershell
python scripts/produce_review_v2.py preflight --package "<output review package>" --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --privacy-manifest "<privacy_asset_manifest.json>" --sync-manifest "<output review package>/sync_manifest.json" --one-shot-html
python scripts/produce_review_v2.py html --package "<output review package>" --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --privacy-manifest "<privacy_asset_manifest.json>" --sync-manifest "<output review package>/sync_manifest.json" --one-shot-html
```

실패 시에는 HTML을 만들지 않고, 실제 고객 자료 부재나 미해결 개인정보 위험처럼 진행을
막는 사실만 보고한다. 훅·카피·컷 순서는 one-shot QA가 강제한다. MP4는 기존의 HTML
승인과 별도 명시적 MP4 승인 뒤에도 공식 `render` 명령으로만 진행한다.

## 3단계 — 사진검수·PD 승인 후 패키지 생성

승인 package에는 현재 리뷰와 일치하는 `.source`, `photo_checked: true`와
`pd_plan_approved: true`가 기록된 `STATUS.md`, 긍정적 PD 승인 범위가 기록된
`APPROVAL_LOG.md`가 이미 있어야 한다. 작업자가 승인 기록을 임의로 만들면 안 된다.

```powershell
$env:PYTHONPATH='.codex_deps'; & 'C:\Users\hjh\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' generate.py --input reviews\inbox_YYYYMMDD\선택파일.txt --approval-package "<승인된 로컬 package>" --with-tts
```

`python`이 정상 동작하면 아래처럼 실행해도 된다.

```powershell
python generate.py --input reviews\inbox_YYYYMMDD\선택파일.txt --approval-package "<승인된 로컬 package>" --with-tts
```

## 4단계 — 생성 후 보고

생성 후에는 아래만 짧게 보고한다.

```text
완료했습니다.

생성 폴더:
output/inbox_YYYYMMDD/010_구축소음_YYYYMMDD_HHMMSS

파일:
- 010_구축소음_script.md
- 010_구축소음_subtitle.srt
- 010_구축소음_voice.mp3

음원 길이:
- 31.25초

확인 포인트:
- script.md에 review_number/product_order_number 포함됨
- TTS는 리뷰2 레퍼런스 속도 기준
- 내용 길이에 맞춰 음원 길이는 자연스럽게 달라질 수 있음
```

## 절대 금지

- 후보 제안 없이 바로 생성 금지
- 품질 기준 충족용으로 얕게 생성 금지. `CONTENT_QUALITY_STANDARD.md` 기준으로 실제 발행 가능한 수준이어야 함
- 음원 길이에 맞추려고 내레이션 내용 삭제 금지
- `caption.txt`, `hashtag.txt` 별도 생성 금지
- 캡션/해시태그 누락 금지. 반드시 `*_script.md` 안에 `## 캡션`, `## 해시태그` 섹션으로 포함
- `reviews/pilot/`을 정식 운영 후보로 우선 선택 금지
- output 루트에 직접 저장하도록 구조 변경 금지
