# UPS API 概述

## API 分组

| 分组 | 文档源 |
|------|--------|
| UPS V2 (国内) | `/config/ups.v2.yaml` |
| UPS International | `/config/upsInternational.yaml` |

## 基本信息

| 项目 | 说明 |
|------|------|
| 基础 URL | `https://test-api.vitedirect.com` |
| 认证 | `x-api-key` |

## 端点（国内）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/rate2/ups` | 查询 UPS 运费 |
| POST | `/shipment2/ups` | 创建 UPS 标签 |
| POST | `/shipment2/ups/batch` | 批量创建 UPS 标签 |

## 端点（国际）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/rate2/ups/international` | 查询国际运费 |
| POST | `/shipment2/ups/international` | 创建国际标签 |

> 通用端点（获取标签、取消标签、余额查询）与 GOFO 共用
