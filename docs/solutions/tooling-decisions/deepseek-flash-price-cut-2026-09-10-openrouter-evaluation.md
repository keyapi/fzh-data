---
okf: v0.1
title: DeepSeek flash 系列 2026-09-10 降价改价 + OpenRouter 迁移评估（结论：不迁）
date: 2026-09-10
category: tooling-decisions
module: new-api-deployment
problem_type: tooling_decision
component: tooling
severity: medium
applies_when:
  - DeepSeek 官方调整 flash 系列定价，new-api 内置价目表需要同步
  - 评估是否把 DeepSeek 上游从官方 API 换成 OpenRouter 等聚合网关
  - 需要按真实用量结构（缓存命中占比、峰谷占比）做供应商成本对比
symptoms:
  - cron 分时定价脚本内置旧价，官方调价后 new-api 计费与官方账单不一致
  - 只看标价（输入/输出单价）会误判 OpenRouter 更便宜，忽略缓存命中单价
root_cause: external_pricing_change
resolution_type: config_change
related_components: [database, cron]
tags: [new-api, deepseek, pricing, openrouter, cache-hit, cost-analysis, cron, model-ratio]
---

# DeepSeek flash 系列 2026-09-10 降价改价 + OpenRouter 迁移评估（结论：不迁）

## Context

DeepSeek 官方 2026-09-09 公告，两件事：

1. **2026-09-10 12:00（北京时间）起 flash 系列降价**：空闲时段 缓存命中 ¥0.02 / 缓存未命中 ¥1 / 输出 ¥4（每百万 tokens）；高峰为空闲的 2 倍 → ¥0.04 / ¥2 / ¥8。**只涉 `deepseek-v4-flash` 与 `deepseek-v4-flash-vision-exp`，V4 Pro 不变。**
2. **2026-09-14 12:00 起 V4 Pro 下线**，请求路由到 V4.1 Flash，**按 V4.1 Flash 计费**。

公司 new-api 网关（`api.vilavi.cn`）的 `deepseek_time_pricing.py` 内置价目表仍是 2026-08-17 的旧价（flash 空闲 ¥1.5/¥4.5/¥0.05、高峰 ¥3/¥9/¥0.10）。若不改，12:00 的 cron 会按旧价写生产库，用户被多收，直到脚本更新。

同时评估「是否把上游从 DeepSeek 官方切到 OpenRouter」。

## Guidance

### 一、用量结构（决定一切的前提）

用 DeepSeek 官方账单导出（`amount-*.csv` + `cost-*.csv`）做**按行单价反解**：官方账单把高峰/空闲拆成**不同单价行**（同一 `(日期, 模型, type)` 会出现两条不同 `price`），因此可以精确还原峰谷 token 占比，不需要假设。

8/17–9/10 共 24 天（峰谷计价期）：

| 模型 | 旧价 ¥ | 新价 ¥ | 降幅 | 高峰 token 占比 |
|---|---|---|---|---|
| deepseek-v4-flash | 573.25 | 332.12 | -42.1% | **79.4%** |
| deepseek-v4-flash-vision-exp | 38.48 | 19.82 | -48.5% | 70.3% |
| deepseek-v4-pro | 266.37 | 266.37 | 0% | 79.9% |
| **合计** | **878.10** | **618.31** | **-29.6%** | — |

折合 30 天：**¥1098 → ¥773，省约 ¥325/月**。

flash 家族 token 结构：**缓存命中 97.2%**、输入未命中 2.37%、输出 0.38%。（agent 类工作负载，长前缀复用。）

对账方法可信度：`sum(price × amount)` 与 `cost-*.csv` 完全相等（937.88 = 937.88），说明单价列可直接用于重算。

### 二、OpenRouter 是否更划算 → 否

用**真实 token 结构 + 实际 79.4% 高峰**折算 `deepseek/deepseek-v4-flash-0731` 各上游（汇率 7.3）：

| 上游 | USD/1M (in / out / cache) | 24天 ¥ | vs 官方新价 |
|---|---|---|---|
| **DeepSeek 官方新价** | ¥1~2 / ¥4~8 / ¥0.02~0.04 | **358.07** | 基准 |
| OpenInference fp8 | $0.050 / $0.160 / $0.0130 | 359.60 | 100% |
| DeepInfra fp8 | $0.060 / $0.180 / $0.0150 | 415.84 | 116% |
| DigitalOcean | $0.080 / $0.252 / $0.0252 | 681.53 | 190% |
| Together | $0.140 / $0.280 / $0.0300 | 835.82 | 233% |
| SiliconFlow fp8 | $0.220 / $0.660 / $0.0280 | 870.95 | 243% |
| **StreamLake fp8** | $0.132 / $0.396 / **$0.0042** | **217.46** | **61%** |

