#!/usr/bin/env python3
"""KRX Open API로 '그날 상장돼 있던 전 종목' 일봉을 날짜별로 수집 (상장폐지 종목 포함 → 생존편향 제거)
맥 터미널:  python3 ~/Downloads/quant/fetch_krx.py
- 키: ~/Claude/kosdaq_db/config.json 의 krx_api_key (또는 환경변수 KRX_API_KEY). 키는 화면·파일에 출력하지 않는다.
- 최근 날짜부터 과거(2011-01-03)로 거슬러 받는다. 중단돼도 다시 실행하면 이어받는다.
- 하루 호출 한도를 다 쓰지 않도록 1회 실행당 최대 7,500회만 호출(옵션: --max N). 남은 분량은 다음 날 다시 실행.
- 저장: raw_krx/<시장>/<YYYYMMDD>.csv.gz. 빈 응답 날짜는 raw_krx/_empty.json 에 기록하고, 서로 다른 2일에 걸쳐 비어 있으면 휴장일로 확정.
- GitHub Actions에서는 환경변수 KRX_API_KEY 를 쓴다."""
import os, sys, json, gzip, csv, io, time, threading, urllib.request, urllib.error
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "raw_krx")
URL = "https://data-dbg.krx.co.kr/svc/apis/"
EP = {"KOSPI": "sto/stk_bydd_trd", "KOSDAQ": "sto/ksq_bydd_trd"}
COLS = ["ISU_CD", "ISU_NM", "TDD_OPNPRC", "TDD_HGPRC", "TDD_LWPRC", "TDD_CLSPRC", "CMPPREVDD_PRC", "FLUC_RT",
        "ACC_TRDVOL", "ACC_TRDVAL", "MKTCAP", "LIST_SHRS", "SECT_TP_NM"]
START = date(2011, 1, 3)
MAX = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 7500
stop = threading.Event()
lock = threading.Lock()
stat = {"done": 0, "rows": 0, "empty": 0, "err": 0, "msg": "", "streak": 0, "new_empty": []}
EMPTY = {}
TODAY = date.today().isoformat()
EMPTY_PATH = os.path.join(OUT, "_empty.json")


def key():
    k = os.environ.get("KRX_API_KEY")
    if not k:
        p = os.path.expanduser("~/Claude/kosdaq_db/config.json")
        if os.path.exists(p):
            k = json.load(open(p, encoding="utf-8")).get("krx_api_key")
    if not k:
        sys.exit("KRX 키를 찾지 못했습니다 (~/Claude/kosdaq_db/config.json 의 krx_api_key).")
    return k


KEY = None


