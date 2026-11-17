#!/usr/bin/env python3
"""DART 다중회사 주요계정(fnlttMultiAcnt)으로 2015년 이후 전 상장사(상장폐지 포함) 재무 이력 수집. 표준 라이브러리만 사용.
- 키: 환경변수 DART_API_KEY (GitHub Actions) 또는 ~/Claude/kosdaq_db/config.json 의 dart_api_key (맥). 키는 출력하지 않는다.
- 호출: 회사 100개 × (연도, 보고서 종류) 단위. 이미 받은 (연도, 보고서)는 건너뛴다.
- 저장: raw_dart/<연도>_<보고서코드>.csv.gz, raw_dart/corp_map.csv"""
import os, sys, io, csv, gzip, json, time, zipfile, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "raw_dart")
API = "https://opendart.fss.or.kr/api/"
REPORTS = ["11011", "11012", "11013", "11014"]     # 사업, 반기, 1분기, 3분기
COLS = ["rcept_no", "corp_code", "stock_code", "fs_div", "sj_div", "account_nm", "thstrm_dt", "thstrm_amount", "thstrm_add_amount", "frmtrm_amount", "currency"]
UA = {"User-Agent": "Mozilla/5.0"}


def key():
    k = os.environ.get("DART_API_KEY")
    if not k:
        p = os.path.expanduser("~/Claude/kosdaq_db/config.json")
        if os.path.exists(p):
            k = json.load(open(p, encoding="utf-8")).get("dart_api_key")
    if not k:
        sys.exit("DART 키가 없습니다. GitHub Secrets의 DART_API_KEY 또는 ~/Claude/kosdaq_db/config.json 의 dart_api_key 가 필요합니다.")
    return k


KEY = None


def get(path, **params):
    url = API + path + "?" + urllib.parse.urlencode({"crtfc_key": KEY, **params})
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return r.read()
        except Exception as e:
            err = repr(e)[:150]; time.sleep(3 * (k + 1))
    raise RuntimeError(err)


def corp_map():
    path = os.path.join(OUT, "corp_map.csv")
    if os.path.exists(path):
        return [r for r in csv.DictReader(open(path, encoding="utf-8"))]
    z = zipfile.ZipFile(io.BytesIO(get("corpCode.xml")))
    root = ET.fromstring(z.read(z.namelist()[0]))
    rows = []
    for el in root.iter("list"):
        sc = (el.findtext("stock_code") or "").strip()
        if len(sc) == 6:
            rows.append({"corp_code": el.findtext("corp_code").strip(), "stock_code": sc, "corp_name": (el.findtext("corp_name") or "").strip()})
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["corp_code", "stock_code", "corp_name"]); w.writeheader(); w.writerows(rows)
    return rows


def fetch(codes, year, rep, size=100):
    rows, calls, i = [], 0, 0
    while i < len(codes):
        chunk = codes[i:i + size]
        js = json.loads(get("fnlttMultiAcnt.json", corp_code=",".join(chunk), bsns_year=str(year), reprt_code=rep).decode("utf-8"))
        calls += 1
        st = js.get("status")
        if st == "000":
            rows += js.get("list", [])
        elif st == "013":
            pass                                   # 해당 묶음에 데이터 없음
        elif st in ("020", "021"):
            raise RuntimeError("DART 한도 초과: " + str(js.get("message")))
        elif size > 10:                            # 묶음 크기 문제 등: 반으로 줄여 재시도
            size //= 2; print(f"  status {st} {js.get('message')} → 묶음 {size}개로 축소", flush=True); continue
        else:
            raise RuntimeError(f"DART 오류 {st}: {js.get('message')}")
        i += len(chunk); time.sleep(0.15)
    return rows, calls


def main():
    global KEY
    KEY = key(); os.makedirs(OUT, exist_ok=True)
    cm = corp_map(); codes = [r["corp_code"] for r in cm]
    print(f"종목코드가 있는 회사 {len(codes)}개 (상장폐지 포함)", flush=True)
    this = date.today().year; total = 0; t0 = time.time()
    for year in range(this, 2014, -1):
        for rep in REPORTS:
            path = os.path.join(OUT, f"{year}_{rep}.csv.gz")
            if os.path.exists(path) and year < this - 1:
                continue                            # 과거분은 한 번 받으면 재수집하지 않음
            try:
                rows, calls = fetch(codes, year, rep)
            except RuntimeError as e:
                print("중단:", e); print(f"누적 호출 {total}회"); sys.exit(0 if "한도" in str(e) else 1)
            total += calls
            buf = io.StringIO(); w = csv.writer(buf); w.writerow(COLS)
            for r in rows:
                w.writerow([r.get(c, "") for c in COLS])
            with gzip.open(path, "wt", encoding="utf-8") as f:
                f.write(buf.getvalue())
            print(f"{year} {rep}: {len(rows):,}행, 회사 {len({r.get('corp_code') for r in rows}):,}개 (호출 {calls})", flush=True)
    print(f"완료: 호출 {total}회, {int(time.time() - t0)}초")


if __name__ == "__main__":
    main()
