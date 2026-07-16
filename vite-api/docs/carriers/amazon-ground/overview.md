# Amazon Ground API 概述

## 基本信息

| 项目 | 说明 |
|------|------|
| API 文档源 | `/config/amazon.yaml` |
| 基础 URL | `https://test-api.vitedirect.com` |
| 认证 | `x-api-key` |
| 服务类型 | `AMAZON_GROUND` |
| 渠道 | `PARCEL` |

## 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/rate2/amazon` | 查询 Amazon 运费 |
| POST | `/shipment2/amazon` | 创建 Amazon 标签 |
| POST | `/shipment2/amazon/batch` | 批量创建标签 |
| GET | `/shipment2/label/{orderId}` | 获取标签 |
| DELETE | `/shipment2/label/{requestId}` | 取消标签 |

## 注意事项

- Amazon 签名确认服务 **不支持**
- Amazon 标签取消有 **60 天** 限制
