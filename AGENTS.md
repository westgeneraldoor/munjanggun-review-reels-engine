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

## 리뷰 릴스 one-shot HTML 범위

사용자가 사진 검수 완료 후 `사진 다 넣었어. HTML까지 가자`와 같은 명시적 문구를
사용하면, **리뷰 릴스에 한해** 별도 PD 기획 승인 없이 HTML preflight와 HTML 프리뷰까지
진행할 수 있습니다. 이 예외는 아래 조건을 모두 충족할 때만 적용합니다.

- 공식 `scripts/produce_review_v2.py`의 `preflight`와 `html` 양쪽에
  `--one-shot-html`을 붙인다. 내부 builder나 renderer를 직접 실행하지 않는다.
- one-shot의 SRT/TTS는 `scripts/generate_one_shot_tts.py`만 사용한다. 이 명령은
  canonical package가 공식 `photo-review`를 통과했고 planning recipe와 표준
  `*_script.md`의 내레이션이 정확히 같을 때만 Gemini TTS `Sulafat` 음성을 만든다.
  Windows SAPI, 임의 MP3, 수동 SRT는 production 증거로 인정하지 않는다.
- planning recipe의 `workflow_contract.name`은 `review-reels-one-shot-v2`,
  `html_scope_authorized: true`, `mp4_scope_authorized: false`여야 한다.
- `scripts/review_reel_intake.py photo-review`가 모든 사진의 use/hold/exclude 판단과
  privacy evidence를 결속해 canonical metadata를 `photo_reviewed`로 전환해야 한다.
  `STATUS.md` 수동 수정은 승인 증거가 아니다.
- 사진 검수, privacy manifest, 리뷰 원문 근거, 실제 리뷰 캡처, TTS/sync 및
  one-shot 구조 QA를 모두 통과해야 한다. 하나라도 실패하면 HTML을 만들지 않는다.
- 리뷰 캡처의 사용자 제공 구도와 해상도는 증거의 일부다. 본문만 crop·확대하거나 이미
  `**` 처리된 아이디를 다시 가리지 않고, 실제로 남은 주문번호 같은 식별 영역만 최소
  마스킹한다. `review_capture_integrity` 검사 실패 시 HTML을 만들지 않는다.
- 이 범위는 `generate.py`의 script/SRT/TTS 승인 게이트를 완화하지 않으며, MP4 권한도
  절대 포함하지 않는다. MP4는 기존 HTML 승인 및 별도 명시적 MP4 승인 기록이 계속 필요하다.

상세 계약과 실행 예시는 `docs/review_reels_one_shot_contract_v2.md`를 따른다.

## 리뷰 릴스 앞단 라우팅과 canonical intake

`리뷰 릴스 만들자`, `리뷰릴스 제작하자`, `리뷰 하나 골라서 폴더 만들어줘`,
`사진 다 넣었어요 HTML까지 가자`처럼 띄어쓰기·어미가 달라도
generic review-content/material-bank보다 항상 `review_reel_production`으로 먼저
라우팅한다. 상태 전이, local material bank adapter와 registry가 배정하는
`content_id`, package 이름, active pointer, one-shot 연결은
`docs/review_reel_production_routing_v1.md`와 `scripts/review_reel_intake.py`만 따른다.

`CAND-*`는 candidate/source reference metadata에만 남기며 package와 이미지 폴더 이름,
사용자-facing 제작 ID로 쓰지 않는다. 새 local package는 반드시 공식 intake CLI로만
만들고, 사진 전에는 script/SRT/TTS/HTML/MP4를 만들지 않는다. dashboard와
`docs/archive/` 기록은 현재 routing authority가 아니다.

기존 `candidate_top60_private.jsonl`을 production에 연결할 때는 임시 inventory JSON을
사람이나 AI가 꾸며내지 않는다. 공식 `create-from-material-bank` 명령이 실제
`candidate_id`, `inventory_id`, `order_id`, `review_id`, `review_text`를 읽고,
local-only source registry가 기존 번호를 스캔해 다음 미사용 세 자리 ID를 배정한다.
같은 candidate는 최초 배정을 재사용하며, 깨진 registry나 identity 변경은 덮어쓰지
않고 실패해야 한다.

