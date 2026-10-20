---
okf: v0.1
type: Research
title: "AI / Agent SOTA 与供应链决策系统适用性（2025–2026）"
date: 2026-10-20
status: active
module: supply-chain
tags:
  - ai-agent
  - demand-forecasting
  - time-series-foundation-models
  - text-to-sql
  - llm-or
  - human-in-the-loop
evidence_policy: "类型 P=论文/基准，V=厂商材料，I=独立评测/独立报道，C=官方规范/案例；强度 A=论文/基准/规范，B=可复现工程或独立评测，C=厂商文档/案例，D=博客/轶事"
sources_count: 35
---

# AI / Agent SOTA 与供应链决策系统适用性（2025–2026）

> 适用对象：约 5 人技术团队、稀疏/间歇需求、缺货截断、频繁新品、多渠多仓、无数据仓库、Excel/Google Sheets 为主。
> 证据访问日期统一为 2026-10-20。厂商声明标 `V`，独立证据标 `I`，两者不混写。未核实处显式写「未证实」。

## 1. 结论先行

1. **时序基础模型（TSFM）值得做挑战者，不应直接做主模型。** 独立研究显示 TimesFM 在汇总精度上可排第一，但优势集中在高周转的平滑/波动品；在占多数的间歇品上，最佳模型随误差指标变化，且基础模型存在系统性低估风险 [S3-003]。更关键的是，预测精度排名与订单服务水平排名可以负相关（工业面板 Spearman −0.555），最低误差不等于最高服务水平 [S3-004]。
2. **稀疏需求的胜负手是「偏差校正 + 分层选模 + 决策指标」，不是换更大的模型。** 同一研究用零训练成本修正 Chronos-2 的实例归一化偏差，把 90% 服务目标下的单物料满足率代理从 77.5% 提到 92.0%，整单满足率从 54% 提到 63% [S3-004]。先做 TSB/Croston/AutoETS + 偏差校正，再谈 TSFM。
3. **LLM 不应直接输出预测数字或补货量。** 对三类主流 LLM 时序预测方法的消融显示：移除语言模型或换成简单注意力层，预测性能不降反升；预训练文本知识没有带来优势，模型也没有真正利用时序顺序 [S3-002]。LLM 的真实价值在「解释、编排、草拟、类比、异常分流」，不在「算最终数」。
4. **Agent 的可靠性还不够独立承担数据决策。** τ-bench 中 gpt-4o 级函数调用代理任务成功率 <50%，零售域重复 8 次全对率 <25% [S3-014]；多 Agent 失败分类研究归纳 14 种失败模式，验证缺失/验证错误是独立一类 [S3-015]；企业级 Text-to-SQL（Spider 2.0）o1-preview 基线仅 21.3% [S3-013]。必须用确定性内核 + 语义层 + 人工审批兜底。
5. **给老板的建议：批一个 6–8 周的「影子对比 + 人审」试点，不批平台。** 三轨并行：统计基线 vs TSFM vs LLM 辅助解释；只读、不下单、不写生产库；以服务水平、库存天数、计划员耗时和决策成本验收，不以 MAPE 单项验收。成本上，TSFM 批量推理几乎可忽略，主要成本是人的复核时间与集成。

## 2. 三栏清单（每条附证据）

### 2.1 能用 AI 做（有独立证据或成熟规范支撑）

| 事项 | 具体做法 | 证据 |
|---|---|---|
| 异常检测与分流 | 规则/统计先判异常，LLM 只做归因草稿与工单路由，人确认 | Agent 可靠性上限 [S3-014][S3-015]；LLM 直接算数无增益 [S3-002] |
| 语义层上的自然语言查询 | Agent 按指标名调用 Metric API，不写裸 SQL；无覆盖时明确拒答 | 语义层显著提升准确率 [S3-020][S3-021]；企业 SQL 仍难 [S3-013] |
| 新品相似品检索 | 用商品属性/标题/图片向量找可比品，LLM 归类，人审后给先验 | 冷启动类比方向有初步证据 [S3-034]，但原文数值未复核，按 C 级使用 |
| 代码/模型草稿生成 | LLM 生成数据管道、OR 模型或测试代码，必须由测试/求解器验证 | OptiMUS、LLMOPT 均为「LLM 建模 + 求解器/自校正」[S3-022][S3-023] |
| 报表、邮件、会议纪要 | 只基于已取好的结构化结果生成文字，引用指标 ID 与 as-of | 低风险文本任务；需防注入 [S3-017] |
| 情景叙述与风险摘要 | 把多组确定性情景结果转成老板能读的一页纸 | 工程实践；不做数值计算 [S3-002] |

### 2.2 不能用 AI 做（明确边界）

| 禁区 | 原因 | 证据 | 可推翻条件（falsifier） |
|---|---|---|---|
| LLM 直接产出最终补货量/采购量 | 语言模型组件对时序预测无增益；代理重复可靠性低 | [S3-002][S3-014] | 预注册 12 次滚动起点、两个需求分层上，LLM 直接数值在决策成本上比 TSB/Chronos-2 低 ≥10%，3 个种子同向、无泄漏 |
| 自动审批高金额采购/付款 | 「过度代理」风险；高影响动作需人批 | [S3-018] | 监管与内控允许全自动，且有双跑与回滚审计时另行评估 |
| 在原始表上自由写 SQL 出经营口径 | 企业级 Text-to-SQL 基线仅 21.3%，错得很自信 | [S3-013][S3-020] | 在自有 golden set 上执行+结果双对拍 ≥99%，连续 3 个月无口径事故 |
| 用 LLM 替代统计/优化内核做最终计算 | 数值不是语言模型的强项；OR 模型需约束验证 | [S3-002][S3-022][S3-023] | 见第一行 |
| 无审计的长期记忆驱动决策 | 记忆会漂移、过期、被注入；失败分类含对话历史丢失 | [S3-015][S3-017] | 记忆有版本、TTL、来源与回放，且 A/B 证明不劣于无记忆 |

