---
okf: v0.1
type: Report
title: 资产复用审计（2026-10-28）
description: 对照 frePPLe 对话资产清单，检查 inventory_policy / sc08_conformal / leadtime_config / supply_netting 是否被重造
tags: [asset-reuse, inventory-policy, conformal, leadtime, audit]
date: 2026-10-28
status: audit-only
---

# 资产复用审计

来源：`D:/Work/赛狐/Cursor-claude/docs/research/supply-chain/2026-10-20/claude/control/reviews/2026-10-28-frepple-conversation-digest.md` §1
「已有资产：不要重造」。本审计**只读**：不改代码、不重写已验收产物、不 push。
逐条核对「已有资产是否被我们在用 / 被重写 / 未被接线」。

## 1. 对照表

| 已有资产 | 位置（证据） | 我们的实现 | 状态 | 判断 |
|---|---|---|---|---|
| `inventory_policy.py` | `experiments/business_phase/`（e3727683）：`simulate_flow` / `simulate_policy` / `metrics` / `bisect_order_up_to`，β 主 α 次、L+R order-up-to、lost_sales/backorder 显式 | `supply_netting/frontier.py:64 replay`、`:110 _target_from`；`frontier_v2.py:70 simulate` | **重复造轮** | 同一套 base-stock 回放有两份；未 import 既有评估器 |
| `sc08_conformal.py` | 同目录（9624b248）：对 actual/forecast **比率**做校准段经验/共形分位；CV / EMP / EMP3x | `frontier.py:110` 对**滚动需求**取 `np.quantile`；`pack.py:38 _z` + `:209`、`decision_pack.py:244` 的 `z95×σ×√14` | **部分重复** | 我们用正态 CV，不是 sc08 的误差比率分位；sc08 已证名义 95% 实际 0.54–0.70 |
| `sc13/leadtime_config.py` | `experiments/sc13/`（当前树）：版本化 JSON、四模式、三段交期、source/sample_size、缺字段即报错 | `so_backlog.py:41` 90 天 baseline（75–90 范围）、春节常量；`so_conditional_supply.py:32-34` 发运 7 / 生产 60 / 海运 35·40 | **未接线 + 重复** | 同一批假设硬编码在两处，无版本/source/sample_size；无任何 import |
| `supply_netting` | digest §1 列为本层资产 | `engine/facts/receipt_buckets` 逐桶净额与恒等式；r5/r6、决策包 r2/h180 消费它 | **本层即资产** | 无重造；保持唯一净额入口 |
| `forecast.py` | `self_fulfilled_demand/forecast.py`（6a7d56bd，未合入本分支） | `supply_netting/forecast.py` 适配器：CURRENT/manifest/schema/哈希校验、窗口分桶、`--allow-unpromoted-forecast` | **适配器复用** | 不重写模型；方法/版本从 manifest 读 |
| PR #300 研究/契约文档 | `docs/research/supply-chain/2026-10-20/**` | `supply_netting/docs/*` 引用（UOM-CANONICAL、frepple digest、supply-decision-contract） | **引用** | 未复制代码，无重复 |

## 2. 发现

| ID | 严重度 | 发现 | 证据 |
|---|---|---|---|
| **A1** | 中 | 自写 base-stock 回放，未复用 `inventory_policy.py` | `frontier.py:64`、`frontier_v2.py:70`；无 `import inventory_policy` |
| **A2** | 中 | `frontier.py:226` 声称「仓库内不存在 inventory_policy / 服务前沿评估器（全工作区检索无代码命中）」——实际资产在 git 历史 e3727683/9624b248，digest §1 已列明 | 检索只看了当前 checkout，未查 git 历史/其它分支 |
| **A3** | 中 | `higher_service_flat95` 用正态 CV（z95×σ×√14），正是 sc08 证明会低估的规则（名义 95% 实际 0.54–0.70） | `pack.py:38,209`、`decision_pack.py:244`；sc08 docstring |
| **A4** | 高 | 交期分段（90 / 7 / 60 / 35 / 40 / 春节 60）硬编码，未接 sc13 版本化合约 | `so_backlog.py:41`、`so_conditional_supply.py:32-34`；`leadtime_config.py` 零 import |
| **A5** | 低 | 同一缓冲公式在本仓库有两份实现（pack 与 decision_pack） | `pack.py:184` / `decision_pack.py:212` |
| **A6** | 低 | 预测资产未合入当前分支，只以产物 + 适配器方式消费 | `self_fulfilled_demand/forecast.py` 仅存在于 6a7d56bd |
| **A7** | — | PR #300 研究资产被引用而非复制 | 引用链完整 |

## 3. 建议（不改代码）

1. **交期（A4，最高优先）**：下一次同日 runbook 把 90/7/60/35/40 改读 `leadtime_config.py` 的 JSON 合约
   （`source=assumed`、`sample_size=0`、版本号落 manifest），缺文件即失败；在接入前保留硬编码但标注
   「assumed + 版本」。
2. **政策评估（A1/A2/A3）**：不再扩写 `frontier_v2`。若还要做服务—库存前沿，先包一层
   `inventory_policy.simulate_flow/metrics`，并在任何服务率表述中引用 sc08 的 0.54–0.70 与
   2.4–4.6× 库存；需要承诺时用比率经验分位，不用正态 CV。
3. **内部去重（A5）**：下次触碰 decision pack 时把 `_per_uom_buffers` 收敛到 `pack` 的实现，只留一处。
4. **预测（A6）**：合并分支后保留适配器，不复制模型逻辑。
5. **文档（A2）**：修正 `frontier.py:226` 的检索范围表述；检索资产必须覆盖 `git log --all`
   与其它分支，不能只看当前 checkout。

## 4. 明确不做

- 不改任何代码；不重写 `supply_netting`、r6/h180、decision pack 的已验收产物。
- 不把 frontier / policy-options 的数字接进主表。
- 不 push。

## 5. 产物

本地目录：`D:/Work/fzh-order-store/en-demand-v1/supply-netting/asset-reuse-audit-2026-10-28/`
- `asset_map.csv`：资产 × 我们的实现 × 状态 × 证据 × 建议
- `duplication_findings.csv`：A1–A7 发现与影响
- `report.md`：本报告副本
- `manifest.json`：输入路径与被检文件清单
