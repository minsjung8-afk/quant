"""지표 10개 계산. 입력: 일봉 DataFrame(open, high, low, close, volume), 날짜 오름차순.
모든 값은 '당일 종가까지의 정보'만 사용한다(미래 참조 금지). 돌파 기준선은 전일까지의 고가/저가."""
import numpy as np
import pandas as pd


def _wilder(s, n):
    return s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c, h, l, v = d["close"], d["high"], d["low"], d["volume"]
    pc = c.shift(1)

    # 1. 장기 이동평균 (추세 필터)
    d["sma200"] = c.rolling(200).mean()
    # 2. 시계열 모멘텀: 최근 1개월(21일) 제외 12개월(252일) 수익률
    d["mom_12_1"] = c.shift(21) / c.shift(252) - 1
    # 3. 상대강도 순위는 종목 간 비교라 panel.py에서 계산 (여기선 원재료인 6개월 수익률만)
    d["ret_126"] = c / c.shift(126) - 1
    # 8. ATR (손절·포지션 크기)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    d["atr14"] = _wilder(tr, 14)
    # 4. ADX (추세 강도)
    up, dn = h.diff(), -l.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=d.index)
    mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=d.index)
    pdi = 100 * _wilder(pdm, 14) / d["atr14"]
    mdi = 100 * _wilder(mdm, 14) / d["atr14"]
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    d["adx14"] = _wilder(dx, 14)
    # 5. 돈치안 채널 (전일까지 기준)
    d["don_hi55"] = h.rolling(55).max().shift(1)
    d["don_lo20"] = l.rolling(20).min().shift(1)
    d["hi252_ratio"] = c / h.rolling(252).max()  # 52주 신고가 근접도
    # 6. 단기 RSI(2)
    diff = c.diff()
    gain, loss = diff.clip(lower=0), -diff.clip(upper=0)
    rs = _wilder(gain, 2) / _wilder(loss, 2).replace(0, np.nan)
    d["rsi2"] = (100 - 100 / (1 + rs)).fillna(100)
    d.loc[d.index[:2], "rsi2"] = np.nan
    # 7. 볼린저밴드 %B, 밴드폭
    ma, sd = c.rolling(20).mean(), c.rolling(20).std(ddof=0)
    d["bb_pctb"] = (c - (ma - 2 * sd)) / (4 * sd).replace(0, np.nan)
    d["bb_width"] = 4 * sd / ma
    # 9. 상대거래량 (전일까지 20일 평균 대비)
    d["rvol20"] = v / v.rolling(20).mean().shift(1)
    # 10. 단기 반전 (5일 수익률)
    d["rev_5d"] = c / c.shift(5) - 1
    return d
