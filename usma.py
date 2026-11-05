"""美股四大指數 MA 通道狀態(道瓊/S&P500/那斯達克/費半)→ 一張卡片。
規則與 MA200-240 頁相同:收盤連續 3 天 > MA×1.02 → 買進;連續 3 天 < MA×0.99 → 賣出。抓不到資料時顯示『暫無資料』。"""
import json
import time
import urllib.request
import pandas as pd

INDICES = [("道瓊", "%5EDJI", 220), ("S&P 500", "%5EGSPC", 220), ("那斯達克", "%5EIXIC", 240), ("費半 SOX", "%5ESOX", 220)]
UP_BAND, DN_BAND, DAYS = 0.02, 0.01, 3
UP, DOWN = "#d9534f", "#2e9e5b"


def fetch(sym, retries=2):
    err = None
    for _ in range(retries + 1):
        for host in ("query1", "query2"):
            try:
                url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}?range=3y&interval=1d"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                r = json.load(urllib.request.urlopen(req, timeout=30))["chart"]["result"][0]
                s = pd.Series(r["indicators"]["quote"][0]["close"], dtype=float,
                              index=pd.to_datetime(r["timestamp"], unit="s").normalize())
                s = s[~s.index.duplicated(keep="last")].dropna()
                if len(s) > 300:
                    return s
            except Exception as e:
                err = e
        time.sleep(3)
    print("美股抓取失敗", sym, err)
    return None


def streak(f):
    return f.groupby((~f).cumsum()).cumsum()


def analyze(close, n):
    ma = close.rolling(n).mean()
    ua, ub = streak(close > ma * (1 + UP_BAND)), streak(close < ma * (1 - DN_BAND))
    sig = pd.Series("", index=close.index)
    sig[ua == DAYS], sig[ub == DAYS] = "買進", "賣出"
    sg = sig[sig != ""]
    return dict(date=close.index[-1], close=close.iloc[-1], ma=ma.iloc[-1], dev=close.iloc[-1] / ma.iloc[-1] - 1,
                ua=int(ua.iloc[-1]), ub=int(ub.iloc[-1]), n=n,
                sig=sg.iloc[-1] if len(sg) else "", sig_date=sg.index[-1] if len(sg) else None)


def card(fetcher=fetch):
    """回傳 (標題, html)"""
    rows, latest = [], None
    for name, sym, n in INDICES:
        s = fetcher(sym)
        if s is None or len(s) < n + 10:
            rows.append(f"<div class=usr><b>{name}</b><small>暫無資料</small></div>")
            continue
        a = analyze(s, n)
        latest = a["date"] if latest is None or a["date"] > latest else latest
        col = UP if a["dev"] >= 0 else DOWN
        state = (f"連續 {a['ua']} 天站上 MA+{UP_BAND:.0%}" if a["ua"] else
                 f"連續 {a['ub']} 天跌破 MA-{DN_BAND:.0%}" if a["ub"] else "通道內")
        sc = (UP if a["sig"] == "買進" else DOWN) if a["sig"] else "inherit"
        last = f"最近訊號 <i style='font-style:normal;color:{sc};font-weight:700'>{a['sig']}</i> {a['sig_date']:%Y-%m-%d}" if a["sig"] else "近三年無訊號"
        rows.append(f"<div class=usr><b>{name}</b><em style='color:{col}'>{a['dev'] * 100:+.2f}%</em>"
                    f"<small>收盤 {a['close']:,.2f}｜MA{n} {a['ma']:,.2f}</small><small>{state}</small><small>{last}</small></div>")
    title = "美股 MA 通道" + (f"(收盤日 {latest:%Y-%m-%d})" if latest is not None else "")
    return title, "".join(rows)
