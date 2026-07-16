---
okf: v0.1
type: Log
module: sellfox_shipping
created: 2026-07-15
updated: 2026-07-16
---

# sellfox_shipping — 变更日志

## 2026-07-16 — 独立综合调研与导航

- 新增独立综合调研，形成以内部 `(sellfox_account_id, package_sn)` 为包裹业务键、以包裹批次为主线的架构判断
- 将 P1 规划为双轨验证：蜴国际 Excel 完整闭环，以及 VITE 测试环境下 Karrio custom connector 与直接 API 适配器的技术对比
- 补齐 `research/index.md`，将独立综合文档设为当前推荐规划入口，并保留旧调研作来源对照
- 为既有 research 文档补齐或规范化 OKF frontmatter，统一使用 `Reference` / `Research` 类型
- 明确 Python 内部统一 snake_case，第三方 camelCase 仅保留在 adapter/gateway wire payload 边界
- 明确一包多单提交意图、逐订单尝试与包裹级聚合状态（仅规划，尚未实现）
- 本条仅记录调研结论与规划更新，不表示相关代码已经实现

## 2026-07-15 — P1 骨架搭建

- 创建项目结构: models, store, sellfox_client, carriers/base
- FastAPI REST API + 基础 Web UI (index + orders 页)
- FastMCP tools: list_orders, get_order, get_order_shipping_info, fetch_orders_from_sellfox, get_carrier_info, list_available_carriers
- Typer CLI: fetch, orders, status, carriers, rules, serve
- Dockerfile + docker-compose.yml
- config.yaml 含仓库、承运人、规则模板
- OKF 文档框架
- ce-compound: 完整调研文档写入 docs/solutions/architecture-patterns/ 和 docs/research/
