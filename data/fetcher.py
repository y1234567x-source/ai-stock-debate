# -*- coding: utf-8 -*-
"""
数据获取层 — 覆盖A股全量分析所需数据
所有函数返回 dict，失败时返回 {"error": "..."} 而非抛出异常

代理绕过策略：
  - fetch_realtime / fetch_kline / fetch_intraday 使用 urllib.request 直连，天然绕过 requests 代理
  - 其余 akshare (eastmoney) 接口通过 _no_proxy() 临时 patch requests.get/post，强制直连
"""

import sys
import os
import json
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8")

try:
    import akshare as ak
    import pandas as pd
except ImportError:
    print(json.dumps({"error": "akshare 或 pandas 未安装，请运行: pip install akshare pandas"}))
    sys.exit(1)


SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "601231"
SINCE_DATE = sys.argv[2] if len(sys.argv) > 2 else None  # 上次分析日期，用于公告时间窗口
TODAY = datetime.today().strftime("%Y%m%d")
TODAY_DASH = f"{TODAY[:4]}-{TODAY[4:6]}-{TODAY[6:8]}"
START_90D = (datetime.today() - timedelta(days=90)).strftime("%Y%m%d")
# K线兜底源的拉取窗口：90自然日只有约61个交易日，算 MA60 时 rolling(60)
# 只剩一两行有效值，稍有停牌/节假日就全是 NaN；取150自然日（约100交易日）
# 与腾讯主源的100根bar对齐
START_150D = (datetime.today() - timedelta(days=150)).strftime("%Y%m%d")
START_1Y = (datetime.today() - timedelta(days=365)).strftime("%Y%m%d")


# ── 代理绕过工具 ──────────────────────────────────────────────

def _no_proxy(fn):
    """
    执行 fn() 期间强制绕过所有代理：
    - patch Session.request + 设置 trust_env=False（屏蔽环境变量代理 + Windows注册表代理）
    - 同时清除代理环境变量作为双保险
    兼容 Clash / V2Ray / Shadowsocks 等本地端口代理场景。
    """
    try:
        import requests as _req
        _orig_req = _req.Session.request
        def _noreq(self, method, url, **kw):
            _saved = self.trust_env
            self.trust_env = False   # 禁止读系统/注册表代理
            try:
                return _orig_req(self, method, url, **kw)
            finally:
                self.trust_env = _saved
        _req.Session.request = _noreq
    except Exception:
        _orig_req = None

    proxy_keys = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']
    saved_env = {k: os.environ.pop(k) for k in proxy_keys if k in os.environ}
    try:
        return fn()
    finally:
        os.environ.update(saved_env)
        if _orig_req is not None:
            try:
                import requests as _req
                _req.Session.request = _orig_req
            except Exception:
                pass


def safe(fn, label):
    try:
        return fn()
    except Exception as e:
        return {"error": f"{label}: {e}"}


def safe_np(fn, label):
    """safe() + 绕过代理（用于 akshare eastmoney 接口）"""
    try:
        return _no_proxy(fn)
    except Exception as e:
        return {"error": f"{label}: {e}"}


# ── 实时行情 ──────────────────────────────────────────────────

def fetch_realtime():
    """腾讯行情API — urllib直连，不走代理"""
    def _():
        import urllib.request
        prefix = "sh" if SYMBOL.startswith("6") else "sz"
        url = f"http://qt.gtimg.cn/q={prefix}{SYMBOL}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            raw = r.read().decode("gbk")
        f = raw.split("~")
        if len(f) < 50:
            return {"error": "腾讯行情数据格式异常"}
        return {
            "代码": SYMBOL,
            "名称": f[1],
            "最新价": float(f[3]),
            "昨收": float(f[4]),
            "今开": float(f[5]),
            "成交量_万手": round(float(f[6]) / 10000, 2),
            "最高": float(f[33]),
            "最低": float(f[34]),
            "涨跌额": round(float(f[3]) - float(f[4]), 2),
            "涨跌幅": round((float(f[3]) - float(f[4])) / float(f[4]) * 100, 2),
            "换手率": float(f[38]) if len(f) > 38 else None,
            "市盈率TTM": float(f[39]) if len(f) > 39 else None,
            "总市值_亿": round(float(f[45]), 2) if len(f) > 45 else None,
            "流通市值_亿": round(float(f[44]), 2) if len(f) > 44 else None,
        }
    return safe(_, "实时行情（腾讯）")


