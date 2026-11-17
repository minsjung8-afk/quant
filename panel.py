"""panel/ 로더 + 종목군 + 지표(날짜×종목 행렬). 모든 지표는 당일 종가까지의 정보만 사용."""
import os
import numpy as np, pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
P = lambda k: pd.read_pickle(os.path.join(BASE, "panel", k + ".pkl")).astype("float64")


def load():
    ret, c0, meta = P("ret"), P("c"), pd.read_pickle(os.path.join(BASE, "panel", "meta.pkl"))
    listed = c0.notna()
    ret = ret.where(ret <= 1.0, 0.0)               # 하루 +100% 초과(감자 후 재개·정리매매 등 기준가 특이값)는 잡을 수 없는 수익으로 보고 0 처리. 하락은 그대로 둔다
    # 상장폐지 이후에는 수익률 0(현금 보유)으로 이어지는 총수익 지수 — 정리매매 손실은 ret에 이미 반영
    I = np.exp(np.log1p(ret.fillna(0.0).clip(lower=-0.999)).cumsum())
    g = (I / c0).where(listed)
    d = {"ret": ret, "I": I, "c": I.where(listed), "o": P("o") * g, "h": P("h") * g, "l": P("l") * g,
         "raw_c": P("raw_c"), "val": P("val"), "mcap": P("mcap"), "listed": listed, "meta": meta}
    return d


def universe(d, min_val=1e9, min_price=1000, min_hist=252, top=None):
    """시점별 종목군: 보통주(스팩·리츠 제외), 상장 후 min_hist 거래일 경과, 20일 평균 거래대금 하한, 주가 하한, 당일 거래 있음"""
    meta = d["meta"]
    common = np.array([k.endswith("0") for k in d["c"].columns])
    bad = meta.name.reindex(d["c"].columns).fillna("").str.contains("스팩|기업인수목적|리츠|인프라펀드|맥쿼리").values
    hist = d["listed"].cumsum() >= min_hist
    liq = d["val"].rolling(20, min_periods=15).mean() >= min_val
    U = d["listed"] & hist & liq & (d["raw_c"] >= min_price) & (d["val"] > 0)
    U.loc[:, ~common | bad] = False
    if top:                                   # 시점별 시가총액 상위 top개 (전일 시총 기준)
        m = d["mcap"].shift(1).where(U)
        U = U & (m.rank(axis=1, ascending=False, method="first") <= top)
    return U


def _wilder(x, n):
    return x.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def indicators(d):
    """점수 행렬 dict (값이 클수록 '매수 쪽'이 되도록 부호를 맞춤). 10개 지표 + 변형."""
    c, h, l, val = d["c"], d["h"], d["l"], d["val"]
    pc = c.shift(1)
    out = {}
    sma200 = c.rolling(200, min_periods=150).mean()
    out["1.200일선 이격(높음)"] = c / sma200 - 1
    out["2.모멘텀 12-1(높음)"] = c.shift(21) / c.shift(252) - 1
    out["3.상대강도 6개월(높음)"] = c / c.shift(126) - 1
    tr = np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs()))
    atr = _wilder(tr, 14)
    up, dn = h.diff(), -l.diff()
    pdm = up.where((up > dn) & (up > 0), 0.0).where(c.notna())
    mdm = dn.where((dn > up) & (dn > 0), 0.0).where(c.notna())
    pdi, mdi = 100 * _wilder(pdm, 14) / atr, 100 * _wilder(mdm, 14) / atr
    adx = _wilder(100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan), 14)
    out["4.ADX(높음)"] = adx
    out["4b.ADX×방향(+DI>-DI)"] = adx * np.sign(pdi - mdi)
    out["5.52주 신고가 근접(높음)"] = c / h.rolling(252, min_periods=200).max()
    diff = c.diff()
    rs = _wilder(diff.clip(lower=0), 2) / _wilder(-diff.clip(upper=0), 2).replace(0, np.nan)
    rsi2 = (100 - 100 / (1 + rs)).where(c.notna())
    out["6.RSI(2) 과매도(낮음)"] = -rsi2
    ma, sd = c.rolling(20).mean(), c.rolling(20).std(ddof=0)
    out["7.볼린저 %B(낮음)"] = -((c - (ma - 2 * sd)) / (4 * sd).replace(0, np.nan))
    out["7b.볼린저 밴드폭(좁음)"] = -(4 * sd / ma)
    out["8.ATR%(낮음=저변동)"] = -(atr / c)
    out["9.상대거래대금(높음)"] = val / val.rolling(20).mean().shift(1)
    out["10.단기반전 5일(하락)"] = -(c / c.shift(5) - 1)
    out["10b.단기반전 21일(하락)"] = -(c / c.shift(21) - 1)
    return out
