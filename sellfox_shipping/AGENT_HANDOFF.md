---
okf: v0.1
type: Handoff
title: sellfox_shipping — Agent 交接说明
description: 包裹中心架构、当前实现、运行方式与后续阶段边界
updated: 2026-07-16
---

# sellfox_shipping — Agent 交接说明

> **赛狐尾程打单系统** — 包裹批次工作流
> 人读文档: [README.md](README.md)
> 当前规划: [docs/research/research-synthesis-2026-07-16.md](docs/research/research-synthesis-2026-07-16.md)

## 架构

```
Sellfox gateway (wire camelCase → internal snake_case)
    → SyncPackagesService（分页、逐行报告、部分失败报告）
    → PackageRepository（SQLAlchemy + SQLite WAL）
    → Typer JSON CLI
```

Legacy Web/MCP/订单接口仍保留，但尚未迁移到新 Service Layer。不要把 legacy skeleton 当作生产闭环。

## 快速启动

```bash
# Web Server (FastAPI + FastMCP)
uv run python -m sellfox_shipping.cli serve

# CLI
uv run python -m sellfox_shipping.cli packages-sync --date-start 2026-07-15 --date-end 2026-07-16 --actor <operator-id> --json
uv run python -m sellfox_shipping.cli fetch --date-start 2026-07-01 --date-end 2026-07-15
uv run python -m sellfox_shipping.cli orders --status to_print --json
uv run python -m sellfox_shipping.cli status 114-1234567-7890123

# Docker
docker compose -f sellfox_shipping/docker-compose.yml up -d
```

## 项目结构

```
sellfox_shipping/
├── main.py              # 入口：FastAPI + FastMCP 组装
├── app.py               # FastAPI app (REST + Web UI)
├── mcp_tools.py         # FastMCP tools (AI Agent 专用)
├── cli.py               # Typer CLI (人类+Agent)
├── models.py            # Pydantic 数据模型
├── store.py             # SQLite 持久化
├── sellfox_client.py    # 赛狐 API 客户端 (通过 proxy)
├── package_models.py    # 包裹领域模型（内部 snake_case）
├── package_repository.py # SQLAlchemy 多对多持久化
├── package_service.py   # 包裹分页同步与数量对账
├── config.yaml          # 仓库、承运人、规则配置
├── carriers/
│   ├── base.py          # AbstractCarrier + CarrierRegistry
│   ├── fedex/           # FedEx (P2)
│   ├── gls/             # GLS (P5)
│   └── dhl/             # DHL (P5)
├── templates/           # Web UI (Jinja2)
├── static/              # 静态资源
└── Dockerfile
```

## 当前阶段：P1A 第一条纵切

- 已实现：代理 Bearer/account 路由、包裹多订单/多商品解析、SQLAlchemy repository、SQLite WAL/foreign keys/busy timeout、幂等 upsert、逐行对账和 `packages-sync` CLI
- 已验证：`uv run pytest tests/sellfox_shipping -q`
- 未调用：`submitToPlatform`
- 未实现：正式 schema migration、钉钉 OIDC、包裹查询/审核 Web/REST、Artifact/AuditEvent、蜴国际 Excel

## 待实现

| 阶段 | 内容 | 依赖 |
|------|------|------|
| P0 | 蜴国际上传/返回/PDF 样例与赛狐提交契约 | 业务真实样例、测试包裹 |
| P1A 后续 | migration、OIDC、包裹查询/审核界面、AuditEvent | 钉钉 OIDC 配置 |
| P1B | 蜴国际 Excel 导出/导入 | P0 样例 |
| P1C | 人工确认后赛狐回写；VITE 技术验证 | 测试范围与账号 |
| P2+ | PDF/packlist、GLS Excel、经验证的 API connector | 各承运人资料 |

## 数据流

```
赛狐订单处理 API
    → sellfox-api-proxy（Bearer + account）
    → SellfoxClient.fetch_package_page()
    → SyncPackagesService.sync()
    → PackageRepository.upsert()
    → JSON reconciliation report
```

## 凭证

| 项目 | 来源 |
|------|------|
| 赛狐 API | `SELLFOX_PROXY_API_KEY` 环境变量，通过 sellfox-api-proxy |
| 蜴国际 | P0 收集真实模板；没有 API |
| VITE | P1C 只在测试环境验证，不替换通途生产 |
| GLS/FedEx | 后续取得账号后验证，不在当前纵切 |
