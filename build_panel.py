"""raw_krx/ → panel/ (날짜×종목 행렬). 수정주가는 KRX 기준가(종가-대비)로 일별 수익률을 구해 연결한다.
사용: python3 build_panel.py [기준일 YYYYMMDD(이 날짜까지)]"""
import os, sys, glob, gzip, io
import numpy as np, pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
ASOF = sys.argv[1] if len(sys.argv) > 1 else "99999999"
num = ["TDD_OPNPRC", "TDD_HGPRC", "TDD_LWPRC", "TDD_CLSPRC", "CMPPREVDD_PRC", "ACC_TRDVOL", "ACC_TRDVAL", "MKTCAP"]
cols = {"date": [], "code": [], "mk": []}
arrs = {k: [] for k in num}
names = {}
for mk in ("KOSPI", "KOSDAQ"):
    for f in sorted(glob.glob(os.path.join(BASE, "raw_krx", mk, "*.csv.gz"))):
        ymd = os.path.basename(f)[:8]
        if ymd > ASOF: continue
        d = pd.read_csv(f, dtype=str, usecols=["ISU_CD", "ISU_NM"] + num)
        cols["date"].append(np.full(len(d), int(ymd), dtype=np.int32))
        cols["code"].append(d["ISU_CD"].values)
        cols["mk"].append(np.full(len(d), mk == "KOSDAQ", dtype=bool))
        for k in num:
            arrs[k].append(pd.to_numeric(d[k].str.replace(",", ""), errors="coerce").values.astype("float64"))
        names.update(zip(d["ISU_CD"].values, d["ISU_NM"].values))
df = pd.DataFrame({"date": np.concatenate(cols["date"]), "code": pd.Categorical(np.concatenate(cols["code"])),
                   "kosdaq": np.concatenate(cols["mk"]), **{k: np.concatenate(v) for k, v in arrs.items()}})
del cols, arrs
df["date"] = pd.to_datetime(df["date"].astype(str))
df = df.rename(columns={"TDD_OPNPRC": "o", "TDD_HGPRC": "h", "TDD_LWPRC": "l",
                        "TDD_CLSPRC": "c", "CMPPREVDD_PRC": "chg", "ACC_TRDVOL": "vol", "ACC_TRDVAL": "val", "MKTCAP": "mcap"})
df = df[df.c > 0].drop_duplicates(["date", "code"])
for k in ("o", "h", "l"):
    df[k] = df[k].where(df[k] > 0, df.c)
base = df.c - df.chg.fillna(0)
df["ret"] = np.where(base > 0, df.c / base - 1, 0.0)
print(f"행 {len(df):,}, 종목 {df.code.nunique():,}, 기간 {df.date.min().date()} ~ {df.date.max().date()}")

dates = np.sort(df.date.unique()); codes = df.code.cat.remove_unused_categories().cat.categories
ri = np.searchsorted(dates, df.date.values); ci = df.code.cat.remove_unused_categories().cat.codes.values
def W(col):
    m = np.full((len(dates), len(codes)), np.nan, dtype="float64")
    m[ri, ci] = df[col].values
    return pd.DataFrame(m, index=pd.DatetimeIndex(dates, name="date"), columns=codes)
ret, c = W("ret"), W("c")
listed = c.notna()
# 첫 관측일 수익률은 0 (상장 첫날 공모가 대비 등락은 잡을 수 없는 수익)
first = listed & ~listed.shift(1, fill_value=False)
ret = ret.mask(first, 0.0)
# 수정계수: 마지막 관측 종가에 맞춰 역산 (adj_c[t] = c_last / prod(1+ret after t))
logr = np.log1p(ret.fillna(0.0).clip(lower=-0.999))
cum = logr.cumsum()
last_idx = listed[::-1].idxmax()                       # 종목별 마지막 관측일
cum_last = pd.Series({k: cum.at[last_idx[k], k] for k in c.columns})
c_last = pd.Series({k: c.at[last_idx[k], k] for k in c.columns})
adj_c = np.exp(cum.sub(cum_last, axis=1)).mul(c_last, axis=1).where(listed)
f = adj_c / c
os.makedirs(os.path.join(BASE, "panel"), exist_ok=True)
def save(k, v): v.astype("float32").to_pickle(os.path.join(BASE, "panel", k + ".pkl"))
save("ret", ret); save("c", adj_c); save("raw_c", c)
del ret, cum, logr
for k in ("o", "h", "l"): save(k, W(k) * f)
save("val", W("val")); save("mcap", W("mcap")); save("vol", W("vol") / f)
g = df.groupby("code", observed=True)
meta = pd.DataFrame({"name": pd.Series(names), "kosdaq": g.kosdaq.last(), "first": g.date.min(), "last": g.date.max()}).dropna(subset=["first"])
meta["mk"] = np.where(meta.kosdaq, "KOSDAQ", "KOSPI")
meta.to_pickle(os.path.join(BASE, "panel", "meta.pkl"))
print("상장폐지(마지막 관측일이 최종일 이전) 종목:", int((meta["last"] < df.date.max()).sum()))
