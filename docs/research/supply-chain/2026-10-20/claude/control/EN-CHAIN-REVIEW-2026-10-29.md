---
okf: v0.1
type: Review
title: Jack EN供应链与timeline的补货证据就绪度审核
date: 2026-10-29
status: complete-read-only
verdict: partial-not-replenishment-ready
scope: local code and handoffs plus 8 production GET requests
---

# EN供应链/timeline补货证据审核

**结论：已达0项、部分5项、未达1项。** 这里的“未达1项”只指**签收→通途入库的时间差对账与在途关闭**；**不是**要求扫外箱号或逐件实收。业务口径已明确：目前没有扫箱收货，**签收即默认全部到达**。当前 EN 可供人工追溯与条件情景消费，但不能把工厂在产/Shipment在途自动变成某日目的仓已证可售供给。 应复用现有`supply-facts/v1`与Shipment自定义字段补齐，不能根据旧`fulfillment_query`的范围说明，误判为EN完全没有头程数据。

审核基准是10/23交接W1/W3的SKU×仓×UOM、阶段互斥、日期分层、实收入库及来源追溯要求；不是“有页面/接口返回200”即达标。已读10/23 Jack交接、10/22 SO关联评审、EN_API全部AGENT_HANDOFF通配文档（相关链路详细核读）、fulfillment_query及实际实现。旧关联评审的四段/每段15单样本结论只作历史证据，不外推到10/29全量。UOM仍按已固化口径：个/套分列，TJ#按套，PK#皮壳1:1，未知单位不合计。

## 六项逐项判定

| # | 要求 | 判定 | 已有字段/端点/单据证据 | 还缺什么，失败会怎样 |
|---|---|---|---|---|
| 1 | SO→WO/JC→DN→Shipment→头程→目的仓入库统一只读视图，SKU×仓×阶段数量/日期 | **部分** | `GET /api/resource/Sales Order/{name}` items.name；WO.sales_order_item、JC.work_order；DN Item.against_sales_order/so_detail；DN.custom_zmt_shipment、Shipment.shipment_delivery_note[]。新`GET /api/method/key_test.supply_facts.get_supply_facts`已有lines/stage_balances/milestones/availability_schedule/links，schema/rule版本、qty/uom/source_record/date_confidence。10/29样本有SO-26-00103/i4ntaautrv、PK#KS0001-CMGDTH-140-LIGHTBEIGE，stage=unknown、qty20、已提交生产计划未建工单。 | supply-facts仍partial=true；external_sources中tongtool_po/receipt/warehouse_receipt均not_integrated。阶段行warehouse仍可能是“半成品仓-FZH”而非海外目的仓，必须另证客户→分公司→目的仓映射。旧CLI只到阶段0–3；尚不能端到端输出已证到仓数量/可售日。 |
| 2 | 头程运单/ETA结构化 | **部分** | 生产Custom Field元数据证实Shipment有custom_zmt_logistic_number/tracking/transport/dest/region/source/snapshot_date/synced_at、eta（预计到港）、atd（离港）、ata（到港）、clr（清关）、dlvr（签收）、appt（派送预约）、events/actual_progress。DN-26-00114→SHIPMENT-00050，logistic_number=91451178，tracking=879260357666，运输美森速快线、region美中、eta11/16。 | 仍有ETD/航次/港口只在description；缺统一事件类型/来源优先级/原始值与修订历史/目的仓可售ETA。SHIPMENT-00007结构化eta=11/18，事件description又含ETA11/08；event_name为空，无法不经规则直接决定哪条有效。预计到港不能当可售日。 |
| 3 | 目的仓到达（签收口径）→通途入库对账、在途关闭 | **未达（仅对账/关闭）** | 业务口径：无扫箱，**签收=默认全部到达**（`receipt_basis=signed_assumed`）；不需要目的仓实收行/逐件数量。supply-facts manifest 明确 receipt/warehouse_receipt not_integrated，`availability_schedule.available_date=null`、`eligible=false`。 | 缺的是**签收时间→通途PO入库时间**的结构化对账：`shipment_signed_at`、`tongtool_receipt_at`、`receipt_lag_days`、`stock_state`（在途/已签收待通途入库/已入库）与关闭记录。Shipment.custom_zmt_wms_in_time 不能当目的仓到达（SHIPMENT-00050 的 warehouse_in 在深圳转运中心、尚报关）；它不能用于关在途。签收状态可用于到达假设，但不能替代通途入库对账。 |
| 4 | 下单/开工/完工/出库/开船/到港/清关/入仓事件时间戳与来源 | **部分** | SO.transaction_date/Item.delivery_date；WO.planned_start_date/actual_start_date/actual_end_date；JC.actual_start_date/actual_end_date，单查可读time_logs；DN.posting_date；Shipment事件event_time/event_date/event_name/location/description/seq。supply-facts milestones有node、baseline_planned_at/committed_due_at/latest_expected_at/actual_at、qty、source_record、observed_at、date_precision/timezone_status。实测WO-26-02609 actual_start=09/01 15:16，actual_end=09/14 17:07。 | cached v10/27.7节点为order_placed/promised_delivery/production_start/production_end/dispatch/departure/arrival/delivery，尚无独立清关/目的仓实收入库节点；不少日期null，timezone_status=unverified。event_time可能是消息记录时间而非实际开船日，预计ETD不得写actual_at。完工须区分首工序完成、全工序/质检完成与真实入库。 |
| 5 | DN缺运单、运单无DN、ETA过期、阶段不明巡检 | **部分** | 旧CLI已有有计划无工单/WO回写滞后/草稿DN/交付逾期/工序停滞等机器码，含影响量、单据、owner_role、recommended_action；Shipment.match_status有Matched/Unmatched/Stale；supply-facts保留unknown、exclusion_reason及manifest覆盖状态。 | 在被审代码/接口中未见四类要求合并成一次可复算巡检：未匹配DN与Shipment全量差集、active/primary多链接冲突、ETA过期且未关闭、阶段unknown及未证目的仓分布。状态字段存在不等于已交付巡检。应给母集/成功/跳过/异常数及逐行证据，不把unknown改0、不自动补号/关在途。 |
| 6 | 只读导出/API字段稳定、分页 | **部分** | CLI支持JSON/Excel；旧REST列表默认name asc、limit_start递增、父子查询去重、in分块40、非200列表报错。生产Shipment列表实测page_length2、start0/2，得到00001/2及00003/4，无交叉。supply-facts有schema_version=supply-facts/v1、rule_version=2026-10-27.7、implementation_version、run_id、as_of、counts、coverage/restricted、partial。 | 未见该综合接口明确过滤/分页/稳定字段契约及契约测试。此次GET携sales_order=SO-26-00103&include_delivered=1，实际manifest.scope={}、返回299 SO/5166 lines；说明这个调用形式未实现期望限域，需确认正确filters格式或明确拒绝未知参数，不能默默扩大范围。旧get_single对HTTP错误可返回{}，200页上限可静默截断，JSON导出无自身schema版本/完整性manifest。分页须报告exhausted/partial并校验缺列。 |

