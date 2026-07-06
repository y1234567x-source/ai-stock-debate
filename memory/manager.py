# -*- coding: utf-8 -*-
"""
记忆层 — 让每个Agent越用越懂这只股票
结构：
  memory/profiles/{symbol}.json     股票档案（持仓、历史分析、Agent笔记）
  memory/decisions_log.json         历史决策记录（用于复盘命中率）
"""

import json
import os
from datetime import datetime, date

PROFILES_DIR = os.path.join(os.path.dirname(__file__), "profiles")
DECISIONS_LOG = os.path.join(os.path.dirname(__file__), "decisions_log.json")
os.makedirs(PROFILES_DIR, exist_ok=True)


# ─── 股票档案 ──────────────────────────────────────────────

def load_profile(symbol: str) -> dict:
    path = os.path.join(PROFILES_DIR, f"{symbol}.json")
    if not os.path.exists(path):
        return _empty_profile(symbol)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_profile(symbol: str, profile: dict):
    path = os.path.join(PROFILES_DIR, f"{symbol}.json")
    profile["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2, default=str)


def _empty_profile(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_updated": None,
        # 用户持仓信息（手动更新）
        "position": {
            "holding": False,
            "cost_price": None,
            "shares": None,
            "position_pct": None,
            "entry_date": None,
        },
        # 飞书文档 token（首次分析后由 Claude Code 写入）
        "feishu_doc_token": None,
        # 各Agent的历史笔记（每次分析后追加）
        "agent_notes": {
            "A_news":        [],
            "B_fundamental": [],
            "C_technical":   [],
            "D_macro":       [],
        },
        # 历史分析摘要（每次分析后追加一条）
        "analysis_history": [],
        # 用户自定义观察点
        "watchpoints": [],
    }


def update_position(symbol: str, holding: bool, cost_price=None,
                    shares=None, position_pct=None, entry_date=None):
    """更新用户持仓信息"""
    profile = load_profile(symbol)
    profile["position"] = {
        "holding": holding,
        "cost_price": cost_price,
        "shares": shares,
        "position_pct": position_pct,
        "entry_date": entry_date,
    }
    save_profile(symbol, profile)


def append_agent_note(symbol: str, agent_key: str, note: str):
    """Agent每次分析后追加笔记（最多保留20条）"""
    profile = load_profile(symbol)
    notes = profile["agent_notes"].get(agent_key, [])
    notes.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "note": note,
    })
    profile["agent_notes"][agent_key] = notes[-20:]
    save_profile(symbol, profile)


def append_analysis(symbol: str, analysis: dict):
    """追加一次完整分析摘要到历史记录"""
    profile = load_profile(symbol)
    entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "price_at_analysis": analysis.get("price"),
        "decision": analysis.get("decision"),
        "confidence": analysis.get("confidence"),
        "stop_loss": analysis.get("stop_loss"),
        "target": analysis.get("target"),
        "summary": analysis.get("summary", ""),
        "actual_outcome": None,  # 事后复盘时填写
    }
    profile["analysis_history"].append(entry)
    profile["analysis_history"] = profile["analysis_history"][-30:]
    save_profile(symbol, profile)


