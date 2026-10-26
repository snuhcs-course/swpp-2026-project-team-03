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

## GP5 to PDF

The standalone [GP5 to PDF module](gp5_to_pdf/README.md) renders completed GP5
tabs through Tabtify. It is separate from the bundled Android demo and from
the MIDI-to-GP5 stage.
