---
type: Spec
title: E 已有供给节点账设计
date: 2026-11-11
status: implementation-authorized
---

# E 已有供给节点账

## 目标与边界

按原始 SKU × 实际仓 × 客户 × 节点回答数量、凭证和到货时间。源文件只读；DuckDB 用 `read_only=True`；不访问网络、EN 或通途 MCP。不改 C、库存、订单。产品池只能是派生视图。当前源不完整，不能把成功产表等同于可以自动下单。

已读 `E_CODEX_BRIEF_20261111.md`，接受其中已核实事实。3 张 SO 的明细与汇总都是 3,674，不是两份供应；SO 未交付，不能由此推断已开工、DN 已建或已发船。波兰 covers 是唯一在范围内的仓；finished 已弃用，614 残量不纳入。

## 节点、单位与时间

| node | 事实与数量 | 时间 / 本轮资格 |
|---|---|---|
| available | EN `available` 原始仓库存，保留 C 的逐 SKU 单位证据 | `snapshot_at` 是观测时间，不是到货时间；原始库存不是 C 合成供给 |
| intransit_observed | EN `intransit`，无批次/运单 | ETA=null；未完成批次互斥，不能与 SO/PO 相加 |
| waiting_observed | EN `waiting_shipment`，字段方向/单号未随导出提供 | 不冒充 DN 待发或新增入库；ETA=null，待补字段语义 |
| so_unshipped | SO 导出 item_code 原样保留，未交付承诺 | `delivery_date` 只存 promised_at，不称确认 ETA；无真实 SO Item.name 则显式标 export_row，不冒造单据行 |
| dn_unshipped / shipped_in_transit | 需 DN Item、装运/运单与实际发运证明 | 本轮没有所需源，覆盖表记 unknown，不造数量 |
| po_open | 采购行净未收；不是销售 SO 的另一个名称 | 需采购行/发运/收货连接；本轮未作为输入，不写 0 |
| external_sold_unposted | 波兰独立账号已售未扣，是负向承诺/负债 | 本轮缺逐单与库存凭证匹配，qty=null；已记账 −195 不能再扣一遍 |
| cg_transfer | 必须 eligible、非 stale、已获可调拨证明、实际目的仓 | 当前 CG 镜像不能证明调拨资格，保留观察；不把 CG 批量归 USNJ/USTX |
| defects / returns_observation | EN `defects`、实际退货仓的库存 | 不进可发；无覆盖的波兰退货仓不写 0 |
| wip | 工单首工序证据及对应 SO Item 的互斥余额 | 当前无源；SO 或 DN 状态不能替代在制事实 |

原始数量不自动当成 finished pieces。EN 单位从 C 事实行随行携带，默认个/未证单位保持未证；套与个不相加；`pieces_per_unit` 不推断。SO 3,674 件采用简报已核实的数量单位，仍保留导出缺少原始 UOM/换算字段的说明。未知数值/日期为 null，显式 0 保留。

## 单号级互斥与数量守恒

1. 权威源键为 `source_system + voucher_type + voucher_no + voucher_line_id`；同一键内容冲突报错。文件观测键为 `源文件 SHA + sheet/CSV行 + field`，与真实单据键分列；快照不伪造 voucher_no。
2. 跨系统只以已证 `SO Item.name → DN Item → shipment allocation → receipt item` 或 `PO Item → shipment allocation → receipt item` 连接。不以 SKU 相同、数量接近、时间邻近、SO.po_no 或全局 max/min 充当去重证据。
3. 互斥额度键为 `root_order_line + allocation_id + 原SKU + 目的仓 + UOM`。部分发运必须拆额度：未发余额、已发未收余额、已收余额精确合计订单净量；同额度跨阶段保留末端余额，来源作为 evidence；合法不同批次均保留。已收部分由 available 接管，收货事件不再加库存。
4. DN 建单不等于实际发运；waiting/intransit 快照没有额度键，只作余额校验。不能把 SO + DN + waiting + intransit + PO 汇总相加。
5. 本轮 SO、EN 在途、待发均保留原量，但 `additive_supply=false`，`counted_qty=null`，原因 `document_lineage_unproven`。不能用 null→0 掩盖未知，也不因保守阻断而声称不存在供给。
6. SO 明细 88 行是权威输入；71 行 product 汇总只作独立对账。每个导出行保留 observation id；缺真实行 ID 不声称已实现生产级单据去重。
7. 复用 `supply_netting.facts.StageBalance/validate_stage_balances` 的数量与阶段校验；实证不足的记录只保留 observation，不抬升为已证 tranche。

## 客户与实际仓

当前 EN 中确认：`波兰-FZHPoland-covers→波兰`、`美东-CENTRADE→USNJ`、`美中-FZH-DANEEY→USTX`。实际存在的 `美中-FZH-DANEEY-退货产品仓` 只归退货观察。`多渠道仓库/大件云仓/星链海外仓` 客户未知；三个 WayfairCG 仓均保持 CG 观察，不能凭地理归公司。

