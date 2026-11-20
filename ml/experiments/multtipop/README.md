# MulTTiPop pipeline test

Tests ROCKY's audio → MIDI → four-instrument collapse pipeline on real pop
recordings with vocals. [MulTTiPop](https://huggingface.co/datasets/gclef-cmu/multtipop)
([paper](https://arxiv.org/abs/2607.08756)) pairs 572 short segments of pop
songs with time-aligned multitrack MIDI. It ships **no audio**: each segment
is a YouTube video id plus a start and end time.

Run every command from the repository root.

## What is tracked and what is local

| Path | In Git | Content |
| --- | --- | --- |
| `ml/experiments/multtipop/samples.csv` | yes | all 572 segments: reference MIDI path, YouTube id, time range, song metadata, note counts per family |
| `ml/experiments/multtipop/candidates.txt` | yes | ids of the segments chosen for testing |
| `ml/experiments/multtipop/audio_manifest.csv` | yes | the chosen segments: YouTube URL, time range, required audio path |
| `data/datasets/multtipop/` | no | the dataset as downloaded; **never edit these MIDI files** |
| `data/audio/multtipop/<id>.wav` | no | segment audio |
| `outputs/multtipop/<id>/` | no | transcriptions, collapsed MIDI, reports, scores |

## 1. Download the dataset

Public, no login needed (CC BY 4.0, about 17 MB).

```bash
uvx --from huggingface_hub hf download gclef-cmu/multtipop \
  --repo-type dataset --local-dir data/datasets/multtipop
```

Each `data/datasets/multtipop/{dev,test}/<id>/` holds `aligned.mid` (the
reference; time 0 is the segment start) and `meta.json`.

## 2. Build the index and the manifest

```bash
uvx --with pretty_midi --with "setuptools<81" python \
  ml/experiments/multtipop/build_index.py
```

To test other segments, edit `candidates.txt` (pick ids from `samples.csv`)
and run this again.

## 3. Put the audio in place

**Input path rule:** the audio for a segment must be at
`data/audio/multtipop/<id>.wav`, where `<id>` is the manifest `id`, and it
must contain exactly `start_sec`–`end_sec` of the listed YouTube video, so
that second 0 of the file is second 0 of `aligned.mid`. Any sample rate and
channel count is fine. The path is also written in the manifest's
`audio_path` column.

The team decided to fetch these segments for private evaluation only:

```bash
uvx --with yt-dlp --with imageio-ffmpeg python \
  ml/experiments/multtipop/fetch_audio.py
```

It fetches only the listed range, skips files that already exist, and can be
rerun if a segment fails (YouTube occasionally answers 403). Keep the audio
out of Git and out of shared folders, and do not train on it; the dataset
authors ask for evaluation use only.

Audio from another source (for example a purchased track) works if it is cut
to the same range, but other releases of a song are often offset from the
YouTube video by a few seconds, which makes every score near zero. Check
against `audio_beats` in `meta.json`.

## 4. Transcribe

MuScriptor (also collapses the reference and the prediction):

```bash
./ml/experiments/multtipop/run_muscriptor.sh medium
```

The script passes `--detect-tempo false`. With tempo detection on, MuScriptor
delays every note by a constant whenever it finds a steady tempo (0.81 s on
one segment), which drops onset F1 from 0.54 to 0.00 on that segment. Keep
it off for anything that is scored against a time-aligned reference.

YourMT3+ needs a clone of its Hugging Face Space, which contains the code and
checkpoints, and realistically a GPU (for example Colab):

```bash
git lfs install
git clone https://huggingface.co/spaces/mimbres/YourMT3
cd YourMT3 && pip install -r requirements.txt
python <repo>/ml/experiments/multtipop/run_yourmt3.py \
  <repo>/data/audio/multtipop <repo>/outputs/multtipop
```

`run_yourmt3.py` has not been executed in this repository's environment yet.
It writes `outputs/multtipop/<id>/yourmt3.mid`; collapse each one with:

```bash
uvx --with pretty_midi --with "setuptools<81" python \
  ml/experiments/multtipop/collapse_midi.py \
  outputs/multtipop/<id>/yourmt3.mid outputs/multtipop/<id>/yourmt3_collapsed.mid \
  --report outputs/multtipop/<id>/yourmt3_collapse_report.json
```

## 5. Collapse rule

`collapse_midi.py` reads a MIDI file and writes a new one with at most four
tracks. It never writes to its input.

| Family | Source |
| --- | --- |
| keyboard | GM programs 0–7 (pianos) and 16–23 (organs) |
| guitar | GM programs 24–31 |
| bass | GM programs 32–39 |
| drums | MIDI channel 10 |

Everything else (strings, brass, synth leads and pads, voices) is dropped and
listed in the JSON report, not forced into a family. About 20% of the
reference notes fall outside the four families, more in late-2000s pop.

With `--drop-vocal-tracks` (used for references), tracks whose name contains
`vocal`, `vox`, `voice`, `melod`, `singer`, or `lyric` are dropped first.
MulTTiPop references come from Lakh MIDI files in which the sung melody is an
ordinary instrument track, sometimes on a piano, organ, or guitar program;
without this step the vocal line is counted as keyboard or guitar. Unnamed
vocal tracks cannot be detected.

## 6. Score

```bash
uvx --with pretty_midi --with mir_eval --with "setuptools<81" python \
  ml/experiments/multtipop/evaluate.py muscriptor_medium
```

Replace `muscriptor_medium` with `yourmt3` for the other model. The result is
`outputs/multtipop/scores_<system>.csv`: onset F1 per family (same pitch,
onset within 50 ms) and Multi F1 (family must match too). A family absent
from the reference is left blank, not scored 0.

## Reading the scores

- The references are community MIDI files aligned automatically, not manual
  transcriptions of these recordings. Arrangements can differ from the
  recording and onsets can be off by tens of milliseconds, so a low score is
  not always the model's fault. `--onset-tolerance 0.1` shows how much of the
  error is timing.
- Comparing two models on the same segments is more reliable than reading
  the absolute numbers, and these are not comparable with BabySlakh scores.
- The newest song in the dataset is from 2009, and the artists are mostly
  American and British.