후보를 신규 제작 대상으로 제시하거나 `create-from-material-bank`를 실행하기 전에는
반드시 공식 `candidate-check`를 먼저 실행한다. 새 source registry에 미배정이어도
과거 `CAND-*` legacy package가 남아 있으면 이미 사용한 후보이므로
`CANDIDATE_LEGACY_PACKAGE_PRESENT`로 차단하고, legacy 산출물은 수정하지 않는다.

Codex Git worktree에는 Git에서 제외된 `reviews/`·`output/`이 복제되지 않는다. 고객자료를
쓰는 production 세션은 저장된 로컬 프로젝트에서 실행하거나 사용자가 지정한 원본
`reviews`·`output`·material-bank 절대경로를 공식 CLI에 넣는다. worktree에 자료가 없다는
이유만으로 원본 부재를 단정하지 않는다. 셸 PATH에 `python`이 없으면 Codex 번들 workspace
dependency를 먼저 불러 그 Python 실행경로로 같은 공식 CLI를 실행하며 내부 모듈로 우회하지 않는다.

`릴스`, `숏폼`, `쇼츠`, `리뷰 영상`은 이 저장소에서 같은 review-reel 제작 의도로
라우팅한다. `HTML 승인. MP4 렌더도 진행해` 같은 문장은 승인 완료가 아니라
`html_approval_and_mp4_render_intent_requested`로만 분류하며, 실제 권한은 아래 공식
approval record가 현재 HTML 해시에 결속된 뒤에만 생긴다.

새 세션은 파일을 쓰기 전에 `review_reel_intake.py status --output-root "output"`으로
활성 `content_id`와 package를 확인합니다. `photo-review`와 `one-shot-html`에는 그 값을
`--expected-content-id`로 반드시 다시 넣습니다. 활성 pointer가 다른 리뷰를 가리키면
`ACTIVE_PACKAGE_CONTENT_ID_MISMATCH`로 파일을 읽기 전에 중단해야 합니다.
각 공식 명령이 끝난 뒤에는 `review_reel_intake.py workflow-next --output-root "output"`을
실행해 다음 합법 단계·필수 입력·승인 대기 여부를 확인합니다. 사진 검수 후에는
`recipe-scaffold`로 현재 QA와 동기화된 planning/edit 골격을 만들고, 오류 코드는
`explain-error --code "<CODE>"`로 해석합니다. scaffold의 `TODO`나 임시 voice hash가
남아 있으면 HTML preflight로 진행할 수 없습니다.

## 포맷 상태

- v2: current production
- v3: experimental
- v3.1: experimental

Instagram과 Naver Clip은 공통 안전·제작 엔진을 쓰는 지원 채널입니다. v3/v3.1은
각각의 가설을 검증하는 실험일 뿐 v2 production을 대체하지 않으며, D-026을 포함한
production gate를 바꾸지 않습니다. 상세 기준은 `docs/reels_format_status_v1.md`를
따릅니다.

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
5. 리뷰 각색 작가 브리프와 `story_mode` 작성
6. PD 기획안 작성
7. 사용자 기획 승인
8. script/SRT/TTS 생성
9. planning_recipe/edit_recipe 생성
10. `reels_qa` 통과
11. HTML 프리뷰 생성
12. Playwright 대표 프레임 자동 QA와 작업자 직접 시각 검수
13. 사용자 HTML 검수
14. 사용자 MP4 렌더 승인
15. 최종 MP4 렌더
16. ffprobe/대표 프레임/개인정보/싱크 QA

one-shot의 창작 기준은 `docs/review_reels_content_standard_v1.md`, 화면·모션 기준은
`docs/review_reels_visual_edit_standard_v1.md`를 따른다.
강조 pop은 chunk 시작 고정 지연이 아니라 강조 단어의 발화 시점에 결속하고, 첫 훅 뒤
본문 자막은 medium 크기를 유지합니다. 발음용 `삼 연동 중문`은 화면에서 공식 제품명
`3연동중문`으로 표시할 수 있으며 리뷰 밑줄은 장면 진입 즉시 짧게 그어져야 합니다.
자막 chunk는 음성의 문장 끝에서 함께 끊고 끝난 문장 뒤에 다음 문장 조각을 붙이지 않습니다.
완성→이전→완성 훅의 첫 3개 shot은 각각 하나의 완결된 음성·자막 주장과 같은 시간 경계를
사용하고, shot별 사진 근거와 해당 발화 조각을 `meaning_match_source`로 결속합니다.
`context`, `choice_turn`, 실측, 공정 설명은 고정 장면이 아니며 리뷰와 사진에 실제
근거가 있을 때만 넣는다. 공식 음성은 Gemini TTS `Sulafat`이며 Windows SAPI 등
임시 음성은 production HTML에 연결하지 않는다.

