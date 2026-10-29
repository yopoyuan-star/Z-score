"""從證交所抓加權指數每日開高低收,補進 data/taiex.csv(只新增尚未有的交易日)"""
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone
import pandas as pd

TPE = timezone(timedelta(hours=8))
URLS = ["https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?date={d}&response=json",
        "https://www.twse.com.tw/indicesReport/MI_5MINS_HIST?response=json&date={d}"]


def _num(v):
    return float(str(v).replace(",", ""))


def fetch_month(year, month):
    """回傳該月每日 Open/High/Low/Close(index 為日期);失敗丟例外"""
    err = None
    for u in URLS:
        try:
            req = urllib.request.Request(u.format(d=f"{year}{month:02d}01"), headers={"User-Agent": "Mozilla/5.0"})
            js = json.load(urllib.request.urlopen(req, timeout=30))
            if js.get("stat") != "OK" or not js.get("data"):
                return pd.DataFrame(columns=["Open", "High", "Low", "Close"])      # 該月尚無資料
            f = js["fields"]
            col = lambda key: next(i for i, n in enumerate(f) if key in n)
            ci, co, ch, cl, cc = col("日期"), col("開盤"), col("最高"), col("最低"), col("收盤")
            rows = {}
            for r in js["data"]:
                y, m, d = str(r[ci]).strip().split("/")                        # 民國年 115/10/28
                rows[pd.Timestamp(int(y) + 1911, int(m), int(d))] = (_num(r[co]), _num(r[ch]), _num(r[cl]), _num(r[cc]))
            return pd.DataFrame.from_dict(rows, orient="index", columns=["Open", "High", "Low", "Close"]).sort_index()
        except Exception as e:                                                    # 換下一個網址
            err = e
    raise RuntimeError(f"證交所抓取失敗: {err}")


def update_data(path, retries=0, wait=180):
    """回傳(完整資料, 新增筆數)。平日 13:35 後若今天還沒資料,最多再試 retries 次(每次等 wait 秒)"""
    df = pd.read_csv(path, parse_dates=["Date"]).set_index("Date")
    added = 0
    for attempt in range(retries + 1):
        now = datetime.now(TPE)
        months = {(now.year, now.month), ((now.replace(day=1) - timedelta(days=1)).year, (now.replace(day=1) - timedelta(days=1)).month)}
        new = []
        try:
            for y, m in sorted(months):
                new.append(fetch_month(y, m))
        except Exception as e:
            print("⚠", e, "→ 沿用現有資料")
            break
        add = pd.concat(new) if new else pd.DataFrame()
        if len(add):
            add = add[~add.index.duplicated(keep="last")]
        add = add[(add.index > df.index[-1]) & (add > 0).all(axis=1) & (add.High >= add.Low)] if len(add) else add
        if len(add):
            df = pd.concat([df, add]).sort_index()
            added += len(add)
            print("新增:", ", ".join(f"{i:%Y-%m-%d}={r.Close:,.2f}" for i, r in add.iterrows()))
        today_missing = now.weekday() < 5 and now.hour >= 13 and df.index[-1].date() < now.date()
        if not today_missing or attempt == retries:
            break
        print(f"今天({now:%Y-%m-%d})尚無資料,{wait} 秒後重試({attempt + 1}/{retries})")
        time.sleep(wait)
    if added:
        out = df.copy()
        out.index = out.index.strftime("%Y-%m-%d")
        out.index.name = "Date"
        out.to_csv(path)
    return df, added