### 2.3 只能辅助（AI 出建议，人/求解器定案）

| 事项 | AI 的角色 | 确定性/人的角色 | 证据 |
|---|---|---|---|
| 需求预测 | TSFM/统计给分布，LLM 解释驱动因素 | 统计基线、偏差校正、分层选模 | [S3-003][S3-004] |
| 新品预测 | 类比检索、属性映射、先验草稿 | 人审可比品、人工调参 | [S3-034]（C 级） |
| 促销/事件影响 | 从邮件、活动文档抽取结构化事件 | 模型估计弹性、人确认事件窗口 | [S3-017] 防注入 |
| 库存/补货 | 把业务规则翻成 OR 模型草稿 | 求解器算最优、校验器验约束 | [S3-022][S3-023] |
| 审批 | 生成摘要、列风险、给置信度 | 老板/计划员拍板、留 reason code | [S3-024][S3-018] |

### 2.4 LLM 在需求预测中的真实增益与伪需求

| 用法 | 判断 | 证据与说明 |
|---|---|---|
| 直接输出预测数字 | **伪需求** | 消融显示移除 LLM 不降反升；预训练无优势 [S3-002] |
| 生成特征/写特征代码 | **有条件有用** | 前提是有测试与数据校验；LLM 写代码的能力在 OR 建模中被验证，但需求解器验证 [S3-022][S3-023] |
| 新品类比 | **有初步证据** | 属性/参考轨迹/文本嵌入方向一致；但多为单数据集、难复现，按 C 级 [S3-034] |
| 文本信号（评论、活动、舆情） | **有初步证据但弱** | 多品类评论研究方向一致，但样本与基线差异大、原文多不可复现（检索摘要，C/D 级）[S3-035] |
| 异常解释/原因归因 | **只能辅助，独立量化证据未找到** | 见 N-303；不要让解释替代验证 |
| 从人工 override 学习 | **有价值** | 允许人对算法输入做判断性调整，平均利润 +4.92%；但精度提升不等于利润提升 [S3-024] |

**边界 1（必须写进制度）：LLM 不得成为补货量/审批结论的最终产出者。** 证据是三条独立线的交集：LLM 组件对时序预测无增益 [S3-002]、代理重复可靠性低 [S3-014]、精度不等于利润 [S3-024]。推翻条件见 2.2 第一行。

## 3. 时序基础模型实测对比

> 说明：「相对统计基线」只写有来源的方向，不把厂商 SOTA 声明当成独立结论。成本按批量推理量级描述，具体金额见第 8 节。

| 模型 | 适用数据形态 | 相对统计基线 | 独立证据 | 成本 | 私有化 | 结论 |
|---|---|---|---|---|---|---|
| **Chronos-2** | 单变量/多变量/带协变量；促销、节假日等已知未来协变量 | 厂商称 fev-bench/GIFT-Eval 零样本领先；独立稀疏研究指出其归一化偏差会伤服务水平，需校正 | [S3-004] 工业面板 +14.5pp 校正增益；[S3-008] 厂商声明 | 120M，单 A10G >300 序列/秒，CPU 可跑 | Apache-2.0，可私有化 | **首选挑战者**；必须做偏差校正与分层 A/B |
| **Chronos-Bolt** | 单变量；小模型适合大批量、CPU | 汇总精度可竞争；间歇段表现分段依赖，独立研究报告负偏差（具体数值未在可读正文核实） | [S3-003] 汇总/分段结论；[S3-007] 厂商速度声明 | 9M–205M，CPU 可推理；比原 Chronos 快至多 250× | Apache-2.0 | CPU 兜底/快速基线；不作为唯一主模型 |
| **TimesFM 2.5** | 单变量；长上下文 | 独立快消研究汇总第一，但优势集中在高周转平滑/波动品；间歇段最佳模型随指标变化 | [S3-003]；[S3-009] | 200M，16k 上下文 | Apache-2.0 | 平滑/波动品候选；间歇品必须与 TSB 对比 |
| **TimesFM 3.0** | 长上下文、多领域 | 厂商称多基准第一；未独立核验 | [S3-009] | 未披露参数（MLX 基准提到 330M） | 权重仅非商业/非生产；商用需 Google Cloud | **不用于生产**，除非拿到商业授权 |
| **Moirai 1.1 / 2.0** | 单变量/多变量；GIFT-Eval 部分切片有优势 | 无独立稀疏需求评测；GIFT-Eval 分数据集互有胜负 | [S3-001] 部分表；[S3-011] | 参数未披露，量级与同类相当 | Apache-2.0 | 可作为第三候选，先做小样本对拍 |
| **TiRex** | 零样本、长短horizon；xLSTM | 论文称 GIFT-Eval/Chronos-ZS SOTA；未独立复现 | [S3-010] | 未披露吞吐 | **CC BY-NC-ND 4.0，非商业** | 研究对照，不进生产 |
| **TimeGPT** | 通用零样本；API | 厂商称 top-3；闭源 API，独立可复现性差 | [S3-031] 厂商论文；检索显示无法独立重跑（C 级） | API 计费，成本随调用 | **不可私有化** | 只做小样本 API 试点，不作为主方案 |
| **Lag-Llama** | 单变量零样本（较早） | 2025–2026 主流基准中未纳入本次核验 | 未找到独立稀疏需求证据 | 低 | 开源 | 已被更新模型覆盖，不建议新项目采用 |
| **统计/全局 ML 基线** | TSB/Croston、AutoETS/AutoARIMA、LightGBM 全局模型 | M5 中纯 ML 显著胜统计基准，但仅在丰富协变量/跨学习条件下；仅约 12% 队伍跑赢全部基准 | [S3-005][S3-006] | 极低 | 完全可控 | **必须有**；稀疏品上很可能是最强基线 |