# ── 日K线 ─────────────────────────────────────────────────────

def fetch_kline():
    """
    日K线 — 优先腾讯直连（urllib），超时/失败时切换东方财富（akshare + 绕代理）。
    返回：均线、近20日区间、近5日明细，以及 SINCE_DATE 之后的增量K线（若有）。
    """

    def _build_result(df):
        """从 DataFrame（含 日期/开盘/收盘/最高/最低/成交量）构建标准结果"""
        for c in ["开盘", "收盘", "最高", "最低", "成交量"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["收盘"]).reset_index(drop=True)
        df["MA5"]  = df["收盘"].rolling(5).mean().round(2)
        df["MA10"] = df["收盘"].rolling(10).mean().round(2)
        df["MA20"] = df["收盘"].rolling(20).mean().round(2)
        df["MA60"] = df["收盘"].rolling(60).mean().round(2)
        df["量比"] = (df["成交量"] / df["成交量"].rolling(5).mean()).round(2)
        latest = df.iloc[-1]
        prev5  = df.tail(6).iloc[0]
        result = {
            "最新收盘": float(latest["收盘"]),
            "MA5":  float(latest["MA5"])  if pd.notna(latest["MA5"])  else None,
            "MA10": float(latest["MA10"]) if pd.notna(latest["MA10"]) else None,
            "MA20": float(latest["MA20"]) if pd.notna(latest["MA20"]) else None,
            "MA60": float(latest["MA60"]) if pd.notna(latest["MA60"]) else None,
            "量比": float(latest["量比"]) if pd.notna(latest["量比"]) else None,
            "5日涨幅": round((float(latest["收盘"]) - float(prev5["收盘"])) / float(prev5["收盘"]) * 100, 2),
            "近20日最高": float(df.tail(20)["最高"].max()),
            "近20日最低": float(df.tail(20)["最低"].min()),
            "近5日明细": df.tail(5)[
                [c for c in ["日期","开盘","收盘","最高","最低","成交量","MA5","MA10","量比"] if c in df.columns]
            ].to_dict(orient="records"),
        }
        if SINCE_DATE:
            try:
                since_ts = pd.Timestamp(SINCE_DATE)
                df["日期_ts"] = pd.to_datetime(df["日期"])
                incr = df[df["日期_ts"] >= since_ts]
                cols = [c for c in ["日期","开盘","收盘","最高","最低","成交量","MA5","MA10","MA20","MA60","量比"] if c in incr.columns]
                result["增量K线"] = incr[cols].to_dict(orient="records")
            except Exception:
                pass
        return result

    def _tencent():
        """腾讯 web.ifzq.gtimg.cn — urllib直连"""
        import urllib.request, json as _json
        prefix = "sh" if SYMBOL.startswith("6") else "sz"
        url = (f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
               f"?param={prefix}{SYMBOL},day,,,100,qfq")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode("utf-8")
        obj = _json.loads(raw)
        stock_data = obj["data"][f"{prefix}{SYMBOL}"]
        raw_days = stock_data.get("qfqday") or stock_data.get("day") or []
        days = [[d[0],d[1],d[2],d[3],d[4],d[5]] for d in raw_days if isinstance(d, list) and len(d) >= 6]
        df = pd.DataFrame(days, columns=["日期","开盘","收盘","最高","最低","成交量"])
        return _build_result(df)

    def _eastmoney():
        """东方财富 akshare 接口 — 调用时已套 _no_proxy"""
        df = ak.stock_zh_a_hist(
            symbol=SYMBOL, period="daily",
            start_date=START_150D, end_date=TODAY,
            adjust="qfq",
        )
        if df is None or df.empty:
            raise ValueError("东方财富K线数据为空")
        rename = {}
        for c in df.columns:
            cs = str(c).strip()
            if "日期" in cs or cs.lower() == "date":    rename[c] = "日期"
            elif "开盘" in cs or cs.lower() == "open":   rename[c] = "开盘"
            elif "收盘" in cs or cs.lower() == "close":  rename[c] = "收盘"
            elif "最高" in cs or cs.lower() == "high":   rename[c] = "最高"
            elif "最低" in cs or cs.lower() == "low":    rename[c] = "最低"
            elif "成交量" in cs or cs.lower() == "volume": rename[c] = "成交量"
        df = df.rename(columns=rename)
        df["日期"] = df["日期"].astype(str).str[:10]
        return _build_result(df)

    result = safe(_tencent, "K线数据（腾讯）")
    if "error" in result:
        fallback = safe_np(_eastmoney, "K线数据（东方财富）")
        if "error" not in fallback:
            fallback["_source"] = "eastmoney_fallback"
            return fallback
    return result


