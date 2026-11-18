"""ETF 최근 5년 성과 순위: (1) 1~3개 ETF 동일비중 보유 조합 전수, (2) 규칙 기반 전략(모멘텀 상위 N, 추세 바스켓).
그리고 '직전 5년에 1등이던 조합이 다음 5년에 어땠는가'를 함께 계산한다. 사용: python3 etf_best5.py"""
import os, json, itertools
import numpy as np, pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
NM = {k: v["naver_name"] for k, v in json.load(open(os.path.join(BASE, "data_etf", "_names.json"), encoding="utf-8")).items()}
px = {f[:6]: pd.read_csv(os.path.join(BASE, "data_etf", f), parse_dates=["date"]).set_index("date").close for f in os.listdir(os.path.join(BASE, "data_etf")) if f.endswith(".csv")}
C = pd.DataFrame(px).sort_index(); C = C.loc[:C["069500"].dropna().index[-1]]
if pd.Timestamp.today().normalize() == C.index[-1]: C = C.iloc[:-1]          # 장중 미확정 봉 제외
C = C.where(C.ffill().notna()).ffill(); RET = C.pct_change()
END = C.index[-1]; W2 = (END - pd.DateOffset(years=5), END); W1 = (END - pd.DateOffset(years=10), END - pd.DateOffset(years=5))
CASH, COST = "153130", 0.00115


def stats(r):
    r = r.dropna(); eq = (1 + r).cumprod(); yrs = len(r) / 252
    return eq.iloc[-1] ** (1 / yrs) - 1, (eq / eq.cummax() - 1).min(), r.mean() / r.std() * np.sqrt(252)


def static_table(a, b, kmax=3):
    R = RET.loc[a:b].iloc[1:]
    ok = [c for c in R.columns if C[c].loc[:a].notna().any() and R[c].notna().all()]     # 구간 시작 전에 상장된 ETF만
    out = []
    for k in range(1, kmax + 1):
        for cs in itertools.combinations(ok, k):
            r = R[list(cs)].mean(axis=1)                                                  # 동일비중(매일 재조정 근사)
            cg, md, sh = stats(r); out.append({"조합": " + ".join(NM[c] for c in cs), "codes": cs, "개수": k, "연수익률": cg, "MDD": md, "샤프": sh})
    return pd.DataFrame(out), ok


ELIG = C.notna().cumsum() >= 252
MOM = {"3개월": C / C.shift(63) - 1, "6개월": C / C.shift(126) - 1, "12개월": C / C.shift(252) - 1,
       "1·3·6·12개월 평균": sum(C / C.shift(n) - 1 for n in (21, 63, 126, 252)) / 4}
SMA = {n: C.rolling(n).mean() for n in (120, 200)}
SETS = {"핵심 6": ["069500", "229200", "133690", "143850", "132030", "148070"],
        "확장 14": ["069500", "229200", "133690", "143850", "132030", "148070", "251350", "195930", "241180", "192090", "195980", "182480", "130680", "305080"],
        "전체 23": [c for c in C.columns if c != CASH]}


def sim(tfn, a, b, every=21, tranches=3):
    cols = list(C.columns); pos = {k: j for j, k in enumerate(cols)}; R = RET.fillna(0).values
    idx = [i for i, t in enumerate(C.index) if a <= t <= b]; outs = []
    for tr in range(tranches):
        off = int(tr * every / tranches); w = np.zeros(len(cols)); pend = None; o = np.zeros(len(idx))
        for n, i in enumerate(idx):
            r = float(w @ R[i]); w = w * (1 + R[i]) / (1 + r) if w.sum() > 0 else w; cost = 0.0
            if pend is not None:
                cost = np.abs(pend - w).sum() * COST; w = pend; pend = None
            o[n] = r - cost
            if n % every == off:
                tw = np.zeros(len(cols))
                for k, v in tfn(i).items(): tw[pos[k]] += v
                pend = tw
        outs.append(o)
    return pd.Series(np.mean(outs, axis=0), index=C.index[idx])


def t_mom(i, A, S, n, absf):
    s = S.iloc[i]; el = [a for a in A if ELIG[a].iloc[i] and np.isfinite(s[a])]; w = {}
    top = sorted(el, key=lambda a: -s[a])[:n]
    for a in top:
        dst = a if (not absf or s[a] > 0) else CASH; w[dst] = w.get(dst, 0) + 1 / n
    if len(top) < n: w[CASH] = w.get(CASH, 0) + (n - len(top)) / n
    return w


def t_trend(i, A, S):
    el = [a for a in A if ELIG[a].iloc[i] and np.isfinite(S[a].iloc[i])]; w = {}
    for a in el:
        dst = a if C[a].iloc[i] > S[a].iloc[i] else CASH; w[dst] = w.get(dst, 0) + 1 / len(el)
    return w or {CASH: 1.0}


