import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright";

const FRAME_SETTLE_WAIT_MS = 500;
const SAFE_AREA_1080X1920 = { top: 220, bottom: 1470 };
const CAPTION_ACCENT_TIMING = { mode: "keyword_onset_sec", pop_duration_ms: 160 };

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error("Usage: node scripts/html-preview-qa.mjs --html <index.html> --edit <edit_recipe.json>");
    }
    result[key.slice(2)] = value;
  }
  return result;
}

function safeName(value) {
  return String(value || "beat").replace(/[^0-9A-Za-z_-]+/g, "_");
}

const args = parseArgs(process.argv.slice(2));
const htmlPath = path.resolve(args.html || "");
const editPath = path.resolve(args.edit || "");
if (!fs.existsSync(htmlPath) || !fs.existsSync(editPath)) {
  throw new Error("HTML or edit recipe is missing.");
}

const edit = JSON.parse(fs.readFileSync(editPath, "utf8"));
const beats = Array.isArray(edit.beats) ? edit.beats : [];
if (beats.length === 0) {
  throw new Error("edit_recipe.beats is empty.");
}

const previewDir = path.dirname(htmlPath);
const frameDir = path.join(previewDir, "_qa_frames");
const reportPath = path.join(previewDir, "html_internal_qa_report.json");
if (fs.existsSync(frameDir) || fs.existsSync(reportPath)) {
  throw new Error("Refusing to overwrite existing HTML QA evidence.");
}
fs.mkdirSync(frameDir);

const chromiumLaunchOptions = { headless: true };
if (process.platform === "win32" && process.env.REVIEW_REEL_ALLOW_GPU !== "1") {
  chromiumLaunchOptions.args = [
    "--disable-gpu",
    "--disable-gpu-compositing",
    "--disable-features=UseSkiaRenderer,CanvasOopRasterization",
  ];
}
const browser = await chromium.launch(chromiumLaunchOptions);
const page = await browser.newPage({ viewport: { width: 1294, height: 960 }, deviceScaleFactor: 1 });
const consoleErrors = [];
page.on("pageerror", (error) => consoleErrors.push(String(error)));
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});

