# AGENT HANDOFF: Vite API Integration

## Module Overview

Vite shipment API integration for FZH company. This module documents the API integration with Vite (vitedirect.com) for multi-carrier shipping label creation, rate queries, and return label management.

## Key Information

| Item | Value |
|------|-------|
| API Doc | http://docs.vitedirect.com/ |
| Test API | https://test-api.vitedirect.com |
| Test System | https://easygo-dev.vitedirect.com/labelHistory |
| Primary Carrier | GOFO Express |
| Auth | x-api-key header |

## Credentials (env)

真实值只放**仓库根** `.env`（见 [`.env.example`](.env.example)）：

- `VITE_API_KEY` / `VITE_API_BASE_URL` — **变量名跨 test/prod 相同，只换值**
- 开发默认填测试环境；生产由部署侧注入同名变量
- EEVEE 登录用 `VITE_TEST_ACCOUNT` / `VITE_TEST_PASSWORD`（勿写入 Markdown）
- 可选：若测试 Key 曾泄露，可联系 VITE 轮换（当前泄露面为 test-api，非生产 Key）

## Key Files

| File | Purpose |
|------|---------|
| `.env.example` | 变量名模板（无真实值） |
| `docs/test-guide/test-credentials.md` | 测试凭证说明（占位符；真值在根 `.env`） |
| `docs/reference/channel-codes.md` | GFUS/YT channel to platform mapping |
| `docs/carriers/gofo-express/` | GOFO Express docs (overview, endpoints, 6 examples) |
| `docs/return-labels/` | Return label documentation |
| `docs/webhooks/setup-guide.md` | Webhook setup instructions |
| `docs/quickstart/` | Getting started guides |

## Common Tasks

1. **Test connectivity**: `curl GET /user/account` with x-api-key
2. **Query rate**: `POST /rate2/gofo`
3. **Create label**: `POST /shipment2/gofo` (need unique requestId)
4. **Get label**: `GET /shipment2/label/{orderId}`
5. **Cancel label**: `DELETE /shipment2/label/{requestId}`

## Important Constraints

- Units: lbs and inch ONLY
- requestId must be globally unique (use timestamp + random)
- Test data is mock data
- Contact support@viteusa.com for production access
