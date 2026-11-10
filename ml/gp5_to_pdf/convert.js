#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const DEFAULT_TIMEOUT_MS = 90_000;
// Pages are served from this made-up origin through Playwright routing.
// Every other request is blocked, so the score never leaves this machine.
const ORIGIN = 'http://gp5-to-pdf.local';
// The package does not export package.json, so find it from its main entry.
const ALPHATAB_DIR = path.resolve(path.dirname(require.resolve('@coderline/alphatab')), '..');
const ALPHATAB_VERSION = JSON.parse(fs.readFileSync(path.join(ALPHATAB_DIR, 'package.json'), 'utf8')).version;

// A4 is 794 px wide at 96 dpi. The PDF margins below leave 718 px for the score.
const PAGE_MARGIN_MM = 10;
const SCORE_WIDTH_PX = 718;
const SCORE_SCALE = 0.75;

function usage() {
  return 'Usage: node convert.js INPUT.gp5 OUTPUT.pdf [--chrome PATH] [--timeout-ms N] [--force]';
}

function parseArgs(argv) {
  if (argv.length < 2) throw new Error(usage());
  const [inputArg, outputArg, ...options] = argv;
  const args = {
    input: path.resolve(inputArg),
    output: path.resolve(outputArg),
    timeoutMs: DEFAULT_TIMEOUT_MS,
    chrome: undefined,
    force: false,
  };
  for (let i = 0; i < options.length; i += 1) {
    const option = options[i];
    if (option === '--force') args.force = true;
    else if (option === '--chrome') args.chrome = options[++i];
    else if (option === '--timeout-ms') args.timeoutMs = Number(options[++i]);
    else throw new Error(`Unknown option: ${option}\n${usage()}`);
  }
  if (path.extname(args.input).toLowerCase() !== '.gp5') {
    throw new Error('Input must be a .gp5 file.');
  }
  if (path.extname(args.output).toLowerCase() !== '.pdf') {
    throw new Error('Output must be a .pdf file.');
  }
  if (!fs.existsSync(args.input) || !fs.statSync(args.input).isFile() || fs.statSync(args.input).size === 0) {
    throw new Error(`Input GP5 file is missing or empty: ${args.input}`);
  }
  if (args.input === args.output) throw new Error('Input and output paths must differ.');
  if (fs.existsSync(args.output) && !args.force) {
    throw new Error(`Output exists (use --force to replace it): ${args.output}`);
  }
  if (args.chrome && !fs.existsSync(args.chrome)) {
    throw new Error(`Chrome executable does not exist: ${args.chrome}`);
  }
  if (!Number.isInteger(args.timeoutMs) || args.timeoutMs < 1000) {
    throw new Error('--timeout-ms must be an integer of at least 1000.');
  }
  return args;
}

const PAGE_HTML = `<!doctype html>
<html><head><meta charset="utf-8">
<style>
  @page { size: A4; margin: ${PAGE_MARGIN_MM}mm; }
  html, body { margin: 0; background: #fff; }
  h1 { font: 600 14px/1.3 sans-serif; margin: 0 0 6px; }
  h1:not(:first-child) { break-before: page; }
  .tuning { font: 11px/1.3 sans-serif; margin: 0 0 6px; }
  .track { width: ${SCORE_WIDTH_PX}px; }
  /* Rows of the score are moved into normal flow so that a page break never cuts a system. */
  .row { position: relative; break-inside: avoid; }
  .row > div { position: absolute !important; }
</style>
<script src="/alphatab/alphaTab.min.js"></script>
</head><body></body></html>`;

const MIME = {
  '.js': 'text/javascript', '.mjs': 'text/javascript', '.woff2': 'font/woff2', '.woff': 'font/woff',
  '.otf': 'font/otf', '.eot': 'application/vnd.ms-fontobject', '.svg': 'image/svg+xml',
};

