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
| 子仓疑似新名 | **不合并**，写 `parent_candidate` + `not_merged_no_evidence`；身份证据补齐前**保留原行但阻断净额**（`subwarehouse_identity_unproven`） | `FZH-DANEEY-皮壳仓库` → `美中-FZH-DANEEY-皮壳仓库` |
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

两个数据集分工：

| 文件 | 用途 | 唯一性 |
|---|---|---|
| `demand_netting.parquet` | **净额专用**：已过滤 `netting_allowed=true`，按四列键汇总 | 四列**唯一** |
| `demand_canonical.parquet` | 明细聚合（13 列，含形态/来源/scope/资格） | 四列**不唯一**，禁止 upsert/按行连接供应 |
| `demand_blocked.parquet` | 阻断账，按四列键 + 原因组合 | 与净额量分离 |

消费顺序：先取 `demand_netting`（已过滤资格），默认自发货再筛 `in_default_series=true`；
3PL 保留但 `in_default_series=false`；阻断量只在 `demand_blocked`。

`netting_allowed=false` 的行**不得直接净额相减**，原因写在 `netting_block_reason`
（可多因，分号分隔）与 `netting_block_primary`：

| 原因 | 含义 |
|---|---|
| `sku_mapping_ambiguous` | 通途SKU 对应多个 EN 物料 |
| `sku_mapping_missing` | 通途SKU 未登记 |
| `uom_missing` | 物料无 stock_uom |
| `uom_not_piece` | stock_uom 非件类 |
| `subwarehouse_identity_unproven` | 未证合并子仓（保留原行，禁止净额） |
| `quantity_invalid` | 数量缺失或 ≤0 |
| `warehouse_identity_unknown` | 仓库未映射 |
| `scope_unknown` | 履约归属未知 |

- FBA：**不进入本表**（本次排除 2,453 行）。
- 3PL/代发：**保留**（5,419 行），`netting_allowed=true`，但 `in_default_series=false`，
  由供应分桶按 scope 自行取舍。
- unknown scope：保留但阻断（7,940 行）。
- 整次构建固定同一 EN 快照；`identity_manifest.sources.en_snapshot` 记录 commit_id、
  orders/lines 文件哈希与行数，可直接反证两次读取一致。
- `demand_kind=unknown` 不单独阻断净额：接口主键不含形态，SKU 物料已区分 Cover/成品；
  需要更严口径的消费方可加 `demand_kind_status='known'` 过滤。

## 4. 本次真实结果（2022-12-01 → 2026-10-31）

审核返修后的数字（修复前见括号）：

| 指标 | 修复后 | 修复前 |
|---|---:|---:|
| 输入需求行 / 数量 | 413,561 / 440,179 | 同左 |
| 明细聚合行 / 数量 | 250,111 / 440,179 | 250,105 / 440,179 |
| 可净额行 / 数量 | **312,208 / 330,508** | 402,494 / 428,576 |
| 阻断行 / 数量 | **101,353 / 109,671** | 11,067 / 11,603 |
| 四列唯一净额行 | **191,701**（四列重复 0） | 未单独输出（四列重复 1,322） |
| 阻断账行 | **57,088** | — |
| 子仓行 / 数量 | 91,413 / 99,167（全部阻断） | 91,413 / 99,167（其中 90,286 / 98,068 曾获准） |
| FBA 排除 | 2,453 行 / 2,558 件 | 同左 |
| 3PL 保留 | 5,419 行 / 5,702 件（`in_default_series=false`） | 同左 |
| unknown scope | 7,940 行 / 8,233 件（全部阻断） | 同左 |
| 唯一 SKU / 物料 / 规范仓 | 2,566 / 1,627 / 24 | 同左 |

**90,286 行去向**：五类未证合并子仓原先获准的 90,286 行 / 98,068 件，现在全部保留原行，
`netting_allowed=false`，`netting_block_primary=subwarehouse_identity_unproven`：

| 子仓 | 保留行 | 数量 | 修复前获准行 |
|---|---:|---:|---:|
| FZH-DANEEY-半成品仓 | 10,179 | 10,249 | 9,163 |
| FZH-DANEEY-成品仓 | 11,757 | 16,430 | 11,732 |
| FZH-DANEEY-皮壳仓库 | 66,771 | 69,639 | 66,718 |
| FZH-DANEEY-退货产品仓 | 2,644 | 2,760 | 2,617 |
| FZHPoland-finished | 62 | 89 | 56 |
| 合计 | 91,413 | 99,167 | **90,286** |

阻断原因（新优先级：SKU 一对多 > SKU 缺失 > UOM 缺失 > UOM 非件类 > 仓库未知 >
子仓未证 > scope 未知 > 数量无效）：

| 原因组合（primary 计数） | 行数 |
|---|---:|
| 子仓未证（含叠加其他原因） | 90,286 |
| 仓库未知（含 scope unknown） | 6,627 |
| SKU 缺失 | 4,203 |
| SKU 一对多 | 237 |
| 合计 | 101,353 |

审核点名的重复键
`2025-07-01 / KS0390-CTTM-120x120x70-CREAMYBEIGE / FZH-DANEEY-半成品仓 / 个`：
明细仍为 2 行（semi_finished 1 + unknown 1，合计 2 件），阻断账 1 行 2 件，净额表 0 行；
不会把 2 件当 1 件，也不会对同一份供应重复扣减。

## 5. 产物

`D:/Work/fzh-order-store/en-demand-v1/canonical/`

| 文件 | 内容 |
|---|---|
| `demand_netting.parquet` | 四列唯一、已过滤资格，供 b08acc05 净额 |
| `demand_blocked.parquet` | 阻断账（四列键 + 原因组合 + 数量） |
| `demand_canonical.parquet` | 明细聚合（含形态/来源/scope/资格；四列不唯一） |
| `demand_line_disposition.parquet` | **每一行输入**的 canonical 键或阻断原因（去向可查） |
| `sku_coverage.parquet` | 每个通途SKU 的行/量、映射、UOM、仓库数、ready/blocked |
| `ambiguity_list.parquet` | 一对多/未映射/仓库/单位/形态歧义 |
| `identity_manifest.json` | 源文件哈希、**EN 快照 commit_id 与 orders/lines 哈希**、计数、接口约定 |
| `item_uom_cache.parquet` | EN `Item.stock_uom` 本地缓存 |
| `cases.md` | 真实可解释案例（旧名合并、子仓不合并、形态推断、未映射、代发、可净额） |

## 6. 已知缺口

1. 五类子仓身份证据补齐前，相关 91,413 行保持阻断（原行未删、未并入主仓）。
2. `sku_map.tsv` 是既有缓存（4,236 行），可能滞后；未映射 302 个 SKU 需主数据补登。
3. 11 个仓库未映射（休斯顿/星链/北美之路/大件云仓等）→ 阻断，不猜归属。
4. 子仓新旧名（如 `FZH-DANEEY-皮壳仓库` vs `美中-FZH-DANEEY-皮壳仓库`）未证合并，保持独立。
5. GS 历史 389,579 行没有发货形态证据，保持 unknown（不按编码相似推断）。
6. UOM 只证明「EN 物料单位」；订单行数量与 UOM 的换算关系未逐 SKU 验证，非件类已阻断。
7. 9 月末交集仍是抽样口径，不代表整月完整覆盖。
