---
okf: v0.1
type: Review
title: SC01 输入基线清册（冻结）
date: 2026-10-23
owner: claude-worker-2
status: 完成；29/29 机械核对通过；只登记 hash/元数据，不做分析、不出量
artifacts:
  - out/business_phase/sc01_input_manifest.json   (只放 hash/元数据，无行级数据)
  - experiments/sc01/sc01_input_manifest.py       (机械复核脚本)
---

# SC01 输入基线清册

> **本文件只登记"这批结论建立在哪些输入上"**：路径、sha256、行数、生成/观测时间、覆盖窗口、
> 口径是否已证。**不做任何分析、不产生任何数量**。
> 复核命令跑完应当得到 `29/29 passed · ALL CHECKS PASS`。

## 1. 冻结输入清单

| 输入 | 路径 | sha256（前 16） | 行数 | 生成 / 观测时间 | 覆盖窗口 | 引入 commit |
|---|---|---|---:|---|---|---|
| 业务母集 | `out/business_phase/destinations.json` | `720b478809128156…` | **1,328** SKU | 2026-10-22 16:29:39（文件内 `generated_at` 同值） | `gs_orders.despatch_date` **2026-04-01 .. 2026-09-30**（近 6 个完整月） | `44def7f5` |
| C 包成品表 | `out/business_phase/final_bundle.csv` | `3bb860a67f2be72e…` | **2,309** SKU×仓 | 2026-10-23 09:39:12（mtime） | 继承母集 | `b02fd083` |
| 供需决 | `out/business_phase/decision_v2.csv` | `4b9efecc892342bf…` | **2,309** | 2026-10-22 17:17:54 | 同母集 | `ab808652` |
| T5 预测 | `out/business_phase/replenishment_v2.csv` | `6b30e751ecda8630…` | **2,309** | 2026-10-22 17:53:52 | 同母集 | `7e0f6fc4` |
| 本地数据仓 | `D:/Work/fzh-order-store/order_store.duckdb` | `0919dd8c852df51e…` | 232 MB | 2026-10-23 09:38:39（mtime） | 见下表 | 未入库（本地） |

**DuckDB 内的关键表（行数已在复核脚本里逐表断言）**

| 表 | 行数 | 覆盖窗口 |
|---|---:|---|
| `gs_orders` | 407,898 | `month` 202301..202609 |
| `monthly_series` | 43,955 | 2023-01 .. 2026-09 |
| `stock_history` | **15,820** | **仅 3 个快照日：2026-10-20 / 21 / 22** |
| `stock_latest` | 4,973 | 当前快照（无日期列） |
| `tongtool_stock` | 5,065 | 当前快照 |
| `sku_item` / `sku_map` | 3,482 / 3,482 | 当前主数据（无时间维度） |
| `bom` / `bom_exploded` | 5,575 / 22,510 | 当前主数据（无时间维度） |
| `item_attr` | 15,230 | 当前主数据 |

> ⚠️ **数据漂移（必须随清单一起传达）**：`destinations.json` 等 C 包产物在生成时记录的是
> DB `sha256 = 25579c5d…`（`db_unchanged: true`），而**当前 DB 是 `0919dd8c…`** ——
> DB 在 2026-10-23 09:38 被更新过。CSV 类产物绑定的是**生成当时**的 DB 状态；
> 想逐位复现，必须找到当时的 DB，否则接受数据漂移。

## 2. 母集对账

| 等式 | 左 | 右 | 结果 |
|---|---|---|---|
| SKU → SKU×仓 | **1,328** 个 SKU | **2,309** 个 SKU×仓 | 每个 SKU 占 1–6 个仓：779(1仓)+240(2)+209(3)+80(4)+17(5)+3(6) = **1,328** ✅ |
| 仓数 | 2,309 行 | **11** 个仓 | 含 `（out_of_scope）` 哨兵 91 行 |
| 母集 vs 全历史 | 母集 **1,328** | 全历史有销量 **2,553** | 差 **1,225** ✅（SC10 口径） |
| 闭合 | 1,328 + 1,225 | 2,553 | **0** |

