# Vite API 渠道代码映射

## 概述

渠道代码用于标识不同的物流服务和回标平台。当前测试环境使用 GOFO Express 服务的以下配置。

## 服务类型

| 服务类型 | 说明 |
|----------|------|
| `GOFO_PARCEL` | GOFO Express 包裹服务（测试环境使用） |
| `GOFO_PX` | GOFO Express 1 - Parcel（API 文档示例） |

## 渠道代码

| 渠道代码 | 说明 | 支持的回标平台 |
|----------|------|----------------|
| `GFUS` | GOFO US 渠道 | TEMU, TIKTOK, SHEIN, EBAY |
| `YT` | YT 渠道 | AMAZON, WALMART |

## 平台与渠道对照表

| 平台 | 渠道代码 | 服务类型 | 备注 |
|------|----------|----------|------|
| TEMU | GFUS | GOFO_PARCEL | 回标标签 |
| TIKTOK | GFUS | GOFO_PARCEL | 回标标签 |
| SHEIN | GFUS | GOFO_PARCEL | 回标标签 |
| EBAY | GFUS | GOFO_PARCEL | 回标标签 |
| AMAZON | YT | GOFO_PARCEL | 回标标签 |
| WALMART | YT | GOFO_PARCEL | 回标标签 |

## 请求示例

```json
{
  "serviceType": "GOFO_PARCEL",
  "channel": "GFUS",
  "shipDate": "2025-07-14",
  "from": { ... },
  "to": { ... },
  "packages": [
    {
      "weight": 2,
      "length": 1,
      "width": 1,
      "height": 1
    }
  ]
}
```

## 注意事项

- 测试环境渠道代码可能与生产环境不同
- 渠道可用性请联系 Vite 客户经理确认
- GOFO 签名确认服务 **不支持**