**根因**：成本由缓存单价主导（官方新价下缓存行占 ¥119/¥358；OpenInference 下占 ¥315/¥360）。官方缓存单价 ¥0.02~0.04/M ≈ $0.0027~0.0055，**比 OpenRouter 几乎所有上游都低**——最便宜的 OpenInference 是 $0.013/M，高峰时是官方的 2.4 倍。输入/输出确实便宜很多（OpenInference 输出 $0.16 vs 官方高峰 $1.096），但省下的 ¥109 被缓存行的 ¥+196 吃掉。

**唯一赢家是 StreamLake**（缓存 $0.0042/M），便宜约 39%——但要 pin 单点、失去回退，且上游 uptime 98.8%、fp8 量化。

> 注意：OpenRouter 缓存本身没问题。官方文档明示 DeepSeek 自动缓存、无需配置，写入按输入价计、读取 0.1x；靠 sticky routing + `session_id` 把后续请求钉在同一上游以保热缓存。是**单价**不占优，不是能力缺失。

### 三、new-api ↔ OpenRouter 接入事实

- **new-api 支持 OpenRouter 渠道：`ChannelTypeOpenRouter = 20`**，默认 base URL `https://openrouter.ai/api`，复用 `openai.Adaptor`（wire-compatible）。
- **上游切换分两层**：
  - **OpenRouter 内部：默认自动**，不是固定。按「避开近 30 秒故障的上游 → 在健康上游中按价格平方反比加权」做负载均衡，其余作 fallback。想固定需请求体带 `provider.order` / `only` / `sort`；new-api 的 type-20 走 OpenAI 适配器，**大概率不透传 `provider` 字段**，因此从 new-api 侧无法指定「只用哪个上游」。
  - **new-api 内部**：同一模型可配多渠道 + 优先级 + 失败重试，可实现「官方为主、OpenRouter 兜底」——按错误/限流切，**不按价格切**。

### 四、中国用户实际掣肘（社区实测）

| 维度 | 情况 |
|---|---|
| 网络 | 服务器在海外、无就近节点；直连首 token 1500–3000ms 且不稳，走代理 600–1200ms；Cursor/Claude Code 这类高频调用有「隔一会就断」的反馈 |
| 支付 | Visa/MC 或 USDC（最低 $10，卡充值约 5.5% + $0.35）；支付宝说法矛盾、有拒付先例 |
| 账单地址 | 填中国大陆/港澳会触发限制（对 Claude/GPT/Gemini 报 403）；社区经验是填美国免税州 |
| 封号 | 有按支付方式/地址识别国内用户的 403 / 封禁报告；OpenRouter 曾通知中国用户无法调用御三家 |
| 数据 | 第三方上游可能留存数据；需 `data_collection: deny` / ZDR，new-api 渠道侧难以设置 |
| 质量 | 最便宜档多为 fp4/fp8 量化，输出与官方 fp 有偏差 |

**结论：不迁移。** OpenRouter 只在「愿意 pin 到 StreamLake 单点」时省 ~39%，代价是代理、支付、合规、质量、可控性，且 pin 后无回退。留作降级/兜底备选即可。

### 五、实施（本次已做）

**`deepseek_time_pricing.py`**：

1. `PRICING` 更新为 9-10 12:00 新价（flash / vision-exp 同价；pro 不变）：
   ```python
   "deepseek-v4-flash": {
       "peak": {"input": 2.0, "output": 8.0, "cache": 0.04},
       "off":  {"input": 1.0, "output": 4.0, "cache": 0.02},
   },
   ```
   换算结果：flash 空闲 `ModelRatio=0.068493` / 高峰 `0.136986`；`CompletionRatio` 恒为 `4.0`；`CacheRatio` 恒为 `0.02`。（pro 不变：高峰 `0.616438` / 空闲 `0.308219`，Completion `3.0`，Cache `0.033333`。）

2. 新增 **`PRO_EOL = datetime(2026, 9, 14, 12, 0, tzinfo=TZ)`** 与 `PRO_ROUTES_TO`：`now >= PRO_EOL` 时把 `deepseek-v4-pro` 的价目替换为 flash 的（路由到 V4.1 Flash 按其计费）。**V4.1 Flash 单价官方未单独公布**，暂等同 flash 系列，9/14 后必须用真实账单核对。

3. 新增 **`--at "YYYY-MM-DD HH:MM"`**：覆盖当前时间，**只打印不写库**（dry-run），用于在 9/14 前演练 Pro 下线分支。刻意做成 dry-run——否则会提前把生产的 pro 价改成 flash 价，造成真实错账。

**`sync_pricing.py`**：`PRICING` 同步为新价（该脚本只 PRINT 不写库，是换算公式的参照）。

**部署**：`scp` 覆盖 `/opt/new-api/deepseek_time_pricing.py`（覆盖前先 `cp -a` 备份为 `.bak-<ts>`），并即时跑一次无参运行写入新价——不等 12:00 cron。

## Why This Matters

