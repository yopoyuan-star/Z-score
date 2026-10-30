"""LINE Flex Message 日報(卡片版面,可上色、對齊)。台股慣例:漲/黃金交叉=紅,跌/死亡交叉=綠。"""
RED, GREEN, GRAY, DARK, SOFT = "#D9534F", "#2E9E5B", "#8A8F98", "#222222", "#F4F5F7"


def _t(text, **kw):
    return {"type": "text", "text": str(text), "wrap": True, **kw}


def row(label, value, color=DARK, bold=False, sub=None):
    right = [_t(value, size="sm", align="end", color=color, weight="bold" if bold else "regular", flex=6)]
    left = [_t(label, size="sm", color=GRAY, flex=4)]
    items = [{"type": "box", "layout": "baseline", "contents": left + right}]
    if sub:
        items.append(_t(sub, size="xs", color=GRAY, align="end"))
    return {"type": "box", "layout": "vertical", "spacing": "xs", "contents": items}


def section(title, rows):
    return {"type": "box", "layout": "vertical", "spacing": "sm", "margin": "lg", "contents": [
        {"type": "separator", "color": "#E3E5E8"},
        _t(title, size="sm", weight="bold", color=DARK, margin="md"), *rows]}


def kd_row(name, k, d, state, zone, lo, hi):
    col = RED if state == "黃金交叉" else GREEN if state == "死亡交叉" else DARK
    return {"type": "box", "layout": "vertical", "spacing": "xs", "contents": [
        {"type": "box", "layout": "baseline", "contents": [
            _t(name, size="sm", weight="bold", flex=2),
            _t(f"K {k:.1f}｜D {d:.1f}", size="sm", flex=5, color=DARK),
            _t(state, size="sm", weight="bold", color=col, align="end", flex=3)]},
        _t(f"合理低~高檔 {lo:.1f}~{hi:.1f}" + (f"｜{zone}" if zone else ""), size="xs", color=GRAY)]}


def bubble(d):
    """d: dict,欄位見 build.py 組裝處。"""
    up = d["chg"] > 0
    chg_col = RED if up else GREEN if d["chg"] < 0 else GRAY
    arrow = "▲" if up else "▼" if d["chg"] < 0 else "－"
    warn_n, warn_all = d["warn_n"], d["warn_n"] == len(d["warn"])
    body = [
        _t(f"{d['close']:,.2f}", size="3xl", weight="bold", color=DARK),
        _t(f"{arrow} {abs(d['chg']):,.2f}　({d['chg_pct']:+.2%})", size="md", weight="bold", color=chg_col),
        section("趨勢訊號", [
            row("200日線", d["ma200_sig"], color=RED if d["ma200_sig"] == "BUY" else GREEN if d["ma200_sig"] == "SELL" else DARK, bold=True,
                sub=f"MA200 {d['ma200']:,.2f}"),
            row("生命線 60×3%", d["life"]),
            row("BUY 數(5>10~80>90)", f"{d['buy9']} / 9")]),
        section("Z-SCORE", [
            row("Z-SCORE(480天)", f"{d['z']:.2f}", bold=True, sub=d["zread"]),
            row("Z低檔｜Z高檔", f"{d['zlo']:.2f}｜{d['zhi']:.2f}"),
            row("MAD ZSCORE", f"{d['mad']:.2f}", sub=f"低 {d['madlo']:.2f}｜高 {d['madhi']:.2f}")]),
        section("乖離與高點", [
            row("季線 / 年線乖離", d["q_y"]),
            row("5年 / 10年線乖離", d["y5_10"]),
            row("近一年最高", f"{d['hi_px']:,.2f}", sub=d["hi_dt"]),
            row("距高點", f"{d['dd']:+.1%}", color=RED if d["dd"] < 0 else DARK, bold=True)]),
        section("動態 KD", [kd_row(*x) for x in d["kd"]]),
        section(f"過熱轉弱警示 {warn_n}/{len(d['warn'])}" + (" ⚠" if warn_all else ""),
                [_t(f"{'✔' if ok else '✖'} {name}", size="sm", color=RED if ok else GRAY) for name, ok in d["warn"]]),
    ]
    return {"type": "bubble", "size": "mega",
            "header": {"type": "box", "layout": "vertical", "backgroundColor": SOFT, "paddingAll": "lg", "contents": [
                _t("📊 加權指數日報", size="lg", weight="bold"), _t(f"資料日期 {d['date']}", size="xs", color=GRAY)]},
            "body": {"type": "box", "layout": "vertical", "paddingAll": "lg", "contents": body},
            "footer": {"type": "box", "layout": "vertical", "contents": [
                {"type": "button", "style": "primary", "color": "#06C755", "height": "sm",
                 "action": {"type": "uri", "label": "查看完整頁面", "uri": d["url"]}},
                _t("僅供研究參考,非投資建議", size="xxs", color=GRAY, align="center", margin="md")]}}


def alt_text(d):
    arrow = "▲" if d["chg"] > 0 else "▼" if d["chg"] < 0 else "－"
    return f"加權 {d['close']:,.2f} {arrow}{abs(d['chg']):,.2f}({d['chg_pct']:+.2%})｜預警 {d['warn_n']}/{len(d['warn'])}｜Z {d['z']:.2f}"
