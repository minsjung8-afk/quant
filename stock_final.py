"""개별 종목 후보의 구간 상세. 사용: python3 stock_final.py fin   (후보는 reports/stock_candidates.csv, 최종 구간은 한 번만 연다)"""
import sys
import numpy as np, pandas as pd
from panel import load, universe, indicators
import rank_backtest as rb

PER = {"dev": ("2013-07-01", "2018-12-31"), "val": ("2019-01-01", "2022-12-31"), "fin": ("2023-01-01", "2026-11-16")}
a, b = PER[sys.argv[1]]
d = load(); IND = indicators(d); UNI = {"시총상위200": universe(d, top=200), "유동성 전종목": universe(d)}
cands = pd.read_csv("reports/stock_candidates.csv")
ix = {k: pd.read_csv(f"data_index/{k}.csv", parse_dates=["date"]).set_index("date").close.pct_change().loc[a:b].dropna() for k in ["KOSPI", "KOSPI200", "KOSDAQ"]}
yr = lambda r: (1 + r).groupby(r.index.year).prod() - 1
cum = lambda r: (1 + r).prod() - 1
ks = rb.stats(ix["KOSPI"])
rows, Y = [], {}
for un in cands.종목군.unique():
    ew = d["ret"].where(UNI[un].shift(1, fill_value=False)).mean(axis=1).loc[a:b]
    es = rb.stats(ew); Y[f"{un} 동일비중"] = yr(ew)
    rows.append({"전략": f"[{un} 동일비중]", **es, "누적": cum(ew)})
    for n, c in enumerate(cands[cands.종목군 == un].조합, 1):
        U = UNI[un]; parts = c.split(" + ")
        S = sum(IND[p].where(U).rank(axis=1, pct=True) for p in parts) / len(parts)
        kw = dict(k=40, every=21, buffer=20)
        r, to = rb.run(d, U, S, a, b, tranches=3, **kw); r2, _ = rb.run(d, U, S, a, b, tranches=3, cost_mult=2, **kw); r21, _ = rb.run(d, U, S, a, b, tranches=21, **kw)
        s, s2, s21 = rb.stats(r), rb.stats(r2), rb.stats(r21)
        y, ye = yr(r), yr(ew); Y[c] = y
        wins = int((y > ye).sum())
        crit = [s["CAGR"] > es["CAGR"], s["MDD"] > es["MDD"], s2["CAGR"] > es["CAGR"], s21["CAGR"] > es["CAGR"], wins >= int(np.ceil(0.75 * len(y)))]
        sub = [s["MDD"] >= 0.8 * ks["MDD"], cum(r) >= 0.8 * cum(ix["KOSPI"])]
        rows.append({"전략": c, **s, "누적": cum(r), "비용2배": s2["CAGR"], "21묶음": s21["CAGR"], "연회전": to, "동일비중 대비 승": f"{wins}/{len(y)}",
                     "주기준1~5": "".join("O" if x else "X" for x in crit), "보조6~7": "".join("O" if x else "X" for x in sub)})
for k, v in ix.items():
    rows.append({"전략": f"[{k}]", **rb.stats(v), "누적": cum(v)}); Y[k] = yr(v)
pd.set_option("display.width", 260); pd.set_option("display.max_colwidth", 70); pd.set_option("display.float_format", "{:.3f}".format)
print(f"=== {sys.argv[1]}: {a} ~ {b} ==="); print(pd.DataFrame(rows).to_string(index=False))
print((pd.DataFrame(Y) * 100).round(1).T.to_string())
