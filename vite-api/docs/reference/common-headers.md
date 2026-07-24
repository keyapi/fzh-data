# 公共请求/响应头

## 请求头

| 请求头 | 必需 | 值 | 说明 |
|--------|------|-----|------|
| `x-api-key` | 是 | `{your-api-key}` | API 认证密钥 |
| `Content-Type` | 是 | `application/json` | 请求体格式 |

## 响应头

标准 HTTP 响应头，包含 `Content-Type: application/json`。

## HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误 |
| 401 | 认证失败（API Key 无效） |
| 500 | 服务器内部错误 |

## 安全说明

- 所有 API 调用必须使用 **HTTPS**（TLS 1.2+）
- 证书由 **DigiCert** 签发
- API Key 应妥善保管，不要泄露给第三方
