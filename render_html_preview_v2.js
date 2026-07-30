const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const { pathToFileURL } = require('url');

function die(message) {
  console.error(message);
  process.exit(2);
}

function argValue(name, fallback = null) {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && idx + 1 < process.argv.length ? process.argv[idx + 1] : fallback;
}

function requireArg(name) {
  const value = argValue(name);
  if (!value) {
    die(`Missing ${name}`);
  }
  return value;
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function readGateReceipt(receiptPath) {
  try {
    return JSON.parse(fs.readFileSync(receiptPath, 'utf8'));
  } catch (error) {
    die(`Invalid gate receipt: ${receiptPath}`);
  }
}

function sha256(filePath) {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

function compactReceiptHash(receiptHash) {
  return Buffer.from(receiptHash, 'hex').toString('base64')
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function receiptBoundary(receiptPath, receipt) {
  if (typeof receipt?.package_path !== 'string' || !receipt.package_path.trim()) {
    throw new Error('GATE_RECEIPT_INVALID');
  }
  const requestedPackagePath = path.resolve(receipt.package_path);
  if (!fs.existsSync(requestedPackagePath)) {
    throw new Error('GATE_RECEIPT_INVALID');
  }
  const packagePath = fs.realpathSync.native(requestedPackagePath);
  if (typeof receipt?.issued_at !== 'string' || !receipt.issued_at.trim()) {
    throw new Error('GATE_RECEIPT_INVALID');
  }
  const receiptDir = fs.realpathSync.native(path.resolve(packagePath, '_work', 'production_gates'));
  const realReceiptPath = fs.realpathSync.native(path.resolve(receiptPath));
  if (path.dirname(realReceiptPath) !== receiptDir) {
    throw new Error('GATE_RECEIPT_OUTSIDE_OFFICIAL_DIR');
  }
  const receiptHash = sha256(realReceiptPath);
  return {
    packagePath,
    receiptHash,
    markerPath: path.join(receiptDir, 'consumed', `${compactReceiptHash(receiptHash)}.json`),
    legacyMarkerPath: path.join(receiptDir, 'consumed', `${receiptHash}.json`),
  };
}

function assertGateReceiptAvailable(receiptPath, receipt) {
  const boundary = receiptBoundary(receiptPath, receipt);
  if (fs.existsSync(boundary.markerPath) || fs.existsSync(boundary.legacyMarkerPath)) {
    throw new Error('GATE_RECEIPT_ALREADY_CONSUMED');
  }
  return boundary;
}

function consumeGateReceipt(receiptPath, receipt) {
  const boundary = assertGateReceiptAvailable(receiptPath, receipt);
  fs.mkdirSync(path.dirname(boundary.markerPath), { recursive: true });
  let descriptor;
  try {
    descriptor = fs.openSync(boundary.markerPath, 'wx');
    fs.writeFileSync(descriptor, `${JSON.stringify({
      schema_version: '1.0',
      action: receipt.action,
      receipt_sha256: boundary.receiptHash,
      receipt_issued_at: receipt.issued_at,
      consumed_at: new Date().toISOString(),
    }, null, 2)}\n`, 'utf8');
  } catch (error) {
    if (error?.code === 'EEXIST') throw new Error('GATE_RECEIPT_ALREADY_CONSUMED');
    throw error;
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
  }
  return boundary.markerPath;
}

function ensureContainedPath(root, relativePath, label) {
  if (typeof relativePath !== 'string' || !relativePath || path.isAbsolute(relativePath)) {
    die(`Invalid ${label} dependency path.`);
  }
  const resolvedRoot = path.resolve(root);
  const resolvedPath = path.resolve(resolvedRoot, relativePath);
  if (resolvedPath === resolvedRoot || !resolvedPath.startsWith(`${resolvedRoot}${path.sep}`)) {
    die(`${label} dependency path escapes its allowed root.`);
  }
  if (!fs.existsSync(resolvedPath)) die(`Missing ${label} dependency: ${relativePath}`);
  const realRoot = fs.realpathSync.native(resolvedRoot);
  const realPath = fs.realpathSync.native(resolvedPath);
  if (realPath === realRoot || !realPath.startsWith(`${realRoot}${path.sep}`)) {
    die(`${label} dependency real path escapes its allowed root.`);
  }
  return resolvedPath;
}

function validateRenderDependencies(receipt) {
  const packagePath = receipt.package_path;
  if (typeof packagePath !== 'string' || !packagePath || !fs.existsSync(packagePath)) {
    die('Gate receipt package path is invalid.');
  }
  const dependencies = receipt.render_dependencies;
  if (!Array.isArray(dependencies) || dependencies.length < 3) {
    die('Gate receipt render dependencies are missing.');
  }
  const seen = new Set();
  const kinds = new Map();
  for (const dependency of dependencies) {
    const { kind, scope, relative_path: relativePath, bytes, sha256: expectedHash } = dependency || {};
    if (!['image', 'voice', 'font'].includes(kind) || !['package', 'repository'].includes(scope)
      || !Number.isInteger(bytes) || bytes < 0 || !/^[0-9a-f]{64}$/.test(expectedHash || '')) {
      die('Gate receipt render dependency is invalid.');
    }
    if ((kind === 'font') !== (scope === 'repository') || (kind !== 'font' && scope !== 'package')) {
      die('Gate receipt render dependency scope is invalid.');
    }
    const key = `${kind}:${scope}:${relativePath}`;
    if (seen.has(key)) die('Gate receipt contains duplicate render dependencies.');
    seen.add(key);
    kinds.set(kind, (kinds.get(kind) || 0) + 1);
    const dependencyPath = ensureContainedPath(
      scope === 'package' ? packagePath : __dirname,
      relativePath,
      kind,
    );
    if (fs.statSync(dependencyPath).size !== bytes || sha256(dependencyPath) !== expectedHash) {
      die(`Gate receipt ${kind} dependency hash does not match the current file.`);
    }
  }
  if (!kinds.get('image') || kinds.get('voice') !== 1 || kinds.get('font') !== 1) {
    die('Gate receipt render dependency set is incomplete.');
  }
}

function validateGateReceipt(receipt, receiptPath, htmlPath, outputPath, preset) {
  if (receipt?.action !== 'render') die('Gate receipt is not a render receipt.');
  try {
    assertGateReceiptAvailable(receiptPath, receipt);
  } catch (error) {
    die(error.message);
  }
  if (path.resolve(receipt.html_path || '') !== htmlPath) die('Gate receipt HTML path does not match --html.');
  if (!fs.existsSync(htmlPath)) die(`Missing HTML preview: ${htmlPath}`);
  const expectedHtmlHash = receipt.html_sha256;
  const actualHtmlHash = sha256(htmlPath);
  if (!/^[0-9a-f]{64}$/.test(expectedHtmlHash || '') || expectedHtmlHash !== actualHtmlHash) {
    die('Gate receipt HTML hash does not match the current HTML preview.');
  }
  validateRenderDependencies(receipt);
  if (path.resolve(receipt.output_path || '') !== outputPath) die('Gate receipt output path does not match --out.');
  const receiptPreset = receipt.preset || {};
  for (const [key, value] of Object.entries(preset)) {
    if (receiptPreset[key] !== value) die(`Gate receipt final preset does not match ${key}.`);
  }
}

function validateFinalPreset({ fps, width, height, videoBitrate, maxrate, bufsize, audioBitrate, audioSampleRate, audioChannels }) {
  if (
    fps !== 30 || width !== 1080 || height !== 1920 || videoBitrate !== '11000k' || maxrate !== '12000k'
    || bufsize !== '24000k' || audioBitrate !== '192k' || audioSampleRate !== '44100' || audioChannels !== '2'
  ) {
    die('Final render preset must be 1080x1920, 30fps, H.264/yuv420p, AAC 44.1kHz stereo at the approved bitrate.');
  }
}

async function main() {
  const htmlPath = path.resolve(requireArg('--html'));
  const outputPath = path.resolve(requireArg('--out'));
  const receiptPath = path.resolve(requireArg('--gate-receipt'));
  const fps = Number(argValue('--fps', '30'));
  const width = Number(argValue('--width', '1080'));
  const height = Number(argValue('--height', '1920'));
  const designWidth = Number(argValue('--design-width', '390'));
  const videoBitrate = argValue('--video-bitrate', '11000k');
  const maxrate = argValue('--maxrate', '12000k');
  const bufsize = argValue('--bufsize', '24000k');
  const audioBitrate = argValue('--audio-bitrate', '192k');
  const audioSampleRate = argValue('--audio-sample-rate', '44100');
  const audioChannels = argValue('--audio-channels', '2');
  const designHeight = designWidth * height / width;
  const deviceScaleFactor = width / designWidth;
  const approvedPreset = {
    width: 1080,
    height: 1920,
    fps: 30,
    video_bitrate: '11000k',
    maxrate: '12000k',
    bufsize: '24000k',
    audio_bitrate: '192k',
    audio_sample_rate: 44100,
    audio_channels: 2,
    video_codec: 'h264',
    pixel_format: 'yuv420p',
  };
  const receipt = readGateReceipt(receiptPath);
  validateGateReceipt(receipt, receiptPath, htmlPath, outputPath, approvedPreset);
  validateFinalPreset({ fps, width, height, videoBitrate, maxrate, bufsize, audioBitrate, audioSampleRate, audioChannels });
  if (!fs.existsSync(htmlPath)) die(`Missing HTML preview: ${htmlPath}`);
  if (fs.existsSync(outputPath)) die(`Refusing to overwrite existing MP4: ${outputPath}`);

  const outputDir = path.dirname(outputPath);
  const frameDir = path.join(outputDir, `${path.basename(outputPath, path.extname(outputPath))}_frames`);
  if (fs.existsSync(frameDir)) die(`Refusing to overwrite existing frame directory: ${frameDir}`);
  try {
    consumeGateReceipt(receiptPath, receipt);
  } catch (error) {
    die(error.message);
  }
  ensureDir(outputDir);
  ensureDir(frameDir);

  const { chromium } = require('playwright');

  const launchOptions = { headless: true };
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) {
    launchOptions.executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  }
  const browser = await chromium.launch(launchOptions);
  const page = await browser.newPage({
    viewport: { width: Math.round(designWidth), height: Math.round(designHeight) },
    deviceScaleFactor,
  });

  await page.goto(pathToFileURL(htmlPath).href);
  await page.waitForLoadState('load');
  await page.evaluate(({ width, height }) => {
    document.documentElement.style.setProperty('--stage-w', `${width}px`);
    document.body.style.margin = '0';
    document.body.style.padding = '0';
    document.body.style.width = `${width}px`;
    document.body.style.height = `${height}px`;
    document.body.style.minHeight = `${height}px`;
    document.body.style.overflow = 'hidden';
    document.body.style.display = 'block';
    document.body.style.background = '#000';

    const side = document.querySelector('.side');
    if (side) side.style.display = 'none';

    const shell = document.querySelector('.preview-shell');
    if (shell) {
      Object.assign(shell.style, {
        position: 'fixed',
        inset: '0',
        width: `${width}px`,
        height: `${height}px`,
        minHeight: `${height}px`,
        display: 'block',
        overflow: 'hidden',
      });
    }

    const phone = document.querySelector('.phone');
    if (phone) {
      Object.assign(phone.style, {
        position: 'absolute',
        inset: '0',
        width: `${width}px`,
        height: `${height}px`,
        borderRadius: '0',
        boxShadow: 'none',
      });
    }
  }, { width: designWidth, height: designHeight });

  const meta = await page.evaluate(() => {
    const currentRecipe = typeof recipe !== 'undefined' ? recipe : window.recipe;
    const beats = currentRecipe?.beats || [];
    const duration = Math.max(...beats.map((b) => b.time[1]));
    const audio = document.getElementById('audio');
    return {
      duration,
      voiceSrc: audio?.src || null,
      title: currentRecipe?.title || document.title || 'preview',
    };
  });

  const frameCount = Math.ceil(meta.duration * fps);
  const stage = page.locator('.stage');
  await stage.waitFor({ state: 'visible', timeout: 5000 });

  for (let i = 0; i < frameCount; i++) {
    const time = Math.min(i / fps, meta.duration);
    await page.evaluate((t) => {
      renderAt(t);
    }, time);
    const framePath = path.join(frameDir, `frame_${String(i + 1).padStart(5, '0')}.png`);
    await stage.screenshot({ path: framePath });
    if ((i + 1) % Math.max(1, Math.floor(fps * 5)) === 0 || i + 1 === frameCount) {
      console.log(`${path.basename(outputPath)}: ${i + 1}/${frameCount} frames`);
    }
  }

  await browser.close();

  const audioPath = meta.voiceSrc && meta.voiceSrc.startsWith('file:///')
    ? decodeURIComponent(new URL(meta.voiceSrc).pathname).replace(/^\/([A-Za-z]:)/, '$1')
    : null;

  const ffmpegArgs = [
    '-n',
    '-framerate', String(fps),
    '-i', path.join(frameDir, 'frame_%05d.png'),
  ];

  if (audioPath && fs.existsSync(audioPath)) {
    ffmpegArgs.push('-i', audioPath, '-map', '0:v:0', '-map', '1:a:0', '-shortest');
  }

  ffmpegArgs.push(
    '-vf', `scale=${width}:${height}:flags=lanczos,setsar=1`,
    '-c:v', 'libx264',
    '-preset', 'slow',
    '-b:v', videoBitrate,
    '-maxrate', maxrate,
    '-bufsize', bufsize,
    '-pix_fmt', 'yuv420p',
    '-r', String(fps),
    '-c:a', 'aac',
    '-b:a', audioBitrate,
    '-ar', audioSampleRate,
    '-ac', audioChannels,
    '-movflags', '+faststart',
    outputPath,
  );

  const ffmpeg = spawnSync('ffmpeg', ffmpegArgs, { stdio: 'inherit' });
  if (ffmpeg.status !== 0) process.exit(ffmpeg.status || 1);

  console.log(outputPath);
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}

module.exports = {
  assertGateReceiptAvailable,
  consumeGateReceipt,
};
