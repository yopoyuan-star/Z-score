"""三大法人買賣超(證交所 BFI82U)+ 外資台指期未平倉淨口數(期交所 OpenAPI)→ 卡片 HTML。
任何一段抓失敗都只顯示『暫無資料』,不影響頁面更新。"""
import json
import urllib.request
from datetime import datetime, timedelta, timezone

TPE = timezone(timedelta(hours=8))
UP, DOWN = "#d9534f", "#2e9e5b"                       # 台股慣例:買超/多方紅、賣超/空方綠
UA = {"User-Agent": "Mozilla/5.0"}
TWSE = "https://www.twse.com.tw/rwd/zh/fund/BFI82U?type=day&dayDate={d}&response=json"
TAIFEX_OI = "https://openapi.taifex.com.tw/v1/DailyMarketReportFut"
TAIFEX = "https://openapi.taifex.com.tw/v1/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate"


def _get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20))


def _num(x):
    try:
        return float(str(x).replace(",", "").replace("+", "").strip())
    except Exception:
        return None


def parse_twse(js):
    """回傳 (日期字串 YYYYMMDD, {'外資':億元,'投信':億元,'自營商':億元,'合計':億元});非交易日回 None。"""
    if not js or js.get("stat") != "OK" or not js.get("data"):
        return None
    out = {"外資": 0.0, "投信": 0.0, "自營商": 0.0}
    total = None
    for r in js["data"]:
        name, diff = str(r[0]), _num(r[-1])
        if diff is None:
            continue
        if name.startswith("外資"):
            out["外資"] += diff
        elif name.startswith("投信"):
            out["投信"] += diff
        elif name.startswith("自營商"):
            out["自營商"] += diff
        elif name.startswith("合計"):
            total = diff
    out = {k: v / 1e8 for k, v in out.items()}
    out["合計"] = (total if total is not None else sum(out.values()) * 1e8) / 1e8
    return str(js.get("date", "")), out


def fetch_twse(back=7):
    d = datetime.now(TPE)
    for i in range(back):
        day = d - timedelta(days=i)
        if day.weekday() >= 5:
            continue
        try:
            got = parse_twse(_get(TWSE.format(d=f"{day:%Y%m%d}")))
            if got:
                return got
        except Exception as e:
            print("三大法人抓取失敗:", e)
    return None


def _pick(row, *must, none=()):
    for k, v in row.items():
        lk = str(k).lower()
        if all(m in lk for m in must) and not any(n in lk for n in none):
            return _num(v)
    return None


def _first(*vals):
    return next((v for v in vals if v is not None), None)


def parse_taifex(rows):
    """找『臺股期貨』×『外資及陸資』那一列 → (日期, 淨口數, 多, 空)。欄位名稱以關鍵字容錯比對。"""
    for r in rows or []:
        vals = [str(v) for v in r.values()]
        if not any("外資" in v for v in vals):
            continue
        if not any(v.strip() in ("臺股期貨", "台股期貨", "TX", "TXF") for v in vals):
            continue
        net = _first(_pick(r, "openinterest", "net", none=("value", "amount")), _pick(r, "未平倉", "淨額", "口數", none=("金額",)))
        lg = _first(_pick(r, "openinterest", "long", none=("value", "amount")), _pick(r, "未平倉", "多方", "口數", none=("金額",)))
        sh = _first(_pick(r, "openinterest", "short", none=("value", "amount")), _pick(r, "未平倉", "空方", "口數", none=("金額",)))
        date = next((str(v) for k, v in r.items() if str(k).lower() in ("date", "日期")), "")
        if net is None and lg is not None and sh is not None:
            net = lg - sh
        if net is not None:
            return date, net, lg, sh
    return None


def fetch_taifex():
    try:
        rows = _get(TAIFEX)
        got = parse_taifex(rows)
        if not got:
            print("外資期貨解析不到;樣本欄位:", list(rows[0].keys()) if rows else rows)
        return got
    except Exception as e:
        print("外資期貨抓取失敗:", e)
        return None


MTX = ("小型臺指期貨", "小型台指期貨", "MTX")


def parse_retail(inst_rows, mkt_rows):
    """散戶多空比 = −(三大法人小台淨未平倉) ÷ 小台全市場未平倉 → (日期, 比值%, 散戶淨口數, 全市場未平倉)。"""
    net, date, seen = 0.0, "", 0
    for r in inst_rows or []:
        vals = [str(v).strip() for v in r.values()]
        if not any(v in MTX for v in vals):
            continue
        if not any(("外資" in v or "投信" in v or "自營" in v) for v in vals):
            continue
        n = _first(_pick(r, "openinterest", "net", none=("value", "amount")), _pick(r, "未平倉", "淨額", "口數", none=("金額",)))
        if n is None:
            continue
        net += n
        seen += 1
        date = date or next((str(v) for k, v in r.items() if str(k).lower() in ("date", "日期")), "")
    oi = 0.0
    for r in mkt_rows or []:
        vals = [str(v).strip() for v in r.values()]
        if not any(v in MTX for v in vals):
            continue
        month = next((str(v) for k, v in r.items() if "month" in str(k).lower() or "到期" in str(k)), "")
        if "/" in month:                               # 跨月價差單不算
            continue
        o = _first(_pick(r, "openinterest", none=("value", "amount")), _pick(r, "未結算", "契約"), _pick(r, "未平倉"))
        if o:
            oi += o
    if seen < 3 or oi <= 0:
        return None
    return date, -net / oi * 100, -net, oi


