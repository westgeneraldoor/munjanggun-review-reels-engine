#!/usr/bin/env node
import fs from "fs";
import crypto from "crypto";
import path from "path";
import { spawnSync } from "child_process";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const repoRoot = path.resolve(path.dirname(__filename), "..");
// Test-only boundary: unit tests may supply a TemporaryDirectory that mirrors
// the ignored output/ and scratch/ layout. Production commands never set this.
const testLocalRoot = process.env.MUNJANGGUN_TEST_LOCAL_ROOT
  ? path.resolve(process.env.MUNJANGGUN_TEST_LOCAL_ROOT)
  : null;

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

function readBoundJson(filePath, packageDir) {
  const bytes = fs.readFileSync(filePath);
  try {
    return {
      evidence: {
        relative_path: path.relative(packageDir, filePath).split(path.sep).join("/"),
        bytes: bytes.length,
        sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
      },
      value: JSON.parse(bytes.toString("utf8")),
    };
  } catch (error) {
    die(`Invalid JSON: ${filePath}\n${error.message}`);
  }
}

function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function localRootKind(targetPath) {
  for (const root of [repoRoot, testLocalRoot].filter(Boolean)) {
    const relative = path.relative(canonicalPath(root), canonicalPath(targetPath));
    if (relative && !relative.startsWith("..") && !path.isAbsolute(relative)) {
      return relative.split(path.sep)[0];
    }
  }
  return null;
}

function sha256(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function boundFileEvidence(filePath, packageDir) {
  return {
    relative_path: path.relative(packageDir, filePath).split(path.sep).join("/"),
    bytes: fs.statSync(filePath).size,
    sha256: sha256(filePath),
  };
}

function ensureInsideOutput(targetPath, label) {
  const first = localRootKind(targetPath);
  if (first !== "output") {
    die(`${label} must be under output/.`);
  }
}

function ensureInsidePackage(targetPath, packageDir, label) {
  const resolved = canonicalPath(targetPath);
  const canonicalPackage = canonicalPath(packageDir);
  if (resolved !== canonicalPackage && !resolved.startsWith(`${canonicalPackage}${path.sep}`)) {
    die(`${label} must stay inside the approved review package folder.`);
  }

  const packageReal = fs.realpathSync.native(packageDir);
  const realBase = nearestExistingPath(resolved);
  const realBaseStats = fs.statSync(realBase);
  const targetRealParent = fs.realpathSync.native(realBaseStats.isDirectory() ? realBase : path.dirname(realBase));
  if (targetRealParent !== packageReal && !targetRealParent.startsWith(`${packageReal}${path.sep}`)) {
    die(`${label} real path must stay inside the approved review package folder.`);
  }
}

function nearestExistingPath(targetPath) {
  let current = path.resolve(targetPath);
  while (!fs.existsSync(current)) {
    const parent = path.dirname(current);
    if (parent === current) {
      die(`No existing parent path for ${targetPath}`);
    }
    current = parent;
  }
  return current;
}

function canonicalPath(targetPath) {
  const resolved = path.resolve(targetPath);
  const existing = nearestExistingPath(resolved);
  const realExisting = fs.realpathSync.native(existing);
  return path.resolve(realExisting, path.relative(existing, resolved));
}

function runJsonCommand(command, args, cwd, label) {
  const [actualCommand, actualArgs] = commandWithEnvironmentOverride(command, args);
  const result = spawnSync(actualCommand, actualArgs, {
    cwd,
    encoding: "utf8",
    shell: false,
  });
  if (result.error) die(`${label} failed: ${result.error.message}`);
  if (result.status !== 0) {
    die(`${label} failed with exit ${result.status}\n${result.stderr || result.stdout || ""}`);
  }
  try {
    return JSON.parse(result.stdout);
  } catch (error) {
    die(`${label} did not return JSON.\n${error.message}\n${result.stdout}`);
  }
}

function runCommand(command, args, cwd, label) {
  const [actualCommand, actualArgs] = commandWithEnvironmentOverride(command, args);
  const result = spawnSync(actualCommand, actualArgs, {
    cwd,
    encoding: "utf8",
    stdio: "pipe",
    shell: false,
  });
  if (result.error) die(`${label} failed: ${result.error.message}`);
  if (result.status !== 0) {
    die(`${label} failed with exit ${result.status}\n${result.stderr || result.stdout || ""}`);
  }
}

function commandWithEnvironmentOverride(command, args) {
  const prefix = command.toUpperCase();
  const actualCommand = process.env[`${prefix}_BIN`] || command;
  const prefixArgs = process.env[`${prefix}_ARGS_JSON`]
    ? JSON.parse(process.env[`${prefix}_ARGS_JSON`])
    : [];
  return [actualCommand, [...prefixArgs, ...args]];
}

function ratioToNumber(value) {
  if (!value) return NaN;
  const [left, right] = String(value).split("/").map(Number);
  if (!Number.isFinite(left)) return NaN;
  if (!Number.isFinite(right) || right === 0) return left;
  return left / right;
}

function numberValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : NaN;
}