# ── 今日分时K线 ───────────────────────────────────────────────

def fetch_intraday():
    """
    今日5分钟K线 — 优先腾讯 ifzq.gtimg.cn（urllib直连），
    失败时切换东方财富（akshare + 绕代理）。
    上次分析距今≤2天时调用。
    """

    def _tencent():
        import urllib.request, json as _json
        prefix = "sh" if SYMBOL.startswith("6") else "sz"
        # 请求80条，覆盖当日全部Bar（约48条）
        url = (f"http://ifzq.gtimg.cn/appstock/app/kline/mkline"
               f"?param={prefix}{SYMBOL},m5,,80,qfq&_var=m5_today")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read().decode("utf-8")
        # 响应格式: m5_today={...}
        json_str = raw[len("m5_today="):]
        obj = _json.loads(json_str)
        bars = obj["data"][f"{prefix}{SYMBOL}"]["m5"]
        # 字段: [时间, 收盘, 开盘, 最高, 最低, 成交量, ...]
        # 时间有两种格式：紧凑型 "202607021500"（12位） 或 "2026-07-02 15:00"
        def _norm_time(t):
            t = str(t)
            if len(t) == 12 and t.isdigit():
                return f"{t[:4]}-{t[4:6]}-{t[6:8]} {t[8:10]}:{t[10:12]}"
            return t
        # 过滤当日数据：匹配 TODAY（紧凑格式前缀）或 TODAY_DASH
        today_bars = [b for b in bars
                      if str(b[0]).startswith(TODAY)      # "20260702..."
                      or str(b[0]).startswith(TODAY_DASH)] # "2026-07-02..."
        if not today_bars:
            today_bars = bars[-48:] if len(bars) > 48 else bars
        records = []
        for b in today_bars:
            try:
                records.append({
                    "时间":   _norm_time(b[0]),
                    "收盘":   float(b[1]),
                    "开盘":   float(b[2]),
                    "最高":   float(b[3]),
                    "最低":   float(b[4]),
                    "成交量": float(b[5]),
                })
            except (IndexError, ValueError, TypeError):
                continue
        if not records:
            raise ValueError("腾讯分时：无有效Bar数据")
        return {
            "今日条数": len(records),
            "今日最高": max(r["最高"] for r in records),
            "今日最低": min(r["最低"] for r in records),
            "今日最新": records[-1]["收盘"],
            "5分钟明细": records[-24:],
        }

    def _eastmoney():
        """akshare 东方财富分时接口 — 调用时已套 _no_proxy"""
        df = ak.stock_zh_a_hist_min_em(symbol=SYMBOL, period="5", adjust="")
        if df is None or df.empty:
            raise ValueError("分时数据为空")
        rename = {}
        for c in df.columns:
            cs = c.strip()
            if "时间" in cs or cs.lower() in ("datetime", "date"): rename[c] = "时间"
            elif cs in ("开盘", "open"):      rename[c] = "开盘"
            elif cs in ("收盘", "close"):     rename[c] = "收盘"
            elif cs in ("最高", "high"):      rename[c] = "最高"
            elif cs in ("最低", "low"):       rename[c] = "最低"
            elif "成交量" in cs or cs.lower() == "volume": rename[c] = "成交量"
        df = df.rename(columns=rename)
        if "时间" in df.columns:
            df["时间"] = pd.to_datetime(df["时间"])
            today_data = df[df["时间"].dt.date == pd.Timestamp(TODAY).date()].copy()
        else:
            today_data = df.tail(48)
        if today_data.empty:
            today_data = df.tail(24)
        keep = [c for c in ["时间","开盘","收盘","最高","最低","成交量"] if c in today_data.columns]
        return {
            "今日条数": len(today_data),
            "今日最高": float(today_data["最高"].max()) if "最高" in today_data.columns else None,
            "今日最低": float(today_data["最低"].min()) if "最低" in today_data.columns else None,
            "今日最新": float(today_data.iloc[-1]["收盘"]) if "收盘" in today_data.columns else None,
            "5分钟明细": today_data.tail(24)[keep].to_dict(orient="records"),
        }

    result = safe(_tencent, "今日分时（腾讯）")
    if "error" in result:
        fallback = safe_np(_eastmoney, "今日分时（东方财富）")
        if "error" not in fallback:
            fallback["_source"] = "eastmoney_fallback"
            return fallback
    return result


