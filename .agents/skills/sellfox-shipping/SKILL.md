---
type: skill
name: sellfox-shipping
description: 赛狐尾程打单 — 从赛狐获取订单，匹配尾程物流商，生成运单标签，回写追踪号
version: 0.1.0
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
---

# sellfox-shipping Skill

## 这是什么

赛狐尾程打单系统。从赛狐获取订单 → 匹配尾程物流 → 生成运单标签 → 回写追踪号到赛狐。

## 架构

三界面共享一个 Service Layer：
- **FastAPI REST API** → Web UI (人类操作)
- **FastMCP Tools** → AI Agent (Claude/Codex/Cursor)
- **Typer CLI** → 终端 (人类 + Agent 脚本)

## 何时触发

当用户提到尾程打单、物流标签、运单号、FedEx/GLS/DHL API、追踪号回写、赛狐发货等时触发。

## 快速命令

```bash
# 启动服务
uv run python -m sellfox_shipping.cli serve

# 拉订单
uv run python -m sellfox_shipping.cli fetch --date-start 2026-07-01 --date-end 2026-07-15

# 查看订单
uv run python -m sellfox_shipping.cli orders --status to_print --json
```

## 项目文件

- `sellfox_shipping/AGENT_HANDOFF.md` — 完整交接文档
- `sellfox_shipping/config.yaml` — 仓库、承运人、规则配置
- `sellfox_shipping/models.py` — Pydantic 数据模型
- `sellfox_shipping/store.py` — SQLite 持久化
- `sellfox_shipping/mcp_tools.py` — AI Agent 工具

## 当前阶段

P1 — 骨架搭建完成。P2 FedEx API 待实现。
