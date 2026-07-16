# sellfox_shipping — 赛狐尾程打单系统

> 三界面架构：Web UI（人类）+ MCP Tools（AI Agent）+ CLI（终端）
> 从赛狐获取订单 → 匹配尾程 → 生成运单标签 → 回写追踪号

## 快速开始

```bash
# 启动 Web 服务
uv run python -m sellfox_shipping.cli serve

# 从赛狐拉订单
uv run python -m sellfox_shipping.cli fetch --date-start 2026-07-01 --date-end 2026-07-15

# 查看订单
uv run python -m sellfox_shipping.cli orders --status to_print
```

打开 http://localhost:8401 查看 Web UI。

## 架构

详见 [AGENT_HANDOFF.md](AGENT_HANDOFF.md) 和 [docs/index.md](docs/index.md)。

## 当前阶段

**P1 — 骨架搭建** (model, store, client, FastAPI, FastMCP, CLI, Web UI)

后续待实现：P2 FedEx API → P3 规则引擎 → P4 批量+报告 → P5 其他承运人 → P6 打磨
