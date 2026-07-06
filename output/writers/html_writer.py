# -*- coding: utf-8 -*-
"""
HTML 报告输出（默认格式）。改造自 quant_debate/templates/renderer.py，
字段对齐新的 reports 结构（agents/parsers.py 产出的 dict，而非 Claude
手写的富 HTML 字符串）。

每次分析生成一个带时间戳的独立文件：output/reports/{symbol}_{时间戳}.html
（沿用原项目 Feishu 集成之前的做法——本地文件场景下没有"避免飞书文档每天
重复"的负担，多个独立文件反而方便按时间线直接打开对比）。
"""

import os
from datetime import datetime

from agents.parsers import markdown_to_html

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "templates", "report.html")


def _safe(val, default="N/A"):
    if val is None or val == "" or (isinstance(val, float) and str(val) == "nan"):
        return default
    return str(val)


def _fmt_price(val) -> str:
    return f"¥{val}" if val is not None else "未设定"


def _verdict_class(text: str) -> str:
    text = (text or "").lower()
    if any(k in text for k in ["买入", "看多", "利好", "bullish", "积极"]):
        return "verdict-bullish"
    if any(k in text for k in ["卖出", "减仓", "看空", "利空", "bearish", "清仓", "不可用"]):
        return "verdict-bearish"
    return "verdict-neutral"


def _decision_badge(decision: str) -> str:
    d = (decision or "").lower()
    if any(k in d for k in ["买入", "加仓"]):
        return "badge-buy"
    if any(k in d for k in ["卖出", "减仓", "清仓"]):
        return "badge-sell"
    return "badge-hold"


def _price_color(change_pct) -> str:
    try:
        return "up" if float(change_pct) >= 0 else "down"
    except (TypeError, ValueError):
        return "up"


def _chip_margin_table(chip: dict, margin: dict, dragon: dict, northbound_stock: dict) -> str:
    rows = ""
    chip_ok = isinstance(chip, dict) and "error" not in chip
    for label, val in [
        ("筹码获利比例", f"{chip.get('获利比例','--')}%" if chip_ok else "暂不可用"),
        ("筹码平均成本", f"¥{chip.get('平均成本','--')}" if chip_ok else "--"),
        ("90%筹码集中度", chip.get('90集中度', '--') if chip_ok else "--"),
        ("70%筹码集中度", chip.get('70集中度', '--') if chip_ok else "--"),
    ]:
        color = "color:var(--muted)" if val in ("--", "暂不可用") else ""
        rows += f"<tr><td style='color:var(--muted)'>{label}</td><td style='{color}'><strong>{val}</strong></td></tr>"

    if isinstance(margin, dict) and "error" not in margin:
        rz = margin.get("融资余额") or 0
        rq = margin.get("融券余量") or 0
        d = margin.get("数据日期", "")
        margin_text = f"融资余额 {int(float(rz or 0) / 1e8):.1f}亿 / 融券余量 {int(rq or 0):,}股（{d}）"
    else:
        margin_text = "<span style='color:var(--muted)'>暂无数据</span>"
    rows += f"<tr><td style='color:var(--muted)'>融资融券</td><td>{margin_text}</td></tr>"

    dragon_text = "<span style='color:var(--muted)'>无上榜记录</span>"
    if isinstance(dragon, dict) and "error" not in dragon:
        cnt = dragon.get("上榜次数")
        if cnt:
            dragon_text = f"近90日上榜 <strong>{cnt}</strong> 次"
        elif dragon.get("近90日龙虎榜"):
            dragon_text = f"<span style='color:var(--muted)'>{dragon['近90日龙虎榜']}</span>"
    rows += f"<tr><td style='color:var(--muted)'>近90日龙虎榜</td><td>{dragon_text}</td></tr>"

    if isinstance(northbound_stock, dict) and "error" not in northbound_stock and "持有情况" not in northbound_stock:
        pct = northbound_stock.get("持股占A股百分比", "")
        inc = northbound_stock.get("今日增持股数", 0) or 0
        dt = northbound_stock.get("数据日期", "")
        inc_str = (f"+{int(inc):,}" if inc > 0 else f"{int(inc):,}") if inc else "0"
        nb_text = f"持股占A股 <strong>{pct}%</strong> / 增持{inc_str}股（{dt[:10]}）"
    elif isinstance(northbound_stock, dict) and "持有情况" in northbound_stock:
        nb_text = f"<span style='color:var(--muted)'>{northbound_stock['持有情况']}</span>"
    else:
        nb_text = "<span style='color:var(--muted)'>暂无数据</span>"
    rows += f"<tr><td style='color:var(--muted)'>北向持股</td><td>{nb_text}</td></tr>"

    return f"<table><tbody>{rows}</tbody></table>"


def _decision_points_html(errors: dict) -> str:
    if not errors:
        return ""
    items = "".join(
        f"<div class='keypoint'><div class='dot' style='background:var(--red)'></div>"
        f"<div>Agent {k} 本次调用失败：{v}</div></div>"
        for k, v in errors.items()
    )
    return f"<h3>⚠️ 本次分析异常提示</h3><div style='margin-bottom:12px'>{items}</div>"


