# 运费查询示例

## POST /rate2/gofo

### curl 请求

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

### 响应

```json
{
  "carrier": "GOFO",
  "serviceType": "GOFO_PX",
  "serviceDescription": "GOFO Express 1 - Parcel",
  "isResidential": false,
  "zone": "1",
  "signature": "NO_SIGNATURE_REQUIRED",
  "currency": "USD",
  "weight": 0.0625,
  "billingWeight": 3.09,
  "dimensionsUnit": "IN",
  "amountDetails": {
    "postageAmount": 6.72
  },
  "totalAmount": 6.72,
  "estimatedDelivery": "N/A"
}
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `totalAmount` | 总运费 (USD) |
| `billingWeight` | 计费重量 (lbs)，可能与实际重量不同 |
| `zone` | 分区编码，影响运费计算 |
| `estimatedDelivery` | 预计送达日期 |

### 错误处理

- **400**: 请求参数错误，检查必填字段
- **401**: API Key 无效
