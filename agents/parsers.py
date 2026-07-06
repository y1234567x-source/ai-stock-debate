# -*- coding: utf-8 -*-
"""
把 LLM 的纯文本输出（遵循 prompts.py 里约定的输出格式）解析为结构化字段。

设计原则：正则提取是"尽力而为"，不是强校验。所有 prompt 都要求模型在末尾输出
`**本次新增笔记**：...`，这是唯一可靠稳定的锚点。除此之外的 verdict/字段抽取
允许抽不到就退化为兜底文案，不应该因为某个字段没匹配上就让整次分析失败——
完整原文永远保留在 body 里，用户始终能看到全部内容，抽取失败只影响摘要展示。
"""

import re
from typing import Callable, List, Optional

# 笔记标记只认核心文字，不限定装饰——prompt 约定的格式是
# `**本次新增笔记**（50字以内）：内容`，但模型经常漂移成
# `### 【本次新增笔记】\n[内容]` 等标题样式，解析必须都能兜住。
NOTE_MARK = "本次新增笔记"


def _clean_note_line(line: str) -> str:
    """去掉笔记内容行两端的 markdown/括号装饰。"""
    return line.strip().strip("*").strip("[]【】").strip()


def extract_note(text: str) -> str:
    if not text:
        return ""
    idx = text.find(NOTE_MARK)
    if idx == -1:
        return ""
    rest = text[idx + len(NOTE_MARK):]
    # 跳过标记后的装饰：`**`、`】`、`（50字以内）` 之类的字数说明、冒号
    rest = re.sub(r"^[\*】\s]*(?:[（(][^）)]*[）)])?[\*\s]*[:：]?", "", rest, count=1)
    for line in rest.splitlines():
        cleaned = _clean_note_line(line)
        if cleaned:
            return cleaned
    return ""


def strip_note(text: str) -> str:
    """去掉笔记标记及其后内容，用于正文展示（避免笔记重复出现两次）。"""
    if not text:
        return ""
    idx = text.find(NOTE_MARK)
    if idx == -1:
        return text.strip()
    # 回退到标记所在行的行首，把 `### 【` 之类的前缀装饰一并去掉
    line_start = text.rfind("\n", 0, idx)
    cut = line_start + 1 if line_start != -1 else 0
    return text[:cut].strip()


def _extract_by_patterns(text: str, patterns: List[str], default: str = "") -> str:
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    return default


def _fallback_verdict(text: str) -> str:
    """兜底：取第一条非空、非标题、非分隔线的正文行，截断到合理长度。"""
    for line in (text or "").splitlines():
        line = line.strip().lstrip("*").strip()
        if line and not line.startswith("━") and not line.startswith("【") and len(line) > 4:
            return line[:60]
    return "查看详情"


# verdict 是头部徽章用的短标签，不是段落。即便正则/兜底抓到一整行，也在此
# 统一截断，避免像 D 的"结论是否维持：[维持，理由：……]"整段塞进徽章、把
# 卡片标题挤成竖排单字。CSS 侧也有 ellipsis 兜底，双重保险。
VERDICT_MAX_LEN = 28


def _clip_verdict(v: str) -> str:
    v = (v or "").strip().strip("[]【】").strip()
    return (v[:VERDICT_MAX_LEN] + "…") if len(v) > VERDICT_MAX_LEN else v


def _base_parse(text: str, verdict_patterns: List[str]) -> dict:
    text = text or ""
    verdict = _extract_by_patterns(text, verdict_patterns) or _fallback_verdict(text)
    return {
        "verdict": _clip_verdict(verdict),
        "note": extract_note(text),
        "body": strip_note(text),
        "raw": text,
    }


def parse_agent_a(text: str) -> dict:
    return _base_parse(text, [
        r"情绪汇总得分[：:]\s*(.+)",
    ])


def parse_agent_b(text: str) -> dict:
    return _base_parse(text, [
        r"当前价¥?[\d.]+处于[：:]\s*(\S+)",
        # 增量模式：只取"维持/更新"关键词，不要把后面整段理由抓进徽章
        r"上次结论是否维持[：:]\s*[\[【]?\s*(维持|更新)",
        r"上次结论是否维持[：:]\s*(.+)",
    ])


def parse_agent_c(text: str) -> dict:
    return _base_parse(text, [
        r"操作信号[：:]\s*(\S+)",
    ])


def parse_agent_d(text: str) -> dict:
    return _base_parse(text, [
        r"行业景气度[：:]\s*(\S+)",
        # 增量模式：只取"维持/更新"关键词，不要把后面整段理由抓进徽章
        r"结论是否维持[：:]\s*[\[【]?\s*(维持|更新)",
        r"结论是否维持[：:]\s*(.+)",
        r"D·行业宏观（?维持/更新）?[：:]\s*(.+)",
    ])


AGENT_PARSERS = {
    "A": parse_agent_a,
    "B": parse_agent_b,
    "C": parse_agent_c,
    "D": parse_agent_d,
}


def _to_float(val: Optional[str]) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _to_int(val: Optional[str], default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(re.sub(r"[^\d]", "", val) or default)
    except ValueError:
        return default


# E 报告里"最终操作建议/最终裁决"章节的锚点。正文分析部分（如"风险收益比"
# 推演）经常先出现一批目标价/止损位数字，必须优先从最终建议章节里提取，
# 否则第一个匹配会抓到推演过程里的数字而非真正的结论。
E_FINAL_SECTION_RE = re.compile(r"最终操作建议|最终裁决|最终判断")


def parse_agent_e(text: str) -> dict:
    """
    解析 E 的最终裁决为结构化字段（旧系统里这是 Claude 手写的 dict，
    这里改为从模型纯文本输出正则提取）。
    """
    text = text or ""

    # 找到锚点时只在"最终操作建议"章节内提取——若该章节里某字段缺失
    # （如"目标价：暂无"），说明模型有意不设，不能回退到全文去抓推演
    # 过程里的数字；找不到锚点时才对全文提取。
    m = E_FINAL_SECTION_RE.search(text)
    final_section = text[m.start():] if m else text

    def _extract(patterns):
        return _extract_by_patterns(final_section, patterns)

    decision = _extract([
        r"操作方向[：:]\s*[【\[]?([^\n】\]]+)[】\]]?",
    ])
    # 去掉 markdown 加粗残留的星号（如 "**操作方向：持有观望**" 会把尾部 ** 捕进组里）
    decision = decision.strip("*【】[] 　") if decision else "未能提取明确操作方向，请查看完整报告"

    confidence = _to_int(_extract([r"置信度[：:]\s*\**\s*(\d+)"]), default=0)

    stop_loss = _to_float(_extract([
        r"(?:更新)?止损位[：:]\s*\**\s*¥?([\d.]+)",
    ]))
    target = _to_float(_extract([
        r"(?:更新)?目标价[：:]\s*\**\s*¥?([\d.]+)",
    ]))

    return {
        "decision": decision,
        "confidence": confidence,
        "stop_loss": stop_loss,
        "target": target,
        "note": extract_note(text),
        "body": strip_note(text),
        "summary": strip_note(text),
        "raw": text,
    }


def markdown_to_html(text: str) -> str:
    """把 Agent 的 Markdown 风格输出转成 HTML，供 HTML 报告展示。"""
    if not text:
        return "<p style='color:var(--muted)'>（无内容）</p>"
    try:
        import markdown
        return markdown.markdown(text, extensions=["tables", "nl2br"])
    except ImportError:
        # markdown 包未装时的极简兜底：只处理换行和加粗，不中断流程
        escaped = (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        return "<p>" + escaped.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