**读表要点**

- GIFT-Eval 覆盖 23 个数据集、144,000 条序列、177M 数据点，但公开基准以平滑、规则采样序列为主，稀疏备件需求很少；不能把 GIFT-Eval 排名直接外推到本公司 [S3-001][S3-004]。
- M5 的胜利条件是「丰富外生变量 + 跨序列学习 + 层级对齐」，且零需求日是最难部分；这正好说明：没有促销/价格/事件等协变量时，ML 的优势会缩水 [S3-005][S3-006]。
- TSFM 的失效模式高度一致：**低估正需求尖峰**、**零需求日与正需求日偏差不对称**、**归一化/分位数处理不当**、**版本/基准污染**。上线前必须做偏差与分层审计 [S3-003][S3-004]。

## 4. Agentic 架构：推荐模式与反例

### 4.1 推荐模式（LLM 编排，确定性内核计算）

```text
用户问题 / 定时任务
  → 意图与槽位解析（LLM，只输出结构化 JSON：指标、时间、渠道、仓库、粒度）
  → 计划器（LLM，从已注册工具清单中选择，不生成裸 SQL）
  → 执行器（确定性：语义层 Metric API / 预测 API / OR 求解器 / 对账服务）
  → 校验器（schema + 不变量 + 对账 + 回放；失败则拒答）
  → 解释器（LLM，引用 metric_id、as_of、行数、口径版本）
  → 人审（prepare → confirm → execute → readback）
```

这与团队已有的 `prepare→confirm→execute→readback` 治理天然契合：LLM 只负责「准备」和「解释」，执行与回读由确定性代码完成。

### 4.2 五个角色分工

| 角色 | 谁来做 | 产出 | 不允许 |
|---|---|---|---|
| 意图解析 | LLM | 结构化查询/任务 JSON | 猜口径、猜渠道 |
| 计划 | LLM | 工具调用序列 | 自由写 SQL、无限循环 |
| 执行 | 确定性代码 | 指标、预测、优化解 | 让 LLM 算最终数 |
| 校验 | 确定性代码 + 第二模型复核 | pass/fail + 证据 | LLM 自评作为唯一验收 |
| 解释/审批 | LLM + 人 | 一页纸、风险、reason code | 自动批准高影响动作 |

### 4.3 反例（不要做）

- **多 Agent 辩论出数字**：失败分类研究显示，失败主要来自规格/协调/验证，而不是模型不够强；增加 Agent 数量不会自动修复验证缺失 [S3-015]。
- **LLM 直连生产库写数据**：OWASP 把「过度功能、过度权限、过度自主」列为独立风险，要求最小权限与高影响动作人审 [S3-018]。
- **LLM 自评作为验收**：τ-bench 的重复可靠性指标说明，单次成功不代表稳定成功；必须用 pass^k 与外部校验 [S3-014]。
- **把网页/邮件/文档内容当指令**：间接提示注入是 OWASP LLM01 的明确类别；外部内容必须隔离并标注为不可信 [S3-017]。
- **无界重试/无 token 上限**：成本与延迟会失控；见第 8 节预算控制。

### 4.4 与确定性计算内核的分工原则

- **LLM 负责「语义」**：理解问题、选工具、解释原因、草拟方案、生成代码草稿。
- **确定性内核负责「数值」**：取数、口径、预测、优化、校验、写回。
- **人负责「目标与例外」**：服务目标、预算、供应商约束、例外审批。
- **一条硬规则**：任何进入审批单的数字，必须能追溯到确定性工具的输出与 metric 版本；LLM 生成的自然语言不得成为数字的唯一来源。

## 5. 语义层 / Text-to-SQL：防止「看起来对、口径错」

企业级 Text-to-SQL 的现实基线很低：Spider 2.0 的 632 个真实工作流问题中，o1-preview 代码代理仅解决 21.3%，而 Spider 1.0 为 91.2%、BIRD 为 73.0% [S3-013]。差距主要来自企业 schema、业务逻辑和多步工作流，不是模型「不会写 SQL」。

**语义层是当前最有效的工程约束。** dbt 的 2026 基准显示，在已建模问题上，语义层把 Sonnet 4.6 从 90.0% 提到 98.2%、把 GPT-5.3 Codex 从 84.1% 提到 100.0%；更重要的是失败形态：Text-to-SQL「会自信地给你一个错数」，语义层「失败就是报错/拒答」[S3-020]。一项 IEEE Cloud Summit 2026 的配对实验（60 个业务问题、4 个模型）报告语义层带来 +15.0 到 +18.3 个百分点提升，McNemar p<0.05（会议摘要，原文页未抓取，按 B 级使用）[S3-021]。

