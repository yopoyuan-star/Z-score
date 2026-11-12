"""每日更新:證交所開高低收 → 480天Z-SCORE 模型 + 日/週/月動態 KD → docs/zscore.html、docs/zscore_output.csv"""
import os
import re
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import model
import usma
import fx
import inst
from fetch_twse import update_data, TPE

PAGE_URL = "https://yopoyuan-star.github.io/Z-score/zscore.html"
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


SLOPE_DAYS, FLAT = 20, 0.005     # MA220 方向:與 20 個交易日前比,> +0.5% 上彎、< −0.5% 下彎、其餘走平


def ma_trend(ma):
    """回傳 (文字, 顏色, 說明);ma = 220 日均線序列"""
    s = ma.dropna()
    if len(s) <= SLOPE_DAYS:
        return "", "#888", ""
    sl = s.iloc[-1] / s.iloc[-1 - SLOPE_DAYS] - 1
    txt, col = ("↗上彎", "#d9534f") if sl > FLAT else ("↘下彎", "#2e9e5b") if sl < -FLAT else ("→走平", "#888")
    return txt, col, f"MA220 近 {SLOPE_DAYS} 個交易日 {sl * 100:+.2f}%"


def cross_run(states):
    """目前黃金/死亡交叉已連續幾個交易日(含今天);回傳 (天數, 是否到資料上限)"""
    v = list(states)
    if not v or not v[-1]:
        return 0, False
    n = 0
    for x in reversed(v):
        if x != v[-1]:
            return n, False
        n += 1
    return n, True


JS2 = r"""
(function(){var i=document.getElementById('cpx'),c=document.getElementById('ccap');if(!i||!c)return;
function f(v){var d=v>=1000?0:2;return v.toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});}
function u(){var v=parseFloat(i.value),k=parseFloat(c.value);for(var p=5;p<=60;p+=5){var e=document.getElementById('cx'+p),q=document.getElementById('cs'+p);var px=(v>0)?v*(1-p/100):0;
if(e)e.textContent=px>0?f(px):'—';if(q)q.textContent=(px>0&&k>0)?Math.floor(k/px).toLocaleString('en-US'):'—';}
}
function sv(){try{localStorage.setItem('zs_cpx',i.value);localStorage.setItem('zs_cap',c.value);}catch(x){}}
try{var s=localStorage.getItem('zs_cpx');if(s)i.value=s;var t=localStorage.getItem('zs_cap');if(t)c.value=t;}catch(x){}
i.addEventListener('input',function(){u();sv();});c.addEventListener('input',function(){u();sv();});u();})();
(function(){var y=document.getElementById('cpy');if(!y)return;
function f(v){var d=v>=1000?0:2;return v.toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});}
function u(){var v=parseFloat(y.value);for(var p=2;p<=20;p+=2){var e=document.getElementById('cy'+p);if(e)e.textContent=(v>0)?f(v*(1-p/100)):'—';}}
try{var s=localStorage.getItem('zs_cpy');if(s)y.value=s;}catch(x){}
y.addEventListener('input',function(){u();try{localStorage.setItem('zs_cpy',y.value);}catch(x){}});u();})();
(function(){var h=document.getElementById('cph');if(!h)return;
function f(v){var d=v>=1000?0:2;return v.toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});}
function u(){var v=parseFloat(h.value);for(var p=10;p<=80;p+=10){var e=document.getElementById('ch'+p);if(e)e.textContent=(v>0)?f(v*(1-p/100)):'—';}}
try{var s=localStorage.getItem('zs_cph');if(s)h.value=s;}catch(x){}
h.addEventListener('input',function(){u();try{localStorage.setItem('zs_cph',h.value);}catch(x){}});u();})();

(function(){var t=document.getElementById('zmemo'),b=document.getElementById('zmemoclr'),K='zs_memo';
if(!t)return;try{t.value=localStorage.getItem(K)||''}catch(e){}
t.addEventListener('input',function(){try{localStorage.setItem(K,t.value)}catch(e){}});
b.addEventListener('click',function(){if(t.value&&!window.confirm('確定清除筆記?'))return;t.value='';try{localStorage.removeItem(K)}catch(e){}});})();
"""


def ma200_state(m):
    """220 日線狀態:BUY=收盤>MA220×1.02、SELL=收盤<MA220×0.99(單日狀態);連續 3 天才是『訊號』。
    回傳 (BUY/SELL/—, 連續天數, 說明, 今天是否剛好第 3 天)"""
    c, ma = m["台股收盤價"], m["220日均線"]
    ua, ub = streak(c > ma * (1 + UP_BAND)), streak(c < ma * (1 - DN_BAND))
    for lab, st, word, sig in (("BUY", ua, f"站上 MA220+{UP_BAND:.0%}", "買進"), ("SELL", ub, f"跌破 MA220−{DN_BAND:.0%}", "賣出")):
        n = int(st.iloc[-1])
        if n > 0:
            if n < DAYS:
                note = f"已連續 {n} 天{word}|再 {DAYS - n} 天確認{sig}訊號"
            elif n == DAYS:
                note = f"已連續 {n} 天{word}|★今日{sig}訊號(第 {DAYS} 天)"
            else:
                d3 = st[st == DAYS].index[-1]
                note = f"已連續 {n} 天{word}|{sig}訊號發出日 {d3:%Y-%m-%d}"
            return lab, n, note, n == DAYS
    return "—", 0, f"介於 MA220−{DN_BAND:.0%} ~ +{UP_BAND:.0%} 之間", False


def warn_state(m, extra=()):
    """過熱轉弱警示:Z 向上穿越 model.SEG_RESET_Z(0.5)起算一段,六條件同時成立 = 6/6。
    (原本是「Z 由負翻正」起算;回測顯示 Z 過熱後不一定會跌破 0,但近 25 年都會跌破 0.5)
    1 本段 Z 曾 >1.5;2 本段前 9 欄(5>10…80>90)曾同時全 BUY;3 現在 BUY 數 <=3;4 週KD、月KD 皆死亡交叉;5 本段 5 年線乖離率曾 >15%;6 本段 90>120、120>150、150>180 三欄曾同時全 BUY。
    Z<=0 的日子不計入統計、也不會觸發 6/6;但不會清掉本段已成立的條件,要等 Z 再次向上穿越 0.5 才重新統計。
    備用重算:加權指數跌破 220 日線至少 20 個交易日後再站回,也開始新的一段(以防 Z 沒跌破 0.5;回測 25 年不影響任何進出)。
    買回重算(extra):右側全部買回的那一天也開始新的一段,過熱條件從頭累積(台股大漲時不必等 Z 或 MA220;回測 25 年不影響任何進出)。"""
    z = m["Z-SCORE"]
    x = model.SEG_RESET_Z
    cnt = sum((m[c] == "BUY").astype(int) for c in XCOLS[:9])
    zup = (z > x) & (z.shift() <= x)                                # 向上穿越 0.5 → 新的一段
    c_, ma_ = m["台股收盤價"], m[f"{model.SEG_MA}日均線"]
    below = c_ < ma_
    run = below.astype(int).groupby((~below).cumsum()).cumsum()     # 連續在 220 日線下的天數
    maup = (~below) & below.shift(fill_value=False) & (run.shift(fill_value=0) >= model.SEG_MA_MIN_BELOW)  # 跌破 ≥20 天後站回
    ext = pd.Series(m.index.isin(list(extra)), index=m.index)       # 全部買回日 → 新的一段
    up = zup | maup | ext
    sid = up.cumsum()
    live = (z > 0) & (sid > 0)                                      # Z<=0 期間不計
    seg = lambda f: (f & live).astype(int).groupby(sid).cummax().astype(bool) & live
    c = [seg(z > 1.5), seg(cnt == 9), cnt <= 3, (m["週KD"] == "死亡交叉") & (m["月KD"] == "死亡交叉"), seg(m["5年線乖離%"] > 0.15),
         seg((m[XCOLS[9]] == "BUY") & (m[XCOLS[10]] == "BUY") & (m[XCOLS[11]] == "BUY"))]
    allok = c[0] & c[1] & c[2] & c[3] & c[4] & c[5] & live
    now_ok = [bool(v.iloc[-1]) for v in c]
    first = start = None
    start_by_ma = None
    if live.iloc[-1]:
        start = up[up].index[-1]                                    # 本段起點:最近一次 Z 上穿 0.5、站回 220 日線或全部買回
        start_by_ma = ("buy" if bool(ext.loc[start]) else "ma" if bool(maup.loc[start]) and not bool(zup.loc[start]) else "z")
        cur = allok & (sid == sid.iloc[-1])
        first = cur[cur].index[0] if cur.any() else None            # 本段第一次 6/6 的日期
    return now_ok, first, (start, start_by_ma), allok, sid


