---
okf: v0.1
type: Guide
title: E3 只读 Agent 原型 — 复现说明
description: 无 LLM 的确定性路由 + 语义层 + 只读工具 + prepare/confirm/execute/readback；15 题评估与结果文件。
date: 2026-10-20
tags: [supply-chain, agent, semantic-layer, read-only]
---

# E3 只读 Agent 原型 — 复现说明

## 1. 这个实验验证什么

用一个窄切片（楔形枕 8 个 SKU × 美中-Daneey 仓 × 2026-03 至 2026-09）验证四件事：

1. Agent 能否选对工具；
2. 能否填对参数（SKU / 仓库 / 渠道 / 时段 / 覆盖期）；
3. 能否拒绝写操作，并给出安全替代；
4. 每个答案是否附带可复核的证据（工具、参数、来源、计算值、回读）。

**不验证**模型智能：路由器是确定性关键词 + 槽位抽取，不调用任何外部 LLM。

## 2. 文件清单

```text
e3_agent/
├── README.md                       # 本文件
├── index.md                        # 目录索引
├── agent.py                        # 路由器 + 语义层 + 8 个只读工具 + 评估
├── questions.json                  # 15 题评估集（含期望状态 / 工具 / 槽位 / 值）
├── results.json                    # 评估输出（由 agent.py --eval 生成）
├── results.md                      # 设计、评估表、判定、失败分析、限制
└── data/
    └── wedge_decision_package.json # 本地内嵌数据（已匿名化）
```

## 3. 快速开始

在仓库根目录执行：

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/e3_agent/agent.py --eval
```

输出：

- 终端打印 15 行评估表与汇总；
- 写入同目录 `results.json`；
- 全部通过时退出码为 0，否则非 0。

只依赖 Python 标准库，无需额外安装。

## 4. 交互式提问与人工确认

```bash
# 会先打印 prepare 计划，再询问 y/N
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/e3_agent/agent.py \
  --ask "2878 在美中 Daneey 仓 2026 年 5 月的销量是多少？"
```

```bash
# 跳过确认（仅因为所有工具只读）
uv run python .../agent.py --ask "2880 的断货窗口是什么时候？" --yes
```

`--eval` 会自动确认，因为 `execute` 只执行只读工具；真实运行时建议保留人工确认闸门。

## 5. 数据与匿名化

- 数据来自本地补货决策信息包（as-of 2026-10-16），已内嵌为 `data/wedge_decision_package.json`。
- 已移除客户名、人员名与邮箱；原客户渠道记为 `channel_a`，非该客户渠道合并为 `other`。
- 保留通途 SKU 后缀、EN 物料号、买家 SKU 与仓库编码，便于与业务报表回查。
- 已知缺口：2026-10 订单表缺失；波兰仓未覆盖；渠道只拆到客户 / 其他两档。
- 口径要点：
  - 库存取通途分仓可用，**不采用 EN Bin**；
  - 在途取通途采购单未到货量，**不采用 SO 未交量**；
  - 月需求率取剔除断货月与到货冲量月后的干净月均（1 位小数，HALF_UP）；
  - 建议补货量 = `ceil(max(0, 月需求率 × 覆盖月数 − 可用 − 在途))`。

## 6. 评估集结构

`questions.json` 的每道题包含：

```json
{
  "id": "Q01",
  "category": "answerable | ambiguous | write | out_of_scope | premise_conflict",
  "question": "……",
  "expected": {
    "status": "answered | needs_clarification | refused_write | out_of_scope | premise_conflict",
    "tool": "monthly_sales",
    "slots": {"sku": "2878", "warehouse": "美中-FZH-DANEEY"},
    "missing_slots": [],
    "values": {"qty": 23},
    "safe_alternative_contains": [],
    "correction_contains": []
  }
}
```

评分同时检查：状态、工具、关键槽位、缺失槽位、数值（容差 0.05）、证据完整性、写操作未执行、安全替代关键词。

## 7. 如何读结果

- `results.md`：设计说明、15 题实际结果、Falsify 判定、失败分析与限制。
- `results.json`：逐题完整结果，含 `router.matched_rules`（命中了哪条规则）、`evidence`（工具 / 参数 / 来源 / 计算步骤 / 回读）与 `checks`（逐项通过情况）。
- `meta.input_sha256` / `meta.questions_sha256`：输入哈希；哈希变化说明数据或题库被改过。

## 8. 扩展方式

新增指标时按顺序做三件事：

1. 在 `SEMANTIC_LAYER` 写定义、权威来源、禁用口径；
2. 在 `TOOLS` 注册只读工具与必填 / 可选参数；
3. 在 `RULES` 增加路由关键词，并在 `questions.json` 增加正例与负例。

新增写能力时不要直接加工具：先设计权限、人工确认、审计与回滚；本原型的策略是“没有写工具”。

## 9. 已知限制

- 关键词路由器对同义表达不稳健，需要真实用户问法盲测。
- 数据是本地快照，不证明线上 API 可用性。
- 渠道与仓库覆盖有限；缺槽位时只澄清，不猜。
- 评估集规模 15 题，且与规则同源，存在选择偏差。
