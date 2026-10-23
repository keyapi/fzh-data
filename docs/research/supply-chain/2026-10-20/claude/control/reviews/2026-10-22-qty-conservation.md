---
okf: v0.1
type: Review
title: SO 行显式关联的数量守恒核查（只读）
date: 2026-10-22
owner: claude-worker
status: 完成；只读；只用显式关联；不作超补/缺补结论
artifacts:
  - experiments/auto_order/check_qty_conservation.py
  - out/auto_order/qty_conservation.csv
  - out/auto_order/qty_conservation.md
---

# SO 行显式关联的数量守恒

> **只读**：71 GET / 200，14.2 s，单线程 200 ms；无写入、不下单、不改配置、不改既有产物。
> **边界**：只核对单据**显式关联**与**算术**；无法显式关联的行记「未观测」，**不按同物料推断**；
> 不复用库存历史，因此**不判断**真实超补或缺补，也不判断到货是否及时。

## 1. 范围与方法

- 范围：`transaction_date` ∈ 2026-01-01..2026-09-30 的**已提交、非取消** SO 行，按 `is_internal_customer` 分外部 / 内部；
  同期已取消 SO 行 **182** 行单独计数，不进守恒。
- 规模：SO 行 **2604**（外部 294 / 内部 2310），**657** 个物料。
- 只认显式字段：
  - SO 表头 `po_no` → 同名 Purchase Order（且行物料、单位一致）；
  - Work Order 表头 `sales_order` == 本 SO（且 `production_item` == 行物料）；
  - Delivery Note Item `so_detail` == 本 SO 行（`so_detail` 为空时回退 `against_sales_order` + 同物料，并做歧义检查）；
  - Delivery Plan Item `so_detail`（只作关联证据，不参与数量）。
- 同单位：需求与供给双方 UOM 字符串必须相同才相加，否则记 `uom_mismatch`，该笔不参与比值但保留计数。
- 共享/分摊：同一 `po_no` 关联多张 SO、同一 WO 面对同一 SO 多行同物料、DN 只有 SO+物料级关联且该 SO 同物料多行——
  一律记为共享/无法归属，**不重复计入**任何单行比值。
- 供给口径：PO 数量、WO **已提交**计划量（草稿单列、已取消不求和）；`produced_qty` 仅记录（既往核查已发现该字段会失真）。

## 2. 守恒恒等式（逐行，仅显式 DN 关联）

| 结果 | 外部 | 内部 | 说明 |
|---|---:|---:|---|
| matched | 184 | 1328 | `delivered_obs + remaining_obs = demand`，且与存储 `delivered_qty` 一致 |
| field_mismatch | 0 | 0 | 恒等式成立但与存储 `delivered_qty` 差额 > 容差 |
| no_dn_unverified | 110 | 982 | 无显式关联 DN，无法核验（不计入守恒） |
| dn_ambiguous | 0 | 0 | DN 只有 SO+物料级关联且该 SO 同物料多行 |
| uom_mismatch | 0 | 0 | DN 单位与 SO 行单位不一致 |

> 恒等式本身按定义恒成立；**真正被检验的是 `delivered_obs` 与存储的 `delivered_qty` 是否一致**。
> 有显式 DN 的 1512 行全部一致，没有观察到 `delivered_qty` 与显式出库明细相矛盾的样本。

## 3. 供给/需求比值（仅单来源、同单位、可归属）

| 范围 | n | min | p25 | 中位 | p75 | max | >1.2 | <0.9 | =1.0 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 外部 | 184 | 1.00 | 1.00 | 1.00 | 1.00 | 80.00 | 3 | 0 | 181 |
| 内部 | 866 | 0.33 | 1.00 | 1.00 | 1.00 | 5.00 | 2 | 1 | 862 |

按月 × 内外部的完整表见 `out/auto_order/qty_conservation.md` 第 2、4 节；上半年 vs 下半年（H2 仅 7–9 月）：

