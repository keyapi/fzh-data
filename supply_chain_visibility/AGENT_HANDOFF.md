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

**必须记住的口径**：工序进度取**第一道工序**完成量、**不跨工序求和**；`WO.status/produced_qty` **不可信**；
`Closed ≠ 已发完`；出库按 `item_code` 匹配、退货行负数**净额抵扣**；EN 的 `po_no` 不是客户 PO。

## 3. 已落地产物（`key_test/`，既有表单/报表已生产部署；2026-10-27 同步 `c34fa53`）

生产发布与后续修复见 `key_test/AGENT_HANDOFF.md` §13–14。**2026-10-27** 已按用户授权把生产 `key_test` 同步到
`c34fa53`（PR #2：新增过滤 + Supply Timeline），并完成 `migrate` + `clear-cache` + `bench restart`；
冒烟通过。新增功能以本次生产部署为准；详见 `JACK_QA.md` 的 `P0-PROD-DEPLOY-2026-10-27`。

| Stage | 产物 | 部署 |
|---|---|---|
| 1 嵌入单据 | `key_test/so_chain.py`（whitelist 方法）+ 追加进 `key_test/public/js/sales_order.js` | 测试机 ✅ / 生产 ✅ |
| 2 原生报表 | `key_test/key_test/report/so_chain_overview/` + `supply_timeline/`（Script Report） | 测试机 ✅ / 生产 ✅ |
| 3 独立屏 | 仅设计 | 未做 |

**部署/回滚/移植步骤**：见 [key_test/AGENT_HANDOFF.md](key_test/AGENT_HANDOFF.md)。

## 4. 边界

- 只覆盖**阶段 0–3**。头程/海运/国外仓（阶段 4–8）外置（钉钉表 / 同事「智美通大屏」，代码未共享），**暂缓接入**。
- **物料需求 / 采购订单 / 采购入库**：EN 侧基本空白，**先记录不做**。
- 呈现形式**建议路线**（嵌入单据 → 原生 KPI/例外 → 小范围独立屏；AI/MCP 仅内部受监督助手）：
  [docs/research/presentation-forms.md](docs/research/presentation-forms.md)。

## 5. 维护约定

- **事实地图要持续更新**：一旦在 EN 上发现新的单据/在用状态（尤其「建了没用」那类），改 `docs/reference/en-supply-chain-map.md` 并记 `docs/log.md`。
- 本子项目文档遵守 OKF v0.1；改动后跑 `uv run python scripts/update_index.py`。
