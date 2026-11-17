"""지표 조합 탐색: 지표 1~3개의 종목군 내 백분위 순위를 평균한 종합 점수로 상위 K 보유.
개발 구간에서 전 조합을 돌리고, 같은 조합을 다른 구간에서도 계산해 '개발 성과가 이후 성과를 예측하는가'를 본다.
사용: python3 search_combo.py"""
import itertools, time, sys
import numpy as np, pandas as pd
from multiprocessing import Pool
from panel import load, universe, indicators
import rank_backtest as rb

DEV, VAL = ("2013-07-01", "2018-12-31"), ("2019-01-01", "2022-12-31")
K, EVERY, TR = 40, 21, 3
d = load(); IND = indicators(d); NAMES = list(IND)
UNI = {"시총상위200": universe(d, top=200), "유동성 전종목": universe(d)}
RANK, SUB = {}, {}
for un, U in UNI.items():
    cols = U.columns[U.any(axis=0)]
    SUB[un] = ({"ret": d["ret"][cols]}, U[cols])
    for nm in NAMES:
        RANK[un, nm] = IND[nm][cols].where(U[cols]).rank(axis=1, pct=True)


def job(args):
    un, combo = args
    dd, U = SUB[un]
    S = sum(RANK[un, n] for n in combo) / len(combo)
    out = {"종목군": un, "조합": " + ".join(combo), "개수": len(combo)}
    for tag, (a, b) in (("dev", DEV), ("val", VAL)):
        r, to = rb.run(dd, U, S, a, b, k=K, every=EVERY, buffer=K // 2, tranches=TR)
        s = rb.stats(r)
        # 비용 2배 근사: 회전율 × 평균 편도비용을 한 번 더 차감
        extra = to * (rb.BUY_COST + rb.SELL_COST)
        out.update({f"{tag}_CAGR": s["CAGR"], f"{tag}_MDD": s["MDD"], f"{tag}_샤프": s["샤프"], f"{tag}_회전": to, f"{tag}_CAGR_비용2배": s["CAGR"] - extra})
    return out


if __name__ == "__main__":
    tasks = [(un, c) for un in UNI for n in (1, 2, 3) for c in itertools.combinations(NAMES, n)]
    t0 = time.time()
    with Pool(2) as p:
        rows = p.map(job, tasks, chunksize=8)
    pd.DataFrame(rows).to_csv("results_combo.csv", index=False)
    print(len(rows), "조합,", int(time.time() - t0), "초")
