# 错误码参考

## HTTP 状态码

| 状态码 | 含义 | 常见原因 |
|--------|------|----------|
| 200 | 请求成功 | - |
| 400 | 请求参数错误 | 缺少必填字段、格式错误 |
| 401 | 未授权 | API Key 无效或缺失 |
| 404 | 资源不存在 | orderId 无效 |
| 500 | 服务器内部错误 | Vite 系统异常，请联系 support@viteusa.com |

## 常见错误与解决方案

### 400 错误

| 错误场景 | 原因 | 解决方案 |
|----------|------|----------|
| requestId 重复 | 使用了相同的 requestId | 确保每次请求使用唯一 requestId |
| 缺少必填字段 | 未填写 fullName/address1/city/state/zipCode | 检查地址字段 |
| 字段超长 | fullName > 35, address1 > 50 等 | 截断字段内容 |
| 单位错误 | 使用了 kg/cm 而非 lbs/inch | 转换单位为 lbs 和 inch |

### 401 错误

| 错误场景 | 原因 | 解决方案 |
|----------|------|----------|
| 缺失 x-api-key | 请求头未包含 API Key | 添加 `x-api-key` 请求头 |
| API Key 无效 | 使用了错误的 Key | 检查 API Key 是否正确 |

### 500 + 标签失败

```json
{
  "orderId": "PPGF-xxx",
  "requestId": "xxx",
  "status": "failed",
  "errorMessage": "label created failed"
}
```

**处理方式**: 检查请求参数后重试，或联系 Vite 技术支持。

## 错误处理最佳实践

1. **唯一 requestId** — 每次请求使用不同的 requestId，便于重试和排查
2. **重试机制** — 对 500 错误实现指数退避重试
3. **参数校验** — 发送前检查字段长度和必填项
4. **日志记录** — 记录所有 API 响应以便排查
