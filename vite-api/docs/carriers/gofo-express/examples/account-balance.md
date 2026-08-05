# 账户余额查询示例

## GET /user/account

### curl 请求

```bash
curl -X GET "https://test-api.vitedirect.com/user/account" \
  -H "x-api-key: <your-vite-api-key>"
```

### 响应

```json
{
  "balance": 1000
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `balance` | number | 账户余额 (USD) |

### 用途

- 创建标签前确认余额充足
- 创建标签后可对比 `currentBalance` 确认扣费
- 定期监控余额，及时充值
