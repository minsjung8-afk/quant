"""후보 전략의 구간별 상세(연도별 수익, 벤치마크 대비). 사용: python3 etf_detail.py dev|val|fin"""
import sys
import numpy as np, pandas as pd
import etf_research as E

p = sys.argv[1]; a, b = E.PERIODS[p]
A = E.SETS["핵심 6"]
CANDS = {
    "A. 1·3·6·12개월 평균 상위3": lambda i: E.target_f1(i, A, E.MOM["1·3·6·12개월 평균"], 3, False),
    "B. 12개월 상위3": lambda i: E.target_f1(i, A, E.MOM["12개월"], 3, False),
    "C. 12개월 상위3 +절대필터": lambda i: E.target_f1(i, A, E.MOM["12개월"], 3, True),
}
B = E.benchmarks(a, b); B = {k: v for k, v in B.items() if not k.startswith("확장")}
B["나스닥100 ETF 보유(참고)"] = E.RET["133690"].loc[a:b]
yr = lambda r: (1 + r).groupby(r.index.year).prod() - 1
R = {}; rows = []
for nm, fn in CANDS.items():
    r, to = E.sim(fn, a, b); r2, _ = E.sim(fn, a, b, cost_mult=2); r21, _ = E.sim(fn, a, b, tranches=21)
    R[nm] = r; s = E.stats(r)
    rows.append({"전략": nm, "연수익률": s["CAGR"], "MDD": s["MDD"], "샤프": s["샤프"], "비용2배": E.stats(r2)["CAGR"], "21묶음": E.stats(r21)["CAGR"], "연회전": to})
for nm, r in B.items():
    s = E.stats(r); rows.append({"전략": nm, "연수익률": s["CAGR"], "MDD": s["MDD"], "샤프": s["샤프"]})
pd.set_option("display.width", 220); pd.set_option("display.float_format", "{:.3f}".format)
print(f"=== {p}: {a} ~ {b} ==="); print(pd.DataFrame(rows).to_string(index=False))
Y = pd.DataFrame({**{k: yr(v) for k, v in R.items()}, **{k: yr(v) for k, v in B.items()}})
print((Y * 100).round(1).T.to_string())
ky, ew = Y["KOSPI"], Y["핵심 6 동일비중 보유"]
bar = max(E.stats(v)["CAGR"] for k, v in B.items() if "참고" not in k); lim = 1.2 * E.stats(B["KOSPI"])["MDD"]
for thr in (0.30, 0.20):
    surge = [t for t in ky.index if ky[t] >= thr]
    print(f"-- 급등 연도 기준 +{int(thr*100)}%: {surge}")
    for nm in CANDS:
        y = Y[nm]; s = E.stats(R[nm])
        wins = sum((y[t] >= 0.7 * ky[t]) if t in surge else (y[t] > ky[t]) for t in y.index)
        ew_ok = all(y[t] > ew[t] for t in surge)
        normal = [t for t in y.index if t not in surge]
        cum = np.prod([1 + y[t] for t in normal]) > np.prod([1 + ky[t] for t in normal])
        row = next(r for r in rows if r["전략"] == nm)
        print(f"   {nm}: 코스피 대비 {wins}/{len(y)}년, 급등연도 동일비중 초과 {'O' if ew_ok else 'X'}, 일반연도 누적 코스피 초과 {'O' if cum else 'X'}, "
              f"연수익률>{bar*100:.1f}% {'O' if s['CAGR']>bar else 'X'}, MDD≥{lim*100:.1f}% {'O' if s['MDD']>=lim else 'X'}, 비용2배 {'O' if row['비용2배']>bar else 'X'}")
