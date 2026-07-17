---
okf: v0.1
type: Log
module: sellfox_shipping
created: 2026-07-15
updated: 2026-07-17
---

# sellfox_shipping — 变更日志

## 2026-07-17 — ERPNext ZLMB 重尺兜底接入

- `CascadingDimsLookup`：赛狐 pageList → ERPNext `ZLMB#{前3段}` Item
- 字段优先级：国外成品 → 绍兴工厂；实测 KS0002-DL-194 → 4.1kg / 58×19×45
- 凭证读 `EN_API/.env`（`ERP_API_KEY`/`ERP_API_SECRET`）；修正 Lesson 17 字段名为 `*_length/width/height`
- 测试 54 passed

## 2026-07-17 — P1B 蜴国际 Excel 导出/导入骨架

- `carriers/lizard/`：上传表构建、追踪号返回解析、commodity pageList 重尺查找
- Service：`ExportLizardUploadService` / `ImportLizardTrackingService`（对账报告 + AuditEvent）
- CLI：`lizard-export`、`lizard-import-tracking`
- 缺 carton dims 的包裹计入 skipped，不静默导出空重尺；ERPNext 兜底另开
- 测试：`test_lizard_spreadsheet` + `test_lizard_batch`；全量 sellfox_shipping 通过

## 2026-07-17 — 重尺来自商品 pageList（非包裹）

- 包裹 API 确无重尺；`/api/commodity/pageList.json` + `skus` + `isGroup=0` 返回 cartonWeight/LWH
- 试转换重生成：8/10 有值；KS0002-DL-194-* carton 为 0
- 文档：`docs/research/sellfox-carton-dims-source-2026-07-17.md`；发货编码暂固定 S0143

## 2026-07-17 — 赛狐→蜴国际试转换 + Colab 遗产

- 确认：参考编号=赛狐 `packageSn`（`P2A…`）；P0 样例 `P8140…` 为通途号
- 试生成 `trial-sellfox-to-lizard-upload-10.xlsx`（重量空：API 无 packageWeight）
- Colab notebook 摘要：`docs/research/colab-notebook-legacy-summary-2026-07-17.md`（notebook 主做背贴，不生成上传表）

## 2026-07-17 — 蜴国际 P0 样例列映射

- 样例已入 `数据源/蜥蜴国际-p0-样例/`（gitignore）；① 仅表头无数据，②③④ 为同事 B 同批往返
- 分析结论：`docs/research/lizard-p0-column-mapping-2026-07-17.md`
- 匹配键 `参考编号/Reference Code`；追踪号 `物流单号`；上传重量为克、返回为 kg

## 2026-07-17 — 本地包裹审核写操作

- 新增 `local_review_status`（pending/approved/rejected）与 Alembic `0002`
- `POST /api/packages/{sn}/review` + 详情页表单；同步不覆盖本地审核状态
- 审核写入 `packages.review` AuditEvent；列表可按本地审核筛选
- 测试 44 passed

## 2026-07-17 — serve 不依赖 fastmcp

- `main.py` 将 FastMCP 改为可选挂载；未安装时仍可启动 Web/REST
- `serve` 关闭 reload、使用 `log_level=info`；无 fastmcp 时提示 MCP disabled
- 实测：`uv run python -m sellfox_shipping.cli serve` 后 `GET /packages` → 200
- 测试：`test_serve_without_fastmcp.py`；全量 36 passed

## 2026-07-16 — P1A Alembic schema migration

- 新增 `schema.upgrade_schema()` + Alembic `0001_package_schema`
- `PackageRepository` 启动改为跑 migration，不再裸 `create_all`
- 已有 create_all 库无 `alembic_version` 时 stamp head，避免重复建表失败
- 依赖增加 `alembic`；测试 34 passed

## 2026-07-16 — P1A 包裹审核 Jinja 页

- 新增 server-rendered `/packages` 与 `/packages/{package_sn}`，共用 ListPackagesService / PackageRepository
- 修正 Starlette 1.2 `TemplateResponse(request, name, context)` 签名（旧写法触发 Jinja LRUCache TypeError）
- 导航加入「包裹」入口；legacy 订单页标注
- 测试：`uv run pytest tests/sellfox_shipping -q` → 32 passed

## 2026-07-16 — P1A 包裹 REST 只读接口

- 新增 `GET /api/packages` 与 `GET /api/packages/{package_sn}`，共用 `ListPackagesService` / `PackageRepository`
- 新增 3 个 FastAPI 定向测试；`uv run pytest tests/sellfox_shipping -q` → 29 passed

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
