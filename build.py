"""每日更新:證交所開高低收 → 480天Z-SCORE 模型 + 日/週/月動態 KD → docs/zscore.html、docs/zscore_output.csv"""
import os
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import model
from fetch_twse import update_data, TPE

CSV, OUT_HTML, OUT_CSV = "data/taiex.csv", "docs/zscore.html", "docs/zscore_output.csv"
TABLE_DAYS, CHART_DAYS, CSV_DAYS = 200, 750, 300
pct = lambda v: "" if pd.isna(v) else f"{v:+.1%}"
num = lambda v, n=2: "" if pd.isna(v) else f"{v:,.{n}f}"


def fmt(v):
    return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:.2f}"


def today_marks(last):
    """最新交易日的垂直虛線與「最新」標籤"""
    x = last.to_pydatetime()
    return dict(shapes=[dict(type="line", xref="x", yref="paper", x0=x, x1=x, y0=0, y1=1, line=dict(color="#888", width=1, dash="dot"))],
                annotations=[dict(x=x, xref="x", y=1, yref="paper", text=f"最新 {last:%m-%d}", showarrow=False, yanchor="bottom", font=dict(size=11, color="#888"))])


def chart(df, cols, title, h=400, first=False):
    f = go.Figure()
    last = df.index[-1]
    for name, color, w, dash in cols:
        f.add_scatter(x=df.index, y=df[name], name=name, line=dict(color=color, width=w, dash=dash))
    for name, color, w, dash in cols:                       # 最新一天:圓點 + 數值
        v = df[name].iloc[-1]
        if pd.notna(v):
            f.add_scatter(x=[last], y=[v], name=name, mode="markers+text", text=[fmt(v)], textposition="middle left",
                          marker=dict(color=color, size=7), textfont=dict(color=color, size=11), showlegend=False, hoverinfo="skip")
    f.update_layout(title=title, height=h, template="plotly_white", hovermode="x unified",
                    margin=dict(l=50, r=20, t=50, b=30), legend=dict(orientation="h", y=-0.12), **today_marks(last))
    return f.to_html(full_html=False, include_plotlyjs="cdn" if first else False)


UP_BAND, DN_BAND, DAYS, YEARS = 0.02, 0.01, 3, 3


def streak(flag):
    return flag.groupby((~flag).cumsum()).cumsum()


def ma_channel(m):
    d = pd.DataFrame({"close": m["台股收盤價"], "ma": m["200日均線"]})
    d["up"], d["dn"] = d.ma * (1 + UP_BAND), d.ma * (1 - DN_BAND)
    d["ua"], d["ub"] = streak(d.close > d.up), streak(d.close < d.dn)
    d["signal"] = ""
    d.loc[d.ua == DAYS, "signal"] = "買進"      # 連續第 3 天站上 MA200+2%
    d.loc[d.ub == DAYS, "signal"] = "賣出"      # 連續第 3 天跌破 MA200-1%
    d = d[d.index >= d.index[-1] - pd.DateOffset(years=YEARS)]
    last = d.iloc[-1]
    state = (f"已連續 {int(last.ua)} 天站上 MA+{UP_BAND:.0%}" if last.ua > 0 else
             f"已連續 {int(last.ub)} 天跌破 MA-{DN_BAND:.0%}" if last.ub > 0 else
             f"位於 MA-{DN_BAND:.0%} ~ MA+{UP_BAND:.0%} 通道內")
    f = go.Figure()
    f.add_scatter(x=d.index, y=d.up, name=f"MA200+{UP_BAND:.0%}", line=dict(color="#d9534f", width=1, dash="dot"))
    f.add_scatter(x=d.index, y=d.dn, name=f"MA200-{DN_BAND:.0%}", line=dict(color="#2e9e5b", width=1, dash="dot"),
                  fill="tonexty", fillcolor="rgba(150,150,150,0.10)")
    f.add_scatter(x=d.index, y=d.ma, name="MA200", line=dict(color="#f0ad4e", width=1.6))
    f.add_scatter(x=d.index, y=d.close, name="收盤", line=dict(color="#1f77b4", width=1.6))
    f.update_layout(title=f"台股加權指數 TAIEX(MA200 +{UP_BAND:.0%} / -{DN_BAND:.0%})", height=460, template="plotly_white",
                    hovermode="x unified", margin=dict(l=50, r=20, t=50, b=30), legend=dict(orientation="h", y=-0.12))
    sigs = d[d.signal != ""].iloc[::-1]
    rows = "".join(f"<tr class='{'buy' if r.signal == '買進' else 'sell'}'><td>{i:%Y-%m-%d}</td><td>{r.signal}</td>"
                   f"<td>{r.close:,.2f}</td><td>{r.ma:,.2f}</td></tr>" for i, r in sigs.iterrows()) or "<tr><td colspan=4>近三年無訊號</td></tr>"
    return f"""<h2>台股加權指數 MA200 通道與買賣訊號</h2>
<div class=status>{d.index[-1]:%Y-%m-%d} 收盤 {last.close:,.2f}|MA200 {last.ma:,.2f}|乖離 {(last.close / last.ma - 1) * 100:+.2f}%|<b>{state}</b></div>
<p class=n>規則:收盤連續 {DAYS} 天高於 MA200×{1 + UP_BAND:.2f} → 買進;連續 {DAYS} 天低於 MA200×{1 - DN_BAND:.2f} → 賣出(於第 {DAYS} 天觸發一次)。</p>
{f.to_html(full_html=False, include_plotlyjs="cdn")}
<details open><summary>買賣訊號(共 {len(sigs)} 筆,新到舊)</summary><div class=wrap><table><tr><th>日期</th><th>訊號</th><th>收盤</th><th>MA200</th></tr>{rows}</table></div></details>""", sigs