# ===== 買賣規則(2026-11 回測定案,G1 版)=====
LEFT = [(0.10, 0.05), (0.15, 0.075), (0.20, 0.10), (0.25, 0.125), (0.30, 0.15)]   # 距一年高點跌幅 → 加碼比例(占總資金,左側合計 50%)
HALF_Z, ARM_DD, BACKUP_DAYS, STOP_DD = -2.5, 0.20, 252, 0.20
# 保險 B(MA220,與 A 並行,任一成立就轉出;2026-11 回測 D 版):全部買回後曾站上 MA220,之後
#   連 3 天收盤 < MA220×0.99 且 MA220 比 20 個交易日前低 0.5% 以上 → 轉出;轉出後連 3 天收盤站回 MA220 → 全部買回(不等 KD)
INS_DAYS, INS_BAND, INS_SLOPE = 3, 0.01, -0.005
# 左側:Z<-2.5 時直接補到 50%;右側先決:Z≤0 或距一年高點跌 20% 或轉出滿 252 個交易日 → 已收完月K KD 金叉全部買回
# 保險:全部買回後收盤跌破買回均價 20% → 再轉出,等月 KD「重新」金叉(先死叉再金叉)才再買回


def closed_month_gold(df):
    """每天可用的「已收完月 K」KD 是否黃金交叉(月底最後一個交易日算當月已收完,其餘看上個月)"""
    per = df.index.to_period("M")
    g = df.groupby(per).agg(High=("High", "max"), Low=("Low", "min"), Close=("Close", "last"))
    k, d = model._kd(g.High.to_numpy(), g.Low.to_numpy(), g.Close.to_numpy())
    gold = pd.Series(k > d, index=g.index)
    last = pd.Series(per != pd.Series(per, index=df.index).shift(-1).values, index=df.index)
    t = df.index[-1]
    last.iloc[-1] = t.normalize() >= (t + pd.offsets.MonthEnd(0)).normalize()
    use = [p if l else p - 1 for p, l in zip(per, last)]
    return pd.Series([bool(gold.get(p, False)) for p in use], index=df.index)


def exit_cycle(m, allok, sid, mgold):
    """依買賣規則逐日追蹤目前所在階段(與 ladder7_grid.py 的 G1 回測相同)。
    6/6 成立 → 轉出;左側:距一年高點 -10/-15/-20/-25/-30% 各買 5/7.5/10/12.5/15%(Z<-2.5 直接補到 50%);
    右側:先決(Z≤0 / 距一年高點跌 20% / 轉出滿 252 日)成立後,已收完月K KD 金叉 → 全部買回;
    全部買回後跌破均價 20% → 再轉出(月 KD 需重新金叉)。
    全部買回當天即開始新的一段(過熱條件從頭累積),之後才會再判斷 6/6。"""
    c = m["台股收盤價"].to_numpy(); hi = m["台股收盤價"].rolling(250, min_periods=1).max().to_numpy()
    z = m["Z-SCORE"].to_numpy(); ok = allok.to_numpy(); sd = sid.to_numpy(); g = mgold.reindex(m.index).fillna(False).to_numpy()
    mav = m["220日均線"].to_numpy(dtype=float)
    dnr = streak(pd.Series(c < mav * (1 - INS_BAND), index=m.index)).to_numpy()
    upr = streak(pd.Series(c > mav, index=m.index)).to_numpy()
    slp = (m["220日均線"] / m["220日均線"].shift(SLOPE_DAYS) - 1).to_numpy()
    st = dict(pos=1.0, ex=None, why=None, arm=None, done=set(), buys=[], blk=None, fresh=False, back=None, avg=None,
              seen=False, maout=False)
    backs = []
    for i in range(len(m)):
        if st["pos"] >= 1:
            if st["avg"] is not None:
                if mav[i] == mav[i] and c[i] > mav[i]: st["seen"] = True
                if c[i] <= st["avg"] * (1 - STOP_DD):          # 保險 A:跌破買回均價 20%
                    st.update(pos=0.0, ex=i, why="停損", arm=("停損後沿用", i), done=set(), buys=[], fresh=True, avg=None, seen=False)
                    continue
                if st["seen"] and dnr[i] >= INS_DAYS and slp[i] < INS_SLOPE:      # 保險 B:MA220
                    st.update(pos=0.0, ex=i, why="MA220", arm=None, done=set(), buys=[], fresh=False, avg=None, seen=False, maout=True)
                    continue
            if ok[i] and sd[i] != st["blk"]:
                st.update(pos=0.0, ex=i, why="6/6", arm=None, done=set(), buys=[], fresh=False, avg=None, seen=False)
            continue
        if st["maout"]:                                   # 保險 B 轉出後:連 3 天站回 MA220 → 全部買回
            if upr[i] >= INS_DAYS:
                st.update(pos=1.0, maout=False, avg=c[i], seen=True, back=i)
            continue
        dd = c[i] / hi[i] - 1
        if st["arm"] is None:
            if z[i] <= 0: st["arm"] = ("Z≤0", i)
            elif dd <= -ARM_DD: st["arm"] = (f"跌{ARM_DD:.0%}", i)
            elif i - st["ex"] >= BACKUP_DAYS: st["arm"] = ("轉出滿 12 個月", i)
        new = st["pos"]
        if z[i] < HALF_Z and new < 0.5: new = 0.5
        for k, (x, w) in enumerate(LEFT):
            if k not in st["done"] and dd <= -x:
                st["done"].add(k); new = min(0.5, new + w)
        if not g[i]: st["fresh"] = False
        if st["arm"] is not None and g[i] and not st["fresh"]: new = 1.0
        if new > st["pos"]:
            st["buys"].append((i, new - st["pos"], c[i])); st["pos"] = new
            if new >= 1:
                st["avg"] = sum(w * p for _, w, p in st["buys"]) / sum(w for _, w, _ in st["buys"])
                st["back"] = i; backs.append(m.index[i]); st["seen"] = False
                st["blk"] = None      # 全部買回當天即重算本段(由 warn_state 的 extra 處理),不再封鎖
    idx = m.index; h = hi[-1]
    nxt = next(((x, w) for k, (x, w) in enumerate(LEFT) if k not in st["done"]), None) if st["pos"] < 1 else None
    inv = [(w, p) for _, w, p in st["buys"]] if st["pos"] < 1 else []
    return dict(state="持有" if st["pos"] >= 1 else "空手", pos=st["pos"], exit=idx[st["ex"]] if st["ex"] is not None else None,
                n=(len(m) - 1 - st["ex"]) if st["ex"] is not None else 0, why=st["why"],
                arm=(st["arm"][0], idx[st["arm"][1]]) if st["arm"] else None, hi=h,
                left_avg=(sum(w * p for w, p in inv) / sum(w for w, _ in inv)) if inv else None,
                nxt=(nxt[0], nxt[1], h * (1 - nxt[0])) if nxt else None, arm_px=h * (1 - ARM_DD),
                avg=st["avg"], stop_px=st["avg"] * (1 - STOP_DD) if st["avg"] else None, back=idx[st["back"]] if st["back"] is not None else None,
                backs=backs, maout=st["maout"], seen=st["seen"],
                ins=dict(dn=int(dnr[-1]), up=int(upr[-1]), slope=float(slp[-1]), ma=float(mav[-1]), ma99=float(mav[-1]) * (1 - INS_BAND),
                         close=float(c[-1])))


def _p(x):
    return f"{x * 100:g}%"


