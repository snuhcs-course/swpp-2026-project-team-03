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

## Pop-DiffuSeq CPU benchmark archive

`tools/benchmark_pop_diffuseq_cpu.py` is a local experiment that loads the
released LMD-matched Pop-DiffuSeq checkpoint and times a fixed-shape,
10-step CPU sampling pass. It is not an end-to-end MIDI generation result.

The upstream code is `musicai-cakecake/pop-diffuseq` at commit
`6c756c2b5c135bcfe2652b2c2f6a44bc5a838b32`. Its README links the
released checkpoints in Google Drive. The local benchmark used
`checkpoints/pop-diffuseq-lmd-matched/ema_0.9999_040000.pt`, together with
`training_args.json` and the vocabulary files in that directory. Those
files, the nested upstream checkout, and `.conda/` are excluded from this
branch; restore them separately before rerunning the benchmark.

Example from the repository root after restoring Python and the checkpoint:

```powershell
python ml/tools/benchmark_pop_diffuseq_cpu.py `
  --repo ml/external/pop-diffuseq `
  --checkpoint ml/checkpoints/pop-diffuseq-lmd-matched/ema_0.9999_040000.pt
```
