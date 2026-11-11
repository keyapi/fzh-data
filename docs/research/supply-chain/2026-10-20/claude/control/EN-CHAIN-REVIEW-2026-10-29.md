---
okf: v0.1
type: Review
title: Jack EN供应链能否作为补货证据：只读实查
date: 2026-10-29
verdict: partial-not-ready-for-confirmed-supply
---

# 结论

**六项：已达0、部分5、未达1。** 已有可用的SO→WO/JC→DN生产追溯和运输单结构化字段，不能说Jack未做；但尚未形成“按SKU×目的仓×阶段互斥数量、目的仓可售日期、实收关闭”的补货证据接口。今天最阻塞的是**生产完成误升格、预计到港/起运仓与目的仓可售混淆、无逐行目的仓实收/在途关闭闭环**。可以继续消费已证现货，未知在途独列；不能把这条链中的全部数量当确定供给，也不能因链条缺证就默认应新下单。

取证窗口2026-10-29 09:31:39～09:36:34（+08:00）；**27次GET=24生产+3测试，26次200、1次404**，无超时/5xx，无重试，无写入。列表page_length最大100；每次请求前固定等待0.25秒（首个除外）。首个测试SO-26-00110返回404是**该SO不存在于测试数据**，不是方法未部署；随后测试SO-24-00000调用同方法200。源文档/脚本与实时响应互相核对，未将历史10/22、10/28统计冒充今日全量。

路径简称：E=`D:/Work/赛狐/Cursor/EN_API/`；V=`D:/Work/赛狐/Cursor/supply_chain_visibility/`。生产base=`https://erpnext.vilavi.cn`，测试base=`https://ensh.vilavi.cn`。

# 六项判定

| 项目 | 判定 | 当前已具备及实证 | 未达补货要求的具体缺口 |
|---|---|---|---|
| 1. SO→WO/JC→DN→Shipment→头程→目的仓入库统一视图 | **部分** | GET `/api/method/key_test.so_chain.get_so_chain?sales_order=SO-26-00110`200，214条SO行；SO-25-00169为82行。返回so_line/item_code/qty/open_qty/shipped_dn/work_orders/dns/生产计划，支持行级WO关联和菲号/工序。DN→Shipment已有正式桥，见DN-26-00111→SHIPMENT-00002。 | RPC行无uom、stock_uom/conversion_factor、canonical_destination_warehouse、available_date/confidence/source_version；不含运输和目的仓实收数量。`E/fulfillment/stages.py:1–4`明确只做0–3段。更严重的是首工序量会触发“生产完成待出库”（详见下）。不可直接转成各阶段互斥供给。 |
| 2. 头程运单与ETA结构化 | **部分** | Shipment自定义字段实际已存在：custom_zmt_logistic_number/tracking/source/transport/dest/region；Date字段atd/ata/clr/dlvr/eta/appt，Datetime synced_at，事件子表events。DN有logistic_number、custom_zmt_shipment及custom_zmt_logistic_numbers子表。不能再一概说只在备注。 | Custom Field明确eta标签为**预计到港**，不是可售；dest为Data，不是目的仓外键；carrier常空。SHIPMENT-00002结构eta=11/17，而节点描述预计到港11/8，缺优先级/解释。SHIPMENT-00051 eta=12/20、无事件，待证来源。当前账号56 Shipment里9个eta空，含FBA/历史失效单，不能直接当9张分公司待催。 |
| 3. 目的仓入库确认/在途关闭 | **未达** | 可复用正式PO桥与通途回执：本次28张分公司DN（8/1..10/27）已有**9**张正式PO链接（较旧8张新增DN-26-00114→PO021742）。缓存po_receipts_8linked_2026-10-28.csv有PO021724的8行、143/143、美中仓、10/28 09:39:07。 | EN统一链未返回目的仓receipt_id/line/received_qty/reversed_qty/available_at，也未将回执和库存快照去重。Shipment.wms_in_time不能代替目的仓入库：SHIPMENT-00002入仓10/21早于开船10/27；SHIPMENT-00041“已入仓”但节点说11/3才开船。不能自动关闭在途。Purchase Receipt首100条抽样存在，但未作海外归属/全量核验，**不据此断言EN不存在入库单**。 |
| 4. 八事件统一timeline与时间戳来源 | **部分** | SO.transaction_date/creation，WO/JC.actual_start_date/actual_end_date，DN.posting_date/posting_time，Shipment.atd/ata/clr/dlvr及events已可读取。WO-26-03268真实工序开始10/9、最近报工10/12可追。 | 尚未统一event_code、actual/estimated、origin/destination、timezone/precision、source_doc+line与observed_at。Shipment Logistics Event.event_time是**Data**，event_name/location在抽样为空，description混实际与预计；SHIPMENT-00044含未来10/30起飞、10/31落地，不能作为已发生事件。WO.actual_end_date可只是最近报工，不能代表整单最终完工。 |
| 5. 质量巡检 | **部分** | `E/fulfillment/rules.py:15,31,113–132`已有生产停滞/工单异常规则。实时字段足以生成物流检查：28张分公司DN中00084/00085/00103缺主logistic_number与custom_zmt_shipment；SHIPMENT-00004为Unmatched，活动DN数0；阶段冲突可定位行。 | 未见Jack交付的统一巡检接口/定时异常账及闭环状态，不能把本轮手工GET审计当成W4已实现。须反查DN运单子表并按纯内胆/FBA/材料规则分流后才催；Shipment-00004原DN链接已is_active=0/removed_at，不应再算有效关联。ETA是到港日期，若ATA已实现就不应误报“过期未到港”：本轮11个旧eta且非签收/POD状态中，**全部已有ATA**，按正确条件此次0个到港ETA过期未兑现；不得凭旧ETA误催。 |
| 6. 只读导出/API稳定性与分页 | **部分** | 标准REST支持fields/filters/limit_start/limit_page_length/order_by；实测Shipment第0、2偏移各取2条，00001/00002与00003/00004无重复；单页100得到56个可见Shipment。生产/测试SO方法均200。CLI可导出JSON/Excel。 | 自定义RPC返回全部SO行，无schema_version/as_of/snapshot_id/分页/穷尽标识，214行响应不能当可增量冻结的批接口。原客户端get_single在HTTP失败后取data默认{}（item_shipment_status.py:304–307），字段回退后可能缺数量证据；分页最多200页却无截断失败。必须输出missing_fields/truncated并fail closed，不能把缺字段/失败读成0或没单。 |