function check(code, label, passed, expected, actual, severity = "fail") {
  return {
    code,
    label,
    status: passed ? "pass" : severity,
    expected,
    actual,
  };
}

function formatMbps(value) {
  return Number.isFinite(value) ? `${(value / 1_000_000).toFixed(2)} Mbps` : "unknown";
}

function representativeTimes(duration) {
  const safeDuration = Number.isFinite(duration) && duration > 0 ? duration : 1;
  const raw = [
    ["hook", 0.5],
    ["problem", Math.min(4, safeDuration * 0.2)],
    ["middle", safeDuration * 0.5],
    ["review_proof", safeDuration * 0.8],
    ["cta", Math.max(0.2, safeDuration - 1.0)],
  ];
  const seen = new Set();
  return raw.map(([label, time]) => {
    const safeTime = Math.max(0, Math.min(Number(time), Math.max(0, safeDuration - 0.05)));
    const rounded = Number(safeTime.toFixed(2));
    let key = rounded.toFixed(2);
    while (seen.has(key)) {
      key = (Number(key) + 0.25).toFixed(2);
    }
    seen.add(key);
    return [label, Math.min(Number(key), Math.max(0, safeDuration - 0.05))];
  });
}

function extractRepresentativeFrames(mp4Path, reportDir, duration) {
  const framesDir = path.join(reportDir, "representative_frames");
  fs.mkdirSync(framesDir, { recursive: true });
  return representativeTimes(duration).map(([label, time], index) => {
    const filePath = path.join(framesDir, `${String(index + 1).padStart(2, "0")}_${label}_${time.toFixed(2)}s.jpg`);
    runCommand(
      "ffmpeg",
      ["-y", "-ss", time.toFixed(3), "-i", mp4Path, "-frames:v", "1", "-q:v", "2", filePath],
      repoRoot,
      `ffmpeg representative frame ${label}`,
    );
    if (!fs.existsSync(filePath)) {
      die(`Representative frame was not written: ${filePath}`);
    }
    return {
      label,
      time_sec: Number(time.toFixed(2)),
      path: filePath,
    };
  });
}

function renderMarkdown(report) {
  const autoRows = report.auto_checks
    .map((item) => `| ${item.status} | ${item.code} | ${item.expected} | ${item.actual} |`)
    .join("\n");
  const frameRows = report.representative_frames
    .map((frame) => `| ${frame.label} | ${frame.time_sec}s | ${frame.path} |`)
    .join("\n");
  const manualRows = report.manual_review.checks
    .map((item) => `- [ ] ${item}`)
    .join("\n");

  return `# Render Post QA Report

- auto_status: ${report.auto_status}
- overall_status: ${report.overall_status}
- final_status: ${report.final_status}
- mp4: ${report.mp4_path}
- generated_at: ${report.generated_at}

## Auto Checks

| status | code | expected | actual |
| --- | --- | --- | --- |
${autoRows}

## Representative Frames

| label | time | path |
| --- | --- | --- |
${frameRows}

## Manual Review Required

${manualRows}

> 자동 검사는 최종 승인과 다릅니다. 대표 프레임을 열어 개인정보, 자막 가림, 음성-자막-화면 싱크를 사람이 확인해야 최종 완료입니다.
`;
}

