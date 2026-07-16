# FedEx API 概述

## API 分组

| 分组 | 文档源 |
|------|--------|
| FedEx V2 (国内) | `/config/fedex.v2.yaml` |
| FedEx International | `/config/fedexInternational.yaml` |

## 基本信息

| 项目 | 说明 |
|------|------|
| 基础 URL | `https://test-api.vitedirect.com` |
| 认证 | `x-api-key` |

## 端点（国内）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/rate2/fedex` | 查询 FedEx 运费 |
| POST | `/shipment2/fedex` | 创建 FedEx 标签 |
| POST | `/shipment2/fedex/batch` | 批量创建 FedEx 标签 |

## 端点（国际）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/rate2/fedex/international` | 查询国际运费 |
| POST | `/shipment2/fedex/international` | 创建国际标签 |

> 通用端点（获取标签、取消标签、余额查询）与 GOFO 共用
