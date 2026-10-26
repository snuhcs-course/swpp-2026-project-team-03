# Machine Learning

Place audio preprocessing, transcription, generation, evaluation, and model
experiments in this directory.

Suggested subdirectories:

- `src/` for reusable library code
- `scripts/` for reproducible training and inference entry points
- `notebooks/` for exploratory analysis
- `configs/` for versioned experiment configuration
- `tests/` for preprocessing and model-interface tests

Do not commit datasets, audio files, checkpoints, or generated outputs. Keep
those in ignored local directories and document download or preparation steps
in this README.
# M2M Arranger experiment

This worktree evaluates the paper's pretrained **band arrangement** model on
BabySlakh symbolic MIDI. The model can reinterpret existing multitrack MIDI
for a requested instrument set. It does not transcribe audio: audio-to-MIDI
transcription remains a separate upstream step in Rocky.

## Local assets

| Path | Contents |
| --- | --- |
| `external/music2music_code/` | Official arrangement code and inference API |
| `external/REMI-z/` | Official tokenizer and multitrack MIDI representation |
| `models/m2m_arranger/` | Requested Hugging Face fine-tuned band-arranger model (174,824,128-byte BF16 safetensors checkpoint plus tokenizer/config files) |
| `models/m2m_drummer/` | Separate Hugging Face four-bar drum-arranger checkpoint used by `scripts/m2m_arrange_midi.py` |
| `models/m2m_ft/` | Tokenizer repository expected by the official API |
| `experiments/m2m_arranger_babyslakh.md` | Experiment purpose, input assumptions, and planned protocol |
| `experiments/babyslakh_input_compatibility_check.md` | Track00002 REMI-z and CPU forward-pass check |

These downloaded repositories and model files are ignored by Git. Their
upstream revisions are recorded below so they can be fetched again:

- `music2music_code`: `8359bbdb53e4463b85f3d887af510d19952da767`
- `REMI-z`: `dbededa3c3bdf58c4d6af7e43e4dbd8563f26a3e`
- Hugging Face `m2m_arranger`: `4b65245bd42b6bb53c38e9ad7f63dc163d19f729`
- Hugging Face `m2m_drummer`: `daf698d1c9d779a48df89e5e175700d470b5c7c4`
- Hugging Face `m2m_ft` tokenizer: `a3e6215e7273e06f312f6c9332a19d171e74f41c`

## Setup and inference

The official code's `api.arranger.BandArranger` loads a Hugging Face model
and accepts a custom list of target General MIDI programs. Its current helper
hardcodes the tokenizer ID `LongshenOu/m2m_ft`; the downloaded tokenizer is
therefore needed for offline use. Set the model and tokenizer paths to the
local directories above when adapting the API for local inference.

The upstream README specifies Python 3.8, PyTorch 2.2.2, Transformers 4.40.0,
and an editable install of REMI-z. The official tutorial constructs
`BandArranger('LongshenOu/m2m_arranger', hf_ckpt=True)` and calls
`arrange(..., instrument_and_voice=[...])`. This checkpoint uses BF16 weights;
loading and a single CPU forward pass were verified on the sample below;
full-song CPU generation speed has not been measured.

## BabySlakh fit and limits

BabySlakh is symbolically compatible in principle because it contains aligned
multitrack MIDI. Before generating, verify each MIDI has valid meter and bar
boundaries and adapt it to the model's REMI-z representation. The paper's
fine-tuning excludes tempo and time-signature tokens and assumes fixed 4/4
meter and stable tempo. Its band-arrangement model was fine-tuned on Slakh2100,
so BabySlakh results are in-domain style results rather than an independent
generalization test.

The paper describes band arrangement as one-bar segment reconstruction with
instrument/voice conditioning and autoregressive history across bars. It also
describes a separate four-bar drum-arrangement task and publishes a separate
`m2m_drummer` checkpoint. The requested `m2m_arranger` checkpoint is the right
starting point for band reinstrumentation; claims about drum generation should
be evaluated separately against the drum-specific checkpoint.

The published band-arrangement experiment removes drums from its input and
uses pitched instrument outputs. In Rocky's four-category notation, the
canonical target program IDs are Piano `0`, Guitar `24`, Bass `32`, and Drums
`128`. The first three are within the band-arranger's intended setting; treat
Drums as unsupported by this particular fine-tuned checkpoint unless a
separate drum-model experiment confirms otherwise.

One input-compatibility check passed for `Track00002/all_src.mid`; see
`experiments/babyslakh_input_compatibility_check.md`. No music has been
generated in this worktree yet. The experiment requirements are in
`experiments/m2m_arranger_babyslakh.md`.
