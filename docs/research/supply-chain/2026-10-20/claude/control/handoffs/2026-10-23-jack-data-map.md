---
okf: v0.1
type: Handoff
title: Jack 数据与背景读取地图（W1）
date: 2026-10-23
owner: claude-foreman
channel: docs/jack-w1-channel
---

# Jack 数据与背景读取地图（W1）

> **一句话**：这个分支（`docs/jack-w1-channel`）是 Jack Agent 的**只读背景包**；
> 项目控制面、供应侧证据、映射资产、SC14 验收契约都在这里。
> **行级业务 CSV/JSON 不在公开仓库**，用本机只读 DuckDB / 备份目录；拿不到就标 `source_missing`，不写 0。

## 1. 先读什么（顺序）

1. `AGENTS.md` —— 项目规则：分支/PR、凭证扫描、公开仓库不放业务数据。
2. `docs/research/supply-chain/2026-10-20/claude/control/handoffs/2026-10-23-jack-supply-timeline.md` —— W1–W4 任务书与边界。
3. `.../control/handoffs/2026-10-23-jack-w1-answers.md` —— 七问答复 + 口径修改 + 红线。
4. `.../control/reviews/2026-10-23-jack-sample10.md` —— **当前 9 个冻结 SKU**（不是旧 8+2）。
5. `.../control/reviews/2026-10-23-sc14-spec.md` + `experiments/sc14/` —— 16 条可执行验收契约（五条红线）。
6. `.../control/reviews/2026-10-23-sc04-supply-stage.md` + `2026-10-23-dn-split.md` —— SC04/SC03 已证供应阶段。
7. `.../control/reviews/2026-10-23-map-evidence.md` —— SKU↔EN 物料映射三态、UOM 与证据分级。
8. `.../control/reviews/2026-10-22-eta-cover-uom-evidence.md` —— ETA/Cover/UOM 缺证现状。
9. `.../control/reviews/2026-10-23-sc09-trial-pack-v1-frozen.md` —— 下游 23 列试用包怎么消费 supply 列。
10. `.../control/PROJECT_BOARD.md` + `DECISIONS.md` —— 当前边界、D16/D17/D33/D35 等决策。
11. `experiments/sc13/` —— W2 交期/运输方式配置的消费端契约（示例参数是 assumed，不是业务批准值）。

> 完整清单见同目录 `2026-10-23-jack-reading-list.md`。

## 2. 本机只读 DuckDB

路径：`D:/Work/fzh-order-store/order_store.duckdb`（**只能 `read_only=True`**）。

| 表 | 行数/规模 | 关键列 | 能回答什么 | 不能怎么用 |
|---|---:|---|---|---|
| `stock_latest` | 当前快照 | `warehouse, sku, available, intransit, waiting_shipment, defects` | 每个 SKU×仓的最新在手/在途/待发 | 点状快照，不证连续；多仓不互通 |
| `stock_history` | 15,820 行 | `snapshot_date, run_id, goods_sku, warehouse_name, available, intransit, batch_complete, stockout_observed, uom_basis` | 3 天日快照；在途→可用的日变动 | 只有 3 天，不能做删失校正；不能定日内断货 |
| `tongtool_po` | 524 行（未结 248） | `ponum, goods_sku, warehouse, quantity, in_quantity, open_qty, status, purchase_date, will_arrive_date, supplier_code` | PO 行、未结量、下单日 | **`will_arrive_date` 全空**；状态码无字典；不能推 ETA |
| `po_open_latest` / `tongtool_po_open` | 180 行 | `sku, warehouse, on_order` | 未结 PO 的聚合便利表 | 不是行级证据；不能替代 `tongtool_po` |
| `sku_item` | 3,482 对 | `sku, item_code, ship_type` | 通途码 ↔ EN 物料（多对一） | 以皮壳为主；不覆盖组件（PK#/ND#） |
| `sku_map` | 3,482 对 | `item_code, tongtool_sku` | 反向查 | 与 `sku_item` 同源，不是独立证据 |
| `bom_exploded` | 22,510 行 | `root, node, level, qty_per_unit` | 组件→成品归属与用量 | 组件**没有自己的通途码**；不能 1:1 当成品 |
| `item_attr` | 15,230 行 | `item, item_name, item_group, moq, min_pack, qty_per_outer, lead_days, safety_stock` | MOQ/装箱/提前期 | `lead_days` 3–30 天，不是端到端交期 |
| `warehouse_dim` | 58 行 | `warehouse_name, status` | 仓库主数据候选 | 需与通途/EN/财务三处对账 |
| `warehouse_map` | 26 行 | `gs_warehouse, current_warehouse, class` | 仓库映射参考 | 不是全量权威；3PL 归属未证 |
| `three_pl_stock` | 98 行 | `warehouse, sku, item_code, ship_type, available, intransit` | 3PL 库存快照 | 归属/可用性未证 |
| `en_orders` | 订单级 | `order_id, sale_date, despatch_date, channel, account, warehouse, order_status, source, month` | 需求背景 | **无行数量**；不能当供给 |
| `stock_run` / `stock_history_run` | 3 个 run | `run_id, snapshot_date, manifest_complete, scope_complete, run_complete, sealed, ...` | 批次完整性与可复现性 | 不能用不完整批次下结论 |

只读查询示例：

```python
import duckdb
con = duckdb.connect("D:/Work/fzh-order-store/order_store.duckdb", read_only=True)
rows = con.execute("""
  select sku, warehouse, available, intransit, waiting_shipment
  from stock_latest
  where sku = ?
""", ["TT0031038K0062927"]).fetchall()
```

