---
okf: v0.1
type: Reference
title: 全 family / 全 SKU 供应链 ETL — 方向修正
description: 从逐客户码试点转为按物料组/物料码批量的增量 ETL；事实表、幂等键、水位线与验收
date: 2026-10-21
tags: [supply-chain, etl, full-family, architecture, duckdb, erpnext]
---

# 全 family / 全 SKU 供应链 ETL — 方向修正

> 结论：**逐客户码 1,486 次查询只适合契约试点，不能作为供应链系统的主链路。**
> 主链路应改为 **按物料组/物料码批量 + 增量水位线 + 幂等事实表**；库存用通途 API 全仓快照，
> 生产/出库用 EN 单据批量抽取，3PL 用后台实盘。

## 1. 已验证：批量查询可行

只读探针（EN 生产，2026-10-21）：

```text
Sales Order Item.item_group in ("三角靠枕","三角靠枕无扣")
→ 333 行 / 56 张 SO（未加日期过滤）
```

说明不需要按 1,486 个客户码逐个查；按 **物料组** 一次可拉出整族 SO，再按日期/仓/状态过滤。
另外可按 `production_item in (item_code chunks)` 拉 WO，按 WO/SO chunks 拉 JC/SE/DN。

## 2. 目标架构（轻量、可增量）

```text
通途 API 全仓库存 ─┐
浏览器库存结存/销售报表 ├─→ 原始层 raw（JSONL/xlsx 原样归档）
EN SO/DN/WO/JC/SE ───┘        ↓
                         标准化层 staging（DuckDB/Parquet）
                              ↓
                         事实/维度层 fact/dim（幂等 upsert）
                              ↓
                         语义层 metrics（覆盖/缺货/建议）
```

### 2.1 事实表与幂等键（与 §2.5–2.8 一致）

| 事实 | 来源 | 幂等键 |
|---|---|---|
| `fact_sales_order_line` | SO + SO Item | `Sales Order Item.name` |
| `fact_delivery_note_line` | DN + DN Item | `Delivery Note Item.name` |
| `fact_work_order` | Work Order | `Work Order.name` |
| `fact_job_card` | Job Card | `Job Card.name` |
| `fact_stock_entry_line` | Manufacture SE + Detail | `Stock Entry Detail.name` |
| `fact_inventory_snapshot` | 通途 API/浏览器 | `(source, run_id/snapshot_id, warehouse_id, sku, 必要库存维度)` + `as_of`；`snapshot_date` 只作分区 |
| `sku_presence` | 库存快照 | `(source, run_id, warehouse_id, sku)`；`presence=observed/missing`、`qty_status=positive/observed_zero/bad/unknown` |
| `fact_in_transit` | 通途 `intransit` / PO / 头程 | `(source, doc_id, line_id, 运输腿/lot)`；`eta_bucket` 可变，不进主键 |
| `fact_3pl_inventory` | Wayfair 后台手工 | `(as_of, 3pl_warehouse, sku)`，`authority=wayfair_backend_manual` |

### 2.2 增量策略（与 §2.6 一致）

- **变更发现**：EN 用 `modified` 发现旧单迟改；`transaction_date`/`posting_date` 只作业务日期，**不能当增量游标**。
- **稳定排序/回读**：`(modified, name)` 排序，设置重叠回读窗口和 `run_started_at` 上界；相同 `modified` 跨页用 name 去重。
- **父单/子行**：命中父单后**整单重拉子表**；删除子行写 tombstone；保留取消、`amended_from`、移出 family、状态修改。
- **提交后推进**：raw→staging→fact 校验并提交后才推进对应水位；partial/失败不推进；周期全量对账发现硬删除。
- **SO 批量**：`item_group in (family groups)` + 日期窗口；父单拉取后按行筛选，保留非 family 同行去向。
- **WO/JC/SE**：按 `production_item in (item_code chunks, ≤40)`；JC/SE 按 WO chunks；SE 查询不完整时产量 unknown，成功量只作 `known_subtotal`。
- **DN**：按 `against_sales_order in (SO chunks)` 或 `posting_date` + item group。
- **库存**：通途 API 全仓分页（13 秒/页，526 退避），每仓保存 `complete/page/hash`；新 run 严格 hash，旧 manifest 用 `--allow-missing-hash` 时标 `integrity_mode=legacy_unverified`。
- **幂等**：所有事实表按主键 upsert；快照不覆盖历史，冲突不静默 first-wins；没有单据行的通途汇总 intransit 独立 snapshot，不编造 `doc_id`。

### 2.3 零库存 vs 缺失（必须分开）

