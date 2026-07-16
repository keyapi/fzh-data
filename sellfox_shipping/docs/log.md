---
okf: v0.1
type: Log
module: sellfox_shipping
created: 2026-07-15
updated: 2026-07-16
---

# sellfox_shipping — 变更日志

## 2026-07-16 — P1A 包裹查询与同步审计

- 新增 `packages-list` CLI：按账户 / 状态 / 渠道过滤本地包裹摘要（`order_count` / `item_count`）
- 新增 `shipping_audit_events` 表；`packages.sync` 结束（含 `partial_failed`）写入 `AuditEvent`（actor + 计数摘要）
- 明确并行边界：同事 Agent 调研 VITE/Karrio 未提交前，本分支不扩展 VITE spike / Karrio connector
- 测试：`uv run pytest tests/sellfox_shipping -q` → 26 passed

## 2026-07-16 — 会话进度交接文档

- 新增 `docs/research/session-progress-2026-07-16.md`：完整记录独立调研落地、命名边界、P1A TDD 实现、审查修复、提交哈希、未完成项与勿踩坑
- 更新 `research/index.md`、`docs/index.md`、`AGENT_HANDOFF.md`：区分「接手继续实现」与「从零独立再调研」阅读顺序
- 目的：新开对话或其它软件 Agent 可从会话进度文档无缝续作，无需依赖聊天上下文

## 2026-07-16 — P1A 包裹只读同步纵切

- 新增内部 snake_case 包裹模型；赛狐 camelCase 仅在 gateway 边界解析
- 修复 Sellfox proxy 动态 account 路径和 Bearer 认证头
- 新增 SQLAlchemy package repository，启用 SQLite WAL、foreign keys、busy timeout，并按账户保存包裹—订单多对多关系
- 新增 `SyncPackagesService`：按实际返回行分页，输出逐行对账；中途 gateway 失败保留已处理结果并返回 `partial_failed`
- 新增 `packages-sync` JSON CLI；要求 actor，部分失败输出报告后返回非零退出码
- 新增 21 个定向测试；当前纵切不调用 `submitToPlatform`，不表示 P1A/P1B 全部完成

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
