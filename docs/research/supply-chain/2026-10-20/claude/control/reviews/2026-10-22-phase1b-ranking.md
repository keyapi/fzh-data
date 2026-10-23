---
okf: v0.1
type: Review
title: Phase 1B 销量口径冻结与排序（1,237 合格映射 SKU）— 生成与对账记录
date: 2026-10-22
owner: claude-worker
status: 完成；只做口径与排序，不出数量、不判补/不补
inputs:
  - out/business_phase/destinations.json（Phase 1A，commit 44def7f5，只读）
  - D:/Work/fzh-order-store/order_store.duckdb（read_only）
artifacts:
  - experiments/business_phase/build_ranking.py
  - out/business_phase/ranking.json
  - out/business_phase/ranking.md
---

# Phase 1B：销量口径冻结与排序

> D14 要求「映射质量与销量排序不得混在同一脚本」：本脚本只读 Phase 1A 产物，
> **不改 destinations.json**，也不碰 V1 生成链。
> 本阶段**不出补货数量、不判补/不补、不做供给匹配**。
> 未访问生产、未扩样、未下单；DB 只读且运行前后 sha256 一致。

## 1. 口径冻结（机器可读：`ranking.json → metric`）

| 项 | 冻结值 | 可复算证据 |
|---|---|---|
| 指标 | `net_qty_6m` = 已发货数量 − 退货/取消，逐 SKU 6 个月累计 | `metric.name/definition` |
| 窗口 | **2026-04..2026-09**（6 个完整月），排除 2026-10（决定日 2026-10-22，不满月） | `metric.window` |
| 日期字段 | **`despatch_date`** | `metric.date_field` |
| 不改用 `sale_date` 的理由 | 同窗口 `sale_date` 只有 **1,326** 个母集 SKU（少 2 个），`despatch_date` 为 **1,328**；差额记录在 `metric.date_field_note`，**不切换、不静默** | — |
| 零填充 | 每个 SKU 都带 6 个月；无行月份 `rows=0, qty=0, zero_filled=true` | 1,237 × 6 = 7,422 个单元 |
| 退货/取消 | 窗口内 **0 条负数量行**、**1 条 0 数量行**；`gs_orders` 无状态字段，故净销量=已发货 —— 这是**声明**，不是默认 | `metric.returns_and_cancellations` |
| 测试单排除 | `platform_sku` 匹配 `(^|[-_])test([-_]|$)`：剔除 **5 行 / 6 件**，涉及 2 个 SKU（`TT0001538K0011180`、`TT0001538K0009462`）；两者仍有非测试销量，不会因此掉出表 | `metric.test_order_exclusion`（含 line_id 清单） |
| 内部调拨排除 | `warehouse/account/channel` 匹配 `调拨\|transfer\|内部\|internal`：**0 行**（查过；白名单式记录判据） | `metric.internal_transfer_exclusion` |
| 套件/单位 | 1,237 个合格物料 BOM 单位均为 **件/个/套**（Phase 1A 已把 29 个无 BOM 的排除在合格集外，故无单位混算）；窗口内 **0 条 TJ# 套件销售行**，无套件/组成件重复 | `metric.kit_and_unit_rules` |
| 可追溯 | 每行 6 个月单元 + `gs_orders` 谓词 + 首/末 `line_id` | 各行 `evidence_pointer` |

**独立复算**：SQL 直接汇总 1,237 个合格 SKU 在窗口内的 `SUM(qty)` = **48,007**；
减去测试行 6 件 = **48,001**，与本产物 `counts.total_net_qty_6m` 完全一致。

## 2. 分层依据与占比

用两个维度判断是否被单一维度主导（阈值 50%）：

| 维度 | 最大层 | 占比 | 是否主导 |
|---|---|---:|---|
| 品类 `item_group` | 三角靠枕 | **63.2%** | **是** |
| 仓 `dominant_warehouse` | CENTRADE | 31.3% | 否 |

→ **按品类分层**，层内排序；Top 50 名额按层占比用**最大余数法**分配。
226 个层里，141 个只有 1 个合格 SKU；前 6 层占比：三角靠枕 63.2%（32 席）、
三角靠枕无扣 6.7%（4 席）、软包墙围 2.9%（2 席）、平条靠枕 2.8%（2 席）、
身体支撑阅读枕 2.0%（1 席）、沙发支撑垫 1.6%（1 席）。
Top50 实际覆盖 **14 个层**，避免了「50 行全是三角靠枕」。