def fetch_retail():
    try:
        got = parse_retail(_get(TAIFEX), _get(TAIFEX_OI))
        if not got:
            print("散戶多空比解析不到(小台法人或全市場未平倉欄位對不上)")
        return got
    except Exception as e:
        print("散戶多空比抓取失敗:", e)
        return None


def fmt_date(s):
    s = str(s).replace("/", "").replace("-", "")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else s


def col(v):
    return UP if v > 0 else DOWN if v < 0 else "inherit"


def sec(color, label, body):
    return f"<div class=zsec style='border-left-color:{color}'><i class=zlab style='color:{color}'>{label}</i>{body}</div>"


def fetch():
    return fetch_twse(), fetch_taifex(), fetch_retail()


def html(data=None):
    tw, fu, rt = data if data else fetch()
    if tw:
        d, o = tw
        cells = "".join(
            f"<div style='display:flex;justify-content:space-between;font-size:15px;font-weight:700'><span style='color:var(--fg)'>{k}</span>"
            f"<span style='color:{col(o[k])}'>{o[k]:+,.1f} 億</span></div>" for k in ("外資", "投信", "自營商"))
        tot = f"<div style='display:flex;justify-content:space-between;font-size:15px;font-weight:800;border-top:1px solid var(--mut);margin-top:2px;padding-top:2px'><span>合計</span><span style='color:{col(o['合計'])}'>{o['合計']:+,.1f} 億</span></div>"
        body = f"{cells}{tot}<small>買超紅 / 賣超綠|資料日 {fmt_date(d)}</small>"
    else:
        body = "<small>暫時無法取得,下次更新會再試</small>"
    a = sec("#00838f", "三大法人買賣超", body)
    if fu:
        d, net, lg, sh = fu
        ls = f"<small>多 {lg:,.0f}｜空 {sh:,.0f} 口</small>" if lg is not None and sh is not None else ""
        body = f"<span style='display:block;font-size:22px;font-weight:700;color:{col(net)}'>{net:+,.0f} 口</span>{ls}<small>臺股期貨・淨未平倉(多−空)|資料日 {fmt_date(d)}</small>"
    else:
        body = "<small>暫時無法取得,下次更新會再試</small>"
    b = sec("#5d4037", "外資台指期未平倉", body)
    if rt:
        d, pct, net, oi = rt
        body = (f"<span style='display:block;font-size:22px;font-weight:700;color:{col(pct)}'>{pct:+.1f}%</span>"
                f"<small>散戶淨 {net:+,.0f} 口|小台全市場 {oi:,.0f} 口</small><small>正=散戶偏多、負=散戶偏空|資料日 {fmt_date(d)}</small>")
    else:
        body = "<small>暫時無法取得,下次更新會再試</small>"
    return a + b + sec("#6a1b9a", "散戶多空比(小台)", body)


def summary(data):
    """LINE 用:回傳 dict(text, tw, fu);兩段都抓不到回 None。"""
    tw, fu, rt = data
    if not tw and not fu and not rt:
        return None
    lines = []
    if tw:
        d, o = tw
        lines.append(f"三大法人買賣超 {fmt_date(d)}\n    外資 {o['外資']:+,.1f}|投信 {o['投信']:+,.1f}|自營 {o['自營商']:+,.1f}|合計 {o['合計']:+,.1f} 億")
    else:
        lines.append("三大法人買賣超 暫無資料")
    if fu:
        d, net, lg, sh = fu
        ls = f"(多 {lg:,.0f}|空 {sh:,.0f})" if lg is not None and sh is not None else ""
        lines.append(f"外資台指期未平倉 {fmt_date(d)}\n    淨 {net:+,.0f} 口{ls}")
    else:
        lines.append("外資台指期未平倉 暫無資料")
    if rt:
        lines.append(f"散戶多空比(小台) {fmt_date(rt[0])}\n    {rt[1]:+.1f}%(散戶淨 {rt[2]:+,.0f} 口|全市場 {rt[3]:,.0f} 口)")
    else:
        lines.append("散戶多空比(小台) 暫無資料")
    return dict(text="\n".join(lines), tw=tw, fu=fu, rt=rt)
