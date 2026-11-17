#!/usr/bin/env python3
"""ETF 전략 B의 일일 신호·가상 운용 기록·대시보드 생성. 표준 라이브러리만 사용(GitHub Actions에서 실행).
규칙: 매월 마지막 거래일 종가의 12개월(252거래일) 수익률 상위 3개를 1/3씩 보유, 다음 거래일 종가에 교체.
출력: site/data.json, site/index.html"""
import os, csv, json
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS = ["069500", "229200", "133690", "143850", "132030", "148070"]
LABEL = {"069500": "국내 대형주", "229200": "국내 코스닥", "133690": "미국 나스닥100", "143850": "미국 S&P500(환헤지)",
         "132030": "금(환헤지)", "148070": "국고채 10년"}
TOPN, LOOK = 3, 252
COST = 0.00015 + 0.0010
OBS_START = "2026-11-17"          # 관찰 시작(이 날 종가 = 1.0)
BT_START = "2012-07-02"


def read(path):
    with open(path, newline="") as f:
        return {r["date"]: float(r["close"]) for r in csv.DictReader(f) if float(r["close"]) > 0}


def main():
    px = {a: read(os.path.join(BASE, "data_etf", a + ".csv")) for a in ASSETS}
    idx = {k: read(os.path.join(BASE, "data_index", k + ".csv")) for k in ("KOSPI", "KOSPI200")}
    names = json.load(open(os.path.join(BASE, "data_etf", "_names.json"), encoding="utf-8"))
    today = date.today().isoformat()
    # 장중 미확정 봉 제외: 오늘 날짜 행은 쓰지 않는다(워크플로는 다음 날 아침에 실행됨)
    dates = sorted(d for d in px["069500"] if d < today or os.environ.get("ALLOW_TODAY") == "1")
    close = {a: [] for a in ASSETS}
    for a in ASSETS:
        last = None
        for d in dates:
            last = px[a].get(d, last)
            close[a].append(last)
    n = len(dates)

    def mom(a, i):
        c, p = close[a][i], close[a][i - LOOK] if i >= LOOK else None
        return (c / p - 1) if (c and p) else None

    def pick(i):
        s = [(mom(a, i), a) for a in ASSETS if mom(a, i) is not None]
        return [a for _, a in sorted(s, reverse=True)[:TOPN]]

    month_end = [i for i in range(n - 1) if dates[i][:7] != dates[i + 1][:7]]      # 월 마지막 거래일(다음 달 첫 거래일이 존재하는 경우만)
    # 운용 시뮬레이션 (월말 판정 → 다음 거래일 종가 체결)
    start_i = next(i for i, d in enumerate(dates) if d >= BT_START)
    w = {}; pending = None; nav = 1.0; navs = [None] * n; hold_hist = []
    ew_nav = 1.0; ew = [None] * n
    for i in range(start_i, n):
        if i > start_i:
            r = sum(wt * (close[a][i] / close[a][i - 1] - 1) for a, wt in w.items() if close[a][i - 1])
            tot = 1 + r
            w = {a: wt * (close[a][i] / close[a][i - 1]) / tot for a, wt in w.items()}
            nav *= tot
            el = [a for a in ASSETS if close[a][i - 1] and i - 1 >= LOOK and close[a][i - 1 - LOOK]]
            if el:
                ew_nav *= 1 + sum(close[a][i] / close[a][i - 1] - 1 for a in el) / len(el)
        if pending is not None:
            tgt = {a: 1.0 / len(pending) for a in pending} if pending else {}
            turn = sum(abs(tgt.get(a, 0) - w.get(a, 0)) for a in set(tgt) | set(w))
            nav *= 1 - turn * COST
            old = set(w); w = tgt
            hold_hist.append({"signal_date": dates[i - 1], "trade_date": dates[i], "hold": pending,
                              "buy": sorted(set(pending) - old), "sell": sorted(old - set(pending))})
            pending = None
        navs[i] = nav; ew[i] = ew_nav
        if i in month_end and pick(i):
            pending = pick(i)
        if i == start_i and not w:
            first = pick(i)
            if first:
                pending = first
    last = n - 1
    cur_hold = hold_hist[-1]["hold"] if hold_hist else []
    rank_now = pick(last)
    table = []
    order = sorted(ASSETS, key=lambda a: -(mom(a, last) if mom(a, last) is not None else -9))
    for r, a in enumerate(order, 1):
        table.append({"code": a, "name": names[a]["naver_name"], "label": LABEL[a], "close": close[a][last], "mom12": mom(a, last),
                      "rank": r, "held": a in cur_hold, "would_hold": a in rank_now})

    def series(vals, i0):
        base = vals[i0]
        return [round(v / base, 4) for v in vals[i0:]]

    def idx_series(k, i0):
        out, lastv = [], None
        for d in dates[i0:]:
            lastv = idx[k].get(d, lastv); out.append(lastv)
        base = next(v for v in out if v)
        return [round((v or base) / base, 4) for v in out]

    def mdd(s):
        peak, m = s[0], 0.0
        for v in s:
            peak = max(peak, v); m = min(m, v / peak - 1)
        return m

    def block(i0):
        s = {"전략 B": series(navs, i0), "6개 자산 동일비중": series(ew, i0), "코스피": idx_series("KOSPI", i0), "코스피200": idx_series("KOSPI200", i0)}
        yrs = max((len(dates) - 1 - i0) / 252, 1e-9)
        st = {k: {"ret": v[-1] - 1, "cagr": (v[-1] ** (1 / yrs) - 1) if yrs >= 1 else None, "mdd": mdd(v)} for k, v in s.items()}
        return s, st

    obs_i = next((i for i, d in enumerate(dates) if d >= OBS_START), last)
    obs_s, obs_st = block(obs_i)
    i3 = max(start_i, last - 252 * 3)
    s3, st3 = block(i3)
    sall, stall = block(start_i)
    step = 5
    data = {
        "asof": dates[last], "built": today, "obs_start": dates[obs_i],
        "hold": [{"code": a, "name": names[a]["naver_name"], "label": LABEL[a]} for a in cur_hold],
        "last_signal": hold_hist[-1] if hold_hist else None,
        "next_signal_month": dates[last][:7],
        "pending_change": {"buy": sorted(set(rank_now) - set(cur_hold)), "sell": sorted(set(cur_hold) - set(rank_now))},
        "table": table,
        "history": hold_hist[-12:][::-1],
        "names": {a: names[a]["naver_name"] for a in ASSETS},
        "obs": {"dates": dates[obs_i:], "series": obs_s, "stats": obs_st},
        "y3": {"dates": dates[i3:][::step], "series": {k: v[::step] for k, v in s3.items()}, "stats": st3},
        "all": {"stats": stall, "from": dates[start_i]},
    }
    os.makedirs(os.path.join(BASE, "site"), exist_ok=True)
    with open(os.path.join(BASE, "site", "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    tpl = open(os.path.join(BASE, "site_template.html"), encoding="utf-8").read()
    with open(os.path.join(BASE, "site", "index.html"), "w", encoding="utf-8") as f:
        f.write(tpl.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False)))
    print(f"기준일 {dates[last]} | 보유 {[names[a]['naver_name'] for a in cur_hold]} | 월말 교체 예고 {data['pending_change']}")
    print("전체 기간:", {k: (round(v['cagr'] * 100, 1), round(v['mdd'] * 100, 1)) for k, v in stall.items()})


if __name__ == "__main__":
    main()
