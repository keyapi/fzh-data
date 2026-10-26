---
okf: v0.1
type: Spec
title: EN 原生供应链报表与 Parquet 分工：生产实测及实施计划
date: 2026-10-26
status: proposed
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
module: supply_chain_visibility
---

# EN Native Supply Reports

## Goal Capsule

继续支持 Parquet 历史线路；人用入口采用与 BOM Cost List V2 相同的 Frappe Script Report，支持日期、SO、DN、物料、客户码和仓库过滤。
生产 EN 已有通途库存最新表、Parquet 历史、定时同步与历史 API，优先复用，不新建本机到 EN 的重复库存推送链。
先做数据口径和有过滤条件的实时查询，再按实测决定是否为昂贵供应推导增加每日派生快照；大范围导出可用 Prepared Report。
本文件是计划，不表示已实施、已批准扩样或生产发布。

## Product Contract

### Requirements

- R1. 人用原生报表，保留筛选、导出、单据跳转与角色权限；程序通过同一服务层或已有历史 API 读取，避免复制业务算法。
- R2. 订单履约保持 SO 行粒度；供应时间线保持 SKU×仓×阶段×日期粒度，明细保留来源单据行，不将两个视角硬合成一张表。
- R3. 支持明确的日期类型：SO 下单日期、DN 过账日期、库存快照日期分别命名。当前 SO/WO 状态不能仅靠日期条件重建任意历史时点。
- R4. 刷新与改筛选时不得实时调用通途外部 API；先读取 EN 内已有库存和业务表，缺失的 PO/运输事实通过独立适配任务补齐。
- R5. 缺源、未知、未匹配和陈旧数据显式展示；不把未知数量填 0，不把无 ETA 推成确定到货日，不将共享库存重复作为多条 SO 的已保障量。
- R6. 第一轮使用已确认的 9 SKU；Top50 后置，扩样不由查询框架选型自动授权。完整性报告保留输入、输出、排除、未知及其原因。
- R7. Parquet 继续承接历史和程序消费。Prepared Report 结果文件是过滤条件下的报表输出，不能替代业务历史或已发布供应快照。
- R8. 第一阶段核实 PO 创建与实际入库时间，并按库存采集窗口对账。PO 创建/到货头部时间不替代逐条 warehousingDate；同时防重复与漏计。自动根据 EN 头程状态对通途 PO 入库不在本阶段范围。

### Acceptance Examples

- AE1. 输入一张 SO，返回其行和关联 PP/WO/JC/DN；同 SO 同物料重复行不得相互串单；退货按已验证净额口径处理。
- AE2. 输入 DN 和过账日期区间，返回所选 DN 涉及的明细；选中 DN 的发货量与 SO 全生命周期累计发货量分列，后者不因 DN 筛选改变含义。
- AE3. 输入 SKU、仓库、库存快照日，返回对应日供给及证据；输入历史日时，当前 WO 状态不能被标成该日的状态。
- AE4. 无权限用户、权限受限客户/公司用户和 API 读取者分别验收；SQL 跨表查询不能仅凭 Report 可见权限就跳过行级授权。
- AE5. 数据源部分失败或范围不符，报表标为不完整，不作为正常完整批发布；旧完整批可查询但显示其真实日期与最新失败状态。
- AE6. 若库存批次采集于 05:17–05:31，05:10 入库可能已在库存内，09:00 入库尚不在该批库存；采集期间和边界事件保守标不确定。若查询时 PO 剩余量已扣除 09:00 入库，不能把该数量漏出供给，也不能重复加到库存和在途。

## Planning Contract

### Production Evidence

以下来自 2026-10-26 对生产 SSH 别名 `阿里云-FZH-ERPNext-frappe` 的只读核对，未改业务数据、任务配置或报表配置。

