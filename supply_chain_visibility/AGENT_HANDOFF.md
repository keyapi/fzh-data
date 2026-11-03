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

**必须记住的口径**：首工序仅是启动里程碑，**不能作为已完成生产供给**；生产供给只认
具备资格的全工序完成证据，且不跨工序求和；`WO.status/produced_qty` **不可信**；
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

## 6. 供应事实批量入口（2026-10-27）

> 2026-10-30新增本地DN/PO消费入口：`supply_position.py`；见
> `docs/reference/supply-position-consumer.md`。依赖完整创建文档的lines，当前
> delivery_plan审计查询尚不返回lines；缺失保留待核。输出只覆盖DN/PO，
> 不作为完整补货/库存结果，不运行历史warehouse_restock导入流程。

- 契约与字段：`docs/reference/supply-facts-contract.md`。
- 服务端：key_test `supply_facts.py` → whitelist `get_supply_facts`（SO 行 → stage_balances / milestones / availability_schedule / links / manifest）。
- 本地入口：`EN_API/supply_facts_export.py`（JSON + Excel + sha256 + `latest.json` 原子指针；失败不覆盖最后成功版本）。
- 人工视图：SO Chain Overview 链条弹窗新增「数量阶段 / 节点 / 分批可售」，与批量入口调同一方法。
- 测试站已部署验收（单 SO 0.63s；278 行全范围 0.72s）；**生产未部署**；9 SKU 待生产授权。

### 6.1 full_supply_facts v6 阶段明细与正式刷新（2026-11-03，RULE/IMPL 2026-11-03.1）

- 离线入口：`supply_pipeline`；正式 EN 只读刷新入口：`supply_snapshot_refresh`。后者先加载
  ABC/权威 scope，再采集分页，并校验稳定 `snapshot_id`、版本、总数、连续性和权限；任何
  采集/发布失败保留旧 latest。
- 主数据集 `full_supply_facts.parquet` 改为阶段明细：item×uom×warehouse×purpose×tt_sku×branch×stage×doc_line/batch_id；含 doc_type/doc_name/doc_line/batch_id/source_identity/stage_fact_id。
- 历史目标汇总迁为独立兼容数据集 `supply_target_summary.parquet/json`；原字段/四层资格保留。
- 阶段只允许 open_po/waiting_shipment/in_transit/received/on_hand；open_po 仅核账不计供给；signed 未通途入库归 in_transit（signed_at）；received 只认通途入库时间；on_hand 只认库存快照。同一物理批次只允许一个 counted_as_supply 当前阶段。
- observed_at/eta/available_at/signed_at/received_at 严格分离；naive/date-only 不假定 UTC。
- purpose 支持 branch/fba/cg；owner_status/cg_stale/cg_eligible/cg_blocking_reasons 显式；stale CG 保留观察但不抵扣。
- 发布/reader 同时校验阶段主数据集、目标汇总、position、timeline；manifest 含 as_of/run_id/输入版本/SHA/行数/阶段唯一键/freshness/stage/unknown/conflict/overlap/CG 统计。
- 统一 `manifest.json`（`supply-publication/v5`）。市场/形态纳入目标唯一键。
- A/B/C（`abc-frozen/v3`）：观察量/归属量/当前可用/下单四层分开；C 必须
  join_full + source_ref + 数量 + UoM 才可归属，否则 `c_not_qualified` 且可信/当前
  均为 null；B/C 单位必须一致才可归属；naive/date-only 不算精确时间；缺身份只进
  未归属池；CG 池不复制；B/C 版本冲突显式。
- 身份补齐命中已有 DN/PO 目标键时禁止覆盖：不同已证 DN 明细来源合并求和、同源重放
  去重、无法证明两行保留并标 `abc_identity_key_conflict`；同 ABC 键库存载荷冲突标
  `abc_inventory_key_conflict`。
- 来源身份与目标归属分开：同一物理来源跨 branch/仓/用途且无
  `allocation_id`+`allocated_qty`+`source_qty` 容量证明 → `source_target_conflict`；
  物流同 DN 明细+商品/UOM+运单跨目标同样 unknown；合法分配还要求实际量严格等于
  allocated_qty、同源容量声明一致、按 allocation 身份去重后不超容量；同目标内也执行。
  allocation 同载荷重放只计一次，冲突标 `source_allocation_conflict`。
- DN/PO 物理身份只含 instance+DN+DN Item；创建审计/PO 号/状态桶属于关系证据。
  PO 作废重建不复制 DN 数量，部分重叠按物理明细并集；同物理明细载荷冲突时 DN/PO
  聚合量全部 unknown（`dn_physical_payload_conflict`）。
- 类型：数量 `decimal128(38,6)`（JSON 规范化字符串），时间 UTC timestamp（date-only/naive
  保留 raw、不假定 UTC）；JSON/Parquet 逐字段回读一致；空表固定 schema；重复键拒收。
- 失败保护：不创建成功 run、不切 latest、`last_attempt.json` failed；reader 识别
  healthy/stale/partial/corrupted/incompatible/refresh-failed。
- reader 每次按本次读取时间从行 `sources[].observed_at` 重算行级 freshness；文件级与
  行级任一 stale/unknown/future 即 stale，新文件头不能掩盖旧行；`allow_stale` 只影响
  可读许可。
- 冻结输入：所有非 `not_provided` 输入必须成功复制并校验 SHA（provided_count ==
  frozen_count）；缺失/变更/复制失败终止发布并保留旧 latest。只有 not_provided 是
  可选缺失。`--replay-run <run_dir> --out <new_out>` 校验字节后复跑，支持空格/中文
  路径，业务内容 SHA 稳定。
- 输入契约：混版缺版本页/分页截断/未 exhausted 拒收；合法业务 partial 不拒收，
  该层汇总 unknown、已证片段保留，`partial_reason=business_partial` 透出 manifest/
  reader；来源状态保守聚合。
- **真实 A/B/C 冻结工作簿验收 pending**（本机暂不可用，未用合成数据冒充）。