ZHOT = 1.5                                                      # Z-SCORE 高於此值 → 粉紅底
WINS = [5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 120, 150, 180]
ZCOLS = [f"{w}天 Z-SCORE" for w in WINS]                        # Excel AH~AT
XCOLS = [f"{a}>{b}天Z" for a, b in zip(WINS[:-1], WINS[1:])]    # Excel AU~BF
MACOLS = {"20日均線", "60日均線", "200日均線", "240日均線"}      # 收盤>均線 粉紅底、<均線 淡綠底
TEXT = {"生命線60*3%", "BUY(200日)2%", "SELL(200日)1%", "Z方向"} | set(XCOLS)
PCT1 = {"5-AVG", "5-STD", "10-AVG", "10-STD"}


def cell(c, r):
    v = r[c]
    if c in ("週KD", "月KD"):
        v = v if isinstance(v, str) else ""
        return f"<td class='{'gold' if v == '黃金交叉' else 'dead' if v == '死亡交叉' else ''}'>{v}</td>"
    if c in TEXT:
        return f"<td{' class=xc' if c in XCOLS else ''}>{v if isinstance(v, str) else ''}</td>"
    if pd.isna(v):
        return "<td></td>"
    if c in MACOLS:
        return f"<td class='{'pk' if r['台股收盤價'] > v else 'gr' if r['台股收盤價'] < v else ''}'>{v:,.2f}</td>"
    if c == "Z-SCORE":
        return f"<td class='{'pk' if v > ZHOT else ''} {'neg' if v < 0 else ''}'>{v:.2f}</td>"
    if c in ZCOLS:                                              # 當天 Z-SCORE 大於該格(N天 Z-SCORE)→ 淡粉底
        return f"<td class='{'pk' if r['Z-SCORE'] > v else ''}'>{v:.2f}</td>"
    if "乖離" in c:
        return f"<td>{pct(v)}</td>"
    if c in PCT1:
        return f"<td>{v:.1%}</td>"
    return f"<td>{num(v, 2)}</td>"


def zchart(m):
    """對應 Excel 的「台股 Z-SCORE」圖:左軸收盤價、右軸 Z-SCORE(-5~5)"""
    f = go.Figure()
    f.add_scatter(x=m.index, y=m["台股收盤價"], name="台股收盤價", line=dict(color="#1f77b4", width=1.4))
    f.add_scatter(x=m.index, y=m["Z-SCORE"], name="Z-SCORE", yaxis="y2", line=dict(color="#c0392b", width=1.4))
    last = m.index[-1]
    f.add_scatter(x=[last], y=[m["台股收盤價"].iloc[-1]], name="台股收盤價", mode="markers+text", text=[fmt(m["台股收盤價"].iloc[-1])],
                  textposition="middle left", marker=dict(color="#1f77b4", size=7), showlegend=False, hoverinfo="skip")
    f.add_scatter(x=[last], y=[m["Z-SCORE"].iloc[-1]], name="Z-SCORE", yaxis="y2", mode="markers+text", text=[fmt(m["Z-SCORE"].iloc[-1])],
                  textposition="top left", marker=dict(color="#c0392b", size=7), showlegend=False, hoverinfo="skip")
    f.update_layout(**today_marks(last))
    f.update_layout(title="台股 Z-SCORE(全部歷史:左軸收盤價、右軸 Z-SCORE)", height=440, template="plotly_white", hovermode="x unified",
                    margin=dict(l=50, r=50, t=50, b=30), legend=dict(orientation="h", y=-0.12),
                    yaxis=dict(title="收盤價"), yaxis2=dict(title="Z-SCORE", overlaying="y", side="right", range=[-5, 5], showgrid=False))
    return f.to_html(full_html=False, include_plotlyjs=False)


