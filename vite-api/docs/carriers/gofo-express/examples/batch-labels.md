# 批量创建标签示例

## POST /shipment2/gofo/batch

### curl 请求

```bash
curl -X POST "https://test-api.vitedirect.com/shipment2/gofo/batch" \
  -H "x-api-key: H5se84hM6Y34Kx2XjfRzg16t6wXSJydq6Bxk1Kzd" \
  -H "Content-Type: application/json" \
  -d '{
    "shipments": [
      {
        "requestId": "1689480000123",
        "serviceType": "GOFO_PX",
        "channel": "GFUS",
        "shipDate": "2025-07-14",
        "memo": "order_001",
        "reference": "ref-1",
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
      },
      {
        "requestId": "1689480000456",
        "serviceType": "GOFO_PX",
        "channel": "GFUS",
        "shipDate": "2025-07-14",
        "memo": "order_002",
        "reference": "ref-2",
        "from": {
          "zipCode": "02478",
          "fullName": "Elbert Chen",
          "address1": "90 Chester rd Belmont",
          "city": "Boston",
          "state": "MA",
          "phoneNumber": "1111111111"
        },
        "to": {
          "zipCode": "10001",
          "fullName": "John Doe",
          "address1": "123 Main St",
          "city": "New York",
          "state": "NY",
          "phoneNumber": "1111111111"
        },
        "packages": [
          {
            "weight": 3,
            "length": 2,
            "width": 2,
            "height": 2
          }
        ]
      }
    ]
  }'
```

### 响应

```json
{
  "labels": [
    {
      "weight": 2,
      "carrier": "GOFO",
      "requestId": "1689480000123",
      "serviceType": "GOFO_PX",
      "serviceDescription": "GOFO Express 1 - Parcel",
      "totalAmount": 7.46,
      "estimatedDelivery": "N/A",
      "reference": "ref-1",
      "zone": 1,
      "amount": {
        "postageAmount": 7.46
      },
      "orderId": "ST-1689480000123-1615297121467"
    },
    {
      "weight": 3,
      "carrier": "GOFO",
      "requestId": "1689480000456",
      "serviceType": "GOFO_PX",
      "serviceDescription": "GOFO Express 1 - Parcel",
      "estimatedDelivery": "N/A",
      "reference": "ref-2",
      "totalAmount": 8.50,
      "zone": 1,
      "amount": {
        "postageAmount": 8.50
      },
      "orderId": "ST-1689480000456-1615297121887"
    }
  ],
  "currentBalance": 9992.99
}
```

### 注意事项

- 批量请求中 **每个 shipment 只能有一个包裹**
- 每个 shipment 的 `requestId` 必须唯一
- 响应中的 `labels` 数组顺序与请求一致
- 批量创建同样返回 `orderId`，可用于后续查询标签状态
