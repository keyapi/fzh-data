---
okf: v0.1
type: Reference
title: 规范需求适配层（canonical sku×warehouse×uom）
description: 全历史 GS + EN 增量的 SKU/仓库/UOM 规范化、净额资格与 b08acc05 接口
tags: [canonical, demand, uom, warehouse, reference]
date: 2026-10-27
status: verified
---

# 规范需求适配层

> 目标：让 2022-12 起的 GS 历史与 2026-10 的 EN 增量用同一套
> `canonical_sku × canonical_warehouse × uom` 被补货/供应分桶消费。
> 不训练模型、不做补货内核、不写生产。

## 1. 运行

```bash
uv run python -m self_fulfilled_demand.canonical \
  --store D:/Work/fzh-order-store/en-demand-v1 \
  --gs-path D:/Work/fzh-order-store/gs_orders.parquet \
  --start 2022-12-01 --end 2026-10-31 \
  --out D:/Work/fzh-order-store/en-demand-v1/canonical
```

首次会为本次出现的唯一 EN 物料补建 `Item.stock_uom` 缓存（只读、分批、最多 6,000 个）；
之后命中缓存不再查。`--no-fetch-uom` 可完全离线。

## 2. 映射规则（不猜、不任取）

### SKU
- 来源：`D:/Work/fzh-order-store/sku_map.tsv`（`Item Customer Detail.ref_code → Item`）。
- `tongtool_sku → item_code` 唯一 → `mapping_status=mapped`，`canonical_sku=item_code`。
- 一对多 → `ambiguous:<sku>`，**不任取**，净额阻断，候选全部写入 `ambiguity_list`。
- 未映射 → `unmapped:<sku>`，净额阻断，保留原始 SKU 与数量。
- 不按编码相似合并 Cover/成品：`PK#…` 与 `KS…` 是不同 canonical SKU。

### 仓库
配置：[`self_fulfilled_demand/warehouse_aliases.json`](../../warehouse_aliases.json)。

| 类型 | 处理 | 例 |
|---|---|---|
| 旧名→新名（有文档证据） | 合并 | `CENTRADE→美东-CENTRADE`、`FZH-DANEEY→美中-FZH-DANEEY`、`FZHPoland-covers→波兰-FZHPoland-covers` |
| 分公司/子仓（声明） | 保留独立规范名 | `FZH-DANEEY-皮壳仓库`、`FZH-DANEEY-成品仓/半成品仓/退货产品仓` |
| 子仓疑似新名 | **不合并**，写 `parent_candidate` + `not_merged_no_evidence` | `FZH-DANEEY-皮壳仓库` → `美中-FZH-DANEEY-皮壳仓库` |
| 成本来源不同 | **不合并** | `FZHPoland-finished` ≠ 波兰 covers |
| 第三方/代发 | 保留独立，标 `third_party` | `WayfairCG-Cranbury仓`、`枫筝海外仓-*-代发仓` |
| 未映射仓 | 保留原名，标 `unknown`，净额阻断 | `星链海外仓`、`休斯顿1号仓` 等 |

### UOM
- 证据：EN `Item.stock_uom`（本次为 1,627 个唯一物料补建缓存，全部命中：1,622 个「个」+ 5 个「套」）。
- 件类单位 → `uom_status=known_piece`，`uom` 写入规范单位。
- 缺失 → `uom=null` + `uom_missing`，净额阻断。
- 非件类（米/kg 等）→ `uom=null` + `uom_not_piece`，净额阻断（订单行数量是件数，不能直接当米数）。

### 发货形态
- EN 行沿用 `demand_kind`（成品/皮壳/半成品）。
- GS 行：若 `(订单, 通途SKU)` 在 EN 里有**唯一**非 unknown 形态 → 沿用，`demand_kind_basis=en_line_match`；
  多条冲突 → 保持 unknown + `en_line_conflict`；无匹配 → unknown（`gs_monthly_sheet_has_no_shipping_method`）。
- 本次全历史 18,317 行由 EN 匹配推断形态；其余 389,579 行仍 unknown（不猜）。

## 3. 净额资格（与 b08acc05 的约定）

主键：**`demand_date × canonical_sku × canonical_warehouse × uom`**。

