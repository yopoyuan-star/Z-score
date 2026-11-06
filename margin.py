"""近 5 日:證交所全市場擔保維持率(官方整戶)與上市櫃融資維持率(財經M平方 MacroMicro 圖表 53117)→ 收盤價卡片下方的小表。
來源 https://macromicro.me/charts/53117/taiwan-taiex-maintenance-margin
抓成功就存 data/margin.csv;抓失敗改用上次存的資料(標示『舊資料』);網站擋 GitHub 主機時,網頁上有『貼上資料』備援(存在瀏覽器)。"""
import csv
import json
import os
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone

CHART_ID = 53117
URLS = [f"https://www.macromicro.me/charts/data/{CHART_ID}", f"https://macromicro.me/charts/data/{CHART_ID}"]
PAGE = f"https://www.macromicro.me/charts/{CHART_ID}/taiwan-taiex-maintenance-margin"
STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "margin.csv")
TPE = timezone(timedelta(hours=8))
OK = lambda v: isinstance(v, (int, float)) and 80 <= v <= 400            # 維持率的合理範圍(排除指數 4 萬點、券資比 2 之類)


def _pairs(node):
    """node 若是 [[日期, 數值], ...] 就回傳 {date: value}"""
    if isinstance(node, list) and len(node) > 5 and all(isinstance(x, (list, tuple)) and len(x) >= 2 for x in node[-3:]):
        out = {}
        for x in node:
            try:
                out[datetime.strptime(str(x[0])[:10], "%Y-%m-%d").date()] = float(x[1])
            except Exception:
                return None
        return out
    return None


def parse(js):
    """彈性解析 MacroMicro 圖表資料 JSON:找出所有『日期-數值』序列;依名稱(含「擔保」/「融資維持」)判斷,
    找不到名稱就依數值範圍(80~400)與圖例順序(證交所擔保 → 上市櫃融資 → 加權指數)。回傳 {date: (擔保, 融資)}"""
    found = []                                                   # (名稱, {date: val})

    def walk(n, name=""):
        p = _pairs(n)
        if p is not None:
            found.append((name, p))
            return
        if isinstance(n, dict):
            nm = next((str(n[k]) for k in ("name_tc", "name", "name_zh", "title", "name_en") if isinstance(n.get(k), str)), name)
            for v in n.values():
                walk(v, nm)
        elif isinstance(n, list):
            for v in n:
                walk(v, name)

    walk(js)
    cand = [(nm, s) for nm, s in found if s and OK(list(s.values())[-1])]
    g = next((s for nm, s in cand if "擔保" in nm), None)
    m = next((s for nm, s in cand if "融資" in nm and "擔保" not in nm), None)
    rest = [s for nm, s in cand if s is not g and s is not m]
    if g is None and rest:
        g = rest.pop(0)
    if m is None and rest:
        m = rest.pop(0)
    if g is None and m is None:
        return {}
    dates = sorted(set((g or {}).keys()) | set((m or {}).keys()))
    return {d: ((g or {}).get(d), (m or {}).get(d)) for d in dates}


def fetch(retries=2):
    err = None
    for _ in range(retries + 1):
        for u in URLS:
            try:
                req = urllib.request.Request(u, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                    "Accept": "application/json, text/plain, */*", "Accept-Language": "zh-TW,zh;q=0.9",
                    "Referer": PAGE, "X-Requested-With": "XMLHttpRequest"})
                data = parse(json.load(urllib.request.urlopen(req, timeout=30)))
                if len(data) >= 3:
                    return data
                err = "資料格式解析不到維持率序列"
            except Exception as e:
                err = e
        time.sleep(3)
    print("維持率抓取失敗(財經M平方):", err)
    return {}


def load():
    out = {}
    try:
        with open(STORE, encoding="utf-8") as f:
            for r in csv.reader(f):
                if len(r) >= 3:
                    out[datetime.strptime(r[0], "%Y-%m-%d").date()] = (float(r[1]) if r[1] else None, float(r[2]) if r[2] else None)
    except Exception:
        pass
    return out


def save(data):
    try:
        old = load()
        old.update(data)
        os.makedirs(os.path.dirname(STORE), exist_ok=True)
        with open(STORE, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            for d, (g, m) in sorted(old.items())[-60:]:
                w.writerow([d.isoformat(), "" if g is None else g, "" if m is None else m])
    except Exception as e:
        print("維持率存檔失敗:", e)


def get(fetcher=fetch):
    """回傳 (近 5 日 [(date, 擔保, 融資)], 是否舊資料)"""
    data = fetcher()
    if data:
        save(data)
        merged = load() or data
        return [(d, *merged[d]) for d in sorted(merged)[-5:]], False
    old = load()
    return [(d, *old[d]) for d in sorted(old)[-5:]], True


def _cell(v, prev):
    if v is None:
        return "<em>—</em>"
    col = "#d9534f" if v < 130 else "#c98a00" if v < 145 else "inherit"        # <130 追繳線 紅;<145 注意 黃
    ch = ""                                                                   # 卡片寬度有限,不顯示增減
    return f"<em style='color:{col}'>{v:.2f}%{ch}</em>"


def _rows_html(rows, stale=False):
    if not rows:
        return "<small style='margin-top:8px'>維持率:暫無資料</small>"
    head = ("<div style='margin-top:10px;font-size:12px;color:var(--mut)'>融資維持率(財經M平方)" + ("・舊資料" if stale else "") + "</div>"
            "<div class=lvr2 style='grid-template-columns:3em 1fr 1fr;font-size:11px;color:var(--mut)'><span>日期</span><em style='font-weight:400'>全市場擔保</em><em style='font-weight:400'>上市櫃融資</em></div>")
    out = [head]
    for i in range(len(rows) - 1, -1, -1):
        d, g, m = rows[i]
        pg = rows[i - 1][1] if i else None
        pm = rows[i - 1][2] if i else None
        out.append(f"<div class=lvr2 style='grid-template-columns:3em 1fr 1fr;font-size:12px'><span>{d:%m/%d}</span>{_cell(g, pg)}{_cell(m, pm)}</div>")
    return "".join(out)


def html(rows, stale=False):
    last = rows[-1][0].isoformat() if rows else ""
    return (f"<div id=mgn data-last='{last}'><div id=mgnrows>{_rows_html(rows, stale)}</div>"
            "<details style='margin-top:6px;font-size:11px;color:var(--mut)'><summary style='cursor:pointer'>貼上維持率資料</summary>"
            "<textarea id=mpaste rows=3 placeholder='自動抓不到時:到財經M平方圖表複製資料(每行 日期 擔保維持率 融資維持率),貼在這裡' "
            "style='width:100%;box-sizing:border-box;font-size:11px;margin-top:4px;background:transparent;color:inherit;border:1px solid var(--mut);border-radius:6px'></textarea></details></div>")