| 期间 | 内/外 | 行数 | 显式关联 | 未观测 | 比值中位数 | >1.2 | <0.9 |
|---|---|---:|---:|---:|---:|---:|---:|
| H1 | 外部 | 154 | 138 | 16 | 1.00 | 1 | 0 |
| H1 | 内部 | 1366 | 1056 | 310 | 1.00 | 2 | 1 |
| H2 | 外部 | 140 | 88 | 52 | 1.00 | 2 | 0 |
| H2 | 内部 | 944 | 773 | 171 | 1.00 | 0 | 0 |

## 4. 三条事实（带边界）

1. **显式关联只能靠 WO/DN**：外部 226/294（76.9%）、内部 1829/2310（79.2%）行有关联证据，其余 68 / 481 行「未观测」。
   `SO.po_no` 解析到 EN PO **0** 行（外部 197 / 内部 1381 行有 `po_no` 却无同名 PO——实测 `po_no` 是客户订单号，如
   `NJHY20260109` / `TXHY20260109加单`，不是 EN PO 单号）；Delivery Plan 关联 **0** 行
   （DP 机制只覆盖更早年份，2026 年没有指向本范围 SO 的行）；WO 按 `sales_order` + 同物料 215 / 1438 行；
   DN 按 `so_detail` 184 / 1328 行。
2. **守恒**：有显式 DN 的 1512 行，`delivered_obs = delivered_qty` **全部一致**（0 mismatch），
   因此没有证据表明已交付数量与出库明细矛盾；但外部 110 / 内部 982 行没有显式 DN，**无法核验**，
   不能据此说这些行已交付数量正确。DN 草稿 0 行、已取消 166 行单独计数。
3. **比值高度集中在 1.0**：可归属样本外部 184 / 内部 866 行，中位数都是 1.00，恰好 1.0 的占 181 / 862；
   >1.2 仅 5 行（外部 3、内部 2，样本如 demand 1 ↔ WO 80、demand 20 ↔ WO 100），<0.9 仅内部 1 行；
   共享未计入 外部 0 / 内部 502 行，UOM 不一致 0 行。**这说明 2026 年内部 SO 行大多一一对应一张同量 WO**，
   是单据结构事实；比值只反映单据数量关系，**不**证明库存真实超补或缺补。

## 5. 实现中发现并修正的问题

1. **`po_no` 不是 PO 单号**：原设想「按 `po_no` 找 PO」在本实例完全落空（0/1578）。
   同表 `Purchase Order Item.sales_order` / `sales_order_item` 字段存在且语义上更准，
   但按 SO 过滤时**连续返回 HTTP 500**（1 张 SO、2 张 SO 均失败），本轮不纳入，
   PO 侧一律记未观测；需要的化应另开小范围授权核查（或在库侧加索引后重试）。
2. **子表字段过滤不能写成点号**：`["Delivery Note Item.against_sales_order","in",...]` 直接 500；
   必须用 `["Delivery Note Item","against_sales_order","in",...]`。DP 同理。
3. **父子表 join 分页不稳定**：`order_by=name asc` 时同一条查询两次可返回不同行
   （实测同一 SO 的 DN 汇总一次 236、一次 117）。已统一 `name asc, idx asc` + 子表行 id 去重。
4. **草稿 WO 会与已提交 WO 重复计入**：同一 SO 行若同时有草稿与已提交 WO，相加会把比值推到 2.0。
   现只把已提交量计入比值，草稿单列为 `wo_draft_qty`（96 行有草稿量）。
5. **「有 `po_no`」不等于「已关联」**：未解析到具体单据的引用不计入观测，避免把客户单号当供给证据。

## 6. 产物与复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/auto_order/check_qty_conservation.py
uv run python scripts/check_secrets.py
```

- `out/auto_order/qty_conservation.csv`：逐行结果（哈希化 SO/行标识、物料、需求与各来源数量、比值与分类；
  **无客户名、无 PO/WO/DN 单号**）。
- `out/auto_order/qty_conservation.md`：预算、恒等式、按月 × 内外、比值分布、H1/H2、三条事实与方法。
- 连续两次运行 CSV 哈希一致：`sha256 前 16 位 = a06ac4f5ba5ad012`（71 GET / 14.2 s / 停止原因空）。
- 生产只读查询在 DN 子表过滤上偶发 500（重查询），脚本会按既有约定停止并写「部分结果」标记；
  本轮正式运行 3 次均正常完成。
