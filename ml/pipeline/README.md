# ROCKY pipeline

## Unified GPU workflow (Iteration 3, in progress)

> **SGS course rule:** Active deployment manifests under `sgs/` use
> `kind: Pod`. The team confirmed that CPU, memory, and a PVC mount may be
> added to the TA's Pod format, as in `pod-bench.yaml`. They pin to `ferrari`
> and mount the existing `muscriptor-data` PVC at `/data`. Historical Job/PVC
> manifests remain under `sgs/legacy/` for reference only; do not apply them.

`unified.py` connects the current independent modules for **one song**. The
server layout uses the SGS shared volume. The unified workflow now uses
the fixed BS-RoFormer SW six-stem model to produce `vocals`, `drums`, `bass`,
`guitar`, `piano`, and `other` audio. With a known original lineup, MuScriptor
large transcribes only the declared original band instruments. An explicitly
absent instrument is excluded from transcription, aligned MIDI and MIDI-GPT
context. With an unknown original lineup, all four band stems are transcribed.
For either lineup, Beat This! always receives `no_vocals.wav`, the sum of all
five non-vocal stems including `other`; the original-lineup selection does not
filter its audio. `vocals.wav` and `other.wav` are never transcribed or merged.
Drum sync runs before alignment to Beat This!
beats. Original instruments omitted from the requested output remain in the
MIDI-GPT context but are removed from the final score.
MuScriptor may label notes in the piano stem as acoustic piano, electric piano,
or organ. During `merge_stems`, these keyboard tracks become one `piano: piano`
track (GM program 0) before beat alignment and MIDI-GPT. Same-pitch onsets in
different tracks within 50 ms are kept once with the later end and stronger
velocity; later same-pitch onsets cut an overlapping earlier note. A non-keyboard
track mistakenly assigned to the piano stem is still excluded.

The app sends an original lineup (`--original unknown` for the entire song, or
selected `keyboard,bass,guitar1/guitar2,drums`) and a required output lineup
(`--requested` with the same instrument names). `guitar1` and `guitar2` mean
one or two guitars, not independent checkboxes. `keyboard` covers piano,
electric piano and organ. When the original is unknown, skyline first decides
whether its guitar TAB should split; that result is treated as one or two
original guitars for the same cases below:

| Original guitars | Requested guitars | Action |
| --- | --- | --- |
| 2 | 2 | skyline `--split always` |
| 2 | 1 | skyline `--split never`, compress chords into one playable part |
| 1 | 1 | skyline `--split never` |
| 1 | 2 | skyline `--split never`, then MIDI-GPT generates a separate second guitar |
| 0 | 1 | MIDI-GPT generates one guitar |
| 0 | 2 | rejected in this iteration |

Only requested parts absent from the declared original (or detected original
when unknown) are generated. A generated second guitar keeps the original
guitar in MIDI-GPT's context; both receive independent TAB processing before
final assembly. The MIDI-GPT `_band.mid` files are not merged again.
MIDI-GPT can generate notes past the input song's end; its raw `_only.mid` is
retained for audit, while `generated_normalized/<part>.mid` is capped at the
larger of the audio duration and the aligned MIDI end before TAB and assembly.

On SGS, model stages used the common Python 3.11
environment and guitar/bass TAB used the isolated Python 3.10 environment.
The source paths are `/data/pipeline` and
`/data/rocky-unified/ml/{beat_align,guitar_tab,midigpt}`.
Set `HF_HOME`, `TORCH_HOME` and the uv cache paths to `/data/cache`. The
command below shows a MIDI/GP5-only run using the current source and the
existing `/data` layout:

```bash
/data/rocky-unified/.venv/bin/python /data/pipeline/unified.py \
  /data/input/song.wav /data/output_unified/new-song \
  --original keyboard,bass,guitar1,drums \
  --requested keyboard,bass,guitar2,drums --no-publish
```

For the current source, the first stage requires `bs-roformer-infer==0.1.5`
and the fixed SW checkpoint/config. On the existing SGS environment,
the team staged them at `/data/bsrofo/pylib` and `/data/bsrofo/models`:

```bash
uv pip install --python /data/rocky-unified/.venv/bin/python \
  --target /data/bsrofo/pylib --no-deps \
  bs-roformer-infer==0.1.5 beartype einops ml-collections absl-py \
  rotary-embedding-torch requests urllib3 idna certifi charset-normalizer
/data/rocky-unified/.venv/bin/python /data/pipeline/unified.py \
  /data/input/song.wav /data/output_unified/new-song \
  --original unknown --requested keyboard,bass,guitar1,drums \
  --bsroformer-models-dir /data/bsrofo/models \
  --bsroformer-lib-dir /data/bsrofo/pylib --no-publish
```

