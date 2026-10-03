# MIDI-RWKV and BabySlakh whole-track generation experiment

Run a missing-track generation experiment over every track in `babyslakh_16k`
using the official pretrained MIDI-RWKV base checkpoint `midi_rwkv.pth` and the
repository's `generate_new_track()` function.

This experiment measures symbolic MIDI generation: the model receives retained
BabySlakh MIDI stems as context and generates one complete target MIDI track. It
does not receive raw audio. Do not describe the result as audio-to-MIDI or as a
whole-track generation task directly validated in the MIDI-RWKV paper; this is
an application of the repository's supported new-track generation function.

## Scope

1. Process all 20 BabySlakh tracks.
2. Run four independent target-family experiments for every track: `Piano`,
   `Guitar`, `Bass`, and `Drums`.
3. Produce one generated candidate for each track and target family, for up to
   80 generated target tracks.
4. Use seed 110 for the primary comparison. Do not select the best output from
   multiple seeds. Additional seeds may be run later as a separate robustness
   experiment.
5. Do not compute evaluation metrics during this generation run.

## Common instrument-family mapping

Collapse detailed instruments into the same four categories before constructing
each experiment:

| Target family | BabySlakh / General MIDI match | Canonical generated track |
| --- | --- | --- |
| Piano | melodic GM programs 0-7 | `Program_0` |
| Guitar | melodic GM programs 24-31 | `Program_24` |
| Bass | melodic GM programs 32-39 | `Program_32` |
| Drums | `is_drum: true`, program 128, or program -1 | `Program_-1` |

Use `inst_class` and `midi_program_name` only as fallbacks when the program or
drum flag is unavailable. Keep instruments outside these four families in the
conditioning context without remapping them.

## Target removal and conditioning

For each track and target family:

1. Read the stem metadata from `metadata.yaml` and MIDI data from the track's
   `MIDI` directory.
2. Sort stems by stem ID so that input-track order is deterministic.
3. Identify every stem belonging to the selected target family. Exclude all of
   them before constructing the model input, including multiple sessions or
   variants of the same family.
4. Use every available non-target MIDI stem as the retained multitrack context.
5. Do not use excluded target notes, durations, density, polyphony, or any other
   target-derived attribute control for conditioning.
6. Pass an empty attribute-control list to `generate_new_track()` for the
   primary experiment.
7. Preserve all excluded target stems, with their original timing, in
   `reference.mid` for later evaluation.
8. Generate one consolidated canonical target track even when several target
   stems were excluded.
9. If no target-family stem exists, mark that case as skipped. If no retained
   MIDI stem remains, mark the case as failed. Record missing MIDI stem files in
   the manifest.

## Preprocessing and pretrained model

1. Use MIDI-RWKV's released `tokenizer_with_acs.json` tokenizer and its
   REMI+/MMM/BPE representation.
2. Use MIDI-RWKV's complete retained multitrack representation without
   fragmenting or reconstructing the input timeline.
3. Preserve the source tempo, time signatures, ticks per quarter, and timeline.
   Resample individual stems only when needed to match the source ticks per
   quarter.
4. Before tokenizing the retained context, remove melodic or drum notes whose
   pitches are absent from the released tokenizer vocabulary. Record the
   supported ranges and removed-note counts in the manifest. Preserve the
   unfiltered excluded stems in `reference.mid`.
5. Load the official `midi_rwkv.pth` pretrained checkpoint. Convert it with the
   official `rwkv.cpp` converter to FP16 GGML when the converted model is not
   already available.
6. Record SHA-256 hashes for both the original checkpoint and converted model.
7. Use the BabySlakh runner at
   `ml/tools/run_midi_rwkv_babyslakh.py`, which calls `generate_new_track()`
   directly. For drums, pass `(-1, [])` so that the prompt contains
   `Program_-1`; do not route drums through upstream validation that rejects
   negative program numbers.

## Generation settings

Use autoregressive sampling with these fixed primary-run settings:

```text
temperature = 1.0
repetition_penalty = 1.2
top_k = 20
top_p = 0.95
epsilon_cutoff = 0.0009
max_new_tokens = 8192
seed = 110
num_beams = 1
do_sample = true
attribute_controls = []
```

Encode the complete retained multitrack MIDI as the prompt, followed by
`Track_Start`, the canonical
`Program_*` token, and the empty attribute-control list.

## Output validation

For every non-skipped case:

1. Verify that the last decoded track matches the requested canonical program;
   for drums, verify `is_drum: true` and the presence of `PitchDrum` events.
2. Verify that the generated track contains at least one note.
3. Do not infer success by comparing decoded track counts with input stem
   counts. MidiTok may merge context stems that share a program.
4. Record whether the model generated `Track_End` naturally.
5. If `max_new_tokens` is reached first, append `Track_End` only for decoding,
   retain the output when it contains a valid target track, and mark the result
   as truncated rather than silently treating it as a clean completion.
6. Clip the generated result to the source MIDI timeline. Record whether notes
   were removed or clipped at the boundary.
7. Record generated note count, token count, decoded duration, source duration,
   and runtime. Mark empty, wrong-program, or entirely out-of-range outputs as
   failed.

## Output layout

Store results by track and target family under
`ml/outputs/midi_rwkv_babyslakh`:

```text
ml/outputs/midi_rwkv_babyslakh/
  Track00001/
    piano/
      generated.mid
      combined.mid
      reference.mid
      generation.log
      manifest.json
    guitar/
      ...
    bass/
      ...
    drums/
      ...
```

- `generated.mid`: only the one consolidated generated canonical target track.
- `reference.mid`: all excluded reference stems with original timing.
- `combined.mid`: retained context tracks plus the generated target track.
- `generation.log`: model output tokens and generation warnings.
- `manifest.json`: case status, target mapping, retained and excluded stem IDs,
  missing MIDI stems, tokenizer and model paths, checkpoint hashes, seed,
  sampling settings, input and generated token counts, context and reference
  track counts, generated note count, source and generated durations,
  `Track_End` status, truncation status, boundary clipping status, warnings, and
  runtime.

## Interpretation constraints

1. The official MIDI-RWKV paper primarily evaluates short bar-infilling. Report
   this whole missing-track experiment as a repository-supported application,
   not as a reproduction of the paper's evaluated task.
2. BabySlakh is synthetic multitrack data and differs from MIDI-RWKV's training
   distribution. Treat this domain shift as a limitation.
3. Compare MIDI-RWKV and MIDI-GPT using the same BabySlakh target-removal,
   family-collapse, reference construction, and evaluation policy.
4. Evaluate only after generation has finished; evaluation is outside this run.