일반 승인 제작에서 `generate.py`를 사용하는 경우 `--approval-package`가 필수입니다.
사진검수 완료 뒤 사용자가 one-shot HTML을 명시 승인한 경우에만
`scripts/generate_one_shot_tts.py`가 별도 PD 승인 패키지 없이 SRT/TTS를 생성할 수
있습니다. 이 예외는 HTML 범위일 뿐 MP4 권한을 만들지 않습니다. 승인 패키지의
`.source`는 현재 리뷰와 일치해야 하고, `STATUS.md`의 `photo_checked`와
`pd_plan_approved`, `APPROVAL_LOG.md`의 긍정적 PD 기획 승인이 모두 확인되어야
합니다. 리뷰 번호 선택만으로 이 기록을 만들거나 승인으로 간주하면 안 됩니다.

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

v2 production의 유일한 공식 진입점은 아래 오케스트레이터입니다. 내부
`reels_qa`, HTML builder, renderer를 직접 호출해 gate를 우회하지 않습니다.

```powershell
# 0. one-shot HTML용 표준 SRT 및 Gemini/Sulafat 최종 음성 생성
python scripts/generate_one_shot_tts.py --package "<output review package>" --planning "<planning_recipe.json>" --script "<*_script.md>"

# 0.5. 실제 음성을 듣고 발음·톤·자막 싱크를 확인한 뒤 해시 결속 영수증 기록
python scripts/produce_review_v2.py voice-review-record --package "<output review package>" --voice "<voice.mp3>" --srt "<captions.srt>" --tts-report "<_work/tts_generation_report.json>" --reviewer "<reviewer>" --evidence-reference "<review evidence>" --check pronunciation_clear --check tone_approved --check caption_sync_approved

# 1. HTML/MP4 산출물 없이 sync manifest를 생성하는 preflight
python scripts/produce_review_v2.py preflight --package "<output review package>" --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --privacy-manifest "<privacy_asset_manifest.json>" --sync-manifest "<output review package>/sync_manifest.json"

# 2. preflight 통과 후 HTML preview 생성
python scripts/produce_review_v2.py html --package "<output review package>" --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --privacy-manifest "<privacy_asset_manifest.json>" --sync-manifest "<output review package>/sync_manifest.json"

# 2.5. 모든 beat와 0.5초·첫 3개 훅 대표 프레임을 직접 본 뒤 기록
python scripts/produce_review_v2.py html-review-record --package "<output review package>" --html "<html_preview>/index.html" --reviewer "<reviewer>" --evidence-reference "<review evidence>" --check hook_sequence_reviewed --check meaning_sync_reviewed --check caption_layout_reviewed --check privacy_reviewed --check review_capture_reviewed --check cta_reviewed

# 2.6. 사용자의 HTML 승인과 별도 MP4 렌더 승인을 각각 현재 HTML 해시에 결속
python scripts/produce_review_v2.py html-approval-record --package "<output review package>" --html "<html_preview>/index.html" --approved-by "<user>" --evidence-reference "<explicit HTML approval>"
python scripts/produce_review_v2.py render-approval-record --package "<output review package>" --html "<html_preview>/index.html" --approved-by "<user>" --evidence-reference "<explicit MP4 render approval>"

# 3. 두 승인이 기록된 뒤 독립 렌더 작업 시작 (`render` 직접 명령은 비활성)
python scripts/produce_review_v2.py render-start --package "<output review package>" --html "<html_preview>/index.html" --privacy-manifest "<privacy_asset_manifest.json>" --sync-manifest "<output review package>/sync_manifest.json" --out "<output review package>/<review-id>_final_render_YYYYMMDD_upload_10mbps.mp4"

# 4. 시작 명령이 반환한 job_id로 진행률/완료 증거 조회
python scripts/produce_review_v2.py render-status --package "<output review package>" --job-id "<job-id>"
```

