---
type: log
module: sellfox_shipping
created: 2026-07-15
---

# sellfox_shipping — 变更日志

## 2026-07-15 — P1 骨架搭建

- 创建项目结构: models, store, sellfox_client, carriers/base
- FastAPI REST API + 基础 Web UI (index + orders 页)
- FastMCP tools: list_orders, get_order, get_order_shipping_info, fetch_orders_from_sellfox, get_carrier_info, list_available_carriers
- Typer CLI: fetch, orders, status, carriers, rules, serve
- Dockerfile + docker-compose.yml
- config.yaml 含仓库、承运人、规则模板
- OKF 文档框架
- ce-compound: 完整调研文档写入 docs/solutions/architecture-patterns/ 和 docs/research/
