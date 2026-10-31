# GP5 to PDF

This module opens a completed GP5 tab in the Tabtify browser editor and exports
its printable layout to PDF. It does not perform MIDI-to-GP5 conversion.
The editor navigation retries up to three times for transient network failures.
If Tabtify's print SVG duplicates a numeric tempo mark on top of a tempo name,
the converter removes only the overlapping copy before saving the PDF. The
tempo name and the second numeric mark remain visible.

## Setup

Install Node.js, run `npm ci` in this directory, and install Playwright's
Chromium browser with `npx playwright install chromium`. On Linux, the pinned
Playwright container image `mcr.microsoft.com/playwright:v1.62.1-noble`
provides the browser and its system libraries; run `npm ci` inside that
container to install this module's Node dependencies. The versions are
recorded in `package-lock.json`. No account or API key is needed.

## Convert

```powershell
node convert.js C:\path\to\input.gp5 C:\path\to\output.pdf
```

Optional arguments: `--chrome C:\path\to\chrome.exe` to select a specific browser,
`--timeout-ms 120000` to allow a longer load, and `--force` to replace an
existing PDF. The process exits nonzero if the GP5 cannot be opened or the PDF
is not produced. The output is written only after conversion succeeds.

Tabtify's PDF menu opens alphaTab's print view. The script saves that print
view through Chromium's PDF API, without an interactive print dialog. The
module prints every track in source order and appends their pages to one PDF.
The print view disables alphaTab's lazy rendering, so long scores are included. Its
selectors depend on Tabtify's current editor UI;
recheck them if that site changes. Input files are provided to Tabtify through
the browser. Do not use this route for private scores unless that service is an
approved destination for them.

## Published reference PDFs

The [results](results/README.md) directory contains PDF exports of all 18 GP5
files in `ml/guitar-tab` at commit `0f0eab8` (10 lead+rhythm scores and 8
merged scores). Its manifest maps each PDF to its source GP5 and records file
hashes and page counts. These are render compatibility examples, not a
note-by-note comparison against the source MIDI.
