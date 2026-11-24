---
okf: v0.1
type: Log
title: 变更日志
description: Supply Copilot 的时序变更记录
tags: [supply-copilot, changelog]
---

# 变更日志

## 2026-11-24（复核修正）

- **期间有效性**：库存观测日晚于声明期间起点时一律拒绝（`demand_bridge.available=false`），
  不再用整期需求减当下库存；确定建议要求期间起点 = EN 快照日。修正前 11/24 库存冲抵
  11/13 起整期，296 行错标可确定、143 行给出确定动作。
- **SO 唯一汇总**：报告改为从证据侧按唯一 `(product_id, branch)` 键重算，
  并拆出 `so_scope`（in_scope 7795 / out_of_scope 10200 / other_branches）；
  旧 `8009` 是跨形态行重复累加 214。
- **缺量不补 0**：`so_evidence` 的 `qty`/`delivered_qty` 缺失保持 `open_qty=null` 并单列；
  `so_stage` 某阶段有缺量行时该阶段合计为 null、`known=false`。
- **旧快照未观察到 ≠ 0**：W1 证据与刷新时点不一致时，`so.current_for_decision=false`，
  SO 不参与"补"的确定判断（动作落 `催已有/待核`）。
- **快照完整性**：已存在快照重算 body 哈希后再比对，防手改。
- 测试增至 29 条（新增期间已逝、跨形态去重、范围外、缺量 null、篡改拒绝）。

## 2026-11-24

- **新增整分公司批量刷新**：`refresh --all --out <私有目录>` 输出不可变快照
  `refresh_<branch>_<as_of>_<sha>.json` + `report.json`；单 SKU `--sku` 用法保持兼容。
- **期间语义**：D5 的 97/157 天标为 `full_period`，不得当剩余期；缺显式期间一律
  `暂不能判断`，只有显式等长期间（`--period-start/--period-end`）才给确定建议。
  实现见 `period.py`（docstring 说明整期/剩余期边界）。
- **W1 SO 去重**：`demand_collaboration.so_evidence.load_deduped` 按 `(so, so_line)`
  折叠重复行并回报折叠数/重复开放量；`load()` 保持原行为。三段（近期/历史/创建日未知）
  合计等于开放总量，SO 恒不计入已证供给。
- **W1 阶段余额**：`so_stage.py` 汇总 `stage_balances`，unknown 阶段原样保留，
  与开放量非同一度量、不可相加、不进 proven。
- **测试**：`supply_copilot/tests/test_refresh_batch.py`（21 条，合成数据）。