def get_agent_context(symbol: str) -> dict:
    """提取给Agent的历史上下文（精简版，减少token）"""
    profile = load_profile(symbol)

    def fmt_notes(notes):
        if not notes:
            return "（首次分析，暂无历史笔记）"
        return "\n".join([f"[{n['date']}] {n['note']}" for n in notes[-5:]])

    def fmt_history(history):
        if not history:
            return "（暂无历史决策记录）"
        lines = []
        for h in history[-5:]:
            outcome = h.get("actual_outcome") or "待复盘"
            lines.append(
                f"[{h['date'][:10]}] 价格¥{h.get('price_at_analysis','?')} "
                f"→ {h.get('decision','?')} (置信度{h.get('confidence','?')}) "
                f"| 实际结果: {outcome}"
            )
        return "\n".join(lines)

    pos = profile["position"]
    holding_str = "未持仓"
    if pos.get("holding"):
        holding_str = (
            f"持仓中 | 成本价¥{pos.get('cost_price','?')} | "
            f"仓位{pos.get('position_pct','?')}% | "
            f"建仓日期{pos.get('entry_date','?')}"
        )

    # 上次分析日期，用于控制公告拉取范围和分析模式
    history = profile.get("analysis_history", [])
    since_date = history[-1]["date"][:10] if history else None

    # 计算距上次分析的天数和分析模式
    if since_date:
        delta = (date.today() - datetime.strptime(since_date, "%Y-%m-%d").date()).days
        if delta <= 2:
            analysis_mode = "intraday"    # 今天/昨天：只看分时+增量K线，B/D可跳过
        elif delta <= 30:
            analysis_mode = "incremental" # 3-30天：增量K线，B/D轻量分析
        else:
            analysis_mode = "full"        # 30天以上：完整分析
        days_since_last = delta
    else:
        analysis_mode = "full"
        days_since_last = None

    # 上次决策摘要（供 E Agent 增量模式引用）
    last_decision = None
    if history:
        h = history[-1]
        last_decision = {
            "date": h["date"][:10],
            "price": h.get("price_at_analysis"),
            "decision": h.get("decision", ""),
            "confidence": h.get("confidence", 0),
            "stop_loss": h.get("stop_loss"),
            "target": h.get("target"),
            "summary": (h.get("summary", "") or "")[:200],
        }

    return {
        "position":           holding_str,
        "A_news_notes":       fmt_notes(profile["agent_notes"].get("A_news", [])),
        "B_fundamental_notes":fmt_notes(profile["agent_notes"].get("B_fundamental", [])),
        "C_technical_notes":  fmt_notes(profile["agent_notes"].get("C_technical", [])),
        "D_macro_notes":      fmt_notes(profile["agent_notes"].get("D_macro", [])),
        "decision_history":   fmt_history(profile["analysis_history"]),
        "since_date":         since_date,
        "days_since_last":    days_since_last,
        "analysis_mode":      analysis_mode,
        "last_decision":      last_decision,
    }


# ─── 决策日志 ──────────────────────────────────────────────

def log_decision(symbol: str, decision: str, price: float,
                 confidence: int, stop_loss: float, target: float, summary: str):
    """记录一次决策到全局日志"""
    if os.path.exists(DECISIONS_LOG):
        with open(DECISIONS_LOG, "r", encoding="utf-8") as f:
            log = json.load(f)
    else:
        log = []

    log.append({
        "date":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symbol":     symbol,
        "price":      price,
        "decision":   decision,
        "confidence": confidence,
        "stop_loss":  stop_loss,
        "target":     target,
        "summary":    summary,
        "outcome":    None,
    })
    log = log[-200:]
    with open(DECISIONS_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2, default=str)


def update_feishu_doc_token(symbol: str, doc_token: str):
    """将飞书文档 token 写入 profile，供下次分析时 append"""
    profile = load_profile(symbol)
    profile["feishu_doc_token"] = doc_token
    save_profile(symbol, profile)


def get_feishu_doc_token(symbol: str) -> str | None:
    """读取该股票对应的飞书文档 token，不存在返回 None"""
    profile = load_profile(symbol)
    return profile.get("feishu_doc_token")


def get_hit_rate(symbol: str = None) -> dict:
    """计算历史决策命中率（有actual_outcome的记录）"""
    if not os.path.exists(DECISIONS_LOG):
        return {"message": "暂无历史记录"}
    with open(DECISIONS_LOG, "r", encoding="utf-8") as f:
        log = json.load(f)
    if symbol:
        log = [x for x in log if x.get("symbol") == symbol]
    total = len([x for x in log if x.get("outcome")])
    correct = len([x for x in log if x.get("outcome") == "correct"])
    return {
        "total_decisions":    len(log),
        "reviewed_decisions": total,
        "correct":            correct,
        "hit_rate":           f"{correct/total*100:.1f}%" if total else "待复盘",
    }


if __name__ == "__main__":
    # 快速测试
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "601231"
    ctx = get_agent_context(sym)
    print(json.dumps(ctx, ensure_ascii=False, indent=2))
