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
| 显式期间 = horizon 长度 | `explicit_period` | true | D5 整期总量套到调用方声明的等长窗口（起点不同会写 note） |
| 显式期间 ≠ horizon 长度 | `explicit_period` | false | 不做比例外推（剩余期需求不能由整期总量代替） |
| 显式期间起点早于包 `as_of` | `explicit_period` | false | 该期间不在 D5 覆盖范围 |
| 包缺 `as_of` | — | false | 时点不明 |

行级字段：`period.basis/start/end/days/determinate/reason/note/forecast_anchor/as_of`。

## 已证供给与各阶段

`supply.proven = on_hand + in_transit + to_ship`，来自同一 EN 快照、单别名匹配、字段齐全。

- 别名部分匹配 / 多别名同时命中 / 同键数量冲突 / 快照缺失 → 不合计，`proven=null`，
  行标 `暂不能判断`（多别名相加会重复计数）。
- `po_open`（D6 `PO追加(去重)`）、`cg_transfer`（D6 `CG可调拨抵扣`）、`so_open`（W1）
  都是**不同阶段**，标 `counts_as_proven: false`，不进 `proven`。
- `supply.unknown` 列出所有为 null 的阶段与原因；未知不补 0。
- `decision.net_requirement = q95 − proven`；只有期间确定且证据齐全时才非 null。

动作：`不补`（净需求 ≤ 0）→ `催已有/待核`（净需求 > 0 且存在未证管线）→ `补`
（净需求 > 0 且无管线可催）→ `暂不能判断`（期间/需求/实时库存任一不可用）。

## W1 SO 去重

- 数据源：`W1_SO.jsonl` 的 `payload.lines`，开放量 = `qty − delivered_qty`。
- 去重键 `(so, so_line)`：重复行只计一次，`so.duplicate_lines_collapsed` 与
  `report.so_dedupe.duplicate_lines/duplicate_open_qty` 回报折叠量。
- 三段保留：`recent_open_qty`（创建日 ≥ as_of−6 个月）/ `history_open_qty` /
  `unknown_date_open_qty`（创建日缺失或晚于 as_of）；三者之和必须等于 `open_qty`，
  行级 `three_bucket_sum_equals_open`、报告级 `so_three_way.balanced` 双向核对。
- `so.included_in_proven_supply` 恒为 `false`：SO 是工厂交付阶段，不是海外可发供给。
- `payload.stage_balances`（若有）另成 `so_stage`：按 `stage` 汇总 in_house 余额，
  `unknown` 原样保留为 `unknown`，`external_fba` 单列，`over_produced` 单独成阶；
  与开放量**不同度量、不可相加**。
- W1 证据 `as_of` 与刷新 `as_of` 不同时进 `report.warnings`。

## report.json 字段

| 字段 | 含义 |
|------|------|
| `bankers` | `input_rows = accepted + rejected + skipped` 与 `balanced` |
| `accepted_by_action` / `accepted_by_period_basis` | 接收行分布 |
| `live_status_counts` | matched / partial / multi_alias / not_found / unavailable… |
| `rejected[]` / `skipped[]` | `row_index`、`product_id`、`reason`、**完整源行** |
| `so_dedupe` | 去重键、读到/唯一/重复行数、重复开放量、非开放跳过计数 |
| `so_three_way` | 三段合计 vs 开放总量与 `balanced` |
| `so_stage` | 阶段余额汇总（非相加、不计已证） |
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

## 样例（2026-11-24，pack 2026-11-13.1）

- `--all`（无显式期间）：输入 296 = 接收 296 + 拒收 0 + 跳过 0；动作全是 `暂不能判断`；
  SO 唯一 987 行、重复 0 行、三段合计 8009 = 开放 8009（守恒）。
- `--period-start 2026-11-13 --period-end 2027-02-17`（97 天等长）：动作
  `{'暂不能判断': 153, '补': 83, '催已有/待核': 22, '不补': 38}`；
  live 状态 `{matched:155, partial:86, multi_alias:55}`。
- 未核实：样例用的是 2026-11-23 的离线 EN 快照（`--live-snapshot`），不是 11-24 当刻；
  W1 SO 证据 `as_of=2026-10-27`；19 行 D5 q95 缺失保持 null。