def _watchpoints_html(e_body: str) -> str:
    html = markdown_to_html(e_body)
    return f"<div class='watchpoint' style='grid-column:1/-1'>{html}</div>"


def _history_timeline(history: list) -> str:
    if not history:
        return '<div style="color:var(--muted);font-size:13px">首次分析，暂无历史记录</div>'
    html = ""
    for h in reversed(history[-8:]):
        outcome = h.get("actual_outcome")
        outcome_tag = ""
        if outcome == "correct":
            outcome_tag = '<span style="color:var(--green);font-size:11px"> ✓ 判断正确</span>'
        elif outcome == "wrong":
            outcome_tag = '<span style="color:var(--red);font-size:11px"> ✗ 判断错误</span>'
        html += f"""<div class="timeline-item">
          <div class="t-date">{h.get('date','')[:10]}</div>
          <div class="t-content">
            <strong>{h.get('decision','?')}</strong>（置信度{h.get('confidence','?')}%）
            @ ¥{h.get('price_at_analysis','?')}
            {outcome_tag}
            <div style="color:var(--muted);font-size:12px;margin-top:4px">{h.get('summary','')}</div>
          </div>
        </div>"""
    return html


def render(data: dict, reports: dict, profile: dict) -> str:
    """
    data: fetcher.py 输出
    reports: orchestrator.run_debate() 返回的 dict（含 A/B/C/D/E/errors）
    profile: memory.manager 的股票档案
    """
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        tmpl = f.read()

    realtime = data.get("realtime", {})
    kline = data.get("kline", {})
    chip = data.get("chip", {})
    margin = data.get("margin", {})
    dragon = data.get("dragon_tiger", {})
    nb_stock = data.get("northbound_stock", {})
    e = reports.get("E", {})

    change_pct = realtime.get("涨跌幅", 0)
    replacements = {
        "{{symbol}}": data.get("stock", ""),
        "{{stock_name}}": realtime.get("名称", ""),
        "{{industry}}": "",
        "{{date}}": data.get("fetch_time", "")[:10],
        "{{fetch_time}}": data.get("fetch_time", ""),
        "{{price}}": _safe(realtime.get("最新价")),
        "{{change_pct}}": f"{'+' if float(change_pct or 0) >= 0 else ''}{change_pct}",
        "{{change_amt}}": _safe(realtime.get("涨跌额")),
        "{{price_color}}": _price_color(change_pct),
        "{{pe}}": _safe(realtime.get("市盈率TTM")),
        "{{market_cap}}": _safe(realtime.get("总市值_亿")),
        "{{ma5}}": _safe(kline.get("MA5")),
        "{{ma20}}": _safe(kline.get("MA20")),
        "{{vol_ratio}}": _safe(kline.get("量比")),
        # E决策
        "{{decision}}": e.get("decision", "分析中"),
        "{{decision_badge}}": _decision_badge(e.get("decision", "")),
        "{{confidence}}": str(e.get("confidence", 0)),
        "{{stop_loss}}": _fmt_price(e.get("stop_loss")),
        "{{target}}": _fmt_price(e.get("target")),
        "{{decision_points}}": _decision_points_html(reports.get("errors", {})),
        "{{watchpoints}}": _watchpoints_html(e.get("body", "")),
        # A/B/C/D 通用字段
        "{{a_verdict}}": reports.get("A", {}).get("verdict", "中性"),
        "{{a_verdict_class}}": _verdict_class(reports.get("A", {}).get("verdict", "")),
        "{{a_body}}": markdown_to_html(reports.get("A", {}).get("body", "")),
        "{{a_note}}": reports.get("A", {}).get("note", ""),
        "{{b_verdict}}": reports.get("B", {}).get("verdict", "中性"),
        "{{b_verdict_class}}": _verdict_class(reports.get("B", {}).get("verdict", "")),
        "{{b_body}}": markdown_to_html(reports.get("B", {}).get("body", "")),
        "{{b_note}}": reports.get("B", {}).get("note", ""),
        "{{c_verdict}}": reports.get("C", {}).get("verdict", "中性"),
        "{{c_verdict_class}}": _verdict_class(reports.get("C", {}).get("verdict", "")),
        "{{c_data_table}}": _chip_margin_table(chip, margin, dragon, nb_stock),
        "{{c_body}}": markdown_to_html(reports.get("C", {}).get("body", "")),
        "{{c_note}}": reports.get("C", {}).get("note", ""),
        "{{d_verdict}}": reports.get("D", {}).get("verdict", "中性"),
        "{{d_verdict_class}}": _verdict_class(reports.get("D", {}).get("verdict", "")),
        "{{d_body}}": markdown_to_html(reports.get("D", {}).get("body", "")),
        "{{d_note}}": reports.get("D", {}).get("note", ""),
        # 历史
        "{{history_timeline}}": _history_timeline(profile.get("analysis_history", [])),
    }

    for k, v in replacements.items():
        tmpl = tmpl.replace(k, str(v) if v is not None else "")

    return tmpl


def save_report(data: dict, reports: dict, profile: dict, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    symbol = data.get("stock", "unknown")
    filename = f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
    path = os.path.join(output_dir, filename)
    html = render(data, reports, profile)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
