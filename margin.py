"""大盤融資維持率(玩股網,扣除 ETF)近 5 日 → 收盤價卡片下方的小表。
來源:https://www.wantgoo.com/stock/margin-trading/exclude-etf/taiex 表格的「維持率」欄(玩股網估算值,非證交所官方『整戶擔保維持率』)。
抓成功就存 data/margin.csv;抓失敗改用上次存的資料(標示『舊資料』);都沒有則顯示『暫無資料』。"""
import csv
import os
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone

URL = "https://www.wantgoo.com/stock/margin-trading/exclude-etf/taiex"
STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "margin.csv")
TPE = timezone(timedelta(hours=8))


def parse(html):
    """從表格列取 (日期, 維持率%);日期 11/04 或 2026/11/04,維持率取該列第一個 80~400 之間、帶 % 的數字"""
    out = {}
    year = datetime.now(TPE).year
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        cells = [re.sub(r"<[^>]+>|&nbsp;", "", c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        if not cells:
            continue
        m = re.fullmatch(r"(?:(\d{4})/)?(\d{1,2})/(\d{1,2})", cells[0])
        if not m:
            continue
        y, mo, d = int(m.group(1) or year), int(m.group(2)), int(m.group(3))
        val = None
        for c in cells[1:]:
            mm = re.fullmatch(r"(\d{2,3}(?:\.\d+)?)\s*%", c)
            if mm and 80 <= float(mm.group(1)) <= 400:
                val = float(mm.group(1))
                break
        if val is None:
            continue
        dt = datetime(y, mo, d).date()
        if dt > datetime.now(TPE).date():                      # 年底跨年:12/xx 出現在 1 月 → 屬於去年
            dt = datetime(y - 1, mo, d).date()
        out[dt] = val
    return sorted(out.items())


def fetch(retries=2):
    err = None
    for _ in range(retries + 1):
        try:
            req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                                                       "Accept-Language": "zh-TW,zh;q=0.9", "Referer": "https://www.wantgoo.com/"})
            html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
            rows = parse(html)
            if len(rows) >= 3:
                return rows
            err = f"表格解析不到資料(頁面長度 {len(html)},可能為動態載入或被擋)"
        except Exception as e:
            err = e
        time.sleep(3)
    print("融資維持率抓取失敗:", err)
    return []


def load():
    try:
        with open(STORE, encoding="utf-8") as f:
            return sorted((datetime.strptime(r[0], "%Y-%m-%d").date(), float(r[1])) for r in csv.reader(f) if r)
    except Exception:
        return []


def save(rows):
    try:
        old = dict(load())
        old.update(dict(rows))
        os.makedirs(os.path.dirname(STORE), exist_ok=True)
        with open(STORE, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            for d, v in sorted(old.items())[-60:]:
                w.writerow([d.isoformat(), v])
    except Exception as e:
        print("融資維持率存檔失敗:", e)


def get(fetcher=fetch):
    """回傳 (近5日 [(date, val)], 是否為舊資料)"""
    rows = fetcher()
    if rows:
        save(rows)
        return sorted(dict(load()).items())[-5:] if os.path.exists(STORE) else rows[-5:], False
    old = load()
    return old[-5:], True


def html(rows, stale=False):
    if not rows:
        return "<small style='margin-top:8px'>融資維持率:暫無資料</small>"
    out = ["<div style='margin-top:10px;font-size:12px;color:var(--mut)'>融資維持率(玩股網)" + ("・舊資料" if stale else "") + "</div>"]
    for i, (d, v) in enumerate(reversed(rows)):
        j = len(rows) - 1 - i
        chg = f"<i style='font-style:normal;font-size:11px;color:var(--mut)'>{'▲' if v > rows[j - 1][1] else '▼' if v < rows[j - 1][1] else '－'}{abs(v - rows[j - 1][1]):.2f}</i>" if j > 0 else ""
        col = "#d9534f" if v < 130 else "#c98a00" if v < 145 else "inherit"        # <130 追繳線 紅;<145 注意 黃
        out.append(f"<div class=lvr2 style='grid-template-columns:3.2em 1fr 3.6em'><span>{d:%m/%d}</span><em style='color:{col}'>{v:.2f}%</em>{chg}</div>")
    return "".join(out)