JS = """
(function(){
var tbl=document.getElementById('bigtbl'),rows=tbl.querySelectorAll('tr.r'),cx=tbl.querySelectorAll('.xc'),
    btns=document.querySelectorAll('.ctl button[data-n]'),xt=document.getElementById('xt');
function setRows(n){rows.forEach(function(t,i){t.style.display=i<n?'':'none'});
  btns.forEach(function(b){b.classList.toggle('on',+b.dataset.n===n)});}
function setX(show){cx.forEach(function(e){e.style.display=show?'':'none'});
  xt.textContent=show?'隱藏':'顯示';xt.dataset.s=show?'1':'0';}
btns.forEach(function(b){b.onclick=function(){setRows(+b.dataset.n)}});
xt.onclick=function(){setX(xt.dataset.s!=='1')};
var wide=window.innerWidth>=700;
setRows(wide?200:60);setX(wide);
})();
"""
CSS2 = """
.ctl{margin:6px 0;font-size:13px}.ctl button{margin-left:6px;padding:3px 10px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);cursor:pointer}
.ctl button.on{background:#1f77b4;color:#fff;border-color:#1f77b4}
.big{max-height:72vh;overflow:auto}.big th{position:sticky;top:0;z-index:2;background:var(--bg)}
.big th:first-child{left:0;z-index:3}.big th.xh{background:#ffe3a3;color:#222}
"""