- API 返回该 SKU/仓且数量为 0 → `observed_zero`（真的 0）。
- API 没返回该 SKU/仓 → `missing/unknown`，**不能补 0**；可能是未铺货、停售、漏拉或接口截断。
- 库存结存可能省略零库存 SKU（实测 API 比 CENTRADE 多 386 个、其中 343 个零；
  DANEEY 多 26 个、其中 25 个零），所以零库存以 API 为准，状态/别名用库存结存补。
- 建议加 `sku_presence(snapshot_date, warehouse_id, sku, presence, qty_status, source)`：
  `presence=observed|missing`，`qty_status=positive|observed_zero|bad|unknown`。

### 2.4 验收

- 每个输入行有 disposition：`used / pending / unmatched / conflict / unknown`。
  逐行记录写入审计 JSONL（`so/line_id/item_code/base/prefix_role/disposition/
  disposition_reason/evidence_ref/qty/uom`），不能只留聚合计数。
- 详情必须完整：`get_single` 返回缺 `items`、`items` 为空/非列表、查询异常都记为
  `detail_none/items_missing/items_not_list/items_empty/detail_error`，`status=partial`；
  不得写 0 行后仍 `complete`。
- 守恒：`detail_ok + 详情失败数 == selected_sos`，`sum(line_dispositions) == 审计行数`；
  不成立即 `audit_mismatch` + exit 1。
- `status` 只表示查询/详情完整性；逐行证据完成度用 `adjudication`
  （`complete / pending_remaining` + 原因码计数）单独表达，两者都不等于 G1 验收。
- 数量守恒：SO→DN→SE、库存→覆盖、在途→实收；不把跨层累加当余额。
- 每批有 `run_id`、输入文件 hash、页数、行数、`complete`、异常清单、审计文件 hash。
- 全 family 跑通后再扩到全 SKU；全 SKU 以 `item_group`/`item` 分片，不按客户码。

### 2.5 E01 family 全集与批量完整性

- 版本化 `family_manifest`：KS leaf（KS0001/KS0248）、规范物料、客户码、`PK#`/`ND#` 等角色映射、
  历史停用/改组、纳入/排除/pending 原因、manifest 版本号。
- 父单批量拉取后**按订单行筛选**，保留非 family 同行去向；不能因为父单被选中就纳入全部行。
- 交叉覆盖：两个 `item_group` 筛选 + manifest item_code 并集 + 已知 9 个试点客户码，
  不能因为不在当前两个组就漏掉已知试点。
  **实测 group-only 只找到 15 SO/135 行，10 个试点客户码只命中 1 个**，所以必须做并集。
  修正 S01/S02 后同窗（delivery_date）结果：**52 SO / 1,510 family 行 / 392 pending /
  122 out_of_scope，10/10 试点命中**；group 2 页、item_code 75 页、pilot 10 页。
  旧 96/380 是 pilot 无日期过滤 + PK# 被当非 family 的口径，不作为同窗结果。
- manifest 记录：查询条件、333/56、原始页数、筛选后行数、未匹配/排除原因。
- **变体码不凭前缀接纳**：`PK#`/`ND#` 只说明编码形态（PK=皮壳、ND=内胆），
  必须由版本化证据表证明 **KS 成品 BOM 消耗该组件**；方向不能反转，
  不能要求 PK/ND 的 BOM 必有 KS（其 BOM 可能是布料）。证据表缺失/未命中/冲突
  一律 pending 并记原因码（`variant_manifest_absent`、`variant_not_in_manifest`、
  `variant_base_not_family`、`variant_base_conflict`、`variant_bom_conflict` 等）。
  本地 BOM 成本表（3,700 行）没有 `PK#`/`ND#` 单元格，包装列是 `SXBZCP#`/
  `SXBZBCP#` 另一套编码，不能当证据。
- **结构证据，不是标签**：证据表必须有 `schema_version/site/as_of/producer/
  rule_version/payload_sha256`（重复 JSON key 直接报错）；每条记录带 canonical KS/
  角色/方向/`valid_from,valid_to`/Item 与 BOM 的 `name,sha256,modified`/
  `candidate_boms[]`（全部已提交且 `eligible_at_evidence=true`，按 canonical/角色/
  方向/UOM/比例一致；default 与今天的 `is_active` 都不消解冲突）。比例按
  **组件 stock 累计 / 输出 stock 数量** 归一，`10 输出配 10 组件` 才为 1；
  同 UOM 下 `qty` 必须等于 `stock_qty`，factor 若给出只能为 1；UOM 换算必须已知且
  正有限。历史窗口只能是 `historical_verified + historical_basis`，
  `current_structure_only` 不得回填为历史真值；停用 Item 可保留历史 family 关系，
  但 `current_planning_eligible=false`，且与 `disabled` 矛盾时标 conflict。
  `schema_version/rule_version/source/site` 必须命中白名单并与当前 run 的 EN 端点绑定；
  源 Item/BOM hash 只是受信 producer 边界，consumer 不重取源文档。
  `evidence_ref` 由消费者从已验证 BOM 派生，不读生产者字符串。
