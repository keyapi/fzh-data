# USPS V2 API 概述

## 基本信息

| 项目 | 说明 |
|------|------|
| API 文档源 | `/swagger-config.yaml` |
| 基础 URL | `https://test-api.vitedirect.com` |
| 认证 | `x-api-key` |

## 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/rate2/usps` | 查询 USPS 运费 |
| POST | `/shipment2/usps` | 创建 USPS 标签 |
| POST | `/shipment2/usps/batch` | 批量创建 USPS 标签 |
| GET | `/shipment2/label/{orderId}` | 获取标签 |
| DELETE | `/shipment2/label/{requestId}` | 取消标签 |
| GET | `/user/account` | 账户余额 |

## 注意事项

- USPS 标签取消有 **60 天** 限制
- 签名确认服务 **不支持**
- 支持地址标准化校验