### 5.1 具体机制（按优先级）

1. **指标契约（Metric Contract）**：每个指标有 owner、版本、粒度、单位、过滤条件、时间语义、币种、退货/取消口径、数据新鲜度。示例：

```yaml
metric: net_sales_qty
owner: supply_chain
version: 2026-10-01
grain: sku x channel x warehouse x day
unit: pcs
filters:
  order_status: [shipped, delivered]
  exclude_cancelled: true
time_semantics: business_date_in_local_tz
source: sellfox.inventory_movement
reconcile_with: tongtool.orders.net_qty
tolerance: 0.5%
```

2. **Agent 只按指标名调用**：通过 Metric API / 语义层查询，不生成裸 SQL。语义层把任务从「写聚合」变成「点名指标」[S3-020]。
3. **强制澄清**：问题含「销量」「库存」「在途」等歧义词时，Agent 必须返回澄清选项，不得猜。
4. **Golden Set**：50–100 个手算基准问题，覆盖渠道、仓库、退货、促销、跨期、币种；每次改口径/换模型全量回归。
5. **双跑对拍**：新旧口径并行 4–8 周，差异按 SKU/渠道下钻，超容差进异常报告，不静默丢弃。
6. **结果证据包**：每次回答附 `metric_id`、`as_of`、过滤条件、行数、口径版本；UI 可展开血缘。
7. **显式拒答**：语义层未覆盖的问题返回「无法回答 + 缺哪个模型」，而不是让 LLM 自由发挥 [S3-020]。
8. **服务端注入权限**：渠道/仓库/金额权限由服务端注入，不由模型决定；行级权限在查询层强制执行。
9. **注入隔离**：外部文档、邮件、网页内容标记为不可信，不触发写操作 [S3-017][S3-019]。
10. **变更管理**：指标定义变更走 code review + 版本号 + 生效日期；历史回放必须能选旧版本。

### 5.2 反例

- 让 Agent 直接连生产库、自由 join 原始表：错误率高且错得自信 [S3-013][S3-020]。
- 用 LLM 生成「本月销量」然后让另一个 LLM 检查：验证方与生成方共享同一盲区，不能替代 golden set。
- 语义层只覆盖 20% 指标就上线：未覆盖问题会退回自由 SQL，事故率反而更高。覆盖率不到 80% 时，明确限制 Agent 只能答已覆盖问题。

## 6. LLM + OR 与 HITL 审批设计

### 6.1 LLM + OR 的正确分工

LLM 不求解，LLM **建模**；求解器 **计算**；校验器 **验约束**；人 **定目标**。

- OptiMUS 用 LLM 生成 LP/MILP 模型与求解代码，在 NL4OPT 达 78.8%、ComplexOR 66.7%、NLP4LP 72.0%，比标准 GPT-4 提示提升 20–30 个百分点；但 IndustryOR 这类真实工业问题上只有 37%–46%（2025 扩展版）[S3-022]。
- LLMOPT 用「五要素建模 + 自校正」，平均求解准确率提升 11.08%；自校正把执行率从 80.03% 提到 94.48%，准确率从 54.81% 提到 76.40%，但 IndustryOR 仍只有 44% [S3-023]。
- 结论：LLM 适合把「业务规则」翻译成「模型草稿」，不适合在真实工业约束上一次性给最终解。必须有人审约束、求解器验可行、回读验业务。

**可复现的最小模式（伪代码）：**

```python
spec = llm.parse(question, schema=ReplenishmentSpec)      # 只输出结构化规格
model = build_model(spec, data=repo.load(spec.data_refs)) # 确定性建模
plan = solver.solve(model, time_limit=30)                 # HiGHS / OR-Tools
assert verify_constraints(model, plan)                    # 库存、产能、MOQ、保质期
assert reconcile_totals(plan, repo)                       # 与源系统对账
text = llm.explain(plan, evidence=plan.metrics)           # 只解释，不改数
```

### 6.2 HITL 审批分层

| 层级 | 动作 | 审批 | 审计 |
|---|---|---|---|
| L0 | 只读查询、报表 | 自动 | 记录问题、指标、as-of |
| L1 | 低金额补货建议 | 一键采纳/拒绝 | 采样复核 + reason code |
| L2 | 中高金额采购、跨仓调拨 | 计划员 + 主管 | 双人、理由、回读 |
| L3 | 写入 ERP/赛狐/通通、付款 | 双人 + 回读 + 回滚预案 | 全量日志、不可篡改 |

- 高影响动作人审是 OWASP 的明确建议；下游系统必须自己做授权，不能信任 LLM 的判断 [S3-018]。
- 现场实验证据：允许商家对库存算法的预测输入做判断性调整，平均利润 +4.92%，但「预测更准」并不必然「利润更高」[S3-024]。因此审批指标必须是利润/服务/库存，不是 MAPE。
- 便利店补货现场实验：简单算法 + 经理处理例外，服务水平提升 2.9%（不增加库存），下单时间从每天 72 分钟降到约 45 分钟（−36.5%）[S3-025][S3-026]。
- MIT 的零售现场实验（约 1,900 SKU）把处理分为自动化、可调自动化、增强三种，发现计划员在不可预测需求下对 AI 有「采纳摩擦」；人何时能增值取决于条件，不是无条件[S3-027]。

### 6.3 人机协议：避免锚定与自动化偏差

