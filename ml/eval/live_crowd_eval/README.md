# Live-audio crowd removal evaluation (Iteration 4, 2026-11-19 – 11-22)

Evaluation set, scripts and results for the experiment described in the Wiki page
"Live-Audio Preprocessing (Crowd Removal) — AI Module Evaluation".
Decision: keep the current pipeline; no live-audio preprocessing for now.

Audio is **not** committed (copyrighted YouTube material, internal testing only).
`manifest.csv` lists every item with its source URL or the team file it came from; `fetch_wav.py` re-downloads the
YouTube items as 44.1 kHz stereo 16-bit WAV (`python3 fetch_wav.py`, needs `yt-dlp` and `ffmpeg`).
`resolved.csv` records the exact video that was downloaded.

| Path | Content |
|---|---|
| `manifest.csv` | 84 items + reference R01: id, group (live / studio / live_pair / studio_clean / nonband / reference), labels, URL or local source |
| `crowd_metrics.csv` | Mel-Band RoFormer Crowd score per item |
| `crowd_secs.json` | Crowd-only and music seconds per pipeline song (L, S, P) |
| `cluster/` | Scripts and Pod specs run on SGS gpu22 (`/data/live_eval`): crowd separation, pipeline runs A / B / C / A2, references |
| `analysis/` | Comparison scripts (run on a laptop from the experiment folder layout: `out/<arm>/<id>/stem_midi_gated/*.mid`, `wav/`) |
| `results/` | Output tables: A vs B / C / Cm / A2 per song and per instrument, crowd-segment note counts, run times |
| `listening/` | Blind listening sheets of the 4 raters (A vs C), answer key, Option 1 check sheet |

Listening renders use the GeneralUser GS SoundFont (not committed; https://github.com/mrbumpy409/GeneralUser-GS),
expected at `analysis/sf/GeneralUser-GS.sf2`.
