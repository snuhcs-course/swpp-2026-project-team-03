# GP5 to PDF

This module renders a completed GP5 tab to PDF with
[alphaTab](https://www.alphatab.net/) in a local headless Chromium. It does not
perform MIDI-to-GP5 conversion. The score never leaves the machine: the page,
alphaTab and its Bravura music font are served from `node_modules`, and every
other network request is blocked.

## Setup

Install Node.js, run `npm ci` in this directory, and install Playwright's
Chromium browser with `npx playwright install chromium`. On Linux, the pinned
Playwright container image `mcr.microsoft.com/playwright:v1.62.1-noble`
provides the browser and its system libraries; run `npm ci` inside that
container to install this module's Node dependencies. The versions, including
`@coderline/alphatab` 1.8.4, are recorded in `package-lock.json`. No account,
API key or network access is needed after setup.

## Convert

```powershell
node convert.js C:\path\to\input.gp5 C:\path\to\output.pdf
```

Optional arguments: `--chrome C:\path\to\chrome.exe` to select a specific browser,
`--timeout-ms 120000` to allow a longer render, and `--force` to replace an
existing PDF. The process exits nonzero if the GP5 cannot be read or the PDF
is not produced. The output is written only after conversion succeeds.

Each track is rendered in alphaTab's page layout on A4 (10 mm margins, scale
0.75) and starts on a new page under a heading with the song title, artist and
track name. Systems are never split across pages. alphaTab cuts long track
names off beside the staff, so that label is hidden and the heading is used
instead. If a numeric tempo mark is drawn on top of a tempo name, the converter
removes only the overlapping copy; the tempo name and the second mark remain.
Converting the 18 reference GP5 files below takes about 10 seconds in total.

Earlier versions uploaded the GP5 to the Tabtify web editor and printed its
alphaTab view. That route depended on a third-party site and its UI selectors,
and sent scores off the machine, so it was replaced.

## Published reference PDFs

The [results](results/README.md) directory contains PDF exports of all 18 GP5
files in `ml/guitar-tab` at commit `0f0eab8` (10 lead+rhythm scores and 8
merged scores). Its manifest maps each PDF to its source GP5 and records file
hashes and page counts. These are render compatibility examples, not a
note-by-note comparison against the source MIDI. They were produced by the
earlier Tabtify route (converter commit `a36bd23`); the alphaTab route gives
the same page count within two pages for each file.