- **人先机后（human-first）**：计划员先写下自己的判断，再展示 AI 建议；有实验显示当 AI 错误时，这能把准确率从 37.8% 提到 68.0%，AI 正确时几乎不损失（93.8%→94.3%）（二手论文综述，D 级）[S3-030]。
- **分歧升级（displacement）**：人与 AI 不一致时由第二人裁决；综述显示在四类任务中三类最优（D 级）[S3-030]。
- **解释不是说服**：自动化偏差综述指出，可解释性可能反向强化错误信任，尤其对低 AI 素养用户；解释应促进验证，而不是替代验证 [S3-030]。
- **不要只报采纳率**：采纳率是虚荣指标；要和覆盖后准确率、FVA、服务/库存结果一起报。

### 6.4 采纳率与反馈闭环的度量

| 指标 | 定义 | 用途 |
|---|---|---|
| 展示采纳率 | 采纳推荐行数 / 展示推荐行数 | 粗看接受度，不能单独考核 |
| 净采纳率 | 未被修改直接采纳 / 展示 | 区分「真接受」与「改了再用」 |
| 分层采纳率 | 按 SKU 价值、需求形态、渠道分层 | 找出模型/流程薄弱段 |
| Override FVA | 人工调整后误差变化 / 调整幅度 | 判断人的调整是否增值 |
| 决策周期 | 推荐生成到审批通过的中位时长 | 衡量流程效率 |
| 业务结果 | 缺货率、库存天数、加急成本、呆滞库存 | 最终验收 |
| 校准度 | 高置信度组的采纳率与准确率 | 发现过度自信/信任错配 |

Override 原因码至少覆盖：需求事件、供应问题、价格/促销、数据错误、策略/客户要求、模型不可解释。每季度用 FVA 评估「哪类 override 该保留、哪类该减少」。

## 7. 风险与工程护栏

| 风险 | 机制 | 工程控制 | 证据 |
|---|---|---|---|
| 幻觉/编数 | LLM 生成了不存在的数 | schema 校验 + 必须引用工具输出 + 无证据拒答 | [S3-002][S3-017] |
| 非确定性 | 同一问题两次答案不同 | temperature 低不够；确定性工具、固定种子、版本锁定、回放 | [S3-014] |
| 数据泄漏 | 未来促销/销量进入特征 | 时间切分、as-of join、特征可用时间审计 | [S3-003][S3-004] |
| 提示注入 | 网页/邮件/文档里的指令 | 不可信内容隔离、不触发写操作、工具白名单 | [S3-017][S3-019] |
| 成本失控 | Agent 循环、长上下文 | 最大步数、最大 token、缓存、离线批处理、预算告警 | 第 8 节假设 |
| 口径漂移 | 指标定义被改 | 语义层版本化 + golden set + 双跑对拍 | [S3-020][S3-021] |
| 过度自动化 | Agent 权限过大 | 只读默认、最小权限、高影响人审、下游授权 | [S3-018] |
| 静默错误 | 不报错但数错 | 行数/总额对账、显式拒答、异常报告 | [S3-020] |
| 模型漂移 | 促销/新品改变分布 | 分层监控、滚动回测、偏差告警 | [S3-003][S3-004] |
| 供应商锁定 | 闭源 API 不可审计 | 优先开源权重、保留基线、导出评测集 | [S3-031] |

**上线门禁（缺一不可）**：schema 校验通过、golden set 全绿、双跑差异在容差内、回放可复现、权限最小化、人工审批路径可用、成本上限已配置。

## 8. 成本估算（含假设与算式）

> 以下不是厂商报价，而是用于量级判断的假设。实际价格随供应商/区域/模型变化。

**假设**：1 万–5 万个活跃 SKU；每周跑批；每条序列 1–3 年日粒度；GPU 按 1 美元/小时量级；LLM 输入 3 美元/百万 token、输出 15 美元/百万 token（仅为算式假设）。

| 工作负载 | 算式 | 每次/每周 | 每年量级 |
|---|---|---|---|
| TSFM 批量推理 | 10,000 SKU ÷ 300 序列/秒 ≈ 33 秒；×10 数据准备开销 ≈ 5.5 分钟；按 1 美元/小时 ≈ 0.09 美元/次 | <0.1 美元 | <10 美元（GPU） |
| 5 万 SKU 批量 | 50,000 ÷ 300 ≈ 167 秒；×10 ≈ 28 分钟 ≈ 0.46 美元/次 | <0.5 美元 | <30 美元 |
| LLM 异常解释 | 300 条/周 ×（2,000 输入 + 500 输出）= 60 万输入 + 15 万输出；0.6×3 + 0.15×15 = 1.8 + 2.25 = 4.05 美元/周 | ≈4 美元 | ≈210 美元 |
| Agent 多轮（×3–5） | 4.05 × 3–5 | 12–20 美元 | 600–1,000 美元 |
| 语义层/golden set | 人工建模为主 | — | 一次性 5–15 人日 |
| 人力复核 | 5 名计划员 × 每天节省 0.5–1 小时 × 250 天 = 625–1,250 小时/年 | — | 主要成本项 |

**结论**：模型推理不是瓶颈，**集成与人的时间才是**。因此试点预算应优先给「数据准备、语义层、双跑对拍、审批流程」，而不是 GPU 或大模型订阅。即使 LLM 成本翻 10 倍，也远小于一次系统性缺货/呆滞的损失；但没有护栏的 Agent 成本可以无限膨胀，必须设硬上限。

## 9. 最小验证实验设计（6–8 周）

### 9.1 数据与切分

