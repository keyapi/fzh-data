# E 已有供给线复核结果（2026-11-11）

> 复核人：Orca/Cursor Grok 4.7 256K High（只读）+ 本机直连通途 API 实测补充。

## 结论

**不能把 E 当作“SKU × 客户 × 节点”的事实源。** 当前 E 只支撑“产品 × 仓池（波兰/美东/美中）”的补货动作，节点是断的、客户维度不存在；要用它回答“某 SKU 给某客户在哪个节点”，必须先补数据。

## P1

1. **节点断裂**
   - SO：只加了 3 张波兰 SO，且并入 `stock_wait`。
   - DN：没有数量，只参与 ETA。
   - 在途：用 `intransit`。
   - 到仓可用：用 C 的 `可发供给`，不是 `en_stock.available`。
   - 次品/退货：`defects` 未读；波兰/美东退货仓不在镜像里。
   - 在制（WIP）：没有。
   - PO：11-05 的未收；`intransit>0` 时整段不加，否则再扣 `waiting_shipment`。
   - CG：`cg_buffer_credit` 与 `可调拨` 取最大值，不求和。

2. **波兰口径（已更正）**
   - 供给线只认 **`波兰-FZHPoland-covers`** 一个仓；`FZHPoland-finished` 已弃用，不属于 E 范围（仓内 22 SKU / 614 件残量仅记录备用）。
   - `en_stock_20261110.parquet` 与 C 的 `2_库存事实层` 都是 5,336 行，波兰只有 covers 仓；这与口径一致。
   - covers 的 10.1M 中 `Buttonkit-pl` 占 9,999,866、`Cotton-EU` 占 99,953，均未进可发供给；真实可售成品约 2,822 件。
   - 真正的缺口不是“仓不在镜像”，而是**波兰外部订单的扣减没有进入 E**：这些订单不在通途，靠彭建每周手工“其他出库”扣减。

3. **重复计数风险**
   - 当前 3 张 SO 没有与待发叠双（波兰 `waiting_shipment` 仅 3）。
   - `inbound = intransit + waiting + SO + po_extra`；PO 已避开在途并扣过待发。
   - 但规则仍是相加：**下一张已经进入 `waiting_shipment` 的 SO 会被算两次**。

## P2

4. **未映射仓有量**：`多渠道仓库` 99,899（其中 FBA-duo 99,557）、`大件云仓` 7,082、`星链海外仓` 待发 2；`京东波兰仓` 不在镜像。这些都没有进入波兰/美东/美中池。
5. **键粒度不够**：D6 键是 `product_id + pool + physical_form + UOM`，没有通途 SKU、仓名、客户、节点列；`stock_wait` 把 EN 待发和 SO 混在一起。做 SKU×客户×节点，还缺 DN 数量、次品、在制。
6. **修复清单（只围绕 covers 仓与波兰外部订单）**
   - 按**单号**互斥：SO / DN / waiting_shipment / PO，禁止再把 SO 加进 `stock_wait`。
   - 把波兰外部订单（`Poland Order`）作为**独立出库事实**接进库存：每周生成“其他出库”草稿或直接从订单事实扣减，避免人手漏扣/晚扣。
   - `defects` 与在制单列，**不进可发供给**。
   - 输出保留 `sku + warehouse_name + customer + node`；聚合到产品池只能作为视图。

## 本机补充证据（直连通途 API，非 MCP）

- `stocksQuery` 过滤参数是 `warehouseName`（`warehouseId` 被忽略）。
- `stocksChangeDetailQuery` 可查最近 7 天，含操作人/凭证类型；波兰皮壳仓 11/05–11/10 有 694 条变动，其中 11/05 彭建一张“其他出库”凭证扣 110 SKU / −195 件。
- `FZHPoland-finished` 近 7 天 0 条变动，印证该仓已停用但仍有残量。
