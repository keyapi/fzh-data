---
okf: v0.1
type: Reference
title: 测试环境凭证说明
description: VITE 测试环境变量名与占位符；真实值仅在仓库根 .env
---

# 测试环境凭证

> ⚠️ **真实凭证只放仓库根目录 `.env`（gitignore），勿写入本文件。**
> 本页仅说明变量名与测试 Base URL；勿用于生产环境。

## API 凭证

| 项目 | 值 |
|------|-----|
| API Key | 见根目录 `.env` 的 `VITE_API_KEY`（占位：`<your-vite-api-key>`） |
| Base URL | `https://test-api.vitedirect.com`（或 `VITE_API_BASE_URL`） |

## EEVEE 系统登录

| 项目 | 值 |
|------|-----|
| 系统地址 | https://easygo-dev.vitedirect.com/labelHistory（或 `VITE_EEVEE_URL`） |
| 邮箱 | 见 `.env` 的 `VITE_TEST_ACCOUNT` |
| 密码 | 见 `.env` 的 `VITE_TEST_PASSWORD` |
| 邀请码 | 见 `.env` / 组织管理员（勿提交明文） |
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
# 测试 API 连通性（Key 从环境变量读取，勿粘贴明文）
curl -X GET "https://test-api.vitedirect.com/user/account" \
  -H "x-api-key: <your-vite-api-key>"

# 预期返回: {"balance": <数值>}
```

## 安全提醒

- ❌ 不要将真实 API Key / EEVEE 密码 / 邀请码提交到仓库
- ❌ 不要在客户端代码中暴露 API Key
- ✅ 变量名各环境一致（`VITE_API_KEY` / `VITE_API_BASE_URL`），**只换值**
- ✅ 开发默认填测试环境值；生产由部署侧 Secret 注入同名变量
- ✅ 泄露后可联系 VITE 轮换**测试** Key（当前泄露面为 test-api，非生产 Key）