- **缓存命中单价才是真正的成本杠杆**：97% 的 token 是缓存命中，所以「输出便宜 3 倍」的吸引力会被「缓存贵 2.4 倍」抵消。只比标价（输入/输出）会得出错误结论。
- **按行单价反解峰谷占比**：官方账单把两档拆成不同单价行，这比「假设 8 小时/24 小时」之类的估算精确得多，也让「我们用量是否集中在高峰」变成可验证事实（答案：79.4%，是）。
- **`--at` 必须是 dry-run**：任何「改时间」的测试开关如果会写库，就会在生产上提前应用未来价格。测试开关的副作用面必须为零。
- **`PRO_EOL` 是已知的未来变更，写进常量而不是等 9/14 再说**：cron 脚本无人值守，未来生效的规则必须提前编码，否则 9/14 当天必然错账。
- **量化上游不是等价替换**：OpenRouter 最便宜档是 fp4/fp8，且不同上游质量/上下文/uptime 不同；「同一个模型名」不等于「同一个服务」。

## When to Apply

- DeepSeek（或其他上游）调价后，同步 new-api 内置价目表。
- 评估从官方直连迁到聚合网关（OpenRouter 等）时——先算**缓存命中占比**，再比价。
- 任何「按时间/日期生效」的计费规则改动。

## Examples

**生产验证实测（2026-09-10 11:22 CST，高峰时段）**：

```
ModelRatio      {"deepseek-v4-pro": 0.616438, "deepseek-v4-flash": 0.136986, "deepseek-v4-flash-vision-exp": 0.136986}
CompletionRatio {"deepseek-v4-pro": 3.0,      "deepseek-v4-flash": 4.0,     "deepseek-v4-flash-vision-exp": 4.0}
CacheRatio      {"deepseek-v4-pro": 0.033333, "deepseek-v4-flash": 0.02,    "deepseek-v4-flash-vision-exp": 0.02}
```

连跑第二次全部「无需变更」，幂等成立。

**Pro 下线分支 dry-run（`--at "2026-09-15 12:00"`）**：

```
V4 Pro 已下线(>= 2026-09-14 12:00)，按 deepseek-v4-flash 价目计费
ModelRatio 将更新 -> {..., "deepseek-v4-pro": 0.068493}
```

**12:00 边界**：cron `0 12 * * 1-5` 会切到新空闲价（flash `0.068493`）；即便 12:00 那次先于部署跑，`*/30 * * * *` 兜底 cron 也会在 30 分钟内纠正。

## 待办 / 风险

- [ ] **9/14 后用真实账单核对 V4.1 Flash 单价**是否等于 flash 系列价；不等则改 `PRO_ROUTES_TO` 或为 pro 单列价目。
- [ ] **模型改名风险**：V4.1 Flash 上线后 DeepSeek 可能把 `deepseek-v4-flash` 改名（内测名 `deepseek-v4.1-flash-expires-on-0910`）。需拉 `GET https://api.deepseek.com/models` 核对；若改名，`ModelRatio`/`CompletionRatio`/`CacheRatio` 要加新 key，**且用户客户端配置要同步改**（影响面大，先报告再动）。
- [ ] OpenRouter 未接入，仅作降级备选记录在案。

## Related

- 脚本：`new-api-deployment/deepseek_time_pricing.py`（生产 `/opt/new-api/deepseek_time_pricing.py`）
- 换算参照：`new-api-deployment/sync_pricing.py`
- 交接文档：`new-api-deployment/AGENT_HANDOFF.md` 第四节「定价配置」
- 前置方案（分时定价机制本身）：[new-api-deepseek-time-based-pricing-automation.md](new-api-deepseek-time-based-pricing-automation.md)
- 用量原始数据：`new-api-deployment/deepseek/usage_data_2026-08-12_2026-09-10.zip`

### 原始来源

**DeepSeek 降价**
- <https://api-docs.deepseek.com/zh-cn/quick_start/pricing/>
- <https://m.ithome.com/html/999953.htm>
- <https://www.techweb.com.cn/it/2026-09-09/2978890.shtml>
- <https://cbgc.scol.com.cn/news/7938588>

**V4 Pro 下线 / V4.1 Flash**
- <https://www.chinaz.com/ainews/30949.shtml>
- <https://dahecube.com/spiderdetail.html?spidid=857614>
- <https://www.cls.cn/detail/2479030>

**OpenRouter 价格与路由**
- <https://openrouter.ai/deepseek/deepseek-v4-flash-0731>
- <https://openrouter.ai/api/v1/models/deepseek/deepseek-v4-flash-0731/endpoints>
- <https://openrouter.ai/docs/features/provider-routing>
- <https://openrouter.ai/docs/features/prompt-caching>

**new-api 渠道支持**
- <https://github.com/QuantumNous/new-api/blob/main/constant/channel.go>
- <https://deepwiki.com/QuantumNous/new-api/4-channel-rest-api>

**中国用户接入风险**
- <https://ofox.ai/zh/blog/openrouter-complete-guide-china-developers-2026/>
- <https://codepick.dev/zh/guides/openrouter-guide/>
- <https://linux.do/t/topic/2184411>
- <https://linux.do/t/topic/1977251>
- <https://global.v2ex.co/t/1201526>
