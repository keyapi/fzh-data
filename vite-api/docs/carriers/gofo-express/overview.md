# GOFO Express API 概述

## 基本信息

| 项目 | 说明 |
|------|------|
| API 名称 | GOFO Express |
| API 文档源 | `/config/gofo.yaml` |
| 基础 URL | `https://test-api.vitedirect.com` |
| 认证 | `x-api-key` 请求头 |
| 单位 | 重量: **lbs** (磅), 尺寸: **inch** (英寸) |

## 服务类型

| 服务类型 | 说明 |
|----------|------|
| `GOFO_PX` | GOFO Express 1 - Parcel |
| `GOFO_PARCEL` | 测试环境使用的包裹服务类型 |

## 渠道代码

| 渠道 | 说明 | 回标平台 |
|------|------|----------|
| `PARCEL` | 通用包裹（文档示例） | - |
| `GFUS` | GOFO US 渠道 | TEMU, TIKTOK, SHEIN, EBAY |
| `YT` | YT 渠道 | AMAZON, WALMART |

> 详细渠道映射见 [渠道代码参考](../../reference/channel-codes.md)

## API 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/rate2/gofo` | 获取运费报价 |
| POST | `/shipment2/gofo` | 创建发货标签 |
| POST | `/shipment2/gofo/batch` | 批量创建标签 |
| GET | `/shipment2/label/{orderId}` | 获取标签详情 |
| DELETE | `/shipment2/label/{requestId}` | 取消标签 |
| GET | `/user/account` | 查询账户余额 |

## 典型流程

```
Step 1: 查询运费 → POST /rate2/gofo
    ↓
Step 2: 创建标签 → POST /shipment2/gofo
    ↓
Step 3: 获取标签 → GET /shipment2/label/{orderId}
    ↓
Step 4: 打印面单 → 从 response.url 下载 PDF
```

## 注意事项

1. **requestId 必须唯一** — 建议使用 `$timestamp + $random_3_digits_number`
2. **仅支持 lbs 和 inch** — 不要使用 kg 或 cm
3. **签名确认服务不支持** — GOFO 不支持 signature 参数
4. **地址字段长度限制** — fullName ≤ 35, address1 ≤ 50, city ≤ 28, state = 2
5. **memo 长度限制** — 标签备注 ≤ 30 个字符
6. **测试数据为模拟数据** — 不代表真实价格
