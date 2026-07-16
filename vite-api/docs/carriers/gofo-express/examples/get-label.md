# 获取标签示例

## GET /shipment2/label/{orderId}

### curl 请求

```bash
# 替换 {orderId} 为创建标签时返回的 orderId
curl -X GET "https://test-api.vitedirect.com/shipment2/label/PPGF-1689480000123-1753253592246" \
  -H "x-api-key: H5se84hM6Y34Kx2XjfRzg16t6wXSJydq6Bxk1Kzd"
```

### 成功响应

```json
[
  {
    "orderId": "PPGF-1689480000123-1753253592246",
    "requestId": "1689480000123",
    "status": "OK",
    "carrier": "GOFO",
    "trackingNumber": "9400111899564088456077",
    "trackingNumbers": ["9400111899564088456077"],
    "url": "http://docs.vitedirect.com/assets/9400110200830513838769.pdf",
    "reference": ""
  }
]
```

### 失败响应 (500)

```json
{
  "orderId": "PPGF-1689480000123-1753253592246",
  "requestId": "1689480000123",
  "status": "failed",
  "reference": "",
  "errorMessage": "label created failed"
}
```

### 状态说明

| 状态 | 说明 |
|------|------|
| `pending` | 标签处理中，等待 |
| `OK` | 标签已生成，可以下载 |
| `failed` | 标签创建失败，查看 `errorMessage` |

### 下载标签

当 `status` 为 `OK` 时，`url` 字段即为标签 PDF 的下载地址。
