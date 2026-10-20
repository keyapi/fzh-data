---
okf: v0.1
type: Research
title: 头程供应商数据接入与 ERPNext 销售出库关联
timestamp: 2026-10-20
tags: [freight, ocean, integration, ERPNext, tracking]
---

# 头程供应商数据接入与 ERPNext 销售出库关联

调研边界：只看底层物流进度数据如何读入，以及如何与 ERPNext 销售出库/订单行建立可追溯关联。用户说明PJ曾对接若干头程供应商（提及“智美通”），Jack正在整理敏感资料；尚无已交付接口、PR 或经验证供应商账号。本次未访问账户、未调用 API、未安装软件、未使用真实单号或凭证。访问日 2026-10-20。

## 结论

先把本地数据契约和文件导入兜底做好，等供应商交出接口资料后再选 API、Webhook、EDI 或文件方式。已有公开接口文档只证明产品存在相应接口，不代表公司租户、订阅、航线或承运商已开通。当前无法确认“智美通”对应的唯一法人/产品，也没有定位到可归属该主体的公开官方开发者文档；不推断它没有 API，也不猜字段。请 PJ/Jack 回传主体全称/官网域名与供应商提供的接口说明，之后再确认。

头程应以运输批次/Shipment 和运输事件为事实粒度，通过明确分摊把货量落到 ERPNext Delivery Note Item 行；DN Item 的 `so_detail` 指向 Sales Order Item 行，`against_sales_order` 指向 Sales Order 头。不是给 Sales Order 填一个 ETA 或船名：一票货可能含多个柜，一柜可能拼多 SO/DN 行，一条 DN 行也可能拆多批。先以只读适配层保存源事件、外部 ID、更新时间和原始来源；匹配不确定的记录进入待人工确认队列。EN Delivery Note 是工厂对客户出库并扣库存的单据，不是海运承运人的事件账本。[R10][L1][L2]

## 接入路线比较

| 路线 | 适用条件与可见粒度 | 授权/更新/限制 | 对本项目的判断 |
|---|---|---|---|
| 供应商/货代 API 或 Webhook | 供应商能用 booking、MBL/HBL、container 等 ID 查事件；支持 push 时由 webhook 传变化 | 每个供应商有自己的订阅、速率、覆盖线路和权限；必须拿到版本化 schema、测试端点和限额。API 文档不是本公司账号可用证明 | 优先问 PJ/Jack 是否可授权只读测试；事件接收端保留重复、迟到、乱序和撤销修正能力。 |
| 船公司 API / DCSA T&T | 直订船司且拿到其客户权限时可按预订、提单或设备标识取船期/里程碑；DCSA 可统一事件语言 | DCSA 是标准，不是免费聚合数据服务；船司是否实现某个版本及允许该客户订阅仍需确认。2.2 包含订阅回调概念，具体字段按发布方 OpenAPI | 作为字段/事件规范参考；不要假设所有货代都提供 DCSA endpoint。[R1][R2] |
| 第三方聚合商（project44、SeaRates 等） | 当供应商覆盖分散且能给到通用识别码时，单一连接层可能返回多承运商海运事件 | project44 文档要求 API client、tenant permissions、区域端点，货代管理货件还有附加权限；SeaRates 官方 API 文档直接打开失败，搜索摘要不作为正文核实。覆盖、时效、价格、历史保存和数据权利均须商务/账户核对 | project44 可进入只读契约验证候选；SeaRates 先取得可读官方文档/账号资格再评估。[R5][R6] |
| 货代 TMS（GoFreight / CargoWise） | 若对方自用该 TMS，可能通过客户 API/Webhook/EDI 提供货代内部作业节点 | CargoWise 页面描述 API/EDI/表格等互联，但 eAdaptor 详细规格/租户配置需客户门户或供应商提供。GoFreight 开发页正文打开为空，仅有搜索摘要线索，字段、授权、限额待核。必须识别供应商实际使用哪套 TMS | 只有拿到“供应商实际使用该系统+授权路径+可读字段样例”才进入接口设计；GoFreight 摘要不当作已验证 schema。[R7][R8] |
| EDI / SFTP / 邮件附件 / 共享表 | 供应商无 API 或未开放权限时，周期性文件可先承载进度与关联键 | 各家 EDI 事务集、列名和更新时间不同；文件有重复发送、迟到更正和编码问题 | 最实用兜底：明确模板版本、批次号、来源文件哈希和导入报告；原文件存档，未匹配行不丢弃。不要因形式旧就排除，它可能是供应商唯一实际可用接口。 |
| AIS 船位开源组件/数据 | 只能从 AIS feed 得到船舶位置/航速等船级观测，适用于查看船舶是否靠近港口 | AisTrack 可接入 AIS 数据流并提供 Java/REST 查询代码（Apache-2.0），但 AIS 数据源另行获取/授权；船名或 MMSI 到具体货柜/提单的关联不由 AIS 自身解决 | 仅可做 toy/独立船位补充，不能替代 booking/柜/提单里程碑、清关、卸柜、还空或仓库签收。[R11] |