def cycle_lines(cy, z):
    """已轉出期間的提示(LINE 與網頁滑鼠說明用);持有中只在保險有效時提示停損價"""
    if cy["state"] == "持有":
        return [f"保險:收盤跌破 {cy['stop_px']:,.0f}(買回均價 {cy['avg']:,.0f} 的 −20%)→ 再轉出"] if cy["stop_px"] else []
    if cy["maout"]:
        i_ = cy["ins"]
        return [("今日保險 B(MA220)成立,請轉出:一半中華電、一半現金" if cy["n"] == 0 else
                 f"保險 B(MA220)轉出 {cy['n']} 個交易日({cy['exit']:%Y-%m-%d} 起)"),
                f"連 {INS_DAYS} 天收盤站回 MA220({i_['ma']:,.0f})→ 全部買回(不等 KD);目前 {min(i_['up'], INS_DAYS)}/{INS_DAYS}"]
    head = ("今日 6/6 成立,請開始執行轉出" if cy["n"] == 0 and cy["why"] == "6/6" else
            f"{'停損' if cy['why'] == '停損' else '已'}轉出 {cy['n']} 個交易日({cy['exit']:%Y-%m-%d} 起)")
    left = (f"左側已投入 {_p(cy['pos'])}" + (f"(均價 {cy['left_avg']:,.0f})" if cy["left_avg"] else "")
            + (f";下一筆 跌{cy['nxt'][0]:.0%} {cy['nxt'][2]:,.0f} 加 {_p(cy['nxt'][1])}" if cy["nxt"] else ";左側已滿 50%"))
    if cy["arm"]:
        right = f"右側已啟動({cy['arm'][0]} {cy['arm'][1]:%m/%d}),等已收完月K KD 金叉全部買回"
    else:
        right = f"右側等 Z≤0 或跌 20%({cy['arm_px']:,.0f});{max(BACKUP_DAYS - cy['n'], 0)} 個交易日後未成立 → 改只看月 KD 金叉"
    return [head, left, right]


def cycle_short(cy):
    """網頁卡片用的一行版本(維持卡片高度)"""
    if cy["state"] == "持有":
        return f"保險:跌破 {cy['stop_px']:,.0f} 再轉出" if cy["stop_px"] else ""
    if cy["n"] == 0 and cy["why"] == "6/6":
        return "今日 6/6 成立,請開始執行轉出"
    if cy["maout"]:
        return ("今日保險 B 成立,請轉出" if cy["n"] == 0 else
                f"MA220保險轉出{cy['n']}日｜站回 {min(cy['ins']['up'], INS_DAYS)}/{INS_DAYS}")
    tail = "等月KD金叉" if cy["arm"] else "等跌20%"
    return f"已轉出{cy['n']}日｜左{_p(cy['pos'])}｜{tail}"


def ins_checks(cy):
    """買回後保險(A 均價 −20%、B MA220)各條件是否成立"""
    i_ = cy["ins"]; held = cy["state"] == "持有" and cy["avg"] is not None
    a = [held, held and i_["close"] <= cy["stop_px"]]
    b = [held, held and cy["seen"], i_["dn"] >= INS_DAYS, i_["slope"] < INS_SLOPE]
    return held, a, b, cy["maout"] and i_["up"] >= INS_DAYS      # 只有保險 B 賣出後才判斷站回


def ins_status(cy):
    held, a, b, _ = ins_checks(cy)
    if cy["state"] != "持有":
        if cy["maout"]:
            return ("⚠ 保險 B 成立:今天轉出!" if cy["n"] == 0 else f"保險 B 轉出中({cy['exit']:%m/%d} 起 {cy['n']} 日),等站回 MA220"), "#c1121f"
        if cy["why"] == "停損":
            return ("⚠ 保險 A 成立:今天轉出!" if cy["n"] == 0 else "保險 A 轉出中,等月KD重新金叉買回"), "#c1121f"
        return "目前空手(6/6 轉出中),全部買回後才啟動", "#c1121f"
    if not held:
        return "持有中(資料內尚未有全部買回),保險未啟動", "#888"
    return f"持有中,保險啟動中(B 已 {sum(b)}/4)", "#1a7f37"


def ins_lines(cy):
    """LINE 用:保險 A / B 狀態"""
    held, a, b, up = ins_checks(cy); i_ = cy["ins"]; ck = lambda o: "☑" if o else "☐"
    if cy["maout"]:
        return []                       # 已在 cycle_lines 說明
    if not held:
        return ["保險 A/B:全部買回後才啟動(A 跌破均價−20%、B MA220)"] if cy["state"] != "持有" else []
    return [f"保險B(MA220){sum(b)}/4:{ck(b[1])}站上過年線 {ck(b[2])}連{INS_DAYS}天<{i_['ma99']:,.0f}({min(i_['dn'], INS_DAYS)}/{INS_DAYS}) "
            f"{ck(b[3])}年線下彎({i_['slope'] * 100:+.2f}%)→ 全打勾就轉出"]


def ins_html(cy):
    held, a, b, up = ins_checks(cy); i_ = cy["ins"]
    ck = lambda o: "<b class=ok>☑</b>" if o else "<b class=no>☐</b>"
    msg, col = ins_status(cy)
    stop = f"{cy['stop_px']:,.0f}(均價 {cy['avg']:,.0f} −20%)" if held else "買回均價 −20%"
    upt = f"{min(i_['up'], INS_DAYS)}/{INS_DAYS}" if cy["maout"] else "(B 賣出後才判斷)"
    return f"""<div class=ins><div><b class=it>🛡 買回後保險</b><br><span class=mu>兩種並行,任一成立就轉出</span><br><b style="color:{col}">{msg}</b></div>
<div class=ic><b>A 均價 −20%(原規則)</b><br>{ck(a[0])} 已全部買回<br>{ck(a[1])} 收盤跌破 {stop} → 轉出<br><span class=mu>↳ 賣出後:等月KD重新金叉買回</span></div>
<div class=ic><b>B MA220(新增)</b> <span class=mu>4 格全打 V → 轉出</span><br>{ck(b[0])} 已全部買回　{ck(b[1])} 買回後站上過 MA220<br>
{ck(b[2])} 連 {INS_DAYS} 天收盤 &lt; MA220−1%({i_['ma99']:,.0f}){min(i_['dn'], INS_DAYS)}/{INS_DAYS}　{ck(b[3])} 年線下彎(20日 {i_['slope'] * 100:+.2f}%)<br>
<span class=mu>↳ 賣出後:</span>{ck(up)} 連 {INS_DAYS} 天站回 MA220({i_['ma']:,.0f}){upt} → 全部買回</div></div>"""


CSS_INS = """
.ins{display:grid;grid-template-columns:minmax(170px,.8fr) 1fr 1.5fr;gap:4px 18px;border:2px solid #2f6fb5;border-radius:8px;padding:6px 12px;margin:0 0 10px;font-size:12.5px;line-height:1.55;background:var(--card)}
.ins .ic{border-left:1px solid #ccd;padding-left:12px}.ins .it{font-size:13.5px}.ins .mu{color:var(--mut)}
.ins b.ok{color:#1a7f37;font-size:14px}.ins b.no{color:#aaa;font-weight:400;font-size:14px}
@media(max-width:760px){.ins{grid-template-columns:1fr}.ins .ic{border-left:0;padding-left:0;border-top:1px solid #ccd;padding-top:4px}}
"""

CSS_TREND = """
.trend{display:grid;grid-template-columns:auto 1fr;gap:6px 16px;align-items:center;border-radius:8px;padding:10px 14px;margin-bottom:10px}
.trend.s_bull{background:#fdecea;box-shadow:inset 0 0 0 2px #e0857c}.trend.s_pull{background:#fff4d6;box-shadow:inset 0 0 0 2px #e3bd52}
.trend.s_bounce{background:#e8f0fb;box-shadow:inset 0 0 0 2px #9db9e3}.trend.s_bear{background:#e5f4ea;box-shadow:inset 0 0 0 2px #8fcba5}
@media (prefers-color-scheme:dark){.trend.s_bull{background:#4a2326}.trend.s_pull{background:#4a3d1c}.trend.s_bounce{background:#1f2f4a}.trend.s_bear{background:#1f3b2a}.trend .chips span{background:#22262d!important;border-color:#333!important}}
.trend .lab{font-size:12px;font-weight:800;color:var(--mut)}.trend .st{font-size:24px;font-weight:800;line-height:1.15}.trend .sub{font-size:12px;color:var(--mut)}
.trend .steps{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:6px}.trend .steps i{font-style:normal;font-size:12px;font-weight:700;padding:2px 10px;border-radius:12px;background:#ececec;color:#999}
.trend .steps i.on{color:#fff}.trend .chips{display:flex;gap:6px;flex-wrap:wrap}.trend .chips span{font-size:12px;padding:2px 8px;border-radius:6px;background:#fff;border:1px solid #e3e3e3}
.trend .ok{color:#d9534f}.trend .ng{color:#2e9e5b}.trend .nt{color:#c77700}.trend .foot{grid-column:1/3;font-size:11.5px;color:var(--mut);border-top:1px dashed rgba(0,0,0,.18);padding-top:4px}
@media (max-width:640px){.trend{grid-template-columns:1fr}.trend .foot{grid-column:1}}
"""


