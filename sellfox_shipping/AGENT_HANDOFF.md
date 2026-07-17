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
> **新 Agent 必读:** [docs/research/session-progress-2026-07-16.md](docs/research/session-progress-2026-07-16.md)  
> **规划入口:** [docs/research/research-synthesis-2026-07-16.md](docs/research/research-synthesis-2026-07-16.md)

## 新对话 / 换 Agent 接手（30 秒）

1. 读 [session-progress-2026-07-16.md](docs/research/session-progress-2026-07-16.md) — 已完成过程、提交、下一步、勿踩坑  
2. 读 [research-synthesis-2026-07-16.md](docs/research/research-synthesis-2026-07-16.md) — 目标架构与阶段（以该文档为准，取代本文旧 P1/P2 叙述）  
3. 跑验证：`uv run pytest tests/sellfox_shipping -q`（末次证据：21 passed）  
4. 当前分支：`research/claude-strange-jones`；关键提交：`27cd46d`（调研）、`0b157e7`（同步）、`275919e`（交接文档）、`ebed58a`（列表+审计）

**阶段口径：** 旧「P1 骨架完成 / P2 FedEx」作废；现行阶段为 **P0 → P1A → P1B → P1C → P2+**。旧代码称 **legacy skeleton**。

## 架构

```
Sellfox gateway (wire camelCase → internal snake_case)
    → SyncPackagesService（分页、逐行报告、部分失败报告）
    → PackageRepository（SQLAlchemy + SQLite WAL）
    → Typer JSON CLI
```

Legacy Web/MCP/订单接口仍保留，但尚未迁移到新 Service Layer。不要把 legacy skeleton 当作生产闭环，也不要在 `store.py` 订单模型上堆蜴国际流程。

## 快速启动

```bash
# 测试
uv run pytest tests/sellfox_shipping -q

# P1A：包裹只读同步（需要 SELLFOX_PROXY_API_KEY；不调用 submitToPlatform）
uv run python -m sellfox_shipping.cli packages-sync \
  --date-start 2026-07-15 --date-end 2026-07-16 \
  --actor <operator-id> --json

# 本地包裹列表（只读本地库）
uv run python -m sellfox_shipping.cli packages-list --status to_audit --json

# P1B：蜴国际上传 Excel（仅 local_review=approved 且渠道含「蜴」；重尺走 commodity pageList）
uv run python -m sellfox_shipping.cli lizard-export -o out/lizard-upload.xlsx --actor <operator-id> --json

# P1B：解析蜴国际返回追踪号 Excel（按 package_sn 对账；尚未回写赛狐）
uv run python -m sellfox_shipping.cli lizard-import-tracking -i path/to/return.xlsx --actor <operator-id> --json

# REST（legacy Web 服务启动后）
# GET /api/packages?status=to_audit&channel=蜴国际
# GET /api/packages/{package_sn}

# Web Server（FastAPI；FastMCP 未安装时自动跳过）
uv run python -m sellfox_shipping.cli serve
# 打开 http://127.0.0.1:8401/packages

# Legacy 订单 CLI（勿作为主流程扩展）
uv run python -m sellfox_shipping.cli fetch --date-start 2026-07-01 --date-end 2026-07-15
uv run python -m sellfox_shipping.cli orders --status to_print --json
```

## 项目结构

```
sellfox_shipping/
├── main.py               # 入口：FastAPI + FastMCP 组装（legacy）
├── app.py                # FastAPI app（legacy REST + Web UI）
├── mcp_tools.py          # FastMCP（legacy；根 uv 环境无 fastmcp，Docker 另装）
├── cli.py                # Typer CLI；packages-sync / lizard-export / lizard-import-tracking
├── lizard_batch.py       # P1B 导出/导入 Service ★
├── models.py             # Legacy 订单中心 Pydantic 模型
├── store.py              # Legacy sqlite3 订单库
├── sellfox_client.py     # 赛狐 gateway：Bearer、动态 account、包裹解析
├── package_models.py     # 包裹领域模型（内部 snake_case）★
├── package_repository.py # SQLAlchemy 多对多持久化 ★
├── package_service.py    # 包裹分页同步与数量对账 ★
├── config.yaml           # proxy、仓库、承运人配置
├── carriers/lizard/      # 蜴国际 Excel 模板与重尺查找 ★
├── carriers/             # 其它承运人抽象（尚未接闭环）
├── templates/            # Web UI (Jinja2)
├── docs/
│   ├── index.md
│   ├── log.md
│   └── research/
│       ├── research-synthesis-2026-07-16.md   # 规划
│       └── session-progress-2026-07-16.md     # 会话进度交接
└── Dockerfile
```

