# supply_chain_visibility — Agent Handoff

> **入口**：先读 [README.md](README.md) 与 [docs/reference/en-supply-chain-map.md](docs/reference/en-supply-chain-map.md)。
> 本子项目 = EN（ERPNext）供应链「下单→出库」的事实地图 + 呈现形式调研 + 已落地的 app 产物。

## 1. 这是什么 / 为什么

绍兴工厂负责人希望把「从下单到出库整条链的信息呈现/查询」做到 **EN 上**（形式未定：报表 / 更友好 UI 都可能）。
本子项目把**事实**摸清、把**形式**调研完、并把前两档**落地到测试机**。

## 2. 事实底盘（别重造）

- **链路主键**：`通途 SKU → Item Customer Detail.ref_code → Sales Order Item.name → {Work Order, Job Card, Delivery Note}`。
  唯一入口文：[EN_API/docs/reference/en-order-to-shipment-chain.md](../EN_API/docs/reference/en-order-to-shipment-chain.md)。
- **已有查询能力**：`EN_API/fulfillment_query.py`（多输入/阶段 0–3/数量对账/齐套/异常，**JSON 为权威输出**）、
  `EN_API/item_shipment_status.py`（单物料引擎，**带 fixture 断言 + 单测，不要整体搬迁**）。
- **EN 全链路实体地图**（含 4 个自定义 app 与「建了没用」的 doctype）：[docs/reference/en-supply-chain-map.md](docs/reference/en-supply-chain-map.md)。
- **自定义 app 拓扑 / 落地链路 / 实测坑**：[docs/reference/en-custom-apps-and-deploy.md](docs/reference/en-custom-apps-and-deploy.md)。

**必须记住的口径**：工序进度取**第一道工序**完成量、**不跨工序求和**；`WO.status` **不能当完工信号**，
但 `produced_qty` **可信**（= 已提交 Manufacture 入库单回写）；`Closed ≠ 已发完`；出库按 `item_code` 匹配、
退货行负数**净额抵扣**；EN 的 `po_no` 不是客户 PO。
「可发」= 入库 + 质检放行 + 可用库存，不能只看工序完成，也不能把 E 的 `instock`（累计入库）当库存。

**新对话必读（2026-11-12 新增）**：

- `docs/solutions/architecture-patterns/en-supply-line-e-replenishment-decision-boundary.md`
  —— E 用于补货/下单决策的边界：`instock` 是累计入库、`inventory/receipt=not_integrated`、
  超发会错抵需求、QC 未放行、Closed 落 stage 3、`partial` 不阻断。
- `docs/solutions/integration-issues/en-so-dn-forwarder-job-status-lookup.md`
  —— SO→DN→`Shipment`→货代 job→`ZMT Shipment Snapshot` 的查询链；**Snapshot 用 `job` 不是 `tracking`**；
  `Shipment.status` 长期 Draft，在途看 `custom_zmt_events` / Snapshot。

## 3. 已落地产物（`key_test/`）

| Stage | 产物 | 部署 |
|---|---|---|
| 1 嵌入单据 | `key_test/so_chain.py`（whitelist 方法）+ 追加进 `key_test/public/js/sales_order.js` | 测试机 ✅、**生产 ✅（2026-11-12 实测 `get_so_chain` 返回 200）** |
| 2 原生报表 | `key_test/key_test__report__so_chain_overview__*`（Script Report） | 测试机 ✅、生产 ✅ |
| 3 独立屏 | 仅设计 | 未做 |

> ⚠️ **仓库快照 ≠ 线上代码**：线上已返回 `shipment_progress`、`all_process_done`、`qc_*`、
> `completion_status`、`production_evidence`、`evidence_conflicts`、`partial/source_status`，
> 仓库里的 `key_test__so_chain.py` 仍是 v4。静态评审前先同步线上源码。

**部署/回滚/移植步骤**：见 [key_test/AGENT_HANDOFF.md](key_test/AGENT_HANDOFF.md)。

## 4. 边界

- 核心仍是**阶段 0–3**；**线上 E 已额外返回 `shipment_progress`**（DN 之后到货代的在途阶段、
  ETA/ATD/ATA/DLVR、冲突标记），但它是**只读展示**，且 `inventory/receipt` 仍是 `not_integrated`。
  不能据此说「E 已覆盖整条供应链」。
- **库存 / 采购在途 / 物料齐套 / lifecycle** 仍未接入；补货决策前必须另取库存与收货数据。
  详见 `docs/solutions/architecture-patterns/en-supply-line-e-replenishment-decision-boundary.md`。
- **物料需求 / 采购订单 / 采购入库**：EN 侧基本空白，**先记录不做**。
- 呈现形式**建议路线**（嵌入单据 → 原生 KPI/例外 → 小范围独立屏；AI/MCP 仅内部受监督助手）：
  [docs/research/presentation-forms.md](docs/research/presentation-forms.md)。
- **预测/库存/交期/分型研究**（先读再动手，别重造）：
  `docs/research/supply-chain/2026-10-20/claude/control/reviews/` 下的
  `2026-10-27-existing-assets-forecast-inventory.md`（已有资产）、
  `2026-10-27-frepple-evaluation.md`（借逻辑不部署）、
  `2026-10-27-sku-segmentation-stockout-promotion.md`（分型/断货/9 月异动）。
- **经验沉淀**：
  `docs/solutions/tooling-decisions/frepple-evaluation-and-borrow-logic.md`（frePPLe 借逻辑不部署）、
  `docs/solutions/workflow-issues/supply-sku-segmentation-and-stockout-evidence.md`（分型/断货口径）。

## 5. 维护约定

- **事实地图要持续更新**：一旦在 EN 上发现新的单据/在用状态（尤其「建了没用」那类），改 `docs/reference/en-supply-chain-map.md` 并记 `docs/log.md`。
- 本子项目文档遵守 OKF v0.1；改动后跑 `uv run python scripts/update_index.py`。
