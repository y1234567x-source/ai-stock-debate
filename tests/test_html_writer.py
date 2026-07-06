# -*- coding: utf-8 -*-
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from output.writers.html_writer import _plain_snippet


def test_snippet_strips_markdown_and_collapses_whitespace():
    # 回归：历史时间线曾把 E 的完整 markdown 正文当纯文本直接塞入，
    # 换行被浏览器吃掉，堆成一坨不可读
    raw = "**E·综合决策报告**\n\n### 信号一致性分析\n\n- A：中性偏多\n- B：无法判断"
    s = _plain_snippet(raw)
    assert "**" not in s and "###" not in s
    assert "\n" not in s
    assert "E·综合决策报告" in s


def test_snippet_truncates_long_text_at_sentence_boundary():
    raw = "第一句结论。" + "后面还有很多很多的推理过程细节" * 20
    s = _plain_snippet(raw, limit=40)
    assert len(s) <= 44  # limit + 句号 + " …"
    assert s.endswith("…")


def test_snippet_keeps_short_text_intact():
    assert _plain_snippet("维持观望，等待信号") == "维持观望，等待信号"


def test_snippet_handles_empty():
    assert _plain_snippet("") == ""
    assert _plain_snippet(None) == ""
