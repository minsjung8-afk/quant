#!/usr/bin/env python3
"""본인의 심사참고 DB 사이트(kosdaq-db.pages.dev)에 공개된 기업별 JSON에서 재무 요약만 뽑아 저장. DART를 호출하지 않는다.
결과: data_fin/fin.json.gz  {meta, companies: {종목코드: {name, market, delisted, kpi:{CFS:[..],OFS:[..]}, quarters, ann5}}}"""
import os, json, gzip, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
SITE = "https://kosdaq-db.pages.dev/data/"
UA = {"User-Agent": "quant-fin-fetch/1.0"}
KEEP = ["bsns_year", "reprt_code", "rcept_no", "label", "kind", "revenue", "op_income", "net_income", "total_assets", "total_liab", "equity",
        "cash", "borrowings", "net_borrowings", "da", "ebitda", "cfo", "int_exp", "cur_assets", "cur_liab"]


def get(path):
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(SITE + path, headers=UA), timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            err = repr(e)[:120]; time.sleep(2 * (k + 1))
    raise RuntimeError(err)


def one(it):
    code = it.get("code")
    try:
        d = get(f"c/{code}.json")
    except Exception as e:
        return code, None, str(e)
    kpi = {fs: [{k: r.get(k) for k in KEEP} for r in rows] for fs, rows in (d.get("kpi") or {}).items()}
    return code, {"name": it.get("name"), "market": it.get("market"), "delisted": it.get("delisted"), "sector": it.get("sector"),
                  "cur": it.get("cur"), "kpi": kpi, "quarters": d.get("quarters"), "ann5": d.get("ann5")}, None


def main():
    idx = get("companies.json")
    items = [it for it in idx["items"] if it.get("code") and it.get("market") in ("KOSPI", "KOSDAQ")]
    print(f"사이트 기준 {idx['meta'].get('built_at')} · 코스피·코스닥 {len(items)}개 (전체 {len(idx['items'])}개)", flush=True)
    out, fail = {}, 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        for n, (code, rec, err) in enumerate(ex.map(one, items), 1):
            if rec is None:
                fail += 1
                if fail <= 5: print("  실패", code, err, flush=True)
            else:
                out[code] = rec
            if n % 500 == 0: print(f"  {n}/{len(items)}", flush=True)
    os.makedirs(os.path.join(BASE, "data_fin"), exist_ok=True)
    with gzip.open(os.path.join(BASE, "data_fin", "fin.json.gz"), "wt", encoding="utf-8") as f:
        json.dump({"meta": idx["meta"], "companies": out}, f, ensure_ascii=False)
    has = sum(1 for v in out.values() if v["kpi"])
    print(f"완료: {len(out)}개 저장(재무 있음 {has}), 실패 {fail}")


if __name__ == "__main__":
    main()
