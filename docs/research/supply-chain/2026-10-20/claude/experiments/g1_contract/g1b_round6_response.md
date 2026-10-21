---
okf: v0.1
type: Review-Response
title: 对 Codex `run_86b2a4645f21` family SO PoC 复审的 S02/S04 修复
description: 变体码证据门、逐行 disposition、详情闸门与 so/line 守恒；回放验收单列
date: 2026-10-21
tags: [supply-chain, family-poc, codex, review, round6, s02, s04]
---

# 对 Codex `run_86b2a4645f21` 复审的 S02/S04 修复

> Codex 结论：S01/S03 verified；S02 partially（`:82-99` 按前缀接纳未证实 `PK#`/`ND#`）；
> S04 partially（`:240-243` 只计数不保存逐行 disposition；`:234` 缺 `items` 静默零行并
> `complete`）。本轮只修 S02/S04；**不重开 U01/旧 T**；真实数据回放与验收单列，
> 本轮未跑生产。

## S02 — 变体码证据门

### 问题定性

`normalize_item()` 去掉 `PK#`/`ND#` 后，`classify_line()` 仅凭
`base.startswith(("KS0001","KS0248"))` 就接纳为 family。前缀只说明编码形态，
**不证明 variant→KS 的 1:1 关系**；本地唯一映射源
`EN产品BOM成本列表20261016.xlsx` 也提供不了这个证据：整表 3,700 行扫描没有任何
`PK#`/`ND#` 单元格，包装列是 `SXBZCP#`/`SXBZBCP#`/`USNJBZCP#` 另一套编码。

### 修复（按 `2026-10-21-s02-evidence-design` 证据契约）

`proven` 不是标签。证据只证明**结构 family 关系**，不证明销量等价。
PK=皮壳、ND=内胆；方向固定为 **KS 成品 BOM 消耗 PK/ND 组件**
（`ks_parent_variant_component`），不要求 PK/ND 的 BOM 必有 KS（其 BOM 可能是布料）。

**文件层（不满足即 exit 2，不降级）**

- 顶层必须有 `schema_version`、`version`、`source`、`site`、`as_of`、
  `producer{name,version}`、`rule_version`、`items`、`payload_sha256`；
  `payload_sha256` 覆盖以上全部字段的 canonical JSON。
- `json.loads(..., object_pairs_hook=...)` 拒绝重复 key（含重复 code），不静默覆盖。
- 不可读/非法 JSON/字段缺失/哈希不匹配 → exit 2。

**条目层（不满足即 pending，逐条原因码）**

| 检查 | 字段 | 失败原因码 |
|---|---|---|
| 未提供证据表 / 未命中 | `--variant-manifest` / `items[code]` | `variant_manifest_absent`、`variant_not_in_manifest` |
| schema / 结构缺失 | `schema_version`、`canonical_ks`、`valid_from/to`、`item`、`bom` | `variant_schema_missing`、`variant_record_invalid`（detail 指字段） |
| canonical KS 在 family manifest | `canonical_ks == base ∈ ks_items` | `variant_base_not_family`、`variant_base_conflict` |
| 角色与语义 | `role == PK/ND`（PK=皮壳，ND=内胆） | `variant_role_mismatch` |
| 只接受结构证据 | `evidence == structural` | `variant_evidence_not_structural` |
| 历史窗口 | `evidence_scope=historical_verified` + `historical_basis` | `variant_current_structure_only`、`variant_historical_unknown`、`variant_historical_basis_missing` |
| 方向不能反转 | `direction == ks_parent_variant_component` | `variant_direction_not_cover_consumption` |
| 证据覆盖回放窗口 | `valid_from <= date_from`、`valid_to >= date_to` | `variant_out_of_validity` |
| 多 BOM 一致 | `resolution == consistent`；候选逐个已提交、`eligible_at_evidence=true`、同 canonical/角色/方向/UOM/比例 | `variant_bom_conflict`、`variant_bom_not_submitted` |
| 比例按 stock 数量归一 | `ratio ≈ component.stock_qty / output.stock_qty == 1` | `variant_ratio_not_1`、`variant_ratio_mismatch` |
| 数量有限且为正 | `qty/stock_qty` 非 0/负/NaN/Inf | `variant_quantity_invalid` |
| UOM 换算 | `uom != stock_uom` 时必须 `conversion_factor>0` 且 `qty*factor==stock_qty` | `variant_uom_conversion_missing/mismatch` |
| 组件/输出身份 | `component.item_code==code`、`output.item_code==base` | `variant_component/output_item_mismatch` |
| Item 有效 | `name==code`、`stock_uom==uom`、`sha256/modified`；`disabled` 不否决历史关系 | `variant_item_mismatch`、`variant_uom_mismatch` |
| 当前规划资格 | `current_planning_eligible` 必填 boolean；停用 Item 可为 false | `variant_current_planning_flag_missing` |
| 选中 BOM 属于候选 | `bom.name/sha256/modified` 与某候选一致 | `variant_selected_bom_not_candidate` |
| 订单行 UOM 与证据一致 | `line.uom == component.uom` | `variant_line_uom_mismatch` |