> 若不做分层，Top50 会被单一品类占满——这正是 D14「若被单一维度主导，先分层再排序」要防的情况。
> 名额分配表完整写在 `ranking.json → stratification.strata`（含每层 share/quota/selected）。

## 3. Top 50

- 选择方式：层内按净销量降序，按 quota 取前 N；并给出 `rank`（Top50 内）、`stratum_rank`
  （层内名次）、`global_rank`（全部 1,237 内名次）。
- 净销量区间：**801 → 62**；5 个「零库存但有销量」、3 个「部分履约」标记在名单内。
- 每行带 `months[6]`、`mapped_item_code`、`item_group`、`evidence_pointer`。
- 断言：50 行、无重复 SKU。

## 4. 紧急履约例外（独立清单，不按销量排序）

- **触发条件**：`stock_latest.waiting_shipment > 0`（存在待发订单 = 可观测的未履约需求）。
  `v_stockout_observed` 只作辅助证据 —— 零库存观测本身不等于未履约，故**不作触发**。
- 结果：**75 个 SKU / 150 待发件**；其中母集内 **37**、母集外 **38**。
  母集外同样有未履约需求（如 `STPPW-04-2` 待发 16 件），所以这份清单**不受业务母集限制**，
  逐条带 `stock_latest` 仓库级证据与断货观测行数。
- 该清单**不是补货建议**：不排序、不判补、不给量。

## 5. Top50 之外的候选（单列，绝不并入）

合格集外（`mapped_ineligible` / `unmapped`）按同一销量口径取前 20 单列，标 `not_in_eligible_ranking=true`：

- 最高是 `C/Linen-Natural-60-688-wow`（60 件，`mapped_ineligible / uom_unknown`）；
- 合格集 Top50 最低净销量是 62，因此本批外部候选**全部低于 Top50 门槛**——
  即使有更高的，也只会单列，不会挪进合格排序。

## 6. 对账

| 项 | 结果 |
|---|---|
| 入 / 出 | **1,237 / 1,237**，`dropped=[]` |
| 每月单元 | 1,237 × 6 = **7,422**，全部带 `zero_filled` |
| Top50 | 50，无重复 |
| 紧急例外 | 75（母集内 37 / 母集外 38） |
| 合格集总净销量 | **48,001**（独立复算一致） |
| 两次运行 | 除 `generated_at` 外**逐字节一致** |
| DB | 只读；前后 sha256 一致，变则拒绝发布 |
| 凭证 | `uv run python scripts/check_secrets.py` 零输出 |
| 临时文件 | 仓库根与 `out/business_phase/` 均无残留 |

## 7. 已知边界

1. **退货/取消不可观测**：`gs_orders` 无状态字段、窗口内无负数量行；若源表本身已扣减，
   净销量成立；若退货走另一个渠道未入表，则净销量偏高。这是**口径声明**，需要业务确认。
2. **测试单判据是命名式**（`platform_sku` 含 `-test`）；若测试单用真实 SKU 名发货则无法识别。
3. **零填充 ≠ 无需求**：无行只表示该月无已发货记录（可能断货、可能无单），不做推断。
4. **分层只按品类**：仓维度未主导（31.3%）；若后续窗口变化导致仓主导，脚本会自动改按仓分层
   （`SPLIT_DIMENSIONS` 顺序 + 阈值判断）。
5. **紧急例外的 75 条是快照事实**（`stock_latest` 是 2026-10-22 快照），不是时间序列；
   待发件从 1 到 16 件不等，未做优先级判断。
6. 本阶段**不判断**销量高低能否推出补货需求——那是后续阶段，且必须先满足 D13 的供给下界条件。

## 8. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/build_ranking.py
uv run python scripts/check_secrets.py
```

产物：`out/business_phase/ranking.json`（158 KB，逐行 + 口径 + 分层 + Top50 + 例外）
与 `out/business_phase/ranking.md`（精简摘要）。

DONE P1B