def main():
    force = os.environ.get("FORCE") == "1"
    df, added = update_data(CSV, retries=int(os.environ.get("RETRIES", "0")))
    if not added and not force and os.path.exists(OUT_HTML):
        print("沒有新資料,不重建頁面")
        return
    m = model.zscore_model(df)
    kd = model.kd_log(df, max(CSV_DAYS, CHART_DAYS))
    m = m.join(kd)
    now = m.iloc[-1]
    k = model.kd_now(df)

    z, lo, hi = now["Z-SCORE"], now["Z低檔"], now["Z高檔"]
    zread = "高於 Z高檔(偏熱)" if z > hi else "低於 Z低檔(偏冷)" if z < lo else "在 Z低檔~Z高檔之間"
    cards = [("收盤", num(now["台股收盤價"])), ("Z-SCORE(480天)", f"{z:.2f}<small>{zread}</small>"),
             ("Z低檔 / Z高檔", f"{lo:.2f} / {hi:.2f}"), ("MAD ZSCORE", f"{now['MAD ZSCORE']:.2f}<small>低 {now['MAD 低檔']:.2f}|高 {now['MAD 高檔']:.2f}</small>"),
             ("200日線 ±", f"{now['BUY(200日)2%'] or now['SELL(200日)1%'] or '—'}<small>MA200 {num(now['200日均線'])}</small>"),
             ("生命線 60×3%", now["生命線60*3%"] or "—"),
             ("季線 / 年線乖離", f"{pct(now['季線乖離'])} / {pct(now['年線乖離'])}"),
             ("5年 / 10年線乖離", f"{pct(now['5年線乖離%'])} / {pct(now['10年線乖離%'])}<small>歷史均值 5年 {pct(now['5-AVG'])}|10年 {pct(now['10-AVG'])}</small>")]
    buy9 = [c for c in XCOLS[:9] if now[c] == "BUY"]
    cards.append(("5>10 ~ 80>90天Z 的 BUY 數", f"{len(buy9)} / 9<small>{'、'.join(c.replace('天Z', '') for c in buy9) or '目前沒有 BUY'}|全部 12 欄:{sum(now[c] == 'BUY' for c in XCOLS)} 個</small>"))
    yr = df[df.index > df.index[-1] - pd.DateOffset(years=1)]                       # 近一年(含最新一天)
    hi_px, hi_dt = yr["High"].max(), yr["High"].idxmax()
    dd = now["台股收盤價"] / hi_px - 1
    lv = [f"-{p}% <b>{hi_px * (1 - p / 100):,.0f}</b>" for p in (10, 15, 20, 25, 30, 35, 40)]
    cards.append(("近一年最高價", f"{hi_px:,.2f}<small>{hi_dt:%Y-%m-%d}|目前收盤距高點 <b style='color:{'#d9534f' if dd < 0 else 'inherit'}'>{dd:+.1%}</b></small>"))
    cards.append(("距近一年高點下跌對應指數", "<small class=lv>" + "<br>".join(" ｜ ".join(lv[i:i + 2]) for i in range(0, 7, 2)) + "</small>"))
    cards_html = "".join(f"<div class=card><span>{a}</span><b>{b}</b></div>" for a, b in cards)
    kd_rows = "".join(
        f"<tr><td>{n}KD</td><td>{v['K']:.1f}</td><td>{v['D']:.1f}</td><td>{v['low']:.1f} ~ {v['high']:.1f}</td>"
        f"<td class='{'hi' if v['zone'] == 'K值高檔' else 'lo' if v['zone'] == 'K值低檔' else ''}'>{v['zone'] or '—'}</td><td class='{'gold' if v['state'] == '黃金交叉' else 'dead' if v['state'] == '死亡交叉' else ''}'>{v['state']}</td></tr>"
        for n, v in k.items())

    cols = ["開盤價", "最高價", "最低價", "台股收盤價", "20日均線", "60日均線", "200日均線", "240日均線",
            "生命線60*3%", "BUY(200日)2%", "SELL(200日)1%", "季線乖離", "年線乖離", "5年線乖離%", "10年線乖離%",
            "Z-SCORE", "Z低檔", "Z高檔", "Z方向", "MAD ZSCORE"] + ZCOLS + XCOLS + ["週KD", "月KD"]
    head = "".join(f"<th class='{'xh xc' if c in XCOLS else ''}'>{c.replace('台股', '')}</th>" for c in ["日期"] + cols)
    body = ""
    for d, r in m.iloc[::-1].head(TABLE_DAYS).iterrows():
        body += f"<tr class=r><td>{d:%Y-%m-%d}</td>{''.join(cell(c, r) for c in cols)}</tr>"

    c1 = chart(m.tail(CHART_DAYS), [("台股收盤價", "#1f77b4", 1.5, None), ("20日均線", "#f0ad4e", 1, None), ("60日均線", "#8e44ad", 1, None),
                                   ("200日均線", "#d9534f", 1.4, None), ("240日均線", "#2e9e5b", 1.4, None)], "台股加權指數 與均線")
    c2 = chart(m.tail(CHART_DAYS), [("Z-SCORE", "#1f77b4", 1.6, None), ("Z高檔", "#d9534f", 1, "dot"), ("Z低檔", "#2e9e5b", 1, "dot")], "480天 Z-SCORE 與動態高低檔")
    c3 = chart(m.tail(CHART_DAYS), [("MAD ZSCORE", "#1f77b4", 1.6, None), ("MAD 高檔", "#d9534f", 1, "dot"), ("MAD 低檔", "#2e9e5b", 1, "dot")], "MAD ZSCORE 與動態高低檔")
    c4 = zchart(m)
    c5 = chart(m.tail(CHART_DAYS), [("週K", "#1f77b4", 1.5, None), ("週D", "#f0ad4e", 1.5, None), ("週K高檔", "#d9534f", 1, "dot"), ("週K低檔", "#2e9e5b", 1, "dot")], "動態週 KD(K、D 與 K 合理高低檔)", 360)
    c6 = chart(m.tail(CHART_DAYS), [("月K", "#1f77b4", 1.5, None), ("月D", "#f0ad4e", 1.5, None), ("月K高檔", "#d9534f", 1, "dot"), ("月K低檔", "#2e9e5b", 1, "dot")], "動態月 KD(K、D 與 K 合理高低檔)", 360)
    ma_html, _ = ma_channel(m)
    stamp = datetime.now(TPE)
    page = f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>480天 Z-SCORE 與日週月動態 KD</title><style>
