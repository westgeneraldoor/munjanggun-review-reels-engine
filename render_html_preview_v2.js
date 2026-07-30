const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const { pathToFileURL } = require('url');
const { chromium } = require('playwright');

const REPO_ROOT = path.resolve(__dirname);

function die(message) {
  console.error(message);
  process.exit(2);
}

function argValue(name, fallback = null) {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && idx + 1 < process.argv.length ? process.argv[idx + 1] : fallback;
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
  return fs.existsSync(filePath) ? fs.readFileSync(filePath, 'utf8') : '';
}

function readJson(filePath, label) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (error) {
    die(`Invalid ${label}: ${filePath}\n${error.message}`);
  }
}

function isInside(parent, candidate) {
  const relative = path.relative(parent, candidate);
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
}

function ensureInsideOutput(targetPath, label) {
  if (!isInside(REPO_ROOT, targetPath)) die(`${label} must stay inside this repository.`);
  const relative = path.relative(REPO_ROOT, targetPath);
  if (relative.split(path.sep)[0] !== 'output') {
    die(`${label} must be under output/ because it may contain customer media.`);
  }
}

function parseBooleanLine(text, key) {
  const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = text.match(new RegExp(`${escaped}\\s*:\\s*(true|false)`, 'i'));
  return match ? match[1].toLowerCase() === 'true' : null;
}

function approvalScopes(text) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => /^-?\s*approved_scope\s*:/i.test(line))
    .map((line) => line.replace(/^-?\s*approved_scope\s*:\s*/i, ''));
}

function hasPositiveApprovalScope(text, pattern) {
  return approvalScopes(text).some((scope) => {
    if (/없음|none|not approved|미승인|보류|pending/i.test(scope)) return false;
    return pattern.test(scope);
  });
}

function validatePackageApproval(packageDir) {
  const statusPath = path.join(packageDir, 'STATUS.md');
  const approvalPath = path.join(packageDir, 'APPROVAL_LOG.md');
  if (!fs.existsSync(statusPath)) die(`Missing STATUS.md: ${statusPath}`);
  if (!fs.existsSync(approvalPath)) die(`Missing APPROVAL_LOG.md: ${approvalPath}`);

  const status = readText(statusPath);
  const approval = readText(approvalPath);
  if (parseBooleanLine(status, 'html_approved_by_user') !== true) {
    die('STATUS.md must contain html_approved_by_user: true before HTML-to-MP4 render.');
  }
  if (parseBooleanLine(status, 'mp4_allowed') !== true) {
    die('STATUS.md must contain mp4_allowed: true before HTML-to-MP4 render.');
  }
  if (!hasPositiveApprovalScope(approval, /HTML|html|프리뷰|preview/i)) {
    die('APPROVAL_LOG.md must record a positive approved_scope for HTML preview.');
  }
  if (!hasPositiveApprovalScope(approval, /(?=.*\bMP4\b)(?=.*(렌더|render|승인|approved))/i)) {
    die('APPROVAL_LOG.md must record a positive approved_scope for explicit MP4 render approval.');
  }
}

function validateSyncManifest(syncManifestPath) {
  const manifest = readJson(syncManifestPath, 'sync manifest');
  if (manifest.ok !== true) die('sync_manifest.ok must be true before HTML-to-MP4 render.');
  if (Array.isArray(manifest.issues) && manifest.issues.length > 0) {
    die('sync_manifest.issues must be empty before HTML-to-MP4 render.');
  }
  const audio = manifest.audio || {};
  const finalDuration = Number(audio.final_voice_duration_sec ?? manifest.final_voice_duration_sec);
  const totalCps = Number(audio.total_voice_cps ?? manifest.total_voice_cps);
  if (!Number.isFinite(finalDuration) || finalDuration <= 0) {
    die('sync_manifest must include a positive final_voice_duration_sec.');
  }
  if (!Number.isFinite(totalCps) || totalCps >= 9.0) {
    die('sync_manifest total_voice_cps must be present and below 9.0.');
  }
  const scenes = manifest.scenes || manifest.beats || [];
  if (!Array.isArray(scenes) || scenes.length === 0) {
    die('sync_manifest must include beat-level meaning_match evidence.');
  }
  for (const [index, scene] of scenes.entries()) {
    const evidence = scene.meaning_match_evidence ?? scene.meaning_match_source;
    if (scene.meaning_match !== true || !String(evidence || '').trim()) {
      die(`sync_manifest scene[${index}] must include meaning_match: true and evidence.`);
    }
  }
}