const checks = [];
const hookSequenceChecks = [];
try {
  await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "load" });
  await page.waitForSelector("#stage");

  const hookBeat = beats[0];
  const hookShots = Array.isArray(hookBeat?.shots) ? hookBeat.shots.slice(0, 3) : [];
  const hookStart = Number(hookBeat?.time?.[0] ?? 0);
  const hookEnd = Number(hookBeat?.time?.[1] ?? hookStart);
  const halfSecondTime = Math.max(hookStart + 0.04, Math.min(0.5, hookEnd - 0.04));
  const shotAtHalfSecond = hookShots.find((shot) => (
    halfSecondTime >= Number(shot.start_sec) && halfSecondTime < Number(shot.end_sec)
  )) || hookShots[0];
  const hookSamples = [
    { label: "hook_0_5s", time: halfSecondTime, assetId: shotAtHalfSecond?.asset_id || null },
    ...hookShots.map((shot, index) => ({
      label: `hook_shot_${index + 1}`,
      time: (Number(shot.start_sec) + Number(shot.end_sec)) / 2,
      assetId: shot.asset_id || null,
    })),
  ];
  const hookFrameDir = path.join(frameDir, "hook_sequence");
  fs.mkdirSync(hookFrameDir);
  for (let index = 0; index < hookSamples.length; index += 1) {
    const sample = hookSamples[index];
    await page.evaluate((time) => {
      const scrubber = document.querySelector("#scrubber");
      scrubber.value = String(time);
      scrubber.dispatchEvent(new Event("input", { bubbles: true }));
    }, sample.time);
    await page.waitForTimeout(FRAME_SETTLE_WAIT_MS);
    const frameName = `${String(index + 1).padStart(2, "0")}_${sample.label}_${sample.time.toFixed(2)}s.png`;
    await page.locator("#stage").screenshot({ path: path.join(hookFrameDir, frameName) });
    hookSequenceChecks.push({
      label: sample.label,
      sample_time_sec: Number(sample.time.toFixed(3)),
      expected_asset_id: sample.assetId,
      frame_relative_path: `_qa_frames/hook_sequence/${frameName}`,
    });
  }

  for (let index = 0; index < beats.length; index += 1) {
    const beat = beats[index];
    const start = Number(beat?.time?.[0] ?? 0);
    const end = Number(beat?.time?.[1] ?? start);
    const sampleTime = Math.max(start + 0.12, Math.min((start + end) / 2, end - 0.08));
    const chunks = Array.isArray(beat.caption_chunks) && beat.caption_chunks.length > 0
      ? beat.caption_chunks
      : [{ text: beat.caption || "", start_sec: start, end_sec: end }];
    const captionSamples = [];
    for (let chunkIndex = 0; chunkIndex < chunks.length; chunkIndex += 1) {
      const chunk = chunks[chunkIndex];
      const chunkStart = Number(chunk.start_sec ?? start);
      const chunkEnd = Number(chunk.end_sec ?? end);
      const chunkTime = Math.max(chunkStart + 0.04, Math.min((chunkStart + chunkEnd) / 2, chunkEnd - 0.04));
      await page.evaluate((time) => {
        const scrubber = document.querySelector("#scrubber");
        scrubber.value = String(time);
        scrubber.dispatchEvent(new Event("input", { bubbles: true }));
      }, chunkTime);
      await page.waitForTimeout(FRAME_SETTLE_WAIT_MS);
      captionSamples.push(await page.evaluate(({ chunkIndex, chunkTime, safeArea }) => {
        const stage = document.querySelector("#stage").getBoundingClientRect();
        const captionNode = document.querySelector("#caption");
        const caption = captionNode.getBoundingClientRect();
        const captionStyle = getComputedStyle(captionNode);
        const scaleX = 1080 / stage.width;
        const scaleY = 1920 / stage.height;
        const top = (caption.top - stage.top) * scaleY;
        const bottom = (caption.bottom - stage.top) * scaleY;
        const lineHeight = Number.parseFloat(captionStyle.lineHeight);
        const captionLines = [...captionNode.querySelectorAll(".caption-line")];
        const lineCount = lineHeight > 0
          ? (captionLines.length > 0
              ? captionLines.reduce(
                  (sum, line) => sum + Math.max(1, Math.round(line.getBoundingClientRect().height / lineHeight)),
                  0,
                )
              : Math.max(1, Math.round(caption.height / lineHeight)))
          : null;
        return {
          chunk_index: chunkIndex,
          sample_time_sec: Number(chunkTime.toFixed(3)),
          text: document.querySelector("#caption").innerText,
          left_1080x1920: Math.round((caption.left - stage.left) * scaleX),
          right_1080x1920: Math.round((caption.right - stage.left) * scaleX),
          top_1080x1920: Math.round(top),
          bottom_1080x1920: Math.round(bottom),
          line_count: lineCount,
          safe: top >= safeArea.top - 0.5 && bottom <= safeArea.bottom + 0.5,
          accent_start_sec: captionNode.querySelector('.em')
            ? Number(captionNode.dataset.accentStartSec)
            : null,
          accent_pop_duration_ms: captionNode.querySelector('.em')
            ? Number(captionNode.dataset.accentPopDurationMs)
            : null,
        };
      }, { chunkIndex, chunkTime, safeArea: SAFE_AREA_1080X1920 }));
    }
    await page.evaluate((time) => {
      const scrubber = document.querySelector("#scrubber");
      scrubber.value = String(time);
      scrubber.dispatchEvent(new Event("input", { bubbles: true }));
    }, sampleTime);
    await page.waitForTimeout(FRAME_SETTLE_WAIT_MS);

    const state = await page.evaluate(() => {
      const stage = document.querySelector("#stage");
      const caption = document.querySelector("#caption");
      const images = [...stage.querySelectorAll("img")];
      const stageBox = stage.getBoundingClientRect();
      const captionBox = caption.getBoundingClientRect();
      const captionStyle = getComputedStyle(caption);
      const visibleImages = images
        .filter((image) => {
          const style = getComputedStyle(image);
          const source = image.currentSrc || image.getAttribute("src") || "";
          return source && style.display !== "none" && Number(style.opacity || "1") > 0.01;
        })
        .map((image) => ({
          id: image.id,
          src: image.currentSrc || image.src,
          loaded: image.complete && image.naturalWidth > 0 && image.naturalHeight > 0,
        }));
      const captionVisible = captionStyle.display !== "none" && Number(captionStyle.opacity || "1") > 0.01;
      const captionInside =
        !captionVisible ||
        (
          captionBox.left >= stageBox.left - 1 &&
          captionBox.right <= stageBox.right + 1 &&
          captionBox.top >= stageBox.top - 1 &&
          captionBox.bottom <= stageBox.bottom + 1
        );
      return {
        caption: caption.innerText,
        captionVisible,
        captionInside,
        captionClientWidth: caption.clientWidth,
        captionScrollWidth: caption.scrollWidth,
        captionClientHeight: caption.clientHeight,
        captionScrollHeight: caption.scrollHeight,
        visibleImages,
      };
    });

    const issues = [];
    if (!state.captionVisible || !state.caption.trim()) issues.push("CAPTION_NOT_VISIBLE");
    if (!state.captionInside) issues.push("CAPTION_OUTSIDE_STAGE");
    if (captionSamples.some((sample) => !sample.safe)) issues.push("CAPTION_DEAD_ZONE");
    if (captionSamples.some((sample) => sample.line_count === null || sample.line_count > 2)) {
      issues.push("CAPTION_LINE_COUNT_EXCESSIVE");
    }
    if (captionSamples.some((sample) => sample.accent_start_sec !== null && (
      !Number.isFinite(sample.accent_start_sec)
      || sample.accent_pop_duration_ms !== CAPTION_ACCENT_TIMING.pop_duration_ms
    ))) {
      issues.push("CAPTION_ACCENT_TIMING_INVALID");
    }
    if (state.caption.includes("\\n") || state.caption.includes("/n")) issues.push("CAPTION_LITERAL_NEWLINE");
    if (state.visibleImages.length === 0 || state.visibleImages.some((image) => !image.loaded)) {
      issues.push("VISIBLE_IMAGE_NOT_LOADED");
    }

    const frameName = `${String(index + 1).padStart(2, "0")}_${safeName(beat.id)}.png`;
    const stage = page.locator("#stage");
    await stage.screenshot({ path: path.join(frameDir, frameName) });
    checks.push({
      beat_id: beat.id || `beat_${index + 1}`,
      narrative_role: beat.narrative_role || beat.phase || null,
      sample_time_sec: Number(sampleTime.toFixed(3)),
      expected_caption: beat.caption || "",
      actual_caption: state.caption,
      caption_samples: captionSamples,
      frame_relative_path: `_qa_frames/${frameName}`,
      visible_images: state.visibleImages,
      issues,
      automatic_status: issues.length === 0 ? "pass" : "fail",
    });
  }
} finally {
  await browser.close();
}

