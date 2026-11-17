"""전수 탐색 결과 순위: 세 구간·세 종목군에서 고르게 통한 조합을 찾는다."""
import numpy as np, pandas as pd
from collections import Counter
from panel import load, universe
import rank_backtest as rb

R = pd.read_csv("reports/full_search_2026-11-17.csv")
d = load()
UNI = {"코스피·코스닥 전체": universe(d, min_val=0, min_price=0), "거래대금 10억 이상": universe(d), "시총 상위 500": universe(d, top=500)}
PER = {"dev": ("2013-07-01", "2018-12-31"), "val": ("2019-01-01", "2022-12-31"), "fin": ("2023-01-01", "2026-11-16")}
ycols = [c for c in R.columns if c.startswith("y2")]
COST = rb.BUY_COST + rb.SELL_COST
EW = {}
for un, U in UNI.items():
    ew = d["ret"].where(U.shift(1, fill_value=False)).mean(axis=1).loc["2013-07-01":"2026-11-16"].fillna(0)
    eq = (1 + ew).cumprod(); m = R.종목군 == un
    EW[un] = {"mdd": (eq / eq.cummax() - 1).min(), "y": (1 + ew).groupby(ew.index.year).prod() - 1,
              **{p: (1 + ew.loc[a:b]).prod() ** (252 / len(ew.loc[a:b])) - 1 for p, (a, b) in PER.items()},
              "all": eq.iloc[-1] ** (252 / len(ew)) - 1}
    for p in PER:
        R.loc[m, "ex_" + p] = R.loc[m, p] - R.loc[m, "회전"] * COST - EW[un][p]          # 비용 2배 가정 후 종목군 대비 초과
    R.loc[m, "wins"] = (R.loc[m, ycols].values > EW[un]["y"].reindex([int(c[1:]) for c in ycols]).values).sum(axis=1)
    R.loc[m, "mdd_ok"] = R.loc[m, "MDD"] > EW[un]["mdd"]
    print(un, {k: (round(v, 3) if not isinstance(v, pd.Series) else None) for k, v in EW[un].items() if k != "y"})
R["worst"] = R[["ex_dev", "ex_val", "ex_fin"]].min(axis=1)
R["pass"] = (R.worst > 0) & R.mdd_ok.astype(bool) & (R.wins >= 9)
print({un: f"{int(R[R.종목군 == un]['pass'].sum())}/{int((R.종목군 == un).sum())}" for un in UNI})
W = R.pivot(index="조합", columns="종목군", values="worst"); Pm = R.pivot(index="조합", columns="종목군", values="pass")
allpass = Pm.all(axis=1); score = W.min(axis=1)
print("세 종목군 모두 통과:", int(allpass.sum()), "/", len(W))
best = score[allpass].sort_values(ascending=False)
pd.set_option("display.width", 300); pd.set_option("display.max_colwidth", 90); pd.set_option("display.float_format", "{:.3f}".format)
T = pd.DataFrame({"최저 초과(세 종목군·세 구간)": best.head(15)}).join(W)
print(T.to_string())
top = best.index[0]
print("\n== 1위:", top)
print(R[R.조합 == top][["종목군", "dev", "val", "fin", "ex_dev", "ex_val", "ex_fin", "MDD", "샤프", "회전", "wins"]].to_string(index=False))
c = Counter(n for x in best.head(30).index for n in x.split(" + ")); print("상위 30개 조합의 지표 빈도:", dict(c.most_common()))
ca = "1.200일선 이격(높음) + 5.52주 신고가 근접(높음) + 8.ATR%(낮음=저변동)"
print("기존 조합 A 순위:", (list(best.index).index(ca) + 1) if ca in best.index else "세 종목군 통과 못함", "| worst:", W.loc[ca].round(3).to_dict(), "| 통과:", Pm.loc[ca].to_dict())
# 단일 지표 성적(코스피·코스닥 전체)
s1 = R[(R.개수 == 1) & (R.종목군 == "코스피·코스닥 전체")][["조합", "ex_dev", "ex_val", "ex_fin", "wins", "MDD"]].sort_values("ex_fin", ascending=False)
print(s1.to_string(index=False))
best.head(15).to_csv("reports/full_rank_top15.csv")
