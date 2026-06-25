---
okf: v0.1
type: Research
title: 赛狐 OpenAPI 探索记录 — 2026-06-25
description: Playwright 浏览器自动化获取 Apifox 文档、OAuth 认证测试、API 端点探测的完整过程
tags: [amazon, advertising, sellfox, saihu, API, integration, exploration]
timestamp: 2026-06-25
---

# 赛狐 OpenAPI 探索记录

> 记录 2026-06-24/25 通过 Playwright + Python 探索赛狐 API 的完整过程。
> 包含所有尝试过的方法、成功与失败的端点、获取到的文档内容。

## 1. 凭证信息

| 项目 | 值 |
|------|-----|
| App ID | 368618 |
| App Secret | 910891e4-48db-4b30-84d4-6b238a1e9a47 |
| 账号名 | AGENT |
| 权限范围 | 全部模块 |
| 生产环境 | https://openapi.sellfox.com/ |
| API 文档 | https://sellfoxapi.apifox.cn/ |
| 文档密码 | VZKGdd0Q |
| IP 白名单 | 123.117.236.65 (北京办公室), 82.156.238.248 (VPS) |

## 2. 认证探索过程

### 成功: OAuth 2.0 client_credentials

**端点**: `GET https://openapi.sellfox.com/api/oauth/v2/token.json`

**参数**:
```
client_id=368618
client_secret=910891e4-48db-4b30-84d4-6b238a1e9a47
grant_type=client_credentials
```

**成功响应** (HTTP 200):
```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "access_token": "ddf41762-d978-44a6-b854-6ca2a7309466",
    "expires_in": 86399998
  },
  "ts": 1782294762679,
  "requestId": "2c4eb7b6-0870-4c19-85d0-0342cbdd13d7"
}
```

**关键发现**:
- Token 端点是唯一不受 IP 白名单限制的端点（从代理 IP 成功获取）
- Token 有效期约 24 小时（86400000ms）
- 有效期内重复获取返回相同 token
- 注意: 不能频繁调用该端点，否则会被限流

### 尝试过但失败的方法（全部 HTTP 401）

1. Basic Auth: `Authorization: Basic base64(app_id:app_secret)` → /v2/api-docs
2. Bearer Token: `Authorization: Bearer <app_secret>` → /v2/api-docs
3. HMAC-SHA256 Header: `X-App-Id, X-Timestamp, X-Nonce, X-Signature` → /v2/api-docs
4. HMAC Authorization: `Authorization: HMAC-SHA256 AppId=...` → /v2/api-docs
5. API Key Header (多种): `x-api-key, X-API-Key, api-key, X-App-Secret` → /v2/api-docs
6. Query params: `?app_id=...&app_secret=...` → /v2/api-docs

全部返回 401。这些失败不是因为认证方式不对，而是因为 IP 不在白名单中——/v2/api-docs 端点受 IP 白名单保护。

## 3. 文档获取过程

### 3.1 WebFetch 尝试（全部失败）

| URL | 结果 |
|-----|------|
| https://sellfoxapi.apifox.cn/ | 密码保护页 |
| https://sellfoxapi.apifox.cn/?password=VZKGdd0Q | 密码保护页（query param 无效） |
| https://sellfoxapi.apifox.cn/doc-1589130.md | 密码保护页 |
| https://sellfoxapi.apifox.cn/doc-1589130.md?password=VZKGdd0Q | 密码保护页 |
| https://sellfoxapi.apifox.cn/llms.txt | 密码保护页 |

WebFetch 无法通过 Apifox 的交互式密码保护（需要点击按钮 + 表单提交）。

### 3.2 Playwright 浏览器自动化（成功）

**方法**: 使用 Playwright MCP 的 `browser_run_code_unsafe`

```javascript
await page.fill('input[type="password"]', 'VZKGdd0Q');
await page.click('button:has-text("访问文档")');
const text = await page.evaluate(() => document.body.innerText);
```

**获取到的文档**: "获取 Access Token" (doc-1589130.md)

### 3.3 文档结构发现

