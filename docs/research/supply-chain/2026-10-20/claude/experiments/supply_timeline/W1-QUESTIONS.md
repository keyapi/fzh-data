# W1 问题清单（首轮存档）

> **状态：Q01–Q08 已由 `docs/jack-w1-channel` 的 `JACK_QA.md`（2026-10-26）答复。**
> 当前口径以 `JACK_ENTRY.md` / `JACK_QA.md` 为准；以下仅保留首轮问题原文，不再作为当前结论。
> 公开仓库不放行级 CSV；只引用聚合计数、字段与代码路径。

---

## [W1-Q01] 2026-10-26

**问题**：SC14 `contract.py` 的 `STAGES` 仍是 5 个原始阶段，没有 spec §1.2 要求新增的 `partially_received` 和 `unknown`。如果 W1 按 spec 输出这两个阶段，`validate_w1` 会报 `E_STAGE`；如果不输出，SC04 基线里的 1 张部分签收 + 1 张状态未知只能留在 `exceptions.csv`，无法进正式 supply 表。

**证据**：
- `docs/jack-w1-channel/.../2026-10-23-sc14-spec.md` §1.2：“必须补两个状态”。
- `experiments/sc14/contract.py`：`STAGES = ("on_hand", "po_open", "in_production", "shipped_in_transit", "received")`。
- 本地 `sc14/test_contract.py` 16/16；当前 W1 样本的 exceptions=0，所以本轮 SC14 仍是 0 error。

**影响**：阶段枚举、SC04 的 partial/unknown 对账、未来 9→Top50 扩展。请确认是更新 `contract.py`，还是要求 W1 把 partial/unknown 只放 `exceptions.csv`。

---

## [W1-Q02] 2026-10-26

**问题**：本机没有 sample10 使用的历史快照：`D:/Work/fzh-order-store/order_store.duckdb`、`D:\Work\库存备份`、`D:\Work\王忠于\成本核算` 均不存在。本轮库存只能取通途实时（**2026-10-26**），而 sample10 的库存快照是 **2026-10-22**；WO/PO/DN 已按 10-20/10-19/10-22 截断。库存差异因此无法逐数对齐。

**证据**：
- `Test-Path D:/Work/...` 均为 False（本机）。
- 本轮 TT0031038 在 DANEEY 的在途为 **496**，sample10 为 **201**；PL 在手 **146** vs sample10 **157**；C/Linen CENTRADE **20** vs **21**。
- 每行已写 `stock_snapshot_live=2026-10-26`、`snapshot_expected.stock=2026-10-22`、`snapshot_mismatch=true`。

**影响**：在手/在途数值、PO 与在途的 `overlap_status`、B_min/B_max。请提供 10-22 的只读 DuckDB/备份（路径 + sha256），或确认接受“实时库存 + 明示 mismatch”的口径。

---

## [W1-Q03] 2026-10-26

**问题**：按 `PK# + 成品码` 推导 WO 物料后，本轮查到 **8 张开放 WO、余 533 个**；sample10 只列了 C/Linen 3 张余 101、CENCord 2 张余 152（合计 253）。多出的 3 张是：
- C/Velvet-White：`WO-26-03110`，余额 100，Not Started，但有 48 张 JC；
- C/Cord-White：`WO-26-03118`，余额 70，Not Started；
- TT0031010：`WO-26-03664`，余额 110，Not Started。

另外 `WO-26-03110` 出现 `produced_qty=0` 但 JC 首工序 `sum_qty=110 > qty=100` 的冲突。

**证据**：
- 本轮 `recon.json → in_production.rows=8 / qty=533`；`W1-RESULTS.md` §3.2。
- sample10 §3：C/Linen 101、CENCord 152；未列上述 3 张。
- 已按 JQ-02：`produced_qty` 只作 estimated remaining，JC 只进 `production_progress`。

**影响**：在产供给、B_min/B_max、sample10 的“在产”名额。请确认这 3 张 WO 是否在 W1 范围；以及 `produced_qty` 与 JC 冲突时以哪个为准（当前保留两者、remaining 用 produced_qty）。

---

## [W1-Q04] 2026-10-26

**问题**：sample10 的 9 SKU 应命中 **7 条开放 PO 行**（TT0031038 91+110、C/Linen 121、TT0312701 480、C/Cord-White 10+102+102）；本轮 `purchaseOrderQuery`（`purchaseDateFrom=2025-01-01`、`purchaseDateTo=2026-10-19 23:59:59`、按 9 个 SKU 查）只返回 **6 条**，缺 C/Cord-White 的 PO021735（102）。

**证据**：
- 本轮 `po_open` 6 行：`PO021705/021716/021717/021727/021733`。
- sample10 §2：C/Cord-White 3 条 PO 共 214，其中 PO021735(102)。
- API 返回 `pageNo/pageSize` 正常（<100 行），不是分页截断。