# 最阻塞的三项：单据级反例

## A. 首工序完成被升成可发货（今天阻断“催发运/确定在产转待发量”）

生产RPC：`/api/method/key_test.so_chain.get_so_chain?sales_order=SO-26-00110`，行 `so_line=5qsq01tuue`、`PK#KS0001-DM-100-ANTHRACITE`，qty/open_qty=140，stage=3/substate=生产完成待出库，但reported=0、instock=0、prog=3/6。工单`WO-26-03268`直接GET确认：裁剪/锁扣眼/拷边Completed，皮壳整件/翻面/质检Pending，produced_qty=0；Job Card列表36张可追，首工序批量合计140。

`V/key_test/key_test__so_chain.py:133–138,275–280`以首道必经量累加判断stage；虽`:218–236`另给reported/instock并避免成品/组件相加，stage却没有改用这个更严格证据。`E/fulfillment/stages.py:49–56`也以first_op_total_completed_qty触发完成。SO-26-00110共51行标待出库，其中37行与末道报工/工厂入库至少一项不足有冲突；这不是说37行全部都物理未完成，**但都不能未经澄清当确定可发量**。同一工序的整批卡与菲号卡、成品/皮壳/内胆亦不能跨层相加。

Jack应分出started_qty、operation_reported_qty、terminal_qualified_qty、factory_received_qty、finished_pending_dn_qty，明确部分完工、超产和冲突隔离；“首工序做完”只证明开工下界，不能给末工序事实。reported若取“最大sequence有卡”的工序也必须检查真正的必经末工序已完成，不能退化到中间工序后仍叫最终完工。

## B. 到港ETA/起运仓入仓不是目的仓可售（今天阻断按日抵扣在途）