- `evidence_ref` 由已验证的选中 BOM 派生（`bom.name@bom.sha256[:12]`），
  生产者给的任意 ref 不再被读取。
- 默认标志（`is_default`）只作偏好，不消解多 BOM 冲突；冲突整体 pending。
- 历史证据看“当时是否有效”（`eligible_at_evidence`），不是今天的 `is_active`；
  当前结构不能回填为 Apr–Sep 历史真值，`current_structure_only` 一律 pending。
  停用 Item 可保留历史 family 关系，但 `current_planning_eligible=false`。
- 证据表里实际出现的 code 并入候选查询（`query_codes = KS/PK#/ND# ∪ items`），
  记录 `variant_query_codes_added` 与 `query_item_codes_effective`。
- `classify_line()` 对带前缀行不再应用 KS 前缀规则；条目问题记 pending，不中断整批，
  并在 `variant_validation_errors[{code,reason,detail}]` 留证（最多 200 条 + 总数）。

**family 与 demand_role 分离**

- 每行新增：`family_membership`（`ks_finished/cover/inner/unknown`）、`demand_role`
  （`terminal_finished/independent_cover/assembly_component/unknown`）、
  `canonical_ks`（+`confirmed/candidate`）、`cover_equivalent_factor`、
  `demand_event_id`、`counting_status`。
- 终端成品 1→皮壳 1；独立 cover 1→皮壳 1；**独立内胆销售不自动产生皮壳需求**
  （`cover_equivalent_factor=0`, `no_cover_demand`）。
- `qty/delivered_qty` 独立 fail-closed：缺数/坏值/NaN/负数记 None + `qty_status`，
  **不再经 `iss.num` 转 0**；`stock_qty` 需 Item stock UOM，本 PoC 记
  `None/requires_item_uom`，不猜。
- SO 行不等于终端销售；本 PoC 不做事件级去重、不输出终端需求合计。

**离线单测**（`test_en_family_poc.py`，44 条，全绿；不联网、不调用 `main()`）覆盖：
仅标签记录、非 family base、角色/方向冲突、ratio=0.5 与 ratio 字段不一致、
同 UOM `qty!=stock_qty`/factor≠1、UOM 换算缺失/不一致、过期、
current_structure_only、历史无 basis、多 BOM 冲突、候选缺 eligible_at_evidence、
当前 inactive 但当时有效、选中 BOM 不在候选、停用 Item 历史保留、
缺 current_planning_eligible、disabled 与 eligible 冲突、缺行 UOM、行 UOM 不一致、
坏 docstatus 不抛异常、未知 record schema、重复 JSON key、payload 篡改、
缺 producer/schema/version/source/site/as_of、未知 schema/rule/source/site、
行键缺失/重复、validator 异常隔离、demand_role 候选标签与 qty fail-closed。

### P1/P2 修复（bb25327b 复审后）

| 项 | 修复 |
|---|---|
| E1 同 UOM 数量矛盾 | `uom == stock_uom` 时强制 `qty ≈ stock_qty`；若给 `conversion_factor` 只能为 1；component/output 两侧都校验。新增 `variant_quantity_mismatch`。 |
| E2 schema/site/source | 文件层白名单 `schema_version=variant_evidence/1`、`rule_version=variant-evidence/1`、`source=erpnext.vilavi.cn`，`site` 必须等于当前 run 的 `ENV_URLS["prod"]`；`version/source` 必填；未知值 exit 2。manifest 记 `schema_decision`。条目 `schema_version` 也必须白名单，否则 `variant_unsupported_record_schema`。 |
| E3 坏 docstatus | `int()` 解析失败 → `variant_record_invalid`，不抛异常；`classify_line` 捕获 validator 异常 → `variant_record_invalid` + `exception:<Type>`；结构性错误计入 `variant_record_error_count`，run 标 partial。 |
| E4 行 UOM / eligibility | 行 `uom` 缺失 → `variant_line_uom_missing`，不再放行；`item.disabled=true` 且 `current_planning_eligible=true` → `variant_planning_eligibility_conflict`。Item/BOM hash 明确为受信 producer 边界，consumer 不重取源文档。 |
| 行键 | 新增 `line_index`、`line_key_status`；`line.name` 缺失/重复记 `line_key_invalid/duplicate`、pending、run partial；不再生成 `A:None`。 |
| demand | `demand_role` 改为 `terminal_finished_candidate / independent_cover_candidate / assembly_component_candidate`，`counting_status` 一律 `event_unverified`；`demand_event_id` 改名 `demand_event_candidate_id`；manifest 记 `demand_quantity_available=false`、`cover_equivalent_factor_consumed=false`。 |

