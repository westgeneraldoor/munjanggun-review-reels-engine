# Munjanggun Review Reels Engine

문장군 네이버 고객리뷰를 기반으로 인스타그램 릴스용 스크립트, SRT, TTS, HTML 프리뷰, 최종 MP4 렌더를 만드는 로컬 자동화 엔진입니다.

## What This Repo Tracks

- 릴스 제작 워크플로 문서
- 리뷰 각색/PD 기획/QA 규칙
- Python/Node 렌더링 스크립트
- HTML 프리뷰 빌더
- QA 테스트 코드
- 프로젝트 운영 대시보드 문서

## What This Repo Does Not Track

아래 항목은 개인정보, 저작권, 용량 문제 때문에 GitHub에 올리지 않습니다.

- `.env`
- `reviews/` 원본 리뷰 텍스트
- `output/` 산출물 전체
- 고객 사진, 리뷰 캡처, 영상, 음성
- ZIP/MP4/MP3/WAV/JPG/PNG 등 미디어 파일
- `node_modules/`, `.codex_deps/`
- 로컬 폰트 파일

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

## Core Commands

Run QA before HTML or MP4 work:

```powershell
python -m video_engine_v2.reels_qa --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --sync-manifest-out "<sync_manifest.json>" --require-one-shot-contract
```

Build HTML preview:

```powershell
python build_html_preview_v2.py --planning "<planning_recipe.json>" --recipe "<edit_recipe.json>"
```

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

Run representative-time HTML visual QA before any MP4 render:

```powershell
node scripts/html-preview-qa.mjs --html "<html_preview>/index.html" --out "<output review package>/_work/html_preview_qa.json"
```

Render approved HTML to upload MP4. This is the current direct production path; it is a dry-run unless `--render-approved` is supplied after a separate explicit user render approval:

```powershell
node render_html_preview_v2.js --html "<html_preview>/index.html" --package "<output review package>" --sync-manifest "<output review package>/sync_manifest.json" --html-qa "<output review package>/_work/html_preview_qa.json" --out "<output review package>/<review-id>_final_render_YYYYMMDD_upload_10mbps.mp4" --fps 30 --width 1080 --height 1920 --render-approved
```

HyperFrames is an official Studio pilot/review path. It is allowed only through `scripts/hyperframes-render-gate.mjs` and the staged gates in `docs/hyperframes_official_adoption_plan_v1.md`; the Stage 1/2 adapter is not the default production renderer.

## Operating Rules

- Do not render MP4 before explicit user approval.
- Do not commit customer source assets or generated output.
- Every reel must pass `video_engine_v2.reels_qa`.
- New one-shot reels must follow `docs/review_reels_one_shot_contract_v1.md` and pass `--require-one-shot-contract` before HTML creation.
- Every final render must pass ffprobe/spec/representative-frame/privacy QA.
- Follow `docs/review_video_publish_workflow_v2.md` and `docs/reels_operations_dashboard_v1.md` before starting a new reel.
- Follow `docs/hyperframes_official_adoption_plan_v1.md` before calling a preview "official HyperFrames".
- Follow `docs/github_pr_workflow.md` for branches, commits, PRs, and GitHub safety checks.
