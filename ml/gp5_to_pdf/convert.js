#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const { PDFDocument } = require('pdf-lib');

const EDITOR_URL = 'https://tabtify.com/tab';
const DEFAULT_TIMEOUT_MS = 90_000;
const NAVIGATION_ATTEMPTS = 3;

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

async function openEditor(page, timeoutMs) {
  let lastError;
  for (let attempt = 1; attempt <= NAVIGATION_ATTEMPTS; attempt += 1) {
    try {
      const response = await page.goto(EDITOR_URL, {
        waitUntil: 'domcontentloaded', timeout: timeoutMs,
      });
      if (!response?.ok()) throw new Error(`Tabtify returned HTTP ${response?.status() ?? 'unknown'}`);
      return;
    } catch (error) {
      lastError = error;
      if (attempt === NAVIGATION_ATTEMPTS) break;
      await page.waitForTimeout(2000);
    }
  }
  throw lastError;
}

async function removeOverlappingTempoDuplicate(printView) {
  return printView.evaluate(() => {
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
  });
}

async function convert(args) {
  const browser = await chromium.launch({
    headless: true,
    ...(args.chrome ? { executablePath: path.resolve(args.chrome) } : {}),
  });
  const temporaryPdf = `${args.output}.${process.pid}.tmp`;
  try {
    // The editor gives roughly 300px to its tools. A 1000px viewport leaves
    // a score close to the printable width of an A4 page.
    const context = await browser.newContext({
      viewport: { width: 1000, height: 1200 },
      locale: 'en-US',
    });
    // alphaTab's print view calls window.print(). Chromium's headless print
    // dialog cannot be completed; page.pdf() saves the same view below.
    await context.addInitScript(() => { window.print = () => {}; });
    const page = await context.newPage();
    page.setDefaultTimeout(args.timeoutMs);
    await openEditor(page, args.timeoutMs);
    await page.locator('#alphatab-container').waitFor({ state: 'visible' });

    const score = page.locator('#alphatab-container');
    const originalScore = await score.textContent();
    const fileChooserPromise = page.waitForEvent('filechooser');
    await page.getByText('Open', { exact: true }).first().click();
    const fileChooser = await fileChooserPromise;
    await fileChooser.setFiles(args.input);

    await page.waitForFunction(
      (previous) => {
        const current = document.querySelector('#alphatab-container')?.textContent;
        const score = document.querySelector('#alphatab-container');
        return current && current !== previous && current.trim().length > 0 &&
          score.querySelectorAll('svg').length > 0;
      },
      originalScore,
      { timeout: args.timeoutMs },
    );
    await page.evaluate(() => new Promise((resolve) => {
      const score = document.querySelector('#alphatab-container');
      let quietTimer;
      const done = () => { observer.disconnect(); resolve(); };
      const observer = new MutationObserver(() => {
        clearTimeout(quietTimer);
        quietTimer = setTimeout(done, 1500);
      });
      observer.observe(score, { childList: true, subtree: true, characterData: true });
      quietTimer = setTimeout(done, 1500);
    }));
    const trackButton = page.locator('button').filter({ hasText: /\d+ strings/ }).last();
    await trackButton.click();
    const tracks = page.locator('[role="button"][tabindex="0"]:has(button[aria-label="Edit track"])');
    const trackCount = await tracks.count();
    if (trackCount < 1) throw new Error('No GP5 tracks found in Tabtify.');
    await tracks.first().click();

    const merged = await PDFDocument.create();
    for (let index = 0; index < trackCount; index += 1) {
      if (index > 0) {
        const previousScore = await score.textContent();
        await trackButton.click();
        await tracks.nth(index).click();
        await page.waitForFunction(
          (previous) => {
            const current = document.querySelector('#alphatab-container')?.textContent;
            return current && current !== previous && document.querySelectorAll('#alphatab-container svg').length > 0;
          },
          previousScore,
          { timeout: args.timeoutMs },
        );
      }

      await page.getByText('Export', { exact: true }).first().click();
      const printViewPromise = page.waitForEvent('popup');
      await page.getByRole('button', { name: /PDF \(\.pdf\)/ }).click();
      const printView = await printViewPromise;
      printView.setDefaultTimeout(args.timeoutMs);
      await printView.setViewportSize({ width: 1000, height: 1200 });
      await printView.locator('svg').first().waitFor({ state: 'visible' });
      await printView.waitForFunction(() =>
        document.querySelectorAll('svg').length > 0 &&
        (document.body.textContent || '').trim().length > 50,
      );
      await printView.evaluate(() => document.fonts.ready);
      const duplicates = await removeOverlappingTempoDuplicate(printView);
      if (duplicates) console.log(`Removed ${duplicates} overlapping duplicate tempo mark(s) from print view.`);
      const trackPdf = await PDFDocument.load(await printView.pdf({
        format: 'A4',
        printBackground: true,
        preferCSSPageSize: true,
      }));
      if (trackPdf.getPageCount() === 0) throw new Error(`Track ${index + 1} produced no PDF pages.`);
      const pages = await merged.copyPages(trackPdf, trackPdf.getPageIndices());
      pages.forEach((pdfPage) => merged.addPage(pdfPage));
      await printView.close();
      const cancel = page.getByRole('button', { name: 'Cancel', exact: true });
      if (await cancel.isVisible()) await cancel.click();
    }
    fs.mkdirSync(path.dirname(args.output), { recursive: true });
    fs.writeFileSync(temporaryPdf, await merged.save());
    const pdf = fs.readFileSync(temporaryPdf);
    if (pdf.length < 1000 || pdf.subarray(0, 5).toString('ascii') !== '%PDF-') {
      throw new Error('Tabtify did not produce a valid PDF.');
    }
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
