# 문장군 리뷰 릴스 엔진 운영 지침

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

## 필수 제작 순서

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
python -m video_engine_v2.reels_qa --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --sync-manifest-out "<sync_manifest.json>"
```

공식 HyperFrames 파일럿 생성:

```powershell
node scripts/recipe-to-hyperframes-pilot.mjs --recipe "<edit_recipe.json>" --out "scratch/hf-pilot-<review-id>"
```

이 명령은 production 렌더러가 아니라 공식 HyperFrames Studio 검수용 파일럿입니다.
`sync_manifest.ok: true`, `final_voice_duration_sec`, beat별 `meaning_match: true`가 없으면 실패해야 합니다.

공식 HyperFrames 검수:

```powershell
cd "scratch/hf-pilot-<review-id>"
npm run check
npm run dev
```

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
