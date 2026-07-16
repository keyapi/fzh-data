# TEMU 回标标签示例 (GFUS 渠道)

## 请求

```bash
curl -X POST "https://test-api.vitedirect.com/shipment2/gofo" \
  -H "x-api-key: H5se84hM6Y34Kx2XjfRzg16t6wXSJydq6Bxk1Kzd" \
  -H "Content-Type: application/json" \
  -d '{
    "requestId": "1689480000789",
    "serviceType": "GOFO_PARCEL",
    "channel": "GFUS",
    "shipDate": "2025-07-14",
    "memo": "TEMU_RETURN_001",
    "reference": "TEMU-ORDER-12345",
    "from": {
      "zipCode": "02478",
      "fullName": "FZH Returns Center",
      "address1": "90 Chester rd Belmont",
      "city": "Boston",
      "state": "MA",
      "phoneNumber": "1111111111"
    },
    "to": {
      "zipCode": "90001",
      "fullName": "Customer Name",
      "address1": "123 Return St",
      "city": "Los Angeles",
      "state": "CA",
      "phoneNumber": "1111111111"
    },
    "packages": [
      {
        "weight": 2,
        "length": 10,
        "width": 8,
        "height": 6
      }
    ]
  }'
```

## 响应

```json
{
  "status": "pending",
  "requestId": "1689480000789",
  "orderId": "PPGF-1689480000789-1753253592246",
  "carrier": "GOFO",
  "serviceType": "GOFO_PARCEL",
  "channel": "GFUS",
  "serviceDescription": "GOFO Express 1 - Parcel",
  "totalAmount": 6.72,
  "currency": "USD",
  "currentBalance": 998716869.47
}
```

## 关键点

| 参数 | 值 | 说明 |
|------|-----|------|
| serviceType | `GOFO_PARCEL` | 测试环境服务类型 |
| channel | `GFUS` | TEMU 回标渠道 |
| reference | `TEMU-ORDER-12345` | 建议填写 TEMU 订单号 |