# ── 基本面 ────────────────────────────────────────────────────

def fetch_financials():
    """
    个股财务指标（近8个报告期，含最新季度）。

    注：早期版本用 stock_financial_abstract_ths（按年度摘要），实测该接口
    对本股票只返回到2011年的数据，严重滞后，无法用于当前估值判断。改用
    stock_financial_analysis_indicator，实测可拿到最新季度（如2026Q1）的
    每股收益、ROE、毛利率、净利率、营收/净利润增速等核心指标。
    """
    def _():
        cur_year = datetime.today().year
        df = ak.stock_financial_analysis_indicator(symbol=SYMBOL, start_year=str(cur_year - 2))
        if df is None or df.empty:
            return {"error": "财务指标数据为空"}
        recent = df.tail(8)
        keep_cols = [c for c in [
            "日期", "摊薄每股收益(元)", "加权净资产收益率(%)", "销售毛利率(%)",
            "销售净利率(%)", "主营业务收入增长率(%)", "净利润增长率(%)",
            "资产负债率(%)", "流动比率", "速动比率",
        ] if c in recent.columns]
        records = recent[keep_cols].to_dict(orient="records") if keep_cols else recent.to_dict(orient="records")
        return {"财务指标_近8期": records}
    return safe_np(_, "财务指标")


def fetch_research_reports():
    """
    近期机构研报：评级、机构名、日期、未来3年盈利预测(EPS/PE)。

    这是"分析师怎么看这只股票"的结构化数据源，不需要联网检索——
    覆盖了原本寄望于 WebSearch 才能获得的分析师观点/目标价信息。
    """
    def _():
        df = ak.stock_research_report_em(symbol=SYMBOL)
        if df is None or df.empty:
            return {"近期研报": "暂无研报"}
        if "日期" in df.columns:
            df = df.sort_values("日期", ascending=False)
        recent = df.head(8)
        keep = [c for c in ["日期", "机构", "东财评级", "报告名称"] if c in recent.columns]
        keep += [c for c in recent.columns if "盈利预测" in str(c)]
        return recent[keep].to_dict(orient="records")
    return safe_np(_, "机构研报")


def fetch_earnings_forecast():
    """
    公司官方业绩预告/快报（上市公司自己披露的，非分析师预测）。

    stock_yjyg_em 按报告期返回全市场数据，需要按报告期日期查询后再按
    股票代码过滤；依次尝试最近4个季度末，命中即返回。
    """
    def _():
        today = datetime.today()
        y = today.year
        candidates = [
            f"{y}1231", f"{y}0930", f"{y}0630", f"{y}0331",
            f"{y-1}1231", f"{y-1}0930",
        ]
        for date_str in candidates:
            try:
                df = ak.stock_yjyg_em(date=date_str)
            except Exception:
                continue
            if df is None or df.empty:
                continue
            code_col = "股票代码" if "股票代码" in df.columns else df.columns[1]
            match = df[df[code_col].astype(str) == SYMBOL]
            if not match.empty:
                keep = [c for c in [
                    "预告指标", "业绩变动", "业绩变动原因", "预告数值", "公告日期",
                ] if c in match.columns]
                records = match[keep].to_dict(orient="records") if keep else match.to_dict(orient="records")
                return {"报告期": date_str, "预告明细": records}
        return {"业绩预告": "近4个季度末均无预告数据"}
    return safe_np(_, "业绩预告")


def fetch_profit_sheet():
    def _():
        df = ak.stock_profit_sheet_by_yearly_em(symbol=SYMBOL)
        if df is None or df.empty:
            return {"error": "利润表为空"}
        key_rows = ["营业总收入", "营业总成本", "毛利润", "净利润", "归属于母公司所有者的净利润"]
        out = {}
        year_cols = [c for c in df.columns if str(c).startswith("20")][:4]
        for _, row in df.iterrows():
            try:
                name = str(row.iloc[0]) if row.iloc[0] is not None else ""
                if any(k in name for k in key_rows):
                    out[name] = {str(c): row[c] for c in year_cols if c in row.index}
            except Exception:
                continue
        return out if out else {"error": "未找到关键利润行"}
    return safe_np(_, "利润表")


# ── 行业宏观（供 D Agent 使用，结构化数据，不需要联网检索）──────