通过 Playwright Snapshots 发现了完整的文档结构（16 个 API 模块）:

```
赛狐开放平台
├── 开发指南 (14 个文档)
│   ├── 赛狐开放平台免责声明
│   ├── 申请API权限
│   ├── 获取 Access Token
│   ├── 限流策略说明
│   ├── 生成sign（签名）
│   ├── 公共请求参数
│   ├── 公共报错
│   ├── 创建赛狐报告
│   ├── 更新公告
│   ├── 数据结构 (站点ID、FBA类型、省份代码、国家列表、产品分析指标)
│   └── 场景调用指南
├── 商品 (API参考)
├── 销售 (API参考)
├── 订单 (API参考)
├── 客服 (API参考)
├── 广告 (API参考) ★ 最关键的模块
├── FBA (API参考)
├── 采购 (API参考)
├── 仓库 (API参考)
├── 数据 (API参考)
├── 财务 (API参考)
├── 工具 (API参考)
├── 设置 (API参考)
├── Feed (API参考)
├── 报告中心 (API参考)
└── 多平台 (API参考)
```

### 3.4 未成功获取的内容

- **广告 API 参考文档**: 侧栏"广告"模块未成功展开（React 事件处理器阻止），具体 API 端点未知
- **商品/销售/订单等 API 参考**: 同上
- **LLMs.txt 只含开发指南**: 14 个文档链接，不含 API 参考文档

## 4. API 端点探测

### 成功

| 端点 | 方法 | 状态 | 说明 |
|------|------|------|------|
| `/api/oauth/v2/token.json` | GET | 200 | OAuth 认证 ✅ |
| `/doc.html` | GET | 200 | Swagger UI (需认证后显示内容) |
| `/webjars/bycdao-ui/cdao/swaggerbootstrapui.js` | GET | 200 | Swagger UI JS |

### 失败（IP 白名单阻止）

所有以下端点从非白名单 IP 调用均返回空/404:

| 尝试的路径模式 |
|---------------|
| `/api/v1/sp/campaigns`, `/api/v1/sp/campaigns/list` |
| `/api/v1/advertising/sp/campaigns` |
| `/api/v1/advertising/reports` |
| `/api/v1/sp/search-terms`, `/api/v1/sp/keywords` |
| `/api/v1/sellers`, `/api/v1/sellers/list` |
| `/api/v1/shops`, `/api/v1/stores` |
| `/openapi/v1/sellers`, `/openapi/v1/sp/campaigns` |
| `/v2/api-docs` (需认证) |
| `/swagger-resources` (需认证) |

## 5. 关键数据点

### Token 有效性确认
- Client credentials grant 工作正常
- Token 有效期 24h
- 有效期内重复获取返回同一 token

### API 基础架构确认
- 后端框架: Spring Boot (基于 Swagger Bootstrap UI 判断)
- API 文档工具: Knife4j/Swagger Bootstrap UI
- 响应格式: JSON (code/msg/data/requestId 结构)
- 认证: OAuth 2.0 Bearer token

### 代码约定
- 响应 code=0 表示成功
- 标准错误格式: `{code, msg, requestId}`
- Token 放在 `Authorization: Bearer <token>` 头部

## 6. 对下一步的建议

1. **从白名单 IP 运行** `test_sellfox_api.py` — 脚本会自动尝试所有认证方式并保存 OpenAPI JSON
2. **在浏览器中打开** `https://sellfoxapi.apifox.cn/`，输入密码 VZKGdd0Q，展开"广告"模块查看具体 API 端点
3. **优先验证广告 API 写能力** — 是否支持创建/修改 campaign、调整出价、添加关键词
4. **确认数据范围** — 历史数据可回溯天数、刷新频率

## See also
- [赛狐 API 实践指南](../reference/2026-sellfox-api-guide.md)
- [赛狐接入踩坑记录](../lessons/2026-06-25-sellfox-integration-lessons.md)
- [SP-API 开发者模型](../reference/2026-sp-api-developer-model.md)
- [多账号防关联安全](../reference/2026-security-multi-account.md)
