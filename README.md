# ai-stock-debate

多角色辩论式 A 股个股投研分析工具。五个 AI 角色——新闻情绪（A）、基本面（B）、技术面（C）、行业宏观（D）、首席决策官（E）——分别独立分析后由 E 综合裁决，给出操作建议、止损位、目标价。

**核心特点：模型可插拔。** 不锁定任何一家 AI 厂商——用 Claude、GPT，还是 DeepSeek、Kimi、通义千问、智谱 GLM 这些国内模型，都能跑起来。你只需要在 `.env` 里换一个 provider 名字。

## 效果预览

跑完一次分析会在 `output/reports/` 生成一份暗色主题 HTML 报告，包含：顶部实时行情栏、E 的综合决策卡（操作方向/置信度/止损/目标价）、A/B/C/D 四个角色可展开的完整分析卡片、历史决策时间线。

## 快速开始

要求 Python 3.10+。

```bash
git clone <你的仓库地址> ai-stock-debate
cd ai-stock-debate
pip install -r requirements.txt
cp .env.example .env        # Windows CMD 用: copy .env.example .env
# 编辑 .env，填入 LLM_PROVIDER / LLM_API_KEY / LLM_MODEL

python analyze.py 002475
```

跑完后终端会打印生成的报告路径，直接用浏览器打开即可。

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

```
用户输入股票代码
      │
      ▼
数据层（data/fetcher.py）── 腾讯行情/K线（双源容错）、akshare 融资融券/龙虎榜/北向持股/公告/
      机构研报（评级+盈利预测）/官方业绩预告/近8期财务指标
      │
      ▼
记忆层（memory/manager.py）── 读取该股票历史档案，判定分析范围：
      │   · 首次 / 距上次 >30天 → 完整分析
      │   · 距上次 3-30天       → 区间增量（只看新增K线/公告）
      │   · 距上次 ≤2天         → 当日增量（改用分时K线）
      ▼
Agent 编排层（agents/orchestrator.py）
      │   A/B/C/D 并行调用 LLM → E 综合裁决（串行）
      ▼
输出层（output/writers/）── HTML（默认）/ Markdown
```

**关于"分析范围判定"**：这套机制只影响"要不要重新处理旧数据"（省 token、省时间），不影响"推理是否完整记录"——不管哪种范围，每次分析的完整报告都会生成，不会因为是增量分析就被压缩成一行结论。同一支股票分析得越多次，记忆档案越丰富，后续分析也越快越省钱。

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
- **不含飞书/企业微信等文档平台集成**：默认只输出本地文件。

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
