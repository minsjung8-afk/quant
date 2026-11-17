"""지표 조합 전수 탐색(1~4개): 조합의 종합 순위 상위 40종목을 보유했을 때의 성과를 전체 기간에 대해 계산.
종목군 3종(코스피·코스닥 전체 보통주, 거래대금 10억 이상, 시총 상위 500)에서 각각 계산해 연도별 수익률을 저장한다."""
import itertools, time
import numpy as np, pandas as pd
from multiprocessing import Pool
from panel import load, universe, indicators
import rank_backtest as rb

A, B = "2013-07-01", "2026-11-16"
d = load(); IND = indicators(d); NAMES = list(IND)
UNI = {"코스피·코스닥 전체": universe(d, min_val=0, min_price=0), "거래대금 10억 이상": universe(d), "시총 상위 500": universe(d, top=500)}
RANK, SUB = {}, {}
for un, U in UNI.items():
    cols = U.columns[U.any(axis=0)]
    SUB[un] = ({"ret": d["ret"][cols]}, U[cols])
    for nm in NAMES:
        RANK[un, nm] = IND[nm][cols].where(U[cols]).rank(axis=1, pct=True)
del IND


def job(args):
    un, combo = args
    dd, U = SUB[un]
    S = sum(RANK[un, n] for n in combo) / len(combo)
    r, to = rb.run(dd, U, S, A, B, k=40, every=21, buffer=20, tranches=3)
    y = (1 + r).groupby(r.index.year).prod() - 1
    eq = (1 + r).cumprod()
    out = {"종목군": un, "조합": " + ".join(combo), "개수": len(combo), "회전": to, "MDD": (eq / eq.cummax() - 1).min(),
           "샤프": r.mean() / r.std() * np.sqrt(252)}
    for per, (a, b) in {"dev": ("2013-07-01", "2018-12-31"), "val": ("2019-01-01", "2022-12-31"), "fin": ("2023-01-01", B)}.items():
        x = r.loc[a:b]; out[per] = (1 + x).prod() ** (252 / len(x)) - 1
    out.update({f"y{k}": v for k, v in y.items()})
    return out


if __name__ == "__main__":
    tasks = [(un, c) for un in UNI for n in (1, 2, 3, 4) for c in itertools.combinations(NAMES, n)]
    t0 = time.time()
    with Pool(2) as p:
        rows = p.map(job, tasks, chunksize=16)
    pd.DataFrame(rows).to_csv("reports/full_search_2026-11-17.csv", index=False)
    print(len(rows), "건,", int(time.time() - t0), "초")
