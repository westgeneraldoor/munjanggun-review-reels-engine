# Munjanggun Review Reels Engine

문장군 네이버 고객리뷰를 기반으로 인스타그램 릴스용 스크립트, SRT, TTS, HTML 프리뷰, 최종 MP4 렌더를 만드는 로컬 자동화 엔진입니다.

## What This Repo Tracks

- 릴스 제작 워크플로 문서
- 리뷰 각색/PD 기획/QA 규칙
- Python/Node 렌더링 스크립트
- HTML 프리뷰 빌더
- QA 테스트 코드
- 프로젝트 운영 대시보드 문서

현재 운영 문서는 루트 `AGENTS.md`의 `핵심 문서` 목록을 따릅니다. 날짜가 지난 감사,
인수인계, 사진 투입 기록, 완료된 계획은 `docs/archive/README.md`에 분리되어 있으며
현재 운영 권한을 갖지 않습니다.

## What This Repo Does Not Track

아래 항목은 개인정보, 저작권, 용량 문제 때문에 GitHub에 올리지 않습니다.

- `.env`
- `reviews/` 원본 리뷰 텍스트
- `output/` 산출물 전체
- 고객 사진, 리뷰 캡처, 영상, 음성
- ZIP/MP4/MP3/WAV/JPG/PNG 등 미디어 파일
- `node_modules/`, `.codex_deps/`
- 로컬 폰트 파일

## Format Status

- v2: current production
- v3: experimental
- v3.1: experimental

See `docs/reels_format_status_v1.md` for the distinct v3/v3.1 hypotheses,
shared Instagram and Naver Clip engine, and the boundary that keeps experiments
from changing v2 production rules.

## Local Setup

1. Copy `.env.example` to `.env`.
2. Fill `GEMINI_API_KEY`.
3. Install Python dependencies:

```powershell
pip install -r requirements.txt
```

4. Install Node dependencies:

```powershell
npm install
```

5. Place the local font file `nelnasamchae.ttf` in the project root when rendering previews.

## Script/SRT/TTS Generation Gate

`generate.py` requires an ignored local approval package before it may call the
model or create script/SRT/TTS artifacts. The package must contain:

- `.source` matching the exact review source key
- `STATUS.md` with `photo_checked: true` and `pd_plan_approved: true`
- `APPROVAL_LOG.md` with a positive PD planning approval and no conflicting denial

Review selection alone is not approval. Do not create or edit these records
unless the photo review and user-approved PD plan actually exist.

```powershell
python generate.py --input "<review.txt>" --approval-package "<approved local package>" --with-tts
```

## Core Commands

Current v2 production work must use the single official entry point below. The
underlying QA, HTML builder, and renderer reject production work without its
gate receipt.

```powershell
# 1. PD approval, privacy evidence, review-source contract, and asset checks.
#    This creates sync_manifest.json without creating HTML or MP4 output.
python scripts/produce_review_v2.py preflight --package "<output review package>" --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --privacy-manifest "<privacy_asset_manifest.json>" --sync-manifest "<output review package>/sync_manifest.json"

# 2. Build the HTML preview after the preflight gate succeeds.
python scripts/produce_review_v2.py html --package "<output review package>" --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --privacy-manifest "<privacy_asset_manifest.json>" --sync-manifest "<output review package>/sync_manifest.json"

# 3. Only after recorded HTML and explicit MP4 approval, render the final preset.
python scripts/produce_review_v2.py render --package "<output review package>" --html "<html_preview>/index.html" --privacy-manifest "<privacy_asset_manifest.json>" --sync-manifest "<output review package>/sync_manifest.json" --out "<output review package>/<review-id>_final_render_YYYYMMDD_upload_10mbps.mp4"
```

The final v2 command enforces 1080x1920, 30fps, H.264/yuv420p, AAC 44.1kHz
stereo, and the approved 11 Mbps video preset. It refuses pre-existing MP4 or
frame directories rather than overwriting them.

### HTML-only one-shot review reels

