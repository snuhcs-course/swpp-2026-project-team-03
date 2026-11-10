# MulTTiPop test results: MIDI pairs

One folder per tested segment, each with two files whose time 0 is the start
of the audio segment:

- `reference.mid`: the dataset's `aligned.mid`, copied unchanged.
- `muscriptor_medium.mid`: MuScriptor `medium` output for the same segment,
  unconditioned, greedy decoding, `--detect-tempo false`.

| Folder | Song | MulTTiPop id (split) | YouTube range (s) |
| --- | --- | --- | --- |
| `Lily_Allen-22_0m33s-1m04s` | Lily Allen – 22 | `WeglOyOLmrY` (test) | 33.40–63.67 |
| `Owl_City-Fireflies_2m35s-3m20s` | Owl City – Fireflies | `nJmBlBEdxAV` (test) | 154.95–199.81 |
| `Taylor_Swift-Fifteen_0m10s-0m54s` | Taylor Swift – Fifteen | `DpgvQJPemad` (dev) | 10.04–53.76 |
| `Carrie_Underwood-Cowboy_Casanova_0m56s-1m27s` | Carrie Underwood – Cowboy Casanova | `nZgWOyE_gry` (test) | 55.76–86.72 |
| `Lady_Gaga-Speechless_0m14s-0m41s` | Lady Gaga – Speechless | `nRPxeXRLgb_` (test) | 13.84–41.28 |
| `U2-Magnificent_0m41s-1m07s` | U2 – Magnificent | `kygzPZbPoKB` (dev) | 40.64–66.63 |
| `Ne_Yo-Closer_0m15s-1m01s` | Ne-Yo – Closer | `nLgakVNzoYp` (test) | 14.82–61.42 |
| `Gwen_Stefani-Early_Winter_0m09s-0m46s` | Gwen Stefani – Early Winter | `kygzJKOLgKB` (test) | 8.61–45.90 |
| `Alicia_Keys-No_One_0m56s-1m28s` | Alicia Keys – No One | `jDgXzvEqoKl` (test) | 55.56–88.34 |
| `The_Killers-Read_My_Mind_1m14s-1m44s` | The Killers – Read My Mind | `ZbgOknqwgnY` (test) | 73.95–104.03 |

The reference files come from [MulTTiPop](https://huggingface.co/datasets/gclef-cmu/multtipop)
by Pruyne et al. (CC BY 4.0), which adapts MIDI from the Lakh MIDI Dataset by
Colin Raffel (CC BY 4.0). They are for evaluation only, not for training.
