# E 已有供给线：给 Codex 的设计与实施任务（2026-11-11）

## 最终目标（唯一标准）

对任意 **SKU × 客户（波兰 / 美东 USNJ / 美中 USTX）**，能回答“这条已有供给线 E 上每个节点现在是什么状态、数量多少、什么时候到”，直接支撑补货决策：**是否下单、是否催单、什么时候下/催**。

不是再产出一版解释性 Excel，而是把 E 做成可复算、可对账、不重复计数的数据层。

## 已知事实（都已核实，不要重新怀疑）

1. 波兰只有 **一个仓**：`波兰-FZHPoland-covers`（通途仓名）。成品仓 `FZHPoland-finished` 已弃用（仅 614 件残量），退货仓/京东波兰仓不在范围。
2. 波兰独立账号订单（Allegro/Empik 等）**不走通途订单**；波兰每周报给彭建（之前王弦），彭建在通途手工“其他出库/报损”扣库存。近 7 天可见：2026-11-05 一张“其他出库”凭证 110 SKU / −195 件。
3. 每天的通途库存备份在：
   - `D:/Work/fzh-order-store/wx_inventory_history.duckdb`（schema `wx_inventory`，`observations`，2026-06-09..10-19，38 个日期）
   - `D:/Work/fzh-order-store/pengjian_inventory_history.duckdb`（schema `pengjian_inventory`，`daily_snapshot`，2026-04-14..10-09，22 个日期）
   - 2026-07-31 前 `warehouse_raw='FZHPoland-covers'`；08-24 起为 `warehouse_raw='波兰仓'`（consolidated，用户确认是 covers 口径）。
4. EN 侧每天抓取的通途库存快照：`D:/Work/fzh-order-store/analysis/en_stock_20261110.parquet`，列 `stock_key, warehouse_name, sku, available, intransit, waiting_shipment, defects, snapshot_at`。
5. C 的可发供给：`D:/Work/fzh-order-store/analysis/C-refresh-20261110/通途库存_A337_v15_refresh_2026-11-10.xlsx` 的 `4_可发供给`（波兰 809 键 / 11,529 件，是皮壳+海绵+骨架拆解合成）。
6. 通途直连 API（可用，不用 MCP）：`https://open.tongtool.com/api-service`，凭据 `D:/Work/赛狐/Cursor/tongtool_api/.env`；`stocksQuery` 用 `warehouseName` 过滤；`stocksChangeDetailQuery` 只能 7 天；签名方式见 `D:/Work/private/codex-tongtool-fba-sync-20261012/tongtool_integration/api/client.py`。
7. 现有 D6：`C:/Users/zhang/.codex/worktrees/supply-position-consumer/owner-restatement/scripts/d6_top50_sandbox_v6_15_20261107.py`，供给列 `C可发供给 / en_stock在途+待发 / PO追加(去重) / CG可调拨抵扣 / SO已下`。
8. 3 张波兰 SO：`D:/Work/fzh-order-store/analysis/so_20261110_20261111.csv` + `so_items_20261110_20261111.csv`（3,674 件），状态 To Deliver and Bill，尚未交付；SO↔DN 关联不可靠。

## 你要做的事

### 第一步：设计（先写 `E_DESIGN.md`，不要先写代码）
给出 E 的节点定义与去重规则，至少覆盖：

- 下单未发（SO 已建、未 DN）
- DN 已建未发 / 已发运在途（含 ETA）
- 到仓可用（covers 仓 available）
- 波兰外部订单已售未扣（独立账号）
- PO 未收（含 ETA）
- CG 可调拨（仅 eligible/非 stale）
- 次品/退货（不进可发，但要在视图里可见）
- 在制（WIP，若数据可得）

必须回答：
1. 每个节点的数量口径（available / waiting_shipment / intransit / defects 哪一列，单位是个还是套）。
2. **互斥规则**：同一批货在 SO、DN、waiting_shipment、PO、在途之间怎么只算一次；给单号级去重键。
3. 客户归属：warehouse→customer 的映射（只列实际存在的仓），以及混仓/多渠道仓怎么处理。
4. 时间：每个节点的 ETA 来源与不确定性；没有 ETA 时怎么标。
5. 输出 schema：至少 `sku, warehouse, customer, node, qty, eta, source, as_of, voucher_no`；产品池聚合只能是视图。

### 第二步：实施（如果设计自洽，就直接写代码）
在 worktree 里写一个最小可跑的脚本（Python，`uv run python`），从第 3/4/5/8 条的数据生成节点级表：
- `D:/Work/fzh-order-store/analysis/E_nodes_20261111.parquet`（或 csv）
- 一个自检报告：每个节点行数/数量、重复计数检查、与 C 的 11,529 对差、与 EN 快照对差。
- 不要写 EN/通途；只读源数据。

### 第三步：给结论
报告里必须明确：
- 这个 E 现在能不能支撑“是否下单/是否催单/何时”——能/有条件/不能，缺哪几项。
- 剩余数据缺口和需要用户/业务拍板的事项（最多 5 条）。

## 约束
- 不改源数据；不写生产系统；不用通途 MCP。
- 所有数字可复算，不确定就标未知。
- 如果设计上有两种合理解法，列出取舍，不要替用户拍板。
