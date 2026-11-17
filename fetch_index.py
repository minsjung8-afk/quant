#!/usr/bin/env python3
"""벤치마크 지수 일봉 수집 (네이버 금융) — 맥 터미널:  python3 ~/Downloads/quant/fetch_index.py
결과: data_index/KOSPI.csv, KOSDAQ.csv, KOSPI200.csv (date,open,high,low,close,volume)"""
import os, re, csv, time, urllib.request
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "data_index")
SYM = {"KOSPI": "KOSPI", "KOSDAQ": "KOSDAQ", "KOSPI200": "KPI200"}
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
ROW = re.compile(r'\["(\d{8})",\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)')

os.makedirs(OUT, exist_ok=True)
end = date.today().strftime("%Y%m%d")
for name, sym in SYM.items():
    url = (f"https://api.finance.naver.com/siseJson.naver?symbol={sym}&requestType=1"
           f"&startTime=20100101&endTime={end}&timeframe=day")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            txt = r.read().decode("utf-8", "replace")
        rows = [(f"{d[:4]}-{d[4:6]}-{d[6:]}", o, h, l, c, v) for d, o, h, l, c, v in ROW.findall(txt) if float(c) > 0]
        if len(rows) < 100:
            open(os.path.join(BASE, f"debug_index_{name}.txt"), "w", encoding="utf-8").write(txt[:5000])
            print(f"{name}: 실패 ({len(rows)}행) — debug_index_{name}.txt 저장")
            continue
        with open(os.path.join(OUT, name + ".csv"), "w", newline="") as f:
            csv.writer(f).writerows([("date", "open", "high", "low", "close", "volume")] + rows)
        print(f"{name}: {len(rows)}일 ({rows[0][0]} ~ {rows[-1][0]}), 최근 종가 {rows[-1][4]}")
    except Exception as e:
        print(f"{name}: 실패 {e!r}")
    time.sleep(0.3)
