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

**Requested stems first (contract 14).** When the original is unknown, the
`focus_probe` stage after separation transcribes the requested instruments'
stems plus drums (drum sync always needs the drum MIDI) and runs the note gate
on the requested ones with the unknown-original sparse rule. If every
requested instrument keeps notes, nothing has to be generated: only these
stems are transcribed and MIDI-GPT does not run (for example a band of
keyboard and bass skips the guitar stem). If any requested instrument is empty
or sparse, the remaining stems are transcribed too (the probe MIDI files are
reused), so MIDI-GPT always has the whole band as context. Two requested
guitars may need a generated second guitar, which is known only after the
guitar TAB; unless `guitar_stereo` already shows two panned guitars, every
stem is transcribed from the start (`probe: {skipped}`). The manifest records
`probe: {in_song, all_found}` and `transcribe_stems` for the server's progress.
A known original (the app's guitar-count redo) skips the probe and
transcribes the declared stems as before. The app's solo mode adds
`--personal`, which only checks that one instrument was requested.

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

The piano-stem merge raised the manifest contract to version 9, and the rule
gates below raised it to version 11. Start a **new** output directory; older
`manifest.json` files cannot be resumed with this code.

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

## Rule gates: non-band input and notes in resting stems

`rule_gates.py` adds two model-free stages to `unified.py`. The thresholds
come from 14 band songs and 45 non-band files measured on 2026-11-09
(`benchmarks/2026-11-09-rule-gates.md`).

**`input_check`** runs right after `bs_roformer`, on the CPU, before any
MuScriptor process starts. It rejects the song when it is shorter than 30 s,
when all six stems together are below -50 dBFS, or when drums + bass + guitar
+ piano carry less than 15 % (`--min-band-ratio`) of the separated energy
(speech, street or room sound, sound effects, a single non-band instrument).
Music built from our instruments, such as piano or guitar solos, passes on
purpose. A rejected song writes
`input_check.json`, sets `manifest.json` `status` to `rejected` with
`rejection.code` (`too_short`, `silent` or `not_band_audio`), and
`unified.py` exits with code 3. The GPU Pod therefore ends after separation
and the agent deletes it, freeing the GPU for the next song. BS-RoFormer runs
in its own process, so no model is left in GPU memory at this point. Resuming
a rejected run repeats the check and gives the same answer.

**`note_gate`** runs after MuScriptor and before `merge_stems`, for every
transcribed stem (drums, bass, guitar, piano). For each note it reads the
stem's loudest 23 ms frame from just before the onset to 0.2 s after it
(0.08 s for drum hits) and compares it with the stem's playing level, the
99th percentile of its frame power. Notes more than 40 dB below
(`--note-floor-db`), or below -65 dBFS, are removed. This targets notes that
MuScriptor writes from the residue of a resting stem. Except for drums, the
gate also cuts a note's end where its stem stays more than 30 dB below its
playing level for 0.5 s: MuScriptor can hold the last note before a rest until
the next onset (한 페이지가 될 수 있게 held one E♭5 for 11 s over bars 113-120,
which the TAB showed as one tied note per bar). Contract 12 adds this trim.
The gated MIDI goes to `stem_midi_gated/`; the raw MuScriptor output stays in
`stem_midi/`, and `note_gate.json` records per-stem counts.

The user's original lineup takes priority:

| Original lineup | Few notes left after the gate | Every note removed by the gate |
| --- | --- | --- |
| declared (instrument selected) | kept | gate skipped for that stem, raw notes kept (`kept_ungated_declared`) |
| unknown | fewer than 20 notes per minute (`--min-notes-per-minute`): stem treated as absent (`dropped_sparse`) | stem absent |

A declared instrument that the gate would empty or that keeps fewer than
`--min-notes-per-minute` notes is still made, but is marked `faint` in
`note_gate.json`. Requested parts marked this way are listed in
`manifest.json` `faint_parts` (`piano`, `guitar`, `bass`, `drums`); the server
passes them to the app, which can warn that the part may be empty or inaccurate.

**`guitar_stereo`** (contract 13) runs before the guitar TAB when the original
lineup is unknown. If the guitar stem's left and right channels are nearly
unrelated (median 1 s correlation below 0.2) and balanced (median energy
balance below 0.17), two guitars are panned apart and `skyline_tab.py` gets
`--split always`. Otherwise its chord rule decides (`ml/guitar_tab`, recalibrated
on 2026-11-09). This catches two guitars that play the same chords in the same
register, such as 21 Guns. The result is kept in `guitar_stereo.json` and
`manifest.json` `guitar_stereo`.

A stem treated as absent behaves like an instrument missing from the original:
if the user's lineup asks for it, MIDI-GPT generates it. When the original is
unknown and no band stem keeps any notes, the song is rejected as
`not_band_audio` at this point (after transcription).

### Measuring the thresholds

```bash
python measure_gates.py /data/output_unified/band14-* /data/output_unified/nonband-* --json gates.json
python measure_gates.py /data/output_unified/hanpe --rest guitar:212.0-224.5
```

It needs runs that still have `stems/` (run with `--no-publish`; the server
deletes stems after a song is complete). Choose `--min-band-ratio` below the
lowest band14 song with a margin and above the non-band audio, and
`--note-floor-db` between the rest-passage notes and the played notes.

## Automatic score and playback publication

`unified.py` calls `publish_scores.py` after assembling `full_score.mid`.
This stage needs MuseScore, Poppler `pdfinfo`, Node.js, `pyguitarpro`, and the
`gp5_to_pdf` module from `ml/gp5-alphatab` with alphaTab/Playwright/Chromium.
The GP5 and rendering assets stay local; Tabtify access is not required.
Install the locked Node dependencies with `npm ci` in `ml/gp5_to_pdf` before
publication (the example CPU Pod does this on startup). Set `--musescore`, `--pdfinfo`,
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
After preparing score and GP5 inputs, the publisher runs independent PDF and
MP3 exports with two workers by default (the CPU Pod passes
`--render-workers 2` explicitly). Set `--render-workers 1` to compare against
sequential export, or use up to four after checking CPU and memory headroom.
It writes the publication contract only after every export succeeds.
Before the two-stage MP3 patch, on the Immigrant Song validation CPU Pod,
forced exports with one, two, then
one worker took 115, 67, and 117 seconds respectively; the second serial run
checks that the gain was not just a warm-cache effect. Package installation
time is excluded from these export timings.

The frontend contract is `scores/score_outputs.json` (version 6): a full-band
PDF and MP3, plus a PDF and MP3 for every present instrument family (guitar,
bass, piano, drums). The MP3 names follow the iteration 2 demo:
`scores/band.mp3`, `scores/guitar.mp3`, `scores/bass.mp3`,
`scores/piano.mp3`, and `scores/drums.mp3`. All playback audio is synthesized
from program-preserving copies of `full_score.mid`; it is not the original
recording or a separated stem. The stage also writes `scores/<part>.mid` for each
present instrument. When a second guitar is generated, `guitar.pdf` is the
combined standard-notation score and `guitar_1.pdf` and `guitar_2.pdf` are
separate TAB PDFs. Matching MIDI and MP3 files are also provided. When
skyline splits two original guitars, `guitar.pdf` contains both TAB parts and
each GP5 track is also published alone as `guitar_1` and `guitar_2` (version 6;
version 5 made these only for a generated second guitar).
`scores/piano.pdf` contains the merged piano-stem track (or an AI-generated
piano part when the original lacks a keyboard). TAB PDFs for guitar and bass come from their
processed GP5 files through `gp5_to_pdf/convert.js` (local alphaTab). When MIDI-GPT
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
unchanged. Each MP3 first imports its MIDI into a MuseScore `.mscx` file and
then renders that score. MuseScore 3's direct MIDI-to-MP3 command rendered
one-note guitar and bass tests identically to piano despite their distinct GM
programs. The two-stage path preserves the final assembled MIDI programs and
notes, including each song's acoustic or electric guitar choice. The
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

The unified runner defaults to two concurrent MuScriptor stem processes on
the SGS A100, starting with guitar and bass to reduce time waiting for the
longest stem. `--transcription-workers 1` uses one process and loads the model
once for all stems; `--transcription-workers 4` is available for comparison.
On the Immigrant Song validation, the one-process stage took 200.54 seconds,
two workers took 160.82 seconds with the long-stem-first order (166.03 seconds
in the old order), and four took 159.23 seconds. Peak GPU memory
for two/four workers was 22,343/44,684 MiB. All four MIDI files were
byte-identical across modes. The two-worker default saves most of the time
with half the GPU memory of four workers; smaller GPUs should use one worker.
An end-to-end two-worker GPU run of that song recorded 303.55 seconds across
stages, versus 360.74 seconds in the one-worker run. Separation also varied
between those runs (73.80 versus 92.04 seconds), so the MuScriptor stage
measurements above are the cleaner concurrency comparison.
Each stem keeps its own progress JSONL and MIDI output; valid MIDI files are
reused on resume. The run manifest records wall-clock `stage_seconds` for
every stage, including the MuScriptor batch.
This changed the pipeline contract to 10: start a new output directory when
switching from an older run.

To repeat the MuScriptor comparison after a completed run, use a fresh
benchmark output directory:

```bash
/data/rocky-unified/.venv/bin/python ml/pipeline/bench_transcription.py \
  /data/output_unified/song/stem_midi/transcription_jobs.json \
  /data/output_unified/song-transcription-bench \
  --model /data/model/model.safetensors --device cuda --workers 2 4
```

The script records wall time, peak GPU memory, and per-stem SHA-256 equality
against the source run's MIDI in `summary.json`. For PDF/MP3 comparison,
rerun `publish_scores.py` on the same completed score with `--force` and
`--render-workers 1` or `2`, keeping the CPU Pod's limits unchanged.

The 12-song November 3 validation gave a baseline median of 807.5 seconds
per song (GPU stage 629.5 seconds, CPU publication 178 seconds). Stem
separation was only 14.1 seconds median; the sum of MuScriptor chunk times
was 302.9 seconds median. These chunk times omit model loading and setup.
MIDI-GPT can also take several minutes for a requested second guitar. The
new `stage_seconds` values measure full stage wall time so the next GPU run
can establish the actual gain; local tests do not measure A100 throughput.

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
converter renders guitar and bass without uploading GP5 files. The CPU Pod
installs the locked Node dependencies on startup; its Playwright image already
contains Chromium. Both Pod examples need the
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
