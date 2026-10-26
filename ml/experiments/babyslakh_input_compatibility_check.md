# BabySlakh input compatibility check

## Scope

Checked whether one BabySlakh multitrack MIDI can be parsed as REMI-z and
encoded in the input format expected by the `m2m_arranger` checkpoint. This
check did not generate music or assess arrangement quality.

## Sample and MIDI structure

- Input: `babyslakh_16k/Track00002/all_src.mid` (`39,224` bytes).
- BabySlakh consists of the first 20 Slakh2100 tracks, so this is a
  prototyping/in-domain sample, not an independent test item ([Zenodo record](https://zenodo.org/records/4603870)).
- MIDI format: type 1, 384 ticks per beat, 14 MIDI tracks including timing and
  end-of-file tracks.
- `metadata.yaml` describes 12 instrument stems. REMI-z reads these as 12
  program IDs: `7, 10, 28, 34, 50, 52, 55, 61, 81, 88, 115, 128`.
- MIDI meter and tempo: one `4/4` time signature and a constant `120 BPM`.
- REMI-z conversion: **passed**, producing 92 bars.
- Bars 0 and 1 are empty. A generation runner should preserve that silence and
  avoid asking the model to invent target notes for those bars.

## Target-mask and tokenizer checks

For each target category, the corresponding source-family tracks were removed
from a sample bar before building the same sequence shape used by the official
band-arranger API:

`[BOS] [INST] i-target [PITCH] content [HIST] history [SEP]`

The fine-tuning tokenizer loaded locally with a 1,010-token vocabulary. Each
masked input encoded without an unknown token and stayed far below the model's
2,048-token context limit.

| Target | Target token | Sample bar | Remaining context programs | Encoded tokens | Tokenization |
| --- | ---: | ---: | --- | ---: | --- |
| Piano | `i-0` | 13 | 34, 50, 81, 88, 128 | 26 | Passed |
| Guitar | `i-24` | 2 | 10, 34, 50, 81, 128 | 33 | Passed |
| Bass | `i-32` | 2 | 10, 28, 50, 81, 128 | 41 | Passed |
| Drums | `i-128` | 2 | 10, 28, 34, 50, 81 | 44 | Tokenizer only |

The Drums row proves only that REMI-z and the tokenizer can represent the
requested token. The paper's band-arrangement fine-tuning removes drums from
its input and targets pitched instruments; use the separate `m2m_drummer`
checkpoint for the paper's drum-arrangement task.

## Checkpoint forward pass

Loaded the local `m2m_arranger` checkpoint on CPU in BF16 and passed the
26-token Piano-conditioned input through the model:

- Tokenizer vocabulary / model vocabulary: `1010 / 1010` (matched)
- Model context limit: `2048` tokens
- Forward output shape: `(1, 26, 1010)`
- Output logits: finite
- Device: CPU

## Conclusion

`Track00002/all_src.mid` is compatible with the REMI-z parser and the
`m2m_arranger` token/model interface. The sample meets the paper's 4/4 and
stable-tempo assumptions. For a representative band-arrangement run, remove
drums from the conditioning input, withhold every track in the requested
target family, and preserve the two initial empty bars without generation.
BabySlakh comes from the Slakh family used in fine-tuning, so these results are
an in-domain compatibility check rather than an independent generalization
evaluation.