- 24–36 个月历史；1,000–2,000 个 SKU；按 ADI/CV² 分层（平滑、波动、间歇、块状），每层至少 200 个 SKU。
- 多渠多仓：至少 3 个渠道 × 2 个仓库；含促销、价格、节假日、缺货标记、在途、lead time。
- 滚动起点 12 次，预测 horizon 4/8/12 周；最后 26 周完全留出，不参与任何调参。
- 缺货截断处理：把缺货期销量标为缺失而非 0；同时保留「观测销量」与「需求上界」两套标签，做敏感性分析。

### 9.2 实验臂

| 臂 | 方法 | 目的 |
|---|---|---|
| A | Naive / SeasonalNaive | 最低基线 |
| B | TSB / Croston / AutoETS / AutoARIMA | 统计基线（稀疏需求强基线） |
| C | LightGBM 全局模型（含协变量） | 跨学习基线 |
| D | Chronos-2 零样本 | TSFM 挑战者 |
| E | TimesFM 2.5 零样本 | TSFM 第二挑战者 |
| F | Chronos-Bolt Small 微调 | 小模型微调对照 |
| G | LLM 辅助解释（不改数） | 人效/采纳实验 |
| H | LLM 直接数值（对照，不作为候选） | 验证「不该做」边界 |

### 9.3 指标

- 精度：MASE、CRPS、pinball loss；分需求形态报告。
- 偏差：平均偏差、正/负需求日分开的偏差、低估尖峰的比例。
- 决策：90%/95% 服务目标下的 fill rate、缺货 SKU-天、库存天数、持有+缺货+加急总成本。
- 人效：计划员复核时间、override 率、override FVA、审批周期。
- 工程：单次跑批时延、失败率、回放一致率、单位成本。

### 9.4 Pass / Falsify 规则（预注册）

1. **H1（TSFM 主模型）**：D 或 E 在间歇层 MASE 比 B 最好的统计基线低 ≥5%，且偏差不劣化、服务水平不下降。否则 TSFM 只能做挑战者/辅助，不能做主模型。
2. **H2（LLM 直接数值）**：H 在决策成本上比 B/D 低 ≥10%，3 个种子同向，且无泄漏。否则「LLM 不得出最终数」边界成立并写入制度。
3. **H3（LLM 辅助解释）**：G 使计划员复核时间下降 ≥20%，且覆盖后准确率不下降、override FVA 不恶化。否则不做解释层，只做报表。
4. **H4（HITL）**：人审 + 例外处理比全自动在决策成本上优 ≥3%（参考现场实验的 +4.92% 利润增益量级 [S3-024]）。否则简化审批，保留全自动 + 抽查。
5. **H5（语义层）**：已覆盖问题上 golden set 执行+结果双对拍 ≥99%，未覆盖问题 100% 显式拒答。否则不上线自然语言查询。

### 9.5 执行与停止条件

- 前 2 周：数据清洗、缺货截断标注、语义层指标契约、golden set。
- 第 3–5 周：A–F 回测；G/H 小样本人工实验（10–20 个计划员任务）。
- 第 6–8 周：影子运行（不写生产），出对比报告与一页纸建议。
- 停止条件：任一臂出现不可解释的泄漏、回放不一致、成本超预算 3 倍、或人工复核时间不降反升。
- 通过后再谈第二阶段：只读试点 → 建议写入（人审）→ 小范围自动执行（L1）。

## 10. 证据表

