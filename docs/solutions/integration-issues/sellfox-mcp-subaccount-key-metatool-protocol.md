---
okf: v0.1
type: Reference
title: 赛狐官方 MCP 换协议——子账号 X-MCP-Key 开通 + 元工具发现目录（零副作用验证写能力）
date: 2026-11-24
category: integration-issues
module: sellfox_mcp
problem_type: integration_issue
component: sellfox-mcp
severity: medium
applies_when:
  - "要接赛狐官方 MCP（api-mcp.sellfox.com/mcp）到 Claude Code / Cursor / Codex"
  - "手上是子账号发的 X-MCP-Key，想确认能读什么、写通道通不通"
  - "9 月按 23 个工具写的脚本突然 tools/list 只有 3 个、且拿不到 mcp-session-id"
  - "sf_describe 返回 status=partial 和 contract_parts，不知道怎么拿 inputSchema"
  - "要在不修改任何线上广告的前提下，判断写工具是空壳还是真接后端"
  - "sf_execute 报 Parameters violate the current inputSchema，但字段看着都传了"
---

# 赛狐官方 MCP 换协议：子账号 Key 开通 + 元工具目录

## 背景

2026-09 我们做过赛狐官方 MCP 的可行性探测，当时结论是：

- 服务端暴露 **23 个扁平工具**（13 只读 + 1 报表任务 + 9 广告写）；
- 服务是**有状态**的（`initialize` 后带 `mcp-session-id`）；
- 路径 A（API 账号 `X-Sellfox-Client-Id/Secret`）可用；
- 路径 B（后台 `X-MCP-Key`）返回 `40027 未启用MCP功能`。

当时没有接入任何客户端，只留了探测脚本。2026-11 赛狐给子账号开放了独立 MCP Key，重新验证后发现**服务端整体换了形态**。

## 现在的样子（2026-11-24 实测）

| 项 | 9 月 | 现在 |
|---|---|---|
| 工具面 | 23 个扁平工具 | **3 个元工具 + 371 个业务工具**的发现目录 |
| 会话 | 有状态（`mcp-session-id`） | **无状态** |
| 路径 B | ❌ `40027` | ✅ 可用，权限随子账号角色（查询/写入） |
| 调用方式 | `tools/call` 直接点名 | `sf_discover` → `sf_describe` → `sf_execute` |

三个元工具：

- `sf_discover`：按业务问句 / domain / operation 找 `tool_id`（`limit` 只能 5–20）；
- `sf_describe`：按 `tool_id` 取契约，返回 `inputSchema` + `contract_version`；
- `sf_execute`：执行，`params` 与 `contract_version` 必填。

## 关键坑（都是实测踩到的）

1. **契约分片**：`sf_describe` 可能返回 `status=partial` + `next_cursor` + `contract_parts[]`。
   必须把同组 `json_fragment` 按 `part_index` 拼起来，用 `sha256` 校验，再 `json.loads` 取 `inputSchema`。
   例：`edit_sp_campaign` 分 3 片，SHA 校验通过后才拿到 `required=['items','shop_id']`。
2. **`page_size` 不是随便填**：广告类工具按描述要求 20–50；传 3 会报 `field_errors: page_size / anyOf`。
3. **订单日期是 datetime**：`yyyy-MM-dd` 报 `date_format`，必须 `yyyy-MM-dd HH:mm:ss`。
4. **批量 describe 会分页**：一次传 3 个 `tool_id` 可能只回一部分 + cursor，要顺着翻。
5. **`field_errors[].path` 可能是空串**，错误定位以 `message` 与 schema 为准。
6. **目录回退 ≠ 匹配结果**：`retrieval_mode=catalog_fallback` 只是把整目录摊开，不能据此推断用户要执行哪些工具。

## 零副作用验证「写能力通不通」

目标：判断写工具是真接后端还是空壳，同时**一笔真实修改都不发**。

方法（已固化进 `sellfox_mcp/scripts/probe_mcp.py --probe-writes`）：

1. `sf_describe` 取契约；**`required` 为空则跳过** —— 空参数可能真的执行，绝对不能发。
2. 有必填字段时才发 `params: {}`；schemas 校验必然拒绝，触达不到业务写逻辑。
3. 判据：
   - `INVALID_PARAMS` + 缺字段清单 ⇒ **鉴权通 + 路由通 + 校验收效**；
   - `40027` / 401 / 403 ⇒ key 未开通或权限不足；
   - 其他 ⇒ 记原样。
4. 前后对同一店铺的 `get_sp_campaign_list` 做快照（`campaignId + budget + state`）比对，证明无变更。

结果：14 个写样本（广告 SP/SB 编辑与创建、订单备注、包裹编辑、自定义报表指标、海外仓备货删除、入库确认、FBA 发货单创建、物流单号申请、商品本地信息修改）全部 `INVALID_PARAMS`；快照完全一致。

> **边界**：这只证明「写通道通」，不证明「参数正确时会成功」「幂等」「失败回滚」。
> 真实写测试必须指定测试店铺、选可回滚字段、当场改回，并取得用户显式授权。

## 权限控制怎么做（重要）

旧做法「按工具名 deny 9 个写工具」**已失效** —— 写操作现在都走 `sf_execute`，没有独立工具名。

现状：

- Claude Code 用户级：`permissions.ask = ["mcp__Sellfox-MCP__sf_execute"]`，每次执行都人工确认；
- 脚本侧：`--execute` 对写前缀（`edit_/create_/save_/update_/delete_/close_/confirm_/audit_/apply_/cancel_/allocate_/allot_/modify_/mark_/batch_/product_update_`）默认拒绝（退出码 2）；
- 干探测：只发空参数。

## 接入做法

- 用户级 MCP 配置：`claude mcp add -t http -s user Sellfox-MCP https://api-mcp.sellfox.com/mcp -H "X-MCP-Key: <key>"`（写 `~/.claude.json`，不进仓库）。
- key 只放两处：用户级配置 + 父仓库 `.env` 的 `SF_MCP_KEY`（gitignored，供脚本读）。
- 不要写进 `.mcp.json` / `.codex/config.toml` 等被 git 跟踪的文件。

## 与自建 proxy 的分工

- 个人分析：官方 MCP（371 工具，开箱即用）；
- 团队自动化 / 需要凭证隔离、限流、审计：`sellfox-api-proxy`；
- 两者并存，上游同一套数据。

## 可复现命令

```bash
export SF_MCP_KEY=<from .env>

uv run python sellfox_mcp/scripts/probe_mcp.py --list-tools --auth mcp-key
uv run python sellfox_mcp/scripts/probe_mcp.py --catalog --auth mcp-key
uv run python sellfox_mcp/scripts/probe_mcp.py --discover "查询亚马逊利润报表" --operation read
uv run python sellfox_mcp/scripts/probe_mcp.py --describe get_shop_page_list
uv run python sellfox_mcp/scripts/probe_mcp.py --smoke-reads --auth mcp-key
uv run python sellfox_mcp/scripts/probe_mcp.py --probe-writes --auth mcp-key
```

## 相关

- [sellfox_mcp/AGENT_HANDOFF.md](../../../sellfox_mcp/AGENT_HANDOFF.md)
- [sellfox_mcp/docs/reference/official-mcp.md](../../../sellfox_mcp/docs/reference/official-mcp.md)
- [2026-09 可行性调研](../../research/2026-09-20-sellfox-official-mcp-feasibility.md)
