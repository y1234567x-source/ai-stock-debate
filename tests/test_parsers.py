# -*- coding: utf-8 -*-
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.parsers import parse_agent_e, extract_note, strip_note
from agents.prompts import build_agent_b_prompt

# 模拟 DeepSeek 真实输出风格：markdown 加粗 + 正文推演里先出现一批价格数字
E_TEXT_WITH_BODY_NUMBERS = """**E·综合决策报告**

### 风险收益比
- **目标价（中性）**：¥64.2（筹码密集区下沿）
- 止损位：跌破短期支撑¥60.66，则看跌至55-57区间

━━━ 最终操作建议 ━━━

**操作方向：持有观望（空仓者不介入）**

**置信度：85%**

**止损位：¥60.50**（跌破前低）

**目标价：** 暂无交易建议

**本次新增笔记**：等待信号
"""


def test_parse_e_strips_markdown_bold_from_decision():
    r = parse_agent_e(E_TEXT_WITH_BODY_NUMBERS)
    assert not r["decision"].endswith("*"), f"decision 含 markdown 残留: {r['decision']!r}"
    assert r["decision"] == "持有观望（空仓者不介入）"


def test_parse_e_extracts_from_final_section_not_body():
    r = parse_agent_e(E_TEXT_WITH_BODY_NUMBERS)
    # 止损应取最终建议里的 60.50，而不是正文推演里的 60.66
    assert r["stop_loss"] == 60.5
    # 最终建议明确"暂无交易建议"，不能回退去抓正文里的 64.2
    assert r["target"] is None
    assert r["confidence"] == 85


def test_parse_e_falls_back_to_whole_text_without_anchor():
    text = "操作方向：买入\n置信度：70%\n止损位：¥10.5\n目标价：¥15.0"
    r = parse_agent_e(text)
    assert r["decision"] == "买入"
    assert r["stop_loss"] == 10.5
    assert r["target"] == 15.0


def test_note_extraction():
    text = "分析正文\n\n**本次新增笔记**（50字以内）：关键信号已出现"
    assert extract_note(text) == "关键信号已出现"
    assert "本次新增笔记" not in strip_note(text)


def test_note_extraction_heading_style():
    # 回归：DeepSeek 实测会把笔记写成标题样式（内容在下一行且带方括号），
    # 曾导致 C 的笔记完全没存进记忆档案
    text = "分析正文\n\n### 【本次新增笔记】\n[趋势空头未改，观察60元支撑。]"
    assert extract_note(text) == "趋势空头未改，观察60元支撑。"
    stripped = strip_note(text)
    assert "本次新增笔记" not in stripped
    assert "###" not in stripped.splitlines()[-1] if stripped else True


def test_note_extraction_absent():
    assert extract_note("正文里根本没写笔记") == ""
    assert strip_note("正文里根本没写笔记") == "正文里根本没写笔记"


def test_b_incremental_prompt_survives_none_last_decision():
    # 回归：f-string 里 `or {{}}` 在 Python 3.12+ 会被解析成"含空dict的set"，
    # last_decision 为 None 时曾直接 TypeError
    data = {
        "stock": "002475", "fetch_time": "2026-07-06",
        "realtime": {"名称": "立讯精密", "最新价": 64.0, "市盈率TTM": 27.0, "总市值_亿": 4700},
        "financials": {}, "profit_sheet": {}, "research_reports": [], "earnings_forecast": {},
    }
    context = {
        "position": "未持仓", "B_fundamental_notes": "n",
        "since_date": "2026-07-03", "days_since_last": 3,
        "analysis_mode": "incremental", "last_decision": None,
    }
    prompt = build_agent_b_prompt(data, context)
    assert "¥?" in prompt  # last_decision 缺失时价格占位为 ?