**R1/R2 证据包**（bb25327b，提交前执行，未用于验收）：

- R1 `out/family_poc/r1_bb25327b/`：manifest sha256 `4275f55f...`，audit `5ccf2d1d...`；R2 `out/family_poc/r2_bb25327b/`：manifest `57dd5d3c...`，audit `5c7ccded...`。
- 两次 52 SO / 2,024 行 / family 132 / pending 1,770 / out_of_scope 122；忽略 `run_id` 的 audit SHA256 均为 `4fec233b...`；`audit_ok=true`。
- 五个详情失败状态本次真实数据未触发（`branch_exercised=false`）。

### 影响口径

无证据表时，原 1,378 行 PK/ND 全部变 pending，family 行数会显著低于 1,510。
**这是预期修正，不是回归**；本轮不重跑，故不发布新数字。证据表由独立只读步骤
（EN `Item`/`BOM`，BOM 子表逐单取父单）生成，需生产只读访问，**本补丁未执行**；
在它落地前 `adjudication=pending_remaining` 是诚实状态。

## S04 — 逐行 disposition、详情闸门与守恒

- **逐行审计文件**：默认 `<out>.audit.jsonl`（可用 `--audit-out` 覆盖）。每个选中 SO
  的**每一行**在 family 过滤前写入：`so/line_id/item_code/base_item_code/prefix_role/
  customer_item_code/customer_hit/item_group/disposition/family_role/disposition_reason/
  evidence_ref/qty/delivered_qty/open_qty/uom/warehouse/.../so_detail_status`。
  原 family JSONL 保留并新增 `disposition_reason`、`evidence_ref`、
  `base_item_code`、`prefix_role`、`customer_hit`、`so_detail_status`。
- **详情状态机**：每个 SO 恰好记一次 —— `detail_ok` / `detail_none` /
  `items_missing` / `items_not_list` / `items_empty` / `detail_error`（查询异常逐单捕获）。
  后五类 → `status=partial`（`detail_failed` 或 `items_unavailable`）、exit 1，
  并写入 `so_audit.failures[]`；**缺 items 不再静默零行并 complete**。
- **守恒**（`audit_checks`，失败 → `partial` + `audit_mismatch` + exit 1）：
  - `detail_ok + 五类失败 == selected_sos`；
  - `sum(line_dispositions) == 审计 JSONL 行数 == line_audit.rows`。
- `line_audit.sha256` 与 `audit_sha256` 入 manifest；`out_sha256` 保持。
- `pilot_seen` 改为在 disposition **之前**统计（查询覆盖），另记 `pilot_seen_family`。
- 状态语义写入 `notes`：**`status` 只表示查询/详情完整性**，逐行证据完成度看
  `adjudication`。

## 回归/验收（单列，未在本轮执行）

固定窗口 `2026-04-01..2026-09-30`、`--date-basis delivery`：

| ID | 场景 | 断言 |
|---|---|---|
| R1 | 同窗口跑两次 | 计数/原因码/审计行排序后一致（忽略 run_id）；`audit_ok=true` |
| R2 | 不带证据表 | family 中 role=PK/ND **= 0**；`variant_manifest_absent` 与变体行数对平；总行数不变 |
| R3 | 带证据表（单独获批构建后） | 每条 family 变体行 `evidence_ref` 非空且可回指 |
| R4 | 守恒 | 两条守恒式成立；JSONL 行数/hash 与 manifest 一致 |
| R5 | 逐行可追溯 | 抽样 pending/out_of_scope，`so/line_id/item_code` 与父单一致，原因码非空 |
| R6 | pilot 覆盖 | `pilot_seen`（覆盖）10/10；`pilot_seen_family` 单列 |
| R7 | `--variant-manifest` 指向不存在文件 | exit 2，不产出“成功” manifest |
| R8 | `items_missing` 未在真实窗口出现 | 记 `branch_exercised=false`，不造合成数据代替 |

命令（回放阶段执行）：

```bash
uv run python en_family_poc.py --date-from 2026-04-01 --date-to 2026-09-30 \
  --date-basis delivery --out out/family_poc/family_so_lines_v4.jsonl
```

## 未做 / 边界

- DN/WO/JC/SE 段、`modified` 水位/tombstone、同单位守恒仍未实现。
- 392 行 pending 只补原因码与逐行输出，不做裁定。
- 真实数字单列报告，不与 33,719 毛量/终端出库做等价断言；也**不是 G1 验收**。
