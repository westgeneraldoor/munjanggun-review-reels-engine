import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright";

const FRAME_SETTLE_WAIT_MS = 500;

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

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1294, height: 960 }, deviceScaleFactor: 1 });
const consoleErrors = [];
page.on("pageerror", (error) => consoleErrors.push(String(error)));
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});

const checks = [];
try {
  await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "load" });
  await page.waitForSelector("#stage");

  for (let index = 0; index < beats.length; index += 1) {
    const beat = beats[index];
    const start = Number(beat?.time?.[0] ?? 0);
    const end = Number(beat?.time?.[1] ?? start);
    const sampleTime = Math.max(start + 0.12, Math.min((start + end) / 2, end - 0.08));
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
  html_path: path.basename(htmlPath),
  edit_recipe_path: path.relative(previewDir, editPath).replaceAll("\\", "/"),
  automatic_status: failedChecks.length === 0 && consoleErrors.length === 0 ? "pass" : "fail",
  overall_status: failedChecks.length === 0 && consoleErrors.length === 0 ? "manual_review_required" : "blocked",
  console_errors: consoleErrors,
  checks,
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