- **family 与 demand_role 分离**：行上同时记 `family_membership`
  （ks_finished/cover/inner）、`demand_role_candidate`（`terminal_finished_candidate/
  independent_cover_candidate/assembly_component_candidate/unknown`）、`canonical_ks`、
  `cover_equivalent_factor`、`demand_event_candidate_id`、`counting_status`。
  内胆独立销售不产生皮壳需求；SO 行不等于终端销售，本 PoC 不做事件级去重、
  不输出终端需求合计，`cover_equivalent_factor` 不参与任何聚合或补货量。
  `line.name` 缺失/重复记 invalid + partial 并保留 `line_index`；
  `qty` 缺数/坏值/NaN/负数记 None + `qty_status`，不转 0（修 `iss.num` 的缺口）。
- 证据表随 `family_manifest` 一起版本化，manifest 记录其
  `schema_version/site/as_of/producer/rule_version/payload_sha256/sha256/
  entries/by_evidence/by_scope`；证据表里实际出现的 code 并入候选查询并记录
  `variant_query_codes_added`。
- 契约由离线单测 `test_en_family_poc.py` 覆盖（44 条：重复 key、假标签、任意 ref、
  方向/比例/同 UOM 数量矛盾/UOM 换算/有效期/多 BOM 冲突/历史范围/行键/
  demand_role 候选/qty fail-closed），不联网、不调用 `main()`。
- 父单明细字段按本仓库接口核对（既有代码遍历 `items`），不把 `order_items` 当唯一真实字段。

### 2.6 E02 增量与失败重跑

- 每个 DocType 明确变更发现字段：`modified` 发现旧单迟改；`transaction_date`/`posting_date`
  只作业务日期，不能互换当增量游标。
- 稳定排序 `(modified, name)`，设置重叠回读窗口与 `run_started_at` 上界。
- 命中父单后整单重拉子表；删除的子行用失效/tombstone；保留取消、`amended_from`、移出 family、状态修改。
- 仅 upsert 新行不能清理消失的旧行；周期全量对账发现硬删除。
- raw/staging/fact 校验并提交后才推进水位；partial/失败不推进；跨来源不装作一个事务快照。
- 若源不保证子行修改带动父 `modified`，需验证并以子表变更/周期全量补偿。

### 2.7 E03 不可变事实键

- `fact_inventory_snapshot` 键：`(source, run_id/snapshot_id, warehouse_id, sku, 必要库存维度)` + `as_of`；
  `snapshot_date` 只作分区/筛选，同日多次采集不覆盖；另建“选定合格快照”视图。
- `fact_in_transit` 去掉可变 `eta_bucket`；用 `source/doc/line/运输腿或lot` 稳定身份，
  ETA/revision/observed_at 另版本化；无单据行的通途汇总 intransit 独立存 snapshot，
  不编造 `doc_id`，不与 DN/物流事实重复累计。
- `float_sales_order_line` 更正为 `fact_sales_order_line`。

### 2.8 E04 守恒与增量回归

- `SO→DN→SE` 不是三层数量直接相等；按相同 cutoff、规范单位、链接粒度检查：
  有效订单/取消/正向发出/原未交/超发，退货单列；JC/SE/DN 分开；unknown 不补 0；
  组件与成品经已确认配方/UOM 换算后才对账。
- 最小回归包：旧日期 SO 后来修改、取消/改单、删子行、移组、相同 `modified` 跨页、
  失败重跑不推进水位、ETA 修订不增供应、同日双快照、缺 SKU 与 explicit 0、SE 详情失败。

## 3. 与业界做法的对齐

- **ODS → DWD/事实层 → 语义层**，不直接在 ERP 事务表上算指标。
- **增量 CDC/水位线 + 周期全量对账**，避免每天全表扫。
- **幂等 upsert + 异常队列**，重复/冲突/未知不静默丢弃。
- **事实/派生/估算/断言分层**（与 08 契约一致），LLM/报表只引用语义层。
- 这些都是供应链数据平台的基本操作；不需要重写研究，只需要把现有试点适配器升级为批量 ETL。

## 4. 下一步

1. 新增 `en_bulk_extract.py`：先跑 family 的 SO→DN→WO→JC→SE，按物料组/物料码 chunks。
2. 用 2026-04..09 全 family 重跑，输出 manifest/hash/逐行 disposition。
3. 库存继续用每日 API 全仓 JSONL；浏览器库存结存/销售报表作为对照与销量补充。
4. 全 family 验收通过后，把 `item_group` 参数扩到全品类/全 SKU。
5. WayfairCG 后台实盘/调拨归属独立 pending；不阻塞批量 ETL。
