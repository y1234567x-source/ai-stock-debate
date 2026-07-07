# ai-stock-debate 多智能体A股个股投研分析工具

多智能体 A 股个股投研分析工具。五个 AI agent——新闻情绪（A）、基本面（B）、技术面（C）、行业宏观（D）、首席决策官（E）——分别独立分析后由 E 综合裁决，给出操作建议、止损位、目标价。

**核心特点：模型可插拔。** 不锁定任何一家 AI 厂商——用 Claude、GPT，还是 DeepSeek、Kimi、通义千问、智谱 GLM 这些国内模型，都能跑起来。你只需要在 `.env` 里换一个 provider 名字。

## 效果预览

跑完一次分析会在 `output/reports/` 生成一份暗色主题 HTML 报告（也可选 Markdown）。以对立讯精密（002475）的一次真实分析为例，报告包含：

**① 顶部实时行情栏**

```
股票代码（000000）投研分析 · 2026-07-06
最新价：¥61.39（-4.73%）  PE(TTM)：26.1x  总市值：4493.19亿
今开 ¥64.79  最高 ¥65.22  最低 ¥61.26  昨收 ¥64.44

```

**② E 的综合决策卡**

```
操作方向：维持原决策（持有观望 / 不建议买入）   置信度：65%
止损位：¥60.0    目标价：未设定
```
<img width="1871" height="745" alt="image" src="https://github.com/user-attachments/assets/41a97bb1-b434-464b-8176-57274c4b4312" />

**③ 新闻情绪、基本面、技术面、行业宏观的完整分析卡片**（可展开），每张卡片给出该维度的推理链、结论和一句话笔记。例如技术面 C 的实际输出片段：

```
C·技术分析师：空头排列，破位阴线看跌，全线套牢但量缩，
观察 60 元支撑及放量站上 MA5（64.67）信号。
```
<img width="1876" height="795" alt="image" src="https://github.com/user-attachments/assets/9fbab71d-71a2-4590-8730-32618c6815f0" />

**④ 历史决策时间线** — 同一支股票分析过多次时，能直接看到每次的价格、决策、置信度变化，验证判断是否被走势印证。
<img width="1874" height="364" alt="image" src="https://github.com/user-attachments/assets/169b1b43-b3ff-4646-9453-ba590a339916" />


> 完整 HTML 报告可交互展开。

## 快速开始（零基础也能跟着做）

### 第 0 步：确认装了 Python

打开终端（Windows 按 `Win+R` 输入 `cmd` 回车；Mac 打开"终端"），输入：

```bash
python --version
```

