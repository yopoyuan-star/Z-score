"""每日更新:證交所開高低收 → 480天Z-SCORE 模型 + 日/週/月動態 KD → docs/zscore.html、docs/zscore_output.csv"""
import os
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import model
from fetch_twse import update_data, TPE

CSV, OUT_HTML, OUT_CSV = "data/taiex.csv", "docs/zscore.html", "docs/zscore_output.csv"
TABLE_DAYS, CHART_DAYS, CSV_DAYS = 60, 750, 300
pct = lambda v: "" if pd.isna(v) else f"{v:+.1%}"
num = lambda v, n=2: "" if pd.isna(v) else f"{v:,.{n}f}"


def chart(df, cols, title, h=400):
    f = go.Figure()
    for name, color, w, dash in cols:
        f.add_scatter(x=df.index, y=df[name], name=name, line=dict(color=color, width=w, dash=dash))
    f.update_layout(title=title, height=h, template="plotly_white", hovermode="x unified",
                    margin=dict(l=50, r=20, t=50, b=30), legend=dict(orientation="h", y=-0.12))
    return f.to_html(full_html=False, include_plotlyjs="cdn" if title.startswith("台股加權指數") else False)


def main():
    force = os.environ.get("FORCE") == "1"
    df, added = update_data(CSV, retries=int(os.environ.get("RETRIES", "0")))
    if not added and not force and os.path.exists(OUT_HTML):
        print("沒有新資料,不重建頁面")
        return
    m = model.zscore_model(df)
    kd = model.kd_log(df, CSV_DAYS)
    m = m.join(kd[["週KD", "月KD"]])
    now = m.iloc[-1]
    k = model.kd_now(df)

    z, lo, hi = now["Z-SCORE"], now["Z低檔"], now["Z高檔"]
    zread = "高於 Z高檔(偏熱)" if z > hi else "低於 Z低檔(偏冷)" if z < lo else "在 Z低檔~Z高檔之間"
    cards = [("收盤", num(now["台股收盤價"])), ("Z-SCORE(480天)", f"{z:.2f}<small>{zread}</small>"),
             ("Z低檔 / Z高檔", f"{lo:.2f} / {hi:.2f}"), ("MAD ZSCORE", f"{now['MAD ZSCORE']:.2f}<small>低 {now['MAD 低檔']:.2f}|高 {now['MAD 高檔']:.2f}</small>"),
             ("200日線 ±", f"{now['BUY(200日)2%'] or now['SELL(200日)1%'] or '—'}<small>MA200 {num(now['200日均線'])}</small>"),
             ("生命線 60×3%", now["生命線60*3%"] or "—"),
             ("季線 / 年線乖離", f"{pct(now['季線乖離'])} / {pct(now['年線乖離'])}"),
             ("5年 / 10年線乖離", f"{pct(now['5年線乖離%'])} / {pct(now['10年線乖離%'])}<small>5年 平均 {pct(now['5-AVG'])}</small>")]
    cards_html = "".join(f"<div class=card><span>{a}</span><b>{b}</b></div>" for a, b in cards)
    kd_rows = "".join(
        f"<tr><td>{n}KD</td><td>{v['K']:.1f}</td><td>{v['D']:.1f}</td><td>{v['low']:.1f} ~ {v['high']:.1f}</td>"
        f"<td class='{'hi' if v['zone'] == 'K值高檔' else 'lo' if v['zone'] == 'K值低檔' else ''}'>{v['zone'] or '—'}</td><td>{v['state']}</td></tr>"
        for n, v in k.items())

    cols = ["開盤價", "最高價", "最低價", "台股收盤價", "20日均線", "60日均線", "200日均線", "240日均線", "生命線60*3%", "BUY(200日)2%", "SELL(200日)1%",
            "季線乖離", "年線乖離", "5年線乖離%", "Z-SCORE", "Z低檔", "Z高檔", "MAD ZSCORE", "週KD", "月KD"]
    head = "".join(f"<th>{c.replace('台股', '')}</th>" for c in ["日期"] + cols)
    body = ""
    for d, r in m.iloc[::-1].head(TABLE_DAYS).iterrows():
        zc = "hi" if r["Z-SCORE"] > r["Z高檔"] else "lo" if r["Z-SCORE"] < r["Z低檔"] else ""
        cells = [f"<td>{d:%Y-%m-%d}</td>"] + [
            f"<td>{num(r[c], 2) if c in cols[:8] else r[c] if c in ('生命線60*3%', 'BUY(200日)2%', 'SELL(200日)1%', '週KD', '月KD') else pct(r[c]) if '乖離' in c else num(r[c], 2)}</td>" for c in cols]
        body += f"<tr class='{zc}'>{''.join(cells)}</tr>"

    c1 = chart(m.tail(CHART_DAYS), [("台股收盤價", "#1f77b4", 1.5, None), ("20日均線", "#f0ad4e", 1, None), ("60日均線", "#8e44ad", 1, None),
                                   ("200日均線", "#d9534f", 1.4, None), ("240日均線", "#2e9e5b", 1.4, None)], "台股加權指數 與均線")
    c2 = chart(m.tail(CHART_DAYS), [("Z-SCORE", "#1f77b4", 1.6, None), ("Z高檔", "#d9534f", 1, "dot"), ("Z低檔", "#2e9e5b", 1, "dot"),
                                   ("MAD ZSCORE", "#999", 1, None)], "480天 Z-SCORE 與動態高低檔")
    stamp = datetime.now(TPE)
    page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>480天 Z-SCORE 與日週月動態 KD</title><style>
