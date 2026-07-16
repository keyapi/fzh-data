---
type: skill
name: sellfox-shipping
description: 赛狐尾程打单 — 从赛狐获取订单，匹配尾程物流商，生成运单标签，回写追踪号
version: 0.2.0
triggers:
  - "尾程"
  - "打单"
  - "shipping"
  - "label"
  - "运单"
  - "追踪号"
  - "tracking"
  - "FedEx"
  - "GLS"
  - "Vite"
  - "物流标签"
  - "sellfox_shipping"
  - "发货标签"
  - "包裹同步"
  - "packages-sync"
---

# sellfox-shipping Skill

## 这是什么

赛狐尾程打单系统。现行主路径是**包裹批次**：赛狐订单处理 API → 本地包裹库 → 审核 →（后续）Excel/API 承运人 → 追踪号回写。

## 新对话必读

1. `sellfox_shipping/docs/research/session-progress-2026-07-16.md`
2. `sellfox_shipping/docs/research/research-synthesis-2026-07-16.md`
3. `sellfox_shipping/AGENT_HANDOFF.md`

阶段口径：旧「P1 骨架 / P2 FedEx」作废；现行 **P0 → P1A → P1B → P1C → P2+**。legacy 订单 Web/MCP/store 勿当生产闭环。

## 何时触发

尾程打单、物流标签、运单号、FedEx/GLS/DHL、追踪号回写、包裹同步、`packages-sync`、蜴国际 Excel、VITE 等。

## 快速命令

```bash
uv run pytest tests/sellfox_shipping -q

# P1A：包裹只读同步（需 SELLFOX_PROXY_API_KEY；不调用 submitToPlatform）
uv run python -m sellfox_shipping.cli packages-sync \
  --date-start 2026-07-15 --date-end 2026-07-16 --actor <id> --json

uv run python -m sellfox_shipping.cli packages-list --status to_audit --json

# Web：http://localhost:8401/packages （serve 后）
uv run python -m sellfox_shipping.cli serve
```

## 项目文件

| 路径 | 用途 |
|------|------|
| `AGENT_HANDOFF.md` | 交接与命令 |
| `package_*.py` / `schema.py` | 包裹模型 / 仓库 / 同步 / Alembic |
| `sellfox_client.py` | 赛狐 gateway（camelCase → snake_case） |
| `models.py` / `store.py` | **legacy** 订单中心 |
| `docs/research/` | 规划与会话进度 |

## 当前阶段（P1A）

已完成：只读同步、列表 CLI/REST/Web、AuditEvent、Alembic。  
未做：OIDC、蜴国际 Excel、`submitToPlatform`、VITE/Karrio（同事可能并行调研）。  
赛狐回写前必须用户确认范围。
