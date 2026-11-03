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
- `supply_chain_visibility/supply_position.py` —— 第二批 supply_position 消费表（创建清单×PO 状态，完成只关 included、部分不分摊、legacy 不伪造、快照防双计、A/B/C/D 构件）。
- `supply_chain_visibility/po_status_refresh.py` —— PO 状态批量刷新（去重、10/批、断点、未查询显式）。
- `supply_chain_visibility/abc_inputs.py` —— 本地冻结 A/B/C 归因：A 目标集合、B 身份权威、C 库存观测；缺维度 null/unknown、CG 池不复制、版本关系显式。
- `supply_chain_visibility/publication.py` —— 统一发布/读取：`full_supply_facts.parquet`（主）+ JSON（追溯）+ `supply_position`（独立 schema）+ `timeline` + manifest/latest；回读/SHA/schema/唯一键校验，失败不切换。
- `supply_chain_visibility/supply_snapshot_refresh.py` —— 正式只读刷新入口：先校验 ABC/权威 scope，再分页采集 EN、校验稳定快照与权限，成功后才原子发布；失败保留旧 latest。
- `supply_chain_visibility/abc_datasets.py` —— A/B/C 版本化 JSON/Parquet 接口，严格字段、有限数、行数、SHA 与 B→C 依赖校验；Excel 仅作冻结回归适配。
- `supply_chain_visibility/supply_pipeline.py` —— 可执行离线链路：保存 API + 可选 A/B/C→创建清单→PO 状态→#323 消费器→full_supply_facts v8/Timeline→Parquet/JSON 统一 manifest（失败保留旧版，`--inspect` 只读查看，`--replay-run` 冻结复跑）。
- `supply_chain_visibility/full_supply_facts.py` —— full-supply-facts/v8：阶段明细主数据集（open_po/waiting_shipment/in_transit/received/on_hand，doc_line/batch_id 粒度，单批一当前阶段）+ 兼容目标汇总 `supply_target_summary`；观察/归属/当前可用/下单四层、C join_full 资格、时间五字段分离、事实身份/物理批次/目标归属分层（fact_identity/physical_lineage_id/payload_hash）、库存只认同线包含、阶段单调与时间冲突、同 lineage 同阶段物理量核账（evidence_only/quantity conflict/allocation sum）、on_hand 时间与新鲜度门槛、CG/stale 显式、重复键拒收、业务冲突 partial 发布、跨层不求和（预测未接）。

## 关键事实（先读，避免重复踩坑）

- EN 的自定义 app 是**各自独立仓库**（`keyapi/*`）：`key_test`（SO 定制主战场）、`light_mes`（MES）、`work_order_task`、`delivery_plan`、`tongtool_integration`、`vilavi_pim`。
- **`Cutting Plan`/`Cutting Task`/`Work Order Split`/`Wip Transfer` 生产库 0 条记录**（建了没用）；真实车辆见地图 §0。
- 落地产物现放 `key_test`，**可移植到别的 app**（见 handoff §6 的移植清单）。

## Related

- `docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md` — 目标架构蓝图
- `EN_API/docs/reference/en-order-to-shipment-chain.md` — 链路导航（阶段 0–3 实体/代码落点）
