---
okf: v0.1
type: Reference
title: TypeSafe System One / Jev 契约与本仓库用法
description: System One HTTP 请求/响应契约、三原语、本仓库的三问题设计与阈值口径、实测行为
tags: [typesafe, jev, system-one, api, reference]
resource: intent_router/typesafe.py
timestamp: 2026-09-21
---
# TypeSafe System One / Jev 契约

来源：<https://docs.typesafe.ai/api.md>、<https://docs.typesafe.ai/primitives/choice.md>、
<https://docs.typesafe.ai/patterns/intent-routing.md>、<https://docs.typesafe.ai/cookbooks/skill_suggestion.md>

**Jev 不生成文本**：输入 `state` + 结构化问题，返回带概率的判定。code 拥有 workflow，
模型只在需要语义理解的地方给出可编程的常识判断。

## HTTP 契约

```
POST https://api.typesafe.ai/v1/systemone
Authorization: Bearer <TYPESAFE_API_KEY>
Content-Type: application/json
```

请求体：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `state` | string \| object \| array | 是 | 要评估的内容 |
| `model` | string | 是 | `"jev-latest"`；响应回显解析后的版本，如 `jev-1.13.0` |
| `questions` | map<我方 key, Question> | 是 | key 由我方定，**不发给模型**，答案按同一 key 返回 |

响应体：`{model, answers: {<key>: Answer}, usage: {input_tokens, output_tokens}}`

### 三原语

| 需要 | 类型 | 关键区别 |
|---|---|---|
| 从固定集合里选一个 | `choice` | 选概率最高项；分布可用来比较竞争项。**≤255 项** |
| 判断条件是否成立 | `noul` | 返回"是"的概率；**没有单独的 confidence** |
| 沿描述性维度给程度 | `score` | 概率加权的位置，落在有序等级上（2–10 级） |

`choice` 的 criteria 是 `{选项名: 描述}`。**选项名和描述都会送给模型**，所以描述写得好不好
直接决定准确率。`instructions` 与每条 criteria 都可以是 string / object / array ——
官方示例（`choice.md` 例 3）就用 object 带 `what`/`not_for`/`examples` 三个字段，且明确
**字段名完全由使用者定、没有保留字**。

### 错误码

| 码 | 含义 | 处理 |
|---|---|---|
| 401 | key 缺失或无效 | 不重试 |
| 422 | 请求体校验失败；body 会指明坏字段 | 不重试（是最有价值的排错信号） |
| 429 | 限流 | 退避重试 |
| 529 | 服务过载 | 退避重试 |

计费：**只有输入 token 计费**，输出免费。

## 本仓库的用法

一次 POST 问**三个问题**（官方文档：并行评估，几乎不额外增加延迟）：

| question key | 类型 | 作用 | 参与闸门 |
|---|---|---|---|
| `module` | choice（全部模块 + `none`） | 路由到哪个模块 | ★ 是 |
| `ambiguity` | noul | 请求是否缺关键限定 | 否 |
| `verb` | choice | 动作类型 | 否 |

`module` 的 criteria 每个值形如：

```json
"item-cost": {
  "coverage": "赛狐采购成本导入：从 EN BOM 成本列表计算绍兴发货成本 → 生成赛狐采购成本导入文件",
  "exclusions": "不用于库存初始值导入(stock-init)、不用于商品重尺(item-weight)",
  "examples": ["采购成本", "BOM成本", "绍兴发货成本"]
}
```

`exclusions` 是最难也最关键的部分 —— `item-cost` / `stock-init` / `warehouse-restock` 同吃
EN BOM 成本，全靠"不用于…"把它们分开。

`none` 选项**恒由 `typesafe.build_payload()` 追加在最后**，不进 `catalog.yaml`，
这样重新生成 catalog 时不可能漏掉它。

## 目录真源与防漂移

`catalog.yaml` 是**运行时唯一真源**（运行时不读 `AGENTS.md`，解析散文太脆）。
`catalog.py::parse_agents_md_modules()` 解析 AGENTS.md 的「## 模块索引」小节，
`tests/test_catalog.py` 断言两边**集合完全相等**，漂移时报错并打出差集。

`python -m intent_router.catalog` 可手动跑同一套比对。

为什么不用自动派生（实测结论，2026-09-21）：

- `.agents/skills/` 的目录数比 AGENTS.md 模块索引表多十几个，且两边互有出入
- 触发信息散在**三种形状**：`triggers:` 列表（8 个）、`trigger:` 单值（1 个）、内嵌 description
  （大多数）、以及**完全没有**（5 个）
- 目录是**多对一**：`sellfox-api` 与 `sellfox-combo-create` 同指 `SELLFOX_API/`

没有任何单一自动源成立。

## 实测行为（2026-09-21）

10 条标注中文样例 + 2 条对照，用 `jev-1.13.0` 实测（下表是 **33 项 catalog 时的原始记录**；
后来 catalog 增到 34、35 项又各重跑一次，仍 10/10，`confidence` 0.97–1.00）：

| 样例 | 命中的 choice | confidence | ambiguity | 输入 token |
|---|---|---|---|---|
| "帮我把 BOM 成本表导进赛狐的采购成本" | item-cost | 1.00 | 0.87 | 5550 |
| "导入库存初始值" | stock-init | 1.00 | 0.95 | 5539 |
| "尾程打单出运单标签" | sellfox-shipping | 1.00 | 0.91 | 5541 |
| "统计一下上个月的尾程异常" | parcel-track | 1.00 | 0.91 | 5544 |
| "把商品重尺填一下…" | item-weight | 1.00 | 0.94 | 5551 |
| "生成四级分类导入文件" | category | 1.00 | 0.93 | 5542 |
| "其他出库清零库存" | other-outbound | 1.00 | 0.94 | 5540 |
| "查一下 FedEx 的轨迹和异常报表" | fedex-track | 1.00 | 0.95 | 5546 |
| "帮我把赛狐图片链接更新到物料组主图" | en-image-upload | 1.00 | 0.93 | 5549 |
| "通途订单特殊规则 1.7.0 本地审计" | tongtool-order-cost | 1.00 | 0.88 | 5551 |
| "那个东西弄一下"（模糊） | **none** | 1.00 | 0.98 | 5539 |
| "帮我订一张去上海的机票"（域外） | **none** | 1.00 | 0.96 | 5543 |

**结论一：`confidence` 在本目录上 0.97–1.00、几近饱和**，连 `none` 胜出时也有 0.99。它是**分布集中度**不是
正确率 —— 因此 `--min-confidence` 实际不触发，它只防"模型犹豫"，不防"模型自信地分错"。
**真正兜底的是 `none` 选项**，实测有效。

**结论二：`ambiguity` 不具区分度**。只跨 0.87–0.98，且清晰请求（stock-init，0.95）与域外请求
（0.96）几乎重叠、方向也正确（模糊 0.98 最高）。保留它只作展示，**不得用作闸门**；命中分支
不显示，避免读者把常数读成风险信号。

**结论三：对抗"自信的错"的唯一手段是默认总打印 top-3 候选**，并滤掉概率 < 0.005 的填充项。

单次成本：随 catalog 变大而增 —— 33 项约 5550、35 项约 **5970 输入 token ≈ $0.00025**（$0.042/M 输入）。

## See also

- [intent_router/README.md](../../README.md) — 三态输出与退出码
- [intent_router/AGENT_HANDOFF.md](../../AGENT_HANDOFF.md) — 函数表与边界条件
- [intent_router/catalog.yaml](../../catalog.yaml) — 运行时目录真源
