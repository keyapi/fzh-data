---
okf: v0.1
type: Review-Response
title: 对 Codex #301 `93e6bd1f` 第三轮 G1b 复审的修复记录
description: T01–T06 修复、E01–E04 批量 ETL 契约、重跑差异与剩余项
date: 2026-10-21
tags: [supply-chain, g1b, codex, review, round3, etl]
---

# 对 Codex #301 `93e6bd1f` 第三轮 G1b 复审的修复记录

> 已关闭项不重做；本轮修 T01–T06，并在 [15-full-family-etl.md](../15-full-family-etl.md)
> 补 E01–E04 批量契约。不等待 Wayfair 资料，不做泛调研。

| ID | 修复 | 验收/证据 |
|---|---|---|
| T01 | `coverage.py` 增加 `presence`/`quantity_status`；完整仓中未返回 SKU → `missing`，不记 0；只有实际返回且校验为 0 → `observed_zero`；3PL/未采样 `available/intransit/supply=None`，只留 `reference_*` | 重算：**129 observed_zero / 2 missing / 192 <2 月 / 127 unknown**；missing 为 `CENVel1612-Black-138-Cover` 与 `CEN003-DPBLUE-100-old` 各 1 件 |
| T02 | `stock_daily_backup.py` 用 `day/run=<run_id>/` 不可变目录；仓文件先写 `.tmp` 再 `os.replace`；`day/manifest.json` 最后原子发布；`g1b_from_daily_backup.py` 校验 manifest `file_sha256`，失配/缺失拒绝（旧 manifest 需 `--allow-missing-hash`） | 不再“旧 manifest + 新仓文件”；hash 失配不重算新 hash 背书 |
| T03 | 转换器保留用户 `requested_warehouses`；manifest 缺请求仓 → `missing_requested` 单列，`complete=false`，不因过滤消失 | 请求 A+B、B 不存在时 B 不再被吞 |
| T04 | `load_stock` 逐仓读取转换产物 `by_warehouse[wh].complete`；global complete 只作摘要；A 成 B 败时 A 仍 complete | 合成一成一败验证 |
| T05 | `missing_doc` 保留 list 阶段 `work_order`；无法定位时置 `se_error=missing_doc_without_work_order`，相关 WO 全部 unknown，不再当 0 | 真实函数 + main 汇总片段复现通过 |
| T06 | headline 过滤统一用 `headline_eligible=window_complete and complete_branches`；缺月/不完整窗口不进无供给/低覆盖计数；SKU 行与 branch 共用 `coverage_eligible` | 5/6 月合成窗口 headline 为空；partial 输出保留但不混入完整统计 |

## 15 的 E01–E04

已在 [15-full-family-etl.md](../15-full-family-etl.md) 增加：

- **E01 family 全集**：版本化 family manifest（KS leaf/规范物料/客户码、PK#/ND# 角色、历史停用/改组、纳入/排除/pending）；父单批量拉取后按行筛选，保留非 family 同行去向；两个 item_group + item_code 并集 + 已知 9 个试点客户码交叉核验；manifest 记录 333/56、页数、筛选后行数。
- **E02 增量/重跑**：每 DocType 明确 `modified` 发现与业务日期字段分离；稳定排序 `(modified,name)`、重叠回读、`run_started_at` 上界；父单命中后整单重拉子表，删除子行 tombstone；取消/amended/移组保留；raw/staging/fact 提交后才推进水位；partial 不推进；周期全量对账。
- **E03 不可变键**：`fact_inventory_snapshot` 用 `(source, run_id/snapshot_id, warehouse_id, sku, ...)` + `as_of`，日期只作分区；“选定合格快照”视图；`fact_in_transit` 去掉可变 `eta_bucket`，ETA 单独版本化；通途汇总 intransit 独立 snapshot，不编造 doc_id；`float_sales_order_line` 更正为 `fact_sales_order_line`。
- **E04 守恒/回归**：SO→DN→SE 不直接相等；按 cutoff/UOM/链接粒度检查有效订单/取消/正向发出/原未交/超发/退货；JC/SE/DN 分开；unknown 不补 0；组件/成品经 BOM/UOM 换算；最小回归包含旧单修改、取消、删子行、移组、同 modified 跨页、失败重跑、ETA 修订、同日双快照、缺 SKU vs explicit0、SE 详情失败。

## 重跑

- 4 仓转换：requested=4/read=4，`complete=True`，bad=0、conflict=0；
  Wayfair `unknown_authority`、supply=None（reference 665），不计缺口。
- **T02 负例**：manifest 期望 hash 全 0，转换器 `read=0`、`complete=false`，
  `hash_mismatches` 记录 expected/actual，不用新 hash 背书。
- **T03 负例**：请求 `美东-CENTRADE + 不存在仓`，`requested=2/read=1`、`complete=false`，
  缺请求仓单列，不再消失。
- **T04 正例**：合成 A 完整、B 缺文件：转换 global=false，但 `by_warehouse[A].complete=true`；
  `load_stock` 的 `selected_complete[A]=true`，A 不被 B 降级。
- **T06**：headline 过滤统一用 `window_complete`；缺月/partial 时 headline 列表为空（代码路径已加）。
- 覆盖：129 observed_zero / 2 missing / 192 <2 月 / 127 unknown；旧 131/194 被 presence 规则取代。
- EN 试点：63 SE 全 `ok`；首/末路由 cut→…→质检发现问题（无卡）→ last_qty=null；
  `last_card` 100 仅辅助；SE 行含 ID/UOM/成品标记。
- 旧 2026-10-21 flat manifest 无 `file_sha256`，本轮验证用 `--allow-missing-hash`；
  新 run 起强制 hash，旧数据不被新 hash 背书。

## 仍未闭合

- 全 family 批量 PoC 尚未实现；E01–E04 是实施契约，不是已跑结果。
- 333/56 只证明查询可用，不证明全族/全页/历史完整。
- Wayfair 后台实盘/调拨归属、旧仓 ID/余额迁移仍 pending。
- 131/194/127（含更新后的 129/192+2 missing）只是 Claude 报告，不是 Codex 复现或 G1 验收。
