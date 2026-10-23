---
okf: v0.1
type: Review
title: PB 涤麻三角断货三源交叉（只读）
date: 2026-10-23
owner: claude-worker
status: 完成；三源对齐 + 区间上/下界；不判物理断货
artifacts:
  - experiments/pb_stockout/pb_cross_source.py
  - out/pb_stockout/pb_30sku_list.csv
  - out/pb_stockout/stockout_intervals.csv
  - out/pb_stockout/cross_source_report.md
---

# PB 涤麻三角断货三源交叉

> **只读**：本地 DuckDB `read_only` + PB orders 目录只读；无生产访问、无写库。
> WX 快照只给「系统非正 / 1–3 低 / 正 / 未知」，**不证明物理断货**；快照之间状态未知，不做每日回填。

## 1. 输入与去重

| 源 | 处理 | 结果 |
|---|---|---|
| checked0stock | 递归扫描（大小写不敏感），按**内容 sha256** 去重 | 89 个文件 → **80 个独立文件**（`NotUsed` 副本与重复下载合并）；独立事件（SKU×事件日）**920** |
| WX 快照 | 仅 `warehouse_scope='source_warehouse'` | **11 个日期**（2026-06-09..2026-07-31） |
| 人工宽表 | `consolidated_warehouse_scope_unverified` | **137,241 行全部排除、未并入** |
| 实际发运 | `gs_orders` channel='PotteryBarn' 按月 | 67 个 PB SKU |

## 2. 名单（冻结 27 个，≈30）

规则：**PB Wedge Pillow 家族**（checked0stock 描述含 `Wedge Pillow`）∩ **GS PotteryBarn 有销量** ∩
**至少一个断货信号**（checked0stock 事件或 WX 非正/低快照），按 PB 累计销量降序。
合格 **27** 个，未凑到 30：不补无信号 SKU、不凭印象扩名单。逐项依据见 `pb_30sku_list.csv`。

- 前 5：`CEN1607NLinen-Ivory-194`(1807)、`CEN1607NLinen-Ivory-153`(1783)、
  `CENKZ1323-LTGrey-153`(1071)、`CENKZ1323-LTGrey-194`(950)、`CENC/Linen-Grey-60CM`(779)。
- 2 个 SKU 累计销量 < 100，标 `low_volume=yes`，**不进入断货结论**。

## 3. 三源交叉（SKU × 日期）

| 源 | 结果（名单内） |
|---|---|
| WX（源仓合计） | 非正快照 **0**、低库存快照 **0**；每个 SKU 有 11–44 个「单仓为 0」的格 |
| checked0stock | 窗口内事件 **152** 次；全历史事件 850 次 |
| 发运 | 窗口内有 0 发货月且此前有销量的 SKU **3** 个 |

**关键观测（三源不一致）**：WX 源仓合计在窗口内始终为正，而同一批 SKU 的 PB 订单被反复阻断；
且这批 SKU 的 WX 可用量主要落在 `FZH-DANEEY-皮壳仓库`（组件仓），不是成品仓。
因此 **SKU 合计为正 ≠ PB 可发**，WX 也不能证实断货。

## 4. 断货区间与上下界

- 信号日 = checked0stock 事件日 ∪ WX 非正/低快照日（窗口内），间隔 ≤14 天归为一个区间。
- **保守下界** = 首末信号日之间的实际观测天数（不外推）。
- **宽松上界** = 保守天数 + 最大快照间隔（15 天）外推，截到窗口最后一天（快照之间状态未知）。
- 共 **33 个区间**，最长 38 天（`CEN1607NLinen-Ivory-153`、`CENC/Linen-Grey-60CM`、`CEN961NLinen-SageGreen-138` 等
  2026-06-15 → 07-23，宽松 46 天）；全部为「仅订单受阻」信号，没有 WX 非正信号参与。
- 不插值、不填每日假库存。

## 5. 可信度分级

**高 0 / 中 3 / 低 24**。同向定义：WX 非正或低快照 + checked0stock 事件 + 发货断档。
高可信为 0 不是缺数据，而是**三源本身不一致**：WX 源仓合计始终为正，三源不可能同向。
中可信的 3 个（订单事件 + 发货断档）见 CSV 的 `credibility=中`。

## 6. 红线逐条检查

1. **通途正几件不自动判恢复**：1–3 件一律记 `low_1_3`，不当作恢复；名单内低快照 0、非正快照 0，
   因此没有任何「由正转恢复」判定被使用。
2. **低销量不直接判断货**：累计销量 < 100 的 SKU 标 `low_volume=yes` 并在结论中排除（本批 2 个）。
3. **人工宽表 scope 未证不并入**：137,241 行全部排除，仅在 CSV 记每 SKU 被排除行数。
4. **不填每日假库存**：输出只有快照点与区间。

## 7. 已知限制

- WX 源仓快照只覆盖 2026-06-09..07-31（11 天）；此后的宽表日期未证、未并入。
- checked0stock 事件跨 2023–2026，与快照窗口只部分重叠；跨窗口事件只作「有无断货史」，不参与区间。
- 发货断档按月判断，月内节奏不可见。
- 本报告不评价 WX/LH 谁更好。

## 8. 可复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/pb_stockout/pb_cross_source.py
uv run python scripts/check_secrets.py
```

- 连续两次运行一致：`pb_30sku_list.csv` md5 `f871085a13b94574cb304989e0188e9d`，
  `stockout_intervals.csv` md5 `7af5765d9f54b10a627fcac2159c136e`。