:root{{--bg:#fff;--fg:#222;--mut:#666;--card:#f4f6f8;--line:#e3e3e3;--hi:#fde8e8;--lo:#e3f6ea}}
@media(prefers-color-scheme:dark){{:root{{--bg:#14161a;--fg:#e6e6e6;--mut:#999;--card:#22262d;--line:#333;--hi:#4a2326;--lo:#1f3b2a}}}}
body{{font-family:system-ui,"Noto Sans TC",sans-serif;max-width:1200px;margin:0 auto;padding:16px;background:var(--bg);color:var(--fg)}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}}.card{{background:var(--card);border-radius:8px;padding:10px 12px}}
.card span{{display:block;font-size:12px;color:var(--mut)}}.card b{{font-size:20px}}.card small{{display:block;font-size:12px;font-weight:400;color:var(--mut)}}
table{{border-collapse:collapse;font-size:13px;width:100%}}th,td{{padding:4px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}
th:first-child,td:first-child{{text-align:left}}.wrap{{overflow-x:auto}}tr.hi,td.hi{{background:var(--hi)}}tr.lo,td.lo{{background:var(--lo)}}
p.n{{color:var(--mut);font-size:13px}}</style></head><body>
<h1>480天 Z-SCORE 與日週月動態 KD</h1>
<p class=n>資料日期:<b>{m.index[-1]:%Y-%m-%d}</b>|頁面更新:{stamp:%Y-%m-%d %H:%M}(台北)|資料來源:臺灣證券交易所 加權指數歷史資料|
<a href="zscore_output.csv">下載最近 {CSV_DAYS} 天完整欄位 CSV</a></p>
<div class=cards>{cards_html}</div>
<h2>日 / 週 / 月 動態 KD</h2><div class=wrap><table><tr><th>週期</th><th>K</th><th>D</th><th>K 合理低檔 ~ 高檔</th><th>位階</th><th>K 與 D</th></tr>{kd_rows}</table></div>
<p class=n>動態:以最新一天為終點,週 K=5 個交易日、月 K=22 個交易日,KD 取 9 根;黃金交叉 = K&gt;D、死亡交叉 = K&lt;D。</p>
{c1}{c2}
<h2>最近 {TABLE_DAYS} 個交易日(紅底:Z-SCORE 高於 Z高檔;綠底:低於 Z低檔)</h2><div class=wrap><table><tr>{head}</tr>{body}</table></div>
<p class=n>本頁欄位對應 Excel「480天Z-SCORE -2.0」工作表。僅供研究參考,非投資建議。</p></body></html>"""
    os.makedirs("docs", exist_ok=True)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(page)
    m.tail(CSV_DAYS).join(kd[["週K", "週D", "月K", "月D"]]).to_csv(OUT_CSV, encoding="utf-8-sig", float_format="%.4f")
    print(f"完成:資料至 {m.index[-1]:%Y-%m-%d},Z={z:.2f},週KD {k['週']['state']},月KD {k['月']['state']}")


if __name__ == "__main__":
    main()