| ID | 主张 | 来源 URL | 类型 | 日期 | 原文摘录/关键节 | 强度 |
|---|---|---|---|---|---|---|
| S3-001 | GIFT-Eval 覆盖 23 数据集、14.4 万序列、1.77 亿点 | https://arxiv.org/abs/2410.10393 | P/I | 2026-10-20 | "23 datasets over 144,000 time series and 177 million data points" | A |
| S3-002 | 移除 LLM 组件不降反升；预训练文本知识无优势 | https://arxiv.org/abs/2406.16964 | P/I | 2026-10-20 | "removing the language model ... does not degrade forecasting performance"; "pretrained LLMs do no better than models trained from scratch" | A |
| S3-003 | TimesFM 汇总第一但优势集中在高周转；间歇段最佳模型随指标变 | https://accesson.kr/jidb/v.17/3/89/59736 | P/I | 2026-10-20 | "TimesFM ranked first on pooled accuracy"; "this performance was concentrated among high-turnover products"; "in the intermittent segment ... the best model changed with the error metric" | A/B |
| S3-004 | 精度排名与服务水平排名负相关；Chronos-2 偏差校正 +14.5pp | https://arxiv.org/abs/2609.13840 | P/I | 2026-10-20 | "Forecast-accuracy rank and order-service rank are negatively correlated ... at -0.555"; "lifts ... from 77.5% to 92.0%" | A |
| S3-005 | M5 预测 42,840 条 Walmart 层级序列 | https://doi.org/10.1016/j.ijforecast.2021.11.013 | P/I | 2026-10-20 | "42,840 time series"；论文第 5 节结论 | A |
| S3-006 | M5 冠军均为纯 ML；仅约 12% 队伍跑赢全部基准，最多约 20% | https://forecasting-strategy.ch/2024/05/16/machine-learning-in-retail-forecasting-results-from-the-m5-competition/ | D | 2026-10-20 | "all of the winning submissions leveraged 'pure' ML models"; "Only c. 12% of the teams managed to outperform all benchmarks"; "up to c. 20%" | D |
| S3-007 | Chronos-Bolt 比原 Chronos 快至多 250×、省内存 20×；Base 205M | https://huggingface.co/amazon/chronos-bolt-base | V | 2026-10-20 | "up to 250 times faster and 20 times more memory-efficient"; "205M" | C |
| S3-008 | Chronos-2 120M、8192 上下文、A10G >300 序列/秒、Apache-2.0 | https://huggingface.co/amazon/chronos-2 | V | 2026-10-20 | "120M-parameter"; "Max. Context Length — 8192"; "over 300 time series forecasts per second on a single A10G GPU" | C |
| S3-009 | TimesFM 2.5 200M/16k，2.5 权重 Apache；3.0 权重非商业 | https://github.com/google-research/timesfm | V | 2026-10-20 | "uses 200M parameters, down from 500M"; "supports up to 16k context length"; 3.0 weights "restricted to non-commercial, non-production use" | C |
| S3-010 | TiRex 论文称 GIFT-Eval/Chronos-ZS SOTA；CC BY-NC-ND | https://arxiv.org/abs/2505.23719 | P/V | 2026-10-20 | "TiRex sets a new state of the art in zero-shot time series forecasting"; "CC BY-NC-ND 4.0" | B |
| S3-011 | Moirai 2.0-R-small（2025-08），仓库 Apache-2.0 | https://github.com/SalesforceAIResearch/uni2ts | V | 2026-10-20 | "Moirai-2.0-R-small (Aug 2025)"; "Apache-2.0 license" | C |
| S3-012 | fev-bench 100 任务、7 域、46 个带协变量任务 | https://arxiv.org/abs/2509.26468 | P/I | 2026-10-20 | "100 forecasting tasks across seven domains, including 46 with covariates" | A |
| S3-013 | Spider 2.0：632 个企业工作流；o1-preview 仅 21.3% | https://arxiv.org/abs/2411.07763 | P/I | 2026-10-20 | "632 real-world text-to-SQL workflow problems"; "only 21.3% of the tasks"; "91.2% on Spider 1.0 and 73.0% on BIRD" | A |
| S3-014 | τ-bench：gpt-4o 级代理 <50%；零售 pass^8 <25% | https://arxiv.org/abs/2406.12045 | P/I | 2026-10-20 | "succeed on <50% of the tasks"; "pass^8 <25% in retail" | A |
| S3-015 | 多 Agent 14 种失败模式，验证缺失/错误独立成类 | https://arxiv.org/abs/2503.13657 | P/I | 2026-10-20 | "14 unique failure modes"; "No or incomplete verification"; "Incorrect verification" | A |
| S3-016 | MCP 定义 Tools/Resources/Prompts；工具调用需用户同意 | https://modelcontextprotocol.io/specification/2025-11-25 | C | 2026-10-20 | "Tools ... actions with side effects"; "hosts must obtain explicit consent before invoking any tool" | A |
| S3-017 | 提示注入含间接注入；建议输出校验、最小权限、高影响人审 | https://genai.owasp.org/llmrisk/llm01-prompt-injection/ | C | 2026-10-20 | "Indirect prompt injections occur when an LLM accepts input from external sources"; "Require human approval for high-risk actions" | A |
| S3-018 | 过度代理=过度功能/权限/自主；高影响动作需人审 | https://genai.owasp.org/llmrisk/llm062025-excessive-agency/ | C | 2026-10-20 | "excessive functionality"; "excessive permissions"; "excessive autonomy"; "require a human to approve high-impact actions" | A |
| S3-019 | AgentDojo：97 任务/629 安全用例；SOTA 模型仍大量失败 | https://arxiv.org/abs/2406.13352 | P/I | 2026-10-20 | "97 realistic tasks and 629 security test cases"; "State-of-the-art LLMs fail at many tasks" | A |
| S3-020 | 语义层把 Text-to-SQL 90.0→98.2、84.1→100；失败形态是报错而非错数 | https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026 | V | 2026-10-20 | "Text-to-SQL will cheerfully give you a wrong number"; "With the Semantic Layer, failure looks like an error message" | C |
| S3-021 | IEEE 配对实验：语义层 +15.0~18.3pp，p<0.05 | https://ieeexplore.ieee.org/document/11627365 | P/I | 2026-10-20 | 会议摘要：60 问题、4 模型、McNemar p<0.05（原文页未抓取） | B |
| S3-022 | OptiMUS 在易/难数据上提升 >20%/>30%；IndustryOR 仍低 | https://arxiv.org/abs/2402.10172 | P/I | 2026-10-20 | "more than 20%" easy; "more than 30%" hard | A |
| S3-023 | LLMOPT 平均求解准确率 +11.08%；自校正提升执行率/准确率 | https://arxiv.org/abs/2410.13213 | P/I | 2026-10-20 | "11.08% average solving accuracy improvement"; "model alignment and self-correction" | A |
| S3-024 | 判断性调整使利润 +4.92%；精度提升不等于利润提升 | https://doi.org/10.1287/mnsc.2024.06321 | P/I | 2026-10-20 | "raised average profitability by 4.92%"; "improved forecast accuracy does not necessarily translate into improved profit" | A |
| S3-025 | 便利店补货系统服务水平 +2.9%，下单时间 −36.5% | https://doi.org/10.1177/10591478251367129 | P/I | 2026-10-20 | 论文摘要（检索）：2.9% service-level improvement；36.5% time reduction | B |
| S3-026 | 独立新闻稿：下单时间 72→45 分钟，人处理例外 | https://www.eurekalert.org/news-releases/1141845 | I | 2026-10-20 | "36.5 percent less time"; "72 minutes a day"; "around 45 minutes after" | B |
| S3-027 | MIT 零售现场实验约 1,900 SKU；计划员存在采纳摩擦 | https://digitalsc.mit.edu/human-ai-collective-intelligence-in-demand-planning/ | I | 2026-10-20 | "approximately 1,900 stock-keeping units"; "reluctance among demand planners to rely on AI-driven algorithms" | B |
| S3-028 | 铁路案例：零样本并非总胜 AutoARIMA，微调后才胜 | https://aws.amazon.com/blogs/machine-learning/how-deutsche-bahn-redefines-forecasting-using-chronos-models-now-available-on-amazon-bedrock-marketplace/ | V | 2026-10-20 | "SMAPE 0.195 versus AutoETS 0.200 and AutoARIMA 0.202"; 第二场景 "0.197 ... versus 0.130"; 微调后 0.127 | C |
| S3-029 | 某全球咖啡连锁 AI 盘点工具约 9 个月后撤下，原因含识别错误 | https://fr.qz.com/starbucks-abandonne-loutil-dinventaire-ai-nomadgo-052226 | I/D | 2026-10-20 | "le comptage automatisé sera retiré"; 误认牛奶种类/漏项；Reuters 报道 | D |
| S3-030 | 自动化偏差综述：XAI 可能反向强化错误信任；人先机后/分歧升级有初步证据 | https://link.springer.com/article/10.1007/s00146-025-02422-7 | P/I | 2026-10-20 | 检索摘要：explainability can backfire；human-first 37.8%→68.0%（二手综述，D 级） | B/D |
| S3-031 | TimeGPT 自称首个时序基础模型；闭源 API，独立复现受限 | https://arxiv.org/abs/2310.03589 | V | 2026-10-20 | "first foundation model for time series"; "zero-shot inference excels" | C |
| S3-032 | MCP 安全：禁止 token passthrough；最小 scope；会话不作为认证 | https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices | C | 2026-10-20 | "Token passthrough ... explicitly forbidden"; "Minimal initial scope set" | A |
| S3-033 | Chronos-Bolt 可 CPU 推理；基准 1024 序列/512 上下文/64 horizon | https://aws.amazon.com/blogs/machine-learning/fast-and-accurate-zero-shot-forecasting-with-chronos-bolt-and-autogluon/ | V | 2026-10-20 | "can also be used on the CPU"; "1024 time series with a context length of 512 ... 64 steps" | C |
| S3-034 | 新品冷启动可用属性+参考轨迹/文本嵌入；原文数值未复核 | https://www.informs-sim.org/wsc25papers/doc107.pdf | P | 2026-10-20 | 检索摘要：CDLF 用静态属性+可比品轨迹+早期销量；PDF 未能解码，按 C 级 | C |
| S3-035 | 评论文本特征在多个单品类研究中提升销量预测；原文多不可复现 | https://onlinelibrary.wiley.com/doi/abs/10.1002/itl2.70158 | P | 2026-10-20 | 检索摘要：评论情感/主题/评分融合提升 RMSE/R²；原文 403，按 C/D 级 | D |