The model files must be under
`/data/bsrofo/models/roformer-model-bs-roformer-sw-by-jarredou/` as
`BS-Rofo-SW-Fixed.ckpt` and `BS-Rofo-SW-Fixed.yaml`. The adapter checks both
SHA-256 values before inference and never downloads a model implicitly. It
passes a safe `song.wav` name to inference, writes the six canonical stems as
32-bit float WAVs, builds a peak-limited `no_vocals.wav` from all five non-vocal
stems, and discards the
large temporary inference files after success. The model and package paths
can be changed with the two `--bsroformer-*` options. The sample command uses
`--no-publish` because the GPU image may lack the PDF/MP3 tools;
omit it once those tools are available to produce all deliverables.

The piano-stem merge raised the manifest contract to version 9. Start a **new**
output directory; older `manifest.json` files cannot be resumed with this code.

`--requested` is required. The output directory must be new, or contain a
`manifest.json` from the same input and configuration when `--resume` is used.
Every stage checks its files before marking completion. Failures leave the
manifest in `failed` status with a log path; rerunning with `--resume` retries
the failed stage. `full_score.mid` and `manifest.json` complete the GPU stage.
The stem MIDI files, `beats.json`, `aligned.mid`, TAB GP5 files, and model logs
are retained under the same output directory for inspection. By default,
`unified.py` then publishes the PDFs and MP3 playback files before reporting
completion. `--no-publish` stops after MIDI/GP5 for diagnostics; rerun with
`--resume` and without that flag to publish the same result.

## Automatic score and playback publication

`unified.py` calls `publish_scores.py` after assembling `full_score.mid`.
This stage needs MuseScore, Poppler `pdfinfo`, Node.js, `pyguitarpro`, the `gp5_to_pdf`
module with Playwright/Chromium, and access to Tabtify for guitar/bass GP5
PDF export. That converter uploads the GP5 to Tabtify, so the caller must
approve that service for the input score. Set `--musescore`, `--pdfinfo`,
`--node`, and `--gp5-converter`
if the executable or module paths differ from the defaults. MuseScore and
`pdfinfo` are checked before model stages; Node and GP5 converter availability
are checked if the finished MIDI contains guitar or bass. The earlier
CPU Job is archived under `sgs/legacy/`. The active
`sgs/score-pdf-pod.example.yaml` uses a CPU-only Pod, which releases the GPU
after transcription and TAB processing. When the PDF/MP3 tools are installed
in the GPU Pod, omitting `--no-publish` also lets `unified.py` run this stage
automatically inside that Pod.
For a standalone local publication with system Chrome, pass
`--chrome /path/to/chrome` to `publish_scores.py`; the SGS Playwright Pod uses
its packaged browser and needs no such option.

The frontend contract is `scores/score_outputs.json` (version 4): a full-band
PDF and MP3, plus a PDF and MP3 for every present instrument family (guitar,
bass, piano, drums). The MP3 names follow the iteration 2 demo:
`scores/band.mp3`, `scores/guitar.mp3`, `scores/bass.mp3`,
`scores/piano.mp3`, and `scores/drums.mp3`. All playback audio is synthesized
from program-preserving copies of `full_score.mid`; it is not the original
recording or a separated stem. The stage also writes `scores/<part>.mid` for each
present instrument. When a second guitar is generated, `guitar.pdf` is the
combined standard-notation score and `guitar_1.pdf` and `guitar_2.pdf` are
separate TAB PDFs. Matching MIDI and MP3 files are also provided. When
skyline splits two original guitars, `guitar.pdf` contains both TAB parts.
`scores/piano.pdf` contains the merged piano-stem track (or an AI-generated
piano part when the original lacks a keyboard). TAB PDFs for guitar and bass come from their
processed GP5 files through `gp5_to_pdf/convert.js` (Tabtify). When MIDI-GPT
adds a second guitar, the combined `guitar.pdf` uses MIDI notation while
`guitar_1.pdf` and `guitar_2.pdf` carry the separate TABs. Full-band, piano and drums
PDFs come from the assembled MIDI through MuseScore. The full-band PDF uses
standard notation; guitar and bass part PDFs include TAB. MuseScore 3 omits
GM drum pitches 39 (clap), 70 (maracas) and 82 (shaker) on import, so
render-only MIDI copies map them to visible surrogate drum symbols. The
original `full_score.mid` and `scores/drums.mid` keep their pitches. Before PDF
export, the imported MuseScore score receives explicit staff names such as
`Electric Guitar`, `Electric Bass`, `Piano`, and `Drum Set`. This avoids
MuseScore 3 showing the GM patch subtypes `Jazz Guitar` and `Fingered Bass`
as if they were different instrument families. GP5 PDF inputs are publication
copies with matching track names and programs; the processed source GP5s stay
unchanged. MP3 inputs preserve the final assembled MIDI programs and notes,
including each song's acoustic or electric guitar choice. The
JSON records the exact mapping and affected note counts. The JSON also records
PDF and MP3 source paths, converter, bytes and SHA-256, plus PDF page counts.
`manifest.json` points to that file through `score_outputs`, and
`score_publication` becomes `complete` only after every requested artifact is
valid. `--resume` rechecks the contract and regenerates missing artifacts.

