# quant

전일 종가 기준 매수·매도 신호 시스템 (개인용).

- `fetch_krx.py` — KRX Open API로 날짜별 전 종목 일봉 수집 → `raw_krx/<시장>/<날짜>.csv.gz` (상장폐지 종목 포함)
- `fetch_index.py` — 벤치마크 지수(코스피·코스닥·코스피200) → `data_index/`
- `indicators.py` / `strategies.py` / `backtest.py` — 지표 10개, 가설 전략, 일봉 백테스터
- `.github/workflows/collect.yml` — 매일 아침 자동 수집. 저장소 Secrets에 `KRX_API_KEY` 필요

주문 기능은 넣지 않는다. API 키는 저장소에 올리지 않는다.