- DN-26-00111→SHIPMENT-00002，物流号999261021003333；atd10/27，eta11/17（字段标签预计到港），appt11/22；节点文本却写预计到港11/8。必须给eta_port、eta_destination_receipt、available_at及各自来源/修订/冲突，不可任选较早值。
- DN-26-00100→SHIPMENT-00041，status11=已入仓、status4=待发、wms_in_time10/17；10/27节点明示大船晚靠、预计11/3开船。这里“入仓”显然不能当波兰仓入库。DN-26-00104-1→SHIPMENT-00044也有10/22入仓、后续预计10/30起飞，字段dest=53-411，需结构化映射目的仓。
- 全56个可见Shipment的docstatus均0（Draft）。这不表示所有物流事件是假数据；应按来源与事件真实性分层，而不是简单要求Shipment提交，也不能把Draft一律当confirmed供应。

Jack应保留当前结构化字段，补event_location_role=origin_hub/port/destination_warehouse、event_kind=actual/estimated、canonical_destination_warehouse和source/conflict。`custom_zmt_pieces`是包件数，不是SKU件数，不得用于物料供给量。

## C. 逐行实收与链路数量分配缺失（今天阻断在途关闭与防重复下单）

Shipment.shipment_delivery_note只有DN引用、金额及is_active/is_primary，没有DN-item→Shipment的分配数量；一张DN多运单/拆批不能把全DN量分别复制进每个运单。正式PO字段是DN.custom_tongtool_purchase_order，不是LH旧po_no。按本轮固定DN日期范围，9个正式链接已实读；未知/候选链接不能升正式。

补货接口需要receipt_doc/receipt_line、PO行/sku、DN行分配量、目的仓实收量、冲销/退货量、received_at、available_at、来源更新时间及与库存快照的包含关系。通途应取入库统计`erp2_purchase_purchasestockquery`对应真实回执，而非purchaseorderquery.in_quantity；本轮仅读既有本地缓存，没有请求通途。PO021724缓存143/143可作为回执样例，仍须保留原回执行ID/UOM/撤销字段，不能把已有库存再加143。EN Stock Entry的Material Consumption for Manufacture是工厂耗料，不是海外入库证明。

# Jack先做三件具体的事

1. **修数量/阶段判定并给10个代表键的只读对账。** 首先以SO-26-00110/WO-26-03268作负例：3/6工序不得待发；用SO-25-00169保留已出库/Closed未发区分；在现有get_so_chain增加uom/stock_uom/conversion_factor、角色/目的仓、互斥阶段向量、source_doc+line与unknown_reason。按已归属订单行封顶，超产/超发隔离；不重做界面。今天先交可复算JSON及阶段守恒/拆批断言。
2. **结构化可售日并解决两张运单的冲突。** 以SHIPMENT-00002与00041/00044为验收：实际/预计、起运/目的分别标；eta_port与available_at分开；日期精度不足保留Date而非补00:00假时间；给source_provider/source_event_id/source_updated_at/observed_at/timezone+precision/confidence与修订优先级。11/17与11/8未决时写冲突/日期未知，不默取较早值。物流补事实，Jack负责接线和门禁。
3. **交目的仓回执闭环+机器接口/巡检，不再只交截图。** 先用DN-00087/PO021724缓存回执验证实收与库存去重，再用00041证明“起运入仓不关闭”。补DN行↔Shipment↔PO行↔目的仓receipt行分配及remaining_in_transit。扩展现有RPC或新增只读批量导出（**建议，未声称已部署**），带schema_version、as_of、snapshot_id、cursor/has_more、source_counts和缺证清单；输出下面巡检队列，按角色分派并在新事实到达后重算。

# 可验收的字段/事件/巡检清单

**供应行最小契约**：`canonical_sku, source_item_code, customer_item_code, canonical_destination_warehouse, warehouse_mapping_basis, role, uom, conversion_factor, so/so_line, wo, jc/tracking_group, dn/dn_line, shipment/shipment_dn_row, po/po_line, source_key, lot_allocation_id, stage, attributed_qty, excess_qty, available_at, date_confidence, as_of, source_updated_at, observed_at, schema_version, missing_evidence`。个/套分列；TJ#按套、PK#按1:1皮壳代理，内胆配套不再作为另一份成品数量；FBA/分公司/第三方分scope。已收货是历史流量，不与当前库存简单相加。