preflight는 planning/edit/review_source/privacy/PD 승인/asset을 검증해
`sync_manifest.json`을 생성합니다. HTML과 MP4는 1080x1920, 30fps,
H.264/yuv420p, AAC 44.1kHz stereo, approved bitrate 외 설정으로 생성할 수
없고, 기존 MP4/frames를 덮어쓰지 않습니다.

에이전트 production 렌더는 호출 제한시간과 분리된 `render-start`만 사용합니다.
`render-status`의 상태가 `succeeded`이고 MP4 bytes/SHA-256이 기록되기 전에는 렌더
완료나 후속 QA 준비 완료로 보고하지 않습니다. `failed` 작업의 frame, receipt, log는
삭제하지 않으며 새 job ID와 새 출력 파일명으로만 다시 시작합니다.

HTML 생성이 끝나면 `*_html_preview_v2/html_artifact_evidence.json`이 자동으로
생기며, 정확한 `index.html` 경로와 SHA-256, HTML gate receipt hash, 그리고 실제
렌더 입력인 image/voice/engine font의 `kind`/`scope`/상대경로/bytes/SHA-256을
보관합니다. `sync_manifest.json`의 `gate_inputs.voice`도 voice 상대경로/bytes/SHA-256을
묶으므로 voice 내용이 바뀌면 기존 sync와 HTML 승인은 stale입니다.
사용자 HTML 승인은 package 루트의 새 `HTML_APPROVAL.json`에만 기록합니다. 이
파일은 `schema_version`, package identity, HTML relative path/SHA-256,
`approved_by_user: true`, `approved_at`, `approval_evidence_reference`, HTML
artifact evidence SHA-256을 모두 가져야 합니다. 따라서 approval은 HTML 파일만이
아니라 artifact evidence에 기록된 image/voice/font dependency hash 전체에 결속됩니다.
legacy의
`html_approved_by_user: true`만으로는 render를 승인하지 않습니다.
별도 MP4 승인도 공식 `render-approval-record`가 만든 `MP4_RENDER_APPROVAL.json`으로
현재 HTML과 `HTML_APPROVAL.json` 해시에 결속합니다. `STATUS.md`나 `APPROVAL_LOG.md`를
손으로 바꾼 것만으로는 렌더를 승인하지 않습니다.

공식 HTML 생성 직후 `scripts/html-preview-qa.mjs`가 모든 beat 대표 프레임과
`html_internal_qa_report.json`을 생성해야 합니다. 자동 검사가 통과해도
`manual_review.status: pending`입니다. 작업자는 `_qa_frames/`를 직접 확인한 뒤에만
사용자에게 `HTML 검수 준비 완료`라고 보고할 수 있습니다. 브라우저 접근이 안 되거나
대표 프레임을 보지 못했다면 `HTML 생성, 내부 시각 QA 대기`라고 보고하며 완료라고
말하지 않습니다.

HTML/render gate receipt는 일회용입니다. 내부 builder/renderer는 artifact 생성 직전
receipt 파일 SHA-256에 결속된 consumed marker를
`_work/production_gates/consumed/`에 원자적으로 기록합니다. 같은 receipt나 복사본을
다시 사용하면 실패해야 하며, receipt와 consumed marker는 삭제하면 안 되는 production
evidence입니다.

`privacy_asset_manifest.json`에는 `checked_at`, package 내부의
`sanitization_report`, 빈 `unresolved_risks`, 그리고 실제 사용 asset의 정확한
`relative_path`/`bytes`/`sha256`가 모두 있어야 합니다. asset 또는 manifest가
바뀌면 sync manifest는 stale이며 preflight부터 다시 실행합니다. 우회 flag는
없습니다.

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

표준 HTML 렌더 후 QA 증거 생성:

```powershell
python scripts/produce_review_v2.py post-render-qa --package "<output review package>" --job-id "<job-id>"
```

이 명령은 성공한 render job에서 MP4와 sync 경로를 직접 읽고 실제 report 경로를
반환합니다. 경로를 수동 조립하거나 package 루트의 고정 report 이름을 가정하지 않습니다.

HyperFrames 렌더 후 QA 증거 생성:

