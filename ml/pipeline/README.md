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

## Adding a stage

1. Put the stage's code in this directory.
2. Add a step at the end of `audio_to_midi.sh`. It reads
   `"$out/transcription.mid"` (and `"$out/stems/"` if it needs audio) and
   writes its result into `"$out"` under a new file name.
3. Add the output file to the table above.

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
