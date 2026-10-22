"""eval_results.csv → 곡별 종합 순위 (MIDI-RWKV 팀 표와 같은 열).

사용법: python scripts/rank_tracks.py [eval_results.csv] [출력.csv]

계산 방식 (MIDI-RWKV 표에서 역으로 추정 — 그쪽 계산식 확인 필요)
  GS match   = 1 - GS차이 (악기별, 드럼 포함 평균)
  PCHE match = 1 - PCHE차이 / log2(12) (악기별, 드럼 제외 평균)
  CP         = 악기별 CP 평균 (드럼 제외)
  Adjusted   = Σ(악기별 지표 평균) / 4  → 평가 못 한 악기는 0점 취급
"""
import sys
import numpy as np
import pandas as pd

src = sys.argv[1] if len(sys.argv) > 1 else "results/eval_results.csv"
out = sys.argv[2] if len(sys.argv) > 2 else "results/track_ranking.csv"
d = pd.read_csv(src)
d["gs_match"] = 1 - d.gs_diff
d["pche_match"] = 1 - d.pche_diff / np.log2(12)
d["score"] = d[["cp", "gs_match", "pche_match"]].mean(axis=1, skipna=True)
rows = []
for (model, song), s in d.groupby(["model", "song"]):
    rows.append(dict(Model=model, Track=song, Generated=f"{len(s)}/4",
                     CP=s.cp.mean(), GS_match=s.gs_match.mean(), PCHE_match=s.pche_match.mean(),
                     Adjusted=s.score.sum() / 4))
r = pd.DataFrame(rows).sort_values(["Model", "Adjusted"], ascending=[True, False])
r.insert(0, "Rank", r.groupby("Model").cumcount() + 1)
r.round(4).to_csv(out, index=False, encoding="utf-8-sig")
print(r.round(4).to_string(index=False))
print("저장:", out)
