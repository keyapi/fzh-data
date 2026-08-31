---
okf: v0.1
type: Research
title: 开源物流方案复用档案与先搜再造执行规范
description: erpnext-shipping、Karrio、Huey、OCA、OpenBoxes 的成熟度与可复用模块评估，以及后续任务包的 Search-before-Build 准入清单
timestamp: 2026-08-07
tags: [sellfox-shipping, open-source, reuse, karrio, erpnext-shipping, huey, outbox]
---

# 开源物流方案复用档案与先搜再造执行规范

## 结论

继续保留 FastAPI + SQLAlchemy + SQLite 单体，不整体安装任何 ERPNext/Odoo shipping 应用或 Karrio Server。直接复用成熟的通用机制，保留本地业务事实与安全状态。`erpnext-shipping` 是 MIT 的活跃项目，适合作为适配器分层、报价归一化、标签/跟踪流程和失败补偿测试场景的参考，不适合作为本项目的运行时依赖。

## 严格评估结果

| 项目 | License | 活跃度 | 领域覆盖 | 结论 |
|---|---|---|---|---|
| [frappe/erpnext-shipping](https://github.com/frappe/erpnext-shipping) | MIT | 活跃，v16.0.0（2026-07-06），version-14/15/16 | ERPNext 内的 Packlink/LetMeShip/SendCloud 多平台 shipping | Adapt / Reference |
| [Karrio](https://github.com/karrioapi/karrio) | 仓库 NOASSERTION（核心/EE 多许可，需逐组件核对） | 活跃 | 多承运商 rate/shipment/label/tracking/manifest/void | Reference，达到门槛再 POC |
| [Huey](https://github.com/coleifer/huey) | MIT | 活跃（2026-08-05） | SQLite/Redis/Postgres 任务队列、锁、限速、计划任务 | 未来 Adopt 为 Worker 外壳 |
| [OCA/delivery-carrier](https://github.com/OCA/delivery-carrier) | AGPL-3.0 | 活跃（2026-08-05） | Odoo 承运商、标签附件、包裹约束、跟踪状态 | Reference，不复制 AGPL 代码 |
| [OpenBoxes](https://github.com/openboxes/openboxes) | EPL-1.0 | 活跃，119 releases | WMS、发运、交接、差异处理 | Reference 工作流 |
| [outbox-streaming](https://github.com/hyzyla/outbox-streaming) | MIT | 2023 后基本停滞，规模小 | SQLAlchemy 事务 Outbox 示例 | Reject 为生产依赖 |

## erpnext-shipping 重点档案

- 仓库：`frappe/erpnext-shipping`；MIT；默认 `develop`；分支 `master`、`version-14`、`version-15`、`version-16`；v16.0.0 于 2026-07-06 发布。
- 核心文件：
  - `erpnext_shipping/erpnext_shipping/shipping.py`：`fetch_shipping_rates` 多承运商报价聚合、`create_shipment`、`print_shipping_label`、`update_tracking`。
  - `erpnext_shipping/erpnext_shipping/utils.py`：地址/电话校验、tracking URL 模板、`match_parcel_service_type_carrier` 服务别名归一化。
  - `doctype/sendcloud/sendcloud.py`：多包裹逐条创建、部分失败补偿取消、标签下载、tracking 拉取。
  - `doctype/letmeship/letmeship.py`、`doctype/parcel_service_type*`：服务与承运商别名模型。
- 可直接借鉴的测试场景：报价聚合时单承运商失败不阻断整体；多包裹部分成功后补偿取消；标签缺失 URL；tracking 接口字段变化；地址必填与电话格式；服务别名映射。
- 不直接依赖的原因：深度耦合 Frappe DocType、hooks、`frappe.db` 与 UI RPC；其 retry/UNKNOWN/人工恢复模型弱于本项目现有 operation/scope/outbox；部分实现有宽泛异常捕获和绕过地址校验的 hack，不符合本项目安全边界。

## Karrio 复用边界

- 不嵌入 Django server；只借鉴 connector 分层：`mapper` 负责协议适配、`proxy` 负责 HTTP、`provider` 负责业务逻辑、`units` 负责服务/包装/跟踪状态归一化。
- 借鉴 schema 生成与 fixture 纪律：请求/响应样例文件先于代码，生成类型不可手改，测试用真实样例驱动。
- 引入门槛保持为：约 5 个 API 承运商，或 GLS/FedEx/UPS 至少两个可复用成熟 connector，或自有 connector 模板明显重复。
- 若未来引入，Karrio 只作为 carrier integration plane；包裹审核、幂等、审计、赛狐回写仍留在本系统。

## Huey 边界

- 未来需要常驻 Worker 时采用 Huey 作为调度外壳，任务只传 operation/outbox ID，不在队列里传业务全量对象。
- 领域状态仍由本项目 SQLite 状态机保存；Huey 只负责领取、锁、退避和计划执行。
- 不提前引入：当前 CLI `run-once` 已满足低于 500 包/日与人工/AI 触发场景。

## 每任务包 Search-before-Build 准入清单

后续任何核心任务包开始编码前，必须先产出该包的复用档案并记录到本目录：

1. 候选项目与具体文件/API 证据。
2. 许可证与引用/复制边界。
3. 本地缺口与该候选重叠的部分。
4. 可移植测试场景清单。
5. Adopt / Adapt / Reference / Reject 结论与理由。

优先级：

- 承运商 connector 架构与报价聚合。
- 取消/退款生命周期。
- tracking/Webhook 乱序与去重。
- 三方对账与成本差异。
- Worker 调度。
- 打印交接、Manifest 与首扫。
- 赛狐回写 Outbox 的幂等与冲突保护（已有设计，继续按真实探针校准管制强度）。

## 赛狐写回管制强度校准

Outbox 不因“重复写回会扣钱”而存在；其价值是区分已发送/未发送、保护新 tracking 不被旧值覆盖、按订单独立失败、保留审计和回读。若真实探针证明相同 `order_id + tracking` 可安全重复提交且无平台副作用，应保留 Outbox 的投递/去重/冲突保护，但去掉不必要的逐条人工审批和永久 `UNKNOWN_BLOCKED`。若探针证明会触发平台推送或状态变化，则维持强管制。当前先由 Jack 在用户指定的全新包裹上完成单包能力探针。

## 来源

- [frappe/erpnext-shipping GitHub](https://github.com/frappe/erpnext-shipping)
- [frappe/erpnext-shipping release v16.0.0](https://github.com/frappe/erpnext-shipping/releases)
- [Karrio Carrier Integration Guide](https://github.com/karrioapi/karrio/blob/main/CARRIER_INTEGRATION_GUIDE.md)
- [Huey GitHub](https://github.com/coleifer/huey)
- [OCA delivery-carrier GitHub](https://github.com/OCA/delivery-carrier)
- [OpenBoxes GitHub](https://github.com/openboxes/openboxes)
- [outbox-streaming GitHub](https://github.com/hyzyla/outbox-streaming)