## 3. 每日库存备份

- 路径：`D:\Work\库存备份\YYYY-MM-DD\warehouse=<id>_<name>.jsonl` + `manifest.json`。
- 时间：每天 **05:17**；14 个启用仓；完整日约 **5,314 行**。
- 现状：10-20 不完整（1 仓 URLError 10060，400 行部分数据，`complete=false`）；
  10-21、10-22 完整（5,314 行，14/14 仓）。
- 用法：先看 `manifest.json.complete` 与每仓 `complete`；不完整批次只能做局部，不能当全量。
- 注意：空仓是有效结果，不写 0；每日快照不能定位日内断货。

## 4. EN 侧已证证据（只读）

| 证据 | 路径/commit | 证明了什么 | 边界 |
|---|---|---|---|
| SC03 Shipment | `control/reviews/2026-10-23-dn-split.md`（`59c4e5ec`） | EN Shipment 11 态 + ETA + 轨迹；47/47 单号命中；按 DN-item-UOM-role 输出向量 | `credited_qty` 未验证，不能当入库数量 |
| SC04 供应阶段 | `control/reviews/2026-10-23-sc04-supply-stage.md`（`228bef77`） | 39 张 DN 各归一段：6 已收 / 30 在途 / 1 部分 / 1 日期未知 / 1 状态未知；47 号/39 DN/4,279 行差额为零 | 只到 DN 级；PO/WO 本地无证据，明确不假设 |
| DN 桥 | `control/reviews/2026-10-23-dn-bridge.md`（`fc0c9562`） | DN 状态接入 | 逐笔 ETA/在途关系未全证 |
| G1B DN/WO/JC/SE | `experiments/g1_contract/g1b_results.md`、`g1b_dn_wo_jc_se.md` | 105 JC 组/516 工序行；SE 覆盖；`produced_qty` 不可当完工账 | 仅窄样本（5–10 SKU），不外推 |
| 映射三态 | `control/reviews/2026-10-23-map-evidence.md` | 39 DN 的 282 码：58 直接 / 217 可推导 / 7 未映射；0/39 数量级证据 | 组件不是独立 SKU；UOM 未证 |
| 生产只读闸门 | `experiments/g1_contract/prod_budget.md` | 每批 300 请求 / 32 MiB / 900 秒；403 原子停机 | 不等于可以随意扫全表 |

## 5. 冻结产物（不要就地改）

| 产物 | 版本/哈希 | 说明 |
|---|---|---|
| SC09 条件试用包 | `M1-TRIAL-v1`，行表 sha `0a9371dc…`，2,309 行/23 列 | 条件 2,058 + HOLD 251；非采购批准；跨 UOM 不可合计 |
| 9 SKU 样本 | `2026-10-23-jack-sample10.md`，9 填充 + 1 缺额 | 冻结后不换样；缺额是“PO·ETA 可验证”本地无样本 |
| 映射证据 | `map_evidence.json` / 三份 CSV（本地） | 行级数据留本地，不提交 |
| 输入快照 | `plan.json`、`ranking.json`、`wo_dn_coverage.json`、DuckDB sha | 见样本冻结报告 §7 |

## 6. 明确没有的东西（不要猜）

| 缺口 | 事实 | 正确做法 |
|---|---|---|
| PO ETA | `tongtool_po` 未结 248 行，`will_arrive_date` 非空 **0 行**；未结行 `in_quantity>0` 0 行 | `date_confidence=unknown`；W2 假设单列 `assumed` |
| WO 完工日 | 样本 WO 的 `planned_end_date` 全空 | `available_date=null`；不推日期 |
| WO 产出 | `Work Order.produced_qty` 有失真（10 SKU 里 2 张） | 只作 `estimated`；JC `sum_qty` 作 progress |
| UOM | 个/套并存，39% 是套；库存 `uom_basis='unknown'` | 不跨单位合计；`uom_proven=false` |
| MOQ/装箱 | `item_attr` 有字段，但未逐 SKU 验证 | 标 `policy_unverified` |
| 需求上下界 | 预测是探索性材料，非验收结论 | 需求侧由分析/业务给；W1 不输出采购量 |
| PO↔DN/Shipment 键 | WO↔PO 0/214；DN↔WO 0/507 | 不假定同批；出 `overlap_status` 两情景 |

## 7. 共享边界

- `keyapi/fzh-data` 是 **PUBLIC**：**行级业务 CSV/JSON 不提交**；只提交文档、代码、聚合计数、schema。
- 需要我方本地快照时：给 **只读路径 + schema + sha256**，不要贴行内容。
- 生产只读：每批 **300 请求 / 32 MiB / 900 秒**；不写、不下单、不改主数据、不合并 PR。
- 时点漂移：库存 10-22 / WO 10-20 / PO 10-19；每行带 `as_of_date` + `snapshot_id`，不要假装同步。

## 8. 沟通

- 分支：`docs/jack-w1-channel`；PR 评论用 `[W1-Qxx]` / `[W1-Axx]`。
- 本机快线程：`D:/Work/fzh-order-store/jack_thread/`（`jack_questions.md` / `foreman_answers.md`）。
- 行级/敏感问题：私有仓库 `keyapi/tongtool_integration` issue（需 Jack 账号有权限）。
- 业务决策（服务水平、预算、交期假设、采购授权）仍由用户拍板；技术口径可直接对话。
