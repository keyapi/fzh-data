---
okf: v0.1
type: Report
title: T5 全范围迭代版摘要（AutoETS 默认 + MA3 fallback）
date: 2026-10-22
owner: claude-worker
status: 迭代版；A=0，B 为条件数量，C 为范围外
artifacts:
  - out/business_phase/replenishment_v2.csv
  - out/business_phase/diff_v1_v2.csv
  - out/business_phase/replenishment_v2.xlsx（本地生成，仓库忽略 *.xlsx）
---

# T5 迭代版摘要

## 1. 覆盖

| 项 | 值 |
|---|---:|
| 输出行数 | 2,309 |
| 覆盖 SKU 数 | 1,328（1,237 合格 + 29 UOM + 62 未映射 = 1,328） |
| SKU×仓合格行 | 2,218 |
| 状态 A / B / B_pending_inventory / C | 0 / 2058 / 160 / 91 |

| 状态 | 6 个月净出库 | 销量占比 |
|---|---:|---:|
| A | 0 | 0.0% |
| B | 48,001 | 98.9% |
| C | 543 | 1.1% |

## 2. 方法

- 默认 **AutoETS**（statsforecast 2.1.1），SKU 级拟合后按该仓近 3 月销量占比分配到仓（显式假设）。
- 逐行 fallback：AutoETS 不可用的 SKU 用 **MA3**，原因写在该行 `fallback理由`。
- 本版行内方法分布：AutoETS 2,106 行、MA3 112 行

### 验证 / 测试反转（迁移风险，不改选）

- 验证集（共同子集）AutoETS WAPE **0.5232**，第二名 combo_dynamic_ew **0.545**。
- 测试集 AutoETS **0.7108**，combo_dynamic_ew **0.61**、seasonal_naive **0.6227**。
- 按裁定 A 仍以 AutoETS 为默认；**测试反转只作为迁移风险**记录，不据此改选。

## 3. 与首版（v1）差异

- 逐 SKU 对比：**726 个 SKU 数量变化**，其余不变或无数量；明细见 `diff_v1_v2.csv`。
- 变化主因：① 模型由 SKU 级 MA3 切到 AutoETS（失败则 MA3）；② 粒度改为 SKU×仓并按销量占比分配；③ PO/在途仍按去重批进入情景，但基数随需求变。

## 4. 使用条件（必须随表一起说明）

- A 类为 0：需求上下界（G8）未给、在产 WO 不在快照，**没有任何行可当已审批数量**。
- B 类数量是**条件区间**，依赖行内 `assumptions`；MOQ/包装/成本未提供，**采购约束待定**。
- 未知为 null（库存未知 160 行数量留空），**没有按 0 计算**。
- 共享池默认不跨仓调拨；跨仓需显式开启并单列假设。

## 5. 剩余缺口

- PO ETA 全表缺失、在产 WO 不在快照、逐笔重叠键缺失、需求上下界（G8）缺失、MOQ/成本缺失。
- 退货/取消不可观测；促销尖峰、运营变化、断货删失均检出未校正。

