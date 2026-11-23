---
okf: v0.1
type: Report
title: 供应净额独立复审返修与 r5（2026-10-27）
description: F1–F4 修复、刷新预测接入、r5 逐桶重跑与仍存缺口
tags: [acceptance, netting, forecast, review-fix, r5]
date: 2026-10-27
status: verified
---

# 独立复审返修 + r5

来源：`C:/Users/zhang/.agent-ops/fzh-data/reviews/supply-review-6614403.md`（verdict=reject）。
本次在 `keyapi/supply-integrate-oct27` tip 上继续，保留 r4c，不 push、不写生产。

## 1. 修复（P1 + F4）

| ID | 问题 | 修法 | 回归 |
|---|---|---|---|
| **F1** | 期初库存绕过排除 gate | `engine.opening_basis()`：只计「已证、非重放、自由」的库存行；FBA / exact_replay / 身份冲突等明确排除并逐条留证；零库存仍是有效观测；无法判定时 `opening=null` | `F1OpeningGate` 5 例 |
| **F2** | 阶段→tranche 丢失证明 | `StageBalance/Tranche` 增加 `identity_confidence / warehouse_confidence / source_complete` 并端到端传递；转换 SupplyRow 不再硬编码 proven/confirmed；未证行由 gate 排除 | `F2TrancheProvenance` 4 例 |
| **F3** | 同批跨阶段重复、重复输入靠 event_id 绕过 | `apply_batch_quota()`：按已证 `batch_key` 在 在产/完工待发/在途/到仓 间保留最靠后阶段，其余留证；数量冲突标 `batch_quantity_conflict`；`_dedupe_exact()` 拦截完全相同行；`build_availability_schedule` 遇重复 `balance_id` 抛 `DuplicateBalanceError`；`split_balance` 用 `split_of` 标记合法拆分；**阶段校验在写产物之前执行**，失败返回 2 且不落盘 | `F3BatchQuotaAndDuplicates` 8 例 |
| **F4** | 到仓待上架被一律排除 | 区分「原始收货证据（receipt_event，不计）」与「已证、未含期初、未来 confirmed 可售日的 tranche（计）」 | `F4ArrivedTranche` 4 例 |

附带（P2、成本低且与 r5 交付直接相关）：

- **F6** 需求入口严格化：布尔用类型/字符串精确判断，坏数量报错，不再 `fillna(0)`。
  预测入口同样用 `_is_true()`，`'false'`/NaN 不会被当 True。
- **F7** manifest 记录**全部输入文件哈希**（库存、PO、通途 PO、sku_map、uom_cache、
  warehouse_aliases、需求、阻断）与代码版本；快照与 `as_of` 差异显式披露。
- **F8** 视界外没有需求键的已证供应逐条落 `supply_facts`（`outside_demand_scope`），
  不再只留一个计数。
- **F9** 空事实表保留固定 schema（里程碑 0 行也有 8 列）。

未做（明确记录）：F5 的 estimated 日期情景。`receipt_buckets` 只认 `confirmed`，
把 estimated 改写成 confirmed 会绕过 gate；两情景对 estimated 的规则需业务裁定，
本轮不擅自改。三态（confirmed/estimated/unknown）已在事实表保留原值。

## 2. 刷新预测接入

- 新增 `supply_netting/forecast.py`：读 `forecast/CURRENT`，校验
  `CURRENT == manifest.run_id`、`schema_version == en-demand-forecast-v1`；
  CLI `--forecast-run-id` 不匹配直接报错，不静默换版本。
- 预测资格用预测自己的 `netting_eligible` / `netting_block_reason`，
  与 `demand_netting.netting_allowed` **是两套字段**，不互相替代。
- 窗口 p50 在窗口天数上均摊，桶只取重叠天数（`allocation_rule` 入 manifest）。
- 不满足资格 / p50 缺失 / 身份一对多 / 单位未知 / 与实际订单重叠 → 逐条留证，不写 0。
- 需求表按来源分列：`forecast_demand` 与 `historical_demand` 在逐桶明细里分开。

## 3. r5 结果

| 项 | 值 |
|---|---|
| 代码 commit | `f730b16270b49279357b6e06555e04fe1c151751`（`git_dirty=false`） |
| 库存快照 | 2026-10-26 05:17:34（备份 `_inputs/en_stock-2026-10-26-backup.parquet`） |
| as_of | 2026-10-26T05:17:34+08:00（与快照差 −0.6 秒） |
| 桶 | protect 7 天 + w1..w4，共 35 天 |
| 需求 | 238,801 行 = 历史 235,891 + 预测 2,910 |
| 预测 | **forecast-20261027-r2**，manifest sha256 `7a41755d…9efc`，窗口 10-29..12-28，582 个键，量 2,378.27 |
| 净额键 / 行 | 545 / 5,450（保守 + 预期 × 5 桶） |
| 期初库存合计 | 17,689（`opening_rows_excluded=0`：真实数据无 FBA/重放期初） |
| 保护期需求 / 缺口 | 311.45 / 34.87（71 个键） |
| 视界末累计未满足 | 449.97 |
| 条件供应量 | 11,305（在途/PO 无 ETA，所有桶已证到货 = 0） |
| 供应事实行 | 9,827（含 2,609 条 `outside_demand_scope`） |
| 恒等式 | 全部通过；`ledger_conserved=true`；阶段校验 0 错误 |

预测去向（60 天窗口 4,518 行）：通过资格 582 键 / 2,910 桶行；未过资格 3,210
（子仓身份未证、仓库未知、SKU 未映射）、p50 缺失 704、零预测 22。

决策包 `pack-2026-10-26-r5/`：545 行、71 个缺口键；建议分布：
不需补 444 / 补（缺口已证）60 / 补（视界内未满足）20 / 观察（条件供给）11 /
观察（低于服务档）8 / 数据不足 2；动作层 补单 46 / 核实到仓 ETA 14 / 催发运 5 /
催生产 4 / 核实 ETA 2。

## 4. 仍然存在的缺口（partial=true）

1. **历史需求不进入未来桶**：全部历史订单早于 as_of（`demand_rows_before_as_of=74,426`），
   净额需求只来自预测；as_of 与预测起点之间 2.78 天没有需求数据，不填 0。
2. **已证到货为 0**：通途在途与通途 PO 都没有逐行 ETA，全部条件态；`receipts` 全桶为 0。
3. **未履约 SO 余额仍未接入**：`--backlog` 为空，工厂 SO 管线只在 pack 的动作层出现，
   不计入海外可用。
4. **预测覆盖不全**：只覆盖通过预测资格的 582 个 SKU×仓；其余键仍只有历史需求。
   预测是销售 SKU 口径，未做成品/皮壳拆分证明。
5. **阶段余额只有通途在途**：未排产/在产/完工待发/到仓待上架无本地源；
   真实数据没有已证批次，`same_batch_excluded_rows=0`（机制由合成用例覆盖）。
6. **F5 未做**：estimated 日期不进任何情景，需业务规则。
7. `pack` 的服务水平缓冲未含提前期；动作层的时效仍标 `timely_coverage_unproven`。

**这不是采购单，也不是供应功能验收**：r5 是 2026-10-26 快照 + 2026-10-29 预测起点的
条件情景，所有数量都带来源与条件标记。
