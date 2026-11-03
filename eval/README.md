# ROCKY AI module evaluation set and thresholds

Declared 2026-11-03, before the results of the runs below. Cases in `eval_set.csv` may be added
but not removed or edited; additions are listed at the end of this file. If a threshold has to
change, the original stays here and the revised one is added next to it with the reason.

## Evaluation set (`eval_set.csv`, 129 cases)

| Subset | Cases | Module | Input | Reference |
|---|---|---|---|---|
| `rwc_band12` | 12 | separation + transcription | RWC 2.0 original mixes (Zenodo record 18656623): RWC_P009, P035, P036, P045, P047, P051, P063, P065, P067, P068, P070, P095 (4/4, live guitar, bass and drums) | RWC aligned MIDI annotations (rwc-music/rwc-annotations, commit 0a1a6c3) |
| `rwc` | 103 | transcription | the other RWC-P and RWC-R songs | same |
| `band14` | 14 | whole pipeline, playability | 14 commercial band songs (audio on the team SGS volume `/data/input_bench`, not committed) | none: validity, time and playability checks |

## Thresholds

| ID | Cases | Metric | Pass if |
|---|---|---|---|
| T1 | rwc_band12 | Multi F1, mean over songs | pipeline with the adopted separator > no separation (MuScriptor on the mix) on the same songs |
| T2 | rwc_band12 | Multi F1, mean over songs | BS-RoFormer SW 6-stem ≥ Demucs htdemucs_6s |
| T3 | rwc_band12 | keyboard onset F1, mean over songs with keyboard notes | BS-RoFormer SW 6-stem > Demucs htdemucs_6s |
| T1' | rwc_band12 | Multi F1 on the four instruments, mean over songs | as T1 (added 2026-11-03, see Additions) |
| T2' | rwc_band12 | Multi F1 on the four instruments, mean over songs | as T2 (added 2026-11-03) |
| T3' | rwc_band12 | keyboard onset F1 on the four instruments, mean over songs with keyboard notes | as T3 (added 2026-11-03) |
| T4 | band14 | valid output (aligned MIDI, full-score MIDI, GP5, PDF) | 100% of songs |
| T5 | band14 | processing time for a 3-minute song (GPU stage) | ≤ 10 minutes |
| T6 | band14 | after TAB / keyboard processing: onsets one player cannot play, notes outside the instrument range | 0 |

`rwc` cases are reported (transcription baseline) without a threshold.

## Metrics and settings

- F1: MuScriptor paper, Section 3.3, via `mir_eval` one-to-one matching, onset tolerance 50 ms,
  offset tolerance max(50 ms, 0.2 x reference duration), frames 62.5 ms, Multi F1 with MT3_FULL_PLUS
  instrument groups (the team RWC evaluation, `metrics.py`, `/data/rwc-eval` on the team SGS volume).
  Per-family onset F1: reference families by GM program (keys 0-7 and 16-23, guitar 24-31, bass 32-39,
  drums); separated runs take the family from the stem a note was transcribed from.
- Scored before beat alignment (alignment moves notes to a 16th grid, which a performance-time
  reference counts as timing errors).
- Transcription: MuScriptor large (`muscriptor==0.4.0`, local weights), `use_sampling=False`,
  `cfg_coef=1.0`, `beam_size=1`, no tempo detection. Separated runs give the app pipeline's stem
  instrument hints (`ml/pipeline/unified.py` HINTS); the no-separation baseline uses none.
- Separation: Demucs `htdemucs_6s` (shifts=1, split, overlap 0.25, as `ml/pipeline/separate_stems.py`),
  BS-RoFormer SW 6-stem (`bs-roformer-infer==0.1.5`, model `roformer-model-bs-roformer-sw-by-jarredou`).

## Commands

RWC separation comparison (SGS, second workspace, A100 40GB on ford): `rwc_separation/`

```bash
bash rwc_separation/setup_env.sh                       # once: /data/envs/{sep,mus}
/data/envs/mus/bin/python rwc_separation/eval_sep.py rwc_separation/songs12.txt
# -> /data/rwc/results/summary.csv (one row per song and method: none, demucs, bsrofo)
/data/envs/mus/bin/python rwc_separation/rescore4.py rwc_separation/songs12.txt
# -> /data/rwc/results/summary4.csv (T1'-T3': the same outputs scored on the four instruments)
```

Whole pipeline (band14): `ml/pipeline/unified.py` on the team SGS volume, as in
`ml/pipeline/README.md`; times from the per-stage logs.
T6 for the guitar and bass TAB: `python eval/t6_tab.py RESULTS_DIR` (one folder per song with `guitar/*.gp5`
and `bass/*.gp5`; needs `pyguitarpro`). It checks each onset against the rules `ml/guitar_tab/skyline_tab.py`
enforces (one note per string, no more notes than strings, fretted notes within 4 frets, frets 0-20).

## Additions

**2026-11-03, T1'-T3' (four-instrument scores), added before the results were examined.**
T1-T3 stay as declared; T1'-T3' are reported next to them.

- Reason: a one-song smoke test (RWC_P035) showed that the RWC reference has every part of the song
  (vocal melody, strings, brass, synths), while the separated pipeline transcribes only the drums, bass,
  guitar and piano stems. T1-T3 count the parts it never tries to transcribe as missed notes, while the
  no-separation baseline can still get credit for them. Listing the 12 references
  (`rwc_separation/ref_tracks.py`): 4-36% of the notes per song (14% overall) are outside the four families.
- Reference: tracks kept by GM program family, as in the per-family onset F1, with two corrections from that
  listing: a track named exactly MELODY / MELO / MELODY 1 / VOCAL is the vocal melody and is dropped whatever
  its program (RWC_P047 `MELODY` is GM 22, in the keyboard range; `GT MELO 1` etc. stay as guitar), and
  RWC_P063 `E.PIANO` (GM 99) is kept as a keyboard part. These two corrections also affect T3's keyboard
  reference; T3 is not changed, T3' uses them.
- Estimate: separated runs keep every note (all from the four stems); the no-separation baseline keeps
  notes whose GM program is in the four families.
- Same metrics as above (`metrics.py`, per-family onset F1), computed by `rwc_separation/rescore4.py` from the
  MIDIs `eval_sep.py` already wrote; nothing is separated or transcribed again.
