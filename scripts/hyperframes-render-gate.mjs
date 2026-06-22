#!/usr/bin/env node
import fs from "fs";
import path from "path";
import { spawnSync } from "child_process";
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
  if (!value) die(`Missing ${name}`);
  return value;
}

function readText(filePath) {
  return fs.existsSync(filePath) ? fs.readFileSync(filePath, "utf8") : "";
}

function readJson(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch (error) {
    die(`Invalid JSON: ${filePath}\n${error.message}`);
  }
}

function relativeFromRepo(targetPath) {
  return path.relative(repoRoot, path.resolve(targetPath));
}

function isInsideRepo(targetPath) {
  const relative = relativeFromRepo(targetPath);
  return relative && !relative.startsWith("..") && !path.isAbsolute(relative);
}

function ensureInsideAllowedLocalRoot(targetPath, label) {
  if (!isInsideRepo(targetPath)) {
    die(`${label} must stay inside this repository.`);
  }
  const first = relativeFromRepo(targetPath).split(path.sep)[0];
  if (!["scratch", "output"].includes(first)) {
    die(`${label} must be under scratch/ or output/ to avoid tracked customer media.`);
  }
}

function ensureInsideOutput(targetPath, label) {
  if (!isInsideRepo(targetPath)) {
    die(`${label} must stay inside this repository.`);
  }
  const first = relativeFromRepo(targetPath).split(path.sep)[0];
  if (first !== "output") {
    die(`${label} must be under output/ because render approval belongs to a review package.`);
  }
}

function parseBooleanLine(text, key) {
  const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`${escaped}\\s*:\\s*(true|false)`, "i");
  const match = text.match(pattern);
  return match ? match[1].toLowerCase() === "true" : null;
}

function approvalScopes(text) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => /^-?\s*approved_scope\s*:/i.test(line))
    .map((line) => line.replace(/^-?\s*approved_scope\s*:\s*/i, ""));
}

function hasPositiveApprovalScope(text, pattern) {
  return approvalScopes(text).some((scope) => {
    if (/없음|none|not approved|미승인|보류|pending/i.test(scope)) {
      return false;
    }
    return pattern.test(scope);
  });
}

function validatePackageApproval(packageDir) {
  const statusPath = path.join(packageDir, "STATUS.md");
  const approvalPath = path.join(packageDir, "APPROVAL_LOG.md");
  if (!fs.existsSync(statusPath)) {
    die(`Missing STATUS.md: ${statusPath}`);
  }
  if (!fs.existsSync(approvalPath)) {
    die(`Missing APPROVAL_LOG.md: ${approvalPath}`);
  }

  const status = readText(statusPath);
  const approval = readText(approvalPath);
  if (parseBooleanLine(status, "html_approved_by_user") !== true) {
    die("STATUS.md must contain html_approved_by_user: true before HyperFrames render.");
  }
  if (parseBooleanLine(status, "mp4_allowed") !== true) {
    die("STATUS.md must contain mp4_allowed: true before HyperFrames render.");
  }
  if (!hasPositiveApprovalScope(approval, /HTML|html|프리뷰|preview|Studio|studio/)) {
    die("APPROVAL_LOG.md must record a positive approved_scope for HTML/Studio preview.");
  }
  if (!hasPositiveApprovalScope(approval, /(?=.*\bMP4\b)(?=.*(렌더|render|승인|approved))/i)) {
    die("APPROVAL_LOG.md must record a positive approved_scope for explicit MP4 render approval.");
  }
}

function validateSyncManifest(syncManifestPath) {
  const manifest = readJson(syncManifestPath);
  if (manifest.ok !== true) {
    die("sync_manifest.ok must be true before HyperFrames render.");
  }
  if (Array.isArray(manifest.issues) && manifest.issues.length > 0) {
    die("sync_manifest.issues must be empty before HyperFrames render.");
  }

  const audio = manifest.audio || {};
  const finalDuration = Number(audio.final_voice_duration_sec ?? manifest.final_voice_duration_sec);
  if (!Number.isFinite(finalDuration) || finalDuration <= 0) {
    die("sync_manifest must include a positive final_voice_duration_sec.");
  }

  const totalCps = Number(audio.total_voice_cps ?? manifest.total_voice_cps);
  if (!Number.isFinite(totalCps)) {
    die("sync_manifest must include total_voice_cps before HyperFrames render.");
  }
  if (totalCps >= 9.0) {
    die("sync_manifest total_voice_cps is too high for render.");
  }

  const scenes = manifest.scenes || manifest.beats || [];
  if (!Array.isArray(scenes) || scenes.length === 0) {
    die("sync_manifest must include scene or beat meaning_match evidence.");
  }
  for (const [index, scene] of scenes.entries()) {
    if (scene.meaning_match !== true) {
      die(`sync_manifest scene[${index}] must have meaning_match: true.`);
    }
    const evidence = scene.meaning_match_evidence ?? scene.meaning_match_source;
    if (!evidence || !String(evidence).trim()) {
      die(`sync_manifest scene[${index}] must include meaning_match evidence.`);
    }
  }
}