const mp4Path = path.resolve(requireArg("--mp4"));
const packageDir = path.resolve(requireArg("--package"));
const syncManifestPath = path.resolve(requireArg("--sync-manifest"));
const renderJobArgument = argValue("--render-job");
const isHyperframesOutput = path.basename(mp4Path).includes("_hyperframes_");
if (!renderJobArgument && !isHyperframesOutput) {
  die("Missing --render-job: standard HTML render QA requires a succeeded durable render job.");
}
const renderJobPath = renderJobArgument ? path.resolve(renderJobArgument) : null;
const reportDir = path.resolve(argValue("--report-dir") || path.join(packageDir, "_work", `render_post_qa_${new Date().toISOString().replace(/[:.]/g, "-")}`));

ensureInsideOutput(packageDir, "Review package");
ensureInsideOutput(mp4Path, "MP4");
ensureInsideOutput(syncManifestPath, "sync_manifest");
ensureInsideOutput(reportDir, "Report directory");
ensureInsidePackage(mp4Path, packageDir, "MP4");
ensureInsidePackage(syncManifestPath, packageDir, "sync_manifest");
ensureInsidePackage(reportDir, packageDir, "Report directory");
if (renderJobPath) {
  ensureInsideOutput(renderJobPath, "render_job");
  ensureInsidePackage(renderJobPath, packageDir, "render_job");
  const relativeJobPath = path.relative(canonicalPath(packageDir), canonicalPath(renderJobPath)).split(path.sep).join("/");
  if (!/^_work\/render_jobs\/[0-9]{8}T[0-9]{12}Z-[0-9a-f]{8}\/render_job\.json$/.test(relativeJobPath)) {
    die("render_job must use the package _work/render_jobs/<job-id>/render_job.json path.");
  }
}

if (!fs.existsSync(mp4Path)) die(`Missing MP4: ${mp4Path}`);
if (!fs.existsSync(syncManifestPath)) die(`Missing sync_manifest: ${syncManifestPath}`);
if (path.extname(mp4Path).toLowerCase() !== ".mp4") {
  die("MP4 path must end with .mp4.");
}
if (!path.basename(mp4Path).includes("upload_10mbps")) {
  die("MP4 filename must include upload_10mbps.");
}

const mp4Input = boundFileEvidence(mp4Path, packageDir);
const { evidence: syncManifestInput, value: syncManifest } = readBoundJson(syncManifestPath, packageDir);
let renderJobReport = null;
if (renderJobPath) {
  const { evidence: renderJobInput, value: renderJob } = readBoundJson(renderJobPath, packageDir);
  const bindings = renderJob.bindings;
  const outputEvidence = renderJob.output_evidence;
  if (!bindings || typeof bindings !== "object" || Array.isArray(bindings)) {
    die("render_job bindings are invalid.");
  }
  const actualBindingsHash = crypto.createHash("sha256").update(canonicalJson(bindings), "utf8").digest("hex");
  if (renderJob.bindings_sha256 !== actualBindingsHash) {
    die("render_job immutable bindings hash is invalid.");
  }
  if (renderJob.state !== "succeeded") {
    die("render_job state must be succeeded before post-render QA.");
  }
  if (path.resolve(bindings.package_path || "") !== packageDir) {
    die("render_job package binding does not match --package.");
  }
  if (path.resolve(bindings.output_path || "") !== mp4Path || path.resolve(outputEvidence?.path || "") !== mp4Path) {
    die("render_job output binding does not match --mp4.");
  }
  if (Number(outputEvidence?.bytes) !== mp4Input.bytes || outputEvidence?.sha256 !== mp4Input.sha256) {
    die("render_job output bytes/SHA-256 do not match the current MP4.");
  }
  if (path.resolve(bindings.sync_manifest_path || "") !== syncManifestPath || bindings.sync_manifest_sha256 !== syncManifestInput.sha256) {
    die("render_job sync manifest binding does not match the current sync manifest.");
  }
  renderJobReport = {
    relative_path: renderJobInput.relative_path,
    bytes: renderJobInput.bytes,
    sha256: renderJobInput.sha256,
    job_id: renderJob.job_id,
    state: renderJob.state,
    output_bytes: outputEvidence.bytes,
    output_sha256: outputEvidence.sha256,
  };
}
if (syncManifest.ok !== true) {
  die("sync_manifest.ok must be true for post-render QA.");
}
if (Array.isArray(syncManifest.issues) && syncManifest.issues.length > 0) {
  die("sync_manifest.issues must be empty for post-render QA.");
}
const syncAudio = syncManifest.audio || {};
const syncFinalVoiceDuration = numberValue(syncAudio.final_voice_duration_sec ?? syncManifest.final_voice_duration_sec);
if (!Number.isFinite(syncFinalVoiceDuration) || syncFinalVoiceDuration <= 0) {
  die("sync_manifest must include a positive final_voice_duration_sec for post-render QA.");
}
const syncTotalCps = numberValue(syncAudio.total_voice_cps ?? syncManifest.total_voice_cps);
if (!Number.isFinite(syncTotalCps)) {
  die("sync_manifest must include total_voice_cps for post-render QA.");
}
if (syncTotalCps >= 9.0) {
  die("sync_manifest total_voice_cps is too high for post-render QA.");
}
const syncScenes = syncManifest.scenes || syncManifest.beats || [];
if (!Array.isArray(syncScenes) || syncScenes.length === 0) {
  die("sync_manifest must include scene or beat meaning_match evidence for post-render QA.");
}
for (const [index, scene] of syncScenes.entries()) {
  if (scene.meaning_match !== true) {
    die(`sync_manifest scene[${index}] must have meaning_match: true for post-render QA.`);
  }
  const evidence = scene.meaning_match_evidence ?? scene.meaning_match_source;
  if (!evidence || !String(evidence).trim()) {
    die(`sync_manifest scene[${index}] must include meaning_match evidence for post-render QA.`);
  }
}