### 官方接口有据，不等于我们可用

公开可读正文已确认 Maersk 要求通过客户门户/销售代表取得 API 接入细节，project44 要 active client ID/secret、tenant feature permissions 和区域 endpoint。CargoWise 的页面只证明它支持若干连接方式，不能推导账户级 eAdaptor schema。SeaRates 和 GoFreight 的官方开发文档 URL 本次未能取得正文，故其 API key、subscription、限额或具体事件字段不作为已核事实。所有候选都必须由供应商/客户管理员确认本账号实际 entitlement、线路覆盖、rate limit、保留期限和测试环境。[R4][R5][R6][R7][R8]

“实时”也需按产品原文理解。project44 文档说明海运信息异步处理，刚创建后不一定立刻出现；SeaRates/GoFreight 具体更新 SLA 本次未从正文核实。接口形式和刷新频率应记在来源元数据，不应把最新查询时间当成事件发生时间。[R5][R6][R7]

## 智美通与同行接口确认清单

**智美通：主体仍未知。** 搜索同名和“智美通 物流/API/海运”未获得足以确认唯一主体的官方开发者页面，现有本地业务蓝图只提到人工登记的 ZM 海运号和钉钉表，不是 API 证据。PJ/Jack 对接时请一次性带回：

- 法人全称、官方域名、具体物流产品/客户门户名称；“智美通”是货代、平台、服务品牌还是货代所用 TMS。
- 合同/账号实际签约主体；接口是承运人直连、TMS 导出、EDI、API、Webhook 还是人工 Excel/邮件。接口/API 是否需要增购、申请白名单/开通模块，以及测试环境流程；价格只按正式报价记录，不估价。
- 可提供的外部主键：订单/booking reference、MBL/HBL、箱号、船名/航次、供应商自定义运输批次号；哪些允许一票多柜、拼柜/分票与改提单。
- 事件字段字典：原始事件代码/描述、计划或实际、事件发生时区、更新时间/修订号、地点/UN/LOCODE、源系统、取消/更正标志；预计更新频率、历史回溯窗口、限流及 429 处理约定。
- 脱敏 API/EDI schema、1–2 条合成或遮盖标识的 sandbox 样本、Webhook 签名算法/重试规则，或版本化文件模板。任何账号凭证另走批准的秘密管理通道，不放文档/PR。

同一清单适用于其他货代/船司。若只能从页面人工查，就将页面导出/人工表列为初版文件连接器；不把浏览器抓取当官方 API。

## 建议的适配层和 EN 关联模型

```text
供应商 API / webhook / EDI / CSV
   → provider adapter + raw envelope archive
   → normalized freight shipment / leg / event
   → explicit allocation (DN Item / SO Item / quantity)
   → EN read-only view + unmatched/review queue
```

- `freight_shipment`: 本地 UUID、provider/system、provider account、运输批次号、货代 job ID、booking/MBL/HBL、目的地、运输模式、首见/末见时间。
- `freight_equipment`: 船司/设备来源、柜号、seal（敏感业务按访问策略脱敏）、船名/航次、箱型。一个 shipment 多柜；一个柜可关联多个运输 leg。
- `freight_event`: provider 原事件 ID/code/文本、标准事件族、planned/actual、地点、event time + timezone、provider updated time、ingested_at、修订/取消标记、payload hash、源文件/API request reference。保留原事件，不只留被映射后的“状态”。
- `freight_allocation`: `freight_shipment/equipment ↔ Delivery Note Item.name`，分摊数量/UOM、依据、匹配置信等级、确认人/时间。DN Item 的 `name` 是自身行 ID；DN Item 的 `so_detail` 指向 Sales Order Item.name，`against_sales_order` 指向 SO 头。允许多对多，守恒校验为分配量不超对应 DN 出库量；未分配和超额显式列出。
- 本地规则指出头程要用 ERPNext `Sales Order.name` 查钉钉表；本地 `po_no` 是内部流转号，不应默认或单独作为头程唯一键。若供应商明确把它作为外部 ref 且样例/账号数据验证映射稳定，可作为附有来源的参考之一。分摊以 DN 行为主，SO 是追溯上层，不用 SO 头替代 DN 行分摊。[L1][L2]
- 关联优先级：供应商明确 shipment/batch ID → booking/MBL/HBL/container 与人工确认的 DN Item 分配 → 通过 DN Item `so_detail` 追溯 SO Item，或通过 DN Item `against_sales_order` 追溯 SO；仅客户名、日期、仓库、件数相同只能产生候选，不能自动绑定。匹配规则带版本、证据、操作者和时间，记录一对多冲突。

不建议先改 ERPNext 的库存交易。可在隔离开发环境用自定义 DocType/API 或独立只读数据库接入，但具体部署位置等接口和字段稳定后再定。ERPNext 的 Delivery Note 能表示仓库发货、分批出库、SO 关联和库存扣减，Ship/Tracking 对象仍需要扩展或外部表承载海运多段运输事件。[R10]

