---
okf: v0.1
type: Reference
title: 整分公司刷新快照 — 期间、W1 去重与对账口径
description: supply_copilot refresh --all 的口径、字段与验收证据
tags: [supply-copilot, refresh, period, so-dedupe, reconciliation]
---

# 整分公司刷新快照

## 命令

```bash
uv run python -m supply_copilot refresh --branch USNJ --as-of 2026-11-24 --all \
  --out <私有目录> [--period-start YYYY-MM-DD --period-end YYYY-MM-DD] \
  [--d6-version v6_22|v6_24] [--horizon 97|157] [--json] [--live-snapshot FILE]

# 单 SKU（兼容旧用法，无 --out 时仍是历史单 SKU 口径）
uv run python -m supply_copilot refresh --branch USNJ --sku KS0001-xxx
```

- `--all` 必须给 `--out`：不允许把全量结果丢到临时目录。
- `--out` 给定时写入 `refresh_<branch>_<as_of>_<sha12>.json`（不可变快照）与
  `report.json`（对账报告）。同内容重跑不重复写；内容不同但文件名相同则拒绝覆盖。
- `--live-snapshot` 读离线 EN 库存 JSON（`{"rows": [...]}` 或数组），免网络、便于复跑。

## 期间语义（D38–D40 / P0 口径）

| 情形 | period_basis | determinate | 说明 |
|------|--------------|--------------|------|
| 未声明期间 | `full_period` | false | D5 整期（97/157 天，起点=包 `as_of`）不得当剩余期用于补货 → `暂不能判断` |
| 显式期间 = horizon 长度，且**库存观测日 = 期间起点** | `explicit_period` | true | D5 整期总量套到调用方声明的等长窗口（起点不同会写 note） |
| 显式期间 ≠ horizon 长度 | `explicit_period` | false | 不做比例外推（剩余期需求不能由整期总量代替） |
| 显式期间起点早于包 `as_of` | `explicit_period` | false | 该期间不在 D5 覆盖范围 |
| **库存观测日晚于期间起点** | `explicit_period` | false | 已逝需求进不了 D5 整期总量扣除，`demand_bridge.available=false`，不桥接就拒绝 |
| 库存观测日早于期间起点 | `explicit_period` | false | 库存不是期初库存 |
| 库存快照缺 `snapshot_at` | `explicit_period` | false | 库存时点不明（D38） |
| 包缺 `as_of` | — | false | 时点不明 |

行级字段：`period.basis/start/end/days/determinate/reason/note/forecast_anchor/as_of/
supply_observed_at/elapsed_days/demand_bridge`。

> **已逝需求桥（2026-11-24 修正）**：早期版本允许"显式等长期间"直接确定，
> 结果 11/24 的库存冲抵 11/13 起的整期需求，296 行全部错标可确定。
> D5 只有整期总量、没有日级需求路径，无法扣除已逝消耗，因此现在一律拒绝；
> 要做确定建议，声明期间起点必须等于 EN 库存观测日。

## 已证供给与各阶段

`supply.proven = on_hand + in_transit + to_ship`，来自同一 EN 快照、单别名匹配、字段齐全。

- 别名部分匹配 / 多别名同时命中 / 同键数量冲突 / 快照缺失 → 不合计，`proven=null`，
  行标 `暂不能判断`（多别名相加会重复计数）。
- `po_open`（D6 `PO追加(去重)`）、`cg_transfer`（D6 `CG可调拨抵扣`）、`so_open`（W1）
  都是**不同阶段**，标 `counts_as_proven: false`，不进 `proven`。
- `supply.unknown` 列出所有为 null 的阶段与原因；未知不补 0。
- `decision.net_requirement = q95 − proven`；只有期间确定且证据齐全时才非 null。

动作：`不补`（净需求 ≤ 0）→ `催已有/待核`（净需求 > 0 且存在未证管线/管线未知）→ `补`
（净需求 > 0 且无管线可催）→ `暂不能判断`（期间/需求/实时库存任一不可用）。

> SO 只有在**证据时点 = 刷新时点且数量完整**时才可视为"已知 0"；旧 W1 快照未观察到
> 不等于当前管线为 0，因此不会因为 SO=0 得出"补"，而是 `催已有/待核`。

## W1 SO 去重

- 数据源：`W1_SO.jsonl` 的 `payload.lines`，开放量 = `qty − delivered_qty`。
- 去重键 `(so, so_line)`：重复行只计一次，`so.duplicate_lines_collapsed` 与
  `report.so_dedupe.duplicate_lines/duplicate_open_qty` 回报折叠量。
- **数量缺失保持 null**：`qty`/`delivered_qty` 缺失或非数字时 `open_qty=null`、
  `qty_status=unknown`，单列在 `so.unknown_qty_lines` / `so.unknown_lines`；
  不参与三段合计，也不当成 0。`so.completeness=partial_unknown_qty`。
- **含未知行的合计一律为 null（第三轮修正）**：行级 `so.open_qty` 及其日期段、
  `so_scope.*`、`so_three_way.open_total`、`so_stage.stage_totals` 只要混入未知量
  就是 `null`；已知部分另存为 `known_open_qty` / `known_recent` / `known_history` /
  `known_unknown_date` / `stage_known_subtotals`；`balanced` 此时为 `null`
  （另给 `known_balanced`）。不允许把"已知小计"写成"总量"或 0。
