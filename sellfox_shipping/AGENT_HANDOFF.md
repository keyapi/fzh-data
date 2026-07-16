# sellfox_shipping — Agent 交接说明

> **赛狐尾程打单系统** — 三界面架构 (Web UI + MCP + CLI)
> 人读文档: [README.md](README.md)

## 架构

```
Service Layer (纯 Python，框架无关，可移植到 ERPNext)
    ├── FastAPI REST    → Web UI   (人类操作)
    ├── FastMCP Tools   → AI Agent (Claude/Codex)
    └── Typer CLI       → 终端     (人类 + Agent)
```

承运人抽象借鉴 Karrio (AbstractProxy + Provider) 和 EasyPost Python SDK (Client-as-Service-Registry)。

## 快速启动

```bash
# Web Server (FastAPI + FastMCP)
uv run python -m sellfox_shipping.cli serve

# CLI
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

## 当前阶段: P1 骨架

P1 完成项: models, store, sellfox_client, FastAPI REST, FastMCP tools, Typer CLI, Web UI, Docker

## 待实现

| 阶段 | 内容 | 依赖 |
|------|------|------|
| P2 | FedEx API 对接 | FedEx 账号 API Key |
| P3 | 规则引擎 + Excel 适配 | 确认物流商模板 |
| P4 | 批量和报告 | — |
| P5 | GLS/DHL/Vite | 各承运人凭证 |
| P6 | 中文优化 + 打印 | — |

## 数据流

```
赛狐 API → sellfox-api-proxy → sellfox_client.fetch_orders()
    → store.upsert_order()
    → carriers[selected].create_shipment()
    → label (ZPL/PDF)
    → sellfox_client.write_tracking()
    → 赛狐回写追踪号
```

## 凭证

| 项目 | 来源 |
|------|------|
| 赛狐 API | 通过 sellfox-api-proxy (已有) |
| FedEx API Key | 待获取 (P2) |
| GLS API | 待获取 (P5) |
| DHL API | 待获取 (P5) |
