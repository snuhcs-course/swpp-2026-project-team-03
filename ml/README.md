# MIDI-RWKV BabySlakh experiment

This worktree has one ML responsibility: test the official pretrained
MIDI-RWKV model as a missing-instrument generator on BabySlakh symbolic MIDI.

## Experiment contract

- Collapse General MIDI programs into Piano, Guitar, Bass, and Drums families.
- For each of 20 BabySlakh tracks, remove every stem in one target family.
- Keep all other MIDI stems as context and never condition on target notes.
- Call MIDI-RWKV `generate_new_track()` with canonical programs 0, 24, 32,
  and -1 respectively.
- Use the official `midi_rwkv.pth` checkpoint converted to FP16 GGML.
- Save generated, combined, and reference MIDI plus a manifest and token log.
- Evaluate completed generations against merged references with the official
  CP, GS, and PCHE formulas adapted to the complete source bar range.

## Layout

| Path | Purpose |
| --- | --- |
| `experiments/midi_rwkv_babyslakh_generation_prompt.md` | Complete experiment specification |
| `tools/run_midi_rwkv_babyslakh.py` | Generation runner |
| `tools/evaluate_midi_rwkv_babyslakh.py` | CP, GS, PCHE and track ranking evaluator |
| `tools/MIDI_RWKV_BABYSLAKH.md` | Setup and command reference |
| `external/MIDI-RWKV/` | Ignored official repository, checkpoint, tokenizer and rwkv.cpp build |
| `outputs/midi_rwkv_babyslakh/` | Ignored generated MIDI, manifests and evaluation reports |

BabySlakh is read from the sibling directory
`C:\Users\USER\AndroidStudioProjects\babyslakh_16k` by default. This experiment
uses MIDI stems only; it does not evaluate raw-audio conditioning.
