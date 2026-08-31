---
okf: v0.1
type: Solution
title: Tongtool ERP2 MCP 接入与双 App 共享限流验证
description: 通途 ERP2.0 MCP 的本机接入、权限探测和共享五次每分钟限流的已验证结论。
module: tongtool_api
date: 2026-08-13
category: integration-issues
problem_type: integration_issue
component: tooling
severity: high
symptoms:
  - "Codex Settings 显示 MCP 已配置，但无法据此判断 ERP2 子接口是否真正可用"
  - "不确定 MCP 是否复用通途 API 限流，以及两个 App 能否各自获得五次每分钟额度"
  - "同一 ERP2 App 的不同工具会返回 200 或 524"
root_cause: incomplete_setup
resolution_type: documentation_update
tags: [tongtool, erp2, mcp, rate-limit, permissions, codex]
related_components: [tongtool_api, codex-mcp, erpnext]
---

# Tongtool ERP2 MCP 接入与双 App 共享限流验证

## Problem

通途 ERP2.0 的两个 AI Agent App 已配置到 Codex，但“配置存在”无法证明 MCP 实际可调用、具体 ERP2 子接口已授权，或 MCP 是否拥有独立于通途 API 的限流额度。若错误地按“每 App 五次/分钟”设计自动化，会在同一商户的并发任务中触发 526 并造成不必要的重试。

## Symptoms

- Codex 重启前后，Settings 只能确认远程 MCP 配置，不显示目标接口的业务授权结果。
- 第二 App 对某些 ERP2 BaseData 工具返回 524，但对仓库查询返回 200。
- MCP 工具调用的传输层可以成功，而返回内容中的 Tongtool 业务码仍可能是 526。

## Investigation

1. 将两个 App 的 Key/Secret 仅写入本地忽略文件 `tongtool_api/.env`，再由 `tongtool_api/setup_codex_mcp.ps1` 管理用户级 `~/.codex/config.toml` 的远程 MCP 段。
2. 完全重启 Codex 后，确认运行时出现 `tongtool_erp2_primary` 与 `tongtool_erp2_secondary` 两组工具；这证明客户端加载了配置，但不等同于接口授权。
3. 对相同的只读 ERP2 BaseData 工具做最小实测。第二 App 的仓库查询返回 200，其他未授权子接口返回 524，确认权限按具体接口细分。
4. 交叉核对私有 EN 集成、公开 Go SDK README、官方 MCP 接入页与官方公共错误码接口。
5. 在两个完整冷却窗口之间执行只读仓库查询：先分别验证主 App 和第二 App 都在第六次返回 526，再进行跨 App 判别。

## Evidence

| Source | Verified fact |
|---|---|
| `keyapi/tongtool_integration` | 客户端有 5/min 主动节流，并将 526 识别为超频。 |
| `hiscaler/tongtool` README | 明确写明“所有接口调用频率为一分钟 5 次”。 |
| 通途官方 AI 服务接入页 | MCP 采用 Streamable HTTP，认证使用两个 Tongtool HTTP headers；未声明独立 MCP 配额。 |
| 通途官方公共错误码接口 | 526 为“接口请求超请求次数限额”；524 为未授权。 |
| 实时 MCP 判别实验 | 主 App 连续五次仓库查询为 200 后，第二 App 的第一调用为 526。 |

完整逐次结果和异常上下文见 [限流实验记录](../../../tongtool_api/docs/research/2026-08-13-rate-limit-experiment.md)。

## Solution

### 1. 将 MCP 配置和真实凭证分层

- 提交项目文档、Skill、`.env.example` 与安装脚本：[Codex](../../../tongtool_api/setup_codex_mcp.ps1)、[Cursor](../../../tongtool_api/setup_cursor_mcp.py)。
- 忽略 `tongtool_api/.env`，真实凭证只进入用户级 Codex `config.toml` 或 Cursor `mcp.json`。
- 同事 clone 并信任项目后获得相同的安装流程与 Skill，但必须自行获得可授权凭证。

### 2. 先探测权限，再运行业务查询

MCP 列出全局工具目录，不能从“看得到工具”推断 App 已授权。对目标端点先发起最小只读调用，并按业务码处理：

| 信号 | 含义 | 处理 |
|---|---|---|
| 200 | 调用成功 | 才能进入分页或自动化流程。 |
| 524 | 该 App 未授权该子接口 | 到通途后台确认具体接口勾选和生效状态，不要当作限流。 |
| 525 | 参数无效 | 保留凭证，按当前 MCP schema 和官方详情修正参数。 |
| 526 | 服务端请求次数限额 | 停止请求，等待新的限流窗口。 |
| MCP -32602 | MCP 输入 schema 拒绝 | 本地参数形状错误，尚未形成 Tongtool 业务调用。 |

### 3. 对整个商户使用一个五次每分钟预算

实时判别序列如下：

```text
clean window
primary warehouseQuery #1..#5 -> 200
secondary warehouseQuery #1    -> 526
```

因此调度器必须把两个 App 的 ERP2 调用合并计数：总量最多五次/分钟。不要通过轮换 App 提升吞吐；应缓存基础数据、收窄时间窗口、分页节流，并在 526 后等待下一窗口。

`tongtool_api/test_mcp_rate_limit.py` 提供可重跑的 `connectivity`、`burst`、`alternate` 和 `discriminate` 模式。它只使用页数为 1、页大小为 1 的仓库查询，输出 App、时间、结果类型与业务码，不输出业务记录或凭证。

复现双 App 判别可运行 `uv run python tongtool_api/test_mcp_rate_limit.py --mode discriminate --cooldown-seconds 65`。脚本在 MCP 初始化前等待冷却窗口，随后只查询一页仓库数据，并输出每次调用和不含业务数据的汇总 JSON；预期信号是五次 `200` 后一次 `526`，而 `524` 属于授权问题，不能作为限流证据。

## Why This Works

MCP 是通途 API 的远程传输入口，不是另一套独立业务额度。Key/Secret 决定 App 的授权集合，但本商户的上游调用预算在两个 App 之间共享。将权限判断和限流判断分别基于 524 与 526，避免把未授权误诊为超频，或把 MCP HTTP 成功误诊为业务成功。

## Prevention

- 任何新 ERP2 自动化先做小范围只读权限探测，记录端点、参数、业务码与日期。
- 对同一商户所有 ERP2 请求共用一个限流器，预算为五次/分钟；命中 526 不做紧密重试。
- 只记录聚合测试结果，订单、包裹、地址和联系方式等生产响应不得写入 git。
- 通途接口文档存在历史不完整或不一致情况时，以当前 MCP schema、官方详情和最小 live 调用交叉验证。

## Related

- [Tongtool ERP2 Agent Handoff](../../../tongtool_api/AGENT_HANDOFF.md)
- [认证、授权与错误码](../../../tongtool_api/docs/reference/authentication-and-errors.md)
- [MCP 安装说明](../../../tongtool_api/docs/reference/mcp-setup.md)
- [来源审计](../../../tongtool_api/docs/research/2026-08-13-source-audit.md)
