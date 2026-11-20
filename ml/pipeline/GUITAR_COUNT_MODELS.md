# Guitar-count models and rollback

## What changed

For an unknown original with guitar notes, `unified.py` can now use three
frozen guitar-count models. Each returns **one** or **two** original guitars:

| Model ID | Classifier | Input |
| --- | --- | --- |
| `fusion_extra_trees` | ExtraTrees | Four existing guitar-count scores, MuScriptor decoder summary, RoFormer guitar summary |
| `fusion_rbf_svm` | RBF SVM | The same inputs |
| `fusion_stem_extra_trees` | ExtraTrees | The same inputs plus four guitar-stem audio scores |

The three `.joblib` files contain fitted transforms and classifier state,
not source audio, song metadata, or per-song labels. The RBF SVM's classifier
state necessarily includes support vectors in transformed feature space.

With `--guitar-count-classifier alpha_three_arm`, a new job receives one model
with probability 1/3. `manifest.json` stores the assignment and reuses it on
resume. `guitar_count.json` stores all three predictions and the selected
model's count. Only the selected count controls guitar TAB split/compression
and any second-guitar generation. The model scores are uncalibrated and do not
change the assignment. This Git change does not update model weights or
assignment probabilities from star ratings.

Known original guitar counts bypass this selection. If stereo measurements
are unavailable, the pipeline uses its prior rule and marks the model result
ineligible. The command-line default is `alpha_three_arm`. It needs the Python
packages in `requirements-alpha.txt` in the interpreter that runs `unified.py`.
The app/server rating linkage is reviewed separately. Deploy the pipeline and
server changes together before serving alpha users.

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