## 轮询、Webhook、文件与数据血缘

- 每供应商独立 adapter、凭证 scope、限速器和运行游标；所有请求使用指数退避/随机抖动，遵守响应 `Retry-After` 和合同频率。生产频率不能从其他供应商/聚合商的示例推断。
- API 轮询以供应商更新游标/更新时间做重叠窗口回查；webhook 先验签、落原文、快速返回，再异步归一。处理重复、乱序、迟到和更正：事件发生时间与上游更新时间分开，不因较老 event time 丢弃较新修订。
- 事件幂等键优先取供应商事件 ID；没有该 ID 时用 `(provider, external shipment ID, event code, event time, location, revision)` 的规范化哈希，并保留原始 payload hash。若源状态被覆盖而不提供事件 ID/修订号，标记低置信度并周期性快照，不假装还原完整历史。
- 文件兜底使用明确列映射版本、时区/UOM规范、源文件名/文件 hash、导入批次 ID、读取时间和导出时间。每批报告总行/新增/重复/更新/未匹配/格式失败数，保留原文件及异常行；相同文件重放应无副作用。
- 血缘：`provider account → source object/key → fetch/run ID → raw payload/file → normalized row → match decision → EN link → report`；每个 ETA/实际节点都可回钻来源和观察时刻。禁止把模型推算 ETA 写成承运人事实。

## 现在可做的无账号试验

可以直接做玩具数据契约测试，不等待 PJ/Jack：构造 2 个合成 Sales Order、3 条 DN Item，其中一条 DN 行分成两条海运 allocation，一柜含两条 DN 行；事件包含 planned ETD、actual departure、ETA 修订、ATA、重复投递、乱序 arrival、未知 MBL、缺箱号和同一柜多批记录。验证：

1. 导入 CSV 与模拟 API/Webhook envelope 均归一成同一事件对象，重复投递幂等、原始值可回查。
2. 一票多柜/多 SO、拆票/拼柜及 DN 部分出库不重不漏；运输数量与 DN Item 数量对账，超额、未知引用、缺时区都进异常表。
3. 事件发生时间和源更新时间分离；ETA 变更追加历史，不能覆盖成“原来就这样”；取消事件不删除事实。
4. `Sales Order.name` / DN Item `name` / DN Item `so_detail` / DN Item `against_sales_order` 关联方向正确；`po_no` 默认不作为头程唯一键，只有明确业务证明后才作为附加引用；人工确认前只有候选，不触碰 EN。

这只能验证本地适配契约和语义，不能验证供应商真实 API、账号授权、字段覆盖或事件时效。真实接口验证必须等 PJ/Jack 提供官方文档、测试账户/导出样例及授权范围。

## 可选路线及边界

| 资产 | 可做什么 | 做不到/不建议 |
|---|---|---|
| ERPNext | Sales Order、Delivery Note Item、库存及订单引用是内部出库/销售事实；REST API 可在授权范围读写 DocType | 原生 Delivery Note 不是多段海运跟踪平台；不能默认存在第三方船司事件、批次分摊、修订时间线。初期只读挂接 |
| OpenBoxes | Lift 官方文档列采购、库存移动、inbound shipment/收货和 stock movement API；本次未在此来源集中复核自托管版代码许可 | 偏仓内物资流，不是面向本公司海运提单/柜事件的跨货代聚合网络；不替代 EN 的 SO/DN 关联 |
| DCSA | 提供海运 T&T 事件语义/接口规范与 conformance sandbox | 是行业标准而非 carrier feed、商业 API entitlement 或覆盖承诺；必须由发布方实际实现并开通 |
| AisTrack (Apache-2.0) | 可自建接收/合并 AIS feed 的船只位置查询组件 | 没有 AIS feed 就无数据；无货柜/提单/EN 行分配或清关、签收语义，作为主方案淘汰 |
| project44 / SeaRates / GoFreight | project44 海运接口正文可读，可作聚合候选；SeaRates/GoFreight 官方文档正文当前失败/待核 | 授权、成本、承运商覆盖、事件 SLA 需按公司账号报价/试用；未证实智美通或现有货代实际支持 |

所有路线中已验证的只有公开文档和接口能力描述。本次没有拿真实货件查询、没有建立生产连接、没有联系供应商，也没有声称 EN 已存储头程事件。

## 证据边界

关键结论与逐项来源记录见 [sources-freight-connectors.md](sources-freight-connectors.md)。一手来源优先选择 DCSA、船司、产品官方 API/支持页、OpenBoxes/ERPNext 官方文档或官方代码仓。FourKites 开发门户仅能打开登录墙，未把搜索摘录当接口字段证据；智美通未定位到可确认主体的官方接口页面。未使用 UPS/FedEx/AfterShip 尾程包裹 API 推导海运进度，也未推测任何供应商价格、字段或合同覆盖。