TREND_STYLE = {   # 狀態 → (class, 文字色, 說明)
    "多頭": ("s_bull", "#c62828", "年線上彎、月KD金叉,趨勢向上"),
    "多頭修正": ("s_pull", "#c77700", "長期多頭架構仍在｜高檔轉弱,尚未轉空"),
    "空頭反彈": ("s_bounce", "#1f5fbf", "長期趨勢偏弱｜月KD金叉多為反彈,留意年線壓力"),
    "空頭": ("s_bear", "#2e7d4f", "跌破年線或深度回檔,趨勢向下"),
}


def trend_state(m, dd, mc, wk_state, wk_run):
    """多空狀態:看 MA220 位置與方向、已收完月 KD、距一年高點跌幅。
    空頭結構 = 連 3 天收在 MA220×0.99 以下且年線不再上彎;深度回檔 = 距一年高點跌逾 20% 且月KD死叉。"""
    c, ma = m["台股收盤價"], m[f"{model.SEG_MA}日均線"]
    px, mav = c.iloc[-1], ma.iloc[-1]
    s_ = ma.dropna()
    slope = s_.iloc[-1] / s_.iloc[-1 - SLOPE_DAYS] - 1 if len(s_) > SLOPE_DAYS else 0.0
    brk = bool((c.iloc[-3:] < ma.iloc[-3:] * 0.99).all())
    up, down = slope > FLAT, slope < -FLAT
    gold = mc["state"] == "黃金交叉"
    deep = dd <= -0.20 and not gold
    if up and not brk and not deep:
        st = "多頭" if gold else "多頭修正"
    else:
        st = "空頭反彈" if gold else "空頭"
    ok, ng, nt = "<b class=ok>✔</b>", "<b class=ng>✘</b>", "<b class=nt>▲</b>"
    chips = [f"{ok if px > mav else ng} 年線{'上方' if px > mav else '下方'} {px / mav - 1:+.1%}(MA{model.SEG_MA} {mav:,.0f})",
             f"{ok if up else ng if down else nt} 年線{'上彎' if up else '下彎' if down else '走平'} {slope:+.2%}/20日",
             f"{ok if gold else ng} 已收完月KD {'金叉' if gold else '死叉'} {mc['K']:.1f} / {mc['D']:.1f}",
             f"{ok if wk_state == '黃金交叉' else ng} 週KD {'金叉' if wk_state == '黃金交叉' else '死叉'}{(' ' + wk_run) if wk_run else ''}",
             f"{nt} 距一年高點 {dd:+.1%}({'已逾' if dd <= -0.20 else '未達'} −20%)"]
    reason = (f"年線{'上' if px > mav else '下'}方{px / mav - 1:+.1%}、年線{'上彎' if up else '下彎' if down else '走平'}、"
              f"月KD{'金叉' if gold else '死叉'}、距高點{dd:+.1%}")
    return dict(state=st, chips=chips, reason=reason, ma=mav)


def trend_html(t, asof):
    cls, col, sub = TREND_STYLE[t["state"]]
    steps = "".join(f"<i class=on style='background:{col}'>● {n}</i>" if n == t["state"] else f"<i>{n}</i>" for n in TREND_STYLE)
    return (f"<div class='trend {cls}'><div><div class=lab>📈 多空狀態({asof:%Y-%m-%d})</div>"
            f"<div class=st style='color:{col}'>{t['state']}</div><div class=sub>{sub}</div></div>"
            f"<div><div class=steps>{steps}</div><div class=chips>{''.join(f'<span>{x}</span>' for x in t['chips'])}</div></div>"
            f"<div class=foot>轉空確認:連 3 天收在 MA{model.SEG_MA}×0.99(約 {t['ma'] * 0.99:,.0f})以下且年線轉下彎,或距一年高點跌逾 20% 且月KD死叉"
            f"｜回到多頭:年線上彎且已收完月K KD 金叉</div></div>")


def ma_channel(m):
    d = pd.DataFrame({"close": m["台股收盤價"], "ma": m["220日均線"]})
    d["up"], d["dn"] = d.ma * (1 + UP_BAND), d.ma * (1 - DN_BAND)
    d["ua"], d["ub"] = streak(d.close > d.up), streak(d.close < d.dn)
    d["signal"] = ""
    d.loc[d.ua == DAYS, "signal"] = "買進"      # 連續第 3 天站上 MA220+2%
    d.loc[d.ub == DAYS, "signal"] = "賣出"      # 連續第 3 天跌破 MA220-1%
    d = d[d.index >= d.index[-1] - pd.DateOffset(years=YEARS)]
    last = d.iloc[-1]
    state = (f"已連續 {int(last.ua)} 天站上 MA+{UP_BAND:.0%}" if last.ua > 0 else
             f"已連續 {int(last.ub)} 天跌破 MA-{DN_BAND:.0%}" if last.ub > 0 else
             f"位於 MA-{DN_BAND:.0%} ~ MA+{UP_BAND:.0%} 通道內")
    f = go.Figure()
    f.add_scatter(x=d.index, y=d.up, name=f"MA220+{UP_BAND:.0%}", line=dict(color="#d9534f", width=1, dash="dot"))
    f.add_scatter(x=d.index, y=d.dn, name=f"MA220-{DN_BAND:.0%}", line=dict(color="#2e9e5b", width=1, dash="dot"),
                  fill="tonexty", fillcolor="rgba(150,150,150,0.10)")
    f.add_scatter(x=d.index, y=d.ma, name="MA220", line=dict(color="#f0ad4e", width=1.6))
    f.add_scatter(x=d.index, y=d.close, name="收盤", line=dict(color="#1f77b4", width=1.6))
    f.update_layout(title=f"台股加權指數 TAIEX(MA220 +{UP_BAND:.0%} / -{DN_BAND:.0%})", height=460, template="plotly_white",
                    hovermode="x unified", margin=dict(l=50, r=20, t=50, b=30), legend=dict(orientation="h", y=-0.12))
    sigs = d[d.signal != ""].iloc[::-1]
    rows = "".join(f"<tr class='{'buy' if r.signal == '買進' else 'sell'}'><td>{i:%Y-%m-%d}</td><td>{r.signal}</td>"
                   f"<td>{r.close:,.2f}</td><td>{r.ma:,.2f}</td></tr>" for i, r in sigs.iterrows()) or "<tr><td colspan=4>近三年無訊號</td></tr>"
    return f"""<h2>台股加權指數 MA220 通道與買賣訊號</h2>
<div class=status>{d.index[-1]:%Y-%m-%d} 收盤 {last.close:,.2f}|MA220 {last.ma:,.2f}|乖離 {(last.close / last.ma - 1) * 100:+.2f}%|<b>{state}</b></div>
<p class=n>規則:收盤連續 {DAYS} 天高於 MA220×{1 + UP_BAND:.2f} → 買進;連續 {DAYS} 天低於 MA220×{1 - DN_BAND:.2f} → 賣出(於第 {DAYS} 天觸發一次)。</p>
{f.to_html(full_html=False, include_plotlyjs="cdn")}
<details open><summary>買賣訊號(共 {len(sigs)} 筆,新到舊)</summary><div class=wrap><table><tr><th>日期</th><th>訊號</th><th>收盤</th><th>MA220</th></tr>{rows}</table></div></details>""", sigs


