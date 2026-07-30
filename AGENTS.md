# 문장군 리뷰 릴스 엔진 운영 지침

## 신규 세션 단일 권위 경로 (현재)

리뷰 릴스 요청은 먼저 `docs/review_reels_one_shot_contract_v1.md`와 `docs/brand/BRAND_SOURCE.md`를 읽는다. 이 두 문서는 아래의 구형 다단계 승인 문구와 충돌할 때 리뷰 릴스 신규 세션에 우선한다.

- 리뷰 번호는 대상 선택이다.
- `018 사진 다 넣었어. HTML까지 가자` 또는 같은 의미의 명시는 사진검수→기획→대본→최종 TTS→SRT/recipe→QA→HTML 프리뷰의 일괄 승인이다. 사소한 PD 선택을 다시 묻지 않는다.
- 실제 원문/사진 부재 또는 해결되지 않은 개인정보 위험만 중단 사유다.
- MP4는 이 명령에 포함되지 않는다. `렌더 승인` 같은 별도 명시 승인과 `STATUS.md`/`APPROVAL_LOG.md`의 긍정 기록 없이는 어떤 렌더 경로도 MP4를 만들 수 없다.
- 신규 HTML은 `python -m video_engine_v2.reels_qa ... --require-one-shot-contract`와 `python build_html_preview_v2.py --planning ... --recipe ...`를 통해서만 만든다.

현재 기본 MP4 경로는 게이트가 붙은 `render_html_preview_v2.js`다. HyperFrames는 `docs/hyperframes_official_adoption_plan_v1.md`의 Studio pilot/검토 표면이며 Stage 1/2 adapter를 production renderer라고 부르지 않는다.

이 저장소는 문장군 고객 리뷰를 기반으로 인스타그램 릴스용 기획, 대본, SRT, TTS, HTML 프리뷰, MP4 렌더를 만드는 엔진입니다.

신규 Codex 세션은 작업 전에 이 파일을 먼저 읽고, 아래 하드 게이트를 지켜야 합니다.

## GitHub Commit 금지

아래 항목은 GitHub에 절대 커밋하지 않습니다.

- `.env`
- `reviews/`
- `output/`
- 고객 사진, 리뷰 캡처, 현장 영상, 음성, MP4
- ZIP/MP3/WAV/JPG/PNG/MP4 등 미디어 파일
- 로컬 폰트 파일
- `node_modules/`, `.codex_deps/`

GitHub는 엔진 코드, 문서, 테스트만 관리합니다. 실제 고객 자료와 렌더 결과물은 로컬 산출물로만 관리합니다.

## 승인 게이트

- 리뷰 번호 지정은 제작 대상 승인일 뿐입니다.
- 사진검수 전 script/SRT/TTS/HTML 생성 금지.
- PD 기획안 승인 전 script/SRT/TTS/HTML 생성 금지.
- HTML 승인 전 MP4 렌더 금지.
- MP4 렌더는 사용자의 명시적 승인 후에만 진행합니다.
- 최종 MP4는 GitHub에 커밋하지 않습니다.

## 총괄 PD 팀 운영 방식

신규 세션은 혼자 빠르게 산출물을 만드는 생성기가 아니라, 아래 내부 팀 관점으로 검토한 뒤 진행해야 합니다.

- 총괄 PD: 콘텐츠 철학, 후킹, 사건성, 사용자 승인 게이트를 최종 판단합니다.
- 리뷰 각색 작가: 원문 리뷰에서 갈등, 불편, 후회, 고민, 놀람, 감동을 찾아 사건 중심 대본으로 바꿉니다.
- 사진 큐레이터: 사진/영상의 역할, 개인정보 위험, 리뷰 내용과의 일치 여부를 먼저 검수합니다.
- 편집 설계자: 음성, 자막, 화면 전환, 사진 무빙, 리뷰 캡처 노출 타이밍이 같은 의미 단위로 움직이는지 설계합니다.
- QA 감시자: 원문 왜곡, 과장 표현, 싱크, 줄바꿈, 자막 크기, 렌더 해상도, 개인정보 노출을 끝까지 물고 늘어집니다.

작업 중 판단이 흔들리면 반드시 이 순서로 자문합니다.

1. 이 콘텐츠는 고객의 문제와 사건에서 출발하는가?
2. 원문 리뷰가 실제로 말한 것만 사용했는가?
3. 사진과 자막과 음성이 같은 순간에 같은 이야기를 하는가?
4. 고객 개인정보나 가족 얼굴 등 가려야 할 것이 남아 있지 않은가?
5. 지금 만든 결과가 사용자가 HTML로 검수할 수 있는 단계인가, 아니면 아직 내부 수정 단계인가?

## 필수 제작 순서

모든 제작 판단은 먼저 `docs/munjanggun_content_operating_principles_v1.md`를 따릅니다.

문장군 콘텐츠는 중문을 설명하는 콘텐츠가 아니라 고객의 문제와 사건을 보여주는 콘텐츠입니다.

