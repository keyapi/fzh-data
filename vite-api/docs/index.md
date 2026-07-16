# Vite API 文档索引

## 快速入门

- [环境配置](quickstart/01-environment-setup.md)
- [首次运费查询](quickstart/02-first-rate-query.md)
- [首次创建标签](quickstart/03-first-label.md)

## 参考文档

- [凭证参考](reference/credentials.md)
- [渠道代码映射](reference/channel-codes.md)
- [公共请求头](reference/common-headers.md)
- [错误码参考](reference/error-codes.md)
- [单位与限制](reference/units-and-limits.md)
- [Webhook 载荷参考](reference/webhook-payloads.md)

## 承运商文档

- [承运商索引](carriers/index.md)
- **GOFO Express** (主要承运商)
  - [概述](carriers/gofo-express/overview.md)
  - [端点参考](carriers/gofo-express/endpoints.md)
  - 示例: [运费查询](carriers/gofo-express/examples/rate-request.md) | [创建标签](carriers/gofo-express/examples/create-label.md) | [批量创建](carriers/gofo-express/examples/batch-labels.md) | [获取标签](carriers/gofo-express/examples/get-label.md) | [取消标签](carriers/gofo-express/examples/cancel-label.md) | [账户余额](carriers/gofo-express/examples/account-balance.md)
- [USPS V2](carriers/usps/overview.md)
- [FedEx](carriers/fedex/overview.md)
- [UPS](carriers/ups/overview.md)
- [Amazon Ground](carriers/amazon-ground/overview.md)
- [EEI](carriers/eei/overview.md)
- [Tracking](carriers/tracking/overview.md)

## 回标标签

- [平台/渠道映射](return-labels/platform-mapping.md)
- [回标标签流程](return-labels/return-label-flow.md)
- 示例: [TEMU 回标](return-labels/examples/temu-return.md) | [Amazon 回标](return-labels/examples/amazon-return.md)

## Webhook

- [配置指南](webhooks/setup-guide.md)
- [载荷参考](webhooks/payload-reference.md)
- 示例: [标签通知](webhooks/examples/label-notification.md)

## 测试指南

- [测试环境说明](test-guide/test-environment.md)
- [测试凭证](test-guide/test-credentials.md)
- [测试场景](test-guide/test-scenarios.md)
- [测试数据注意事项](test-guide/test-data-tips.md)

## 其他

- [集成经验教训](lessons/2026-07-16-integration-lessons.md)
- [API 探索研究](research/2026-07-16-vite-api-exploration.md)
- [集成方案设计](specs/2026-07-16-integration-design.md)
- [变更日志](log.md)
