"""重現 Z-SCORE 模型「480天Z-SCORE -2.0」工作表的欄位,以及日/週/月「動態」KD(已與 Excel 數值逐一核對)。
動態 KD:以最新一天為終點,每 5 個交易日(週)/22 個交易日(月)合成一根 K 棒,KD 取 9 根,
K=2/3×K前+1/3×RSV、D=2/3×D前+1/3×K。K 合理低/高檔 = 近 N 根 K 值平均 ∓ 倍數×標準差。"""
import numpy as np
import pandas as pd

W_BAR, M_BAR, W_WINDOW = 5, 22, 1400     # 週 K=5 日、月 K=22 日;週 KD 只取最近 1400 個交易日(同 Excel)
KD_N, KD_SEED = 9, 50.0
THR = {"日": (120, 1.0), "週": (59, 1.2), "月": (35, 1.0)}   # (取樣根數, 倍數),與 Excel 日KD/週kd/月kd-36 一致


def _kd(h, l, c):
    hh = pd.Series(h).rolling(KD_N, min_periods=1).max().to_numpy()
    ll = pd.Series(l).rolling(KD_N, min_periods=1).min().to_numpy()
    rsv = np.where(hh > ll, (c - ll) / np.where(hh > ll, hh - ll, 1) * 100, 50.0)
    k, d, pk, pdv = np.empty(len(c)), np.empty(len(c)), KD_SEED, KD_SEED
    for i, r in enumerate(rsv):
        pk = 2 / 3 * pk + r / 3
        pdv = 2 / 3 * pdv + pk / 3
        k[i], d[i] = pk, pdv
    return k, d


def dynamic_kd(df, bar, window=None, upto=None, kind="週"):
    """以第 upto 列(含)為最新一天,回傳 K、D、黃金/死亡交叉狀態、K 合理低/高檔與位階"""
    x = df if upto is None else df.iloc[:upto]
    if window:
        x = x.iloc[-window:]
    n = (len(x) // bar) * bar
    x = x.iloc[len(x) - n:]
    h, l, c = (x[col].to_numpy().reshape(-1, bar) for col in ("High", "Low", "Close"))
    k, d = _kd(h.max(1), l.min(1), c[:, -1])
    w, f = THR[kind]
    s = pd.Series(k).iloc[-w:]
    lo, hi = s.mean() - f * s.std(), s.mean() + f * s.std()
    state = "黃金交叉" if k[-1] > d[-1] else "死亡交叉" if k[-1] < d[-1] else ""
    zone = "K值高檔" if k[-1] > hi else "K值低檔" if k[-1] < lo else ""
    return dict(K=k[-1], D=d[-1], state=state, low=lo, high=hi, zone=zone)


def kd_now(df):
    return {"日": dynamic_kd(df, 1, None, kind="日"),
            "週": dynamic_kd(df, W_BAR, W_WINDOW, kind="週"),
            "月": dynamic_kd(df, M_BAR, None, kind="月")}


def kd_log(df, days):
    """最近 days 天,每天以「當天為終點」的動態週/月 KD(對應 Excel 貼在 BG/BH 的紀錄)"""
    rows = []
    for i in range(len(df) - days, len(df)):
        w = dynamic_kd(df, W_BAR, W_WINDOW, i + 1, "週")
        m = dynamic_kd(df, M_BAR, None, i + 1, "月")
        rows.append((df.index[i], w["K"], w["D"], w["state"], w["low"], w["high"], m["K"], m["D"], m["state"], m["low"], m["high"]))
    return pd.DataFrame(rows, columns=["Date", "週K", "週D", "週KD", "週K低檔", "週K高檔", "月K", "月D", "月KD", "月K低檔", "月K高檔"]).set_index("Date")


def zscore_model(df):
    c = df.Close
    out = pd.DataFrame(index=df.index)
    out["開盤價"], out["最高價"], out["最低價"], out["台股收盤價"] = df.Open, df.High, df.Low, c
    for n in (20, 40, 60, 80, 200, 240):
        out[f"{n}日均線"] = c.rolling(n).mean()
    ma60, ma200, ma240 = out["60日均線"], out["200日均線"], out["240日均線"]
    out["生命線60*3%"] = np.where(c > ma60 * 1.03, "多", np.where(c < ma60 * 0.97, "空", ""))
    out["BUY(200日)2%"] = np.where(c > ma200 * 1.02, "BUY", "")
    out["SELL(200日)1%"] = np.where(c < ma200 * 0.99, "SELL", "")
    out["季線乖離"], out["年線乖離"] = (c - ma60) / ma60, (c - ma240) / ma240
    m5 = c.rolling(1100).mean()
    out["5年線乖離%"] = (c - m5) / m5
    out["5-AVG"], out["5-STD"] = out["5年線乖離%"].rolling(660).mean(), out["5年線乖離%"].rolling(660).std()
    m10 = c.rolling(2200).mean()
    out["10年線乖離%"] = (c - m10) / m10
    out["10-AVG"], out["10-STD"] = out["10年線乖離%"].rolling(660).mean(), out["10年線乖離%"].rolling(660).std()
    out["480天平均"] = c.rolling(480).mean()
    z = (c - out["480天平均"]) / c.rolling(480).std()
    out["Z-SCORE"] = z
    out["Z低檔"] = z.rolling(200).mean() - 1.2 * z.rolling(200).std()
    out["Z高檔"] = z.rolling(200).mean() + 1.2 * z.rolling(200).std()
    out["Z方向"] = np.where(z > z.shift(), "↑", "↓")
    med = c.rolling(481).median()
    dist = (c - med).abs()
    out["中位數"], out["每筆資料與中位數的距離"] = med, dist
    out["算距離的中位數"] = dist.rolling(480).median()
    mad = 0.6745 * (c - med) / out["算距離的中位數"]
    out["MAD ZSCORE"] = mad
    out["MAD 低檔"] = mad.rolling(200).mean() - 1.2 * mad.rolling(200).std()
    out["MAD 高檔"] = mad.rolling(200).mean() + 1.2 * mad.rolling(200).std()
    wins = [5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 120, 150, 180]
    for w in wins:
        out[f"{w}天 Z-SCORE"] = z.rolling(w).mean()
    for a, b in zip(wins[:-1], wins[1:]):
        out[f"{a}>{b}天Z"] = np.where(out[f"{a}天 Z-SCORE"] > out[f"{b}天 Z-SCORE"], "BUY", "")
    return out