def rule_table(a, b):
    out = []
    for sn, A in SETS.items():
        for mn, n, f in itertools.product(MOM, (1, 2, 3), (False, True)):
            r = sim(lambda i: t_mom(i, A, MOM[mn], n, f), a, b); cg, md, sh = stats(r)
            out.append({"전략": f"[{sn}] 모멘텀 {mn} 상위{n}" + (" +절대필터" if f else ""), "연수익률": cg, "MDD": md, "샤프": sh})
        for m in SMA:
            r = sim(lambda i: t_trend(i, A, SMA[m]), a, b); cg, md, sh = stats(r)
            out.append({"전략": f"[{sn}] 추세 바스켓 {m}일선", "연수익률": cg, "MDD": md, "샤프": sh})
    return pd.DataFrame(out)


if __name__ == "__main__":
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 90); pd.set_option("display.float_format", "{:.3f}".format)
    print(f"최근 5년: {W2[0].date()} ~ {W2[1].date()} / 직전 5년: {W1[0].date()} ~ {W1[1].date()}")
    for k in ("KOSPI", "KOSPI200", "KOSDAQ"):
        s = pd.read_csv(os.path.join(BASE, "data_index", k + ".csv"), parse_dates=["date"]).set_index("date").close.loc[:END].pct_change()
        print(f"  {k}: 최근 5년 {tuple(round(x,3) for x in stats(s.loc[W2[0]:W2[1]]))}, 직전 5년 {tuple(round(x,3) for x in stats(s.loc[W1[0]:W1[1]]))}")
    S2, ok2 = static_table(*W2); S1, ok1 = static_table(*W1)
    print(f"\n[1] ETF 보유 조합 — 최근 5년 (대상 {len(ok2)}개 ETF, 조합 {len(S2)}개)")
    print("단일 ETF:"); print(S2[S2.개수 == 1].sort_values("연수익률", ascending=False).drop(columns=["codes", "개수"]).to_string(index=False))
    print("수익률 상위 10:"); print(S2.sort_values("연수익률", ascending=False).head(10).drop(columns="codes").to_string(index=False))
    print("샤프 상위 10:"); print(S2.sort_values("샤프", ascending=False).head(10).drop(columns="codes").to_string(index=False))
    T2 = rule_table(*W2); T1 = rule_table(*W1)
    print(f"\n[2] 규칙 기반 전략 — 최근 5년 ({len(T2)}개)"); print(T2.sort_values("연수익률", ascending=False).head(10).to_string(index=False))
    print("샤프 상위 5:"); print(T2.sort_values("샤프", ascending=False).head(5).to_string(index=False))
    # 직전 5년의 1등이 최근 5년에 어땠나
    print("\n[3] 직전 5년 1등 → 최근 5년 성적")
    S2i = S2.set_index("조합"); n2 = len(S2)
    for key in ("연수익률", "샤프"):
        top = S1.sort_values(key, ascending=False).head(5)
        for _, r in top.iterrows():
            if r["조합"] in S2i.index:
                x = S2i.loc[r["조합"]]; rank = int((S2[key] > x[key]).sum()) + 1
                print(f"  보유조합({key} 기준) {r['조합']}: 직전 {r[key]:.3f} → 최근 {x[key]:.3f} (최근 순위 {rank}/{n2})")
    m = T1.merge(T2, on="전략", suffixes=("_직전", "_최근"))
    for key in ("연수익률", "샤프"):
        for _, r in m.sort_values(key + "_직전", ascending=False).head(3).iterrows():
            print(f"  규칙전략({key} 기준) {r['전략']}: 직전 {r[key+'_직전']:.3f} → 최근 {r[key+'_최근']:.3f} (최근 순위 {int((m[key+'_최근'] > r[key+'_최근']).sum())+1}/{len(m)})")
    common = S1.merge(S2, on="조합", suffixes=("_1", "_2"))
    print("  보유조합 순위상관(직전↔최근): 연수익률 %.2f, 샤프 %.2f (공통 %d개) | 규칙전략: 연수익률 %.2f, 샤프 %.2f" % (
        common["연수익률_1"].corr(common["연수익률_2"], method="spearman"), common["샤프_1"].corr(common["샤프_2"], method="spearman"), len(common),
        m["연수익률_직전"].corr(m["연수익률_최근"], method="spearman"), m["샤프_직전"].corr(m["샤프_최근"], method="spearman")))
    S2.drop(columns="codes").to_csv("reports/etf_static_5y_2026-11-18.csv", index=False); T2.to_csv("reports/etf_rules_5y_2026-11-18.csv", index=False)