| 业务事件 | 现有读取端点/字段 | Jack必须补的语义 |
|---|---|---|
| 下单 | GET resource/Sales Order/{so}:transaction_date、creation、items.name/qty/uom | business_order_date与系统创建时间分开；SO-26-00110=9/2、creation15:54不是承诺供给日 |
| 开工 | GET resource/Work Order/{wo}、Job Card/{jc}:actual_start_date/time_logs | 用已证作业/报工来源，排除虚拟一键完工/重复卡；不是WO.status |
| 完工 | JC必经末工序total_completed_qty/actual_end_date及工厂合格入库凭证 | 终检/角色合格量，不取首工序或WO最后一次报工冒充全完 |
| 工厂出库 | GET resource/Delivery Note/{dn}:docstatus、posting_date+posting_time、items.name/so_detail/item_code/stock_qty/uom | 退货带符号、拆批归属，出库不等于海外可用 |
| 开船 | Shipment.custom_zmt_atd + events/人工节点 | actual_departure_at，区分预计ETD和source观察时间 |
| 到港 | custom_zmt_ata / eta | actual_arrival_port_at与eta_port分开，解决provider冲突 |
| 清关 | custom_zmt_clr / events | customs_cleared_at与报关放行/目的地清关区分，保留事件ID |
| 目的仓实收/可售 | 通途入库回执或已证EN目的仓凭证 | destination_received_at、qty、receipt_line、available_at、冲销与快照包含关系 |

**巡检每条输出**：异常码/严重度、SKU+仓+scope、影响量（未知为空）、源单据行、观察日、具体缺项、事实责任角色、首次发现/最后变化、处理状态。至少有：
- DN主运单/Shipment缺失并反查子表；纯ND/FBA/取消/退货与8/1历史政策分层，不把例外当错误催物流。
- Shipment无**活动**DN/重复主关联；SHIPMENT-00004旧链接removed_at=10/23、is_active=0，不得借旧DN再次计量。
- 同DN多运单分配量超DN净量、同运单SKU量未分配；候选PO与正式PO分列。
- 到港ETA已过且无ATA/后继已实现事件；不可把已到港后等待派送误报为到港逾期。目的仓预约/可售延期另列。
- 报完工但末工序/质量/工厂入库未证（本次140个反例）；头部actual_end_date已填但必经工序Pending；阶段向量不守恒/数量超发。
- status11“已入仓”但地点起运或未知，或入仓早于开船；预计节点未来时间不得进实际事件。
- 陈旧同步、缺日期/缺单位/缺目的仓、403/字段回退/截页。失败/缺数保留unknown，不能当0继续净算。

# 今天如何使用，不误停整个补货项目

- **可用**：正式SO/WO/JC/DN行追溯、已证目的仓现货、正式DN→PO桥、已证开船事件；结构化字段可直接复用。
- **有条件用**：到港ETA只能作运输情景；阶段未明/单位/分配未证的量不抵扣，但必须先查现有SO避免重复新购。个别键证据闭环可单独释放，不等全目录。
- **不能用**：首工序量当可发成品、入仓标签当海外实收、Shipment包件数当SKU量、无ETA在途当及时到、把旧单修改时间当事件时间。缺这三类证据会阻塞今天该键的确定补货量/动作与在途关闭；它们不阻塞需求预测或已证现货分析。

# 取证边界和来源

已读指定Jack交接、10/22关联审计、EN_API全部AGENT_HANDOFF文件（重点物料发货状态/DN追溯）、fulfillment_query.py及其实现、en-server-access.md。已有Fulfillment FieldValue能承载kind/source/source_record/observed_at，但observed_at来自查询时刻（evidence.py:11–35），不是业务事件发生时刻，仍需两者分列。旧DP样本覆盖和98GET统计只作历史，不外推今日。

分页只做小样本：两页各2条无重叠；Shipment单页56<100为当前账号可见范围。Purchase Receipt首100条为样本且未穷尽，不报全量覆盖/缺失率。自定义SO响应214行是单SO方法返回，非列表page_length被设为214。本次无5xx/超时，按规则未发生需停止的故障；404已查明为测试SO不存在。未执行源CLI默认重试/扇出，无POST/PUT/PATCH/DELETE、无EN/通途修改、无push。只写本报告；响应和无凭据请求计数临时保留在本机Temp，不把凭据/请求头写入报告。
