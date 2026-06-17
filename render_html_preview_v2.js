const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const { pathToFileURL } = require('url');
const { chromium } = require('playwright');

function argValue(name, fallback = null) {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && idx + 1 < process.argv.length ? process.argv[idx + 1] : fallback;
}

function requireArg(name) {
  const value = argValue(name);
  if (!value) {
    console.error(`Missing ${name}`);
    process.exit(2);
  }
  return value;
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

async function main() {
  const htmlPath = path.resolve(requireArg('--html'));
  const outputPath = path.resolve(requireArg('--out'));
  const fps = Number(argValue('--fps', '24'));
  const width = Number(argValue('--width', '720'));
  const height = Number(argValue('--height', '1280'));
  const designWidth = Number(argValue('--design-width', '390'));
  const videoBitrate = argValue('--video-bitrate', '11000k');
  const maxrate = argValue('--maxrate', '12000k');
  const bufsize = argValue('--bufsize', '24000k');
  const audioBitrate = argValue('--audio-bitrate', '192k');
  const audioSampleRate = argValue('--audio-sample-rate', '44100');
  const audioChannels = argValue('--audio-channels', '2');
  const designHeight = designWidth * height / width;
  const deviceScaleFactor = width / designWidth;
  const keepFrames = process.argv.includes('--keep-frames');

  const outputDir = path.dirname(outputPath);
  const frameDir = path.join(outputDir, `${path.basename(outputPath, path.extname(outputPath))}_frames`);
  ensureDir(outputDir);
  if (fs.existsSync(frameDir)) fs.rmSync(frameDir, { recursive: true, force: true });
  ensureDir(frameDir);

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
    '-y',
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

  if (!keepFrames) fs.rmSync(frameDir, { recursive: true, force: true });
  console.log(outputPath);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