const ffprobe = runJsonCommand(
  "ffprobe",
  ["-v", "error", "-print_format", "json", "-show_format", "-show_streams", mp4Path],
  repoRoot,
  "ffprobe",
);

const streams = ffprobe.streams || [];
const video = streams.find((stream) => stream.codec_type === "video") || {};
const audio = streams.find((stream) => stream.codec_type === "audio") || {};
const format = ffprobe.format || {};
const duration = numberValue(format.duration || video.duration || syncManifest.audio?.final_voice_duration_sec);
const fps = ratioToNumber(video.avg_frame_rate || video.r_frame_rate);
const videoBitrate = numberValue(video.bit_rate || format.bit_rate);
const audioBitrate = numberValue(audio.bit_rate);
const audioSampleRate = numberValue(audio.sample_rate);
const finalVoiceDuration = syncFinalVoiceDuration;

const autoChecks = [
  check("MP4_CONTAINER", "mp4 container", String(format.format_name || "").includes("mp4"), "format_name includes mp4", String(format.format_name ?? "missing")),
  check("VIDEO_CODEC", "video codec", video.codec_name === "h264", "h264", String(video.codec_name ?? "missing")),
  check("VIDEO_PIXEL_FORMAT", "video pixel format", video.pix_fmt === "yuv420p", "yuv420p", String(video.pix_fmt ?? "missing")),
  check("VIDEO_WIDTH", "video width", Number(video.width) === 1080, "1080", String(video.width ?? "missing")),
  check("VIDEO_HEIGHT", "video height", Number(video.height) === 1920, "1920", String(video.height ?? "missing")),
  check("VIDEO_FPS", "video fps", Number.isFinite(fps) && fps >= 29.5 && fps <= 30.5, "29.5-30.5", Number.isFinite(fps) ? fps.toFixed(3) : "missing"),
  check("VIDEO_BITRATE", "video bitrate", Number.isFinite(videoBitrate) && videoBitrate >= 8_000_000 && videoBitrate <= 13_000_000, "8-13 Mbps", formatMbps(videoBitrate)),
  check("AUDIO_CODEC", "audio codec", audio.codec_name === "aac", "aac", String(audio.codec_name ?? "missing")),
  check("AUDIO_SAMPLE_RATE", "audio sample rate", audioSampleRate === 44100, "44100", String(audio.sample_rate ?? "missing")),
  check("AUDIO_CHANNELS", "audio channels", Number(audio.channels) === 2, "2", String(audio.channels ?? "missing")),
  check("AUDIO_BITRATE", "audio bitrate", Number.isFinite(audioBitrate) && audioBitrate >= 160_000 && audioBitrate <= 256_000, "160-256 kbps", Number.isFinite(audioBitrate) ? `${Math.round(audioBitrate / 1000)} kbps` : "missing"),
  check("DURATION_PRESENT", "duration present", Number.isFinite(duration) && duration > 0, "> 0 sec", Number.isFinite(duration) ? `${duration.toFixed(3)} sec` : "missing"),
  check("VOICE_DURATION_COMPATIBLE", "voice duration compatible", Number.isFinite(duration) && Math.abs(duration - finalVoiceDuration) <= 2.0, "mp4 duration within +/-2.0s of final voice duration", `mp4=${Number.isFinite(duration) ? duration.toFixed(3) : "missing"}, voice=${finalVoiceDuration.toFixed(3)}`),
];

