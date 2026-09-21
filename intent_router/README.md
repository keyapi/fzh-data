---
okf: v0.1
type: Guide
title: intent_router — 中文意图 → 本仓库模块路由
description: 用 TypeSafe Jev / System One 把中文请求路由到本仓库业务模块，输出模块名 + 目录 + 置信度；置信度不足不猜。
tags: [intent-router, typesafe, jev, routing]
updated: 2026-09-21
---

# intent_router — 中文意图 → 本仓库模块路由

输入一句中文需求，输出它属于本仓库哪个业务模块（模块名 + 目录 + 置信度）。判断引擎是
**TypeSafe Jev / System One** —— 一个不生成文本、只返回带概率判定的决策模型。

## 它解决什么问题

本仓库的模块索引表有 30 多个模块，Agent 目前靠 `.agents/skills/*/SKILL.md` 的**触发词**匹配。触发词是关键词、
不是语义，所以：

- "帮我把这周的 BOM 成本导进赛狐采购成本" 要同时命中"成本/BOM/赛狐"才落到 `item-cost`
- `item-cost` / `stock-init` / `warehouse-restock` 三个模块**同吃 EN BOM 成本**，触发词天然分不开

本模块做的是**语义前置分流**：给出模块名，然后交回给对应模块自己的流程。它**不**执行任何业务动作。

## 快速开始

```bash
# 把一句中文请求路由到某个模块
uv run python -m intent_router.cli route "帮我把 BOM 成本表导进赛狐的采购成本"

# 看完整候选概率分布
uv run python -m intent_router.cli route "统计一下上个月的尾程异常" --show-candidates

# 给脚本用
uv run python -m intent_router.cli route "导入库存初始值" --json

# 核对 catalog（全部模块 + none）
uv run python -m intent_router.cli catalog
```

### 三态输出

**(a) 命中 —— 退出码 0**

```
模块      item-cost
目录      item_cost_sx/
置信度    1.00  (阈值 0.50)
动作      apply
模型      jev-1.13.0
候选      item-cost 1.00
下一步    cd item_cost_sx/ && uv run python bom_cost_to_saihu_item_cost.py
```

**(b) 无法判定 —— 退出码 3**（置信度低于阈值，或模型选了 `none`）

```
结果      无法判定，需人工/澄清
原因      模型选择 none（请求与任何模块都不匹配）
歧义度    0.96
模型      jev-1.13.0
候选      none 1.00
建议      请补充：平台(赛狐/EN/通途)？数据源文件？动作(生成导入文件 / 写回)？
```

**(c) 调用失败 —— 退出码 2**

```
结果      调用失败
原因      HTTP 401：{"detail":{"error_type":"authentication_error",...}}
提示      检查 TYPESAFE_API_KEY；已查找的 .env：D:\Work\赛狐\Cursor\.env；可用 --env-file 指定
```

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 命中模块 |
| 1 | 用法错误或缺凭证 |
| 2 | API / 传输错误 |
| 3 | 需人工介入（低置信度或 `none`） |

沿用 `web_automation/scripts/dispatch.py` 的**通用退出码约定**，但**不复用它的状态词表** ——
那是「执行环境状态」（`NEED_LOGIN`/`NEED_BROWSER`），本工具的「低置信度」是「认知不确定」，
混用会让两个词都失准。而且 AGENTS.md 规定通途/赛狐/浏览器任务的唯一权威是 `dispatch.py`，
本工具只给模块名、不替它派发状态。条目带 `web_task` 时，下一步会打印 dispatch 命令。

## 凭证

`TYPESAFE_API_KEY`。存放于**父仓库** `D:\Work\赛狐\Cursor\.env`。

本模块的 `.env` 加载是**有界上溯**的（`env.py`）：从包目录逐级向上找 `.env`，就近优先，
只补未 export 的变量。这一点很重要 —— 在 git worktree 里，包目录到父仓库 `.env` 之间隔着
4 层（`parents[4]`），而本仓库既有的三个 `.env` 加载器都假设「仓库根 = `parents[1]`」，
在 worktree 里全部取不到 key。

## 关键行为（别被数字误导）

- **`--min-confidence` 在本仓库这个目录上几乎不触发**。实测：10 条标注中文样例
  全部 `confidence ≥ 0.97`（多数为 1.00），连"那个东西弄一下"和"帮我订机票"（都落到 `none`）也有 0.99。
  `confidence` 是**分布集中度**不是正确率 —— 它只防「模型犹豫」，不防「模型自信地分错」。
  **真正兜底的是 `none` 选项**（实测有效：模糊请求与域外请求都正确落 `none`）。
- 默认**总是**打印 top-3 候选（不只在低置信时），这是发现「自信的错」的唯一窗口。
- 候选行会**滤掉概率 < 0.005 的选项** —— 概率挤在一个选项上时，其余都是 0.00，列出来只是噪音。
- `歧义度` 只在「无法判定」分支显示。实测它只跨 0.87–0.98，且清晰请求（0.95）与域外请求
  （0.96）几乎重叠，**不具区分度**，只在命中分支显示会误导成"有风险"。

## 目录

```
intent_router/
├── cli.py            # argparse 入口；三态渲染；退出码
├── router.py         # 编排：build → POST（退避重试）→ parse → 阈值闸门
├── typesafe.py       # 纯函数：build_payload / parse_answer / normalize_option / apply_gate
├── catalog.py        # 读 catalog.yaml + 解析 AGENTS.md 做漂移比对
├── catalog.yaml      # ★运行时目录真源（模块 + 路由描述）
├── env.py            # .env 有界上溯加载
├── AGENT_HANDOFF.md  # Agent 入口
└── docs/             # OKF v0.1 bundle
```

细节见 [`AGENT_HANDOFF.md`](AGENT_HANDOFF.md) 与 [`docs/`](docs/)。
