"""가설 조합. 각 전략은 entry(행) -> bool, exit(행, 보유상태) -> 사유 or None 과 손절 배수를 정의.
신호는 당일 종가로 판정, 체결은 익일 시가."""
from dataclasses import dataclass
from typing import Callable, Optional
import pandas as pd


@dataclass
class Strategy:
    name: str
    desc: str
    entry: Callable[[pd.Series], bool]
    exit: Callable[[pd.Series, dict], Optional[str]]
    stop_atr: float = 3.0      # 진입가 - N*ATR 고정 손절 (0이면 미사용)
    trail_atr: float = 0.0     # 보유 중 최고 종가 - N*ATR 추적 청산 (0이면 미사용)
    max_hold: int = 0          # 최대 보유일 (0이면 무제한)


def _ok(r, cols):
    return all(pd.notna(getattr(r, c)) for c in cols)


def pullback(rsi_in=10, rsi_out=70, max_hold=10, stop_atr=3.0):
    def entry(r):
        return _ok(r, ["sma200", "rsi2"]) and r.close > r.sma200 and r.rsi2 < rsi_in
    def exit_(r, pos):
        if r.rsi2 > rsi_out: return "RSI회복"
        if r.close < r.sma200: return "추세이탈"
        return None
    return Strategy(f"눌림목(rsi<{rsi_in})", "200일선 위 + RSI(2) 과매도 매수, RSI 회복 시 매도",
                    entry, exit_, stop_atr=stop_atr, max_hold=max_hold)


def breakout(rvol_min=1.5, trail_atr=3.0):
    def entry(r):
        return (_ok(r, ["sma200", "don_hi55", "rvol20"]) and r.close > r.sma200
                and r.close > r.don_hi55 and r.rvol20 >= rvol_min)
    def exit_(r, pos):
        if pd.notna(r.don_lo20) and r.close < r.don_lo20: return "20일저가이탈"
        return None
    return Strategy(f"돌파(rvol>={rvol_min})", "55일 신고가 돌파 + 거래량 동반 매수, 20일 저가 이탈 또는 ATR 추적 청산",
                    entry, exit_, stop_atr=0.0, trail_atr=trail_atr)


def trend(adx_min=20, stop_atr=0.0):
    def entry(r):
        return (_ok(r, ["sma200", "mom_12_1", "adx14"]) and r.close > r.sma200
                and r.mom_12_1 > 0 and r.adx14 >= adx_min)
    def exit_(r, pos):
        if r.close < r.sma200: return "추세이탈"
        if pd.notna(r.mom_12_1) and r.mom_12_1 < 0: return "모멘텀소멸"
        return None
    return Strategy(f"추세추종(adx>={adx_min})", "200일선 위 + 12-1 모멘텀 양수 + ADX 확인 매수, 추세 이탈 시 매도",
                    entry, exit_, stop_atr=stop_atr)


DEFAULTS = [pullback(), breakout(), trend()]