- **按 product_id 唯一汇总（2026-11-24 修正）**：296 个形态键只有 290 个唯一
  `product_id`；SO 按产品附挂，同产品的各形态行共享同一汇总，**不可跨行相加**。
  行级保留 `so.aggregation` 说明；报告一律从证据侧按唯一键重算。
- **范围分解**：`so_scope.in_scope`（快照范围唯一键）/ `so_scope.out_of_scope`
  （本分公司但不在本次 D6 选取范围）/ `so_scope.branch_total`（前两者之和）/
  `so_scope.other_branches`（其它分公司）。`so_dedupe` 是**文件级（全分公司）**
  统计，不等于快照范围。
- 三段保留：`recent_open_qty`（创建日 ≥ as_of−6 个月）/ `history_open_qty` /
  `unknown_date_open_qty`（创建日缺失或晚于 as_of）；**已知**三段之和等于**已知**
  `open_qty`（`known_three_bucket_sum_equals_known_open`），报告级
  `so_three_way.known_balanced` 复核；完整时 `balanced` 才为 true/false。
- `so.current_for_decision`：证据 `as_of` = 刷新 `as_of` 才为 true；否则
  `completeness=stale_observation`，SO 不参与"补"的确定判断。
- `so.included_in_proven_supply` 恒为 `false`：SO 是工厂交付阶段，不是海外可发供给。
- `payload.stage_balances`（若有）另成 `so_stage`：按 `stage` 汇总 in_house 余额，
  `unknown` 原样保留为 `unknown`，`external_fba` 单列，`over_produced` 单独成阶；
  某阶段只要有数量缺失行，该阶段合计即为 **null**（不是 0），`so_stage_complete=false`，
  已知部分见 `stage_known_subtotals`；与开放量**不同度量、不可相加**。

## report.json 字段

| 字段 | 含义 |
|------|------|
| `bankers` | `input_rows = accepted + rejected + skipped` 与 `balanced` |
| `accepted_by_action` / `accepted_by_period_basis` | 接收行分布 |
| `live_status_counts` | matched / partial / multi_alias / not_found / unavailable… |
| `rejected[]` / `skipped[]` | `row_index`、`product_id`、`reason`、**完整源行** |
| `so_dedupe` | 文件级（全分公司）去重键、读到/唯一/已知/未知数量/重复行数、非开放跳过计数 |
| `so_three_way` | **快照范围**唯一键的三段合计 vs 开放总量、`balanced`（不完整时 null）、`known_*` 小计、`known_balanced` |
| `so_scope` | in_scope / out_of_scope（含原因）/ branch_total / other_branches 分解 |
| `so_stage` | 阶段余额汇总：`stage_totals`（含未知为 null）、`stage_known_subtotals`（非相加、不计已证） |
| `snapshot` | 文件名 + 整包/行级 sha256 + 行数 |
| `source_hashes` | D5/D6/sku_map/W1 的 sha256 + 与 manifest 不一致清单 |
| `warnings` | 陈旧快照、SO 证据时点、全行整期拒绝、q95 缺失等 |
| `field_dictionary` | 字段口径 |

拒收 = 结构上无法成行（缺 product_id、缺形态/UOM）；跳过 = `(product_id, 形态, UOM)`
重复。证据不足的行**不拒收**，仍进快照并标 `暂不能判断`。

## 确定性

`snapshot_sha256 = sha256(canonical(整包去掉该字段))`，`rows_sha256` 覆盖行数组；
不含运行时钟。同一输入（含同一 live 快照）→ 同一字节。测试
`test_snapshot_hash_is_deterministic` 与两次 `--out` 目录 `diff -r` 均已验证。
已存在的快照文件会**重算 body 哈希**并与记录值比对，不一致即拒绝覆盖（防手改）。

## 样例（2026-11-24，pack 2026-11-13.1，真实 EN 快照 2026-11-24 05:17:57）

- `--all`（无显式期间）：输入 296 = 接收 296 + 拒收 0 + 跳过 0；动作全是 `暂不能判断`。
- `--period-start 2026-11-13 --period-end 2027-02-17`（起点早于库存观测日 11 天）：
  296 行全部拒绝（已逝需求未桥接），动作全为 `暂不能判断`。
- `--period-start 2026-11-24 --period-end 2027-02-28`（97 天，起点=库存观测日）：
  `{'暂不能判断': 153, '催已有/待核': 105, '不补': 38}`，**无 `补`** —— W1 证据
  `as_of=2026-10-27` 非当前，不能断言"无管线可催"。
  live 状态 `{matched:155, partial:86, multi_alias:55}`。
- SO（同一 W1，SHA `dc6b97bd…`）：文件级 987 唯一开放行 / 419 键（全分公司）；
  USNJ 快照范围 88 唯一键 / 160 行 / 开放 **7795**（近期 6717 + 历史 1078）；
  范围外（本分公司非快照范围）173 行 / **10200**；其它分公司 654 行 / 33546（单列）。
- 未核实：W1 SO 证据 `as_of=2026-10-27` 早于刷新时点；19 行 D5 q95 缺失保持 null；
  `available/intransit/waiting_shipment` 三类是否业务互斥未核实（D39）。
- 旧样例 `8009` 已作废：那是把 SO 按形态行重复累加（7795 + 跨形态重复 214）。

