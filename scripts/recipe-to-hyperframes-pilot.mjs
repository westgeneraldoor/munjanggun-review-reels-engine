#!/usr/bin/env node
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const repoRoot = path.resolve(path.dirname(__filename), "..");
const HYPERFRAMES_VERSION = "0.6.121";

function die(message) {
  console.error(message);
  process.exit(2);
}

function argValue(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 && index + 1 < process.argv.length ? process.argv[index + 1] : null;
}

function hasFlag(name) {
  return process.argv.includes(name);
}

function requireArg(name) {
  const value = argValue(name);
  if (!value) {
    console.error(`Missing ${name}`);
    process.exit(2);
  }
  return value;
}

function mkdirp(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function copyAsset(sourcePath, targetPath) {
  mkdirp(path.dirname(targetPath));
  fs.copyFileSync(sourcePath, targetPath);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function resolveSource(packageDir, value) {
  return path.isAbsolute(value) ? value : path.resolve(packageDir, value);
}

function safeAssetName(role, filename) {
  const ext = path.extname(filename) || ".jpg";
  return `${role.replace(/[^\w.-]/g, "_")}${ext}`;
}

function ensureLocalOutputPath(outDir) {
  const relative = path.relative(repoRoot, outDir);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    die("Refusing to copy customer media outside this repository. Use --out under scratch/ or output/.");
  }

  const first = relative.split(path.sep)[0];
  if (!["scratch", "output"].includes(first)) {
    die("Refusing to generate customer-media HyperFrames project inside a tracked repo path. Use --out under scratch/ or output/.");
  }
}

function captionHtml(beat) {
  return String(beat.caption || "")
    .split("\n")
    .filter(Boolean)
    .map((line) => `<span class="line">${escapeHtml(line)}</span>`)
    .join("\n");
}

function captionClass(layout = {}) {
  const position = layout.position || "center";
  if (position === "upper") return "caption upper";
  if (position === "lower") return "caption lower";
  if (position === "bottom") return "caption bottom";
  return "caption center";
}

function writeJson(filePath, value) {
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function validateApprovedRecipe(recipe) {
  const issues = [];
  const beats = recipe.beats || [];
  const syncManifest = recipe.sync_manifest || {};
  const syncPolicy = recipe.audio_plan?.sync_policy || {};

  if (!Array.isArray(beats) || beats.length === 0) {
    issues.push("beats must be a non-empty array");
  }
  if (!recipe.source?.image_dir) {
    issues.push("source.image_dir is required");
  }
  if (!recipe.source?.voice && !recipe.audio_plan?.narration) {
    issues.push("source.voice or audio_plan.narration is required");
  }
  if (!recipe.asset_roles || Object.keys(recipe.asset_roles).length === 0) {
    issues.push("asset_roles must be present");
  }
  if (syncManifest.ok !== true) {
    issues.push("sync_manifest.ok must be true; run reels_qa before generating a HyperFrames pilot");
  }
  if (Array.isArray(syncManifest.issues) && syncManifest.issues.length > 0) {
    issues.push("sync_manifest.issues must be empty");
  }
  if (!Number.isFinite(Number(syncPolicy.final_voice_duration_sec)) || Number(syncPolicy.final_voice_duration_sec) <= 0) {
    issues.push("audio_plan.sync_policy.final_voice_duration_sec must be present and positive");
  }

  let previousEnd = -Infinity;
  for (const [index, beat] of beats.entries()) {
    const label = `beat[${index}]`;
    const start = Number(beat.time?.[0]);
    const end = Number(beat.time?.[1]);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
      issues.push(`${label}.time must be [start, end] with end > start`);
    }
    if (Number.isFinite(start) && start < previousEnd - 0.02) {
      issues.push(`${label}.time overlaps the previous beat`);
    }
    if (Number.isFinite(end)) previousEnd = end;
    if (!beat.asset || !recipe.asset_roles?.[beat.asset]) {
      issues.push(`${label}.asset must reference asset_roles`);
    }
    if (!beat.caption) {
      issues.push(`${label}.caption is required`);
    }
    if (beat.meaning_match !== true) {
      issues.push(`${label}.meaning_match must be true`);
    }
  }

  if (issues.length > 0) {
    die(`Refusing to generate official HyperFrames pilot:\n- ${issues.join("\n- ")}`);
  }
}

const recipePath = path.resolve(requireArg("--recipe"));
const outDir = path.resolve(requireArg("--out"));
const useSubcompositions = hasFlag("--subcompositions");
ensureLocalOutputPath(outDir);

const recipe = JSON.parse(fs.readFileSync(recipePath, "utf8"));
validateApprovedRecipe(recipe);
const packageDir = resolveSource(path.dirname(recipePath), recipe.source?.package_dir || ".");
const imageDir = resolveSource(packageDir, recipe.source?.image_dir || ".");
const assetsDir = path.join(outDir, "assets");

mkdirp(outDir);
mkdirp(assetsDir);

const assetUrls = {};
for (const [role, filename] of Object.entries(recipe.asset_roles || {})) {
  const sourcePath = path.join(imageDir, filename);
  if (!fs.existsSync(sourcePath)) {
    throw new Error(`Missing asset for role ${role}: ${sourcePath}`);
  }
  const targetName = safeAssetName(role, filename);
  copyAsset(sourcePath, path.join(assetsDir, targetName));
  assetUrls[role] = `assets/${targetName}`;
}

const voiceSource = resolveSource(packageDir, recipe.source?.voice || recipe.audio_plan?.narration || "");
if (!voiceSource || !fs.existsSync(voiceSource)) {
  throw new Error(`Missing voice source: ${voiceSource}`);
}
copyAsset(voiceSource, path.join(assetsDir, "voice.mp3"));
assetUrls.voice = "assets/voice.mp3";

const fontSource = path.join(repoRoot, "nelnasamchae.ttf");
if (fs.existsSync(fontSource)) {
  copyAsset(fontSource, path.join(assetsDir, "nelnasamchae.ttf"));
  assetUrls.font = "assets/nelnasamchae.ttf";
}

const duration = Number(recipe.audio_plan?.sync_policy?.final_voice_duration_sec)
  || Math.max(...(recipe.beats || []).map((beat) => Number(beat.time?.[1] || 0)));

const sceneHtml = (recipe.beats || []).map((beat, index) => {
  const start = Number(beat.time[0]);
  const end = Number(beat.time[1]);
  const durationSec = Math.max(0.05, end - start - 0.006);
  const sceneId = `scene-${String(index + 1).padStart(2, "0")}`;
  const proofClass = String(beat.phase || "").includes("review") ? " proof-scene" : "";
  const image = assetUrls[beat.asset];
  return `
      <div id="${sceneId}" class="scene clip${proofClass}" data-start="${start.toFixed(3)}" data-duration="${durationSec.toFixed(3)}" data-track-index="0">
        <img class="photo" src="${image}" alt="" data-layout-allow-overflow />
        <div class="shade"></div>
        <div class="${captionClass(beat.caption_layout)}">
          ${captionHtml(beat)}
        </div>
      </div>`;
}).join("\n");

const transitionHtml = (recipe.beats || []).slice(1).map((beat, index) => {
  const start = Math.max(0, Number(beat.time[0]) - 0.18);
  return `
      <div id="transition-${index + 1}" class="clip transition-sweep" data-start="${start.toFixed(3)}" data-duration="0.420" data-track-index="2"></div>`;
}).join("\n");

const sceneTweens = (recipe.beats || []).map((beat, index) => {
  const start = Number(beat.time[0]);
  const end = Number(beat.time[1]);
  const delay = Number(beat.caption_delay_sec || 0.16);
  const sceneId = `#scene-${String(index + 1).padStart(2, "0")}`;
  const photoScale = index % 2 === 0 ? 1.06 : 1.04;
  const photoX = index % 2 === 0 ? -18 : 16;
  const photoY = index % 3 === 0 ? -14 : 10;
  return `
      tl.fromTo("${sceneId} .photo", { scale: 1.01, x: 0, y: 0 }, { scale: ${photoScale}, x: ${photoX}, y: ${photoY}, duration: ${Math.max(1.2, end - start).toFixed(3)}, ease: "sine.inOut" }, ${start.toFixed(3)});
      tl.from("${sceneId} .caption .line", { y: 34, opacity: 0, scale: 0.98, stagger: 0.08, duration: 0.46, ease: "power3.out" }, ${(start + delay).toFixed(3)});
      tl.from("${sceneId} .caption", { scale: 0.985, duration: 0.34, ease: "power2.out" }, ${(start + delay + 0.18).toFixed(3)});`;
}).join("\n");

const transitionTweens = (recipe.beats || []).slice(1).map((beat, index) => {
  const start = Math.max(0, Number(beat.time[0]) - 0.18);
  return `
      tl.fromTo("#transition-${index + 1}", { opacity: 0, xPercent: -120 }, { opacity: 0.92, xPercent: 120, duration: 0.42, ease: "power2.inOut" }, ${start.toFixed(3)});`;
}).join("\n");

const title = recipe.title || path.basename(recipePath, path.extname(recipePath));

const design = `# Munjanggun HyperFrames Pilot Design

## Style Prompt

Warm Korean review proof reel for Munjanggun. The viewer should feel a real customer story and field care, not a flashy ad. Use large friendly Korean display captions, restrained warm yellow accents, real site photos, gentle motion, and clean proof-focused pacing.

## Colors

- Background: \`#171410\`
- Foreground: \`#fff6dc\`
- Primary accent: \`#ffd84d\`
- Proof shadow: \`rgba(0, 0, 0, 0.72)\`

## Typography

- Primary Korean font: \`MunjangBody\` from local \`nelnasamchae.ttf\`
- Captions use heavy visual weight, large video-safe sizes, and short lines.

## What NOT to Do

- Do not add random stickers, arrows, circles, or UI badges.
- Do not cover review captures with large text.
- Do not use sound effects by default.
- Do not use product-first hooks.
- Do not use generic web fonts or purple/blue AI-looking gradients.
`;

function sceneCompositionHtml(beat, index) {
  const start = Number(beat.time[0]);
  const end = Number(beat.time[1]);
  const durationSec = Math.max(0.05, end - start - 0.006);
  const sceneId = `scene-${String(index + 1).padStart(2, "0")}`;
  const proofClass = String(beat.phase || "").includes("review") ? " proof-scene" : "";
  const image = `../${assetUrls[beat.asset]}`;
  const photoScale = index % 2 === 0 ? 1.06 : 1.04;
  const photoX = index % 2 === 0 ? -18 : 16;
  const photoY = index % 3 === 0 ? -14 : 10;
  const delay = Number(beat.caption_delay_sec || 0.16);

  return `<!doctype html>
<html lang="ko">
  <head>
    <meta charset="UTF-8" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  </head>
  <body>
    <template id="${sceneId}-template">
      <div id="${sceneId}" data-composition-id="${sceneId}" data-width="1080" data-height="1920">
        <div class="scene${proofClass}">
          <div class="photo-frame" data-studio-editable="photo-frame">
            <img class="photo-motion" src="${image}" alt="" data-layout-allow-overflow />
          </div>
          <div class="shade"></div>
          <div class="${captionClass(beat.caption_layout)}" data-studio-editable="caption-layout">
            <div class="caption-motion">
              ${captionHtml(beat)}
            </div>
          </div>
        </div>
        <style>
          @font-face {
            font-family: "MunjangBody";
            src: url("../${assetUrls.font || ""}") format("truetype");
            font-display: swap;
          }
          #${sceneId} {
            position: relative;
            width: 1080px;
            height: 1920px;
            overflow: hidden;
            background: #171410;
            font-family: "MunjangBody", sans-serif;
          }
          #${sceneId} * { box-sizing: border-box; }
          #${sceneId} .scene {
            position: absolute;
            inset: 0;
            overflow: hidden;
            background: #171410;
          }
          #${sceneId} .photo-frame {
            position: absolute;
            inset: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
          }
          #${sceneId} .photo-motion {
            position: absolute;
            inset: -24px;
            width: calc(100% + 48px);
            height: calc(100% + 48px);
            object-fit: cover;
            transform-origin: center;
            will-change: transform;
          }
          #${sceneId} .shade {
            position: absolute;
            inset: 0;
            background:
              linear-gradient(to bottom, rgba(0,0,0,0.14), rgba(0,0,0,0.02) 32%, rgba(0,0,0,0.18) 66%, rgba(0,0,0,0.42)),
              radial-gradient(circle at 50% 42%, rgba(255,216,77,0.04), rgba(0,0,0,0.12) 70%);
          }
          #${sceneId} .proof-scene .photo-frame {
            inset: 0;
            width: 100%;
            height: 100%;
            background: rgba(20,17,12,0.92);
          }
          #${sceneId} .proof-scene .photo-motion {
            inset: 0;
            width: 100%;
            height: 100%;
            object-fit: contain;
            background: rgba(20,17,12,0.92);
          }
          #${sceneId} .proof-scene .shade {
            background: linear-gradient(to bottom, rgba(0,0,0,0.10), rgba(0,0,0,0.28));
          }
          #${sceneId} .caption {
            position: absolute;
            left: 90px;
            right: 90px;
            z-index: 4;
          }
          #${sceneId} .caption-motion {
            display: flex;
            flex-direction: column;
            gap: 12px;
            text-align: center;
            color: #ffd84d;
            font-weight: 900;
            font-size: 112px;
            line-height: 1.02;
            letter-spacing: -0.025em;
            text-shadow: 0 8px 0 rgba(0,0,0,0.72), 0 18px 46px rgba(0,0,0,0.58);
            -webkit-text-stroke: 3px rgba(23,20,16,0.78);
            paint-order: stroke fill;
            word-break: keep-all;
          }
          #${sceneId} .caption.center { top: 50%; transform: translateY(-50%); }
          #${sceneId} .caption.upper { top: 150px; }
          #${sceneId} .caption.lower { bottom: 210px; }
          #${sceneId} .caption.bottom { bottom: 145px; }
          #${sceneId} .caption.upper .caption-motion { font-size: 84px; }
          #${sceneId} .caption.lower .caption-motion,
          #${sceneId} .caption.bottom .caption-motion { font-size: 94px; }
          #${sceneId} .caption .line { display: block; }
        </style>
        <script>
          window.__timelines = window.__timelines || {};
          const tl = gsap.timeline({ paused: true });
          tl.fromTo(".photo-motion", { scale: 1.01, x: 0, y: 0 }, { scale: ${photoScale}, x: ${photoX}, y: ${photoY}, duration: ${Math.max(1.2, durationSec).toFixed(3)}, ease: "sine.inOut" }, 0);
          tl.from(".caption-motion .line", { y: 34, opacity: 0, scale: 0.98, stagger: 0.08, duration: 0.46, ease: "power3.out" }, ${delay.toFixed(3)});
          tl.from(".caption-motion", { scale: 0.985, duration: 0.34, ease: "power2.out" }, ${(delay + 0.18).toFixed(3)});
          window.__timelines["${sceneId}"] = tl;
        </script>
      </div>
    </template>
  </body>
</html>
`;
}

function subcompositionClipHtml(beat, index) {
  const start = Number(beat.time[0]);
  const end = Number(beat.time[1]);
  const durationSec = Math.max(0.05, end - start - 0.006);
  const sceneId = `scene-${String(index + 1).padStart(2, "0")}`;

  return `
      <div
        id="${sceneId}-clip"
        class="clip composition-clip"
        data-composition-id="${sceneId}"
        data-composition-src="compositions/${sceneId}.html"
        data-start="${start.toFixed(3)}"
        data-duration="${durationSec.toFixed(3)}"
        data-track-index="0"
      ></div>`;
}

function subcompositionRootHtml() {
  const clips = (recipe.beats || []).map(subcompositionClipHtml).join("\n");

  return `<!doctype html>
<html lang="ko">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * { margin: 0; padding: 0; box-sizing: border-box; }
      html, body {
        width: 1080px;
        height: 1920px;
        overflow: hidden;
        background: #171410;
      }
      #root {
        position: relative;
        width: 1080px;
        height: 1920px;
        overflow: hidden;
        background: #171410;
      }
      .clip {
        position: absolute;
        inset: 0;
        overflow: hidden;
        background: #171410;
      }
      .transition-sweep {
        position: absolute;
        inset: 0;
        background: linear-gradient(103deg,
          rgba(255,216,77,0) 0%,
          rgba(255,246,220,0.05) 28%,
          rgba(255,246,220,0.72) 48%,
          rgba(255,216,77,0.42) 56%,
          rgba(255,216,77,0) 78%);
        mix-blend-mode: screen;
        opacity: 0;
        pointer-events: none;
        z-index: 8;
      }
      audio { display: none; }
    </style>
  </head>
  <body>
    <div
      id="root"
      data-composition-id="main"
      data-start="0"
      data-duration="${duration.toFixed(3)}"
      data-width="1080"
      data-height="1920"
    >
${clips}
${transitionHtml}
      <audio id="voice" src="${assetUrls.voice}" data-start="0" data-duration="${duration.toFixed(3)}" data-track-index="3" data-volume="1"></audio>
    </div>
    <script>
      window.__timelines = window.__timelines || {};
      const tl = gsap.timeline({ paused: true });
${transitionTweens}
      tl.to("#root", { opacity: 0, duration: 0.35, ease: "sine.inOut" }, ${(duration - 0.35).toFixed(3)});
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
`;
}

const html = `<!doctype html>
<html lang="ko">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1080, height=1920" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      @font-face {
        font-family: "MunjangBody";
        src: url("${assetUrls.font || ""}") format("truetype");
        font-display: swap;
      }
      * { margin: 0; padding: 0; box-sizing: border-box; }
      html, body {
        width: 1080px;
        height: 1920px;
        overflow: hidden;
        background: #171410;
        font-family: "MunjangBody", sans-serif;
      }
      #root {
        position: relative;
        width: 1080px;
        height: 1920px;
        overflow: hidden;
        background: #171410;
      }
      .clip {
        position: absolute;
        inset: 0;
        overflow: hidden;
        background: #171410;
      }
      .scene .photo {
        position: absolute;
        inset: -24px;
        width: calc(100% + 48px);
        height: calc(100% + 48px);
        object-fit: cover;
        transform-origin: center;
        will-change: transform;
      }
      .shade {
        position: absolute;
        inset: 0;
        background:
          linear-gradient(to bottom, rgba(0,0,0,0.14), rgba(0,0,0,0.02) 32%, rgba(0,0,0,0.18) 66%, rgba(0,0,0,0.42)),
          radial-gradient(circle at 50% 42%, rgba(255,216,77,0.04), rgba(0,0,0,0.12) 70%);
      }
      .proof-scene .photo {
        object-fit: contain;
        background: rgba(20,17,12,0.92);
      }
      .proof-scene .shade {
        background: linear-gradient(to bottom, rgba(0,0,0,0.10), rgba(0,0,0,0.28));
      }
      .caption {
        position: absolute;
        left: 90px;
        right: 90px;
        display: flex;
        flex-direction: column;
        gap: 12px;
        text-align: center;
        color: #ffd84d;
        font-weight: 900;
        font-size: 112px;
        line-height: 1.02;
        letter-spacing: -0.025em;
        text-shadow: 0 8px 0 rgba(0,0,0,0.72), 0 18px 46px rgba(0,0,0,0.58);
        -webkit-text-stroke: 3px rgba(23,20,16,0.78);
        paint-order: stroke fill;
        word-break: keep-all;
        z-index: 4;
      }
      .caption.center { top: 50%; transform: translateY(-50%); }
      .caption.upper { top: 150px; font-size: 84px; }
      .caption.lower { bottom: 210px; font-size: 94px; }
      .caption.bottom { bottom: 145px; font-size: 94px; }
      .caption .line { display: block; }
      .transition-sweep {
        position: absolute;
        inset: 0;
        background: linear-gradient(103deg,
          rgba(255,216,77,0) 0%,
          rgba(255,246,220,0.05) 28%,
          rgba(255,246,220,0.72) 48%,
          rgba(255,216,77,0.42) 56%,
          rgba(255,216,77,0) 78%);
        mix-blend-mode: screen;
        opacity: 0;
        pointer-events: none;
        z-index: 8;
      }
      audio { display: none; }
    </style>
  </head>
  <body>
    <div
      id="root"
      data-composition-id="main"
      data-start="0"
      data-duration="${duration.toFixed(3)}"
      data-width="1080"
      data-height="1920"
    >
${sceneHtml}
${transitionHtml}
      <audio id="voice" src="${assetUrls.voice}" data-start="0" data-duration="${duration.toFixed(3)}" data-track-index="3" data-volume="1"></audio>
    </div>
    <script>
      window.__timelines = window.__timelines || {};
      const tl = gsap.timeline({ paused: true });
${sceneTweens}
${transitionTweens}
      tl.to("#root", { opacity: 0, duration: 0.35, ease: "sine.inOut" }, ${(duration - 0.35).toFixed(3)});
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
`;

writeJson(path.join(outDir, "package.json"), {
  name: path.basename(outDir).toLowerCase().replace(/[^a-z0-9_-]/g, "-"),
  private: true,
  type: "module",
  scripts: {
    dev: `npx --yes hyperframes@${HYPERFRAMES_VERSION} preview`,
    check: `npx --yes hyperframes@${HYPERFRAMES_VERSION} lint && npx --yes hyperframes@${HYPERFRAMES_VERSION} validate && npx --yes hyperframes@${HYPERFRAMES_VERSION} inspect`,
    render: `npx --yes hyperframes@${HYPERFRAMES_VERSION} render`,
  },
});

writeJson(path.join(outDir, "hyperframes.json"), {
  $schema: "https://hyperframes.heygen.com/schema/hyperframes.json",
  registry: "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
  paths: {
    blocks: "compositions",
    components: "compositions/components",
    assets: "assets",
  },
});

writeJson(path.join(outDir, "meta.json"), {
  id: path.basename(outDir),
  name: title,
  sourceRecipe: recipePath,
  generatedAt: new Date().toISOString(),
});

fs.writeFileSync(path.join(outDir, "DESIGN.md"), design, "utf8");
if (useSubcompositions) {
  const compositionsDir = path.join(outDir, "compositions");
  mkdirp(compositionsDir);
  for (const [index, beat] of (recipe.beats || []).entries()) {
    const sceneId = `scene-${String(index + 1).padStart(2, "0")}`;
    fs.writeFileSync(path.join(compositionsDir, `${sceneId}.html`), sceneCompositionHtml(beat, index), "utf8");
  }
  fs.writeFileSync(path.join(outDir, "index.html"), subcompositionRootHtml(), "utf8");
} else {
  fs.writeFileSync(path.join(outDir, "index.html"), html, "utf8");
}

console.log(`Wrote official HyperFrames pilot: ${outDir}`);
console.log(`Mode: ${useSubcompositions ? "sub-compositions" : "single-file"}`);
console.log(`Run: cd "${outDir}" && npm run check`);
console.log(`Preview: cd "${outDir}" && npm run dev`);