## 独立样本与关键风险

### A. 新旧两个入口不是同一覆盖范围

`D:/Work/赛狐/Cursor/EN_API/fulfillment_query.py:17`只转到fulfillment.cli；`fulfillment/assemble.py:117`–129只取DN/WO/JC/PP；`fulfillment/stages.py:1`明确阶段4–8不产出。`FulfillmentLine`粒度SO行，`model.py:71`–91没有海外目的仓/UOM/全链事件字段；JSON虽有原始DN，不等于稳定SKU×目的仓×UOM供给接口。不要继续在这个阶段0–3输出上假定头程已接通；新`supply-facts/v1`已有更适合的字段，应统一消费适配、避免另起一套阶段算法。

### B. 首道工序完成不是成品可发证明（高风险）

`item_shipment_status.py:666`–703的done_qty取首道工序完成量；`fulfillment/stages.py:49`–56据该量达到订单量即判“生产完成待出库”。本次**纯内存**样例：订单10，裁剪Completed10，包装Open0，resolve_stage仍返回阶段3“生产完成待出库”。这不能进入已证供给。应分开生产进度、完工入库、质检/可发状态，阶段推进必须有相应证据；不能仅靠WO.status，亦不能用首工序替代完工。新supply-facts对首工序/推断量须同样保留qty_basis/置信度，未证不计入已证可售。

### C. 头程“入仓”与目的仓“入库”必须分开（最阻塞）

SHIPMENT-00050的warehouse_in为深圳转运中心10/27，尚报关；其结构化wms_in_time与预计11/16到港并存，已经证明“入仓”并非目的仓到达。该Shipment关联DN-26-00114；DN混有ND#行100件及PK#行17个，禁止跨UOM/角色相加成一个可售量。按业务口径，**签收即默认全部到达**；需要的是签收状态 + 签收时间 + 通途PO入库时间/状态，按批次对账，**不要求逐箱实收行**。credited_qty仍不得代替通途入库。

### D. 接口版本有了，但限域和完整性还需实证

