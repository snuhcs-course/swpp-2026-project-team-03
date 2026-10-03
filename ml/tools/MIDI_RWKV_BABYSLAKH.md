# MIDI-RWKV BabySlakh runner

`run_midi_rwkv_babyslakh.py` removes a target instrument family from each
BabySlakh track and calls MIDI-RWKV's `generate_new_track()` using every
remaining MIDI stem as context.

## Instrument collapse

The runner normalizes detailed General MIDI programs before generation:

| Family | Source GM programs | Canonical model program |
| --- | --- | --- |
| Piano | 0-7 | 0 |
| Guitar | 24-31 | 24 |
| Bass | 32-39 | 32 |
| Drums | drum track / BabySlakh program 128 | `Program_-1` |

Metadata labels are used as a fallback. All stems mapped to the selected target
family are excluded. The model generates one consolidated canonical target
track. Target note events and target-derived attribute controls are never used
for conditioning.

`Program_-1` is passed directly to MIDI-RWKV's `generate_new_track()`. The
runner validates the final decoded track by its drum flag and note content.
This matters because MidiTok can merge context stems that share a program, so
the decoded track count can be smaller than the number of input stems.

## Setup

The official repository is cloned locally at `ml/external/MIDI-RWKV` with its
pinned submodules. It is ignored by the Rocky repository because it is an
independent Git repository and contains the pretrained checkpoint.

Use Python 3.11 and install the MIDI-RWKV dependencies plus PyYAML:

```powershell
pip install torch transformers miditok symusic numpy pyyaml
```

Build the `rwkv.cpp` shared library by following its Windows instructions. The
runner loads the official `midi_rwkv.pth` pretrained checkpoint. If the
converted model is absent, it automatically runs the official converter and
creates an FP16 GGML model at
`rwkv.cpp/python/rwkv_cpp/rcpp.bin`.

The equivalent manual conversion command is:

```powershell
python ml/external/MIDI-RWKV/rwkv.cpp/python/convert_pytorch_to_ggml.py `
  ml/external/MIDI-RWKV/midi_rwkv.pth `
  ml/external/MIDI-RWKV/rwkv.cpp/python/rwkv_cpp/rcpp.bin `
  FP16
```

## Run

All 20 tracks and all four targets:

```powershell
python ml/tools/run_midi_rwkv_babyslakh.py
```

Use `--reconvert-model` to force checkpoint conversion again. Use
`--checkpoint-path` only when evaluating a different pretrained PyTorch
checkpoint.

A single track and target for an initial CPU measurement:

```powershell
python ml/tools/run_midi_rwkv_babyslakh.py `
  --tracks Track00001 `
  --targets Piano
```

Use `--overwrite` to replace a completed case. A failed case writes its error to
`manifest.json`; subsequent cases continue unless `--fail-fast` is set.

A short CPU smoke test for drum generation is:

```powershell
python ml/tools/run_midi_rwkv_babyslakh.py `
  --tracks Track00001 `
  --targets Drums `
  --max-new-tokens 128 `
  --overwrite `
  --fail-fast
```

The token limit can stop generation before the model emits `Track_End`. The
runner records that condition as a warning and still writes a valid MIDI when
the decoded target track contains notes. Use the default 8192-token limit for
the full experiment.

## Output

Results are written under `ml/outputs/midi_rwkv_babyslakh`:

```text
Track00001/
  piano/
    generated.mid
    combined.mid
    reference.mid
    generation.log
    manifest.json
```

- `generated.mid` contains the one generated canonical target track.
- `combined.mid` contains retained context tracks and the generated track.
- `reference.mid` contains every excluded target-family stem.
- `manifest.json` records the collapse mapping, included and excluded stems,
  sampling settings, checkpoint hash, runtime, warnings, and output statistics.