/** Serves the page, alphaTab and its music font from node_modules; blocks everything else. */
async function routeLocalFiles(context, gp5) {
  await context.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== ORIGIN) return route.abort('blockedbyclient');
    if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: PAGE_HTML });
    if (url.pathname === '/input.gp5') return route.fulfill({ contentType: 'application/octet-stream', body: gp5 });
    if (url.pathname.startsWith('/alphatab/')) {
      const file = path.join(ALPHATAB_DIR, 'dist', path.normalize(url.pathname.slice('/alphatab/'.length)));
      if (file.startsWith(path.join(ALPHATAB_DIR, 'dist')) && fs.existsSync(file)) {
        return route.fulfill({ contentType: MIME[path.extname(file)] || 'application/octet-stream', body: fs.readFileSync(file) });
      }
    }
    return route.fulfill({ status: 404, body: '' });
  });
}

/** Runs in the page: renders every track one after another and returns the track names. */
async function renderAllTracks({ scale, width }) {
  const at = window.alphaTab;
  const bytes = new Uint8Array(await (await fetch('/input.gp5')).arrayBuffer());
  const settings = () => {
    const s = new at.Settings();
    s.core.fontDirectory = '/alphatab/font/';
    s.core.useWorkers = false;
    s.core.enableLazyLoading = false;
    s.core.includeNoteBounds = false;
    s.player.enablePlayer = false;
    s.display.layoutMode = at.LayoutMode.Page;
    s.display.scale = scale;
    return s;
  };
  const score = at.importer.ScoreLoader.loadScoreFromBytes(bytes, settings());
  if (!score.tracks.length) throw new Error('No GP5 tracks found.');
  // alphaTab cuts long track names off beside the staff, so the name is printed as a heading instead.
  score.stylesheet.singleTrackTrackNamePolicy = at.model.TrackNamePolicy.Hidden;
  const songTitle = [score.title, score.artist].map((t) => (t || '').trim()).filter(Boolean).join(' - ');
  const pitchName = (pitch, preferFlats) => {
    const names = preferFlats
      ? ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']
      : ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
    return names[((pitch % 12) + 12) % 12];
  };
  const standardTunings = [
    [64, 59, 55, 50, 45, 40], // six-string guitar, top TAB line first
    [43, 38, 33, 28],         // four-string bass
    [43, 38, 33, 28, 23],     // five-string bass
  ];
  const isCommonDownTuning = (tuning) => standardTunings.some((standard) =>
    tuning.length === standard.length && [1, 2, 3, 4].some((semitones) =>
      standard.every((pitch, i) => tuning[i] === pitch - semitones)));

  for (let index = 0; index < score.tracks.length; index += 1) {
    const holder = document.createElement('div');
    holder.className = 'track';
    holder.style.width = `${width}px`;
    const heading = document.createElement('h1');
    heading.textContent = [songTitle, score.tracks[index].name].filter(Boolean).join(' · ');
    document.body.appendChild(heading);
    const tuning = score.tracks[index].staves[0]?.tuning;
    if (tuning?.length) {
      const label = document.createElement('p');
      label.className = 'tuning';
      const pitches = Array.from(tuning);
      const preferFlats = isCommonDownTuning(pitches);
      label.textContent = `String tuning (top to bottom): ${pitches.map((pitch) => pitchName(pitch, preferFlats)).join(' · ')}`;
      document.body.appendChild(label);
    }
    document.body.appendChild(holder);
    const api = new at.AlphaTabApi(holder, settings());
    await new Promise((resolve, reject) => {
      api.postRenderFinished.on(resolve);
      api.error.on((e) => reject(new Error(e?.message || String(e))));
      api.renderScore(score, [index]);
    });

    // alphaTab places each rendered chunk absolutely. Group chunks that share
    // a top edge into rows, then stack the rows in normal flow.
    const surface = holder.querySelector('.at-surface');
    const chunks = [...surface.children].filter((el) => el.tagName === 'DIV');
    const rows = new Map();
    for (const chunk of chunks) {
      const top = Math.round(parseFloat(chunk.style.top) || 0);
      if (!rows.has(top)) rows.set(top, []);
      rows.get(top).push(chunk);
    }
    // Rows stay inside the surface: alphaTab's music-font CSS only applies there.
    const flow = surface;
    for (const top of [...rows.keys()].sort((a, b) => a - b)) {
      const row = document.createElement('div');
      row.className = 'row';
      let height = 0;
      for (const chunk of rows.get(top)) {
        height = Math.max(height, parseFloat(chunk.style.height) || chunk.getBoundingClientRect().height);
        chunk.style.top = '0px';
        row.appendChild(chunk);
      }
      row.style.height = `${Math.ceil(height)}px`;
      flow.appendChild(row);
    }
    surface.style.height = 'auto';
    surface.style.position = 'static';
    holder.style.height = 'auto';
  }
  await document.fonts.ready;
  return score.tracks.map((t) => t.name);
}

