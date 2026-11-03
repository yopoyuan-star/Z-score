"""美元兌新台幣(USD/TWD)近 N 個交易日:Yahoo Finance 公開圖表資料(TWD=X)→ 卡片 HTML(含小走勢圖)。失敗時回傳『暫無資料』卡片,不影響頁面更新。"""
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone

TPE = timezone(timedelta(hours=8))
URLS = ["https://query1.finance.yahoo.com/v8/finance/chart/TWD=X?range=3mo&interval=1d",
        "https://query2.finance.yahoo.com/v8/finance/chart/TWD=X?range=3mo&interval=1d"]
UP, DOWN = "#d9534f", "#2e9e5b"                       # 台股慣例:上漲紅、下跌綠


def parse(js):
    res = js["chart"]["result"][0]
    ts, close = res["timestamp"], res["indicators"]["quote"][0]["close"]
    rows = {}
    for t, c in zip(ts, close):
        if c is None or not (20 < c < 45):            # 去掉缺值與明顯異常的點
            continue
        rows[datetime.fromtimestamp(t, TPE).date()] = float(c)
    return sorted(rows.items())


def fetch(retries=2):
    err = None
    for k in range(retries + 1):
        for u in URLS:
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
                rows = parse(json.load(urllib.request.urlopen(req, timeout=20)))
                if len(rows) >= 5:
                    return rows
            except Exception as e:
                err = e
        time.sleep(3)
    print("匯率抓取失敗:", err)
    return []


def spark(vals, color, w=220, h=44, pad=5):
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    pts = [(pad + i * (w - 2 * pad) / (len(vals) - 1), pad + (hi - v) / span * (h - 2 * pad)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    x, y = pts[-1]
    return (f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" style="width:100%;height:{h}px;display:block;margin-top:6px" role="img" aria-label="美元兌台幣近 {len(vals)} 個交易日走勢">'
            f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>'
            f'<path d="M{x:.1f} {y:.1f}h0" stroke="{color}" stroke-width="7" stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg>')


def card(n=20):
    """回傳 (標題, 內容 HTML);以及原始資料列表(供 LINE 日報使用)。"""
    title = "美元兌台幣 USD/TWD"
    rows = fetch()[-n:]
    if len(rows) < 2:
        return (title, "—<small>暫時無法取得匯率資料,下次更新會再試</small>"), []
    vals = [v for _, v in rows]
    last, prev = vals[-1], vals[-2]
    chg = last - prev
    col = UP if chg > 0 else DOWN if chg < 0 else "inherit"
    arrow = "▲" if chg > 0 else "▼" if chg < 0 else "－"
    html = (f"{last:.3f}"
            f"<small style='color:{col};font-size:14px;font-weight:600'>{arrow} {abs(chg):.3f}　({chg / prev:+.2%})</small>"
            f"{spark(vals, col if chg else '#888')}"
            f"<small>近 {len(vals)} 日 {rows[0][0]:%m/%d}~{rows[-1][0]:%m/%d}|高 {max(vals):.3f}・低 {min(vals):.3f}</small>"
            f"<small>數字上升 = 台幣貶值</small>")
    return (title, html), rows


BLOCKS = "▁▂▃▄▅▆▇█"


def summary(rows):
    """LINE 用:最新匯率、漲跌、文字小走勢(▁▂▃…)、區間高低。rows 為 [(date, close), ...];無資料回傳 None。"""
    if len(rows) < 2:
        return None
    vals = [v for _, v in rows]
    lo, hi = min(vals), max(vals)
    spark = "".join(BLOCKS[min(7, int((v - lo) / ((hi - lo) or 1) * 8))] for v in vals)
    last, prev = vals[-1], vals[-2]
    chg = last - prev
    arrow = "▲" if chg > 0 else "▼" if chg < 0 else "－"
    d = dict(last=last, chg=chg, pct=chg / prev, arrow=arrow, spark=spark, lo=lo, hi=hi, d0=f"{rows[0][0]:%m/%d}", d1=f"{rows[-1][0]:%m/%d}", n=len(vals))
    d["text"] = f"美元兌台幣 {last:.3f}  {arrow} {abs(chg):.3f}({chg / prev:+.2%})\n    近{len(vals)}日 {spark}  高 {hi:.3f}|低 {lo:.3f}"
    return d
