---
okf: v0.1
type: Review
title: 全母集补货建议批处理（1,328 SKU）— 首版交付记录
date: 2026-10-22
owner: claude-worker
status: 已交付首版（CSV + XLSX + summary）；A=0，B 为条件数量，C 为范围外
inputs:
  - out/business_phase/destinations.json（44def7f5，只读）
  - out/business_phase/ranking.json（d50310a6，只读）
  - out/business_phase/plan.json（d04e943c，只读）
  - out/business_phase/ten_sample_freeze.json（909635da，只读）
  - D:/Work/fzh-order-store/order_store.duckdb（read_only）
artifacts:
  - experiments/business_phase/build_replenishment_batch.py
  - out/business_phase/replenishment_all.csv
  - out/business_phase/summary.md
  - （out/business_phase/replenishment_all.xlsx 仅在本地生成，仓库 .gitignore 忽略 *.xlsx，未提交）
---

# 全母集补货建议批处理（首版）

> 范围 = **1,328**：1,237 映射合格参与计算；**29 单位待证 + 62 未映射**以状态 C
> 留在表内（`out_of_scope_uom` / `out_of_scope_unmapped`），**未静默丢弃**。
> 只本地离线、DB 只读；未改冻结名单 / plan / ranking / destinations / V1 产物；
> 提交的是聚合成建议表，不含原始订单明细。

## 1. 能否今晚出首版

**能。** CSV、XLSX（本机已有 `openpyxl`）与 `summary.md` 已生成；1,328 行齐全、
计数相加、8 例自检全部一致。**提交范围**：脚本 + CSV + summary + 本记录；
XLSX 仅本地生成（仓库 `.gitignore` 忽略 `*.xlsx`），需要时可由同一脚本一键重建。

需要业务知道的前提：**A 类为 0 行**——不是漏算，而是按 R4 标准，
需求上下界（G8）未提供、在产 WO 不在快照，没有任何一行能到“可审批数量”。
因此首版的价值是 **B 类条件数量 + 逐行假设 + 阻塞清单**，不是可直接下单的订单量。

## 2. 计数与状态

| 项 | 值 |
|---|---:|
| 输出行数 / SKU 数 | 1,328 / 1,328 |
| 映射合格（参与计算） | 1,237 |
| 单位待证（C：out_of_scope_uom） | 29 |
| 未映射（C：out_of_scope_unmapped） | 62 |
| 1,237 + 29 + 62 | **1,328** ✅ |

| 状态 | 行数 | 6 个月净销量 | 销量占比 |
|---|---:|---:|---:|
| A 证据充分可审批 | **0** | 0 | 0.0% |
| B 条件数量（显式假设） | **1,237** | 48,001 | 98.9% |
| C 范围外（同单位不可算 / 映射不合格） | **91** | 543 | 1.1% |

## 3. 自检：8 个冻结代表 SKU 与 N2 已发布结余逐项对齐

| SKU | 期望结余 | 本批重算 | 来源 | 一致 |
|---|---:|---:|---|---|
| `TT0031038K0062927` | 345 | 345 | N2 B1 | ✅ |
| `C/Linen-Natural-100-688-wow` | 55 | 55 | N2 B1 | ✅ |
| `TT0312701K0064561` | 181 | 181 | N2 B2 | ✅ |
| `C/Cord-DKBlue-100-713-wow` | 6 | 6 | N2 B2 | ✅ |
| `C/Velvet-White-100-664-wow` | 0 | 0 | N2 B3 | ✅ |
| `TT0031010K0062880` | 0 | 0 | N2 B3 | ✅ |
| `C/Linen-Natural-194-688-wow` | 366 | 366 | plan.supply_lower（S7） | ✅ |
| `CENCord995-DKGrey-97` | 1 | 1 | plan.supply_lower（S8） | ✅ |

脚本在**全量运行前**断言这 8 项；任一不符即 `SystemExit`，不会带着错的基线出表。

## 4. 列（15 固定 + 1 附加）

`SKU / 仓 / 历史窗口 / 预测方法 / 未来需求(P50/P90) / 库存日期与数量 / PO已知量 /
在产已知量 / 出库已知量 / 去重状态 / 提前期情景(L60/L90/L120) / 建议补货数量或条件区间 /
需要时间 / 缺失字段与证据 / 状态`，另加 **`assumptions`**（B 类必填，任务要求写在行内）。

