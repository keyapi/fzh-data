# 创建标签示例

## POST /shipment2/gofo

### curl 请求

```bash
curl -X POST "https://test-api.vitedirect.com/shipment2/gofo" \
  -H "x-api-key: H5se84hM6Y34Kx2XjfRzg16t6wXSJydq6Bxk1Kzd" \
  -H "Content-Type: application/json" \
  -d '{
    "requestId": "1689480000123",
    "serviceType": "GOFO_PX",
    "channel": "GFUS",
    "shipDate": "2025-07-14",
    "memo": "test_memo",
    "reference": "ORDER-001",
    "from": {
      "zipCode": "02478",
      "fullName": "Elbert Chen",
      "address1": "90 Chester rd Belmont",
      "city": "Boston",
      "state": "MA",
      "phoneNumber": "1111111111"
    },
    "to": {
      "zipCode": "03053-7414",
      "fullName": "Wilson Wu",
      "address1": "55 Harvey Rd",
      "city": "Londonderry",
      "state": "NH",
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
  "status": "pending",
  "requestId": "1689480000123",
  "orderId": "PPGF-1689480000123-1753253592246",
  "carrier": "GOFO",
  "serviceType": "GOFO_PX",
  "channel": "GFUS",
  "serviceDescription": "GOFO Express 1 - Parcel",
  "isResidential": false,
  "zone": "8",
  "amountDetails": {
    "postageAmount": 6.72
  },
  "signature": "NO_SIGNATURE_REQUIRED",
  "totalAmount": 6.72,
  "currency": "USD",
  "weight": 0.0625,
  "billingWeight": 0.0625,
  "weightUnit": "LBS",
  "dimensionsUnit": "IN",
  "currentBalance": 998716869.47
}
```

### 关键字段

| 字段 | 说明 | 用途 |
|------|------|------|
| `orderId` | 标签订单ID | 后续查询/获取标签时使用 |
| `requestId` | 请求ID | 取消标签时使用 |
| `currentBalance` | 当前余额 | 扣费后快照 |
| `totalAmount` | 本单费用 | 扣费金额 |

### requestId 生成建议

```javascript
// requestId = 时间戳 + 3位随机数
const requestId = Date.now() + Math.floor(Math.random() * 900 + 100).toString();
// 示例: "1689480000123"
```

### 注意事项

- `requestId` 必须全局唯一，重复会导致请求失败
- 标签创建后状态为 `pending`，需要通过 `GET /shipment2/label/{orderId}` 获取最终状态和PDF链接
