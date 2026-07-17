# 测试环境凭证

> ⚠️ **本文件包含测试环境真实凭证，请勿用于生产环境！**

## API 凭证

| 项目 | 值 |
|------|-----|
| API Key | `<your-vite-api-key>` |
| Base URL | `https://test-api.vitedirect.com` |

## EEVEE 系统登录

| 项目 | 值 |
|------|-----|
| 系统地址 | https://easygo-dev.vitedirect.com/labelHistory |
| 邮箱 | us@mxdeals.com |
| 密码 | fzh123456 |
| 邀请码 | 17512718117529 |
| 公司名称 | FZH |

## API Hook URL

| 项目 | 值 |
|------|-----|
| 状态 | ⏳ 尚未填写 |
| 配置位置 | EEVEE 系统 → 组织管理页面 |

## 测试账户余额

可在 EEVEE 系统中查看 API 充值、打单信息和打单费用。

## 验证连接

```bash
# 测试 API 连通性
curl -X GET "https://test-api.vitedirect.com/user/account" \
  -H "x-api-key: <your-vite-api-key>"

# 预期返回: {"balance": <数值>}
```

## 安全提醒

- ❌ 不要将此文件提交到公共代码仓库
- ❌ 不要在客户端代码中暴露 API Key
- ✅ 生产环境使用不同的 API Key
- ✅ 建议将凭据写入 `.env` 文件并使用环境变量引用
