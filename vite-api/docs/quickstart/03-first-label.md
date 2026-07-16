# 首次创建标签

## 目标

创建 GOFO Express 发货标签，获取 PDF 面单。

## Step 1: 创建标签

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

## Step 2: 获取响应

```json
{
  "status": "pending",
  "requestId": "1689480000123",
  "orderId": "PPGF-1689480000123-1753253592246",
  "serviceType": "GOFO_PX",
  "totalAmount": 6.72,
  "currentBalance": 998716869.47
}
```

关键信息:
- **`orderId`**: `PPGF-1689480000123-1753253592246` — 后续查询标签使用
- **`requestId`**: `1689480000123` — 取消标签时使用

## Step 3: 获取标签 PDF

```bash
curl -X GET "https://test-api.vitedirect.com/shipment2/label/PPGF-1689480000123-1753253592246" \
  -H "x-api-key: H5se84hM6Y34Kx2XjfRzg16t6wXSJydq6Bxk1Kzd"
```

成功响应:
```json
[
  {
    "orderId": "PPGF-1689480000123-1753253592246",
    "status": "OK",
    "trackingNumber": "9400111899564088456077",
    "url": "http://docs.vitedirect.com/assets/label.pdf",
    "reference": "ORDER-001"
  }
]
```

## requestId 生成方法

```javascript
// JavaScript: 时间戳 + 3位随机数
const requestId = Date.now() + String(Math.floor(Math.random() * 900 + 100));
```

```python
# Python: 时间戳 + 3位随机数
import time
import random
request_id = str(int(time.time() * 1000)) + str(random.randint(100, 999))
```

## 关键提醒

- `requestId` 必须全局唯一，不可重复使用
- 标签创建后为 `pending` 状态，需等待处理完成
- 测试环境数据为模拟数据，PDF 可能无法下载
