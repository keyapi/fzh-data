---
okf: v0.1
type: Reference
title: "中文意图路由（intent_router）—— TypeSafe Jev + 置信度闸门"
date: 2026-09-21
category: docs/solutions/tooling-decisions/
module: intent_router
problem_type: tooling_decision
component: tooling
severity: low
applies_when:
  - "需要把一句中文需求路由到本仓库 30+ 个模块中的一个，而不是靠触发词关键词匹配"
  - "要在流程里引入带概率、可编程的语义判断（分类 / 路由 / 打分），而不是让模型生成文本"
  - "要给 TypeSafe Jev 写调用代码，或判断 confidence / ambiguity 能不能当闸门用"
  - "在 git worktree 里读父仓库 .env 取不到凭证（本仓库既有三个加载器都犯这个错）"
tags: [typesafe, jev, system-one, intent-routing, llm, worktree, env]
---

# 中文意图路由（intent_router）—— TypeSafe Jev + 置信度闸门

## 背景

本仓库有 30+ 个业务模块，Agent 靠 `.agents/skills/*/SKILL.md` 的**触发词**匹配。触发词是关键词匹配，不是语义：一句「帮我把这周的 BOM 成本导进赛狐采购成本」要同时命中"成本 / BOM / 赛狐"才落到 `item-cost`；而 `item-cost` / `stock-init` / `warehouse-restock` **同吃 EN BOM 成本**，触发词天然分不开。

目标：输入一句中文需求 → 输出该由哪个模块接。**只分类，不执行** —— 业务动作仍交回对应模块自己的流程。

## 决策

选 **TypeSafe Jev / System One**（决策模型，返回带概率的判定，不生成文本）+ **原生 `requests`**（不引 SDK，零新依赖，与仓库既有的 DeepSeek / Qwen 调用风格一致）。

- `catalog.yaml` 为**运行时目录真源**，与 `AGENTS.md` 模块索引表由 `tests/test_catalog.py` 断言**集合相等**
- 一次请求问 3 个问题：`module`（多选一 + `none`）、`ambiguity`、`verb`
- `criteria` 用 **object** 形式 `{coverage, exclusions, examples}`；`exclusions`（"不用于…"）是分开兄弟模块的关键
- `none` 选项恒由 `build_payload()` 追加，**不进 catalog** —— 防止重新生成时被漏掉
- 阈值闸门 + `none` 兜底；退出码 0/1/2/3 复用 `dispatch.py` 的通用约定，但**状态词表保持独立**

## 为什么不自动派生 catalog

实测三种自动源都不成立：`.agents/skills/` 的目录数比 AGENTS.md 模块索引表多十几个且互有出入；触发信息散在**三种形状**（`triggers:` 列表 / `trigger:` 单值 / 内嵌在 `description` / 还有完全没有的）；目录还是**多对一**（`sellfox-api` 与 `sellfox-combo-create` 同指 `SELLFOX_API/`）。所以人工策展 YAML + 一个集合相等测试卡漂移。

> 该测试**已经按设计生效过一次**：PR #249 往 AGENTS.md 加了 `ce-okf` 行，合并后漂移测试立刻报错并打出差集 `只在 AGENTS.md 里：['ce-okf']`，补上 catalog 条目即恢复。这正是它该做的事 —— 响亮失败，而不是静默错路由。

## 实测（真实调用，非推测）

**31 条标注中文样例全中**（catalog 从 33 长到 56 项期间多次重跑，均无回归）；「那个东西弄一下」与「帮我订一张去上海的机票」均正确落 `none`。单次约 9815 输入 token ≈ **$0.00041**。

两个反直觉结论，都已写进代码文档：

1. **`confidence` 几近饱和：0.98–1.00**（连 `none` 胜出时也是）。它是**分布集中度不是正确率**，所以 `--min-confidence` 实际**不触发** —— 它只防「模型犹豫」，不防「模型自信地分错」。**真正兜底的是 `none` 选项**。
2. **`ambiguity` 不具区分度**：只跨 0.66–0.98，清晰请求与域外请求的取值区间重叠（方向正确但不是可用信号）。因此只在「无法判定」分支显示，命中分支不显示，避免把常数读成风险信号。

对抗「自信的错」的唯一手段是**默认总打印 top-3 候选**，并滤掉概率 < 0.005 的填充项。

## 坑

- **worktree 里 `.env` 在 `parents[4]`，不是 `parents[1]`。** 本仓库既有三个 `.env` 加载器（`amazon_pairing/judge.py` 的 `parents[1]`、`parcel_track/cli.py` 走到 `AGENTS.md` 就停、`EN_API/translate_item_group_names.py` 硬编码 3 层）**在当前 worktree 全部取不到 key**。改法是有界上溯（`env.py`，就近优先 + `setdefault` 只补不覆盖），两种布局都能命中。
- **YAML 会把裸写的数字标量强制转换**：`examples` 里的 `401` 被解析成 int，导致 string 形式 criteria 渲染崩溃。数据加引号 + 渲染层显式 `str()` + 加回归测试。
- **worktree 里不要 `uv run`**（另建 `.venv`）。用父仓库解释器 + `PYTHONPATH` 指向 worktree 根。
- **`AGENTS.md` 表格解析脆性**：需容忍字面量 `—` 目录（`frappe-*`）、brace 展开（`web-automation`）、跨行重复目录（`SELLFOX_API/`）。
- **`criteria` 用 object 形式是安全的**，但不是照文档猜的：实现前先用 2 选项 payload 打了一发真实请求确认（HTTP 200，无 422）。官方 `choice.md` 例 3 也用了 object + 自定义字段名。

## 参考

- 代码与契约：`intent_router/AGENT_HANDOFF.md`、`intent_router/docs/reference/typesafe-contract.md`
- 官方：<https://docs.typesafe.ai/patterns/intent-routing.md>、<https://docs.typesafe.ai/cookbooks/skill_suggestion.md>
- 相关：`CONCEPTS.md` 的「意图路由 (intent_router)」词表
