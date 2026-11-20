# Guitar-count models and rollback

## What changed

For an unknown original with guitar notes, `unified.py` can now use three
frozen guitar-count models. Each returns **one** or **two** original guitars:

| Model ID | Classifier | Input |
| --- | --- | --- |
| `fusion_extra_trees` | ExtraTrees | Four existing guitar-count scores, MuScriptor decoder summary, RoFormer guitar summary |
| `fusion_rbf_svm` | RBF SVM | The same inputs |
| `fusion_stem_extra_trees` | ExtraTrees | The same inputs plus four guitar-stem audio scores |

The three `.joblib` files contain fitted transforms and classifier parameters;
they are frozen in Git and a job
does not fit or update them. The files contain fitted transforms and classifier
state, not source audio, song metadata, or per-song labels. The RBF SVM's
classifier state necessarily includes support vectors in transformed feature
space.

With `--guitar-count-classifier alpha_three_arm`, a new job receives one model
with probability 1/3. `manifest.json` stores the assignment and reuses it on
resume. Only that model is loaded and run for the job. `guitar_count.json`
stores its prediction and selected count. Only that count controls guitar TAB
split/compression and any second-guitar generation. The model scores are
uncalibrated and do not change the assignment. This Git change does not update
model weights or assignment probabilities from star ratings.

## Decision after alpha testing

After alpha testing, use the collected ratings and per-model job records to
choose one of the three arms or roll back to the bundled four-score ExtraTrees
model. Compare rating distribution and submission rate alongside completion,
failure, and processing time. Keep the 1/3 assignment fixed during alpha.
Selecting one alpha arm as the sole production model requires a reviewed
code/configuration change; the ExtraTrees rollback is already bundled below.
Do not use independent evaluation material to tune this decision or claim an
independent result for a model chosen from that material.

Known original guitar counts bypass this selection. If stereo measurements
are unavailable, or an alpha feature/model step fails, the pipeline uses its
prior stereo then skyline rule. `guitar_count.json` records `rule_fallback`,
the error and `experiment_eligible: false`. The command-line default is
`alpha_three_arm`.
The app/server rating linkage is reviewed separately. Deploy the pipeline and
server changes together before serving alpha users.

## Deployment files and environment

Copy these files together to `/data/pipeline` on each serving PVC:

- `unified.py`, `guitar_count_model.py`, `guitar_count_alpha.py`,
  `guitar_count_extra_trees_v1.json`, `guitar_count_alpha_models/`
- `decoder_logits_feature.py`, `roformer_shared_feature.py`,
  `stem_audio_features.py`, `transcribe_with_progress.py`, `rule_gates.py`

Install `requirements-alpha.txt` into `/data/rocky-unified/.venv`, the Python
environment that runs `unified.py`. First record the installed versions of
numpy, scipy, scikit-learn, joblib and narwhals, and use a dry run to inspect
the dependency changes. Install with dependencies enabled; `narwhals` is a
required package. Check the model environment and a full pipeline smoke run
before switching API Pods. The TAB subprocess uses its own environment.
The deployment order is pipeline files and model packages on both PVCs,
then PR #31's server version. PR merge alone does not update a PVC or Pod.

The RoFormer summary currently requires a second model pass. Stem separation
delegates to the upstream inference subprocess; changing it to capture a hook
would change the feature extraction path used by these frozen artifacts.
`manifest.json` records the extra pass in `stage_seconds.roformer_shared`.
The isolated GPU smoke (`rocky-alpha-three-arm-smoke-20261120-v4`) recorded
14.12 seconds for this second pass and 20.45 seconds for stem separation on
its one input. These are stage timings for that run, not an estimate for all songs.

## Bundled rollback model

The four-score ExtraTrees model is **included in this Git change**:

- Artifact: `guitar_count_extra_trees_v1.json`
- Inference: `guitar_count_model.py` (no scikit-learn or SciPy at runtime)
- Input: guitar-stem left/right correlation and balance, plus the gated MIDI's
  unplayable-chord and wide-range fractions
- Artifact SHA-256 after Git checkout:
  `def05aa9ff3a25f5c449d7830cb09c7c9610dd8d9aff08b267d8893898e1298d`

To use it for **new** jobs, pass:

```text
--guitar-count-classifier extra_trees
```

The adjacent JSON artifact is the default `--guitar-count-model` path. For an
explicit path, run:

```text
--guitar-count-classifier extra_trees \
--guitar-count-model /data/pipeline/guitar_count_extra_trees_v1.json
```

Keep each already-started three-model job on its recorded assignment when
using `--resume`. Start a **new output directory** for a fallback run; the
manifest checks input, settings, model hash, and assigned arm. Do not replace
model files behind an in-progress job. The earlier sequential stereo → skyline
method is available with `--guitar-count-classifier rule`. This gives two rollback steps: three models → four-score
ExtraTrees → prior rule.

## Verification and limits

An isolated SGS GPU run completed through `full_score.mid` (Pod
`rocky-alpha-three-arm-smoke-20261120-v4`, exit code 0). All three models
produced a count, and their required feature vectors passed consistency
checks. Local pipeline tests pass. This verifies a working GPU code path,
**not** classification accuracy.

PDF/MP3 publication and app/server star-rating linkage were outside this
check. Verify those integrations before the alpha rollout.
