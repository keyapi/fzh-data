# 取消标签示例

## DELETE /shipment2/label/{requestId}

### curl 请求

```bash
# 替换 {requestId} 为创建标签时使用的 requestId
curl -X DELETE "https://test-api.vitedirect.com/shipment2/label/1689480000123" \
  -H "x-api-key: <your-vite-api-key>"
```

### 响应

```json
{
  "status": "success",
  "message": "target label has been canceled"
}
```

### 注意事项

- 可以通过 `orderId` 或 `requestId` 取消标签
- 取消成功返回 `status: "success"`
- USPS 标签取消有 60 天限制（Vite 规定）