:root{{--bg:#fff;--fg:#222;--mut:#666;--card:#f4f6f8;--line:#e3e3e3;--hi:#fde8e8;--pk:#fde0ec;--gr:#dcf3e4}}
@media(prefers-color-scheme:dark){{:root{{--bg:#14161a;--fg:#e6e6e6;--mut:#999;--card:#22262d;--line:#333;--hi:#4a2326;--pk:#5a2a3f;--gr:#1f3b2a}}}}
body{{font-family:system-ui,"Noto Sans TC",sans-serif;max-width:1200px;margin:0 auto;padding:16px;background:var(--bg);color:var(--fg)}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px}}.card{{background:var(--card);border-radius:8px;padding:10px 12px}}
.card span{{display:block;font-size:12px;color:var(--mut)}}.card b{{font-size:20px}}.card small.lv{{line-height:1.45;margin-top:2px}}.card small{{display:block;font-size:12px;font-weight:400;color:var(--mut)}}
table{{border-collapse:collapse;font-size:13px;width:100%}}th,td{{padding:4px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}
th:first-child,td:first-child{{text-align:left}}.wrap{{overflow-x:auto}}.wrap td:first-child,.wrap th:first-child{{position:sticky;left:0;background:var(--bg)}}td.hi{{background:var(--hi)}}td.pk{{background:var(--pk)}}td.gr{{background:var(--gr)}}.neg{{color:#d9534f;font-weight:700}}th.xh{{background:#ffe3a3;color:#222}}
p.n{{color:var(--mut);font-size:13px}}.gold{{color:#d9534f;font-weight:700}}.dead{{color:#2e9e5b;font-weight:700}}
.status{{background:var(--card);padding:8px 12px;border-radius:6px;font-size:14px}}tr.buy td:nth-child(2){{color:#d9534f;font-weight:700}}
tr.sell td:nth-child(2){{color:#2e9e5b;font-weight:700}}summary{{cursor:pointer;margin:8px 0;font-weight:600}}{CSS2}</style></head><body>
<h1>480天 Z-SCORE 與日週月動態 KD</h1>
<p class=n>資料日期:<b>{m.index[-1]:%Y-%m-%d}</b>|頁面更新:{stamp:%Y-%m-%d %H:%M}(台北)|資料來源:臺灣證券交易所 加權指數歷史資料|
<a href="zscore_output.csv">下載最近 {CSV_DAYS} 天完整欄位 CSV</a></p>
<div class=cards>{cards_html}</div>
<h2>日 / 週 / 月 動態 KD</h2><div class=wrap><table><tr><th>週期</th><th>K</th><th>D</th><th>K 合理低檔 ~ 高檔</th><th>位階</th><th>K 與 D</th></tr>{kd_rows}</table></div>
<p class=n>動態:以最新一天為終點,週 K=5 個交易日、月 K=22 個交易日,KD 取 9 根;黃金交叉 = K&gt;D、死亡交叉 = K&lt;D。</p>
{ma_html}
{c1}{c5}{c6}{c4}{c2}{c3}
<h2>最近 {TABLE_DAYS} 個交易日(Z-SCORE &gt; {ZHOT} 粉紅底、&lt; 0 紅字;當天 Z-SCORE 大於某天期 Z-SCORE → 該格粉紅底;收盤高於 20/60/200/240 日線 → 該均線格粉紅、低於 → 淡綠)</h2>
<div class=ctl>顯示列數:<button data-n=60>60</button><button data-n=120>120</button><button data-n=200>200</button>
<span style="margin-left:14px">Z 交叉欄(5&gt;10 … 150&gt;180):</span><button id=xt>隱藏</button></div>
<div class="wrap big"><table id=bigtbl><tr>{head}</tr>{body}</table></div><script>{JS}</script>
<p class=n>本頁欄位對應 Excel「480天Z-SCORE -2.0」工作表。僅供研究參考,非投資建議。</p></body></html>"""
    os.makedirs("docs", exist_ok=True)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(page)
    m.tail(CSV_DAYS).to_csv(OUT_CSV, encoding="utf-8-sig", float_format="%.4f")
    print(f"完成:資料至 {m.index[-1]:%Y-%m-%d},Z={z:.2f},週KD {k['週']['state']},月KD {k['月']['state']}")


if __name__ == "__main__":
    main()
