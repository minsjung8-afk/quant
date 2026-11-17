"""검증을 거친 구성요소들을 고정 비중으로 섞었을 때의 성과(전 구간 공개 이후의 분석 — 표본 내 결과임).
구성요소: S=개별 종목 조합 A(200일선 이격+52주 신고가+저변동성, 상위 40), K=KODEX 200 보유, B=ETF 전략 B, E=핵심 6 ETF 동일비중"""
import itertools
import numpy as np, pandas as pd
from panel import load, universe, indicators
import rank_backtest as rb
import etf_research as E

A0, B0 = "2013-07-01", "2026-11-16"
PER = {"개발": ("2013-07-01", "2018-12-31"), "검증": ("2019-01-01", "2022-12-31"), "최종": ("2023-01-01", B0), "전체": (A0, B0)}
d = load(); IND = indicators(d); U = universe(d)
parts = ["1.200일선 이격(높음)", "5.52주 신고가 근접(높음)", "8.ATR%(낮음=저변동)"]
S = sum(IND[p].where(U).rank(axis=1, pct=True) for p in parts) / 3
comp = {}
comp["S 종목선별"], _ = rb.run(d, U, S, A0, B0, k=40, every=21, buffer=20, tranches=3)
comp["K 코스피200 ETF"] = E.RET["069500"].loc[A0:B0]
comp["B ETF전략"], _ = E.sim(lambda i: E.target_f1(i, E.SETS["핵심 6"], E.MOM["12개월"], 3, False), A0, B0)
comp["E ETF 6종 분산"], _ = E.sim(lambda i: E.target_bh(i, E.SETS["핵심 6"]), A0, B0)
C = pd.DataFrame(comp).dropna()
kospi = pd.read_csv("data_index/KOSPI.csv", parse_dates=["date"]).set_index("date").close.pct_change().reindex(C.index).fillna(0)
cum = lambda r: (1 + r).prod() - 1
yr = lambda r: (1 + r).groupby(r.index.year).prod() - 1


def row(name, r):
    out = {"구성": name}
    ok = True
    for p, (a, b) in PER.items():
        x, k = r.loc[a:b], kospi.loc[a:b]; s, ks = rb.stats(x), rb.stats(k)
        m_ok, c_ok = s["MDD"] >= 0.8 * ks["MDD"], cum(x) >= 0.8 * cum(k)
        out[f"{p} 연수익"] = s["CAGR"]; out[f"{p} MDD"] = s["MDD"]
        out[f"{p} 판정"] = ("O" if m_ok else "X") + ("O" if c_ok else "X")
        if p != "전체": ok &= m_ok and c_ok
    out["샤프(전체)"] = rb.stats(r)["샤프"]; out["최저 구간 샤프"] = min(rb.stats(r.loc[a:b])["샤프"] for p, (a, b) in PER.items() if p != "전체")
    y, ky = yr(r), yr(kospi); out["코스피 대비 승"] = f"{int((y > ky).sum())}/{len(y)}"; out["3구간 모두 통과"] = "예" if ok else "-"
    return out


if __name__ == "__main__":
    names = list(C.columns); rows = [row("코스피(지수)", kospi)]
    for n in (1, 2, 3):
        for cset in itertools.combinations(names, n):
            if "B ETF전략" in cset and "E ETF 6종 분산" in cset: continue      # 같은 자산군 중복
            rows.append(row(" + ".join(x.split()[0] for x in cset) if n > 1 else cset[0], C[list(cset)].mean(axis=1)))
    T = pd.DataFrame(rows)
    pd.set_option("display.width", 300); pd.set_option("display.float_format", "{:.3f}".format)
    print(T.to_string(index=False))
    print("\n일간 수익률 상관:"); print(C.assign(코스피=kospi).corr().round(2).to_string())
    ex = C.sub(kospi, axis=0); print("\n코스피 대비 초과수익(연도별, %p):"); print(((pd.DataFrame({k: yr(C[k]) for k in C}).sub(yr(kospi), axis=0)) * 100).round(1).T.to_string())
    T.to_csv("reports/combine_2026-11-17.csv", index=False)