The branch's earlier `audio_to_midi.sh` remains a two-stage alternative.
`unified.py` is an independent server workflow; Android still shows bundled
demo results. Instrument presence currently uses GM
program groups and excludes tracks from the vocal stem; ambiguous instruments
still need user review. Beat alignment assumes one tempo and one meter per
song. The SW piano stem still requires listening and score review.

The sections below document the earlier `audio_to_midi.sh` alternative. Its
stage table does not describe the full `unified.py` workflow above.

| Stage | Tool | Status |
| --- | --- | --- |
| 1. Remove vocals | Demucs `htdemucs` | done |
| 2. Transcribe to MIDI | MuScriptor | done |
| 3. Later stages | to be added | not started |

## Run

From the repository root:

```bash
./ml/pipeline/audio_to_midi.sh INPUT_AUDIO [OUTPUT_DIR] [MODEL] [DEVICE]
```

| Argument | Default | Values |
| --- | --- | --- |
| `INPUT_AUDIO` | required | wav, mp3, flac, or m4a |
| `OUTPUT_DIR` | `outputs/pipeline` | any directory |
| `MODEL` | `large` | `small`, `medium`, `large`, or a path to a `.safetensors` file |
| `DEVICE` | `auto` | `auto`, `cpu`, `cuda` |

Example:

```bash
./ml/pipeline/audio_to_midi.sh "data/audio/band_songs/21 Guns - Green Day.wav"
```

The default model, `large`, is meant for a CUDA GPU, where transcription
takes roughly as long as the song. On a Mac it runs on the CPU and is slow:
4 to 14 times the song's length in our runs. Pass `medium` as `MODEL` for
quick local checks (a 26-second clip takes about 2 minutes).

## Requirements

