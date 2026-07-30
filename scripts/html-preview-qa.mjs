#!/usr/bin/env node
import fs from "fs";
import path from "path";
import { pathToFileURL } from "url";
import { chromium } from "playwright";

function die(message) {
  console.error(message);
  process.exit(2);
}

function argValue(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 && index + 1 < process.argv.length ? process.argv[index + 1] : null;
}

function requireArg(name) {
  const value = argValue(name);
  if (!value) die(`Missing ${name}`);
  return value;
}

function roleOf(beat) {
  return String(beat.narrative_role || beat.role || beat.phase || "").trim();
}

function timeFor(beat, fallback) {
  const range = Array.isArray(beat?.time) ? beat.time : [];
  const start = Number(range[0]);
  const end = Number(range[1]);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return fallback;
  return Math.min(end - 0.08, start + Math.max(0.12, (end - start) / 2));
}

function inside(inner, outer, tolerance = 2) {
  return inner.left >= outer.left - tolerance
    && inner.top >= outer.top - tolerance
    && inner.right <= outer.right + tolerance
    && inner.bottom <= outer.bottom + tolerance;
}

async function sample(page, time) {
  await page.evaluate((nextTime) => {
    if (typeof renderAt !== "function") throw new Error("HTML preview must expose renderAt(time) for QA.");
    renderAt(nextTime);
  }, time);
  return page.evaluate(() => {
    const rect = (node) => {
      if (!node) return null;
      const value = node.getBoundingClientRect();
      return { left: value.left, top: value.top, right: value.right, bottom: value.bottom, width: value.width, height: value.height };
    };
    const stage = document.querySelector(".stage");
    const caption = document.querySelector(".caption");
    const reviewCard = document.querySelector(".review-card");
    const asset = document.querySelector(".asset.main");
    return {
      stage: rect(stage),
      caption: {
        rect: rect(caption),
        opacity: Number(window.getComputedStyle(caption).opacity),
        text: String(caption?.innerText || "").trim(),
      },
      reviewCard: {
        rect: rect(reviewCard),
        opacity: Number(window.getComputedStyle(reviewCard).opacity),
      },
      asset: {
        src: String(asset?.getAttribute("src") || ""),
        naturalWidth: Number(asset?.naturalWidth || 0),
        naturalHeight: Number(asset?.naturalHeight || 0),
      },
    };
  });
}

function inspectPoint(name, snapshot, { expectsReview = false } = {}) {
  const issues = [];
  if (!snapshot.stage || snapshot.stage.width <= 0 || snapshot.stage.height <= 0) {
    issues.push("stage is empty or unavailable");
  }
  if (!snapshot.asset.src || snapshot.asset.naturalWidth <= 0 || snapshot.asset.naturalHeight <= 0) {
    issues.push("main visual asset is empty or failed to load");
  }
  if (snapshot.caption.opacity > 0.05) {
    if (!snapshot.caption.text) issues.push("visible caption is empty");
    if (snapshot.caption.rect && snapshot.stage && !inside(snapshot.caption.rect, snapshot.stage)) {
      issues.push("caption is clipped outside the stage");
    }
  }
  if (snapshot.reviewCard.opacity > 0.05 && snapshot.reviewCard.rect && snapshot.stage && !inside(snapshot.reviewCard.rect, snapshot.stage)) {
    issues.push("review card is clipped outside the stage");
  }
  if (name === "first_hook" && snapshot.reviewCard.opacity > 0.05) {
    issues.push("review card appeared before its proof beat");
  }
  if (expectsReview && snapshot.reviewCard.opacity <= 0.05) {
    issues.push("review proof beat did not reveal the review card");
  }
  return { name, ok: issues.length === 0, issues };
}

async function main() {
  const htmlPath = path.resolve(requireArg("--html"));
  const outputPath = path.resolve(requireArg("--out"));
  if (!fs.existsSync(htmlPath)) die(`Missing HTML preview: ${htmlPath}`);

  const launchOptions = { headless: true };
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) launchOptions.executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  const browser = await chromium.launch(launchOptions);
  let checks;
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 693 }, deviceScaleFactor: 1 });
    await page.goto(pathToFileURL(htmlPath).href);
    await page.waitForLoadState("load");
    const recipe = await page.evaluate(() => {
      const currentRecipe = typeof recipe !== "undefined" ? recipe : window.recipe;
      return currentRecipe || null;
    });
    const beats = Array.isArray(recipe?.beats) ? recipe.beats : [];
    if (beats.length === 0) die("HTML preview recipe must include beats.");
    const reviewBeat = beats.find((beat) => roleOf(beat) === "review_proof" || beat.asset === "review_capture");
    const ctaBeat = beats.find((beat) => roleOf(beat) === "cta") || beats.at(-1);
    if (!reviewBeat) die("HTML preview recipe must include an actual review_proof beat.");
    const duration = Math.max(...beats.map((beat) => Number(beat.time?.[1]) || 0));
    const points = [
      { name: "first_hook", time: Math.min(0.4, Math.max(0, duration - 0.01)), expectsReview: false },
      { name: "review_proof", time: timeFor(reviewBeat, duration / 2), expectsReview: true },
      { name: "final_cta", time: timeFor(ctaBeat, Math.max(0, duration - 0.08)), expectsReview: false },
    ];
    checks = [];
    for (const point of points) {
      const snapshot = await sample(page, point.time);
      checks.push({ ...inspectPoint(point.name, snapshot, point), time_sec: Number(point.time.toFixed(3)) });
    }
  } finally {
    await browser.close();
  }

  const report = {
    schema_version: "1.0",
    ok: checks.every((check) => check.ok),
    checks,
    manual_review_required: ["visual tone", "photo privacy", "caption-to-subject judgment", "voice-caption-screen meaning sync"],
  };
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  console.log(outputPath);
  if (!report.ok) process.exit(1);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