| 核对项 | 生产事实 | 对方案的影响 |
|---|---|---|
| 框架版本 | Frappe 15.48.0、ERPNext 15.43.3 | 以已安装版本源码核对能力，不套用 develop 分支行为 |
| BOM Cost List / V2 | 均为 Script Report，均 prepared_report=1；V2 属于 work_order_task | 用户的类比成立：跨表取数、Python 汇总、JS 过滤器已有成熟落点 |
| V2 执行路径 | 物料组过滤，批次内字典缓存，读取 BOM/物料/成本/物流等资料 | 复杂计算可以放原生报表，但不代表应该照搬逐物料查询方式 |
| V2 最近结果 | 当日一批从创建到完成约 48.57 秒 | 含排队和计算，不能当作纯 CPU/SQL 用时或固定性能基准 |
| SO Chain Overview | prepared_report=0；本次执行一次，4,512 行、12 列，execute 约 1.694 秒 | 当前已有同步跨表汇总实例；不是浏览器端到端延迟或并发压测 |
| SO 过滤器 | Python 模块有 customer/from_date/only_overdue；JS filters=[]，Report 子表 filters=[] | 服务端处理参数已有，但不能据此声称 UI 已有 SO/DN/物料过滤器；新增过滤器需 JS 与浏览器验收 |
| 库存同步开关 | Tongtool Settings.enable_stock_sync=1；05:17 cron stopped=0 | Windows 旧备份任务 Disabled 不等于生产 EN 同步停用 |
| 最新库存 | Tongtool Stock Latest 为 5,316 行，均来自同一 05:17 批次 | 当前库存可在 EN 内查，不受本机磁盘可达性限制 |
| 完整运行 | 10-24/25/26 均有 scheduled、14 仓、complete=1 的运行记录；当日约 05:31 完成 | 06:30 的供应任务可以复用已到齐的生产数据，仍需按实际批次检查 |
| 历史 | 生产 stock.parquet 已存在，含 10-20 至 10-26 七个日期 | Parquet 路线已在生产服务器落地，不只存在本机 |
| 历史接口 | stock_sync.get_stock_history 支持 SKU/仓/日期，检查库存读取权限，上限 5,000 行 | 可复用查询逻辑；完整导出不能默默吃掉 LIMIT 后的剩余行 |
| 部署版本 | key_test=f7ea65a；tongtool_integration=e957e092；work_order_task=e667558a | 后续实施前重新核实版本，不用本仓库旧副本覆盖服务器代码 |

原生库存实现位置为 `tongtool_integration/sync/stock_sync.py`：定时入口送 long 队列，最新表＋Parquet＋运行日志已具备。
其 `run_stock_snapshot` 当前先更新最新表/文件，再判断 complete；实施时须验证失败批与手动子集批如何影响最新数据，而不能只看最近一条成功日志。
此次未故障注入，也未证明现有发布逻辑具备完整批切换保证。
公开文档只记录结构、批次计数和观测，不保存 SKU 级数量、成本、凭证或运行输出附件。

### Alternatives

| 方式 | 查询时工作 | 优点 | 成本与限制 |
|---|---|---|---|
| A. 原生同步跨表汇总 | EN 按过滤条件读取 DB，批量关联并计算 | 当前业务状态及时、路径短、运维简单 | 每次执行仍有 DB/CPU 开销；必须尽早下推筛选 |
| B. 原生 Prepared Report | 同样计算转到 long worker，结果按报表/用户/过滤条件复用 | 浏览器不长时间占着请求，可承载大范围导出 | 计算和 DB 压力仍在；排队与陈旧结果要管理，不是全用户共享每日快照 |
| C. 业务预计算＋原生轻查询 | 定时生成派生供应结果，查询时只过滤、汇总 | 重复昂贵计算摊到批次，数量口径和来源可追溯 | 增加发布状态和陈旧度管理；不能比源快照更实时 |
| D. 外部计算后推 EN | 外部引擎算，再上传派生结果 | 若已有稳定外部引擎，可复用；可隔离 EN 的计算资源 | 多一道同步；当前库存已在 EN，因此没有默认必要 |

### Key Technical Decisions