新接口本次返回manifest：schema supply-facts/v1、rule2026-10-27.7、as_of10/29、run_id b5b5eb6e67364188a51caf7651484625；input/output均5166、stage_balances5993、milestones17181、availability_schedule4423、links14063、partial=true。**这些是一次非预期限域响应的样本计数，不是全EN完整性结论，也不是完成Jack验收的SKU母集。** 不继续全量拉取；请Jack先公开正确调用方式，并让响应回显生效scope/过滤器、页号/next_cursor与完整性状态。

旧分页代码证据：`item_shipment_status.py:270`–301默认稳定排序、按实收行推进，但达到200页直接退出且无partial标识；`get_single:304`–307经api_get只取data，不检查HTTP，失败可变空单据。CLI`--sleep`默认0.15仅控制部分单文档循环，列表翻页无全局限速；本次审核没有运行该CLI，使用独立全局≥250ms GET包装。

## Jack先做三件事（顺序即优先级）

1. **交付“签收→通途入库”的时间差与在途关闭。** 按业务口径，**不扫箱、不要求逐件实收，签收即默认全部到达**（`receipt_basis=signed_assumed`）。先拿10/23指定10个代表SKU及DN-26-00114/Shipment00050样本，按原始SKU×目的仓×UOM×批次输出：DN行、官方PO、Shipment分配、`shipment_signed_at`、`tongtool_receipt_at`、`receipt_lag_days`、`stock_state`（在途/已签收待通途入库/已入库）、关闭量/余额、source/observed_at。验收：一个数量只在一个状态里（未签收=在途；已签收未入库=已到未入库；通途已入库=库存）；签收后不得继续算在途，也不得同时算通途库存；无通途关联时null并单列。深圳集货入仓**不能**冒充海外到达；但海外Shipment签收可以作为到达假设。
2. **在现有Shipment与supply-facts上统一“双线进度/事件/ETA/完工证据”契约。** Shipment已有物流商爬虫与人工两条线：**以进度更靠后的一条为准**，暴露`latest_progress_status/at/source/source_updated_at/is_final/conflict_flag`；不需要爬虫原始报文。明确SO行→WO/JC→DN行→Shipment批次关联；目的仓映射独立于工厂warehouse；ETA预计到港与预计入仓/可售分列，保留计划/预计/实际、来源/优先级、消息时间与事件时间、版本修订。先处理Shipment00007两套ETA、00050深圳入仓，以及首道完成误判样例。验收：下单/开工/完工/出库/开船/到港/清关/签收八节点逐项有来源或显式未知；PK#1:1、TJ#套、ND#组件和个/套分列；未证日期/数量永不自动进入confirmed supply。
3. **交付一个有稳定过滤/分页的只读导出和同批巡检。** 公布supply-facts参数与schema，单SO查询必须回显且只含该SO，未知参数报错；分页稳定排序/游标、唯一键、分页穷尽/截断/权限失败均显式partial，不把单文档失败当空。导出附输入范围/observed_at/规则版本/哈希/行数对账；同一次快照产出DN无有效Shipment/运单、Shipment无DN、多primary、ETA过期未关闭、unknown阶段/未证目的仓五类异常及责任角色。验收：10样本先跑通、相同快照重跑一致、缺列/失败不静默、两页不漏不重，再扩Top50；不是先重拉全量或人工补号。

以上三件都是事实与只读接口工作，不含预测、采购量政策、自动写回或下单。用户已确认约3个月普通路径、多窗口/最长6个月、春节+60天应进入合适供应路径情景；不能加到需求或已到仓/已在途路径上，更不能用“SO下单+3个月”替代这次缺失的逐笔ETA证据。这里不再重做交期模型。

## GET审计与范围限制

本次生产GET共**8次**，单线程，每次前休眠0.25秒，无自动重试，全部HTTP200；凭证仅内存读取EN_API/.env，未打印/落盘。端点明细：

- GET Shipment/SHIPMENT-00007、Delivery Note/DN-26-00114、Work Order/WO-26-02609，各1次；
- GET key_test.supply_facts.get_supply_facts，携sales_order/include_delivered，1次（响应范围超出预期，已停止继续此接口）；
- GET Custom Field，dt=Shipment、字段名/标签/类型/选项，1次；
- GET Shipment/SHIPMENT-00050，1次；
- GET Shipment列表，name asc、page_length2、start0与2，各1次。

另只读10/27本地97 SO缓存，观察milestones节点覆盖和manifest外部源未接入；不是重新请求97单。本审核没有写EN/通途、修改配置/权限、运行生成/导入脚本或push；仅新增用户指定本评审文件。报告按OKF带frontmatter，未扩改索引或其他项目文件，以遵守本次只读评审范围。结论限本地被审实现与这些生产样本；未见验收产物不等于断言其他未审分支/页面绝对不存在能力。