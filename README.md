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
python -m video_engine_v2.reels_qa --planning "<planning_recipe.json>" --edit "<edit_recipe.json>" --sync-manifest-out "<sync_manifest.json>"
```

Build HTML preview:

```powershell
python build_html_preview_v2.py --recipe "<edit_recipe.json>"
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

Render approved HTML to upload MP4:

```powershell
node render_html_preview_v2.js --html "<html_preview>/index.html" --out "<output>_upload_10mbps.mp4" --fps 30 --width 1080 --height 1920
```

The command above is the current production render path. HyperFrames render is introduced only after the staged gates in `docs/hyperframes_official_adoption_plan_v1.md`.

## Operating Rules

- Do not render MP4 before explicit user approval.
- Do not commit customer source assets or generated output.
- Every reel must pass `video_engine_v2.reels_qa`.
- Every final render must pass ffprobe/spec/representative-frame/privacy QA.
- Follow `docs/review_video_publish_workflow_v2.md` and `docs/reels_operations_dashboard_v1.md` before starting a new reel.
- Follow `docs/hyperframes_official_adoption_plan_v1.md` before calling a preview "official HyperFrames".
- Follow `docs/github_pr_workflow.md` for branches, commits, PRs, and GitHub safety checks.