**影响**：PO 供给、B_min/B_max、C/Cord-White 的“PO·ETA 不确定”样本。请确认该 PO 的 purchaseDate/warehouse 是否落在上述过滤范围内，或 API 是否需要按 `createdDate`/无日期过滤再查一次。

---

## [W1-Q05] 2026-10-26

**问题**：`overlap_status` 目前按 `(sku, warehouse)` 汇总 open_po 与 intransit，完全相等才判 `same_batch_suspected`。实时库存下 TT0031038 的 201 PO vs 496 在途 → `unknown`，因此 PO 进入 B_min；sample10 的 201=201 因库存快照不同无法复现。请确认：
1. 这个按 SKU×仓的相等判定是否就是你们期望的 `same_batch_suspected`；
2. B_min 是否应只排除 `same_batch_suspected` 的 PO（当前做法），B_max 全部保留；
3. 没有 `batch_key` 时是否允许 B_min/B_max 之外再给一个 `dedup_assumed` 单值（当前未给）。

**证据**：本轮 `recon.json → po_overlap_suspected`；B_min 未证 UOM 2,645 / B_max 3,358（差 713）。
**影响**：PO/在途去重和下游 supply 情景。

---

## [W1-Q06] 2026-10-26

**问题**：本轮所有映射的 `identity_confidence` 都是 `derived`，因为本机没有 `sku_item`（3,482 对）/`bom_exploded`。当前按 sample10 的“关联物料”建 9 个 SKU 的成品/皮壳/组件行：
- `CENCord995-DKGrey-97` 输出成品 `KS0001-QDKTR-100-DEEPGREY` + 皮壳 `PK#KS0001-QDKTR-100-DEEPGREY` 两行；
- `TT0312701K0064561` 是 `component`（主体骨架）；
- 其余为 `finished`。

请确认：是否要求用 `sku_item` 把可证映射升级为 `proven`？`PK#` 皮壳行是否只作 `role=cover`、永不 1:1 转成品？组件行是否需要单独 `scope=component`（SC14 只有 in_house/external_fba）。

**证据**：`config/sample_skus.json`；`W1-RESULTS.md` §3.3/§7；本轮 236 行中 `role=cover` 的 in_production 8 行。
**影响**：SKU 粒度、组件行是否进 supply、SC14 的 `E_REQUIRED_NULL` 是否继续为 0。

---

## [W1-Q07] 2026-10-26

**问题**：仓库映射目前是 `tongtool_warehouse_master + assumed_en`：
- `WayfairCG-Cranbury仓` 标 `3pl`，归属未证；
- `FZH-DANEEY-成品仓` / `半成品仓` 在通途主数据 `status=0`（停用），但仍返回库存行；
- CENTRADE/DANEEY 按 3PL 处理；波兰按 own。

请确认这 6 个仓的 `warehouse_scope`、`warehouse_confidence`，以及 3PL 是否应与自有仓分开、不与自有仓合并。

**证据**：`config/warehouse_map.json`；`erp2_basedata_warehousequery` 返回 58 仓；本轮 on_hand 23 个 counted 组合，含 WayfairCG 4 行。
**影响**：仓库维度、handoff 的“多仓不互通”、SC09 的 `supply_own_*` 列。

---

## [W1-Q08] 2026-10-26

**问题**：本轮 `received` 有 28 行，全部是 Shipment 已签收的 `received_evidenced`，`qty=null + qty_status=unknown`；`received_booked=0`（Stock Entry 实收 0）。这与 SC04 的 6 张 received_before_snapshot 是**证据层 vs 记账层**的差异。9 SKU 样本只覆盖其中 1 张（DN-26-00067）；其余 5 张不在样本内。

请确认：
1. `received_evidenced` 数量保持 null 是否可接受；
2. 是否需要在 W1 主表之外单独输出 `received_booked.csv` / `exceptions.csv` 给 SC04 对账；
3. 9 SKU 覆盖 8/39 DN、1,516/4,279 行（6 在途、1 已收、1 未知）是否符合预期。

**证据**：`out/sc04_recon.json`；SC04 重算 39/47/4,279，阶段与 FBA 全部差 0；W1 样本覆盖 8/8/1,516。
**影响**：received 语义、SC04 对账范围、W3 的 supply_confirmed/unknown。

---

## 附：本轮硬指标（供回复引用）

- SC14：**0 error / 136 warning**（68 W_UOM_UNPROVEN + 68 W_UOM_FLAG）；16/16 用例通过。
- SC04 对账：39 DN / 47 号 / 4,279 行 / 5 阶段 / FBA 17——**全部差 0**。
- W1：236 supply 行；B_min（UOM 未证 2,645 / 个 533）；B_max（3,358 / 533）。