1. 리뷰 원문 확인
2. 사진/영상 소스 확인
3. 개인정보 위험 검수
4. 사진 역할 매핑
5. 리뷰 각색 작가 브리프 작성
6. PD 기획안 작성
7. 사용자 기획 승인
8. script/SRT/TTS 생성
9. planning_recipe/edit_recipe 생성
10. `reels_qa` 통과
11. HTML 프리뷰 생성
12. 사용자 HTML 검수
13. 사용자 MP4 렌더 승인
14. 최종 MP4 렌더
15. ffprobe/대표 프레임/개인정보/싱크 QA

## 원문 왜곡 방지 게이트

리뷰 기반 릴스는 원본 리뷰를 배신하면 안 됩니다.

HTML 생성 전 planning_recipe에는 아래 메타데이터가 있어야 합니다.

- `review_source.text`
- `review_source.review_quote_for_proof`
- `review_source.inferred_fields`
- `review_source.unsupported_story_elements`

하드 실패 조건:

- `review_quote_for_proof`가 원문 리뷰에 실제 포함되어 있지 않음
- 원문에 없는 소음/냄새/먼지/반려동물/아이/공사난이도 소재를 실제 사건처럼 사용
- 원문에 없는 감정을 고객의 실제 감정처럼 사용
- 원문에 없는 90%, 100%, 완벽, 보장, 무조건, 완벽 차단 같은 강한 claim 사용
- `unsupported_story_elements`가 비어 있지 않음
- 추론이 필요한데 `inferred_fields`에 표시하지 않음

## QA 명령

HTML 생성 전:

```powershell
python -m video_engine_v2.reels_qa --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --sync-manifest-out "<sync_manifest.json>" --require-one-shot-contract
```

공식 HyperFrames 파일럿 생성:

```powershell
node scripts/recipe-to-hyperframes-pilot.mjs --recipe "<edit_recipe.json>" --out "scratch/hf-pilot-<review-id>"
```

Stage 2 장면 분리 파일럿:

```powershell
node scripts/recipe-to-hyperframes-pilot.mjs --recipe "<edit_recipe.json>" --out "scratch/hf-pilot-<review-id>-subcomp" --subcompositions
```

이 명령은 production 렌더러가 아니라 공식 HyperFrames Studio 검수용 파일럿입니다.
`sync_manifest.ok: true`, `final_voice_duration_sec`, beat별 `meaning_match: true`가 없으면 실패해야 합니다.

공식 HyperFrames 검수:

```powershell
cd "scratch/hf-pilot-<review-id>"
npm run check
npm run dev
```

공식 HyperFrames 렌더 게이트:

```powershell
node scripts/hyperframes-render-gate.mjs --project "scratch/hf-pilot-<review-id>" --package "<output review package>" --sync-manifest "<output review package>/sync_manifest.json" --out "<output review package>/<review-id>_final_render_YYYYMMDD_hyperframes_upload_10mbps.mp4"
```

위 명령은 기본적으로 dry-run이며 MP4를 만들지 않습니다.
사용자의 명시적 MP4 렌더 승인 후에만 `--render-approved`를 붙입니다.
생성된 HyperFrames 파일럿의 `npm run render` 직접 실행은 금지되며, 렌더는 반드시 `scripts/hyperframes-render-gate.mjs`를 통해서만 진행합니다.

렌더 후 QA 증거 생성:

```powershell
node scripts/render-post-qa.mjs --mp4 "<output review package>/<review-id>_final_render_YYYYMMDD_hyperframes_upload_10mbps.mp4" --package "<output review package>" --sync-manifest "<output review package>/sync_manifest.json"
```

이 명령은 최종 승인자가 아니라 증거 기록자입니다.
자동 검사 통과 후에도 `overall_status: manual_review_required`, `manual_review.status: pending` 상태로 남아야 하며, 총괄 PD가 대표 프레임의 개인정보/자막/싱크를 직접 확인해야 최종 완료입니다.

저장소 테스트:

```powershell
python -m unittest discover -s tests
```

GitHub PR 전:

```powershell
npm run validate
```

## 핵심 문서

- `README.md`
- `docs/munjanggun_content_operating_principles_v1.md`
- `docs/review_video_publish_workflow_v2.md`
- `docs/reels_operations_dashboard_v1.md`
- `docs/reels_writer_persona_v1.md`
- `docs/reels_hook_formula_v1.md`
- `docs/hyperframes_official_adoption_plan_v1.md`
- `docs/reels_privacy_asset_qa_rules_v1.md`
- `docs/render_qa_rules_v2.md`
- `docs/github_pr_workflow.md`
- `docs/construction_reels_system_transfer_20260616.md`

## 최종 책임

자동화가 늘어도 최종 책임은 총괄 PD에게 있습니다.

작가, 사진 큐레이터, 편집 설계자, QA 감시자 역할은 품질을 끌어올리기 위한 내부 팀 구조이며, 최종 판단은 총괄 PD가 합니다.
