"""국내 데이터 백테스트: python3 run_kr.py [개발구간 종료일=2021-12-31] [기준일(이 날짜까지만 사용)]
전략별·구간별 성과 + 동일비중 단순보유(벤치마크) 비교. 결과는 results/ 에 저장."""
import sys, glob, os
from multiprocessing import Pool
import numpy as np, pandas as pd
from indicators import add_indicators
from strategies import DEFAULTS
from backtest import run, metrics, Costs

BASE = os.path.dirname(os.path.abspath(__file__))
SPLIT = sys.argv[1] if len(sys.argv) > 1 else "2021-12-31"
ASOF = sys.argv[2] if len(sys.argv) > 2 else None


def work(f):
    tk = os.path.basename(f)[:-4]
    d = pd.read_csv(f, parse_dates=["date"]).set_index("date").sort_index()
    if ASOF: d = d.loc[:ASOF]
    if len(d) < 300: return None
    d = add_indicators(d)
    out = {"_bh": d.close.pct_change().fillna(0).rename(tk)}
    for k, st in enumerate(DEFAULTS):
        tr, eq = run(d, st)
        out[k] = (tr.assign(ticker=tk), eq.pct_change().fillna(eq.iloc[0] - 1).rename(tk))
    return out


def stats(tr, rets, a, b):
    r = rets.loc[a:b]
    port = (1 + r.mean(axis=1)).cumprod()          # 상장된 종목 동일비중, 미보유분은 현금
    t = tr[(tr.entry_date >= r.index[0]) & (tr.entry_date <= r.index[-1])]
    m = metrics(t, port)
    held = (r.fillna(0) != 0)
    m["노출도"] = float(held.sum().sum() / r.notna().sum().sum())
    m["보유중연수익"] = float(r.fillna(0).sum().sum() / held.sum().sum() * 252)   # 보유일 기준 연환산(단리)
    return m


if __name__ == "__main__":
    files = sorted(glob.glob(os.path.join(BASE, "data_kr", "*.csv")))
    with Pool() as p:
        res = [x for x in p.map(work, files, chunksize=8) if x]
    print(f"종목 {len(res)}개, 개발 ~{SPLIT} / 검증 이후")
    os.makedirs(os.path.join(BASE, "results"), exist_ok=True)
    rows = []
    bh = pd.concat([x["_bh"] for x in res], axis=1)
    for nm, a, b in [("개발", None, SPLIT), ("검증", pd.Timestamp(SPLIT) + pd.Timedelta(days=1), None)]:
        r = bh.loc[a:b]; port = (1 + r.mean(axis=1)).cumprod()
        rows.append(dict(전략="단순보유(동일비중)", 구간=nm, **metrics(pd.DataFrame(), port), 노출도=1.0, 보유중연수익=float(r.stack().mean() * 252)))
    for k, st in enumerate(DEFAULTS):
        tr = pd.concat([x[k][0] for x in res if len(x[k][0])])
        rets = pd.concat([x[k][1] for x in res], axis=1)
        tr.to_csv(os.path.join(BASE, "results", f"trades_{k}.csv"), index=False)
        for nm, a, b in [("개발", None, SPLIT), ("검증", pd.Timestamp(SPLIT) + pd.Timedelta(days=1), None)]:
            rows.append(dict(전략=st.name, 구간=nm, **stats(tr, rets, a, b)))
        yr = tr.assign(y=tr.entry_date.dt.year).groupby("y").ret.agg(["count", "mean"])
        yr.to_csv(os.path.join(BASE, "results", f"yearly_{k}.csv"))
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(BASE, "results", "summary.csv"), index=False)
    pd.set_option("display.width", 250); pd.set_option("display.float_format", "{:.3f}".format)
    print(out.to_string(index=False))
