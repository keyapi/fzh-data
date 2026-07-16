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

## Key Files

| File | Purpose |
|------|---------|
| `docs/test-guide/test-credentials.md` | **Test credentials (real values)** |
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
