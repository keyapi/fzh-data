# Vite API 凭证参考

## 认证方式

所有 API 请求必须通过 `x-api-key` 请求头传递 API Key。

```
x-api-key: <your-api-key>
```

## API Key 说明

| 项目 | 说明 |
|------|------|
| 获取方式 | 在 vitedirect.com 注册账号后申请 |
| 传输方式 | HTTPS (TLS 1.2) |
| 请求头名称 | `x-api-key` |
| 证书签发机构 | DigiCert |

## 环境凭证

| 环境 | Base URL | 说明 |
|------|----------|------|
| 测试环境 | `https://test-api.vitedirect.com` | 用于开发和集成测试 |
| 生产环境 | 联系 Vite 技术支持获取 | 用于正式业务 |

## 测试凭证

> ⚠️ **测试凭证请参见 `docs/test-guide/test-credentials.md`**
> 
> 该文件包含真实的 API Key 和账号信息，仅用于测试环境。

## 联系渠道

- **技术支持邮箱**: support@viteusa.com
- **Webhook 配置**: 在 EEVEE 系统组织管理页面配置（需管理员权限）
