# -*- coding: utf-8 -*-
"""
Agent 编排层：并行跑 A/B/C/D，全部完成后串行跑 E，整合成最终 reports dict。

用 ThreadPoolExecutor 而非 asyncio——这是一次性 CLI 脚本（跑一次退出），
不是常驻服务，同步 SDK + 线程池对"4个IO调用之后等全部返回"这个场景完全
够用，复杂度更低，出错时堆栈也更直接。
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from providers.base import LLMProvider, LLMProviderError

from .parsers import AGENT_PARSERS, parse_agent_e
from .prompts import (
    build_agent_a_prompt,
    build_agent_b_prompt,
    build_agent_c_prompt,
    build_agent_d_prompt,
    build_agent_e_prompt,
)

AGENT_BUILDERS = {
    "A": build_agent_a_prompt,
    "B": build_agent_b_prompt,
    "C": build_agent_c_prompt,
    "D": build_agent_d_prompt,
}

AGENT_LABELS = {
    "A": "新闻信息官",
    "B": "基本面研究员",
    "C": "技术分析师",
    "D": "行业宏观分析师",
}


def _call_with_retry(provider: LLMProvider, prompt: str, max_retries: int) -> str:
    attempt = 0
    last_err: LLMProviderError = None
    while attempt <= max_retries:
        try:
            resp = provider.complete(prompt)
            return resp.text
        except LLMProviderError as e:
            last_err = e
            if not e.retryable or attempt == max_retries:
                raise
            time.sleep(2)
            attempt += 1
    # 理论上不会走到这里（循环内要么 return 要么 raise），保底抛出最后一次错误
    raise last_err


def _degraded_report(agent_key: str, error: LLMProviderError) -> dict:
    label = AGENT_LABELS.get(agent_key, agent_key)
    msg = f"（本次调用失败：{error}）"
    return {
        "verdict": "数据不可用",
        "note": f"{label}本次调用失败，E 裁决时请降低对该维度的依赖权重",
        "body": f"**{agent_key} · {label}**\n\n{msg}\n\n"
                f"该异常可能是网络问题、API Key 无效或触发限流，建议检查 .env 配置后重跑。",
        "raw": msg,
        "error": str(error),
    }


def run_debate(symbol: str, data: dict, context: dict, provider: LLMProvider,
                max_retries: int = 1,
                progress: Callable[[str], None] = None) -> dict:
    """
    跑完整的五角色辩论流程。

    返回 dict，结构：
      {
        "A": {...parsed...}, "B": {...}, "C": {...}, "D": {...},
        "E": {...parsed E_structured...},
        "errors": {agent_key: error_message, ...}   # 本次运行中出现的错误，可能为空
      }
    """
    progress = progress or (lambda msg: None)
    results: dict = {}
    errors: dict = {}

    progress("  [Agent层] 并行调用 A/B/C/D...")
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {}
        for key, builder in AGENT_BUILDERS.items():
            prompt = builder(data, context)
            futures[pool.submit(_call_with_retry, provider, prompt, max_retries)] = key

        for future in as_completed(futures):
            key = futures[future]
            try:
                raw_text = future.result()
                results[key] = AGENT_PARSERS[key](raw_text)
                progress(f"  [Agent层] {key} 完成")
            except LLMProviderError as e:
                errors[key] = str(e)
                results[key] = _degraded_report(key, e)
                progress(f"  [Agent层] {key} 失败: {e}")

    # E 需要看到四份报告的正文（供其做综合裁决），即使某些是降级占位报告，
    # build_agent_e_prompt 本身已经兼容"某 Agent 未返回报告"的情况。
    e_input_reports = {key: results[key]["raw"] for key in ("A", "B", "C", "D")}

    progress("  [Agent层] 串行调用 E 综合裁决...")
    try:
        e_prompt = build_agent_e_prompt(e_input_reports, data, context)
        e_raw = _call_with_retry(provider, e_prompt, max_retries)
        e_parsed = parse_agent_e(e_raw)
        progress("  [Agent层] E 完成")
    except LLMProviderError as e:
        # E 阶段失败没有下游可以兜底，直接向上抛出，由 CLI 层决定报错退出
        raise RuntimeError(
            f"E（首席决策官）调用失败，无法生成最终裁决：{e}\n"
            f"A/B/C/D 已完成的分析内容不受影响，可检查 .env 配置或稍后重试。"
        ) from e

    return {
        "A": results["A"], "B": results["B"], "C": results["C"], "D": results["D"],
        "E": e_parsed,
        "errors": errors,
    }