/** Runs in the page: removes a numeric tempo mark that is drawn on top of a tempo name. */
function removeOverlappingTempoDuplicate() {
  let removed = 0;
  for (const svg of document.querySelectorAll('svg')) {
    const texts = [...svg.querySelectorAll('text')];
    for (let index = 1; index + 3 < texts.length; index += 1) {
      const [firstSymbol, firstBpm, name, secondSymbol, secondBpm] = texts.slice(index - 1, index + 4);
      const bpm = firstBpm.textContent?.trim();
      if (!/^=\s*\d+(?:\.\d+)?$/.test(bpm) || bpm !== secondBpm.textContent?.trim()) continue;
      const symbol = firstSymbol.textContent || '';
      if (!/\p{L}/u.test(name.textContent || '') || symbol !== secondSymbol.textContent ||
          [...symbol].length !== 1 || symbol.codePointAt(0) < 0xE000) continue;
      const first = firstBpm.getBoundingClientRect();
      const label = name.getBoundingClientRect();
      const second = secondBpm.getBoundingClientRect();
      const overlap = Math.min(first.right, label.right) - Math.max(first.left, label.left);
      if (Math.abs(first.top - label.top) > 2 || Math.abs(first.top - second.top) > 2) continue;
      if (overlap < first.width / 2 || second.left < label.right || second.left - label.right > 30) continue;
      firstSymbol.remove();
      firstBpm.remove();
      removed += 1;
      index += 3;
    }
  }
  return removed;
}

async function convert(args) {
  const gp5 = fs.readFileSync(args.input);
  const browser = await chromium.launch({
    headless: true,
    ...(args.chrome ? { executablePath: path.resolve(args.chrome) } : {}),
  });
  const temporaryPdf = `${args.output}.${process.pid}.tmp`;
  try {
    const context = await browser.newContext({ viewport: { width: 794, height: 1123 }, locale: 'en-US' });
    await routeLocalFiles(context, gp5);
    const page = await context.newPage();
    page.setDefaultTimeout(args.timeoutMs);
    const pageErrors = [];
    page.on('pageerror', (error) => pageErrors.push(error.message));
    await page.goto(`${ORIGIN}/`, { waitUntil: 'load' });
    if (!(await page.evaluate(() => Boolean(window.alphaTab)))) {
      throw new Error(`alphaTab did not load. ${pageErrors.join(' ')}`.trim());
    }
    const tracks = await page.evaluate(renderAllTracks, { scale: SCORE_SCALE, width: SCORE_WIDTH_PX });
    const duplicates = await page.evaluate(removeOverlappingTempoDuplicate);
    if (duplicates) console.log(`Removed ${duplicates} overlapping duplicate tempo mark(s).`);
    console.log(`Rendered ${tracks.length} track(s) with alphaTab ${ALPHATAB_VERSION}: ${tracks.join(', ')}`);

    const pdf = await page.pdf({ format: 'A4', printBackground: true, preferCSSPageSize: true });
    if (pdf.length < 1000 || pdf.subarray(0, 5).toString('ascii') !== '%PDF-') {
      throw new Error('alphaTab did not produce a valid PDF.');
    }
    fs.mkdirSync(path.dirname(args.output), { recursive: true });
    fs.writeFileSync(temporaryPdf, pdf);
    fs.renameSync(temporaryPdf, args.output);
    return args.output;
  } finally {
    if (fs.existsSync(temporaryPdf)) fs.unlinkSync(temporaryPdf);
    await browser.close();
  }
}

if (require.main === module) {
  try {
    const args = parseArgs(process.argv.slice(2));
    convert(args).then(
      (output) => console.log(`Wrote ${output}`),
      (error) => { console.error(`GP5 to PDF failed: ${error.message}`); process.exitCode = 1; },
    );
  } catch (error) {
    console.error(error.message);
    process.exitCode = 2;
  }
}

module.exports = { parseArgs, convert };