- KTD1. 原生 Script Report 是展示和查询框架，A/B/C 都能使用它。Parquet 是存储与分析选择，不是与报表框架竞争的 UI 方案。
- KTD2. 优先 A；宽范围导出可用 B；只有实测证明重复供应推导昂贵或每日冻结结果确有需要时，再启用 C。D 保留为后备，不因旧交接的本机路径假设而先行建设。
- KTD3. EN 现有 SO/DN/WO/JC 与最新库存优先在服务端本地批量查，不经 REST 逐单回环，不在报表 execute 中拉外部 API。
- KTD4. 原生报表不天然消除重复计算；性能收益来自过滤下推、按目标单据批量关联、索引以及必要的预计算。long worker 只改变运行方式，不减少算法工作量，也不隔离共享数据库。
- KTD5. 保留 Parquet 历史与同源程序接口；若 W1 仍在外部计算，优先复用其纯计算逻辑与冻结回归用例，待输入/性能验证后再决定是否移入 EN 服务层，不承诺零移植成本。
- KTD6. 表格各层先聚合再 join，防止一条 SO 行×多 WO×多 DN×多 JC 乘法放大。WO 用 SO 行外键及已验证兜底；DN 的重复物料归属需沿用证据，不按 item_code 复制总数到每条 SO 行。
- KTD7. 库存 batch_id 从实际行的 run_id 关联运行范围和完整性，不直接取最新创建的 Stock Run。生产存在手动子集运行，complete=1 仅证明所请求范围完成。
- KTD8. 供应展示明确库存采集起点、完成时间、EN 单据查询时间；14 分钟采集区间不是严格同一瞬间快照。使用者可区分库存时点与当前履约事实。
- KTD9. 入库查询按日期窗口分页复用，避免逐 PO 扫全量；相邻请求至少间隔 13 秒，遇 526 停止并明确报错。这只是调用方节流，不代表绕开商户全局共享限流。读原生报表不触发外部 API。
- KTD10. 已实测 purchaseStockQuery 存在 warehousingDate（秒）、PO/SKU/仓及 warehousingNum，但响应缺独立流水/行 ID 和单位。保留每条原始行与弱身份标记，不用内容哈希静默吞掉可能真实相同的两笔入库；在唯一性、单位和库存桶影响未证实时，不自动修正可用库存或抵扣在途。
- KTD11. 05:47 的 stock_change.parquet 已有 operate_time、凭证类型/号、available/intransit 等桶增量，可作辅助证据；操作类型、时间覆盖及凭证映射仍需验证，不能仅加采购入库而忽略出库、占用/释放、退货和手工调整。

### Performance Policy

不把 2k 行当作框架上限，不用 BOM V2 的生成时长推断新报表一定慢。
普通筛选暂以 execute 冷执行不超过 3 秒为验证目标；记录 SQL 数、查询计划、扫描范围及返回量。
同一固定样本至少记录首次与重复执行；并发和宽范围在测试环境验证，禁止在生产反复重跑全量 BOM 作为压测。
超目标先减少全表扫描和逐行 DB 查询；仍慢且必须重复计算时再采用 C，偶发宽导出优先 B。
以上为验收目标，不是已获得的性能保证；不要求缓存命中结果证明冷执行性能。

## Implementation Units

### U1. 冻结数据契约与生产资产映射

依赖：无；先写数量对账和日期口径用例。
落点：本目录计划、`supply_chain_visibility/docs/reference/en-chain-cardinality.md`、`EN_API/fulfillment/` 现有逻辑，以及 app 仓库的 `tongtool_integration/sync/stock_sync.py`。
核对 PO 的实际权威来源、刷新时点、开放量、状态与库存在途重叠；目前未发现对应 EN PO DocType，不宣称已全量入 EN，实施前继续查证接口/外部表路径。
验证同批最新行、日志、Parquet 日期及范围；分清已知 0、未知、无匹配与未纳入范围。
源完整性是所有执行方式的放行前置，不只约束 U4 的派生快照：若部分失败或手动子集会覆盖当前全仓数据，先在 `tongtool_integration/sync/stock_sync.py` 修正验证后发布规则，或改为读取可证明范围完整的保留批次；若不存在可用完整批，报表只展示不可用状态，不发布正常供给结论。
对应回归落点为 `tongtool_integration/tests/test_stock_sync.py`（遵循 app 既有测试目录调整），覆盖全仓批、子集批、部分仓失败、文件写入中断和最新表批次关联；保留批来源必须明确，不能假设同日 Parquet 覆写前的数据还在。
验收：9 SKU 每个来源的数量可追溯；不以“最新成功日志”替代实际已发布批。
用例落点：`key_test/tests/test_supply_query_contract.py`（app 仓库，新增）。

