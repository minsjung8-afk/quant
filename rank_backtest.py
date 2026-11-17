"""순위 기반 포트폴리오 백테스트: N거래일마다 점수 상위 K종목 동일비중 보유.
신호는 리밸런싱일 종가로 판정, 체결은 다음 거래일 종가. 비용 = 교체 금액 × (편도 비용)."""
import numpy as np, pandas as pd

BUY_COST = 0.00015 + 0.0005            # 수수료 + 슬리피지
SELL_COST = 0.00015 + 0.0005 + 0.0020  # + 거래세(가정값)


def run(d, U, score, a, b, k=40, every=21, cost_mult=1.0, buffer=0):
    """buffer>0 이면 기존 보유 종목은 순위 k+buffer 안에 있는 동안 유지(회전율 축소)"""
    ret = d["ret"].fillna(0.0).values
    dates = d["ret"].index
    Uv, S = U.values, score.values
    idx = [i for i in range(len(dates)) if a <= str(dates[i].date()) <= b]
    w = np.zeros(ret.shape[1]); pending = None
    out, turns, held = [], [], []
    for n, i in enumerate(idx):
        r = float(w @ ret[i])                      # 오늘 수익 (어제까지의 비중)
        w = w * (1 + ret[i])
        cost = 0.0
        if pending is not None:                    # 어제 판정한 목표를 오늘 종가에 체결
            gross = w.sum() if w.sum() > 0 else 1.0
            cur = w / gross if w.sum() > 0 else w
            tgt = pending
            buy, sell = np.clip(tgt - cur, 0, None).sum(), np.clip(cur - tgt, 0, None).sum()
            cost = (buy * BUY_COST + sell * SELL_COST) * cost_mult
            turns.append(sell); w = tgt.copy(); pending = None
        else:
            if w.sum() > 0: w = w / w.sum()
        out.append(r - cost)
        if n % every == 0:
            m = Uv[i] & np.isfinite(S[i])
            if m.sum() >= k:
                order = np.argsort(-np.where(m, S[i], -np.inf))
                top = set(order[:k])
                if buffer:
                    keep = set(np.nonzero(w > 0)[0]) & set(order[:k + buffer])
                    sel = list(keep)[:k]
                    for j in order:
                        if len(sel) >= k: break
                        if j not in keep: sel.append(j)
                    top = set(sel)
                t = np.zeros_like(w); t[list(top)] = 1.0 / len(top); pending = t
        held.append(int((w > 0).sum()))
    r = pd.Series(out, index=dates[idx])
    return r, (np.sum(turns) / (len(idx) / 252) if turns else 0.0)


def stats(r):
    eq = (1 + r).cumprod(); yrs = len(r) / 252
    return {"CAGR": eq.iloc[-1] ** (1 / yrs) - 1, "MDD": (eq / eq.cummax() - 1).min(),
            "샤프": r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else np.nan}
