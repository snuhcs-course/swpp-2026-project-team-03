# M2M Arranger on BabySlakh: experiment specification

## Purpose

Assess whether the NeurIPS 2025 pretrained band-arrangement checkpoint can
generate requested instrumental tracks from BabySlakh multitrack MIDI. Rocky's
long-term target categories are Piano, Guitar, Bass, and Drums. This is a
symbolic-MIDI arrangement experiment; it does not assess audio transcription.

## Model and representation

- Model: `LongshenOu/m2m_arranger` from `ml/models/m2m_arranger/`.
- Tokenizer: REMI-z, using the fine-tuning tokenizer in `ml/models/m2m_ft/`.
- Generation API: official `BandArranger`, with an explicit target program list.
- Keep target notes out of the content conditioning when measuring
  reconstruction. Retain the other tracks as the musical context.
- Use the API's preceding-bar history for song-level continuity.

## Input checks before generation

For each MIDI, record the track programs, meter, tempo map, bar count, and
whether notes align to a usable bar grid. The published fine-tuned model omits
tempo/time-signature tokens and assumes 4/4 with stable tempo. Reject or report
unsupported meters and tempo changes rather than silently misaligning bars.
Merge tracks in the same target category only when that choice is explicit and
preserve the unmodified source MIDI for comparison.

For the `m2m_arranger` band task, remove drum tracks from the conditioning
input to match the published setup. This means the band-arrangement
experiments do not test use of drum MIDI as context.

## Target categories

Use canonical target program IDs Piano `0`, Guitar `24`, Bass `32`, and Drums
`128`. The linked `m2m_arranger` is the band's reinstrumentation checkpoint;
the published band-arrangement task removes drums from its input and is trained
for pitched instrument outputs. The paper trains and publishes a separate
four-bar drum arrangement model (`LongshenOu/m2m_drummer`). Therefore, treat
drum generation from `m2m_arranger` as unsupported unless a dedicated
exploratory run establishes that it works; use `m2m_drummer` for the paper's
drum task.

## Output and evaluation

Save one generated MIDI and a manifest per input track and target category.
Record model/tokenizer revisions, requested program IDs, random seed, sampling
settings, input MIDI hash, generation status, and any preprocessing. Evaluate
successful outputs against withheld target MIDI using note-level precision,
recall, and F1 with declared onset/offset tolerances; also report instrument
correctness, pitch range, note density, and listening review. Report failures
and unsupported inputs in the per-case table; do not count them as zero-quality
music without separately reporting generation coverage.

The input and output are expected to retain the source segment structure. The
paper explicitly lists that shared-structure assumption and fixed 4/4/stable
tempo scope as limitations. Generated scores should therefore be interpreted
as arrangement outputs, not proof of robust transcription or arbitrary-meter
support.