const failedChecks = checks.filter((check) => check.automatic_status !== "pass");
const report = {
  schema_version: "review-reel-html-internal-qa-v1",
  frame_settle_wait_ms: FRAME_SETTLE_WAIT_MS,
  caption_safe_area_1080x1920: SAFE_AREA_1080X1920,
  caption_accent_timing_ms: CAPTION_ACCENT_TIMING,
  html_path: path.basename(htmlPath),
  edit_recipe_path: path.relative(previewDir, editPath).replaceAll("\\", "/"),
  automatic_status: failedChecks.length === 0 && consoleErrors.length === 0 ? "pass" : "fail",
  overall_status: failedChecks.length === 0 && consoleErrors.length === 0 ? "manual_review_required" : "blocked",
  console_errors: consoleErrors,
  checks,
  hook_sequence_checks: hookSequenceChecks,
  manual_review: {
    status: "pending",
    required_checks: [
      "first hook is immediate and dramatic",
      "voice caption and visual express the same meaning",
      "caption does not cover the subject",
      "actual review capture is readable and appears once",
      "final CTA lands without delay",
      "privacy risks are absent",
    ],
  },
};
fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(reportPath);
if (report.automatic_status !== "pass") {
  console.error(JSON.stringify({
    failed_checks: failedChecks.map((check) => ({ beat_id: check.beat_id, issues: check.issues })),
    console_errors: consoleErrors,
  }));
  process.exitCode = 2;
}