def fetch_pmi():
    """
    中国官方制造业/非制造业PMI（近6个月），反映宏观景气度趋势。
    这是"行业景气度/全球宏观影响"判断的客观数据源，不依赖训练知识。

    用 macro_china_pmi()（东方财富，单次分页请求，~3秒）而非
    macro_china_pmi_yearly()（jin10.com，拉取2005年至今全部历史，
    实测约60秒+，对每次分析都要跑一遍的场景太慢）。
    """
    def _():
        df = ak.macro_china_pmi()
        if df is None or df.empty:
            return {"error": "PMI数据为空"}
        # 该接口按月份倒序排列（最新月份在最前）
        recent = df.head(6)
        return recent.to_dict(orient="records")
    return safe(_, "制造业PMI")


def fetch_industry_board():
    """
    个股所属行业板块 + 板块指数近期走势（近90日）。

    依赖 push2.eastmoney.com，部分本地代理环境下该域名族可能连接不稳定
    （与筹码分布接口是同一类限制），失败时优雅降级为 {"error": ...}，
    不影响其余数据和分析继续进行。
    """
    def _():
        info = ak.stock_individual_info_em(symbol=SYMBOL)
        if info is None or info.empty:
            return {"error": "个股信息为空"}
        industry = None
        key_col, val_col = info.columns[0], info.columns[1]
        for _, r in info.iterrows():
            if "行业" in str(r[key_col]):
                industry = r[val_col]
                break
        if not industry:
            return {"error": "未找到所属行业分类"}

        hist = ak.stock_board_industry_hist_em(
            symbol=industry, start_date=START_90D, end_date=TODAY, period="日k", adjust=""
        )
        if hist is None or hist.empty:
            return {"所属行业": industry, "板块指数": "数据为空"}
        recent = hist.tail(10)
        keep = [c for c in ["日期", "收盘", "涨跌幅"] if c in recent.columns]
        return {
            "所属行业": industry,
            "板块近10日走势": recent[keep].to_dict(orient="records") if keep else recent.to_dict(orient="records"),
        }
    return safe_np(_, "行业板块")


# ── 资金面 ────────────────────────────────────────────────────

def fetch_northbound():
    """北向资金近10日流向"""
    def _():
        fn = getattr(ak, "stock_hsgt_north_flow_em",
             getattr(ak, "stock_hsgt_north_net_flow_in_em",
             getattr(ak, "stock_hsgt_north_acc_flow_in_em", None)))
        if fn is None:
            return {"error": "北向资金接口不可用（akshare版本）"}
        df = fn(symbol="北向资金") if "symbol" in fn.__code__.co_varnames else fn()
        if df is None or df.empty:
            return {"error": "北向资金数据为空"}
        date_col = next((c for c in df.columns if "日期" in c or "date" in c.lower()), df.columns[0])
        flow_col = next((c for c in df.columns if "净" in c or "flow" in c.lower()), df.columns[1])
        last10 = df.tail(10)
        return {
            "近10日净流入合计": str(last10[flow_col].sum()),
            "近10日明细": last10[[date_col, flow_col]].to_dict(orient="records"),
        }
    return safe_np(_, "北向资金")


def fetch_northbound_stock():
    """个股北向持股历史（按日）"""
    def _():
        df = ak.stock_hsgt_individual_em(symbol=SYMBOL)
        if df is None or df.empty:
            return {"持有情况": "无北向持股数据"}
        latest = df.iloc[-1]
        return {
            "数据日期": str(latest.get("持股日期", "")),
            "持股占A股百分比": float(latest.get("持股数量占A股百分比", 0)),
            "今日增持股数": float(latest.get("今日增持股数", 0) or 0),
            "持股市值": float(latest.get("持股市值", 0) or 0),
            "当日涨跌幅": float(latest.get("当日涨跌幅", 0) or 0),
        }
    return safe_np(_, "北向持股")


def fetch_margin():
    """融资融券 — 沪市SSE接口，深市SZSE接口，自动向前找最近有数据的交易日"""
    def _():
        is_sh = SYMBOL.startswith("6")
        for delta in range(1, 6):
            d = (datetime.today() - timedelta(days=delta)).strftime("%Y%m%d")
            try:
                if is_sh:
                    df = ak.stock_margin_detail_sse(date=d)
                    code_col = "标的证券代码"
                else:
                    df = ak.stock_margin_detail_szse(date=d)
                    code_col = "证券代码"
                if df is None or df.empty:
                    continue
                if code_col not in df.columns:
                    continue
                row = df[df[code_col].astype(str).str.contains(SYMBOL, na=False)]
                if row.empty:
                    continue
                r = row.iloc[0].to_dict()
                r["数据日期"] = d
                return {k: (float(v) if isinstance(v, (int, float)) else str(v)) for k, v in r.items()}
            except Exception:
                continue
        return {"error": "融资融券: 近5日均无数据"}
    return safe(_, "融资融券")