```powershell
node scripts/render-post-qa.mjs --mp4 "<output review package>/<review-id>_final_render_YYYYMMDD_hyperframes_upload_10mbps.mp4" --package "<output review package>" --sync-manifest "<output review package>/sync_manifest.json"

# 대표 프레임과 최종 영상의 자막·개인정보·리뷰 증거·음성 싱크를 직접 본 뒤 기록
python scripts/produce_review_v2.py render-review-record --package "<output review package>" --mp4 "<output review package>/<review-id>_final_render_YYYYMMDD_upload_10mbps.mp4" --post-qa-report "<post-render-qa가 반환한 report 경로>" --reviewer "<reviewer>" --evidence-reference "<review evidence>" --check caption_layout_reviewed --check privacy_reviewed --check review_capture_reviewed --check voice_caption_visual_sync_reviewed --check hook_and_cta_reviewed
```

이 명령은 최종 승인자가 아니라 증거 기록자입니다.
자동 검사 통과 후에도 `overall_status: manual_review_required`, `manual_review.status: pending` 상태로 남아야 하며, 총괄 PD가 대표 프레임의 개인정보/자막/싱크를 직접 확인해야 최종 완료입니다.
새 `render_post_qa_report.json`은 package identity와 대상 upload MP4 및 사용한 sync
manifest의 상대경로, bytes, SHA-256을 기록합니다. package state scan에서 과거
`auto_status: pass`는 `post_render_qa_pass_evidence_present`일 뿐이며, 현재 MP4와
현재 sync manifest가 모두 이 결속값과 일치할 때만 `render_complete: true`입니다.
이 값은 자동검사까지 결속된 기술 완료입니다. 별도 `render-review-record` 영수증이 현재
MP4·post-QA report·대표 프레임과 모두 일치해 `qa_reviewed: true`가 되고, 두 값이 같은
MP4에 대해 모두 참일 때만 `final_delivery_complete: true`로 최종 완성을 보고합니다.
hash가 없는 legacy pass 보고서는 `unknown`으로
남으며, 기존 upload MP4 package를 삭제하거나 재렌더 대상으로 해석하지 않습니다.
게시·성과는 별도 명시 증거가 없으면 계속 `unknown`입니다.

로컬 정리 제안은 아래 read-only 명령으로 확인합니다. 이 명령은
`reviews/`, final upload MP4, recipe, privacy/post-render QA 증거를 보호합니다.

```powershell
python scripts/cleanup_dry_run.py --root "<local artifact root>" --report "<outside-output-scratch-reviews>/cleanup-dry-run.json"
```

실제 삭제는 사용자가 범위를 명시 승인한 뒤에만 별도 apply 명령으로 실행합니다.
apply 명령은 동일 보고서의 SHA-256/bytes/root를 재검증하며
`frame_intermediate`, `contact_sheet`, `rejected_intermediate`만 허용합니다.
`scale_lock` MP4는 허용하지 않습니다.

```powershell
python scripts/cleanup_apply.py --root "<local artifact root>" --report "<cleanup-dry-run.json>" --category frame_intermediate --category contact_sheet --category rejected_intermediate --confirm DELETE_GENERATED_INTERMEDIATES
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
- `docs/munjanggun_content_operating_principles_v1.md`
- `docs/review_video_publish_workflow_v2.md`
- `docs/reels_operations_dashboard_v1.md`
- `docs/review_reels_content_standard_v1.md`
- `docs/review_reels_visual_edit_standard_v1.md`
- `docs/review_recipe_contract_v2.md`
- `docs/reels_posting_copy_standard_v2.md`
- `docs/reels_privacy_asset_qa_rules_v1.md`
- `docs/render_qa_rules_v2.md`
- `docs/github_pr_workflow.md`

HyperFrames 작업을 할 때만 `docs/hyperframes_official_adoption_plan_v1.md`를 추가로
읽습니다. 명령별 추가 입력은 해당 명령 문서가 안내하되, 일반 읽기 목록을 따로
만들지 않습니다.

과거 감사, 인수인계, 사진 투입 기록, 완료된 로드맵은
`docs/archive/README.md`에서 찾습니다. archive 문서는 현재 운영 권한을 갖지 않습니다.

## 최종 책임

자동화가 늘어도 최종 책임은 총괄 PD에게 있습니다.

작가, 사진 큐레이터, 편집 설계자, QA 감시자 역할은 품질을 끌어올리기 위한 내부 팀 구조이며, 최종 판단은 총괄 PD가 합니다.