function validateHyperFramesProject(projectDir) {
  const required = ["package.json", "index.html", "DESIGN.md"];
  for (const name of required) {
    const filePath = path.join(projectDir, name);
    if (!fs.existsSync(filePath)) {
      die(`Missing HyperFrames project file: ${filePath}`);
    }
  }

  const packageJson = readJson(path.join(projectDir, "package.json"));
  const scripts = packageJson.scripts || {};
  if (!scripts.check || !String(scripts.check).includes("hyperframes")) {
    die("HyperFrames project package.json must expose a hyperframes check script.");
  }
  if (!scripts.render || !String(scripts.render).includes("Direct HyperFrames render is blocked")) {
    die("HyperFrames project package.json must block direct npm run render.");
  }
  for (const [name, command] of Object.entries(scripts)) {
    if (name === "render") continue;
    if (/hyperframes@?[^\s"]*\s+render|hyperframes.*\brender\b/i.test(String(command))) {
      die(`HyperFrames project package.json must not expose direct render script: ${name}`);
    }
  }
}

function runCommand(command, args, cwd, label) {
  const result = spawnSync(command, args, {
    cwd,
    encoding: "utf8",
    stdio: "inherit",
    shell: process.platform === "win32",
  });
  if (result.error) {
    die(`${label} failed: ${result.error.message}`);
  }
  if (result.status !== 0) {
    die(`${label} failed with exit ${result.status}`);
  }
}

function finalQaReminder(outputPath) {
  return [
    "After render, run Munjanggun final QA:",
    "- ffprobe/spec check: 1080x1920, 30fps, upload bitrate target",
    "- representative frames: hook, problem, middle, review proof, CTA",
    "- privacy check: face/family photo/address/vehicle/reflection risk",
    "- sync sanity: voice/caption/screen meaning alignment",
    `- output: ${outputPath}`,
  ].join("\n");
}

const projectDir = path.resolve(requireArg("--project"));
const packageDir = path.resolve(requireArg("--package"));
const syncManifestPath = path.resolve(requireArg("--sync-manifest"));
const outputPath = path.resolve(requireArg("--out"));
const renderApproved = hasFlag("--render-approved");

ensureInsideAllowedLocalRoot(projectDir, "HyperFrames project");
ensureInsideOutput(packageDir, "Review package");
ensureInsideOutput(outputPath, "MP4 output");

if (path.extname(outputPath).toLowerCase() !== ".mp4") {
  die("MP4 output must end with .mp4.");
}
if (!path.basename(outputPath).includes("upload_10mbps")) {
  die("MP4 output filename must include upload_10mbps.");
}
if (!path.resolve(outputPath).startsWith(`${packageDir}${path.sep}`)) {
  die("MP4 output must be written inside the approved review package folder.");
}
if (!fs.existsSync(syncManifestPath)) {
  die(`Missing sync_manifest: ${syncManifestPath}`);
}
if (!path.resolve(syncManifestPath).startsWith(`${packageDir}${path.sep}`)) {
  die("sync_manifest must be stored inside the approved review package folder.");
}

validatePackageApproval(packageDir);
validateSyncManifest(syncManifestPath);
validateHyperFramesProject(projectDir);

if (!renderApproved) {
  console.log("HyperFrames render gate passed in dry-run mode.");
  console.log("No MP4 was rendered because --render-approved was not provided.");
  console.log("To render after explicit user approval:");
  console.log(`  node scripts/hyperframes-render-gate.mjs --project "${projectDir}" --package "${packageDir}" --sync-manifest "${syncManifestPath}" --out "${outputPath}" --render-approved`);
  console.log(finalQaReminder(outputPath));
  process.exit(0);
}

runCommand("npm", ["run", "check"], projectDir, "HyperFrames check");
runCommand("npx", ["--yes", `hyperframes@${HYPERFRAMES_VERSION}`, "render", "--output", outputPath, "--fps", "30", "--quality", "high"], projectDir, "HyperFrames render");
console.log(finalQaReminder(outputPath));
