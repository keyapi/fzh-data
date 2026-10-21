---
okf: v0.1
type: Review-Response
title: 对 Codex #301 `fd1029b4` 第二轮 G1b 复审的修复记录
description: RR01–RR08 修复、重跑口径与仍未闭合项
date: 2026-10-21
tags: [supply-chain, g1b, codex, review, round2]
---

# 对 Codex #301 `fd1029b4` 第二轮 G1b 复审的修复记录

> 已关闭项不重做：DN 行键、差 7、BOM 歧义、仓名业务口径。
> 本轮修 RR01–RR08，重点是把 `daily backup → 转换 → coverage` 的完整性绑定到实际选中数据。

| ID | 修复 | 验收/证据 |
|---|---|---|
| RR01 | `coverage.py`：`complete` 绑定到**选中的具体仓/文件**；坏值/冲突把对应仓标 incomplete；按 `REQUIRED_SUPPLY_WAREHOUSES` 判断 branch 是否全覆盖（USNJ=CENTRADE、USTX=DANEEY、PL=PL）；旧快照 complete 不再并集放行 | `selected_complete`、`incomplete_warehouses`、`coverage_eligible_branches`；4 仓测试 3PL 不再 sampled_complete |
| RR02 | `from_daily_backup.py`：空/NaN/Inf/负数/分数→bad row，不转 0；同仓同 SKU 重复同值计数、异值 conflict 并**整键丢弃**（不 first-wins）；缺文件/坏行/冲突→该仓 complete=false；文件 sha256 | `bad_rows_total`、`duplicate_same`、`duplicate_conflicts`、`file_hashes`、`complete_warehouses` |
| RR03 | `stock_daily_backup.py`：`rows_of` 对未知结构抛错；业务码必须 200；合法空数组与无法解析分开；请求仓未命中/空仓清单不再 `all([])` 成功；坏行降低该仓 complete；JSONL/manifest 先写 tmp 再原子替换；加 `run_id`/`script_version` | 单仓 1 页测试 truncated/complete=false；全量补跑 manifest `complete=True` |
| RR04 | `en_extract.py`：首/末工序取**路由首/末**，无卡则数量 unknown，不用后道替代；保留 JC ID/status/docstatus/for_quantity；另给 `last_card_operation` 辅助诊断 | 试点 `first_operation=裁剪`、`last_operation=通用返工`（无卡→last_qty=null），不把缝制改名成首道 |
| RR05 | `en_extract.py`：每张 SE 保留行 ID/item/qty/uom/stock_uom/目标仓/finished 标记；状态 `ok/missing_doc/no_finished_lines/no_matching_finished_line/uom_unknown`；只有 `ok` 才计 finished_qty；详情失败/无匹配/UOM 未知保持 unknown，不把 WO 产量当 0 | `se_status` 每 WO；四量 `produced_pending_stock_in` 仅在 last_op 与 se 都已知时算 |
| RR06 | `coverage.py`：Wayfair 即使 API complete 也只标 `unknown_authority`；权威源必须是 Wayfair 后台 manual；API 库存只作参考，不进入缺口 | `3PL [unknown_authority]`，供给 665 只展示，不计缺口 |
| RR07 | 转换器输出 `requested/read/missing_warehouses`、逐仓 complete、file_hashes；缺文件明确失败；manifest 原子发布 | 4 仓测试 requested=4/read=4/complete=True |
| RR08 | 订单非整数/NaN/Inf 不再纳入毛量，进 bad samples；未匹配按文本分 `pending_text_tri_rows` 与 `non_family_rows`；`coverage_eligible` 依赖窗口完整 | 6/6 月；本批 non-integer=0；pending text-tri **763 行/931 件**，non_family 11,478/13,696，合计 45,129/48,346 |

## 重跑口径

- 2026-10-21 用 4 仓（CENTRADE/DANEEY/PL/WayfairCG-Cranbury）跑
  `daily backup → 转换 → coverage`：requested=4/read=4/complete=True，bad=0、conflict=0；
  Wayfair 标 `unknown_authority`，不计缺口；USNJ/USTX/PL 仍为 `sampled_complete`，
  缺口 131/194/127 不变。
- EN 试点重跑：`first_operation=裁剪`、`last_operation=质检发现问题`（无卡→last_qty=null），
  `last_card_operation=质检`（100）作为辅助；`produced_pending_stock_in=null`，
  `produced_pending_stock_in_last_card=0`（辅助，不替代契约末道）；63 张 SE 全部 `status=ok`，
  含行 ID/UOM/成品标记。
- `stock_daily_backup.py --max-pages 1`：`truncated=true`、`complete=false`，不再把截断当完整。
- 131/194/127 仍是 Claude 该批完整快照报告，不称 Codex 复现或 G1 门槛通过。
- 2026-10-20 18:19 与 2026-10-21 09:46 是两批：前者用于 131/194/127；后者是每日 API 补跑，
  `complete=True`，不自动给前批背书。
- top10 9/9 `difference=0` 只是同 SO 字段分解自洽；不等于四量/全 family 验收。
- 库存结存 1,527 / 销售报表 568 / API 1,140 的粒度不同（唯一 SKU/branch×SKU/别名），
  不能直接断言“谁更全”；同 cutoff 下 API 是零库存 SKU 超集，库存结存有状态/别名。

## 仍未闭合

- WayfairCG 后台实盘/供货归属：Tongtool/Sellfox 调拨 API 均 0 条，仍 unknown。
- 全 family EN 单据未全量抽取；需批量 ETL，不逐客户码 1,486 次。
- 旧皮壳仓 ID/余额迁移凭证 pending。
- RR04 的 `last_operation=通用返工` 无卡导致 last_qty=null 是保守结果；
  若业务确认返工/质检问题工序可忽略，需要路由 `required` 字段或业务规则。