历史 `FZHPoland-covers` 及已确认 consolidated `波兰仓` 只在历史视图映射 covers；`CENTRADE/美东仓`、`美中仓` 与早期分形态子仓保留原仓名、映射依据与历史角色，不将退货子仓并入可售。SO 的 `成品仓 - FZH/半成品仓 - FZH` 是工厂来源仓，客户取导出 pool；另外存目的 covers 仓，绝不把工厂仓当海外现货仓。

## 输出与防误消费

`E_nodes_20261111.parquet` 是源事实长表：

`node_id, sku, product_id, warehouse, destination_warehouse, customer, node, qty, uom, uom_status, eta, eta_status, promised_at, source, source_row, source_record_id, source_as_of, as_of, voucher_no, voucher_line_id, voucher_line_status, overlap_group, additive_supply, counted_qty, counting_reason, c_bucket, physical_form`。

- `warehouse` 始终是实际观测仓，SO 工厂仓与目的仓分列。
- null counted_qty 表示无法证明可叠加，不是零供应。源总量只能按 source/node/UOM 核账，不能跨节点总和。
- `E_available_view_20261111.parquet` 直接保留 C 的 product×pool×form×UOM 及可发供给、proof、门禁；不是另一份节点库存，禁止与 raw available 相加。
- `E_inventory_history_20261111.parquet` 保留两个只读库的历史 available 证据，按源/日期/仓/UOM 隔离，绝不加入当前库存；两个库同日重叠不相加，不从库存下降猜销量或外部订单。
- `E_coverage_20261111.parquet` 各客户×节点覆盖、缺源原因及 unknown qty；缺节点不靠造零行补齐。
- `E_reconciliation_20261111.parquet` 逐 EN stock_key 与 C 事实层原量对差、C 视图重放、两份 SO 对差；以及 JSON/Markdown 汇总、SHA manifest。

## 两种解法及取舍

本轮实现有证据门禁的节点账：保留全部原量、阻断未证叠加，可复算但暂不提供完整已有供应总额。另一方案是在缺单号时按 SKU 聚合抵扣 SO/PO/waiting/intransit：会得到单一数字，却可能错扣不同批次或重复计数；不实施，不替业务把数量估计当事实。客户/ETA 不明时也不自动分摊。

## 验收与实现顺序

1. 先写回归测试：SO 两导出不重复；同 stock_key 冲突拒绝；单号相同的不同明细不得误删；无 ETA 不用承诺日代替；套/个不合计；未知覆盖不填零；同仓/同 SKU 历史多源不加入当前库存。
2. 实现本地读取与节点构建；DuckDB 只读且所有源哈希前后一致；缺列/非有限数量/未来快照报错，历史时点明确。
3. EN 每一行×4数量字段可追溯；C 事实层逐 SKU 原始 available 对差为 0。波兰 C 867 视图行中 809 数量非空、58 为未知，已知合计 11,529，重放差 0；不把 58 空量算 0。
4. SO 明细/汇总按汇总声明的 SO 集合×product_id×pool 对差为 0，总量 3,674；拼接单号不是新凭证，每个明细只允许归入一组汇总，不均分/复制数量。所有无关联未来量 netting 阻断，重复观察键为 0。
5. 自检报告分别列节点行数/已知量/未知行/排除原因，所有源输入去向与历史源日期/行数、C 排除桶及转换前后差异可追溯。结论最多列 5 项缺口/业务选择。

官方语义参考：[ERPNext DN 可部分交付](https://docs.frappe.io/erpnext/delivery-note)、[DuckDB 只读连接](https://duckdb.org/docs/current/clients/python/dbapi)。本地判定以项目数据和用户已核实事实为准。

## 运行与本次验证

```powershell
uv run python -m supply_netting.e_nodes --as-of 2026-11-11T23:59:59+08:00
uv run python -m pytest supply_netting/tests/test_e_nodes.py -q
```

`as_of` 是报告截止时点，不冒充源刷新时间。默认源在 `D:/Work/fzh-order-store`，可用 `--data-root` 与 `--output-dir` 重放同 schema 的本地快照；没有远程读取功能。默认 `--expected-c-poland 11529` 是本次验收基准，新快照须显式变更基准，不能静默通过旧基线。

2026-11-11 实跑：当前节点 21,432，历史 239,022，EN 原始库存 5,336 行对差 0；SO 88 行/3,674 只登记一次。C 波兰 867 行（809 已知、58 未知），显示总量 11,529；分单位为 11,521 个与 8 套，不能把总显示量当作 11,529 个。6 个输入前后 SHA 不变；9 个产物回读/哈希验证通过。全模块 153 个测试通过，其中 E 契约 13 个。