**证据覆盖度声明**：共 35 条证据，全部进入上表。独立、可复现的「稀疏需求 TSFM」证据仍然偏少；在 TimeGPT 私有化、LLM 异常解释、中国跨境场景三个子问题上未达到饱和，见 N-3xx。

## 11. 未找到项（检索词与范围）

| ID | 未找到的内容 | 检索词/范围 | 说明 |
|---|---|---|---|
| N-301 | TimeGPT 在稀疏/间歇 SKU 上的独立同行评审评测 | "TimeGPT intermittent demand", "TimeGPT GIFT-Eval independent" | 仅见厂商声明；闭源 API 难以独立重跑 |
| N-302 | LLM 直接数值预测稳定击败统计基线的独立证据 | "LLM direct forecasting beats statistical baseline intermittent" | 反向证据明确 [S3-002]；未找到支持性 A 级证据 |
| N-303 | LLM 异常解释提升计划员决策质量的量化研究 | "LLM anomaly explanation demand planning user study" | 工程上合理，但缺独立量化；不要把它当已证实收益 |
| N-304 | LLM Agent 在需求计划生产环境的审计级案例 | "LLM agent demand planning production case study 2025 2026" | 多为厂商案例/宣传，缺独立审计 |
| N-305 | 中国跨境电商业态的公开需求预测基准 | "cross-border e-commerce demand forecasting benchmark China" | 未找到可复现公开数据；本公司数据只能自建评测集 |
| N-306 | TSFM 生产级每 SKU 成本（含特征工程/重训/监控） | "time series foundation model inference cost per SKU production" | 只有吞吐/延迟，缺全成本口径 |
| N-307 | Moirai 2.0 在间歇需求上的独立评测 | "Moirai 2.0 intermittent demand evaluation" | GIFT-Eval 分切片有结果，但无稀疏需求专评 |
| N-308 | GIFT-Eval 含全部模型版本的统一聚合榜 | "GIFT-Eval leaderboard aggregate Chronos TimesFM Moirai" | 检索只得到分数据集表，版本混杂 |

**后续补证建议**：优先补 N-303（做 10–20 人的小规模用户实验即可）、N-306（用本公司 1,000 SKU 跑一次全成本核算）、N-305（自建 12 个月滚动评测集）。其余不影响当前决策。
