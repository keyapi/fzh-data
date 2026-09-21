---
okf: v0.1
type: Guide
title: sellfox_mcp — 赛狐官方托管 MCP 的接入与探测
description: 赛狐官方 MCP（api-mcp.sellfox.com/mcp）的接入参考与可复现探测脚本；含两条鉴权路径、23 个工具的三分类、写操作安全护栏
tags: [sellfox, mcp, ads, auth, probe]
timestamp: 2026-09-20
---

# sellfox_mcp

赛狐**官方托管** MCP 的接入参考 + 可复现探测脚本。

> 与 `sellfox-api-proxy/` 区分：那是**我们自己的 VPS 代理**（`api.vilavi.cn/sellfox`，签发自己的 key）；
> 本模块说的是**赛狐官方**那个托管端点（要直接拿生产 App ID/Secret 去连）。

## 一句话

端点 `https://api-mcp.sellfox.com/mcp`，协议 `2025-06-18`，鉴权走**请求头**（不需要 OAuth）。
**23 个工具 = 13 只读 + 1 非破坏性写 + 9 个会改线上广告的写。**

## 先跑这个

```bash
# 凭据从环境变量读，不要写进命令行历史
export SF_ID=<API账号的App ID>
export SF_SECRET=<API账号的App Secret>

uv run python sellfox_mcp/scripts/probe_mcp.py --check-token   # 验凭据 + IP 白名单
uv run python sellfox_mcp/scripts/probe_mcp.py --list-tools    # 列工具（三分类）
uv run python sellfox_mcp/scripts/probe_mcp.py --call get_shop_page_list --args '{"page_no":"1","page_size":"5"}'
```

## 铁律

1. **写工具默认不碰**。脚本内置护栏：写工具与白名单外工具一律拒绝（退出码 2），除非显式 `--allow-write`。
   那 9 个写工具会改**线上广告**（`edit_sp_campaign` 单次可改 100 条）。
2. **凭证不落盘**。App ID/Secret 是生产凭证，只从环境变量读；不要写进任何文件或提交。
3. **别把 `X-MCP-Key` 和 API 账号凭证搞混** —— 它们是**两条独立通道**，前者目前「未启用」，
   后者可用。详见 [docs/reference/official-mcp.md](docs/reference/official-mcp.md#二鉴权两条独立路径)。
4. **业务数据不入库**。探测返回真实店铺/订单数据，文档与提交里只留**结构**不留内容。

## 两条鉴权路径（最容易搞错的地方）

| 路径 | 头 | 来源 | 状态 |
|---|---|---|---|
| **A** | `X-Sellfox-Client-Id` + `X-Sellfox-Client-Secret` | API 账号凭证 | ✅ 可用 |
| **B** | `X-MCP-Key` | 后台「业务设置 → 全局 → MCP管理」 | ❌ 未启用（`40027`） |

## 目录

- [docs/index.md](docs/index.md) — OKF 文档索引
- [docs/reference/official-mcp.md](docs/reference/official-mcp.md) — **完整操作参考**（端点 / 鉴权 / 工具清单 / 实测证据 / 脚本用法）
- [scripts/probe_mcp.py](scripts/probe_mcp.py) — 探测脚本
- [AGENT_HANDOFF.md](AGENT_HANDOFF.md) — Agent 交接
- 决策背景：[../docs/research/2026-09-20-sellfox-official-mcp-feasibility.md](../docs/research/2026-09-20-sellfox-official-mcp-feasibility.md)

## 非目标

- 不封装/不透传赛狐 API —— 那分别由 `sellfox-api-proxy`（自有代理）与 `SELLFOX_API`（客户端与文档）负责
- 不调用任何破坏性写工具（本模块只做**只读探测**）
