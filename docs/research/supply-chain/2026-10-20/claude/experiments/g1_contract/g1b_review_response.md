---
okf: v0.1
type: Review-Response
title: 对 Codex #301 `d9a11557` G1b 复审的修复记录
description: G1B01–09 逐项修复、重跑口径与仍未闭合项
date: 2026-10-20
tags: [supply-chain, g1b, codex, review, response]
---

# 对 Codex #301 `d9a11557` G1b 复审的修复记录

> 结论：**首版不是契约验收**；本轮只修适配器与报告口径，不扩 top10–20。
> 修复后用同一批本地输入重跑；WayfairCG 实盘、仓库合并证据仍标 unknown/unverified。

| ID | 修复 | 证据/结果 |
|---|---|---|
| G1B01 | `g1b_coverage.py` 增加 `supply_status`；只有 `sampled_complete` 分支进入缺口/低覆盖；PL 单独采样，WayfairCG `unknown`，退货仓 `demand_only`；旧 450/501 撤回 | 缺口计数改为 branch×SKU；旧数字不再发布 |
| G1B02 | 订单必需列校验；缺月/缺列 `window_complete=false`；坏数量/负数/非整数/缺 SKU/缺仓分别计数，不转 0；库存坏值 `None` 不聚合 | 本批 bad_qty=0、negative=0、非整数=0、缺 SKU/仓=0 |
| G1B03 | 库存查询校验业务码/响应结构；满 `max_pages` 且末页仍满 → `truncated=true`、`complete=false`；capture_start/end、page_meta | 新快照 JSON 带 `complete`/`page_meta`；旧快照标 legacy |
| G1B04 | 库存按 `(warehouse, sku)` 去重；相同忽略、不同冲突并置 incomplete；多快照同仓只取最新 `fetched_at` | `duplicate_conflicts`、`duplicates_ignored`、`selected_file_per_warehouse` |
| G1B05 | JC 按工序聚合，不再跨工序求和；首道/末道取有卡的工序；无 JC=unknown；补 Manufacture SE；四量按 WO 输出 | 试点 63 张 SE；`first/last/se/pending` 分列 |
| G1B06 | `EN_API/item_shipment_status.py` 的 DN 投影增加 `Delivery Note Item.name`；导出 `dn_line_id` | 100 条 DN 行都有自身 ID |
| G1B07 | 未发量互斥分解：死单/在产/无计划/超发；作废单不计入 | 421+622+9-16=1,036，difference=0；7=+9-16 |
| G1B08 | 同客户码多 EN 物料 → 该码进 `ambiguous` 并从映射移除，订单侧单列，不 fail-open | 本批 ambiguous=0，但规则已 fail-closed |
| G1B09 | 新增 [g1b_warehouse_evidence.md](g1b_warehouse_evidence.md)：当前仓 ID/状态、历史 2026-05/08 旧皮壳仓余额；无改名/迁移凭证 → `unverified` | 不再宣称“已并入” |

## P2 报告完善

- 覆盖分开 `on-hand` 与 `含在途名义`；在途无 ETA，不当服务承诺；跨 SKU 总量不互换。
- 去掉 `lead_date` 导出（`legacy_lead_display_excluded=true`）；`so_delivery_date` 缺失进 `field_issues`。
- manifest 增加月份观测、缺月/缺列、坏行、库存 complete/page 元信息；逐行主状态分开。
- 快照标 `snapshot_is_transactional=false`，记录 capture_start/end。
- 每日备份：浏览器 `tongtu.stock.export` 实测只产成本/头程模板，不是库存数量；
  新增 `stock_daily_backup.py`（API）与 `FZH-TongtuStockApiDaily` 05:17。
- 5% 退货仅未来需求情景；库存净算不二次冲减。

## 仍未闭合

- 完整 API 库存快照重跑后，重新计算缺口；在此之前不发布 450/501。
- 旧皮壳仓的 ID/改名/迁移/余额凭证仍缺；`unverified`。
- WayfairCG 后台库存与调拨归属仍 unknown。
- top10–20 扩样等上述修复重跑通过后再做。