**1,225 个为什么不在母集**：母集只取 **despatch 2026-04..09** 六个完整月；
这 1,225 个 SKU 有更早的历史销量、近 6 月无发货（老品/停售），**是设计如此、不是遗漏**。
（详见 `2026-10-23-sc10-catalog-diff.md` §2。）

## 3. 单位与仓口径清册

### 3.1 已证

| 口径 | 证据 |
|---|---|
| 母集时间窗 | `destinations.scope.mother_set_definition`（despatch 2026-04-01..09-30） |
| 仓名清单 | `stock_history` 10 个仓；`final_bundle` 11 个（多一个 `（out_of_scope）` 哨兵） |
| 库存观测时点 | `stock_history` **恰 3 天**：2026-10-20/21/22 |
| SKU ↔ EN 物料 | `sku_item` 3,482 对（与 `sku_map` 完全一致，0 冲突） |
| BOM 组件关系 | `bom_exploded` 22,510 行 |

### 3.2 未证（引用时必须写明）

| 口径 | 现状 |
|---|---|
| **库存单位（UOM）** | **`stock_history.uom_basis` 15,820 行全部 `unknown`** —— 一个都没证。`stock_latest`/`tongtool_stock` 无单位列，`item_attr` 无 uom 字段 |
| 仓与实物对应 | 未做盘点核对，只按仓名口径 |
| 快照之间的出入库 | 无台账，10-20/21/22 之间发生了什么**不可知** |
| EN `Item.stock_uom` | **未查**（需生产只读） |
| 承运商 ETA / 到货 | 只有 ETA 字段，**未证**；且已发现 4 张 DN 的 ETA 已过期 |
| PO / WO | 本地无证据（`forward_net` 里 `wo_status` 全 `not_observed`） |

> **推论**：任何跨 UOM 的合计（"总件数"）都**不成立**——个与套混存，
> 见 `2026-10-23-map-evidence.md` §4。

## 4. 不在本批范围（避免误以为已覆盖）

| 不在范围 | 说明 |
|---|---|
| **EN 生产实时数据（DN / Shipment）** | 是 2026-10-23 **当场只读 REST 拉取**的，**没有冻结快照**；只把结果留在 `out/business_phase/dn_*.csv` 与 `sc04/`。重跑会拿到**那一刻**的实时值，不是本清单的冻结值 |
| **承运商 API**（FedEx / UPS / GLS） | 本批**从未调用**；所有物流状态都来自 EN 的 `custom_zmt_*` 字段 |
| EN `Item.stock_uom` / `Stock Ledger Entry` / 盘点单 | 未查 |
| 通途商品档案单位字段 | 本地表无该列，未查 |
| 钉钉头程 / 发货信息表 / PO·WO 明细 | 未接入 |
| 2026-08-01 之前的 803 张 DN | 未覆盖（Jack 的映射只维护 8/1 起） |
| 外部 FBA 仓库存 | 不在任何本地口径，**不可追踪** |

## 5. 复现命令与预期输出

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/sc01/sc01_input_manifest.py
```

**预期**：29 条检查全部 `OK`，末行 `ALL CHECKS PASS`。检查覆盖：
4 个文件的 sha256 + 行数、DB sha256、10 张表行数、快照日恰为 3 天、
`uom_basis` 全部 `unknown`（15,820/15,820）、`monthly_series` 2,553 个 SKU、
母集 1,328 / SKU×仓 2,309 / 11 仓 / rows-per-SKU 分布 / `1,328+1,225=2,553`。

> 若某项 FAIL，**先看是不是 DB 漂移**（当前 `0919dd8c…`）或上游产物被重跑过，
> 不要就地改本清单——改清单等于换基线，需要重新冻结并升版。

## 6. 边界

1. 只登记，不做分析、不出数量。
2. 本清单**不覆盖** EN 生产实时数据与承运商 API（见 §4）。
3. 所有"已证"仅指**文件层面存在且 hash 一致**；业务口径是否成立另见各专项报告。
4. 未 commit、未 push。
