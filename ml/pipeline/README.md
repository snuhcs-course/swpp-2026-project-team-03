# ROCKY pipeline

One command that takes a song and produces a MIDI transcription. Later stages
(beat alignment, arrangement, part generation) are added to the same script.

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

## Running on the team GPU server (SGS)

The team workspace on [SGS](https://sgs-docs.snucse.org/) has one A100 GPU and
a 20 GiB volume, `muscriptor-data`, that already holds the MuScriptor `large`
weights. No Hugging Face login is needed there. Set up `kubectl` and
`kubelogin` as the SGS manual describes, then, from the repository root:

```bash
# 1. Start the file-transfer pod (no GPU). The volume already exists; this
#    does not recreate or erase it.
kubectl apply -f ml/pipeline/sgs/storage.yaml
kubectl wait --for=condition=Ready pod/rocky-files

# 2. Copy the pipeline code and the songs to the volume.
export COPYFILE_DISABLE=1   # macOS only: keeps ._ metadata files out of the archive
tar -C ml/pipeline -cf - . | kubectl exec -i rocky-files -- tar -C /data/pipeline -xf -
tar -C <folder with songs> -cf - . | kubectl exec -i rocky-files -- tar -C /data/input -xf -

# 3. Run. The pod processes every file in /data/input and exits.
kubectl apply -f ml/pipeline/sgs/gpu-job.yaml
kubectl logs -f rocky-pipeline

# 4. Fetch the results, then remove the finished pod.
mkdir -p outputs/pipeline
kubectl exec rocky-files -- tar -C /data/output -cf - . | tar -C outputs/pipeline -xf -
kubectl delete pod rocky-pipeline
```

A 2 min 27 s song took 3 min 16 s in total on the A100 once the packages were
installed. Songs that already have `/data/output/<name>/transcription.mid` are
skipped; delete that folder to redo a song.

| Path on the volume | Content |
| --- | --- |
| `/data/model/model.safetensors` | MuScriptor `large` weights |
| `/data/pipeline/` | copy of this directory |
| `/data/input/` | songs to process |
| `/data/output/<name>/` | results, same layout as above |
| `/data/cache/` | installed Python packages and downloaded Demucs weights (11 GiB) |

Things to know:

- The workspace has **one GPU**. A second GPU pod is rejected until the first
  one ends, so tell the team before a long run.
- A GPU pod that leaves the GPU idle for 30 minutes is killed by SGS. The job
  pod exits by itself when it finishes; do not keep GPU shells open.
- The volume is on the `ferrari` node, so the job waits for a free GPU on that
  node.
- About 3.7 GiB of the volume is free. Put the weights of another large model
  on a new volume (the workspace quota has 30 GiB left) and mount both.
- Deleting the `muscriptor-data` volume claim erases the weights and the
  installed packages.

## Adding a stage

1. Put the stage's code in this directory.
2. Add a step at the end of `audio_to_midi.sh`. It reads
   `"$out/transcription.mid"` (and `"$out/stems/"` if it needs audio) and
   writes its result into `"$out"` under a new file name.
3. Add the output file to the table above.
4. For the GPU server, copy the stage's weights to the volume and pass their
   path to the stage, the way `sgs/run_all.sh` passes
   `/data/model/model.safetensors`.

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
