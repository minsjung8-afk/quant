"""지표별 단독 검증: 종목군 안에서 지표 순위 상위 20% vs 전체/하위 20%의 이후 수익률.
사용: python3 research_indicators.py 2013-07-01 2018-12-31   (개발 구간만 본다)"""
import sys
import numpy as np, pandas as pd
from panel import load, universe, indicators

A, B = sys.argv[1], sys.argv[2]
d = load(); U = universe(d); ind = indicators(d); I = d["I"]
dates = I.index
rows = []
for h in (5, 21):
    fwd = (I.shift(-(h + 1)) / I.shift(-1) - 1).values      # 다음 날 종가 매수 → h거래일 보유
    pos = [i for i in range(len(dates)) if A <= str(dates[i].date()) <= B][::h]
    for nm, S in ind.items():
        s = S.values
        top_ex, spread, n = [], [], []
        for i in pos:
            m = U.values[i] & np.isfinite(s[i]) & np.isfinite(fwd[i])
            if m.sum() < 100: continue
            x, y = s[i][m], fwd[i][m]
            q = np.quantile(x, [0.2, 0.8])
            t, b = y[x >= q[1]].mean(), y[x <= q[0]].mean()
            top_ex.append(t - y.mean()); spread.append(t - b); n.append(m.sum())
        te, sp = np.array(top_ex), np.array(spread)
        ann = 252 / h
        rows.append({"지표": nm, "보유일": h, "표본": len(te), "평균 종목수": int(np.mean(n)),
                     "상위20% 초과수익(연)": te.mean() * ann, "t": te.mean() / te.std(ddof=1) * np.sqrt(len(te)),
                     "승률": (te > 0).mean(), "상위-하위(연)": sp.mean() * ann,
                     "t(상-하)": sp.mean() / sp.std(ddof=1) * np.sqrt(len(sp))})
out = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.float_format", "{:.3f}".format)
for h in (5, 21):
    print(f"\n=== 보유 {h}거래일 ({A} ~ {B}) ===")
    print(out[out.보유일 == h].drop(columns="보유일").sort_values("t", ascending=False).to_string(index=False))
out.to_csv(f"results_indicators_{A[:4]}_{B[:4]}.csv", index=False)
