# -*- coding: utf-8 -*-
"""
ai-stock-debate CLI 主入口。

用法：
  python analyze.py 002475
  python analyze.py 002475 --provider deepseek --model deepseek-chat
  python analyze.py 002475 --output-format md
  python analyze.py 002475 --dry-run
  python analyze.py 002475 --no-memory
  python analyze.py --hit-rate 002475
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _log(msg: str):
    print(msg)


def fetch_data(symbol: str, since_date: str = None) -> dict:
    """调用 data/fetcher.py 拉取全量行情/K线/公告数据。"""
    fetcher = os.path.join(ROOT, "data", "fetcher.py")
    _log(f"  [数据层] 正在拉取 {symbol} 数据（公告起始日：{since_date or '近30天'}）...")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [sys.executable, fetcher, symbol]
    if since_date:
        cmd.append(since_date)
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=240, env=env)
    except subprocess.TimeoutExpired:
        _log("  [数据层] FAIL: 拉取超时（240秒，公告接口在数据量大时可能较慢，可重试）")
        return {"stock": symbol, "error": "数据拉取超时", "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    output = result.stdout.decode("utf-8", errors="replace").strip()
    stderr = result.stderr.decode("utf-8", errors="replace").strip()
    json_start = output.find("{")
    if json_start == -1:
        _log(f"  [数据层] FAIL: 无 JSON 输出，stderr={stderr[:200]}")
        return {"stock": symbol, "error": "数据获取失败", "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    try:
        data = json.loads(output[json_start:])
    except json.JSONDecodeError as e:
        _log(f"  [数据层] FAIL: JSON 解析失败（输出可能被截断）: {e}")
        return {"stock": symbol, "error": f"数据输出格式异常: {e}", "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    _log(f"  [数据层] OK 数据获取完成，时间：{data.get('fetch_time', '')}")
    return data


def load_memory(symbol: str, no_memory: bool = False):
    from memory.manager import load_profile, get_agent_context, _empty_profile
    if no_memory:
        # 调试用：忽略历史记忆，强制走完整分析（不修改已保存的记忆文件）
        profile = _empty_profile(symbol)
        context = {
            "position": "未持仓", "A_news_notes": "（首次分析，暂无历史笔记）",
            "B_fundamental_notes": "（首次分析，暂无历史笔记）",
            "C_technical_notes": "（首次分析，暂无历史笔记）",
            "D_macro_notes": "（首次分析，暂无历史笔记）",
            "decision_history": "（暂无历史决策记录）",
            "since_date": None, "days_since_last": None,
            "analysis_mode": "full", "last_decision": None,
        }
        return profile, context
    profile = load_profile(symbol)
    context = get_agent_context(symbol)
    return profile, context


def save_memory(symbol: str, data: dict, reports: dict):
    from memory.manager import append_agent_note, append_analysis, log_decision
    e = reports.get("E", {})
    for key in ("A", "B", "C", "D"):
        note = (reports.get(key, {}) or {}).get("note", "").strip()
        if note:
            append_agent_note(symbol, {"A": "A_news", "B": "B_fundamental",
                                        "C": "C_technical", "D": "D_macro"}[key], note)

    price = data.get("realtime", {}).get("最新价") or data.get("kline", {}).get("最新收盘")
    append_analysis(symbol, {
        "price": price,
        "decision": e.get("decision", ""),
        "confidence": e.get("confidence", 0),
        "stop_loss": e.get("stop_loss"),
        "target": e.get("target"),
        "summary": e.get("summary", ""),
    })
    if e.get("decision") and price:
        log_decision(
            symbol=symbol, decision=e.get("decision", ""), price=float(price),
            confidence=int(e.get("confidence", 0) or 0),
            stop_loss=float(e.get("stop_loss") or 0),
            target=float(e.get("target") or 0),
            summary=e.get("summary", ""),
        )
    _log("  [记忆层] 笔记和决策已保存")


def run_analysis(args) -> int:
    from agents.orchestrator import run_debate

    symbol = args.symbol

    # --dry-run 只测数据层+记忆层，不需要也不应该要求 LLM 配置齐全
    if args.dry_run:
        profile, context = load_memory(symbol, no_memory=args.no_memory)
        since_date = args.since or context.get("since_date")
        data = fetch_data(symbol, since_date=since_date)
        _log("\n--dry-run 模式：仅展示已拉取数据和记忆上下文，不调用 LLM\n")
        _log(json.dumps({"data_keys": list(data.keys()), "context": context}, ensure_ascii=False, indent=2))
        return 0

    from config import load_config_or_exit
    from providers import get_provider

    cfg = load_config_or_exit()
    if args.provider:
        cfg.llm_provider = args.provider
    if args.model:
        cfg.llm_model = args.model

    try:
        provider = get_provider(cfg)
    except Exception as e:
        print(f"\n[Provider 初始化失败] {e}\n", file=sys.stderr)
        return 1

    _log(f"\n=== ai-stock-debate | {symbol} | provider={provider.provider_name} model={cfg.llm_model} ===\n")

    profile, context = load_memory(symbol, no_memory=args.no_memory)
    since_date = args.since or context.get("since_date")
    data = fetch_data(symbol, since_date=since_date)

    if "error" in data and data.get("error") not in (None, ""):
        # 部分数据源失败不代表整体失败（fetcher.py 内部已做单接口降级），
        # 只有当核心的 realtime/kline 都缺失时才算彻底失败
        if not data.get("realtime") and not data.get("kline"):
            print(f"\n[数据获取失败] {data['error']}\n", file=sys.stderr)
            return 1

    mode = context.get("analysis_mode", "full")
    _log(f"  [记忆层] 分析模式：{mode}" +
         (f"（距上次分析 {context.get('days_since_last')} 天）" if context.get("days_since_last") is not None else "（首次分析）"))

    try:
        reports = run_debate(symbol, data, context, provider,
                              max_retries=cfg.llm_max_retries, progress=_log)
    except RuntimeError as e:
        print(f"\n[分析失败] {e}\n", file=sys.stderr)
        return 1

    if reports.get("errors"):
        _log(f"  [提示] 本次有 {len(reports['errors'])} 个 Agent 调用失败，报告中已标注，不影响其余部分")

    if args.no_memory:
        _log("  [记忆层] --no-memory 模式：本次结果不写入记忆档案（调试用）")
    else:
        save_memory(symbol, data, reports)

    formats = [f.strip().lower() for f in args.output_format.split(",") if f.strip()]
    unknown = [f for f in formats if f not in ("html", "md")]
    if unknown:
        _log(f"  [警告] 未知的输出格式 {unknown}（支持 html / md），将被忽略")
    if not any(f in ("html", "md") for f in formats):
        _log("  [警告] 没有有效的输出格式，默认改用 html")
        formats = ["html"]
    output_dir = args.output_dir or os.path.join(ROOT, "output", "reports")
    saved_paths = []

    if "html" in formats:
        from output.writers import html_writer
        path = html_writer.save_report(data, reports, profile, output_dir)
        saved_paths.append(path)
    if "md" in formats:
        from output.writers import markdown_writer
        path = markdown_writer.save_report(data, reports, profile, output_dir)
        saved_paths.append(path)

    _log("\n=== 分析完成 ===")
    for p in saved_paths:
        _log(f"  报告已生成：{p}")

    e = reports.get("E", {})
    _log(f"\n【E 最终裁决】{e.get('decision', '')}（置信度 {e.get('confidence', '?')}%）")
    if e.get("stop_loss"):
        _log(f"  止损位：¥{e.get('stop_loss')}")
    if e.get("target"):
        _log(f"  目标价：¥{e.get('target')}")
    return 0


def run_hit_rate(symbol: str) -> int:
    from memory.manager import get_hit_rate
    result = get_hit_rate(symbol)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ai-stock-debate: 多角色辩论式 A 股个股投研分析（模型可插拔）")
    p.add_argument("symbol", nargs="?", help="6位股票代码，如 002475")
    p.add_argument("--provider", help="覆盖 .env 里的 LLM_PROVIDER")
    p.add_argument("--model", help="覆盖 .env 里的 LLM_MODEL")
    p.add_argument("--output-format", default="html", help="输出格式：html（默认）/ md / html,md")
    p.add_argument("--output-dir", help="报告输出目录，默认 ./output/reports")
    p.add_argument("--since", help="手动指定公告拉取起始日期（YYYY-MM-DD），覆盖记忆推算值，调试用")
    p.add_argument("--dry-run", action="store_true", help="只拉数据+读记忆，不调用 LLM，调试数据层用")
    p.add_argument("--no-memory", action="store_true", help="忽略历史记忆，强制走完整分析，调试用")
    p.add_argument("--hit-rate", metavar="SYMBOL", help="查看该股票（或全部，留空）的历史决策命中率")
    return p


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.hit_rate is not None:
        sys.exit(run_hit_rate(args.hit_rate))

    if not args.symbol:
        parser.error("请提供股票代码，例如: python analyze.py 002475")

    sys.exit(run_analysis(args))


if __name__ == "__main__":
    main()
