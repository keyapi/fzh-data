---
okf: v0.1
type: Reference
title: 通途 PO 入库时间与库存快照对账
date: 2026-10-26
module: tongtool_api
tags: [purchase-stock, receipt, snapshot, reconciliation]
---

# PO Receipt Time

## Verified Interface

只读工具 `erp2_purchase_purchasestockquery`：必填 `warehousingDateFrom`、`warehousingDateTo`；可选 `purchaseOrderCode`、`pageNo`、`pageSize`。
实测按已知 PO 与其到货附近的小日期窗口查询成功，返回 2 行；近两日和近一周查询均成功但返回空页，不能把空窗口解释为接口不存在或所有历史均无入库。
原始业务响应只保存在仓库外临时文件，不提交公开仓库。

| 字段 | 已观察含义与限制 |
|---|---|
| purchaseDate / createdDate | PO 查询头部的采购、创建时间，样本精确到分钟 |
| purchaseArrivalDate | PO 头部到货时间，样本精确到分钟；不等同于逐条实际入库时间 |
| warehousingDate | 入库查询中的时间，样本精确到秒；时间字符串未带时区，适配器显式标记来源时区待确认 |
| purchaseOrderCode / purchaseOrderId | 采购单关联键 |
| goodsDetailId / sku | 货品标识 |
| warehouseId / warehouseName | 入库仓库 |
| warehousingNum | 适配器名 reported_receipt_quantity，保留源字段名；不可把 quantity、金额或单价当成本次入库量 |
| quantity | 独立保留为订单数量来源，不混到 warehousingNum |
| receipt_id / line_id / uom | 本次响应未提供；不得伪造稳定事件 ID 或静默猜单位 |

EN 的 Delivery Note 按钮将 logistic_number 放进 PO externalNumber，创建成功后写回 custom_tongtool_purchase_order 与 custom_tongtool_po_created_on。
后者是 EN 创建/写回时间，不是入库时间；手动 PO 不保证具有上述关联，不因无 EN 按钮记录就排除。

## 2026-10-26 实测补充

- `PO021694`（全收）：入库 26 行，事件 `2026-07-27 22:36:06–08`，PO 头 `purchaseArrivalDate=22:35`；26 行与 PO 行 1:1，`warehousingNum == quantity`。
- `PO021704`（50 行）：PO 头 `purchaseArrivalDate=2026-10-14 07:22`，但实际分两批——**38 行 10-14、12 行 10-19**。按头日期 ±1.5 天采集只返回 38 行（漏 24%）；放宽到 09-01–10-26 才返回 50 行。
- 10-01–10-26 全量小样本：102 行 / 8 张 PO / 102 个 `(PO, SKU)`；没有同一 PO×SKU 的多条入库行。部分/多批入库与 `warehousingNum` 的“本次量 vs 累计量”仍未证。
- 响应仍无稳定 `receipt_id/line_id/uom`；`warehousingDate` 与头部时间内部一致（差 1–3 分钟），但绝对时区未证。
- 重叠窗口采集实测（09-01–10-26，14 天窗 / 2 天重叠）：**166 输入 → 150 唯一 + 16 重叠重复**；12 张 PO / 113 SKU；无截断；`possible_duplicate=0`。
- 接入对账（`supply_chain_visibility/receipt_coverage.py`）：150 条唯一行全部为 `unknown`（`missing_stable_id`），150 行无 UOM、时间无时区；`not_collected=0`。未自动抵扣在途。

**采集要求**：不能只用 PO 头日期定窗；使用 `tongtool_api/receipt_collector.py` 的重叠窗口（默认 7 天窗 / 1 天重叠）+ 仓库外缓存，并把窗口外行交给对账标 `not_collected`，避免静默漏计。

## Time Reconciliation

05:17 是当前库存批次开始时刻，而不是所有仓库的精确读取时刻；有每仓采集窗口时优先使用，没有时采用整个批次开始/完成区间。

| 事件位置 | 处理 |
|---|---|
| 严格早于采集开始 | 标记 before；可能已反映在库存，但仍需确认入库生效/接口延迟语义 |
| 严格晚于采集完成 | 标记 after，仅作 receipt_delta_candidate |
| 等于边界或处于采集区间 | 标记 uncertain |
| 时间、身份、单位或仓库窗口缺失 | 原行保留为 unknown，不填 0 |

例：09:00 已入库、库存仍是 05:17 批次，但 PO 当前剩余量已减少，会产生漏计；把完整 PO 与包含入库的库存直接相加，又会重复计入。
因此，不能混用库存批次时点与当前 PO 剩余量后宣称数量完整。
不直接把 receipt 候选增量加到 available：库存可用桶还受出库、占用/释放、退货及手工调整影响。
生产已有 stock_change_sync.py 与 stock_change.parquet，含 operate_time、凭证类型/号和各库存桶增量，应复用作辅助核对，但不把其全部事件当作采购入库。

## Implementation

- `tongtool_api/purchase_receipts.py`：注入已有 MCP caller 的只读适配器；有界分页、13 秒相邻请求节流、严格错误与分页回显检查、显式 truncated 标志；无重试风暴。节流只约束本调用方，商户多 App 仍共享 5 次/分钟。
- `tongtool_api/receipt_collector.py`：重叠窗口 + 仓库外缓存 + 显式弱键；跨窗口重复标 `overlap_duplicate`，同窗口重复保留并标 `possible_duplicate`；不伪造稳定 ID/UOM。
- `tongtool_api/collect_receipts_cli.py`：有界采集入口（`--from/--to/--window-days/--overlap-days/--max-pages/--cache-dir/--out/--coverage-out`）；截断时退出码 2，需提高 `--max-pages` 或加 `--allow-truncated`。
- `supply_chain_visibility/receipt_coverage.py`：`CollectionResult` → `ReceiptEvent` → `reconcile_receipts`；输出聚合的 coverage / unknown / duplicate 报告，不含行级数量。
- `supply_chain_visibility/receipt_bridge.py`：PO 剩余 / 库存快照 / 入库事件的按 SKU×仓×UOM 桥接；输出 before/after/uncertain/unknown_time/not_collected 计数与 flags，不自动调整库存或在途。
- `supply_chain_visibility/overlap_gates.py`：PO/在途同批、DN trace、外部 FBA、未映射、未知 UOM、cover 转换的有序 gate；B_min 只留一侧，B_max 两侧保留。
- `supply_chain_visibility/supply_integration.py`：组装 canonical rows + gates + bridge + 聚合；`report_only()` 只返回聚合/flag，供报表调用，不改变既有报表入口。
- `supply_chain_visibility/receipt_reconciliation.py`：无网络的时间对账核心；强身份重放去重、冲突隔离、按 SKU×仓×单位分开汇总；新增 `not_collected`、`weak_event_key`、`possible_duplicate`/`dedup_assumed` 透传。输入数＝已分类唯一行＋重复行＋冲突行＋未知行＋未采集行。
- 真实响应缺强身份时保持弱身份，不按相同内容去重；不将这个适配器当作已经具备精准自动库存回放的证明。
- 查询窗口按上海业务时区格式化；来源事件字符串本身未带时区，保留 unverified，调用者必须核实来源时区后再送入要求 aware timestamp 的对账核心。
- 单元测试只用合成 fixture；自动通途 PO 入库、调度改点和库存写回不在本次范围。

相关：[原生报表计划](../../../supply_chain_visibility/docs/research/2026-10-26-en-native-report-plan.md)、[供应整合设计](../../../supply_chain_visibility/docs/research/2026-10-26-receipt-supply-integration.md)、[PO API](purchase-orders.md)。
