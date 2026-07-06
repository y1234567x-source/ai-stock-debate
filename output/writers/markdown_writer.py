# -*- coding: utf-8 -*-
"""
Markdown 报告输出（可选附加格式，--output-format md 时启用）。

与 HTML 输出保持一致的简单策略：每次分析生成一个带时间戳的独立文件
（output/reports/{symbol}_{时间戳}.md），不做增量单文件追加。原因：
增量追加需要用锚点定位区块做替换，一旦文件被用户手动编辑过锚点就可能
丢失，鲁棒性成本明显高于收益；而记忆机制本身（memory/profiles/{symbol}.json）
已经承担了"越用越懂这支股票"的核心价值，与本地报告文件是否合并无关。
"""

import os
from datetime import datetime


def _fmt_price(val) -> str:
    return f"¥{val}" if val is not None else "未设定"


def _fmt_agent_section(title: str, report: dict) -> str:
    verdict = report.get("verdict", "")
    body = report.get("body", "")
    note = report.get("note", "")
    lines = [f"### {title}", "", f"**结论：{verdict}**", "", body or "（无内容）"]
    if note:
        lines += ["", f"> 笔记：{note}"]
    return "\n".join(lines)


def render(data: dict, reports: dict, profile: dict) -> str:
    r = data.get("realtime", {})
    e = reports.get("E", {})
    fetch_time = data.get("fetch_time", "")
    stock = data.get("stock", "")
    name = r.get("名称", "")
    errors = reports.get("errors", {})

    lines = [
        f"# {name}（{stock}）投研分析 · {fetch_time[:10]}",
        "",
        f"数据获取时间：{fetch_time}",
        "",
        "## 当前行情",
        "",
        f"- 最新价：¥{r.get('最新价', '?')}（{r.get('涨跌幅', '?')}%）",
        f"- PE(TTM)：{r.get('市盈率TTM', '?')}x | 总市值：{r.get('总市值_亿', '?')}亿",
        f"- 今开 ¥{r.get('今开', '?')} 最高 ¥{r.get('最高', '?')} 最低 ¥{r.get('最低', '?')} 昨收 ¥{r.get('昨收', '?')}",
        "",
        "## E · 最终裁决",
        "",
        f"**操作方向：{e.get('decision', '')}**（置信度 {e.get('confidence', '?')}%）",
        "",
        f"- 止损位：{_fmt_price(e.get('stop_loss'))}",
        f"- 目标价：{_fmt_price(e.get('target'))}",
        "",
        e.get("body", ""),
    ]

    if errors:
        lines += ["", "## ⚠️ 本次分析异常提示", ""]
        for k, v in errors.items():
            lines.append(f"- Agent {k} 本次调用失败：{v}")

    lines += [
        "",
        "---",
        "",
        _fmt_agent_section("A · 新闻信息官", reports.get("A", {})),
        "",
        _fmt_agent_section("B · 基本面研究员", reports.get("B", {})),
        "",
        _fmt_agent_section("C · 技术分析师", reports.get("C", {})),
        "",
        _fmt_agent_section("D · 行业宏观分析师", reports.get("D", {})),
    ]

    return "\n".join(lines)


def save_report(data: dict, reports: dict, profile: dict, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    symbol = data.get("stock", "unknown")
    filename = f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    path = os.path.join(output_dir, filename)
    content = render(data, reports, profile)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path