function validateHtmlQa(htmlQaPath) {
  const report = readJson(htmlQaPath, 'HTML preview QA report');
  if (report.ok !== true) die('HTML preview QA report must have ok: true before MP4 render.');
  const failedChecks = (report.checks || []).filter((check) => check && check.ok === false);
  if (failedChecks.length > 0) die('HTML preview QA report contains failed representative-frame checks.');
}

function cleanupGeneratedFrames(framePaths, frameDir) {
  for (const framePath of framePaths) {
    if (fs.existsSync(framePath)) fs.unlinkSync(framePath);
  }
  if (fs.existsSync(frameDir)) fs.rmdirSync(frameDir);
}

async function renderApprovedHtml({ htmlPath, outputPath, packageDir, fps, width, height, designWidth, keepFrames }) {
  const designHeight = designWidth * height / width;
  const deviceScaleFactor = width / designWidth;
  const workDir = path.join(packageDir, '_work');
  fs.mkdirSync(workDir, { recursive: true });
  const frameDir = path.join(workDir, `${path.basename(outputPath, path.extname(outputPath))}_frames_${process.pid}_${Date.now()}`);
  fs.mkdirSync(frameDir);
  const framePaths = [];

  const launchOptions = { headless: true };
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) {
    launchOptions.executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  }
  const browser = await chromium.launch(launchOptions);
  let meta;
  try {
    const page = await browser.newPage({
      viewport: { width: Math.round(designWidth), height: Math.round(designHeight) },
      deviceScaleFactor,
    });
    await page.goto(pathToFileURL(htmlPath).href);
    await page.waitForLoadState('load');
    await page.evaluate(({ stageWidth, stageHeight }) => {
      document.documentElement.style.setProperty('--stage-w', `${stageWidth}px`);
      document.body.style.margin = '0';
      document.body.style.padding = '0';
      document.body.style.width = `${stageWidth}px`;
      document.body.style.height = `${stageHeight}px`;
      document.body.style.minHeight = `${stageHeight}px`;
      document.body.style.overflow = 'hidden';
      document.body.style.display = 'block';
      document.body.style.background = '#000';
      const side = document.querySelector('.side');
      if (side) side.style.display = 'none';
      const shell = document.querySelector('.preview-shell');
      if (shell) Object.assign(shell.style, { position: 'fixed', inset: '0', width: `${stageWidth}px`, height: `${stageHeight}px`, minHeight: `${stageHeight}px`, display: 'block', overflow: 'hidden' });
      const phone = document.querySelector('.phone');
      if (phone) Object.assign(phone.style, { position: 'absolute', inset: '0', width: `${stageWidth}px`, height: `${stageHeight}px`, borderRadius: '0', boxShadow: 'none' });
    }, { stageWidth: designWidth, stageHeight: designHeight });
    meta = await page.evaluate(() => {
      const currentRecipe = typeof recipe !== 'undefined' ? recipe : window.recipe;
      const beats = currentRecipe?.beats || [];
      return { duration: Math.max(...beats.map((beat) => beat.time[1])), voiceSrc: document.getElementById('audio')?.src || null };
    });
    const stage = page.locator('.stage');
    await stage.waitFor({ state: 'visible', timeout: 5000 });
    const frameCount = Math.ceil(meta.duration * fps);
    for (let index = 0; index < frameCount; index += 1) {
      await page.evaluate((time) => renderAt(time), Math.min(index / fps, meta.duration));
      const framePath = path.join(frameDir, `frame_${String(index + 1).padStart(5, '0')}.png`);
      await stage.screenshot({ path: framePath });
      framePaths.push(framePath);
    }
  } finally {
    await browser.close();
  }

  const audioPath = meta.voiceSrc && meta.voiceSrc.startsWith('file:///')
    ? decodeURIComponent(new URL(meta.voiceSrc).pathname).replace(/^\/([A-Za-z]:)/, '$1')
    : null;
  const ffmpegArgs = ['-n', '-framerate', String(fps), '-i', path.join(frameDir, 'frame_%05d.png')];
  if (audioPath && fs.existsSync(audioPath)) ffmpegArgs.push('-i', audioPath, '-map', '0:v:0', '-map', '1:a:0', '-shortest');
  ffmpegArgs.push('-vf', `scale=${width}:${height}:flags=lanczos,setsar=1`, '-c:v', 'libx264', '-preset', 'slow', '-b:v', argValue('--video-bitrate', '11000k'), '-maxrate', argValue('--maxrate', '12000k'), '-bufsize', argValue('--bufsize', '24000k'), '-pix_fmt', 'yuv420p', '-r', String(fps), '-c:a', 'aac', '-b:a', argValue('--audio-bitrate', '192k'), '-ar', argValue('--audio-sample-rate', '44100'), '-ac', argValue('--audio-channels', '2'), '-movflags', '+faststart', outputPath);
  const ffmpeg = spawnSync('ffmpeg', ffmpegArgs, { stdio: 'inherit', shell: process.platform === 'win32' });
  if (ffmpeg.status !== 0) die(`ffmpeg failed with exit ${ffmpeg.status || 1}; generated frames were preserved at ${frameDir}.`);
  if (!keepFrames) cleanupGeneratedFrames(framePaths, frameDir);
}