Before any review-reel package is created, use the canonical routing and intake
contract in `docs/review_reel_production_routing_v1.md`. The official
`scripts/review_reel_intake.py` CLI creates only a private pre-photo package,
uses a local-registry-backed numeric content ID, and keeps `CAND-*` only as
source metadata. The `create-from-material-bank` command adapts the actual
private JSONL fields (`candidate_id`, `inventory_id`, `order_id`, `review_id`,
and `review_text`) without requiring an operator to invent a second inventory.
It also resolves the active package for the one-shot request below; it never
provides an MP4 render route.

```powershell
python scripts/review_reel_intake.py create-from-material-bank --output-root "output" --reviews-root "reviews" --material-bank "<candidate_top60_private.jsonl>" --candidate-id "<selected CAND-*>" --content-slug "<event-focused slug>"
```

The private source registry scans existing `reviews/` and `output/` IDs, assigns
the next unused three-digit ID, and reuses that binding on every retry. Invalid
registry data or changed source identity is a hard failure, never a silent
reset.

For an explicit user instruction equivalent to `사진 다 넣었어. HTML까지 가자`, a
review-reel package may use the HTML-only one-shot route. It never grants MP4
authority and does not bypass the script/SRT/TTS approval gate. The planning
recipe must contain the `review-reels-one-shot-v2` contract with HTML scope
authorized and MP4 scope explicitly false. Run both official phases with the
same flag:

```powershell
python scripts/produce_review_v2.py preflight --package "<output review package>" --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --privacy-manifest "<privacy_asset_manifest.json>" --sync-manifest "<output review package>/sync_manifest.json" --one-shot-html
python scripts/produce_review_v2.py html --package "<output review package>" --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --privacy-manifest "<privacy_asset_manifest.json>" --sync-manifest "<output review package>/sync_manifest.json" --one-shot-html
```

The strict contract requires photo/privacy evidence, an actual review capture,
the event-to-CTA narrative sequence, direct visual relevance, readable
captions, voice-master timing, and source-grounded claims. See
`docs/review_reels_one_shot_contract_v2.md` for the complete boundary.
Creative decisions and the approved 004/005 pacing baseline are defined in
`docs/review_reels_gold_playbook_v1.md`.

Photo intake is not approved by editing `STATUS.md`. Run the official
`scripts/review_reel_intake.py photo-review` transition with a complete
use/hold/exclude decision file and hash-bound privacy manifest. Only then may a
canonical package enter `photo_reviewed`.

The privacy manifest is a binding evidence record: it must include a non-empty
`checked_at`, a local sanitization report, no unresolved risks, and the exact
selected asset set with package-relative paths, byte counts, and SHA-256
hashes. A changed asset or manifest makes the verified sync manifest stale and
requires a fresh preflight; there is no bypass flag.

`video_engine_v2.reels_qa`, `build_html_preview_v2.py`, and
`render_html_preview_v2.js` are internal components of this production path.
`video_engine_v2.reels_qa` is an internal diagnostic module, not an official
production artifact-generation entry point.

After HTML generation, the orchestrator records
`*_html_preview_v2/html_artifact_evidence.json` with the exact HTML SHA-256 and
its HTML gate receipt hash. It also records every renderer dependency: package
image/voice and the repository-local engine font, each with kind, scope,
relative path, bytes, and SHA-256. `sync_manifest.json` separately binds the
voice path/bytes/SHA-256, so a changed voice makes both sync and HTML approval
stale. Explicit user approval must be recorded separately in `HTML_APPROVAL.json`
with package identity, relative path, HTML SHA-256, approval timestamp, and an
approval evidence reference; its artifact-evidence hash binds the full dependency
list. A legacy boolean-only approval is not render authorization.
It also runs `scripts/html-preview-qa.mjs`, captures every beat under
`_qa_frames/`, and writes `html_internal_qa_report.json`. Automatic success
still means `manual_review_required`; a task that did not inspect those frames
must not report the preview as complete.

Official HTML and render gate receipts are single-use. The builder/renderer
atomically records a hash-bound marker under `_work/production_gates/consumed/`
before creating artifacts. A copied or previously consumed receipt is rejected;
rerun the official orchestrator to obtain a fresh receipt. Receipt files and
their consumed markers are production evidence and must not be cleaned up.