ZHOT = 1.5                                                      # Z-SCORE 高於此值 → 粉紅底
WINS = [5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 120, 150, 180]
ZCOLS = [f"{w}天 Z-SCORE" for w in WINS]                        # Excel AH~AT
XCOLS = [f"{a}>{b}天Z" for a, b in zip(WINS[:-1], WINS[1:])]    # Excel AU~BF
MACOLS = {"20日均線", "60日均線", "220日均線", "240日均線"}      # 收盤>均線 粉紅底、<均線 淡綠底
TEXT = {"生命線60*3%", "BUY(220日)2%", "SELL(220日)1%", "Z方向"} | set(XCOLS)
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
    mc = model.closed_month_kd(df)                      # 已收完月 K(日曆月)

    z, lo, hi = now["Z-SCORE"], now["Z低檔"], now["Z高檔"]
    zread = "高於 Z高檔(偏熱)" if z > hi else "低於 Z低檔(偏冷)" if z < lo else "在 Z低檔~Z高檔之間"
    prev = m["台股收盤價"].iloc[-2]
    chg = now["台股收盤價"] - prev
    chg_pct = chg / prev
    chg_col = "#d9534f" if chg > 0 else "#2e9e5b" if chg < 0 else "inherit"        # 台股慣例:漲紅、跌綠
    arrow = "▲" if chg > 0 else "▼" if chg < 0 else "－"
    chg_html = f"<small style='color:{chg_col};font-size:15px;font-weight:600'>{arrow} {abs(chg):,.2f}　({chg_pct:+.2%})</small>"
    ma_lab, ma_n, ma_note, ma_today = ma200_state(m)
    tr_txt, tr_col, tr_note = ma_trend(m["220日均線"])
    tr_html = (f"<span title='{tr_note}' style='display:inline;font-size:15px;font-weight:700;margin-left:8px;color:{tr_col}'>年線{tr_txt}</span>" if tr_txt else "")
    _dk, _dd = model._kd(df.High.to_numpy(), df.Low.to_numpy(), df.Close.to_numpy())
    _dst = ["黃金交叉" if a > b else "死亡交叉" if a < b else "" for a, b in zip(_dk, _dd)]
    runs = {"日": cross_run(_dst), "週": cross_run(m["週KD"]), "月": cross_run(m["月KD"])}
    run_txt = lambda n: ("" if not runs[n][0] else f"連{'≥' if runs[n][1] else ''}{runs[n][0]}日")
    kd_run_html = {n: (f' <small style="display:inline;font-size:12px">{run_txt(n)}</small>' if run_txt(n) else "") for n in runs}
    inst_data = inst.fetch()                              # 三大法人 + 外資期貨(網頁與 LINE 共用)
    fx_card, fx_rows = fx.card(20)                         # 美元兌台幣 + 近 20 日小走勢圖(整合進收盤卡片);抓不到時顯示『暫無資料』
    fx_html = ("<div style='margin-top:10px;font-size:12px;color:var(--mut);font-weight:400'>美元兌台幣 USD/TWD</div>"
               "<div style='font-size:18px;font-weight:700'>" + fx_card[1].replace("<small>數字上升 = 台幣貶值</small>", "") + "</div>")
    cards = [(f"收盤(收盤日 {m.index[-1]:%Y-%m-%d})", f"{num(now['台股收盤價'])}{chg_html}<div style='margin-top:10px'>{inst.html(inst_data)}</div>"), ("Z-SCORE(480天)", f"{z:.2f}<small>{zread}</small><small>Z低檔 {lo:.2f}｜Z高檔 {hi:.2f}</small><small style='margin-top:8px'>MAD ZSCORE <i style='font-style:normal;font-weight:700;font-size:16px'>{now['MAD ZSCORE']:.2f}</i></small><small>MAD 低檔 {now['MAD 低檔']:.2f}｜高檔 {now['MAD 高檔']:.2f}</small>"),
             ("MAD ZSCORE", f"{now['MAD ZSCORE']:.2f}<small>低 {now['MAD 低檔']:.2f}|高 {now['MAD 高檔']:.2f}</small>"),
             ("220日線 ±", f"{ma_lab}{tr_html}<small>{ma_note.replace('|', '<br>')}</small><small>MA220 {num(now['220日均線'])}</small><small>生命線 60×3%:{now['生命線60*3%'] or '—'}</small>"),
             ("季線 / 年線乖離", f"{pct(now['季線乖離'])} / {pct(now['年線乖離'])}"),
             ("5年 / 10年線乖離", f"{pct(now['5年線乖離%'])} / {pct(now['10年線乖離%'])}<small>歷史均值 5年 {pct(now['5-AVG'])}|10年 {pct(now['10-AVG'])}</small>")]
    buy9 = [c for c in XCOLS[:9] if now[c] == "BUY"]
    cards.append(("5>10 ~ 80>90天Z 的 BUY 數", f"{len(buy9)} / 9<small>{'、'.join(c.replace('天Z', '') for c in buy9) or '目前沒有 BUY'}|全部 12 欄:{sum(now[c] == 'BUY' for c in XCOLS)} 個</small>"))
    yr = df[df.index > df.index[-1] - pd.DateOffset(years=1)]                       # 近一年(含最新一天)
    hi_px, hi_dt = yr["High"].max(), yr["High"].idxmax()
    dd = now["台股收盤價"] / hi_px - 1
    trend = trend_state(m, dd, mc, k["週"]["state"], run_txt("週"))
    row = lambda p: f"<div class=lvr><span>-{p}%</span><i>→</i><em>{hi_px * (1 - p / 100):,.0f}</em></div>"
    _mg = closed_month_gold(df)
    _extra = []
    for _ in range(4):                                  # 全部買回日會開新的一段 → 反覆計算到買回日期不再改變
        wok, wfirst, (wstart, wstart_ma), wall, wsid = warn_state(m, _extra)
        cyc = exit_cycle(m, wall, wsid, _mg)
        if cyc["backs"] == _extra:
            break
        _extra = cyc["backs"]
    cyl = cycle_lines(cyc, z)
    insl = ins_lines(cyc)
    _tip = "\n".join(cyl).replace("'", "")
    cyl_html = (f"<br><span title='{_tip}' style='display:inline;font-size:11px;font-weight:700;color:#ffd60a'>{cycle_short(cyc)}</span>" if cyl and (cyc["state"] != "持有" or not all(wok))
                else "<br>(目前已達 6/6,請開始執行)" if all(wok) else "")
    mk = lambda ok: "✔" if ok else "✖"
    wlines = (f"{mk(wok[0])} 本段曾 Z>1.5　{mk(wok[1])} 9 欄曾全 BUY<br>{mk(wok[2])} BUY 數≤3(現 {int(sum(now[c] == 'BUY' for c in XCOLS[:9]))})　{mk(wok[3])} 週月 KD 雙死叉<br>{mk(wok[4])} 本段 5 年乖離曾>15%(現 {pct(now['5年線乖離%'])})<br>{mk(wok[5])} 本段 90>120、120>150、150>180 曾同時全 BUY")
    wnote = ((f"本段自 {wstart:%Y-%m-%d} 全部買回重算" if wstart_ma == "buy" else
              f"本段自 {wstart:%Y-%m-%d} 站回 MA{model.SEG_MA}" if wstart_ma == "ma" else f"本段自 {wstart:%Y-%m-%d} Z 上穿 {model.SEG_RESET_Z:g}")
             if wstart is not None else "Z 目前在 0 以下") + (f"|首次 6/6:{wfirst:%Y-%m-%d}" if wfirst is not None and all(wok) else "")
    cards.append(("過熱轉弱警示", f"{sum(wok)} / 6{'　⚠' if all(wok) else ''}<small>{wlines}</small><small>{wnote}</small><div class='ptip{' hot' if all(wok) else ''}'>⚠ 6/6 成立須轉出：一半中華電、一半現金!!{cyl_html}</div>"))
    cards.append(("近一年最高價", f"{hi_px:,.2f}<small>{hi_dt:%Y-%m-%d}|目前收盤距高點 <b style='color:{'#d9534f' if dd < 0 else 'inherit'}'>{dd:+.1%}</b></small>"))
    cards.append(("距高點下跌 10~25% 對應指數", "".join(row(p) for p in (10, 15, 20, 25))))
    cards.append(("距高點下跌 30~40% 對應指數", "".join(row(p) for p in (30, 35, 40))))
    # 卡片排序(依你的箭頭):第一排 收盤、Z-SCORE、220日線、BUY 數、近一年最高價;第二排 季年線乖離、5/10年乖離、下跌對應指數 兩格、MAD
    assert len(cards) == 11
    cards = [cards[i] for i in (0, 7, 3, 1, 6, 8, 4, 5, 9, 10, 2)]     # 第一排:收盤、過熱轉弱警示、220日線、Z-SCORE、BUY 數
    # Z-SCORE 卡片整合三組數字(Z-SCORE / MAD ZSCORE / BUY 數),各用不同顏色與編號分區,避免看錯
    def zsec(color, label, big, lines):
        return (f"<div class=zsec style='border-left-color:{color}'><i class=zlab style='color:{color}'>{label}</i>"
                f"<i class=zbig>{big}</i>{''.join(f'<small>{x}</small>' for x in lines)}</div>")
    zhtml = (zsec("#1f6feb", "① Z-SCORE(480天)", f"{z:.2f}", [zread, f"Z低檔 {lo:.2f}｜Z高檔 {hi:.2f}"])
             + zsec("#8250df", "② MAD ZSCORE", f"{now['MAD ZSCORE']:.2f}", [f"MAD 低檔 {now['MAD 低檔']:.2f}｜高檔 {now['MAD 高檔']:.2f}"])
             + zsec("#d97706", "③ BUY 數(5>10 ~ 80>90 共 9 欄)", f"{len(buy9)} / 9",
                    ['、'.join(c.replace('天Z', '') for c in buy9) or '目前沒有 BUY', f"全部 12 欄:{sum(now[c] == 'BUY' for c in XCOLS)} 個"]))
    # ④ 動態 KD 摘要(與下方「日 / 週 / 月 動態 KD」表同一份資料,只是複製一份到上方)
    def kdline(n, v):
        col = "#d9534f" if v["state"] == "黃金交叉" else "#2e9e5b" if v["state"] == "死亡交叉" else "var(--mut)"
        tip = f"{n}KD K {v['K']:.1f}|D {v['D']:.1f}|K 合理低檔~高檔 {v['low']:.1f}~{v['high']:.1f}" + (f"|{v['zone']}" if v["zone"] else "")
        return (f"<div title='{tip}' style='display:flex;justify-content:space-between;gap:4px;font-size:12px;font-weight:700;line-height:1.55;white-space:nowrap'>"
                f"<span style='display:inline;font-size:12px;color:var(--fg)'>{n}KD {v['K']:.1f}/{v['D']:.1f}</span>"
                f"<span style='display:inline;font-size:12px;color:{col}'>{v['state']}{(' ' + run_txt(n)) if run_txt(n) else ''}</span></div>")
    zhtml += ("<div class=zsec style='border-left-color:#00897b'><i class=zlab style='color:#00897b'>④ 日 / 週 / 月 動態KD</i>"
              + "".join(kdline(n, v) for n, v in k.items()) + "</div>")
    zi = next(k for k, c in enumerate(cards) if c[0] == "Z-SCORE(480天)")
    cards[zi] = ("Z-SCORE 區(①藍 ②紫 ③橘 ④綠)", zhtml)
    cards = [c for c in cards if not c[0].startswith("5>10 ~ 80>90天Z")]
    # 220日線卡片整合四組數字(220日線訊號 / 近一年最高價 / 季年線乖離 / 5·10年線乖離),各用不同顏色與編號分區
    def wrapsec(color, label, html):
        return f"<div class=zsec style='border-left-color:{color}'><i class=zlab style='color:{color}'>{label}</i>{html}</div>"
    byt = {c[0]: c[1] for c in cards}
    ma_color = {"BUY": "#c62828", "SELL": "#2e7d32"}.get(ma_lab, "#1565c0")
    mhtml = (wrapsec(ma_color, "① 220日線 訊號", byt["220日線 ±"])
             + wrapsec("#0f9d8f", "② 近一年最高價", byt["近一年最高價"])
             + wrapsec("#c2185b", "③ 季線 / 年線乖離", byt["季線 / 年線乖離"])
             + wrapsec("#6d4c41", "④ 5年 / 10年線乖離", byt["5年 / 10年線乖離"]))
    mi = next(k for k, c in enumerate(cards) if c[0] == "220日線 ±")
    cards[mi] = ("220日線區(①~④ 分區顯示)", mhtml)
    cards = [c for c in cards if c[0] not in ("近一年最高價", "季線 / 年線乖離", "5年 / 10年線乖離")]
    # 美元兌台幣(含小走勢圖)移到「過熱轉弱警示」卡片下方,讓收盤卡片不要太長
    _w = next(k for k, c in enumerate(cards) if c[0] == "過熱轉弱警示")
    # 已收完月 K(日曆月,當月未過完不算):放在警示紅框下方、美元兌台幣上方
    _mc_col = "#d9534f" if mc["state"] == "黃金交叉" else "#2e9e5b" if mc["state"] == "死亡交叉" else "inherit"
    # 注意:卡片 CSS 有 .card span{display:block},所以這裡的 span 都要寫 display:inline
    # 寫成一行,並把美元兌台幣小走勢圖從 44px 壓到 26px,讓這張卡片總高度幾乎不變(不撐高第一排)
    # 一行顯示日期、交叉、K、D;12px 會超出卡片 232px 的內寬(208px),所以用 11px(實測約 201px)
    _s = "display:inline;font-size:11px"
    mc_html = (f"<div style='margin-top:6px;font-size:11px;font-weight:700;white-space:nowrap'>"
               f"<span style='{_s};font-weight:400;color:var(--mut)'>已收完月K {mc['date']:%m/%d}</span> "
               f"<span style='{_s};color:{_mc_col}'>{mc['state'] or '—'}</span> K {mc['K']:.1f} "
               f"<span style='{_s};font-weight:400;color:var(--mut)'>D {mc['D']:.1f}</span></div>")
    fx_html = re.sub(r"height:\s*44px", "height:26px", fx_html)                 # fx.py 小走勢圖原本 44px
    cards[_w] = (cards[_w][0], cards[_w][1] + mc_html + "<div style='margin-top:10px;border-top:1px solid var(--line);padding-top:2px'>" + fx_html + "</div>")
    # 距高點下跌 10~25% 與 30~40% 合併成一張(-10% ~ -40%)
    _i1 = next(k for k, c in enumerate(cards) if c[0].startswith("距高點下跌 10~25%"))
    _i2 = next(k for k, c in enumerate(cards) if c[0].startswith("距高點下跌 30~40%"))
    cards[_i1] = ("距高點下跌 10~40% 對應指數", cards[_i1][1] + cards[_i2][1])
    del cards[_i2]
    cards.insert(4, usma.card())                           # 美股四大指數 MA 通道狀態:放第一排最右邊(原 BUY 數卡片的位置)
    cards = [c for c in cards if c[0] != "MAD ZSCORE"]            # MAD 已整合進 Z-SCORE 卡片
    cards.append(("最高價回檔對應價(輸入最高價)", "<div class=cin><label>最高價<input id=cph type=number inputmode=decimal step=any value='" + f"{hi_px:.2f}" + "' aria-label='最高價'></label></div>" + "".join(f"<div class=lvr2 style='grid-template-columns:3em 1fr'><span>-{p}%</span><em id=ch{p}>—</em></div>" for p in range(10, 90, 10))))
    cards.append(("跌 2~20% 對應價(輸入股價)", "<div class=cin><label>股價<input id=cpy type=number inputmode=decimal step=any value='" + f"{now['台股收盤價']:.2f}" + "' aria-label='股價'></label></div>" + "".join(f"<div class=lvr2 style='grid-template-columns:3em 1fr'><span>-{p}%</span><em id=cy{p}>—</em></div>" for p in range(2, 22, 2))))
    crow = lambda p: f"<div class=lvr2><span>-{p}%</span><em id=cx{p}>—</em><u id=cs{p}>—</u></div>"
    chead = "<div class=lvr2 style='font-size:11px;color:var(--mut)'><span>跌幅</span><em>價格</em><u>可買股數</u></div>"
    cards.append(("跌幅對應價與可買股數", f"<div class=cin><label>可用資金<input id=ccap type=number inputmode=decimal step=any placeholder='例:1000000' aria-label='可用資金'></label><label>股價<input id=cpx type=number inputmode=decimal step=any value='{now['台股收盤價']:.2f}' aria-label='股價'></label></div>{chead}{''.join(crow(p) for p in range(5, 45, 5))}"))
    cards.append(("跌幅對應價與可買股數(續)", chead + "".join(crow(p) for p in range(45, 65, 5)) + "<small>股數 = 可用資金 ÷ 對應價(無條件捨去,不含手續費)</small>"))
    wcls = "w3" if all(wok) else "w2" if sum(wok) >= 4 else "w1"                   # 警示卡底色:全中=紅、4~5 項=黃、其餘=綠
    mcls = {"BUY": "m_buy", "SELL": "m_sell"}.get(ma_lab, "m_mid")                  # 220日線底色:BUY=紅(台股慣例)、SELL=綠、其餘=藍灰
    _pal = ["#1565c0", "#0f9d8f", "#c2185b", "#e08a00", "#7b3fc9"]
    cards_html = "".join(
        f"<div class='card{' ' + wcls if a == '過熱轉弱警示' else ' ' + mcls if a.startswith('220日線') else ''}'>"
        f"<span class=ct style='color:{_pal[k % 5]};border-bottom-color:{_pal[k % 5]}'>{a}</span><b>{b}</b></div>"
        for k, (a, b) in enumerate(cards))
    kd_rows = "".join(
        f"<tr><td>{n}KD</td><td>{v['K']:.1f}</td><td>{v['D']:.1f}</td><td>{v['low']:.1f} ~ {v['high']:.1f}</td>"
        f"<td class='{'hi' if v['zone'] == 'K值高檔' else 'lo' if v['zone'] == 'K值低檔' else ''}'>{v['zone'] or '—'}</td><td class='{'gold' if v['state'] == '黃金交叉' else 'dead' if v['state'] == '死亡交叉' else ''}'>{v['state']}{kd_run_html[n]}</td></tr>"
        for n, v in k.items())

    cols = ["開盤價", "最高價", "最低價", "台股收盤價", "20日均線", "60日均線", "220日均線", "240日均線",
            "生命線60*3%", "BUY(220日)2%", "SELL(220日)1%", "季線乖離", "年線乖離", "5年線乖離%", "10年線乖離%",
            "Z-SCORE", "Z低檔", "Z高檔", "Z方向", "MAD ZSCORE"] + ZCOLS + XCOLS + ["週KD", "月KD"]
    head = "".join(f"<th class='{'xh xc' if c in XCOLS else ''}'>{c.replace('台股', '')}</th>" for c in ["日期"] + cols)
    body = ""
    for d, r in m.iloc[::-1].head(TABLE_DAYS).iterrows():
        body += f"<tr class=r><td>{d:%Y-%m-%d}</td>{''.join(cell(c, r) for c in cols)}</tr>"

    c1 = chart(m.tail(CHART_DAYS), [("台股收盤價", "#1f77b4", 1.5, None), ("20日均線", "#f0ad4e", 1, None), ("60日均線", "#8e44ad", 1, None),
                                   ("220日均線", "#d9534f", 1.4, None), ("240日均線", "#2e9e5b", 1.4, None)], "台股加權指數 與均線")
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
.card.m_buy{{background:#fdecea;box-shadow:inset 0 0 0 2px #e0857c}}.card.m_sell{{background:#e5f4ea;box-shadow:inset 0 0 0 2px #8fcba5}}.card.m_mid{{background:#e8f0fb;box-shadow:inset 0 0 0 2px #9db9e3}}
.card.w3{{background:#fdecea;box-shadow:inset 0 0 0 2px #e0857c}}.card.w2{{background:#fff4d6;box-shadow:inset 0 0 0 2px #e3bd52}}.card.w1{{background:#e5f4ea;box-shadow:inset 0 0 0 2px #8fcba5}}
@media(prefers-color-scheme:dark){{.card.m_buy{{background:#4a2326;box-shadow:inset 0 0 0 2px #b9534b}}.card.m_sell{{background:#1f3b2a;box-shadow:inset 0 0 0 2px #3f8a5c}}.card.m_mid{{background:#1f2f4a;box-shadow:inset 0 0 0 2px #4a6fa5}}.card.w3{{background:#4a2326;box-shadow:inset 0 0 0 2px #b9534b}}.card.w2{{background:#4a3d1c;box-shadow:inset 0 0 0 2px #a98a2e}}.card.w1{{background:#1f3b2a;box-shadow:inset 0 0 0 2px #3f8a5c}}}}
.card .usr{{display:grid;grid-template-columns:1fr auto;column-gap:6px;margin:2px 0 6px;font-weight:400}}.card .usr b{{font-size:14px}}.card .usr em{{font-style:normal;font-weight:700;font-size:14px;text-align:right}}.card .usr small{{grid-column:1/3;font-size:11px;color:var(--mut);line-height:1.3}}
.card .ptip{{margin-top:8px;padding:6px 8px;border-radius:6px;background:#c1121f;color:#fff;font-size:13px;font-weight:800;line-height:1.4;border:2px solid #ffd60a}}.card .ptip.hot{{animation:ptipb 1.6s ease-in-out infinite}}@keyframes ptipb{{50%{{background:#ff6b00}}}}@media(prefers-reduced-motion:reduce){{.card .ptip.hot{{animation:none}}}}
.card .zsec{{border-left:5px solid;padding:2px 0 3px 8px;margin:8px 0 6px;border-radius:2px}}.card .zlab{{display:block;font-style:normal;font-size:12px;font-weight:800}}.card .zbig{{display:block;font-style:normal;font-size:22px;font-weight:700;line-height:1.25}}
.cin{{display:flex;gap:6px;margin:4px 0 6px}}.cin label{{flex:1;min-width:0;font-size:11px;font-weight:400;color:var(--mut)}}.cin input{{width:100%;box-sizing:border-box;font-size:16px;font-weight:700;padding:4px 6px;border:1px solid var(--mut);border-radius:6px;background:transparent;color:inherit}}
.lvr2{{display:grid;grid-template-columns:3em 1fr 1fr;gap:4px;font-size:14px;font-weight:400;line-height:1.6;font-variant-numeric:tabular-nums}}.lvr2 em{{font-style:normal;font-weight:700;text-align:right}}.lvr2 u{{text-decoration:none;text-align:right;color:var(--mut)}}
.card span{{display:block;font-size:12px;color:var(--mut)}}.card>span.ct{{font-size:15px;font-weight:800;padding-bottom:4px;margin-bottom:6px;border-bottom:2px solid;line-height:1.3}}.card b{{font-size:20px}}.lvr{{display:grid;grid-template-columns:3.4em 1.6em 1fr;font-size:14px;font-weight:400;line-height:1.55;font-variant-numeric:tabular-nums}}.lvr span{{color:var(--mut)}}.lvr i{{font-style:normal;color:var(--mut)}}.lvr em{{font-style:normal;font-weight:700;text-align:right;padding-right:30%}}.card small{{display:block;font-size:12px;font-weight:400;color:var(--mut)}}
.hd{{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap}}.hl{{flex:1 1 520px;min-width:0}}.memo{{flex:0 1 380px;min-width:260px;margin-top:2px}}.memo .mh{{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;font-size:14px}}.memo textarea{{width:100%;box-sizing:border-box;height:122px;resize:vertical;font:inherit;font-size:14px;line-height:1.6;padding:8px 10px;border:2px solid #f2b705;border-radius:8px;background:var(--card);color:var(--fg)}}.memo button{{font:inherit;font-size:12px;padding:3px 10px;border:1px solid var(--mut);border-radius:6px;background:transparent;color:var(--fg);cursor:pointer}}.hrow{{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin:-6px 0 -4px}}.hrow h1{{margin:0}}.rules{{flex:1 1 250px;min-width:250px;max-width:312px;box-sizing:border-box;border:2px solid #d9534f;border-radius:8px;padding:3px 9px;font-size:11.5px;line-height:1.4;background:var(--card)}}.rules b.t{{font-size:12.5px}}.rules span{{color:var(--mut)}}
table{{border-collapse:collapse;font-size:13px;width:100%}}th,td{{padding:4px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}
th:first-child,td:first-child{{text-align:left}}.wrap{{overflow-x:auto}}.wrap td:first-child,.wrap th:first-child{{position:sticky;left:0;background:var(--bg)}}td.hi{{background:var(--hi)}}td.pk{{background:var(--pk)}}td.gr{{background:var(--gr)}}.neg{{color:#d9534f;font-weight:700}}th.xh{{background:#ffe3a3;color:#222}}
p.n{{color:var(--mut);font-size:13px}}.gold{{color:#d9534f;font-weight:700}}.dead{{color:#2e9e5b;font-weight:700}}
.status{{background:var(--card);padding:8px 12px;border-radius:6px;font-size:14px}}tr.buy td:nth-child(2){{color:#d9534f;font-weight:700}}
tr.sell td:nth-child(2){{color:#2e9e5b;font-weight:700}}summary{{cursor:pointer;margin:8px 0;font-weight:600}}{CSS2}{CSS_TREND}{CSS_INS}</style></head><body>
<div class=hd><div class=hl>
<nav style="display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px">
<span style="padding:7px 14px;border-radius:999px;background:#222;color:#fff;font-size:14px;font-weight:600">📈 Z-SCORE 與動態 KD</span>
<a href="https://yopoyuan-star.github.io/MA200-240/" style="padding:7px 14px;border-radius:999px;background:#eef1f5;color:#1a5fb4;font-size:14px;font-weight:600;text-decoration:none">📊 MA220/240 均線訊號(台股/美股) →</a>
<a href="https://yopoyuan-star.github.io/Pyramid-Layout-Spreadsheet/" style="padding:7px 14px;border-radius:999px;background:#eef1f5;color:#1a5fb4;font-size:14px;font-weight:600;text-decoration:none">🔺 金字塔加碼試算 →</a>
<a href="https://www.wantgoo.com/stock/margin-trading/exclude-etf/taiex" target="_blank" rel="noopener" title="玩股網:大盤融資融券(排除 ETF)" style="padding:7px 12px;border-radius:999px;background:#eef1f5;color:#1a5fb4;font-size:14px;font-weight:600;text-decoration:none">📊 大盤融資 ↗</a></nav>
<div class=hrow><h1>480天 Z-SCORE 與日週月動態 KD</h1>
<div class=rules><b class=t>📋 買賣規則</b><span title="G1 規則、空手時一半中華電一半現金;加權指數(不含息)2006~2026 近 20 年回測(g1_halfcht.py)。0050 含息:近 15 年 22.2%、近 10 年 28.5%,最大回撤 −15.4%">　近20年年化 16.7%、回撤 −31.8%</span><div title="6/6 本段重算:Z 向上穿越 {model.SEG_RESET_Z:g},或加權指數跌破 {model.SEG_MA} 日線至少 {model.SEG_MA_MIN_BELOW} 個交易日後再站回;或右側全部買回當天">① <b>轉出</b>:6/6 全成立→<b>一半中華電、一半現金</b></div><div title="距一年高點 −10/−15/−20/−25/−30% 各買 5/7.5/10/12.5/15%(占總資金,左側合計 50%);Z&lt;−2.5 直接補到 50%">② <b>左側</b>:跌 10~30% 分 5 筆買,共 50%</div><div title="先決(三選一):Z≤0、距一年高點跌 20%、轉出滿 12 個月;成立後已收完月K KD 金叉 → 全部買回。保險:全部買回後收盤跌破買回均價 20% → 再轉出">③ <b>右側</b>:跌20%或Z≤0後,月KD金叉全買</div></div></div>
<p class=n>資料日期:<b>{m.index[-1]:%Y-%m-%d}</b>|頁面更新:{stamp:%Y-%m-%d %H:%M}(台北)|資料來源:臺灣證券交易所 加權指數歷史資料|
<a href="zscore_output.csv">下載最近 {CSV_DAYS} 天完整欄位 CSV</a></p>
</div><div class=memo><div class=mh><b>📝 筆記</b><button type=button id=zmemoclr>清除筆記</button></div><textarea id=zmemo maxlength=3000 placeholder="在這裡做筆記(自動儲存在這個瀏覽器)"></textarea></div></div>
{ins_html(cyc)}
{trend_html(trend, m.index[-1])}
<div class=cards>{cards_html}</div>
<h2>日 / 週 / 月 動態 KD</h2><div class=wrap><table><tr><th>週期</th><th>K</th><th>D</th><th>K 合理低檔 ~ 高檔</th><th>位階</th><th>K 與 D</th></tr>{kd_rows}</table></div>
<p class=n>動態:以最新一天為終點,週 K=5 個交易日、月 K=22 個交易日,KD 取 9 根;黃金交叉 = K&gt;D、死亡交叉 = K&lt;D;「連 N 日」= 目前的交叉狀態已連續 N 個交易日。</p>
{ma_html}
{c1}{c5}{c6}{c4}{c2}{c3}
<h2>最近 {TABLE_DAYS} 個交易日(Z-SCORE &gt; {ZHOT} 粉紅底、&lt; 0 紅字;當天 Z-SCORE 大於某天期 Z-SCORE → 該格粉紅底;收盤高於 20/60/220/240 日線 → 該均線格粉紅、低於 → 淡綠)</h2>
<div class=ctl>顯示列數:<button data-n=60>60</button><button data-n=120>120</button><button data-n=200>200</button>
<span style="margin-left:14px">Z 交叉欄(5&gt;10 … 150&gt;180):</span><button id=xt>隱藏</button></div>
<div class="wrap big"><table id=bigtbl><tr>{head}</tr>{body}</table></div><script>{JS}</script><script>{JS2}</script>
<p class=n>本頁欄位對應 Excel「480天Z-SCORE -2.0」工作表。僅供研究參考,非投資建議。</p></body></html>"""
    os.makedirs("docs", exist_ok=True)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(page)
    m.tail(CSV_DAYS).to_csv(OUT_CSV, encoding="utf-8-sig", float_format="%.4f")
    import notify
    fxd = fx.summary(fx_rows)
    insd = inst.summary(inst_data)
    kdl = "\n".join(f"{n}KD  K {v['K']:.1f}|D {v['D']:.1f}|{v['state']}{(' ' + run_txt(n)) if run_txt(n) else ''}\n    合理低~高檔 {v['low']:.1f}~{v['high']:.1f}|{v['zone'] or '—'}"
                    for n, v in k.items())
    summary = (f"📊 加權指數日報 {m.index[-1]:%Y-%m-%d}\n"
               f"收盤 {now['台股收盤價']:,.2f}  {arrow} {abs(chg):,.2f}({chg_pct:+.2%})\n"
               f"多空狀態:{trend['state']}\n    {trend['reason']}\n"
               f"Z-SCORE(480天) {z:.2f}({zread})\n    Z低檔 {lo:.2f}|Z高檔 {hi:.2f}\n"
               f"220日線 {ma_lab}|MA220 {num(now['220日均線'])}{('|年線' + tr_txt + '(' + tr_note.replace('MA220 ', '') + ')') if tr_txt else ''}\n    {ma_note.replace('|', '|')}\n"
               f"生命線 60×3%:{now['生命線60*3%'] or '—'}\n"
               f"BUY 數 {len(buy9)}/9|全部 12 欄 {sum(now[c] == 'BUY' for c in XCOLS)} 個\n"
               f"近一年最高 {hi_px:,.2f}({hi_dt:%Y-%m-%d})|距高點 {dd:+.1%}\n"
               f"季線 / 年線乖離 {pct(now['季線乖離'])} / {pct(now['年線乖離'])}\n"
               f"5年 / 10年線乖離 {pct(now['5年線乖離%'])} / {pct(now['10年線乖離%'])}\n"
               f"MAD ZSCORE {now['MAD ZSCORE']:.2f}(低 {now['MAD 低檔']:.2f}|高 {now['MAD 高檔']:.2f})\n"
               f"{fxd['text'] if fxd else '美元兌台幣 暫無資料'}\n"
               f"{insd['text'] if insd else '三大法人/外資期貨 暫無資料'}\n"
               f"過熱轉弱警示 {sum(wok)}/6:曾Z>1.5 {mk(wok[0])}|9欄曾全BUY {mk(wok[1])}|BUY≤3 {mk(wok[2])}|週月KD雙死叉 {mk(wok[3])}|5年乖離曾>15% {mk(wok[4])}|90>120~150>180曾全BUY {mk(wok[5])}\n"
               f"⚠ 6/6 成立須轉出：一半中華電、一半現金!!{'' if cyl else '(目前已達 6/6,請開始執行)' if all(wok) else ''}\n"
               + "".join(f"    {t}\n" for t in cyl + insl) +
               f"{kdl}\n\n詳細頁面:{PAGE_URL}")
    import flexmsg
    fd = dict(date=f"{m.index[-1]:%Y-%m-%d}", close=now["台股收盤價"], chg=chg, chg_pct=chg_pct,
              ma200_sig=ma_lab, ma200_note=ma_note, ma200=now["220日均線"], ma200_trend=(f"年線{tr_txt}({tr_note.replace('MA220 ', '')})" if tr_txt else ""), life=now["生命線60*3%"] or "—",
              buy9=len(buy9), z=z, zread=zread, zlo=lo, zhi=hi, mad=now["MAD ZSCORE"], madlo=now["MAD 低檔"], madhi=now["MAD 高檔"],
              q_y=f"{pct(now['季線乖離'])} / {pct(now['年線乖離'])}", y5_10=f"{pct(now['5年線乖離%'])} / {pct(now['10年線乖離%'])}",
              hi_px=hi_px, hi_dt=f"{hi_dt:%Y-%m-%d}", dd=dd, trend=trend["state"], trend_reason=trend["reason"],
              kd=[(f"{n}KD", v["K"], v["D"], v["state"], v["zone"], v["low"], v["high"], run_txt(n)) for n, v in k.items()],
              warn=list(zip(["本段 Z 曾大於 1.5", "本段 9 欄曾同時全 BUY", "BUY 數剩 3 個以下", "週、月 KD 雙死叉", "本段 5 年乖離曾大於 15%", "本段 90>120、120>150、150>180 曾同時全 BUY"], wok)),
              warn_n=sum(wok), cycle=cyl + insl, url=PAGE_URL, fx=fxd, inst=insd)
    notify.run(m, summary, flexmsg.bubble(fd), flexmsg.alt_text(fd))                          # 每天發日報;連續第 3 天突破/跌破時,日報最上面加警示
    print(f"完成:資料至 {m.index[-1]:%Y-%m-%d},Z={z:.2f},週KD {k['週']['state']},月KD {k['月']['state']}")


if __name__ == "__main__":
    main()