如果显示 `Python 3.10` 或更高版本，就可以继续。如果提示"命令未找到"或版本低于 3.10，去 [python.org](https://www.python.org/downloads/) 下载安装最新版（Windows 安装时记得勾选 **"Add Python to PATH"**）。

### 第 1 步：下载项目

```bash
git clone https://github.com/y1234567x-source/ai-stock-debate.git
cd ai-stock-debate
```

> 没装 git 也可以：在 GitHub 仓库页面点绿色 `Code` 按钮 → `Download ZIP`，解压后进入文件夹。

### 第 2 步：安装依赖

```bash
pip install -r requirements.txt
```

（这一步会自动装好 akshare、pandas、openai 等库，联网需要几分钟。）

### 第 3 步：申请一个 AI 模型的 API Key

这是唯一需要花钱的部分，但很便宜。**推荐新手用 DeepSeek**：注册后充几块钱就够跑很多次，去 [platform.deepseek.com](https://platform.deepseek.com/api_keys) 创建一个 API Key（一串 `sk-` 开头的字符）。其他模型见下方[支持列表](#支持的模型--provider)。

### 第 4 步：填配置

把示例配置复制一份成正式配置：

```bash
cp .env.example .env          # Windows CMD 用: copy .env.example .env
```

然后用记事本 / 任意编辑器打开 `.env` 文件，填三行（以 DeepSeek 为例）：

```ini
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-你刚申请的那串key
LLM_MODEL=deepseek-chat
```


### 第 5 步：开跑

```bash
python analyze.py 002475      # 换成你想分析的任意 6 位 A 股代码
```

终端会打印进度，跑完（约 1-3 分钟）后会显示生成的报告路径，例如：

```
报告已生成：output/reports/002475_20260706_1058.html
```

用浏览器打开这个 HTML 文件就能看到完整报告。想同时要 Markdown 版本，加个参数：`python analyze.py 002475 --output-format html,md`。

## 支持的模型 / Provider

| Provider 名 | 默认 base_url | 获取 API Key |
|---|---|---|
| `anthropic` | 官方 SDK 直连 | https://console.anthropic.com/ |
| `openai` | `api.openai.com/v1` | https://platform.openai.com/api-keys |
| `deepseek` | `api.deepseek.com/v1` | https://platform.deepseek.com/api_keys |
| `moonshot` / `kimi` | `api.moonshot.cn/v1` | https://platform.moonshot.cn/ |
| `qwen` / `dashscope` | `dashscope.aliyuncs.com/compatible-mode/v1` | https://dashscope.console.aliyun.com/ |
| `glm` / `zhipu` | `open.bigmodel.cn/api/paas/v4` | https://open.bigmodel.cn/ |
| `minimax` | `api.minimax.chat/v1` | https://platform.minimaxi.com/（接入前请对照官方最新文档核实兼容性） |
| `custom` | 你自己填 `LLM_BASE_URL` | 任何声明兼容 OpenAI Chat Completions 协议的服务 |

只要在 `.env` 里填对应的 `LLM_PROVIDER` 名字，`LLM_MODEL` 填该家的模型标识即可，不用记 base_url。

## 配置说明（`.env`）

| 变量 | 必填 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | 是 | 见上表 |
| `LLM_API_KEY` | 是 | 对应厂商的 API Key |
| `LLM_MODEL` | 是 | 模型标识，如 `deepseek-chat` |
| `LLM_BASE_URL` | 否 | 自定义端点，覆盖默认映射；`custom` provider 必填 |
| `LLM_MAX_TOKENS` | 否 | 单次调用最大 token 数，默认 4096 |
| `LLM_TIMEOUT` | 否 | 单次调用超时秒数，默认 120 |
| `LLM_MAX_RETRIES` | 否 | 超时/限流错误的重试次数，默认 1 |

## 系统架构

整体分四层，数据自下而上流动：

```
用户输入股票代码
      │
      ▼
① 数据层（data/fetcher.py）──── 14 类结构化行情/财务/资金/宏观数据
      │
      ▼
② 记忆层（memory/manager.py）── 读历史档案，判定分析范围（省 token）
      │
      ▼
③ Agent 编排层（agents/orchestrator.py）
      │   A ┐
      │   B ├─ 四角色【并行】各调用一次 LLM，独立分析
      │   C │
      │   D ┘
      │   └─→ E 汇总四份报告，【串行】调用一次 LLM 做综合裁决
      ▼
④ 输出层（output/writers/）──── HTML（默认）/ Markdown 报告
```

### ① 数据层：接入了哪些真实数据接口

所有数据都是运行时实时拉取的真实市场数据（来自腾讯财经、东方财富、同花顺，经 [akshare](https://github.com/akfamily/akshare) 开源库封装），**不是模型凭训练记忆编造的**：

| 数据类别 | 具体内容 | 来源 | 主要服务的角色 |
|---|---|---|---|
| 实时行情 | 现价、涨跌幅、换手率、PE(TTM)、市值 | 腾讯 | 全部 |
| 日 K 线 | 近 100 日 K 线、MA5/10/20/60 均线、量比、近 20 日高低 | 腾讯（主）+ 东方财富（兜底） | C |
| 财务指标 | 近 8 期营收/净利/毛利率/ROE 等 | 同花顺 | B |
| 利润表 | 分季度利润表明细 | 东方财富 | B |
| 机构研报 | 券商评级、2026-2028 年盈利预测 | 东方财富 | A、B |
| 业绩预告 | 官方发布的预增/预减指引 | 东方财富 | A、B |
| 制造业 PMI | 全国制造业景气度月度趋势 | 国家统计局 | D |
| 行业板块 | 个股所属行业板块指数走势 | 东方财富 | D |
| 北向资金 | 整体流向 + 个股北向持股 | 东方财富 | C、D |
| 融资融券 | 融资余额、融资买入、融券余量 | 沪深交易所 | C |
| 龙虎榜 | 近 90 日机构/游资上榜记录 | 东方财富 | C |
| 筹码分布 | 获利比例、平均成本、集中度 | 东方财富 | C |
| 公司公告 | 增量时间窗内的交易所公告 | 东方财富 | A |

### ② 记忆层：让重复分析越来越省

读取该股票的历史档案后，按"距上次分析多久"判定本次分析范围：

- **首次 / 距上次 >30 天** → 完整分析（全部数据源、全部方法论步骤重跑一遍）
- **距上次 3-30 天** → 区间增量（只看新增 K 线/公告，B/D 沿用上次结论并核实变化）
- **距上次 ≤2 天** → 当日增量（改用分时 K 线，聚焦盘中变化）

> "分析范围判定"只影响"要不要重新处理旧数据"（省 token、省时间），不影响"推理是否完整记录"——不管哪种范围，每次都会生成完整报告，不会因为是增量就压缩成一行结论。同一支股票分析越多次，记忆档案越丰富，后续也越快越省钱。

### ③ Agent 编排层：五个角色分别在做什么

A/B/C/D 拿到同一份数据后**并行、独立**分析（互不影响，避免相互带偏），各自产出一份带推理链的报告和一句话笔记；E 最后拿到四份报告做**综合裁决**。每个角色都有一套固定的专业方法论框架（写死在 `agents/prompts.py`，不是让模型自由发挥）：

| 角色 | 定位 | 分析框架（核心步骤） |
|---|---|---|
| **A** | 新闻信息官 | 逐条评估公告/研报评级/业绩预告 → 判断利好利空 → 给出情绪评分（0-10） |
| **B** | 基本面研究员 | 三表联动 → 杜邦分解 ROE → PE/PEG 估值定锚 → 保守/中性/乐观三档安全边际 → 最大财务风险 |
| **C** | 技术分析师 | 均线趋势 → K 线形态 → 量价关系 → 筹码博弈 → 主力资金行为 → 给出具体入场/止损价位 |
| **D** | 行业宏观分析师 | 行业景气度（PMI+板块指数）→ 产业链地位 → 竞争格局 → 全球宏观（汇率/地缘/北向）→ 未来 3 个月催化剂日历 |
| **E** | 首席决策官 | 检验 ABCD 信号一致性 → 按市场环境分配权重 → 算风险收益比（赔率<1.5 不操作）→ 对比历史决策 → 给出最终操作方向、置信度、止损、目标价 |

这种"先分工独立分析、再汇总裁决"的设计，好处是每个维度都被认真对待、分歧点会被 E 显式指出（而不是被一个笼统的结论掩盖），也让最终建议的推理过程完全可追溯。

### ④ 输出层

把结构化的分析结果渲染成暗色主题 HTML（默认）或 Markdown，写入 `output/reports/`。

## 输出说明

- 默认生成 HTML（`output/reports/{代码}_{时间戳}.html`），暗色主题，点击展开各 Agent 完整推理
- `--output-format md` 或 `--output-format html,md` 可以额外生成 Markdown 版本
- 每次分析都是独立文件，方便按时间线直接打开对比历史报告

## 记忆机制

`memory/profiles/{代码}.json` 记录该股票的：
- 各 Agent 历史笔记（最近 20 条）
- 历史分析摘要与决策记录（最近 30 条）
- 持仓信息（可用 `memory/manager.py` 的 `update_position()` 手动更新成本价/仓位）

`memory/decisions_log.json` 是全局决策日志，用于 `--hit-rate` 统计历史命中率（需要先手动在记录里补充 `actual_outcome: "correct"/"wrong"` 做复盘）。

## 常见问题

**Q: 数据拉取失败/超时怎么办？**
`data/fetcher.py` 对腾讯 K 线接口做了东方财富兜底，对走系统代理容易被拦截的接口（分时K线、筹码分布等）做了 `_no_proxy()` 绕过逻辑。如果本地开了 Clash/V2Ray 等代理软件仍然拉取失败，可以尝试在代理规则里把 `eastmoney.com` / `gtimg.cn` 加入直连白名单。

**Q: 某个 Agent 调用失败了，报告还能看吗？**
能。单个 Agent（A/B/C/D）调用失败会生成一份"数据不可用"的降级占位报告，报告顶部会有明确的异常提示区块，E 依然能基于其余 Agent 的结果给出裁决。只有 E 本身调用失败时才会整体报错退出（没有下游可以兜底最终裁决）。

**Q: 怎么查看历史命中率？**
`python analyze.py --hit-rate 002475`（查看单支股票）或 `python analyze.py --hit-rate ""`（查看全部）。

## 已知局限（v1）

- **不做通用网页检索**：没有接入搜索 API，模型不会主动去搜索新闻网站/论坛/研报网站的自由文本内容。但这不等于"没有数据"——公司公告、机构研报（含评级和 2026-2028 年盈利预测）、官方业绩预告、近8期财务指标、制造业PMI、行业板块指数走势，都通过 `data/fetcher.py` 的结构化接口（akshare）实时拉取，A/B/D 三个角色基于这些真实、当前的数据做判断，不是靠训练知识瞎猜。
- **D（行业宏观）里仍有一小部分依赖模型训练知识**：竞争格局变化、具体政策解读这类自由文本内容没有对应的结构化接口，D 会诚实标注"基于训练知识，可能非最新"，不会编造具体的最新事件。
- **行业板块数据依赖 `push2.eastmoney.com`**：部分本地代理环境下这个域名可能连接不稳定（与筹码分布是同一类限制），失败时优雅降级，不影响其余分析。

## Roadmap

- [ ] 接入搜索 API，补齐自由文本类新闻/论坛情绪的覆盖（结构化数据——公告/研报/财务指标——已经不依赖联网检索）
- [ ] D（行业宏观）接入更多结构化宏观数据源，减少对训练知识的依赖
- [ ] 更多输出插件：飞书文档、企业微信、Notion
- [ ] 支持不同角色使用不同 provider（如 A/B/C/D 用便宜模型，E 用更强模型做裁决）
- [ ] pip 可安装包 / PyPI 发布

欢迎 PR。

## 免责声明

本项目仅供技术研究与学习交流使用，**不构成任何投资建议**。AI 生成的分析内容可能存在事实错误、过时信息或逻辑缺陷，据此进行的任何投资操作，风险由使用者自行承担，与本项目及贡献者无关。

## License

MIT，见 [LICENSE](LICENSE)。第三方数据接口（akshare、腾讯、东方财富等）的使用需遵守各自服务条款。
