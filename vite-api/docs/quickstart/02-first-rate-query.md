# 首次运费查询

## 目标

使用 Vite API 查询 GOFO Express 的运费报价。

## 请求

```bash
curl -X POST "https://test-api.vitedirect.com/rate2/gofo" \
  -H "x-api-key: <your-vite-api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "shipDate": "2025-07-14",
    "serviceType": "GOFO_PX",
    "channel": "GFUS",
    "from": {
      "fullName": "Easy tech INC",
      "address1": "1715 E Grevillea Ct",
      "city": "NEWHALL",
      "state": "CA",
      "zipCode": "91321",
      "phoneNumber": "1111111111"
    },
    "to": {
      "fullName": "Wilson",
      "address1": "55 Harvey road",
      "city": "Londonderry",
      "state": "NH",
      "zipCode": "03053",
      "phoneNumber": "1111111111"
    },
    "packages": [
      {
        "weight": 2,
        "length": 1,
        "width": 1,
        "height": 1
      }
    ]
  }'
```

## 响应解析

```json
{
  "carrier": "GOFO",
  "serviceType": "GOFO_PX",
  "totalAmount": 6.72,
  "billingWeight": 3.09,
  "amountDetails": {
    "postageAmount": 6.72
  }
}
```

| 字段 | 值 | 说明 |
|------|-----|------|
| `totalAmount` | 6.72 USD | 预估运费 |
| `billingWeight` | 3.09 lbs | 计费重量（可能 > 实际重量） |
| `postageAmount` | 6.72 USD | 邮资金额 |

## 常见问题

### Q: 400 Bad Request
- 检查必填字段是否完整
- 检查字段长度是否超标
- 确认使用了 lbs/inch 单位

### Q: 401 Unauthorized
- 确认 `x-api-key` 请求头已添加
- 确认 API Key 值正确
