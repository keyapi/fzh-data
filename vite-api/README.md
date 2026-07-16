# Vite API 集成文档

## 概述

FZH 公司 Vite 发货 API 集成项目。支持多承运商（GOFO Express、USPS、FedEx、UPS、Amazon Ground）的发货标签创建、运费查询和回标标签管理。

## 主要承运商

| 承运商 | 状态 | 用途 |
|--------|------|------|
| **GOFO Express** | ★ 已完成 | 回标标签 (TEMU/TIKTOK/SHEIN/EBAY/AMAZON/WALMART) |
| USPS V2 | ○ 基础文档 | 美国国内发货 |
| FedEx V2 | ○ 基础文档 | 国内+国际发货 |
| UPS V2 | ○ 基础文档 | 国内+国际发货 |
| Amazon Ground | ○ 基础文档 | Amazon 发货 |
| EEI | ○ 基础文档 | 出口申报 |
| Tracking | ○ 基础文档 | 包裹追踪 |

## 快速开始

```bash
# 测试连通性
curl -X GET "https://test-api.vitedirect.com/user/account" \
  -H "x-api-key: H5se84hM6Y34Kx2XjfRzg16t6wXSJydq6Bxk1Kzd"
```

## 文档目录

| 路径 | 说明 |
|------|------|
| [docs/quickstart/](docs/quickstart/index.md) | 快速入门指南 |
| [docs/reference/](docs/reference/index.md) | 参考文档 |
| [docs/carriers/gofo-express/](docs/carriers/gofo-express/index.md) | GOFO Express 详细文档 |
| [docs/return-labels/](docs/return-labels/index.md) | 回标标签文档 |
| [docs/webhooks/](docs/webhooks/index.md) | Webhook 配置 |
| [docs/test-guide/](docs/test-guide/index.md) | 测试指南 |
| [docs/specs/](docs/specs/2026-07-16-integration-design.md) | 集成方案设计 |

## 相关链接

- API 文档: http://docs.vitedirect.com/
- 测试系统: https://easygo-dev.vitedirect.com/labelHistory
- 技术支持: support@viteusa.com

## 注意事项

- API 仅接受 **lbs** (磅) 和 **inch** (英寸)
- 所有请求需携带 `x-api-key` 请求头
- 当前文档基于测试环境，生产环境需更新凭证和 URL
