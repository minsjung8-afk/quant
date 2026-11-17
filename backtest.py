"""일봉 백테스터. 종가 신호 -> 익일 시가 체결. 손절/추적청산은 장중 저가 도달 시 체결(갭하락은 시가)."""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from strategies import Strategy


@dataclass
class Costs:
    commission: float = 0.00015   # 편도 수수료
    sell_tax: float = 0.0020      # 매도 시 거래세 등 (국내 가정값, 미국은 0으로)
    slippage: float = 0.0005      # 편도 슬리피지


def run(df: pd.DataFrame, st: Strategy, costs: Costs = Costs()):
    """df: add_indicators 결과. 반환: (거래 DataFrame, 일별 자산곡선 Series[시작=1])"""
    trades, pos, pending = [], None, None
    eq, equity = 1.0, []
    idx = df.index
    o, h, l, c, atr = (df[k].values for k in ["open", "high", "low", "close", "atr14"])
    prev_c = None
    for i, r in enumerate(df.itertuples()):
        day_ret = 0.0
        exit_px = reason = None
        # 1) 전일 신호 체결 (시가)
        if pending == "buy" and pos is None and np.isfinite(o[i]) and o[i] > 0:
            px = o[i] * (1 + costs.slippage)
            a = atr[i - 1] if i > 0 else np.nan
            pos = dict(entry_i=i, entry_date=idx[i], entry=px, atr=a, hi_close=c[i],
                       stop=px - st.stop_atr * a if st.stop_atr and np.isfinite(a) else -np.inf)
            day_ret = c[i] / px - 1 - costs.commission
        elif pending and pending != "buy" and pos is not None:
            exit_px, reason = o[i], pending
        pending = None
        # 2) 보유 중: 장중 손절/추적청산
        if pos is not None and exit_px is None and pos["entry_i"] != i:
            stop = pos["stop"]
            if st.trail_atr and np.isfinite(pos["atr"]):
                stop = max(stop, pos["hi_close"] - st.trail_atr * atr[i - 1])
            if l[i] <= stop:
                exit_px = min(o[i], stop)
                reason = "손절" if stop == pos["stop"] else "추적청산"
        # 3) 청산 처리
        if exit_px is not None:
            net = exit_px * (1 - costs.slippage - costs.commission - costs.sell_tax)
            day_ret = net / prev_c - 1
            trades.append(dict(entry_date=pos["entry_date"], exit_date=idx[i], entry=pos["entry"],
                               exit=net, ret=net / pos["entry"] * (1 - costs.commission) - 1,
                               days=i - pos["entry_i"], reason=reason))
            pos = None
        elif pos is not None and pos["entry_i"] != i:
            day_ret = c[i] / prev_c - 1
        eq *= 1 + day_ret
        equity.append(eq)
        # 4) 종가 신호 판정 -> 익일 체결 예약
        if pos is not None:
            pos["hi_close"] = max(pos["hi_close"], c[i])
            why = st.exit(r, pos)
            if why is None and st.max_hold and i - pos["entry_i"] + 1 >= st.max_hold:
                why = "시간청산"
            pending = why
        elif st.entry(r):
            pending = "buy"
        prev_c = c[i]
    return pd.DataFrame(trades), pd.Series(equity, index=idx)


def metrics(trades: pd.DataFrame, equity: pd.Series) -> dict:
    yrs = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
    mdd = (equity / equity.cummax() - 1).min()
    dr = equity.pct_change().dropna()
    out = dict(거래수=len(trades), CAGR=equity.iloc[-1] ** (1 / yrs) - 1, MDD=mdd,
               샤프=dr.mean() / dr.std() * np.sqrt(252) if dr.std() > 0 else np.nan)
    if len(trades):
        w, ls = trades.ret[trades.ret > 0], trades.ret[trades.ret <= 0]
        out.update(승률=len(w) / len(trades), 평균수익=trades.ret.mean(), 평균보유일=trades.days.mean(),
                   손익비=w.sum() / -ls.sum() if ls.sum() < 0 else np.inf)
    return out


def current_signal(df: pd.DataFrame, st: Strategy, costs: Costs = Costs()) -> dict:
    """마지막 날 종가 기준 상태: 매수 / 보유 / 매도 / 관망 (2단계 대시보드용)"""
    trades, _ = run(df, st, costs)
    last = df.iloc[-1]
    # 마지막 날까지 돌린 뒤의 상태를 재현
    state = _replay_state(df, st, costs)
    return dict(date=df.index[-1], close=float(last.close), **state)


def _replay_state(df, st, costs):
    pos, pending = None, None
    o, l, c, atr = (df[k].values for k in ["open", "low", "close", "atr14"])
    for i, r in enumerate(df.itertuples()):
        closed = False
        if pending == "buy" and pos is None:
            a = atr[i - 1]
            pos = dict(entry_i=i, entry=o[i], atr=a, hi_close=c[i],
                       stop=o[i] - st.stop_atr * a if st.stop_atr and np.isfinite(a) else -np.inf)
        elif pending and pending != "buy" and pos is not None:
            pos, closed = None, True
        pending = None
        if pos is not None and pos["entry_i"] != i:
            stop = pos["stop"]
            if st.trail_atr and np.isfinite(pos["atr"]):
                stop = max(stop, pos["hi_close"] - st.trail_atr * atr[i - 1])
            if l[i] <= stop:
                pos, closed = None, True
        if pos is not None:
            pos["hi_close"] = max(pos["hi_close"], c[i])
            why = st.exit(r, pos)
            if why is None and st.max_hold and i - pos["entry_i"] + 1 >= st.max_hold:
                why = "시간청산"
            pending = why
        elif not closed and st.entry(r):
            pending = "buy"
    if pos is None:
        return dict(signal="매수" if pending == "buy" else "관망", reason="진입조건 충족" if pending == "buy" else "", stop=None)
    stop = pos["stop"]
    if st.trail_atr and np.isfinite(pos["atr"]):
        stop = max(stop, pos["hi_close"] - st.trail_atr * atr[-1])
    return dict(signal="매도" if pending else "보유", reason=pending or "",
                stop=None if not np.isfinite(stop) else float(stop))
