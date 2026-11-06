# GP5 PDF converter comparison (2026-11-07 KST)

## Scope

Compare only the GP5-to-PDF stage, not stem separation, transcription, TAB
generation, MuseScore publication, Pod startup, or dependency installation.
The input is the completed guitar TAB for the mobile `Sweet_Child_O_mine`
run (`95d61db30e3b`):

- GP5: `/data/mp3_fix_validation_20261104/run/scores/guitar_render.gp5`
- Size: 20,067 bytes
- SHA-256: `2d87735dc26aba55002b63b77b9e8fca0208b04d70d372020d6f4ec22db62625`
- Old converter: the previously active
  `/data/rocky-unified/ml/gp5_to_pdf/convert.js`, now preserved at
  `/data/rocky-unified/ml/gp5_to_pdf_tabtify_20261107/convert.js`
- New converter: staged at
  `/data/gp5_alphatab_trial_20261107/gp5_to_pdf/convert.js`, now active at
  `/data/rocky-unified/ml/gp5_to_pdf/convert.js`; copied from `ml/gp5-alphatab`
  at `5c9450f`

Both were measured in one CPU-only Pod on `ferrari` with the same
`mcr.microsoft.com/playwright:v1.62.1-noble` image, CPU limit 4 and memory
limit 8 GiB. The Pod ran old/new/new/old. `npm ci` ran before the timer. Each
timed command started a fresh Node/Chromium process and wrote a distinct PDF:

```bash
node "$CONVERTER" "$INPUT" "$OUTPUT" --timeout-ms 180000
```

The Pod command, with post-deployment paths to the same converter versions, is
in `sgs/gp5-pdf-benchmark-pod.example.yaml`. Timings
were measured with `date +%s%3N`; `timings.tsv` and the PDFs are in the local
`rocky-gp5-alphatab-benchmark-20261107` results folder.

| Run | Tabtify, s | Local alphaTab, s |
| --- | ---: | ---: |
| 1 | 11.275 | 1.607 |
| 2 | 10.686 | 1.576 |
| Mean | 10.981 | 1.592 |

Both versions produced valid A4 PDFs with 19 pages. The first pages were
rendered and inspected. For this one GP5, local alphaTab was **6.90× faster**,
saving **9.389 s (85.5%)** per conversion on average. This is a two-run,
one-song result; it does not estimate the whole pipeline latency or quality
across songs. Layout is not pixel-identical because the renderers use different
page styles.

## Pipeline verification

The updated `publish_scores.py` was tested with the existing completed run
copied to `/data/gp5_alphatab_trial_20261107/run`. Its old Tabtify PDFs were
invalidated by converter identity and regenerated automatically. The resulting
`score_outputs.json` remained version 5; `guitar.pdf` and `bass.pdf` report
`gp5-alphatab` (19 and 7 pages), while drums and MP3 artifacts remained
valid. The CPU publication Pod completed successfully. The Python publication
tests passed: `17 passed in 0.71s`.

To repeat the converter timing on SGS, give the Pod a fresh name (the original
Pod has completed), then run:

```bash
kubectl -n ws-qt1ja5byz6220 apply -f ml/pipeline/sgs/gp5-pdf-benchmark-pod.example.yaml
kubectl -n ws-qt1ja5byz6220 logs pod/rocky-gp5-alphatab-bench-20261107
```

The benchmark Pod is CPU-only and does not delete other Pods or the PVC.