const failedChecks = autoChecks.filter((item) => item.status === "fail");
const frames = extractRepresentativeFrames(mp4Path, reportDir, duration);
const mp4AfterFrames = boundFileEvidence(mp4Path, packageDir);
if (mp4AfterFrames.bytes !== mp4Input.bytes || mp4AfterFrames.sha256 !== mp4Input.sha256) {
  die("MP4 changed during representative frame extraction; post-render QA report was not written.");
}

const report = {
  schema_version: "1.2",
  generated_at: new Date().toISOString(),
  mp4_path: mp4Path,
  mp4_relative_path: mp4Input.relative_path,
  mp4_bytes: mp4Input.bytes,
  mp4_sha256: mp4Input.sha256,
  package_dir: packageDir,
  package_identity: {
    package_path: packageDir,
    package_name: path.basename(packageDir),
  },
  sync_manifest_path: syncManifestPath,
  sync_manifest_relative_path: syncManifestInput.relative_path,
  sync_manifest_bytes: syncManifestInput.bytes,
  sync_manifest_sha256: syncManifestInput.sha256,
  render_job: renderJobReport,
  auto_status: failedChecks.length === 0 ? "pass" : "fail",
  overall_status: failedChecks.length === 0 ? "manual_review_required" : "blocked",
  final_status: failedChecks.length === 0 ? "needs_human_review" : "blocked",
  ffprobe_summary: {
    format_name: format.format_name || null,
    duration_sec: Number.isFinite(duration) ? Number(duration.toFixed(3)) : null,
    bit_rate: Number.isFinite(numberValue(format.bit_rate)) ? numberValue(format.bit_rate) : null,
    video: {
      codec_name: video.codec_name || null,
      width: video.width || null,
      height: video.height || null,
      fps: Number.isFinite(fps) ? Number(fps.toFixed(3)) : null,
      bit_rate: Number.isFinite(videoBitrate) ? videoBitrate : null,
    },
    audio: {
      codec_name: audio.codec_name || null,
      sample_rate: audio.sample_rate || null,
      channels: audio.channels || null,
      bit_rate: Number.isFinite(audioBitrate) ? audioBitrate : null,
    },
  },
  auto_checks: autoChecks,
  representative_frames: frames,
  manual_review: {
    status: "pending",
    checks: [
      "대표 프레임 5장 모두에서 자막 크기/위치/가림 확인",
      "주소/건물명/동호수/차량번호/송장/전화번호 노출 확인",
      "가족사진/얼굴/유리 반사 얼굴 노출 확인",
      "리뷰 캡처 개인정보와 과도한 원문 노출 확인",
      "음성-자막-화면 의미 싱크 확인",
      "첫 후킹, 중반 제품/실측, 후반 리뷰 증명, 마지막 CTA 흐름 확인",
    ],
  },
};

fs.mkdirSync(reportDir, { recursive: true });
const jsonPath = path.join(reportDir, "render_post_qa_report.json");
const markdownPath = path.join(reportDir, "render_post_qa_report.md");
writeJson(jsonPath, report);
fs.writeFileSync(markdownPath, renderMarkdown(report), "utf8");

console.log(`Render post QA report: ${jsonPath}`);
console.log(`Manual review status: ${report.manual_review.status}`);
if (failedChecks.length > 0) {
  console.error(`Render post QA failed: ${failedChecks.map((item) => item.code).join(", ")}`);
  process.exit(2);
}