`netting_allowed=false` 的行**不得直接净额相减**，原因写在 `netting_block_reason`
（可多因，分号分隔）与 `netting_block_primary`：

| 原因 | 含义 |
|---|---|
| `sku_mapping_ambiguous` | 通途SKU 对应多个 EN 物料 |
| `sku_mapping_missing` | 通途SKU 未登记 |
| `uom_missing` | 物料无 stock_uom |
| `uom_not_piece` | stock_uom 非件类 |
| `warehouse_identity_unknown` | 仓库未映射 |
| `scope_unknown` | 履约归属未知 |

- FBA：**不进入本表**（本次排除 2,453 行）。
- 3PL/代发：**保留**（5,419 行），`netting_allowed=true`，但 `in_default_series=false`，
  由供应分桶按 scope 自行取舍。
- unknown scope：保留但阻断（7,940 行）。
- `demand_kind=unknown` 不单独阻断净额：接口主键不含形态，SKU 物料已区分 Cover/成品；
  需要更严口径的消费方可加 `demand_kind_status='known'` 过滤。

## 4. 本次真实结果（2022-12-01 → 2026-10-31）

| 指标 | 值 |
|---|---|
| 输入需求行 / 数量 | 413,561 / 440,179 |
| 规范行（聚合后） / 数量 | 250,105 / 440,179（无丢失） |
| 可净额行 / 数量 | 402,494 / 428,576 |
| 阻断行 / 数量 | 11,067 / 11,603 |
| FBA 排除 | 2,453 行 |
| 3PL 保留 | 5,419 行 |
| unknown scope | 7,940 行（全部阻断） |
| 唯一 SKU / 物料 / 规范仓 | 2,566 / 1,627 / 24 |
| 旧名合并命中 | CENTRADE 160,459；FZHPoland-covers 102,543；FZH-DANEEY 25,834 |
| 歧义清单 | 327 条：未映射 SKU 302、未映射仓 11、一对多 SKU 7、子仓未合并 5、UOM 缺失 1、形态 unknown 1 |

阻断原因分布：

| 原因 | 行数 |
|---|---|
| 仓库未知 + 归属未知 | 6,626 |
| SKU 未映射 + UOM 缺失 | 2,879 |
| SKU 未映射 + UOM 缺失 + 仓库未知 + 归属未知 | 1,314 |
| SKU 一对多 + UOM 缺失 | 237 |
| SKU 未映射 + UOM 缺失 + 仓库未知 | 10 |
| 仓库未知 | 1 |

## 5. 产物

`D:/Work/fzh-order-store/en-demand-v1/canonical/`

| 文件 | 内容 |
|---|---|
| `demand_canonical.parquet` | 规范需求聚合（含 `netting_allowed` / 原因 / 形态 / scope） |
| `demand_line_disposition.parquet` | **每一行输入**的 canonical 键或阻断原因（去向可查） |
| `sku_coverage.parquet` | 每个通途SKU 的行/量、映射、UOM、仓库数、ready/blocked |
| `ambiguity_list.parquet` | 一对多/未映射/仓库/单位/形态歧义 |
| `identity_manifest.json` | 源文件哈希、计数、接口约定、口径说明 |
| `item_uom_cache.parquet` | EN `Item.stock_uom` 本地缓存 |
| `cases.md` | 真实可解释案例（旧名合并、子仓不合并、形态推断、未映射、代发、可净额） |

## 6. 已知缺口

1. `sku_map.tsv` 是既有缓存（4,236 行），可能滞后；未映射 302 个 SKU 需主数据补登。
2. 11 个仓库未映射（休斯顿/星链/北美之路/大件云仓等）→ 阻断，不猜归属。
3. 子仓新旧名（如 `FZH-DANEEY-皮壳仓库` vs `美中-FZH-DANEEY-皮壳仓库`）未证合并，保持独立。
4. GS 历史 389,579 行没有发货形态证据，保持 unknown（不按编码相似推断）。
5. UOM 只证明「EN 物料单位」；订单行数量与 UOM 的换算关系未逐 SKU 验证，非件类已阻断。
6. 9 月末交集仍是抽样口径，不代表整月完整覆盖。
