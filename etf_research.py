"""국내 상장 ETF 자산배분 전략 검증. 신호는 종가 판정 → 다음 거래일 종가 체결, 월 1회(21거래일) 교체, 3묶음 분산.
전략군: F1 상대 모멘텀 상위 N (+절대 모멘텀 필터), F2 추세 바스켓(이동평균 위 자산만 보유)
사용: python3 etf_research.py"""
import os, itertools
import numpy as np, pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
END = "2026-11-16"
COST = 0.00015 + 0.0010          # 편도: 수수료 + 호가 스프레드·슬리피지 (ETF는 거래세 없음)
CASH = "153130"
SETS = {
    "핵심 6": ["069500", "229200", "133690", "143850", "132030", "148070"],
    "확장 14": ["069500", "229200", "133690", "143850", "132030", "148070", "251350", "195930", "241180", "192090",
              "195980", "182480", "130680", "305080"],
}
PERIODS = {"dev": ("2012-07-02", "2018-12-31"), "val": ("2019-01-01", "2022-12-31"), "fin": ("2023-01-01", END)}


def load():
    px = {}
    for f in sorted(os.listdir(os.path.join(BASE, "data_etf"))):
        if f.endswith(".csv"):
            px[f[:6]] = pd.read_csv(os.path.join(BASE, "data_etf", f), parse_dates=["date"]).set_index("date").close
    c = pd.DataFrame(px).sort_index().loc[:END]
    c = c.where(c.ffill().notna()).ffill()                 # 상장 이후 결측(거래 없음)은 직전가
    return c


C = load()
RET = C.pct_change().fillna(0.0)
ELIG = C.notna().cumsum() >= 252                           # 상장 후 1년 경과
MOM = {"12개월": C / C.shift(252) - 1, "6개월": C / C.shift(126) - 1,
       "1·3·6·12개월 평균": sum(C / C.shift(n) - 1 for n in (21, 63, 126, 252)) / 4}
SMA = {n: C.rolling(n).mean() for n in (120, 200)}


def target_f1(i, assets, score, n, absf):
    s = score.iloc[i]
    el = [a for a in assets if ELIG[a].iloc[i] and np.isfinite(s[a])]
    w = {}
    if not el:
        return {CASH: 1.0}
    top = sorted(el, key=lambda a: -s[a])[:n]
    for a in top:
        dest = a if (not absf or s[a] > 0) else CASH
        w[dest] = w.get(dest, 0) + 1.0 / n
    if len(top) < n:
        w[CASH] = w.get(CASH, 0) + (n - len(top)) / n
    return w


def target_f2(i, assets, sma):
    el = [a for a in assets if ELIG[a].iloc[i] and np.isfinite(sma[a].iloc[i])]
    w = {}
    if not el:
        return {CASH: 1.0}
    for a in el:
        dest = a if C[a].iloc[i] > sma[a].iloc[i] else CASH
        w[dest] = w.get(dest, 0) + 1.0 / len(el)
    return w


def target_bh(i, assets):
    el = [a for a in assets if ELIG[a].iloc[i]]
    return {a: 1.0 / len(el) for a in el} if el else {CASH: 1.0}


def sim(tfn, a, b, every=21, tranches=3, cost_mult=1.0):
    cols = list(C.columns); pos = {k: j for j, k in enumerate(cols)}
    R = RET.values; idx = [i for i, dts in enumerate(C.index) if a <= str(dts.date()) <= b]
    outs, turn = [], []
    for t in range(tranches):
        off = int(t * every / tranches)
        w = np.zeros(len(cols)); pending = None; o = np.zeros(len(idx)); tv = 0.0
        for n, i in enumerate(idx):
            r = float(w @ R[i]); w = w * (1 + R[i]) / (1 + r) if w.sum() > 0 else w
            cost = 0.0
            if pending is not None:
                tr = np.abs(pending - w).sum(); cost = tr * COST * cost_mult; tv += tr / 2; w = pending; pending = None
            o[n] = r - cost
            if n % every == off:
                tw = np.zeros(len(cols))
                for k, v in tfn(i).items():
                    tw[pos[k]] = v
                pending = tw
        outs.append(o); turn.append(tv)
    return pd.Series(np.mean(outs, axis=0), index=C.index[idx]), float(np.mean(turn)) / (len(idx) / 252)


def stats(r):
    eq = (1 + r).cumprod(); yrs = len(r) / 252
    return {"CAGR": eq.iloc[-1] ** (1 / yrs) - 1, "MDD": (eq / eq.cummax() - 1).min(), "샤프": r.mean() / r.std() * np.sqrt(252)}


def trials():
    for sn, assets in SETS.items():
        for mn, n, absf in itertools.product(MOM, (1, 2, 3), (False, True)):
            yield (f"상대모멘텀 {mn} 상위{n}" + (" +절대필터" if absf else ""), sn,
                   (lambda i, A=assets, S=MOM[mn], N=n, F=absf: target_f1(i, A, S, N, F)))
        for m in SMA:
            yield (f"추세 바스켓 {m}일선", sn, (lambda i, A=assets, S=SMA[m]: target_f2(i, A, S)))


def benchmarks(a, b):
    out = {}
    for k in ("KOSPI", "KOSDAQ", "KOSPI200"):
        out[k] = pd.read_csv(os.path.join(BASE, "data_index", k + ".csv"), parse_dates=["date"]).set_index("date").close.pct_change().loc[a:b].dropna()
    for sn, assets in SETS.items():
        out[f"{sn} 동일비중 보유"] = sim(lambda i, A=assets: target_bh(i, A), a, b)[0]
    return out


if __name__ == "__main__":
    rows = []
    B = {p: benchmarks(*PERIODS[p]) for p in ("dev", "val")}
    for p in B:
        print(p, {k: f"{stats(v)['CAGR']*100:.1f}% / {stats(v)['MDD']*100:.0f}%" for k, v in B[p].items()})
    for nm, sn, fn in trials():
        row = {"전략": nm, "자산군": sn}
        for p in ("dev", "val"):
            r, to = sim(fn, *PERIODS[p]); r2, _ = sim(fn, *PERIODS[p], cost_mult=2)
            s = stats(r)
            row.update({f"{p}_CAGR": s["CAGR"], f"{p}_MDD": s["MDD"], f"{p}_샤프": s["샤프"], f"{p}_CAGR2": stats(r2)["CAGR"], f"{p}_회전": to})
            bar = max(stats(v)["CAGR"] for k, v in B[p].items() if not k.endswith("보유") or k.startswith(sn))
            row[f"{p}_합격"] = bool(s["CAGR"] > bar and s["MDD"] >= 1.2 * stats(B[p]["KOSPI"])["MDD"] and stats(r2)["CAGR"] > bar)
        rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(BASE, "reports", "etf_search_2026-11-17.csv"), index=False)
    pd.set_option("display.width", 250); pd.set_option("display.float_format", "{:.3f}".format); pd.set_option("display.max_rows", 100)
    print(out.sort_values("dev_샤프", ascending=False).to_string(index=False))
    print("개발 합격", int(out.dev_합격.sum()), "/", len(out), " 개발·검증 모두 합격", int((out.dev_합격 & out.val_합격).sum()),
          " 순위상관(샤프) %.2f" % out["dev_샤프"].corr(out["val_샤프"], method="spearman"))