`★` = 2026-07-16 P1A 纵切新增/主路径。

## 命名边界（强制）

| 层 | 规则 |
|----|------|
| Python / DB / 内部 JSON | `snake_case`（`package_sn`, `channel_name`, `tracking_number`） |
| 类名 | `PascalCase` |
| 赛狐 / VITE wire | 官方 camelCase，仅在 gateway 出现（`packageSn`, `trackNo`） |
| 转换 | adapter / Pydantic alias；request hash 用内部 snake_case canonical DTO |

详见综合文档 §2.5。

## 当前阶段：P1A 第一条纵切（已提交）

**已实现**

- 代理 `Authorization: Bearer` + `/v1/{proxy_account}/...`
- 包裹列表解析，保留全部 `orders[]` / `items[]`（一包多单）
- 唯一键 `(account_id, package_sn)`；订单/包裹多对多
- SQLite WAL + foreign_keys + busy_timeout；并发 upsert 用 ON CONFLICT
- `SyncPackagesService`：按实际行数分页；`input = success+skipped+failed+unmatched`
- `partial_failed`：中途失败保留已落库结果 + 报告；CLI 退出码 1
- `packages-sync` JSON CLI（强制非空 `actor`）
- `packages-list`：本地包裹摘要查询（状态/渠道过滤）
- `shipping_audit_events`：同步结束写 `packages.sync` 审计（含部分失败）
- REST：`GET /api/packages`、`GET /api/packages/{package_sn}`
- Web：`/packages`、`/packages/{package_sn}` server-rendered 审核只读页
- Schema：Alembic `0001_package_schema`；仓库启动自动 upgrade/stamp

**已验证：** `uv run pytest tests/sellfox_shipping -q` → 34 passed  

**未调用：** `submitToPlatform`  

**并行中（同事 Agent，未提交）：** VITE API / Karrio 调研 — 本分支暂不碰  

**未实现：** 钉钉 OIDC、Artifact 批次表、ERPNext 重尺兜底、`submitToPlatform` 安全回写、追踪号写回本地/赛狐

## 待实现

| 阶段 | 内容 | 依赖 |
|------|------|------|
| P0 | 赛狐提交与回读契约；ERPNext 兜底（并行） | 测试包裹；Claude 调研 |
| P1A 后续 | OIDC；legacy 入口隔离 | 钉钉 OIDC 配置 |
| P1B 后续 | 导入结果落库追踪号；缺 dims 人工补录 UI | ERPNext 兜底可选 |
| P1C | 人工确认后赛狐回写；VITE 测试 spike | 测试范围与账号 |
| P2+ | PDF/packlist、GLS Excel、经验证的 API connector | 各承运人资料 |

详细决策与暂不做边界见综合调研文档。过程细节见 [session-progress](docs/research/session-progress-2026-07-16.md)。

## 数据流（现行主路径）

```
赛狐订单处理 API getPackagePage
    → sellfox-api-proxy（Bearer + account）
    → SellfoxClient.fetch_package_page()
    → SyncPackagesService.sync()
    → PackageRepository.upsert()
    → JSON reconciliation report
```

## 凭证

| 项目 | 来源 |
|------|------|
| 赛狐 API | 环境变量 `SELLFOX_PROXY_API_KEY`，经 sellfox-api-proxy |
| 蜴国际 API | 根目录 `.env`：`YIGLOBAL_APP_TOKEN` / `YIGLOBAL_APP_KEY`（见 [`.env.example`](.env.example)；模块文档在 `yiglobal-api/`） |
| VITE 测试 | 根目录 `.env`：`VITE_API_KEY` / `VITE_API_BASE_URL`（变量名跨环境一致，只换值） |
| GLS/FedEx | 后续验证，不在当前纵切 |

真调前：复制 [`.env.example`](.env.example) 键到仓库根 `.env`。禁止把真实 Key 写入仓库或文档。赛狐导入/回写前必须用户确认范围。
