# Official HyperFrames Adoption Plan v1

This document records the migration path from the current local HTML preview renderer to the official HyperFrames Studio/CLI workflow.

## Decision

The review reels engine must not be fully replaced by HyperFrames.

Instead, the stable Munjanggun layers stay in charge of the editorial and safety decisions:

```text
review source integrity
photo/privacy QA
writer brief
PD planning
TTS and sync QA
planning_recipe / edit_recipe
```

Official HyperFrames should be introduced at the composition layer.
The current adapter is a pilot bridge, not the production renderer:

```text
edit_recipe
-> HyperFrames project
-> npx hyperframes lint / validate / inspect
-> npx hyperframes preview Studio
-> production render only after a later Stage 4 gate
```

In short:

```text
Munjanggun engine = judgment and safety
HyperFrames = timeline UI, visual inspection, composition preview, render surface
```

## Why Not Replace Everything

The current engine already has project-specific strengths that HyperFrames does not know by default:

- review-source distortion prevention
- claim and emotion gates
- Korean TTS speed and sync QA
- customer photo/privacy workflow
- upload bitrate and representative-frame QA
- user approval gates before MP4 render

Throwing these away would make the engine look more polished while becoming less safe.

## Why Adopt HyperFrames

The current local HTML preview is useful but custom. It does not provide the official HyperFrames Studio experience.

HyperFrames adds:

- timeline-oriented Studio preview
- `npx hyperframes lint`
- `npx hyperframes validate`
- `npx hyperframes inspect`
- official render command
- clearer composition contracts through `data-composition-id`, `data-start`, `data-duration`, and `data-track-index`

The 105 pilot proved that official HyperFrames can load a Munjanggun recipe-derived composition and run its validation stack.

## Non-Negotiable Rules

- Never call the old local HTML preview "official HyperFrames".
- Never call the Stage 1 adapter a production renderer.
- Never render MP4 before user approval.
- Never commit generated HyperFrames projects that contain customer media.
- Generated HyperFrames pilots must live under ignored local paths such as `scratch/` or `output/`.
- The pilot adapter must reject recipes without passing `sync_manifest.ok`, verified final voice duration, and per-beat `meaning_match`.
- Every official HyperFrames project must include a `DESIGN.md`.
- Every generated composition must pass `npx hyperframes lint`, `validate`, and `inspect` before preview handoff.
- HyperFrames render does not replace final privacy/ffprobe/representative-frame QA.

## Pilot Command

Generate a local official HyperFrames pilot from an approved edit recipe.
The recipe must already have passed `video_engine_v2.reels_qa` and contain `sync_manifest.ok: true`:

```powershell
node scripts/recipe-to-hyperframes-pilot.mjs `
  --recipe "<approved_edit_recipe.json>" `
  --out "scratch/hf-pilot-<review-id>"
```

For Stage 2 scene isolation, add `--subcompositions`:

```powershell
node scripts/recipe-to-hyperframes-pilot.mjs `
  --recipe "<approved_edit_recipe.json>" `
  --out "scratch/hf-pilot-<review-id>-subcomp" `
  --subcompositions
```

Then:

```powershell
cd "<the same folder passed to --out>"
npm run check
npm run dev
```

Hand the user the Studio URL:

```text
http://localhost:3002/#project/hf-pilot-<review-id>
```

## Current Pilot Findings

The first 105 pilot showed:

- Official HyperFrames environment works on this PC.
- Node 24 and FFmpeg are available.
- `npx hyperframes@0.6.121` runs.
- A generated 1080x1920 composition can pass lint/validate/inspect with zero errors.
- HyperFrames catches problems the old preview did not catch, such as clip visibility mistakes, track overlap, text overflow, and contrast warnings.

It also showed what must improve before production:

- Scene clips should eventually move into `compositions/scene-XX.html` sub-compositions.
- GSAP-heavy elements can block Studio drag/resize write-back.
- Keyword accent styling needs a HyperFrames-native treatment, not a direct copy of the old HTML preview markup.

## Production Migration Stages

### Stage 1. Pilot Adapter

Use `scripts/recipe-to-hyperframes-pilot.mjs` to generate local pilots from approved recipes.

Goal:

- prove preview/check/render flow
- compare Studio experience against old `file://` HTML preview
- keep all customer media local and ignored
- fail early if the recipe has not passed the existing Munjanggun sync/meaning QA

### Stage 2. Sub-Composition Adapter

Generate each beat as a separate sub-composition:

```text
index.html
compositions/scene-01.html
compositions/scene-02.html
...
assets/
DESIGN.md
```

Goal:

- reduce dense-track warnings
- make scenes easier to inspect and revise
- isolate scene-specific CSS and GSAP

The Stage 2 adapter is enabled with `--subcompositions`.
It keeps root `index.html` responsible for overall timing, narration audio, and scene-to-scene transition sweeps.
Each beat-specific scene lives in `compositions/scene-XX.html` with its own scoped CSS and registered GSAP timeline.
This is still a pilot preview/check surface, not the production MP4 render path.

### Stage 3. Studio-Friendly Motion

Move layout and edit-sensitive properties into CSS. Use GSAP mostly for entrance timing and photo motion.

Goal:

- preserve Studio timeline visibility
- reduce `gsap_studio_edit_blocked`
- make manual timeline adjustment easier

The Stage 3 adapter keeps edit-sensitive layout containers out of GSAP targets:

- `.photo-frame` owns the photo region and can be inspected as the layout anchor.
- `.photo-motion` owns Ken Burns-style motion.
- `.caption` owns caption placement.
- `.caption-motion` owns caption entrance and micro-scale motion.

This does not eliminate every `gsap_studio_edit_blocked` warning, because intentional animated internals are still GSAP-owned.
It prevents the most important layout anchors from being GSAP-owned, which makes Studio review and future manual adjustment safer.

### Stage 4. Official Render Gate

Only after user approves HyperFrames Studio preview:

```powershell
npm run render
```

Then run the existing Munjanggun final QA:

- ffprobe
- bitrate/spec check
- representative frames
- privacy check
- voice/sync sanity check

## Final Direction

The best future state is not "old renderer or HyperFrames".

The best future state is:

```text
Munjanggun review intelligence
+ Munjanggun QA gates
+ official HyperFrames Studio and render surface
```

This keeps the engine safe while making the editing experience more professional.
