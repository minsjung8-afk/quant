"""순위 기반 포트폴리오 백테스트: N거래일마다 점수 상위 K종목 동일비중 보유.
- 신호는 종가로 판정, 체결은 다음 거래일 종가. 비용 = 매수·매도 금액 × 편도 비용.
- tranches: 자금을 여러 묶음으로 나눠 서로 다른 날 교체(교체일 운 제거)
- buffer: 기존 보유 종목은 순위 k+buffer 안이면 유지(회전율 축소)
- expo: 날짜별 목표 주식 비중(시장 필터). 나머지는 현금(수익 0)"""
import numpy as np, pandas as pd

BUY_COST = 0.00015 + 0.0005            # 수수료 + 슬리피지
SELL_COST = 0.00015 + 0.0005 + 0.0020  # + 거래세(가정값)


def _one(ret, Uv, S, idx, k, every, offset, cost_mult, buffer, expo):
    w = np.zeros(ret.shape[1]); pending = None; sel = []
    out = np.zeros(len(idx)); sells = 0.0; last_e = None
    for n, i in enumerate(idx):
        r = float(w @ ret[i])
        w = w * (1 + ret[i]) / (1 + r)                     # 총자산 대비 비중으로 재정규화
        cost = 0.0
        if pending is not None:
            buy, sell = np.clip(pending - w, 0, None).sum(), np.clip(w - pending, 0, None).sum()
            cost = (buy * BUY_COST + sell * SELL_COST) * cost_mult
            sells += sell; w = pending; pending = None
        out[n] = r - cost
        e = 1.0 if expo is None else expo[i]
        if n % every == offset:
            m = Uv[i] & np.isfinite(S[i])
            if m.sum() >= k:
                order = np.argsort(-np.where(m, S[i], -np.inf))
                if buffer and sel:
                    keep = [j for j in sel if j in set(order[:k + buffer].tolist())]
                    new = [j for j in order.tolist() if j not in set(keep)]
                    sel = (keep + new)[:k]
                else:
                    sel = order[:k].tolist()
                t = np.zeros_like(w); t[sel] = e / k; pending = t; last_e = e
        elif last_e is not None and e != last_e and sel:    # 시장 필터 변화 → 보유 종목 비중만 조정
            cur = w.sum()
            pending = w * (e / cur) if cur > 0 else None
            if cur == 0:
                t = np.zeros_like(w); t[sel] = e / k; pending = t
            last_e = e
    return out, sells


def run(d, U, score, a, b, k=40, every=21, cost_mult=1.0, buffer=0, tranches=1, expo=None):
    ret = d["ret"].fillna(0.0).values
    dates = d["ret"].index
    idx = [i for i in range(len(dates)) if a <= str(dates[i].date()) <= b]
    ev = None if expo is None else expo.reindex(dates).ffill().fillna(1.0).values
    outs, sells = [], []
    for t in range(tranches):
        o, s = _one(ret, U.values, score.values, idx, k, every, int(t * every / tranches), cost_mult, buffer, ev)
        outs.append(o); sells.append(s)
    r = pd.Series(np.mean(outs, axis=0), index=dates[idx])
    return r, float(np.mean(sells)) / (len(idx) / 252)


def stats(r):
    eq = (1 + r).cumprod(); yrs = len(r) / 252
    return {"CAGR": eq.iloc[-1] ** (1 / yrs) - 1, "MDD": (eq / eq.cummax() - 1).min(),
            "샤프": r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else np.nan}


def market_filter(index_close, n=200, low=0.5):
    """코스피가 n일 이동평균 아래면 주식 비중 low, 위면 1.0 (당일 종가로 판정 → 다음 날 체결)"""
    return pd.Series(np.where(index_close < index_close.rolling(n).mean(), low, 1.0), index=index_close.index)
