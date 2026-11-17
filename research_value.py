"""kosdaq-db 재무(fin_kpi 내보내기)로 가치·우량 지표의 종목 선별 효과를 본다. 공시 접수일 이후에만 수치를 사용.
사용: python3 research_value.py <kpi_export.csv>
한계: 재무가 2024~2026년분뿐이라 2025-04 이후만 시험 가능(표본 약 19개월), 대상은 코스닥 약 690사."""
import sys
import numpy as np, pandas as pd
from panel import load, universe, indicators

K = pd.read_csv(sys.argv[1], dtype={"stock_code": str, "rcept_no": str, "reprt_code": str})
K["avail"] = pd.to_datetime(K.rcept_no.str[:8], errors="coerce")
K = K.dropna(subset=["avail"]).sort_values(["stock_code", "avail", "fs_div"])       # CFS가 OFS보다 앞(연결 우선)
K = K.drop_duplicates(["stock_code", "bsns_year", "reprt_code"], keep="first")
d = load(); U0 = universe(d); IND = indicators(d); I = d["I"]; dates = I.index
codes = [c for c in K.stock_code.unique() if c in I.columns]
ANN = K[K.reprt_code == "11011"]
START, END = "2025-04-01", "2026-11-16"
pos = [i for i in range(len(dates)) if START <= str(dates[i].date()) <= END][::21]
pos = [i for i in pos if i + 22 < len(dates)]
fwd = (I.shift(-22) / I.shift(-1) - 1)
TECH = ["1.200일선 이격(높음)", "5.52주 신고가 근접(높음)", "8.ATR%(낮음=저변동)"]
rows = []; store = {}
for i in pos:
    t = dates[i]
    inc = ANN[ANN.avail < t].groupby("stock_code").last()            # 접수일 기준 최신 연간 손익
    bal = K[K.avail < t].groupby("stock_code").last()                # 최신 보고서의 재무상태
    u = [c for c in codes if U0[c].iloc[i] and c in inc.index and c in bal.index]
    if len(u) < 100: continue
    mc = d["mcap"].iloc[i].reindex(u); inc, bal = inc.reindex(u), bal.reindex(u)
    ev = mc + bal.borrowings.fillna(0) - bal.cash.fillna(0)
    f = pd.DataFrame({
        "이익수익률 (PER 낮음)": inc.net_income / mc, "자본/시총 (PBR 낮음)": bal.equity / mc, "영업이익/시총": inc.op_income / mc,
        "매출/시총 (PSR 낮음)": inc.revenue / mc, "EBITDA/EV (EV/EBITDA 낮음)": (inc.ebitda / ev).where(ev > 0),
        "ROE (높음)": (inc.net_income / bal.equity).where(bal.equity > 0), "영업이익률 (높음)": inc.op_income / inc.revenue.where(inc.revenue > 0),
        "부채비율 (낮음)": -(bal.total_liab / bal.equity).where(bal.equity > 0),
    })
    rk = f.rank(pct=True)
    tech = sum(IND[n].iloc[i].reindex(u).rank(pct=True) for n in TECH) / 3
    rk["[기술] 200일선+52주신고가+저변동성"] = tech.rank(pct=True)
    rk["[가치 종합] PER·PBR·영업이익/시총"] = rk[["이익수익률 (PER 낮음)", "자본/시총 (PBR 낮음)", "영업이익/시총"]].mean(axis=1).rank(pct=True)
    rk["[우량 종합] ROE·영업이익률·부채비율"] = rk[["ROE (높음)", "영업이익률 (높음)", "부채비율 (낮음)"]].mean(axis=1).rank(pct=True)
    rk["[기술+가치]"] = (rk["[기술] 200일선+52주신고가+저변동성"] + rk["[가치 종합] PER·PBR·영업이익/시총"]).rank(pct=True)
    rk["[기술+우량]"] = (rk["[기술] 200일선+52주신고가+저변동성"] + rk["[우량 종합] ROE·영업이익률·부채비율"]).rank(pct=True)
    rk["[기술+가치+우량]"] = (rk["[기술] 200일선+52주신고가+저변동성"] + rk["[가치 종합] PER·PBR·영업이익/시총"] + rk["[우량 종합] ROE·영업이익률·부채비율"]).rank(pct=True)
    y = fwd.iloc[i].reindex(u)
    for col in rk:
        m = rk[col].notna() & y.notna()
        if m.sum() < 60: continue
        x, yy = rk[col][m], y[m]
        rows.append({"지표": col, "date": t, "n": int(m.sum()), "top": yy[x >= 0.8].mean() - yy.mean(), "bot": yy[x <= 0.2].mean() - yy.mean(), "univ": yy.mean()})
R = pd.DataFrame(rows)
g = R.groupby("지표", sort=False)
out = pd.DataFrame({"표본(월)": g.size(), "평균 종목수": g.n.mean().round(0), "상위20% 초과(월%)": g.top.mean() * 100, "t": g.top.mean() / g.top.std(ddof=1) * np.sqrt(g.size()),
                    "이긴 달": g.top.apply(lambda s: f"{int((s > 0).sum())}/{len(s)}"), "하위20% 초과(월%)": g.bot.mean() * 100,
                    "상위-하위(월%)": (g.top.mean() - g.bot.mean()) * 100})
pd.set_option("display.width", 220); pd.set_option("display.float_format", "{:.2f}".format)
print(f"기간 {dates[pos[0]].date()} ~ {dates[pos[-1]].date()} (판정일 기준), 종목군 월평균 수익 {R.groupby('date').univ.first().mean()*100:.2f}%")
print(out.to_string())
out.to_csv("reports/value_test_2026-11-17.csv")