- [uv](https://docs.astral.sh/uv/). The script installs Demucs and MuScriptor
  through `uvx` on first use; nothing else needs to be installed.
- A Hugging Face account that has accepted the MuScriptor license
  (`https://huggingface.co/MuScriptor/muscriptor-large`, CC BY-NC 4.0; each
  model size has its own page), and
  `hf auth login` on the machine. Not needed when `MODEL` is a local file.

## Output

Everything for one song goes to `OUTPUT_DIR/<input file name without extension>/`:

| File | Content |
| --- | --- |
| `stems/vocals.wav`, `drums.wav`, `bass.wav`, `other.wav` | Demucs stems, 44.1 kHz stereo |
| `stems/no_vocals.wav` | drums + bass + other; the input to transcription |
| `transcription.mid` | MuScriptor output |
| `demucs.log`, `transcription.log` | logs of each stage |

`transcription.mid` has one track per detected instrument, with General MIDI
programs and drums on channel 10. Note times are in seconds from the start of
the audio. The file carries no tempo or bar information, because MuScriptor's
tempo detection is turned off (it delays every note by a constant). A stage
that needs beats has to estimate them from the audio.

Instruments are not collapsed to piano, guitar, bass, and drums. That mapping
belongs to the arrangement stage.

## Transcription progress

MuScriptor transcribes in 5-second chunks and reports each finished chunk,
but the `muscriptor transcribe` command drops those reports when it writes
MIDI. `transcribe_with_progress.py` makes the same call through the Python
API and writes one JSON line per finished chunk, so a server can show the app
a percentage and the time left:

```bash
uvx --python 3.13 --from muscriptor==0.4.0 python ml/pipeline/transcribe_with_progress.py \
    out/stems/no_vocals.wav out/transcription.mid --model large --progress out/progress.jsonl
```

```json
{"stage": "transcribe", "completed": 12, "total": 30, "fraction": 0.4, "elapsed_sec": 61.8, "eta_sec": 92.7}
```

`eta_sec` is null until the first chunk finishes. On a 26-second clip
(`small`, Mac CPU) its MIDI was byte-identical to the command's, and the
estimate after the first chunk (38.5 s left) was within 2 s of the actual
time. `audio_to_midi.sh` still uses the command.

## Running on the team GPU server (SGS)

All active SGS YAML files in this directory are `apiVersion: v1`, `kind: Pod`.
They pin to `ferrari` and mount the existing `muscriptor-data` PVC at `/data`.
They do not create, resize, or delete the PVC. Keep this node choice because
the team data resides there. Choose **one** GPU Pod workflow:

| File | Role |
| --- | --- |
| `sgs/pod.yaml` | Interactive GPU shell (`gpu-shell05`) with `/data` access |
| `sgs/unified-pod.example.yaml` | One-song GPU transcription/TAB runner; edit input, output, and lineups first |
| `sgs/score-pdf-pod.example.yaml` | CPU-only PDF/MP3 publication for the matching run directory |
| `sgs/files-pod.yaml` | Optional CPU-only transfer shell; do not apply if `rocky-files` already exists |

The interactive shell stays running until stopped; run the pipeline inside it
with `kubectl exec`, then copy results and release the GPU Pod:

```bash
kubectl auth whoami
kubectl -n ws-qt1ja5byz6220 apply -f ml/pipeline/sgs/pod.yaml
kubectl -n ws-qt1ja5byz6220 get pod gpu-shell05
kubectl -n ws-qt1ja5byz6220 exec -it gpu-shell05 -- bash
# Run unified.py with the intended --original and --requested values.
# Copy results with kubectl cp before deleting the Pod.
kubectl -n ws-qt1ja5byz6220 delete -f ml/pipeline/sgs/pod.yaml
```

For a one-song GPU run, set `ROCKY_INPUT_AUDIO`, `ROCKY_OUTPUT_DIR`,
`ROCKY_ORIGINAL`, and `ROCKY_REQUESTED` in `sgs/unified-pod.example.yaml`.
Its `--resume` option accepts a new output directory or a matching manifest.
The GPU Pod stops after MIDI/GP5 with `--no-publish` so the GPU is released
before CPU-only PDF/MP3 rendering. After the GPU Pod reaches `Succeeded`,
set `ROCKY_RUN_DIR` in `sgs/score-pdf-pod.example.yaml` to the same output
directory and run the CPU Pod:

```bash
kubectl -n ws-qt1ja5byz6220 apply -f ml/pipeline/sgs/unified-pod.example.yaml
kubectl -n ws-qt1ja5byz6220 logs -f pod/rocky-unified-example
kubectl -n ws-qt1ja5byz6220 get pod rocky-unified-example
kubectl -n ws-qt1ja5byz6220 apply -f ml/pipeline/sgs/score-pdf-pod.example.yaml
kubectl -n ws-qt1ja5byz6220 logs -f pod/rocky-score-pdf-example
kubectl -n ws-qt1ja5byz6220 get pod rocky-score-pdf-example
```

The CPU Pod writes `scores/score_outputs.json`, PDF scores, and MP3 playback
files under the same `/data/output_unified/<song>` directory. Run it only
after the GPU Pod succeeds. It installs MuseScore 3 and Poppler in its
ephemeral container; the Playwright image supplies Node/Chromium. The GP5
converter uses Tabtify for guitar and bass, so provide network access and
confirm the input score may be uploaded there. Both Pod examples need the
model environments, checkpoints, BS-RoFormer SW package, and current source
code staged at the paths in `/data`. The CUDA base image in `sgs/pod.yaml`
does not install the Python/PDF tools itself. Check the resulting
`manifest.json` and `scores/score_outputs.json`, copy any wanted results
before cleanup, and remove only the Pods created for the run. The old
`*job*.yaml`, `gpu-job.yaml`, and `volume.yaml` remain in `sgs/legacy/`
as history; never apply them for a new run. None of these steps changes the
Android bundled demo.

## Adding a stage

1. Put the stage's code in this directory.
2. Add a step at the end of `audio_to_midi.sh`. It reads
   `"$out/transcription.mid"` (and `"$out/stems/"` if it needs audio) and
   writes its result into `"$out"` under a new file name.
3. Add the output file to the table above.
4. For the SGS GPU Pod, stage weights on the existing `/data` PVC and pass
   their paths as CLI arguments. `sgs/legacy/run_all.sh` documents the older
   `/data/model/model.safetensors` workflow.

The script skips Demucs when `stems/no_vocals.wav` already exists, so a later
stage can be rerun on a song without separating it again.

## Known limits

- MuScriptor `large` gives broken output on Apple GPUs (MPS), so on a Mac
  the script runs it on the CPU unless `DEVICE` is given.
- Demucs output differs slightly between runs because it applies a random time
  shift, so two runs on the same song do not give byte-identical MIDI.
- On real pop recordings the transcription is far from exact: onset F1 was
  0.38 on ten MulTTiPop segments with `medium`, higher on guitar-band songs
  and lower on synth-heavy ones. `large` has not been scored on that set.
- The script processes one song per call.
- MuScriptor 0.4.0 and Demucs 4.1.0 are pinned in `audio_to_midi.sh`. Change
  them there, and recheck the output, to use newer releases.
