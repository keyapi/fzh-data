# Amazon 回标标签示例 (YT 渠道)

## 请求

```bash
curl -X POST "https://test-api.vitedirect.com/shipment2/gofo" \
  -H "x-api-key: H5se84hM6Y34Kx2XjfRzg16t6wXSJydq6Bxk1Kzd" \
  -H "Content-Type: application/json" \
  -d '{
    "requestId": "1689480000987",
    "serviceType": "GOFO_PARCEL",
    "channel": "YT",
    "shipDate": "2025-07-14",
    "memo": "AMZ_RETURN_001",
    "reference": "AMZ-ORDER-67890",
    "from": {
      "zipCode": "02478",
      "fullName": "FZH Returns Center",
      "address1": "90 Chester rd Belmont",
      "city": "Boston",
      "state": "MA",
      "phoneNumber": "1111111111"
    },
    "to": {
      "zipCode": "98101",
      "fullName": "Amazon Customer",
      "address1": "456 Return Ave",
      "city": "Seattle",
      "state": "WA",
      "phoneNumber": "1111111111"
    },
    "packages": [
      {
        "weight": 3,
        "length": 12,
        "width": 10,
        "height": 8
      }
    ]
  }'
```

## 响应

```json
{
  "status": "pending",
  "requestId": "1689480000987",
  "orderId": "PPGF-1689480000987-1753253592246",
  "carrier": "GOFO",
  "serviceType": "GOFO_PARCEL",
  "channel": "YT",
  "serviceDescription": "GOFO Express 1 - Parcel",
  "totalAmount": 7.50,
  "currency": "USD",
  "currentBalance": 998716862.97
}
```

## 关键点

| 参数 | 值 | 说明 |
|------|-----|------|
| serviceType | `GOFO_PARCEL` | 测试环境服务类型 |
| channel | `YT` | Amazon/Walmart 回标渠道 |
| reference | `AMZ-ORDER-67890` | 建议填写 Amazon 订单号 |
