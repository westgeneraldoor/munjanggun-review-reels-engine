import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright";

const SAFE_AREA = { top: 220, bottom: 1470 };

function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error("Usage: node scripts/html-layout-precheck.mjs --html <index.html> --edit <edit_recipe.json>");
    }
    result[key.slice(2)] = value;
  }
  return result;
}

const args = parseArgs(process.argv.slice(2));
const htmlPath = path.resolve(args.html || "");
const editPath = path.resolve(args.edit || "");
if (!fs.existsSync(htmlPath) || !fs.existsSync(editPath)) {
  throw new Error("HTML or edit recipe is missing.");
}
const edit = JSON.parse(fs.readFileSync(editPath, "utf8"));
const beats = Array.isArray(edit.beats) ? edit.beats : [];
if (beats.length === 0) throw new Error("edit_recipe.beats is empty.");

const launchOptions = { headless: true };
if (process.platform === "win32" && process.env.REVIEW_REEL_ALLOW_GPU !== "1") {
  launchOptions.args = [
    "--disable-gpu",
    "--disable-gpu-compositing",
    "--disable-features=UseSkiaRenderer,CanvasOopRasterization",
  ];
}
const browser = await chromium.launch(launchOptions);
const page = await browser.newPage({ viewport: { width: 1294, height: 960 }, deviceScaleFactor: 1 });
const checks = [];
const consoleErrors = [];
page.on("pageerror", (error) => consoleErrors.push(String(error)));
page.on("console", (message) => {
  if (message.type() === "error") consoleErrors.push(message.text());
});

try {
  await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "load" });
  await page.waitForSelector("#stage");
  await page.evaluate(() => document.fonts?.ready);
  for (const beat of beats) {
    const start = Number(beat?.time?.[0] ?? 0);
    const end = Number(beat?.time?.[1] ?? start);
    const chunks = Array.isArray(beat.caption_chunks) && beat.caption_chunks.length > 0
      ? beat.caption_chunks
      : [{ text: beat.caption || "", start_sec: start, end_sec: end }];
    for (let chunkIndex = 0; chunkIndex < chunks.length; chunkIndex += 1) {
      const chunk = chunks[chunkIndex];
      const chunkStart = Number(chunk.start_sec ?? start);
      const chunkEnd = Number(chunk.end_sec ?? end);
      const sampleTime = Math.max(chunkStart + 0.04, Math.min((chunkStart + chunkEnd) / 2, chunkEnd - 0.04));
      await page.evaluate((time) => {
        const scrubber = document.querySelector("#scrubber");
        scrubber.value = String(time);
        scrubber.dispatchEvent(new Event("input", { bubbles: true }));
      }, sampleTime);
      await page.waitForTimeout(60);
      const measurement = await page.evaluate(({ safeArea }) => {
        const stageNode = document.querySelector("#stage");
        const captionNode = document.querySelector("#caption");
        const stage = stageNode.getBoundingClientRect();
        const caption = captionNode.getBoundingClientRect();
        const style = getComputedStyle(captionNode);
        const lineHeight = Number.parseFloat(style.lineHeight);
        const lines = [...captionNode.querySelectorAll(".caption-line")];
        const lineCount = lineHeight > 0
          ? (lines.length > 0
              ? lines.reduce((sum, line) => sum + Math.max(1, Math.round(line.getBoundingClientRect().height / lineHeight)), 0)
              : Math.max(1, Math.round(caption.height / lineHeight)))
          : null;
        const scaleY = 1920 / stage.height;
        const top = (caption.top - stage.top) * scaleY;
        const bottom = (caption.bottom - stage.top) * scaleY;
        return {
          text: captionNode.innerText,
          line_count: lineCount,
          top_1080x1920: Math.round(top),
          bottom_1080x1920: Math.round(bottom),
          safe: top >= safeArea.top - 0.5 && bottom <= safeArea.bottom + 0.5,
          overflow: captionNode.scrollWidth > captionNode.clientWidth + 1 || captionNode.scrollHeight > captionNode.clientHeight + 1,
        };
      }, { safeArea: SAFE_AREA });
      const issues = [];
      if (!measurement.text.trim()) issues.push("CAPTION_NOT_VISIBLE");
      if (measurement.line_count === null || measurement.line_count > 2) issues.push("CAPTION_LINE_COUNT_EXCESSIVE");
      if (!measurement.safe) issues.push("CAPTION_DEAD_ZONE");
      if (measurement.overflow) issues.push("CAPTION_OVERFLOW");
      checks.push({
        beat_id: beat.id || null,
        chunk_index: chunkIndex,
        sample_time_sec: Number(sampleTime.toFixed(3)),
        ...measurement,
        issues,
      });
    }
  }
} finally {
  await browser.close();
}

const failed = checks.filter((check) => check.issues.length > 0);
const report = {
  schema_version: "review-reel-html-layout-precheck-v1",
  status: failed.length === 0 && consoleErrors.length === 0 ? "pass" : "fail",
  caption_safe_area_1080x1920: SAFE_AREA,
  checks,
  console_errors: consoleErrors,
};
process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
process.exitCode = report.status === "pass" ? 0 : 2;