Build an official HyperFrames Studio pilot from an approved edit recipe.
This is a pilot preview path, not the production renderer yet:

```powershell
node scripts/recipe-to-hyperframes-pilot.mjs --recipe "<edit_recipe.json>" --out "scratch/hf-pilot-<review-id>"
cd "scratch/hf-pilot-<review-id>"
npm run check
npm run dev
```

For the Stage 2 scene-isolated pilot, add `--subcompositions` and use a separate local output folder:

```powershell
node scripts/recipe-to-hyperframes-pilot.mjs --recipe "<edit_recipe.json>" --out "scratch/hf-pilot-<review-id>-subcomp" --subcompositions
```

Official HyperFrames render must go through the Munjanggun render gate.
The generated pilot blocks direct `npm run render` so approval cannot be bypassed:

```powershell
node scripts/hyperframes-render-gate.mjs --project "scratch/hf-pilot-<review-id>" --package "<output review package>" --sync-manifest "<output review package>/sync_manifest.json" --out "<output review package>/<review-id>_final_render_YYYYMMDD_hyperframes_upload_10mbps.mp4"
```

The command above is a dry-run and does not create MP4. Add `--render-approved` only after explicit user MP4 render approval.

After an approved MP4 is rendered, create the post-render QA evidence package:

```powershell
node scripts/render-post-qa.mjs --mp4 "<output review package>/<review-id>_final_render_YYYYMMDD_hyperframes_upload_10mbps.mp4" --package "<output review package>" --sync-manifest "<output review package>/sync_manifest.json"
```

This writes local `render_post_qa_report.json`, `render_post_qa_report.md`, and representative frames under the ignored review package `_work/` folder. Passing automatic checks still leaves `overall_status: manual_review_required` until a human reviews privacy, captions, and sync.
New QA reports bind the exact upload MP4 and the used `sync_manifest.json` with
package-relative paths, bytes, and SHA-256. In read-only package state, a
historical QA `pass` is separate from a current hash-verified `render_complete:
true`: both the MP4 and current sync manifest must still match. Hashless legacy
reports remain `unknown`. Existing upload MP4 packages are preserved, not a
deletion or automatic re-render queue. Published and performance remain `unknown`
without their own retained evidence.

## Cleanup is report-bound and approval-gated

The candidate scanner is read-only. It excludes reviews/final uploads/recipes/
privacy and post-render evidence, and refuses to write its report inside scanned
artifact folders.

```powershell
python scripts/cleanup_dry_run.py --root "<local artifact root>" --report "<outside-output-scratch-reviews>/cleanup-dry-run.json"
```

After explicit user approval, the separate apply command accepts only the
hash-verified `frame_intermediate`, `contact_sheet`, and
`rejected_intermediate` entries from that exact report. It never accepts
`scale_lock` MP4 candidates.

```powershell
python scripts/cleanup_apply.py --root "<local artifact root>" --report "<cleanup-dry-run.json>" --category frame_intermediate --category contact_sheet --category rejected_intermediate --confirm DELETE_GENERATED_INTERMEDIATES
```

HyperFrames remains a pilot path. Its render is allowed only through
`scripts/hyperframes-render-gate.mjs` and the staged gates in
`docs/hyperframes_official_adoption_plan_v1.md`; it is not the v2 production
renderer.

## Operating Rules

- Do not render MP4 before explicit user approval.
- Do not commit customer source assets or generated output.
- Every reel must pass `video_engine_v2.reels_qa`.
- Every final render must pass ffprobe/spec/representative-frame/privacy QA.
- Follow `docs/review_video_publish_workflow_v2.md` and `docs/reels_operations_dashboard_v1.md` before starting a new reel.
- Follow `docs/hyperframes_official_adoption_plan_v1.md` before calling a preview "official HyperFrames".
- Follow `docs/github_pr_workflow.md` for branches, commits, PRs, and GitHub safety checks.
