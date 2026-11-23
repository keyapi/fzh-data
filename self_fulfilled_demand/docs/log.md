---
okf: v0.1
type: Log
title: 自发货需求增量接入 — 变更日志
description: 2026-10-27 接入、审查返修与真实采集记录
tags: [log, demand, en-demand-v1]
updated: 2026-10-27
---

# 变更日志

## 2026-10-27

- 新建 `self_fulfilled_demand/`：EN `Tongtool Order` 只读增量 + 本地 Parquet + 旧 GS 消费接口。
- 实测 EN schema：154,632 单（自发货 120,808 / FBA 33,824），子表 `order_items` / `packages`
  可从父单列表接口扁平读取；`goods_detail_id` 大面积为空，行身份改用 raw `orderDetailsId` + idx 回退。
- 完成真实采集（窗口 A 6,800 + 窗口 B 20,703 = 27,503 单；28,823 行；24,323 包裹）。
- 审查返修 D01–D08：
  - 履约类型与需求有效性分离；代发/unknown 进 `deferred` 而不是 quarantine。
  - GS 按发货口径 + EN 补洞/覆盖；新增 `superseded_cross_cutover` 防止跨切点同量双计。
  - 分页预算耗尽抛 `EnBudgetExhausted`，标 partial、不推水位；同时间戳用 `limit_start` 推进。
  - 快照目录 + `CURRENT` + `commit.json`；损坏指针报错；`pinned()` 固定快照读取。
  - `sale_date` 缺失单列 `date_unknown`；GS 缺列直接报错。
  - 新增 `demand_by_day_sku_warehouse` + UOM 证据字段（未知保留 null）。
- 初次采集由修复前进程启动；用 `finalize_store` 收编快照并按独立计数（6,800 / 27,503）
  与 9 月末 1,816 行交集（数量差 0）离线验证，manifest 标 `validation_status=passed`。
- 离线测试 22 个通过。

## 2026-10-27（续）规范需求适配层

- 新增 `canonical.py` + `warehouse_aliases.json`：全历史 GS 与 EN 增量统一到
  `canonical_sku × canonical_warehouse × uom`，给供应分桶 b08acc05 消费。
- 实跑 2022-12-01→2026-10-31：413,561 行 / 440,179 件输入；可净额 402,494 行 / 428,576 件；
  阻断 11,067 行 / 11,603 件；FBA 排除 2,453 行，3PL 保留 5,419 行。
- 仓库旧名合并 288,836 行（CENTRADE/FZHPoland-covers/FZH-DANEEY）；子仓 5 类未证合并保持独立。
- EN `Item.stock_uom` 有界补建 1,627 个物料（1,622 个 + 5 套），零缺失。
- GS 历史 18,317 行通过唯一 EN 行匹配补齐发货形态；其余保持 unknown。
- 离线测试新增 10 个 canonical 用例（共 31 个）。

## 2026-10-27（审核返修 da4fa1e6）

- 五类未证合并子仓（FZH-DANEEY 半成品/成品/皮壳/退货、FZHPoland-finished）保留原行但
  阻断净额（`subwarehouse_identity_unproven`）；90,286 行 / 98,068 件从可净额移出。
- 新增 `demand_netting.parquet`（四列唯一，已过滤资格）与 `demand_blocked.parquet`（阻断账）；
  `demand_canonical.parquet` 明确为明细聚合，禁止 upsert/按行连接供应。
- 整次构建固定同一 EN 快照；manifest 记录 `en_snapshot` 的 commit_id 与 orders/lines 哈希。
- 新增 21 个审核回归（共 52 个）：完整构建守恒、四列键、五类子仓、未知/空仓、FBA 端到端、
  GS 形态、UOM 缺失/空白、复合原因、空输入/缺日期/无效数量、SKU TSV 空字段、快照切换、供应目标过滤。
- 修复后：可净额 312,208 行 / 330,508 件；阻断 101,353 行 / 109,671 件；四列重复 0。
