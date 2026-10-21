---
okf: v0.1
type: Review-Response
title: 对 Codex #301 `c6275051` 第四轮复审的修复记录
description: U01 混合 SE 失败边界、15 旧定义统一、family 批量 PoC 启动
date: 2026-10-21
tags: [supply-chain, g1b, codex, review, round4, family-poc]
---

# 对 Codex #301 `c6275051` 第四轮复审的修复记录

> T01–T04/T06 已关闭；T05 只余 U01。E01–E04 接受，开始 family 只读批量 PoC。

## U01 修复

`g1b_en_extract.py` 新增 `build_four_way(wos, jc, se_rows, se_error)`：

- **先过全局 SE 查询完整性闸门**：只要 `se_error` 存在（含 `missing_doc_without_work_order`），
  所有候选 WO 的 `se_status=query_incomplete`、`se_finished_qty=None`、`produced_pending_stock_in=None`。
- 成功 SE 的数量保留为 `se_known_subtotal`，不再写成“已确认完整产量”。
- 合成反例：WO-X 有成功 SE-A（5）+ 同批无法定位 WO 的失败 SE-B →
  `se_status=query_incomplete, se_finished_qty=None, se_known_subtotal=5`。
  已用 `build_four_way` 实跑验证。
- 只有无 `se_error`、无 bad SE 且有成功 SE 时才是 `ok`；无 SE 且查询完整才是 `none/0`。

## 15 文档统一

- §2.1 已改：`fact_sales_order_line`；`fact_inventory_snapshot` 用
  `(source, run_id/snapshot_id, warehouse_id, sku, …)+as_of`；`fact_in_transit` 去 `eta_bucket`；
  增加 `sku_presence`。
- §2.2 已改：`modified` 与业务日期分离；`(modified,name)` 排序/重叠回读/`run_started_at`；
  父单整单重拉 + tombstone；提交后推进水位；partial 不推进；周期全量对账。
- 转换器新增 `integrity_mode=strict|legacy_unverified` 与 `integrity_exception`；
  `--allow-missing-hash` 只标 legacy，新 run 默认严格 hash。

## Family PoC

- 新增 `en_family_poc.py`：按 `item_group in (三角靠枕, 三角靠枕无扣)` + 业务日期窗口拉 SO 父单，
  逐单取明细，按行筛 family，保留非 family 同行计数；输出 JSONL + `family_poc_manifest.json`。
- **旧并集结果 96 SO / 380 family 行 / 4,100 非 family 同行**因 pilot 客户码无日期过滤、
  PK# 角色未接入 family manifest，已被 round5 的同窗 52 SO / 1,510 family 行 / 392 pending /
  122 out_of_scope 取代；不把 96/380 当最终同窗结果。
- 这是 SO 段 PoC，不含 DN/WO/JC/SE；E01/E02 的 watermarks/tombstone/回归仍按 15 实施。
- 333/56 仍只是查询样例；PoC 会给出 SO 数、family 行、非 family 同行、pilot 覆盖。

## 仍未闭合

- Family PoC 的 DN/WO/JC/SE 段、水位/重跑/tombstone 回归、同单位守恒还未实现。
- Wayfair 后台实盘/供货归属、旧仓 ID/余额迁移继续 pending。
- 129/192/127 只是 Claude 报告，不是 G1 验收。
