# -*- coding: utf-8 -*-
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from providers.base import LLMProvider, LLMProviderError, LLMResponse
from agents.orchestrator import run_debate

FIXTURE_DATA = {
    "stock": "002475",
    "fetch_time": "2026-07-03 10:00:00",
    "realtime": {"名称": "立讯精密", "最新价": 60.9, "涨跌幅": -8.06, "市盈率TTM": 25.89, "总市值_亿": 4457.3},
    "kline": {"MA5": 66.17, "MA10": 68.0, "MA20": 68.87, "MA60": 67.56, "量比": 1.0,
              "5日涨幅": -5.0, "近20日最高": 78.0, "近20日最低": 60.66, "近5日明细": []},
    "chip": {"error": "unavailable"},
    "margin": {"error": "unavailable"},
    "dragon_tiger": {"上榜次数": 0},
    "northbound_stock": {"持有情况": "无数据"},
    "northbound": {"error": "unavailable"},
    "financials": {}, "profit_sheet": {},
    "announcements": [],
    "intraday": {},
}

FIXTURE_CONTEXT = {
    "position": "未持仓",
    "A_news_notes": "（首次分析，暂无历史笔记）",
    "B_fundamental_notes": "（首次分析，暂无历史笔记）",
    "C_technical_notes": "（首次分析，暂无历史笔记）",
    "D_macro_notes": "（首次分析，暂无历史笔记）",
    "decision_history": "（暂无历史决策记录）",
    "since_date": None,
    "days_since_last": None,
    "analysis_mode": "full",
    "last_decision": None,
}

CANNED_TEXT = {
    "A": "**A·新闻官分析报告**\n\n情绪汇总得分：2分\n\n**本次新增笔记**：无重大事项",
    "B": "**B·基本面研究员分析报告**\n\n估值结论：\n- 当前价¥60.9处于：低估\n\n**本次新增笔记**：PE偏低",
    "C": "**C·技术分析师分析报告**\n\n操作信号：观望\n\n**本次新增笔记**：等待企稳",
    "D": "**D·行业宏观分析师报告**\n\n行业景气度：→\n\n**本次新增笔记**：无变化",
    "E": (
        "**E·综合决策报告**\n\n━━━ 最终操作建议 ━━━\n"
        "操作方向：【持有观望】\n置信度：70%\n止损位：¥59.0\n目标价：¥68.0\n"
        "**本次新增笔记**：等待信号"
    ),
}


class FakeProvider(LLMProvider):
    """按 prompt 内容里出现的 Agent 标记词返回预设文本；可注入指定 Agent 失败一次。"""

    def __init__(self, fail_agents=None, fail_times=1):
        super().__init__(api_key="fake", model="fake-model")
        self.fail_agents = fail_agents or set()
        self.fail_times = fail_times
        self._fail_count = {}

    @property
    def provider_name(self):
        return "fake"

    def complete(self, prompt: str, system=None) -> LLMResponse:
        # 只看开头片段判断是哪个 Agent 的 prompt——E 的 prompt 会把 A/B/C/D
        # 的完整原始报告文本嵌入到正文里，如果搜索整个 prompt，B 的 canned
        # 文本里恰好包含"基本面研究员"（B 自己的 marker），会被误判成 B。
        # 每个 prompt 的自我介绍都在最前面，所以只需要看开头。
        head = prompt[:150]
        for key in ("A", "B", "C", "D", "E"):
            marker = {
                "A": "新闻信息官", "B": "基本面研究员", "C": "技术分析师",
                "D": "行业与宏观分析师", "E": "独立投资决策者",
            }[key]
            if marker in head or f"Agent {key}" in head:
                if key in self.fail_agents:
                    n = self._fail_count.get(key, 0)
                    if n < self.fail_times:
                        self._fail_count[key] = n + 1
                        raise LLMProviderError(f"{key} 模拟失败", retryable=True)
                return LLMResponse(text=CANNED_TEXT[key], model="fake-model", provider="fake")
        return LLMResponse(text="（未匹配到角色）", model="fake-model", provider="fake")


def test_run_debate_happy_path():
    provider = FakeProvider()
    result = run_debate("002475", FIXTURE_DATA, FIXTURE_CONTEXT, provider, max_retries=1)

    assert set(result.keys()) == {"A", "B", "C", "D", "E", "errors"}
    assert result["errors"] == {}
    assert result["E"]["decision"] == "持有观望"
    assert result["E"]["confidence"] == 70
    assert result["E"]["stop_loss"] == 59.0
    assert result["E"]["target"] == 68.0
    for key in ("A", "B", "C", "D"):
        assert result[key]["note"]
        assert result[key]["verdict"]


def test_run_debate_degrades_single_agent_failure():
    # C 一直失败（超过重试次数），其余正常；整体分析仍应完成，C 变成降级占位报告
    provider = FakeProvider(fail_agents={"C"}, fail_times=99)
    result = run_debate("002475", FIXTURE_DATA, FIXTURE_CONTEXT, provider, max_retries=1)

    assert "C" in result["errors"]
    assert result["C"]["verdict"] == "数据不可用"
    # 其余角色和最终裁决不受影响
    assert result["A"]["verdict"]
    assert result["E"]["decision"] == "持有观望"


def test_run_debate_retries_transient_failure():
    # B 第一次失败（可重试），第二次成功；max_retries=1 应该刚好覆盖
    provider = FakeProvider(fail_agents={"B"}, fail_times=1)
    result = run_debate("002475", FIXTURE_DATA, FIXTURE_CONTEXT, provider, max_retries=1)

    assert result["errors"] == {}
    assert result["B"]["verdict"] != "数据不可用"


def test_run_debate_e_failure_raises():
    provider = FakeProvider(fail_agents={"E"}, fail_times=99)
    try:
        run_debate("002475", FIXTURE_DATA, FIXTURE_CONTEXT, provider, max_retries=0)
        assert False, "应该抛出 RuntimeError"
    except RuntimeError as e:
        assert "E" in str(e) or "首席决策官" in str(e)
