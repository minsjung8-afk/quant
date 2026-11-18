"""기술적 지표 13개 + 재무 지표 9개를 모두 넣어 종목 선별 효과를 본다 (코스피·코스닥 전체, 심사참고 DB 사이트의 재무 사용).
재무는 2024~2026년분뿐이라 2025-04 이후 약 18개월만 시험 가능. 공시 접수일(분기 손익은 분기말+50일, 4분기는 +95일) 이후에만 사용.
사용: python3 research_all.py"""
import json, gzip, itertools
import numpy as np, pandas as pd
from panel import load, universe, indicators

d = load(); IND = indicators(d); I = d["I"]; dates = I.index
FIN = json.load(gzip.open("data_fin/fin.json.gz", "rt", encoding="utf-8"))["companies"]
FIN = {k: v for k, v in FIN.items() if not v.get("cur") and k in I.columns and v["kpi"]}
START = "2025-04-01"
pos = [i for i in range(len(dates)) if str(dates[i].date()) >= START][::21]
pos = [i for i in pos if i + 22 < len(dates)]
fwd = I.shift(-22) / I.shift(-1) - 1


def qend(label):
    yy, q = int(label[:2]) + 2000, int(label[3])
    return pd.Timestamp(yy, q * 3, 1) + pd.offsets.MonthEnd(0)


# 회사별 시점 자료 준비
REC = {}
for code, v in FIN.items():
    rows = v["kpi"].get("CFS") or v["kpi"].get("OFS") or []
    rr = []
    for r in rows:
        rc = str(r.get("rcept_no") or "")[:8]
        if len(rc) == 8 and rc.isdigit():
            rr.append((pd.Timestamp(rc), r))
    qs = (v.get("quarters") or {}); qs = qs.get("CFS") or qs.get("OFS") or []
    qq = [(qend(x["label"]) + pd.Timedelta(days=95 if x["label"].endswith("4Q") else 50), x) for x in qs if x.get("ltm_op") is not None]
    REC[code] = (sorted(rr, key=lambda t: t[0]), sorted(qq, key=lambda t: t[0]))


def fundamentals(t, codes, mcap):
    out = {}
    for c in codes:
        rr, qq = REC[c]
        ann = [r for a, r in rr if a < t and r["kind"] == "annual"]
        bs = [r for a, r in rr if a < t]
        ql = [x for a, x in qq if a < t]
        if not ann or not bs: continue
        A, B, m = ann[-1], bs[-1], mcap[c]
        if not (m and m > 0): continue
        g = lambda r, k: (r.get(k) if r.get(k) is not None else np.nan)
        ltm_op = ql[-1]["ltm_op"] if ql else np.nan
        ltm_eb = (ql[-1].get("ltm_ebitda") if ql and ql[-1].get("ltm_ebitda") is not None else g(A, "ebitda"))
        nd = (ql[-1].get("nd") if ql and ql[-1].get("nd") is not None else g(B, "borrowings") - g(B, "cash"))
        ev = m + (nd if np.isfinite(nd) else 0)
        eq = g(B, "equity")
        out[c] = {"F1.이익수익률(PER 낮음)": g(A, "net_income") / m, "F2.자본/시총(PBR 낮음)": eq / m, "F3.매출/시총(PSR 낮음)": g(A, "revenue") / m,
                  "F4.영업이익/시총(연간)": g(A, "op_income") / m, "F5.영업이익/시총(최근 4분기)": ltm_op / m,
                  "F6.EBITDA/EV(EV/EBITDA 낮음)": (ltm_eb / ev) if ev > 0 else np.nan,
                  "F7.ROE(높음)": (g(A, "net_income") / eq) if eq and eq > 0 else np.nan,
                  "F8.영업이익률(높음)": (g(A, "op_income") / g(A, "revenue")) if g(A, "revenue") and g(A, "revenue") > 0 else np.nan,
                  "F9.부채비율(낮음)": -(g(B, "total_liab") / eq) if eq and eq > 0 else np.nan}
    return pd.DataFrame(out).T


UNIS = {"코스피·코스닥 전체": universe(d, min_val=0, min_price=0), "거래대금 10억 이상": universe(d)}
RES = {}
for un, U in UNIS.items():
    panels = []
    for i in pos:
        t = dates[i]
        codes = [c for c in FIN if U[c].iloc[i]]
        f = fundamentals(t, codes, d["mcap"].iloc[i])
        u = list(f.index)
        tech = pd.DataFrame({"T" + n: IND[n].iloc[i].reindex(u) for n in IND})
        X = pd.concat([tech, f], axis=1).rank(pct=True)
        panels.append((t, X, fwd.iloc[i].reindex(u)))
    names = list(panels[0][1].columns)
    rows = []
    for n in (1, 2, 3):
        for combo in itertools.combinations(names, n):
            ex, bot = [], []
            for t, X, y in panels:
                s = X[list(combo)].mean(axis=1, skipna=False)
                m = s.notna() & y.notna()
                if m.sum() < 100: continue
                sv, yv = s[m].values, y[m].values
                hi, lo = np.quantile(sv, 0.8), np.quantile(sv, 0.2)
                ex.append(yv[sv >= hi].mean() - yv.mean()); bot.append(yv[sv <= lo].mean() - yv.mean())
            if len(ex) < 12: continue
            e = np.array(ex); h = len(e) // 2
            rows.append({"조합": " + ".join(combo), "개수": n, "월수": len(e), "상위초과(월%)": e.mean() * 100, "t": e.mean() / e.std(ddof=1) * np.sqrt(len(e)),
                         "이긴 달": int((e > 0).sum()), "전반(월%)": e[:h].mean() * 100, "후반(월%)": e[h:].mean() * 100, "하위초과(월%)": np.mean(bot) * 100})
    R = pd.DataFrame(rows); R["약한 쪽 절반"] = R[["전반(월%)", "후반(월%)"]].min(axis=1)
    R.to_csv(f"reports/all_factors_{'whole' if un.startswith('코스피') else 'liquid'}_2026-11-18.csv", index=False)
    RES[un] = (R, np.mean([len(X) for _, X, _ in panels]), panels)
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 95); pd.set_option("display.float_format", "{:.2f}".format)
    print(f"\n######## {un}: 판정일 {dates[pos[0]].date()} ~ {dates[pos[-1]].date()} ({len(panels)}개월), 평균 {RES[un][1]:.0f}종목, 조합 {len(R)}개")
    print("--- 단일 지표"); print(R[R.개수 == 1].sort_values("상위초과(월%)", ascending=False).drop(columns=["개수", "약한 쪽 절반"]).to_string(index=False))
    print("--- 조합 상위 12 (전·후반 중 약한 쪽 기준)"); print(R.sort_values("약한 쪽 절반", ascending=False).head(12).drop(columns=["개수"]).to_string(index=False))
    print("전·후반 모두 플러스인 조합 비율: %.0f%%" % ((R["약한 쪽 절반"] > 0).mean() * 100), "| 전반↔후반 순위상관 %.2f" % R["전반(월%)"].corr(R["후반(월%)"], method="spearman"))
