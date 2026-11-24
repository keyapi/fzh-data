---
okf: v0.1
type: Guide
title: sellfox_mcp — 赛狐官方托管 MCP 的接入与探测
description: 赛狐官方 MCP（api-mcp.sellfox.com/mcp）新协议接入参考与可复现探测脚本；3 个元工具 + 371 个业务工具、两条鉴权路径、写能力干探测护栏
tags: [sellfox, mcp, ads, auth, probe]
timestamp: 2026-11-24
---

# sellfox_mcp

赛狐**官方托管** MCP 的接入参考 + 可复现探测脚本。

> 与 `sellfox-api-proxy/` 区分：那是**我们自己的 VPS 代理**（`api.vilavi.cn/sellfox`，签发自己的 key）；
> 本模块说的是**赛狐官方**那个托管端点。

## 一句话

端点 `https://api-mcp.sellfox.com/mcp`，协议 `2025-06-18`，**无状态**，鉴权走请求头。
**3 个元工具**（`sf_discover` / `sf_describe` / `sf_execute`）+ **371 个业务工具**的发现目录（读约 317 / 写约 54）。

## 先跑这个

```bash
# 凭据从环境变量读，不要写进命令行历史
export SF_MCP_KEY=<子账号 MCP Key>

uv run python sellfox_mcp/scripts/probe_mcp.py --list-tools --auth mcp-key    # 3 个元工具
uv run python sellfox_mcp/scripts/probe_mcp.py --catalog --auth mcp-key       # 371 个业务工具，读写分类
uv run python sellfox_mcp/scripts/probe_mcp.py --smoke-reads --auth mcp-key   # 店铺/订单/利润/库存/广告
uv run python sellfox_mcp/scripts/probe_mcp.py --probe-writes --auth mcp-key  # 写能力干探测（零变更）
```

## 铁律

1. **写工具默认不碰**。`--execute` 对 `edit_*`/`create_*`/`save_*`/`update_*`… 一律拒绝（退出码 2），需 `--allow-write`。
   `--probe-writes` 只对有必填字段的写工具发空参数（必被 schema 拒绝），**不会产生任何变更**。
2. **凭证不落盘**。`SF_MCP_KEY` 只放本机用户级 MCP 配置与父仓库 `.env`；不进仓库、不进命令行历史。
3. **两条鉴权通道别混**。`X-MCP-Key`（子账号，权限随角色）与 `X-Sellfox-Client-Id/Secret`（API 账号）是**独立两条路**。
4. **业务数据不入库**。探测返回真实店铺/订单/金额；文档与提交里只留**结构**（字段名、分页形状）。
5. **写能力不等于写安全**。干探测只证明通道通；真实写测试须指定测试店铺 + 可回滚字段 + 显式授权。

## 两条鉴权路径

| 路径 | 头 | 来源 | 状态 |
|---|---|---|---|
| **A** | `X-Sellfox-Client-Id` + `X-Sellfox-Client-Secret` | API 账号凭证 | ✅ 可用 |
| **B** | `X-MCP-Key` | 子账号「MCP管理」 | ✅ 2026-11 起已开通 |

## 接入状态

- 本机 Claude Code：用户级已加 `Sellfox-MCP`（`~/.claude.json`），`sf_execute` 设为人工确认（`permissions.ask`）。
- 其它机器：各自用自己子账号的 key，不要把 key 分享给他人。

## 目录

- [docs/index.md](docs/index.md) — OKF 文档索引
- [docs/reference/official-mcp.md](docs/reference/official-mcp.md) — **完整操作参考**（端点/鉴权/工具面/调用链/契约分片/坑/能力矩阵/干探测）
- [scripts/probe_mcp.py](scripts/probe_mcp.py) — 探测脚本
- [AGENT_HANDOFF.md](AGENT_HANDOFF.md) — Agent 交接
- 决策背景：[../docs/research/2026-09-20-sellfox-official-mcp-feasibility.md](../docs/research/2026-09-20-sellfox-official-mcp-feasibility.md)

## 非目标

- 不封装/不透传赛狐 API —— 那分别由 `sellfox-api-proxy`（自有代理）与 `SELLFOX_API`（客户端与文档）负责
- 不做真实写测试；只做空参数干探测