def fetch_dragon_tiger():
    def _():
        df = ak.stock_lhb_detail_em(start_date=START_90D, end_date=TODAY)
        if df.empty:
            return {"近90日龙虎榜": "无上榜记录"}
        if "代码" in df.columns:
            matched = df[df["代码"] == SYMBOL]
        elif "股票代码" in df.columns:
            matched = df[df["股票代码"] == SYMBOL]
        else:
            return {"近90日龙虎榜": "无法匹配代码列"}
        if matched.empty:
            return {"近90日龙虎榜": "无上榜记录"}
        return {
            "上榜次数": len(matched),
            "上榜记录": matched.tail(5).to_dict(orient="records"),
        }
    return safe_np(_, "龙虎榜")


def fetch_chip():
    def _():
        df = ak.stock_cyq_em(symbol=SYMBOL, adjust="qfq")
        if df.empty:
            return {"error": "筹码分布数据为空"}
        latest = df.iloc[-1]
        return {
            "获利比例": float(latest.get("获利比例", 0)),
            "平均成本": float(latest.get("平均成本", 0)),
            "90集中度": float(latest.get("90集中度", 0)),
            "70集中度": float(latest.get("70集中度", 0)),
        }
    return safe_np(_, "筹码分布")


def fetch_announcements():
    """
    拉取个股公告：时间窗口为上次分析至今，最多不超过30天。

    直接把 begin_date/end_date 传给接口做服务端过滤，而不是拉全部历史公告
    再客户端筛选——实测后者因为要翻遍该股票的完整公告历史，耗时可达70秒+，
    传日期参数后降到10秒以内。
    """
    def _():
        cap_30d = pd.Timestamp(TODAY) - pd.Timedelta(days=30)
        if SINCE_DATE:
            since = pd.Timestamp(SINCE_DATE)
            cutoff = since if since > cap_30d else cap_30d
        else:
            cutoff = cap_30d

        df = ak.stock_individual_notice_report(
            security=SYMBOL, symbol="全部",
            begin_date=cutoff.strftime("%Y-%m-%d"), end_date=TODAY_DASH,
        )
        if df is None or df.empty:
            # 该时间窗口内确实无公告时，退回拉最近的几条（不限定日期）作为背景参考
            df = ak.stock_individual_notice_report(security=SYMBOL, symbol="全部")
            if df is None or df.empty:
                return {"近期公告": "暂无公告"}
            return df.head(5).to_dict(orient="records")

        df["公告日期"] = pd.to_datetime(df["公告日期"], errors="coerce")
        df = df.sort_values("公告日期", ascending=False)
        df["公告日期"] = df["公告日期"].dt.strftime("%Y-%m-%d")
        keep = [c for c in ["公告日期", "公告标题", "公告类型", "网址"] if c in df.columns]
        return df.head(10)[keep].to_dict(orient="records")
    return safe(_, "公司公告")


if __name__ == "__main__":
    need_intraday = False
    if SINCE_DATE:
        try:
            delta = (datetime.strptime(TODAY, "%Y%m%d").date() -
                     datetime.strptime(SINCE_DATE, "%Y-%m-%d").date()).days
            need_intraday = delta <= 2
        except Exception:
            pass

    result = {
        "stock":            SYMBOL,
        "since_date":       SINCE_DATE,
        "fetch_time":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "realtime":         fetch_realtime(),
        "kline":            fetch_kline(),
        "financials":       fetch_financials(),
        "profit_sheet":     fetch_profit_sheet(),
        "research_reports": fetch_research_reports(),
        "earnings_forecast": fetch_earnings_forecast(),
        "pmi":              fetch_pmi(),
        "industry_board":   fetch_industry_board(),
        "northbound":       fetch_northbound(),
        "northbound_stock": fetch_northbound_stock(),
        "margin":           fetch_margin(),
        "dragon_tiger":     fetch_dragon_tiger(),
        "chip":             fetch_chip(),
        "announcements":    fetch_announcements(),
    }
    if need_intraday:
        result["intraday"] = fetch_intraday()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