### U1b. PO 入库事件与快照时间对账

依赖：U1 的来源确认；先于完整供给/在途可承诺汇总发布。
本仓库落点：`tongtool_api/purchase_receipts.py`、`tongtool_api/tests/test_purchase_receipts.py`、`supply_chain_visibility/receipt_reconciliation.py`、`supply_chain_visibility/tests/test_receipt_reconciliation.py`。
读取 purchaseOrderQuery 的创建/采购/到货头部字段与 purchaseStockQuery 的逐条入库字段，分别保留，不混淆精度与含义；EN 按钮的 custom_tongtool_po_created_on 只证明按钮写回时间。
纯对账核心将确证有效时间划分为采集前、采集后、窗口内/边界不确定；按仓窗口优先、批次窗口保守兜底，按 SKU×仓×单位汇总，不直接改变业务库存。
相同稳定事件/行 ID 的同内容重放去重，冲突版本隔离；真实响应没有稳定 ID 或单位时保持未知。每个输入行都能归入成功分类、重复、冲突、未知之一。
用例覆盖 05:10、05:17 边界、采集期间、09:00、分批入库、重复拉取、同 ID 改量、缺时间、时区转换、分页截断及 526；自动采购入库另立后续任务。

### U2. 原生履约报表与过滤器

依赖：U1。
app 仓库落点：`key_test/key_test/report/so_chain_overview/so_chain_overview.py`、同目录 `.js`、`key_test/supply_query.py`（新增服务层）。
本仓库同步落点：`supply_chain_visibility/key_test/key_test__report__so_chain_overview__so_chain_overview.{py,js,json}` 与相关交接记录。
新增 SO、DN、物料、客户码、客户、仓库与明确命名的日期条件；先界定 SO 行，再只读取目标关联单据，避免现在每次重新扫描全部 DN/WO/菲号。
时间口径参照 R3；DN 选择影响所选 DN 明细量，SO 全周期累计量保留独立列。
用例落点：`key_test/tests/test_supply_query.py`；覆盖重复同物料 SO 行、多 WO、多 DN、退货、未匹配 DN、无工单、空结果与跨公司权限。
浏览器验收：过滤器真正出现、Link 候选可用、改条件生效、空结果说明、导出与屏幕一致。

### U3. 原生供应时间线与 Parquet 查询

依赖：U1，可与 U2 分开交付。
app 仓库落点：`key_test/key_test/report/supply_timeline/supply_timeline.{py,js,json}`（新增）、`key_test/supply_query.py`；复用 `tongtool_integration/sync/stock_sync.py:get_stock_history` 的历史查询规则，避免内部 HTTP 回环。
过滤器含 SKU/物料、仓库、阶段、库存快照日和预计可用日期区间；SO/DN 仅作为来源追踪条件，不改变供应主粒度。
历史库存与当前单据状态混合时明确标识，完整供应历史须来自已保存派生快照，不能把当前表查成任意过去时点。
用例落点：`key_test/tests/test_supply_timeline.py`；覆盖无 ETA、未知单位、在途/PO 去重、数据不完整、同日多批与原始明细 drill-down。
全量历史导出按完整性校验设计分页或独立导出任务，不直接复用现有 5,000 行有界 API 作为完整源。

### U4. 实测后选择执行策略

