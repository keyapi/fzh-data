# supply_chain_visibility — EN 供应链可视化与履约查询

> **一句话**：把「从下单到出库」的供应链信息做成 EN（ERPNext）上可查、可看的能力。
> 起因：绍兴工厂负责人希望把整条链的信息呈现/查询做到 EN 上（形式未定）。
> 本子项目 = **事实地图 + 呈现形式调研 + 已落地的 app 产物**。

## 现状（2026-10-13）

| 项 | 状态 | 在哪 |
|---|---|---|
| EN 全链路**事实地图**（含自定义 app） | ✅ 已实测 | [docs/reference/en-supply-chain-map.md](docs/reference/en-supply-chain-map.md) |
| 呈现形式**调研 + 建议路线** | ✅ 已出 | [docs/research/presentation-forms.md](docs/research/presentation-forms.md) |
| **Stage 1**：SO 表单内嵌链条摘要 | ✅ 测试机已部署验证 | [key_test/](key_test/)、[key_test/AGENT_HANDOFF.md](key_test/AGENT_HANDOFF.md) |
| **Stage 2**：原生报表 SO Chain Overview | ✅ 测试机已部署验证 | 同上 |
| **Stage 3**：小范围独立屏 | ⏳ 仅设计 | [key_test/AGENT_HANDOFF.md](key_test/AGENT_HANDOFF.md) §5 |
| 生产部署 | ⏳ 未做 | 部署步骤见 handoff |

**边界**：只覆盖**阶段 0–3**（销售订单→生产计划→工单→工序卡→销售出库）。头程/海运/国外仓（阶段 4–8）
外置（钉钉表 / 同事「智美通数据大屏」，代码未共享），**2026-10-13 决定暂缓接入**。
**物料需求 / 采购订单 / 采购入库** 在 EN 侧基本空白，**先记录不做**。

## 已有可复用的查询能力（在 `EN_API/`）

- `EN_API/fulfillment_query.py` + `EN_API/fulfillment/` —— 给通途 SKU 追「SO→PP→WO→JC→DN」，多输入/阶段/齐套/异常，**JSON 为权威输出**。
- `EN_API/item_shipment_status.py` —— 单物料引擎（含 fixture 断言 + 单测，**不要整体搬迁**）。
- `EN_API/docs/reference/en-order-to-shipment-chain.md` —— 链路导航。

## 关键事实（先读，避免重复踩坑）

- EN 的自定义 app 是**各自独立仓库**（`keyapi/*`）：`key_test`（SO 定制主战场）、`light_mes`（MES）、`work_order_task`、`delivery_plan`、`tongtool_integration`、`vilavi_pim`。
- **`Cutting Plan`/`Cutting Task`/`Work Order Split`/`Wip Transfer` 生产库 0 条记录**（建了没用）；真实车辆见地图 §0。
- 落地产物现放 `key_test`，**可移植到别的 app**（见 handoff §6 的移植清单）。

## Related

- `docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md` — 目标架构蓝图
- `EN_API/docs/reference/en-order-to-shipment-chain.md` — 链路导航（阶段 0–3 实体/代码落点）
