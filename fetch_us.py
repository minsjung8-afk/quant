#!/usr/bin/env python3
"""미국 ETF·지수 일봉 수집 (무료 경로: 야후 차트 API → 실패 시 Stooq). 추가 설치 없음.
결과: data_us/<티커>.csv (date,open,high,low,close,adjclose,volume)
 - open~close: 분할 반영 가격, adjclose: 분할+배당 반영 종가(총수익 계산용)
개별 종목은 여기서 받지 않는다(상장폐지 종목이 없어 백테스트가 부풀려짐)."""
import os, sys, csv, json, time, urllib.request, urllib.parse
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "data_us")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
      "Accept": "application/json,text/csv,*/*"}
TICKERS = {
    "지수": ["^GSPC", "^NDX", "^RUT", "^VIX"],
    "시장 ETF": ["SPY", "QQQ", "IWM", "DIA", "VTI", "MDY"],
    "섹터 ETF": ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC", "SMH", "XBI", "ITB", "KRE"],
    "스타일 ETF": ["MTUM", "QUAL", "VLUE", "USMV", "VUG", "VTV"],
    "해외 ETF": ["EFA", "EEM", "EWJ", "EWY", "FXI", "INDA"],
    "채권·대체 ETF": ["TLT", "IEF", "SHY", "LQD", "HYG", "GLD", "SLV", "USO", "VNQ", "DBC"],
}


def http(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def yahoo(t):
    q = urllib.parse.quote(t)
    for host in ("query1", "query2"):
        try:
            js = json.loads(http(f"https://{host}.finance.yahoo.com/v8/finance/chart/{q}?period1=946684800&period2=9999999999&interval=1d&events=div%2Csplits"))
            res = js["chart"]["result"][0]
            ts, qd = res["timestamp"], res["indicators"]["quote"][0]
            adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or qd["close"]
            rows = []
            for i, s in enumerate(ts):
                o, h, l, c, v, a = qd["open"][i], qd["high"][i], qd["low"][i], qd["close"][i], qd["volume"][i], adj[i]
                if None in (o, h, l, c) or c <= 0:
                    continue
                d = datetime.fromtimestamp(s, timezone.utc).strftime("%Y-%m-%d")
                rows.append((d, round(o, 4), round(h, 4), round(l, 4), round(c, 4), round(a if a else c, 4), int(v or 0)))
            if len(rows) > 200:
                return rows, "yahoo"
        except Exception as e:
            err = repr(e)[:120]
            time.sleep(1)
    raise RuntimeError(err)


def stooq(t):
    if t.startswith("^"):
        sym = {"^GSPC": "^spx", "^NDX": "^ndx", "^RUT": "^rut", "^VIX": "^vix"}.get(t)
    else:
        sym = t.lower() + ".us"
    if not sym:
        raise RuntimeError("no stooq symbol")
    txt = http(f"https://stooq.com/q/d/l/?s={urllib.parse.quote(sym)}&i=d")
    rows = []
    for r in csv.DictReader(txt.splitlines()):
        try:
            if r["Date"] < "2000-01-01":
                continue
            c = float(r["Close"])
            rows.append((r["Date"], float(r["Open"]), float(r["High"]), float(r["Low"]), c, c, int(float(r.get("Volume") or 0))))
        except Exception:
            continue
    if len(rows) <= 200:
        raise RuntimeError("stooq: " + txt[:80].replace("\n", " "))
    return rows, "stooq"      # Stooq 가격은 분할·배당이 이미 반영된 값


def main():
    os.makedirs(OUT, exist_ok=True)
    ok, fail, src = 0, [], {}
    for grp, ts in TICKERS.items():
        for t in ts:
            rows, last = None, ""
            for fn in (yahoo, stooq):
                try:
                    rows, s = fn(t)
                    break
                except Exception as e:
                    last += f"[{fn.__name__}: {str(e)[:90]}] "
            if not rows:
                fail.append(t); print(f"  실패 {t} — {last}", flush=True); continue
            with open(os.path.join(OUT, t.replace("^", "_") + ".csv"), "w", newline="") as f:
                csv.writer(f).writerows([("date", "open", "high", "low", "close", "adjclose", "volume")] + rows)
            ok += 1; src[s] = src.get(s, 0) + 1
            time.sleep(0.4)
    with open(os.path.join(OUT, "_universe.json"), "w", encoding="utf-8") as f:
        json.dump(TICKERS, f, ensure_ascii=False, indent=1)
    print(f"완료: 성공 {ok} (출처 {src}), 실패 {len(fail)} {fail}")
    if ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
