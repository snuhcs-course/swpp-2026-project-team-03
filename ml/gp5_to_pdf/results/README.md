# GP5 to PDF reference results

These 18 PDFs were generated from the GP5 files in
[`ml/guitar-tab` at `0f0eab8`](https://github.com/snuhcs-course/swpp-2026-project-team-03/tree/0f0eab8680d6c621326d75f87db1b39ce7dae323/ml/guitar_tab/results)
with the converter at `a36bd23`. The folder layout mirrors the source results:
10 `skyline lead+rhythm` files and 8 `merged` files.

[`manifest.json`](manifest.json) gives the source GP5 and PDF SHA-256 hashes
and PDF page count for each file. All 18 conversions exited successfully. The
PDFs total 234 pages; every page contains text. All 10 lead+rhythm PDFs
contain both guitar tracks. A merged PDF contains one guitar track. Korean
filenames were included in the checks.

To reproduce one result, obtain the GP5 from the source branch and run:

```powershell
cd ml\gp5_to_pdf\results
node ..\convert.js 'path\to\source.gp5' 'path\to\result.pdf' --chrome 'C:\Program Files\Google\Chrome\Application\chrome.exe'
```

Install dependencies as described in the parent README. Tabtify controls the
score layout, so a later site version may give different page breaks. These
checks establish that the source GP5 files render as PDFs; they do not compare
the notes or fingerings with the upstream MIDI files.