依赖：U2/U3 基线完成。
先在测试环境记录普通筛选、9 SKU、Top50 候选范围、历史区间及导出的 execute 时间、SQL 数、内存和结果计数。
报表超过同步预算时先优化 U2/U3；偶发宽导出使用原生 Prepared Report。
每日供应冻结确有需要或复算成本较高时，才在 app 增加 `key_test/supply_snapshot.py`、运行头和派生明细 DocType，06:30 独立任务只读取完成的来源批次；不让每次用户刷新触发采集/全量构建。
跨 DB/Parquet 的写入不宣称天然同一事务：验证后切换发布标记，失败保留前一完整批，文件用临时文件与原子替换，保留恢复路径。
用例落点：`key_test/tests/test_supply_snapshot.py`（仅采用派生快照时新增）；覆盖重复触发、任务重叠、部分批、手动子集、发布中断和旧批回退。

### U5. 测试发布与交接

依赖：U2/U3，及实际采用的 U4 分支。
在 app 测试分支实现并 migrate 验证，按两个 app 仓库的归属提交，再同步本仓库产物与文档；生产发布沿既有 PR 审批流程。
部署只涉及已批准报表/派生数据，不修改 SO/WO/DN/库存账/主数据；外部接口和订阅发送另按明确范围实施。
app 改动前读取各自仓库 AGENTS 与基线，不能用本仓库副本覆盖较新生产代码。
交接更新 `supply_chain_visibility/key_test/AGENT_HANDOFF.md` 与 Jack 的 `JACK_QA.md`，标明实际采用 A/B/C、数据来源、过滤器语义、性能记录和回滚入口。

## Verification Contract

- 冻结回归：沿用 W1/SC14 已有样本与合成 fixture；冻结结果和每日实时结果分开验收，不强求实时数字等于冻结值。
- 数量守恒：来源量＝纳入量＋明确排除量＋未知/待核对量；多表 join 不重复放大，单位不可混加。
- 原生查询：服务层与报表、API、导出同口径；JS 与服务端均处理过滤器，权限和 SQL 参数化全覆盖。
- 性能：当前 1.694 秒只作为一例参考；测试环境验证冷执行、重复执行、目标并发、宽导出，记录差异而非仅写“通过”。
- 运行模式：Prepared Report 在已安装版本中走 long，默认超时 25 分钟；超过约 15 秒的 Script Report 可能被框架自动改为 prepared，需要在实施中核对实际配置与用户体验。
- 源完整性：验证运行范围、run_id 和实际发布行一致，手动子集 Success 不冒充全仓完整；失败与陈旧在页面可见。
- 发布放行：无论最终选同步、prepared 或派生快照，均先验证源批次保护；无法取得已校验完整批时只展示不可用，不把后置 U4 当作数据完整性的兜底。
- 文件发布：如采用派生快照，专门测试数据库与文件之间的中断恢复；普通 Prepared Report 生成不充当业务快照发布标志。
- 文档：OKF frontmatter、目录导航、bundle log、根索引与凭证扫描；不提交行级业务附件。

## Definition of Done

- 日期/SO/DN/物料过滤在真实浏览器可用，支持权限、导出与单据下钻。
- 履约和供应两个粒度可解释，未知与陈旧信息可见，样本数量对账无未说明差额。
- 性能记录决定同步、prepared 或派生快照的具体分工；不以架构偏好替代测量。
- 已有生产库存与 Parquet 底座被复用；没有无必要的第二套库存采集或本机推送链。
- 测试先行、PR 审批后发布；生产行为与实际落地版本写入交接。

## Sources and Confidence

- 原生报表过滤器与返回能力：[Frappe Script Report](https://docs.frappe.io/framework/user/en/desk/reports/script-report)。
- Prepared 的用户体验与运行方式：[Using Prepared Report](https://docs.frappe.io/erpnext/prepared-report)。
- 与生产版本一致的队列实现：[Frappe v15.48.0 prepared_report.py](https://github.com/frappe/frappe/blob/v15.48.0/frappe/core/doctype/prepared_report/prepared_report.py)。
- 仓库模式：`EN_API/bom_cost_list_excel.py`、`supply_chain_visibility/key_test/`、`supply_chain_visibility/docs/reference/en-custom-apps-and-deploy.md`。
- 原生框架、生产库存与历史可用性：已直接核实。未来供应推导成本、业务历史回放覆盖、PO 接入与并发容量：仍需 U1/U4 验证，当前不承诺。
