# Vite API 探索研究

## 探索日期

2026-07-16

## 信息来源

- API 文档: http://docs.vitedirect.com/ (Swagger UI)
- 测试系统: https://easygo-dev.vitedirect.com/labelHistory (EEVEE)

## API 架构观察

### 多承运商统一架构

Vite API 采用统一的多承运商架构，所有承运商遵循类似的请求/响应模式：

| 承运商 | URL 路径前缀 | API 文档源 |
|--------|-------------|------------|
| USPS V2 | `/rate2/usps`, `/shipment2/usps` | `swagger-config.yaml` |
| FedEx V2 | `/rate2/fedex`, `/shipment2/fedex` | `config/fedex.v2.yaml` |
| FedEx Intl | `/rate2/fedex/international` | `config/fedexInternational.yaml` |
| UPS V2 | `/rate2/ups`, `/shipment2/ups` | `config/ups.v2.yaml` |
| UPS Intl | `/rate2/ups/international` | `config/upsInternational.yaml` |
| GOFO Express | `/rate2/gofo`, `/shipment2/gofo` | `config/gofo.yaml` |
| Amazon Ground | `/rate2/amazon`, `/shipment2/amazon` | `config/amazon.yaml` |
| EEI | `/eei` | `config/eei.yaml` |
| Tracking | `/track` | `config/track.yaml` |

### 通用端点

以下端点跨承运商共用：
- `GET /shipment2/label/{orderId}` — 获取标签
- `DELETE /shipment2/label/{requestId}` — 取消标签
- `GET /user/account` — 账户余额

### 认证

所有 API 使用 `x-api-key` 请求头认证，无需 OAuth 或 JWT。

## 测试环境发现

- EEVEE 系统为 Vue.js SPA 应用
- `labelHistory` 路径可能仅显示标签历史记录
- 系统侧边栏包含多个功能模块
