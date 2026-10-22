# T19 WO/DN 覆盖与关联缺口

> 只盘点**本地已有**材料：不新增数据库数据查询（仅 information_schema 结构）、不访问生产、不扩样、不外推。

## 1. 查过的来源

| 来源 | 类型 | 覆盖 | 结论 |
|---|---|---|---|
| order_store.duckdb | 表结构 | 53 表 | 无 Work Order / Delivery Note 实体或键（WO/DN 列 0 个） |
| g1_contract/out/dn_wo_jc_se* | WO/DN/JC/SE 关联 | 7 个 run，10 个 SKU | 主用 `dn_wo_jc_se_expand10_phase1_r2`（audit/evidence 通过，10 SKU） |
| g1b_en_*.json | 原始 EN 抓取 | 15 个文件 / 10 个 SKU | WO 行与 production_four_way 原始字段 |
| out/replenishment_v0/evidence.json | V0.1 供给证据 | 10 个 SKU | 开放 WO 剩余量与 ETA 状态 |
| out/business_phase/n2_b1–b3.json | 链条表 | 6 个 SKU | 显式写“WO 不在本快照”，无具体 WO 材料 |
| out/g1b_coverage_*.json | BOM/库存/订单 | 多 SKU | 无 WO/DN 字段（仅作交叉说明） |

## 2. 三态计数（相加 = 2,309）

| 状态 | 行数 | SKU | 含义 |
|---|---:|---:|---|
| `covered_validated` | **0** | 0 | 有材料且可用于供给 |
| `covered_unvalidated` | **32** | 10 | 有材料但未通过校验，**不得计供给** |
| `no_material_found` | **2277** | 1318 | 本地来源均未覆盖（逐行列出查过的来源） |

**为什么 `covered_validated` 为 0**：10 个有材料的 SKU 中 7 个关联通过自审、3 个存在 C2 mismatch/unverified；但无论关联是否通过，**开放 WO 的 ETA 全部缺失**（`planned_end_date_all_null`），无法放入 L60/L90/L120 窗口；另有 1 个 SKU 的 KS/PK# UOM 口径未证。故全部只能算 `covered_unvalidated`，不得计入供给。

## 3. 有材料的 10 个 SKU（全部 covered_unvalidated）

| SKU | 开放 WO | 剩余量（不计供给） | ETA 缺失 | 关联自审 | 失败原因 |
|---|---:|---:|---:|---|---|
| `C/Cord-DKBlue-100-713-wow` | 1 | 35 | 1 | 通过 | eta_missing |
| `C/Cord-Grey-100-710-wow` | 2 | 28 | 2 | 未通过 | association_not_validated、eta_missing |
| `C/Linen-Natural-100-688-wow` | 3 | 101 | 3 | 通过 | eta_missing |
| `C/Linen-Natural-153-688-wow` | 3 | 612 | 3 | 未通过 | association_not_validated、eta_missing |
| `C/Linen-Natural-194-688-wow` | 2 | 620 | 2 | 通过 | eta_missing |
| `C/Linen-White-100-662-WOW` | 1 | 20 | 1 | 通过 | eta_missing |
| `C/Velvet-Grey-100-705-wow` | 2 | 52 | 2 | 通过 | eta_missing |
| `CEN003-DPBLUE-100` | 1 | 260 | 1 | 未通过 | association_not_validated、eta_missing |
| `CENCord995-DKGrey-97` | 2 | 152 | 2 | 通过 | eta_missing |
| `TT0000671K0063721` | 7 | 310 | 7 | 通过 | eta_missing、uom_kind_mixed_or_unknown |

## 4. 关联键覆盖（有键 / 缺键）

| 关联 | 总数 | 有键 | 缺键 | 说明 |
|---|---:|---:|---:|---|
| WO↔SO | 214 | 173 | 41 | 缺键原因：{'wo_no_sales_order': 41} |
| DN↔WO | 507 | 0 | 507 | DN 行只带 SO 键，无 WO 键 |
| WO↔PO | 214 | 0 | 214 | 任何本地来源都没有 WO→PO 键 |

## 5. 结论

- 主表 2,309 行 / 1,328 SKU 中，WO/DN 材料只覆盖 **10 个 SKU（32 行）**；其余 **1,318 个 SKU（2,277 行）** 在本地 WO/DN 来源中确实没有材料。
- 10 个 SKU **全部是 `covered_unvalidated`**：关联/守恒可查，但开放 WO 缺 ETA、且 KS/PK# UOM 口径未证，不能计入供给。
- 关联缺口是结构性的：DN 行没有 WO 键（只能经 SO 间接关联），WO 也没有 PO 键；这两类缺口靠现有材料无法补齐，不猜测。
- 与主表 `在产状态=work_order_not_in_snapshot` 的关系：主表把在产一律按 0，本表说明其中 10 个 SKU 其实**有 WO 材料**（但不可用作供给），其余 SKU 才是真正的“无材料”。

## 6. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/build_wo_dn_coverage.py
uv run python scripts/check_secrets.py
```

只读 DB（仅 information_schema）；输入哈希见 JSON；三态与计数断言在脚本内。