- **历史窗口**：2026-04..2026-09（6 个完整月，`despatch_date`）。
- **预测方法**：`mean3 + 滚动 90 天同形窗口残差的 conformal-style 上抬`；
  1,070 行用本 SKU 自有残差（own），167 行因自身残差不足 3 个而用全母集池化（pooled），
  行内写明 `own n=`。
- **库存日期与数量**：`2026-10-22: available=N`；已证为 0 时显式写「已证为 0」；
  无库存行写 `null（无库存行，不等于 0）`（本批 29 行）。
- **PO 已知量**：有未结 PO 写 `数量（行数，ETA 全缺）`；无记录写
  `null（无未结 PO 记录；按 0 假设）`（本批 1,162 行）——**null 与 0 分得开**。
- **在产已知量**：全部为空（WO 不在快照），并在 `缺失字段与证据` 写明。
- **出库已知量**：6 个月净出库数量（扣测试单；退货/取消不可观测，见 §7）。
- **去重状态**：`suspected_duplicate`（在途=未结 PO）/ `duplicate_candidate_lines`
  （同数量 PO 行）/ `unproven` / `not_applicable`。
- **提前期情景**：L60 / L90 / L120 的 P50 值（情景，不是承诺到货时间）。
- **建议补货数量或条件区间**：B 类给 `下限–上限` 区间；C 类为空。
- **需要时间**：仅当有已承诺待发订单时写快照日，其余为空。
- **缺失字段与证据**：逐项写缺什么、指向哪张表。

## 5. 规则落实

| 规则 | 落实方式 |
|---|---|
| SO 与预测不重复冲减 | 需求只用预测，SO 不冲减、不加成；行内注「SO 重叠未证」 |
| 内部 SO 不作额外终端需求 | 未把 waiting 量加进需求；仅用于“已承诺需求”事实与需要时间 |
| PO/在途只作情景变量 | 计算区间时按去重批/两批进入情景，且 `assumptions` 明写 |
| 未知不填 0 | 无记录一律 `null + 说明`；0 只用于“已证为 0”或“假设按 0 计”并标注 |
| “无在途”只能写假设 | 行内写「无在途记录，按 0 计（假设，不得表述为真实无在途）」 |
| MOQ/成本缺失 | 每行 `缺失字段与证据` 标「采购约束待定」，不伪装成订单量 |

## 6. 主要阻塞（按行计，全 1,328 行）

1. PO ETA 全表缺失（未结 248 行、0 行有 `will_arrive_date`）
2. 在产 WO 不在快照（供给上界无法证实）
3. 需求上下界 G8 未提供（P50/P90 只是估计）
4. 逐笔去重键缺失（在途可能与 PO 重复；同数量 PO 行可能重复录入）
5. MOQ / 成本未提供（采购约束待定）

## 7. 口径边界（必须在业务侧确认）

1. **退货/取消不可观测**：`gs_orders` 无状态字段、窗口内 0 条负数量行；
   净出库=已发货。若退货另走渠道，需求会被高估。
2. **P90 是滚动经验/conformal-style 估计**，不保证 90% 覆盖（V1 已披露）。
3. **在产/ETA 缺失**使上限不完整：短缺方向也不可定论，所以 A=0。
4. **零库存已证为 0** 与 **无库存行（未取到）** 在表中分开标注。
5. 提前期情景是 L60/L90/L120 的需求口径，不含实际生产/运输时间。

## 8. 复现与校验

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/build_replenishment_batch.py
uv run python scripts/check_secrets.py
```

- 两次运行 CSV **逐字节一致**（已实测）。
- DB 只读，前后 sha256 一致；输入四份产物的 sha256 记录在脚本运行时校验。
- xlsx 仅在本机已有 `openpyxl` 时生成（本机有，已生成约 130 KB，**未提交**：仓库忽略 `*.xlsx`）；
  无依赖时只交 CSV。CSV 是**聚合建议表**（每 SKU 一行，无订单明细），按本任务授权提交。
- 脚本曾修正两个自身缺陷（均在本记录提交前）：
  ① 残差只用了 6 个月窗口 → 改为全历史；② 历史窗口误用未来窗口的绝对月份 → 改为每个起点单独生成同形日历窗口。

## 9. 明确不做

- 不下单、不改生产主数据、不猜配、不扩写入。
- 不把 B 类条件区间当订单量；不把 A=0 解释为“都不用补”。
