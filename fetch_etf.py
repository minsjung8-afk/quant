#!/usr/bin/env python3
"""국내 상장 ETF 일봉 수집 (네이버 금융, 분할 반영 가격·분배금 미반영).
결과: data_etf/<코드>.csv (date,open,high,low,close,volume), data_etf/_names.json (코드→네이버 종목명, 코드 검증용)"""
import os, re, csv, json, time, urllib.request
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "data_etf")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
ROW = re.compile(r'\["(\d{8})",\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)')
# 코드: 기대하는 자산 (실제 종목명은 _names.json 으로 대조)
ETF = {
    "069500": "국내 대형주 (코스피200)", "229200": "국내 코스닥150", "133690": "미국 나스닥100 (환노출)",
    "143850": "미국 S&P500 선물 (환헤지)", "360750": "미국 S&P500 (환노출)", "379800": "미국 S&P500 TR", "379810": "미국 나스닥100 TR",
    "251350": "선진국 MSCI World", "195930": "유럽 유로스탁스50 (H)", "241180": "일본 니케이225", "192090": "중국 CSI300",
    "195980": "신흥국 MSCI (H)", "114260": "국고채 3년", "148070": "국고채 10년", "153130": "단기채권 (현금 대용)",
    "305080": "미국채 10년 선물", "304660": "미국채 30년 선물 (H)", "132030": "금 선물 (H)", "411060": "금 현물",
    "130680": "원유 선물 (H)", "261240": "미국 달러 선물", "182480": "미국 리츠 (H)", "091160": "국내 반도체", "091170": "국내 은행",
}


def http(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def main():
    os.makedirs(OUT, exist_ok=True)
    end = date.today().strftime("%Y%m%d")
    names, ok = {}, 0
    for code, what in ETF.items():
        try:
            txt = http(f"https://api.finance.naver.com/siseJson.naver?symbol={code}&requestType=1&startTime=20020101&endTime={end}&timeframe=day")
            rows = [(f"{d[:4]}-{d[4:6]}-{d[6:]}", o, h, l, c, v) for d, o, h, l, c, v in ROW.findall(txt) if float(c) > 0]
            if len(rows) < 50:
                raise ValueError(f"{len(rows)}행")
            with open(os.path.join(OUT, code + ".csv"), "w", newline="") as f:
                csv.writer(f).writerows([("date", "open", "high", "low", "close", "volume")] + rows)
            ok += 1
            try:
                names[code] = json.loads(http(f"https://m.stock.naver.com/api/stock/{code}/basic")).get("stockName", "")
            except Exception:
                names[code] = ""
            print(f"{code} [{what}] → {names[code] or '(이름 조회 실패)'}: {len(rows)}일, {rows[0][0]} ~ {rows[-1][0]}", flush=True)
        except Exception as e:
            print(f"{code} [{what}] 실패: {e!r}", flush=True)
        time.sleep(0.3)
    with open(os.path.join(OUT, "_names.json"), "w", encoding="utf-8") as f:
        json.dump({k: {"expected": ETF[k], "naver_name": names.get(k, "")} for k in ETF}, f, ensure_ascii=False, indent=1)
    print(f"완료: {ok}/{len(ETF)}")


if __name__ == "__main__":
    main()