def call(mk, ymd):
    req = urllib.request.Request(f"{URL}{EP[mk]}?basDd={ymd}",
                                 headers={"AUTH_KEY": KEY, "User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        js = json.loads(r.read().decode("utf-8"))
    if "OutBlock_1" in js:
        return js["OutBlock_1"]
    for v in js.values():
        if isinstance(v, list):
            return v
    return []


def save(mk, ymd, rows):
    path = os.path.join(OUT, mk, ymd + ".csv.gz")
    buf = io.StringIO()
    if rows:
        w = csv.writer(buf)
        w.writerow(COLS)
        for r in rows:
            w.writerow([r.get(c, "") for c in COLS])
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        f.write(buf.getvalue())
    os.replace(tmp, path)


def job(task):
    mk, ymd = task
    if stop.is_set():
        return
    for k in range(4):
        try:
            rows = call(mk, ymd)
            if rows:
                save(mk, ymd, rows)
            with lock:
                stat["done"] += 1
                stat["rows"] += len(rows)
                stat["empty"] += (not rows)
                if rows:
                    stat["streak"] = 0
                else:
                    stat["streak"] += 1
                    EMPTY.setdefault(f"{mk}/{ymd}", [])
                    if TODAY not in EMPTY[f"{mk}/{ymd}"]:
                        EMPTY[f"{mk}/{ymd}"].append(TODAY)
                    stat["new_empty"].append(f"{mk}/{ymd}")
                    if stat["streak"] >= 24:      # 연휴로는 불가능한 연속 빈 응답 → 한도 소진·장애로 판단
                        stat["msg"] = "빈 응답이 24회 연속 — KRX 호출 한도 소진 또는 장애로 보고 중단(이번 연속분은 휴장일로 기록하지 않음)"
                        for k2 in stat["new_empty"][-24:]:
                            if TODAY in EMPTY.get(k2, []):
                                EMPTY[k2].remove(TODAY)
                        stop.set()
                if stat["done"] % 200 == 0:
                    print(f"  {stat['done']}회 완료 (최근 처리 {mk} {ymd}, 누적 {stat['rows']:,}행)", flush=True)
            return
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:200]
            if e.code in (401, 403, 429):
                with lock:
                    stat["msg"] = f"{mk} {ymd} HTTP {e.code}: {body}"
                stop.set()
                return
            err = f"HTTP {e.code} {body}"
        except Exception as e:
            err = repr(e)
        time.sleep(2 * (k + 1))
    with lock:
        stat["err"] += 1
        if stat["err"] <= 5:
            print(f"  실패 {mk} {ymd}: {err}", flush=True)
        if stat["err"] >= 30:
            stat["msg"] = f"오류가 30회 누적되어 중단: {err}"
            stop.set()


def main():
    global KEY
    KEY = key()
    for mk in EP:
        os.makedirs(os.path.join(OUT, mk), exist_ok=True)
    if os.path.exists(EMPTY_PATH):
        EMPTY.update(json.load(open(EMPTY_PATH, encoding="utf-8")))
    # 1) 사전 점검: 최근 거래일 1일치로 두 시장 모두 응답하는지 확인
    d = date.today() - timedelta(days=1)
    for mk in EP:
        ok = False
        for back in range(10):
            dd = d - timedelta(days=back)
            if dd.weekday() >= 5:
                continue
            try:
                rows = call(mk, dd.strftime("%Y%m%d"))
            except urllib.error.HTTPError as e:
                sys.exit(f"[점검 실패] {mk} HTTP {e.code}: {e.read().decode('utf-8','replace')[:200]}\n"
                         f"→ KRX Open API에서 '{'유가증권' if mk=='KOSPI' else '코스닥'} 일별매매정보' 이용신청이 승인돼 있는지 확인이 필요합니다.")
            if rows:
                print(f"[점검] {mk} {dd}: {len(rows)}종목, 필드 {sorted(rows[0].keys())}")
                ok = True
                break
        if not ok:
            sys.exit(f"[점검 실패] {mk}: 최근 10일간 데이터가 없습니다.")
    # 2) 할 일 목록 (최근 → 과거)
    tasks, dd = [], date.today() - timedelta(days=1)
    while dd >= START:
        if dd.weekday() < 5:
            ymd = dd.strftime("%Y%m%d")
            for mk in EP:
                tried = EMPTY.get(f"{mk}/{ymd}", [])
                recent = (date.today() - dd).days <= 7        # 최근 7일은 미집계일 수 있어 휴장 확정 안 함
                if os.path.exists(os.path.join(OUT, mk, ymd + ".csv.gz")):
                    continue
                if not recent and (len(tried) >= 2 or TODAY in tried):
                    continue
                tasks.append((mk, ymd))
        dd -= timedelta(days=1)
    total = len(tasks)
    tasks = tasks[:MAX]
    print(f"남은 호출 {total:,}회 중 이번 실행 {len(tasks):,}회", flush=True)
    t0 = time.time()
    try:
        with ThreadPoolExecutor(max_workers=3) as ex:
            list(ex.map(job, tasks))
    except KeyboardInterrupt:
        stop.set()
        print("중단됨.")
    with open(EMPTY_PATH, "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in sorted(EMPTY.items()) if v}, f)
    left = total - stat["done"]
    print(f"이번 실행: {stat['done']:,}회 성공(휴장일 {stat['empty']:,}), 실패 {stat['err']}, {int(time.time()-t0)}초. 남은 호출 {left:,}회.")
    if stat["msg"]:
        print("중단 사유:", stat["msg"])
    print("완료." if left <= 0 else "남은 분량은 다음 실행에서 이어받습니다.")


if __name__ == "__main__":
    main()
