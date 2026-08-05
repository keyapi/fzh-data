---
okf: v0.1
type: Research
title: 成熟尾程打单系统与开源方案调研
description: 商业系统、Karrio 与托管 API 的能力比较及 FZH 采用结论
timestamp: 2026-08-04
tags: [sellfox-shipping, shipping, karrio, reliability]
---

# 成熟尾程打单系统与开源方案调研

## 结论

FZH 当前不应替换现有系统，也不应先建设微服务或通用 Shipping SaaS。推荐组合借鉴：

- ShipStation 的仓库批次和作废工作流。
- Sendcloud 的 Webhook 重试、失败记录和费用差异处理。
- Shipium / Metapack 的候选服务解释、故障转移和 SLA 数据模型。
- EasyPost / Shippo 的异步 Batch、Manifest、Tracker 对象模型。
- Karrio 的承运商 connector 规范，但仅在复用收益达到门槛时采用。

完成态不是“调用 API 下载 PDF”，而是：同步、预检、审核、路由、购标、标签、回写核验、打印、交接、首扫、异常和账单对账。

## 产品比较

| 产品 | 最值得借鉴 | 不适合直接照搬的部分 |
|---|---|---|
| ShipStation | 操作员批次、局部成功、作废后保留历史 | 产品边界大于当前需求 |
| EasyPost / Shippo | 异步对象、Webhook、Manifest、退款状态 | 托管后端不可自行扩展承运商 |
| Sendcloud | 乱序事件、重试和失败日志、账单调整 | 欧洲 SaaS 业务模型不等同于自有物流商 |
| Shipium / Metapack | 硬约束、候选评分、落选原因、SLA | 企业级成本和复杂度过高 |
| nShift | EDI、Transmitted Batch、End-of-Day | 当前承运商数量不足以支撑引入 |
| Veeqo | 扫码复核、Manifest、退货、审计 | 会把范围扩成 WMS |

成熟系统的共同约束：下单、标签、Manifest、回写、打印、追踪和退款必须是不同状态轴；网络超时属于结果未知，不能直接重试。

## 开源与 API 方案

### Karrio

Karrio 是当前最完整的开源、自托管、多承运商候选，具备 rate、shipment、label、tracking、manifest、pickup、void 和部分 return connector。适合以独立 HTTP 服务运行，不应把 Django server 嵌入现有 FastAPI。

当前不采用 Karrio Server，原因是 VITE 和蜴国际仍需自定义适配，现有两个 API 承运商不足以抵消部署、Redis/PostgreSQL、升级和 LGPL 边界成本。

重新评估门槛：

- API 承运商达到约 5 个；或
- GLS、FedEx、UPS 等新增承运商中至少两个可复用成熟 connector；或
- 自有 connector 的字段和测试模板已经明显重复。

即使采用，Karrio 也只负责 carrier integration plane；赛狐包裹、审核、幂等、审计和回写仍归本系统。

### EasyPost / ShipEngine / Shippo

这些是商业聚合 API 的开源 SDK，不是开源后端。可作为标准承运商覆盖补充或灾备，但必须位于内部 ShippingPort 后面，不能成为本地领域模型。

ERPNext Shipping、OCA/Odoo、Medusa、Saleor 和 OpenBoxes 可借鉴 provider 或数据模型，不适合作为本项目 shipping kernel。

## FZH 采用决策

1. 保留 FastAPI 模块化单体和直接 adapter。
2. API 与 Excel 是同等级执行通道，共用预检、Attempt、Artifact、追踪和审计模型。
3. 第一优先级是解决重复标签、未知结果、孤儿运单和赛狐回写失败，而不是增加 connector 数量。
4. 当前规模先强化 SQLite；出现持续写竞争、多实例任务争用或恢复目标不满足时再迁 PostgreSQL。
5. 装箱算法延期。当前尺寸语义和数量高度问题作为独立后续任务，不混入可靠性 PR。

## 主要来源

- [ShipStation Batch Shipping](https://help.shipstation.com/hc/en-us/articles/360035969752-Introduction-to-Batch-Shipping)
- [ShipStation Void Labels](https://help.shipstation.com/hc/en-us/articles/360026157751-Void-Labels)
- [EasyPost Webhooks](https://docs.easypost.com/guides/webhooks-guide)
- [EasyPost ScanForm](https://docs.easypost.com/docs/scan-form)
- [Shippo Webhooks](https://docs.goshippo.com/docs/tracking/webhooks)
- [Sendcloud Parcel Webhooks](https://sendcloud.dev/api/v3/webhooks/parcel-status-changed)
- [Shipium Evaluated Service Methods](https://docs.shipium.com/docs/evaluated-service-methods)
- [Metapack Carrier Allocation Rules](https://help.metapack.com/hc/en-gb/articles/360008988538-Carrier-Allocation-Rules)
- [Karrio repository](https://github.com/karrioapi/karrio)
- [AWS Transactional Outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
