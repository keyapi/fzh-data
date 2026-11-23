---
type: Log
title: 运营需求协同变更记录
---

# 变更记录

## 2026-11-13

- 新增 EN 实时库存覆盖层（只读）：读取 `Tongtool Stock Run` + `Tongtool Stock Latest`，按通途 SKU+仓 join，附 `available/intransit/waiting_shipment/defects`、`run_id`、`snapshot_at` 与快照 C/E 差值。失败回退本地缓存并标旧，无缓存标不可用；未知不补 0，不写 EN、不写快照。`waiting_shipment` 文案固定为“通途库存待发，未关联单据/订单”。
- SO 证据增加 `transaction_date` 与 `delivery_date`；按创建日期分“近期（默认 6 个月）/历史开放/创建日未知”三段，历史正余额单列不丢弃；明细显示创建、交付、已交/未交、逾期。
- 测试新增真实快照（169/1/9）、6 个月分组边界、实时覆盖层缺失回退、未知不补 0 与快照不被改写。
- 新增 USNJ 建议接入只读规划；区分需求基准、补货快照与运营覆盖，列出分阶段验收。复审文件缺失、试点证据冲突保留为前置待核项；未改代码或生产。
- 落地 P1：`recommendation.py` 将显式 CSV 转为不可变 `recommendation_snapshot`，独立表存储，不改 D5 基准/D6/C/E；工作台新增只读“USNJ 建议”页签与四类筛选，未知不补 0；无改量/审批/下单入口，`service_certified`/`replenishment_eligible` 恒 false。

## 2026-11-11

- 新增本地界面、SQLite版本台账、提案/独立审批/冲突/撤销/发布、JSON/Parquet、本地D5只读审计与EN Page/RPC桥接。
- 独立复审修正事件null、未知库存、截止日、撤销入口和Host校验。
- 真实D5审计保留236条拒收；未伪装为全量成功，未改生产或现有预测结果。
