"""ADX 순위 전략의 장치 조합을 한 구간에서 비교. 사용: python3 dev_grid.py 2013-07-01 2018-12-31"""
import sys, itertools
import numpy as np, pandas as pd
from panel import load, universe, indicators
from rank_backtest import run, stats, market_filter

A, B = sys.argv[1], sys.argv[2]
d = load(); U = universe(d, top=200); Uall = universe(d); S = indicators(d)["4.ADX(높음)"]
ix = {k: pd.read_csv(f"data_index/{k}.csv", parse_dates=["date"]).set_index("date").close.loc[:"2026-11-16"] for k in ["KOSPI", "KOSDAQ", "KOSPI200"]}
bench = {k: v.pct_change().loc[A:B].dropna() for k, v in ix.items()}
bench["전종목 동일비중"] = d["ret"].where(Uall.shift(1, fill_value=False)).mean(axis=1).loc[A:B]
bench["상위200 동일비중"] = d["ret"].where(U.shift(1, fill_value=False)).mean(axis=1).loc[A:B]
expo = market_filter(ix["KOSPI"])
yr = lambda r: (1 + r).groupby(r.index.year).prod() - 1
bs = {k: stats(v) for k, v in bench.items()}
best_bench = max(v["CAGR"] for v in bs.values()); mdd_lim = 1.2 * bs["KOSPI"]["MDD"]
print(f"구간 {A} ~ {B}")
print("벤치마크:", {k: f"{v['CAGR']*100:.1f}% / MDD {v['MDD']*100:.1f}%" for k, v in bs.items()})
print(f"합격선: 연수익률 > {best_bench*100:.1f}% (모든 벤치마크 초과), MDD ≥ {mdd_lim*100:.1f}%, 비용 2배에도 초과")
ky = yr(bench["KOSPI"]); surge = set(ky.index[ky >= 0.30])
rows = []
for every, buf, flt in itertools.product((21, 63, 126), (0, 20), (False, True)):
    kw = dict(k=40, every=every, buffer=buf, tranches=3, expo=expo if flt else None)
    r, to = run(d, U, S, A, B, **kw); r2, _ = run(d, U, S, A, B, cost_mult=2, **kw)
    s, s2 = stats(r), stats(r2); y = yr(r)
    wins = sum((y[t] >= 0.7 * ky[t]) if t in surge else (y[t] > ky[t]) for t in y.index)
    ok = s["CAGR"] > best_bench and s["MDD"] >= mdd_lim and s2["CAGR"] > best_bench
    rows.append({"교체주기": every, "버퍼": buf, "시장필터": "O" if flt else "-", "연수익률": s["CAGR"], "MDD": s["MDD"], "샤프": s["샤프"],
                 "비용2배 연수익률": s2["CAGR"], "연회전": to, "코스피 대비 승": f"{wins}/{len(y)}", "판정": "합격" if ok else "미달"})
pd.set_option("display.width", 220); pd.set_option("display.float_format", "{:.3f}".format)
print(pd.DataFrame(rows).to_string(index=False))