async function main() {
  const htmlPath = path.resolve(requireArg('--html'));
  const outputPath = path.resolve(requireArg('--out'));
  const packageDir = path.resolve(requireArg('--package'));
  const syncManifestPath = path.resolve(requireArg('--sync-manifest'));
  const htmlQaPath = path.resolve(requireArg('--html-qa'));
  const renderApproved = hasFlag('--render-approved');
  const fps = Number(argValue('--fps', '30'));
  const width = Number(argValue('--width', '1080'));
  const height = Number(argValue('--height', '1920'));
  const designWidth = Number(argValue('--design-width', '390'));

  ensureInsideOutput(packageDir, 'Review package');
  ensureInsideOutput(htmlPath, 'HTML preview');
  ensureInsideOutput(outputPath, 'MP4 output');
  ensureInsideOutput(syncManifestPath, 'sync_manifest');
  ensureInsideOutput(htmlQaPath, 'HTML preview QA report');
  if (!isInside(packageDir, htmlPath) || !isInside(packageDir, outputPath) || !isInside(packageDir, syncManifestPath) || !isInside(packageDir, htmlQaPath)) {
    die('HTML preview, MP4 output, sync_manifest, and HTML QA report must stay inside the approved review package.');
  }
  if (path.extname(outputPath).toLowerCase() !== '.mp4' || !path.basename(outputPath).includes('upload_10mbps')) {
    die('MP4 output must end with .mp4 and include upload_10mbps in its filename.');
  }
  if (!fs.existsSync(htmlPath) || !fs.existsSync(syncManifestPath) || !fs.existsSync(htmlQaPath)) {
    die('HTML preview, sync_manifest, and HTML preview QA report must exist before render.');
  }
  if (fs.existsSync(outputPath)) die(`Refusing to overwrite existing MP4: ${outputPath}`);

  validatePackageApproval(packageDir);
  validateSyncManifest(syncManifestPath);
  validateHtmlQa(htmlQaPath);
  if (!renderApproved) {
    console.log('HTML-to-MP4 render gate passed in dry-run mode.');
    console.log('No MP4 was rendered because --render-approved was not provided.');
    return;
  }

  await renderApprovedHtml({ htmlPath, outputPath, packageDir, fps, width, height, designWidth, keepFrames: hasFlag('--keep-frames') });
  console.log(`Rendered ${outputPath}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
