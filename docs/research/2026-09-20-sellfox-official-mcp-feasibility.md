---
type: Research
title: 赛狐官方 MCP 可行性 — 官方托管端点在，自定义头鉴权，无 OAuth；23 个工具中 11 个是「写」
description: 实测 https://api-mcp.sellfox.com/mcp 可用（protocol 2025-06-18，serverInfo sellfox-api v1.30.0）。鉴权走 X-Sellfox-Client-Id/Secret 请求头，非 OAuth —— 与 FAC 相反。23 个工具含 11 个 SP 广告写操作，与项目既有「赛狐广告无写 API」约束冲突，需复核
tags: [sellfox, mcp, research, oauth, ads, feasibility]
timestamp: 2026-09-20
---

# 赛狐官方 MCP 可行性调研（2026-09-20）

## 一句话结论

**能接，而且比 FAC 简单。** 赛狐有**官方托管**的 MCP 服务：

| 项 | 值 | 来源 |
|---|---|---|
| 端点 | `https://api-mcp.sellfox.com/mcp` | **实测（本机 curl）** |
| 传输 | `streamable-http` | 实测（返回 `content-type: text/event-stream`） |
| 协议版本 | `2025-06-18` —— **与 FAC 完全相同** | 实测 `initialize` 响应 |
| 服务端标识 | `{"name":"sellfox-api","version":"1.30.0"}` | 实测 |
| 鉴权 | 请求头 `X-Sellfox-Client-Id` + `X-Sellfox-Client-Secret` | 实测（服务端自报） |
| OAuth | ❌ **不需要** | 实测（`initialize` 无凭据即 200） |

**关键差异：鉴权方式与 FAC 正好相反。**

- FAC：**OAuth 2.1 + PKCE + DCR**，ChatGPT 里必须选「OAuth」
- 赛狐：**静态请求头**，ChatGPT 里必须选「**访问令牌/API 密钥** → 标头方案「**自定义标头**」」

也就是说 —— 建 ChatGPT 应用时那个「标头方案（持有者/基本/自定义标头）」下拉，**对 FAC 是死路，对赛狐才是正解**。

---

## 一、实测记录（本机直接探测，可复现）

### 1.1 `initialize` 无需凭据即成功

```
POST https://api-mcp.sellfox.com/mcp
Accept: application/json, text/event-stream
→ HTTP/2 200, text/event-stream, mcp-session-id: <...>

{"jsonrpc":"2.0","id":1,"result":{
  "protocolVersion":"2025-06-18",
  "capabilities":{"experimental":{},"prompts":{...},"resources":{...},"tools":{...}},
  "serverInfo":{"name":"sellfox-api","version":"1.30.0"},
  "instructions":"SellfoxAPI MCP Server，提供店铺列表、订单列表、订单详情查询和自定义报表数据查询功能"}}
```

> 注意 `initialize` **不校验凭据** —— 鉴权推迟到工具调用时。所以「能 initialize」不等于「有权限」。

### 1.2 服务是有状态的：`tools/list` 需要 session

不带 `mcp-session-id` 直接调 `tools/list`：

```
HTTP/2 400
{"error":{"code":-32600,"message":"Bad Request: Missing session ID"}}
```

必须先 `initialize` 拿 `mcp-session-id` 头、再发 `notifications/initialized`，之后才能 `tools/list`。

### 1.3 鉴权在工具调用时校验

| 场景 | 结果 |
|---|---|
| 无凭据调 `get_shop_page_list` | 返回错误文本：`缺少凭证配置。stdio 模式：请设置环境变量 SELLFOX_CLIENT_ID 和 SELLFOX_CLIENT_SECRET；streamable-http 模式：请在请求头中携带 X-Sellfox-Client-Id 和 X-Sellfox-Client-Secret` |
| **假凭据**调 `get_shop_page_list` | 服务端转去调 `https://openapi.sellfox.com/api/oauth/v2/token.json?client_id=...&client_secret=...&grant_type=client_credentials` → **401 Authorization Required** |

两条推论（均来自实测）：

1. 官方 MCP **自己**去 `openapi.sellfox.com` 用 **client_credentials** 换 token —— 所以它后台用的就是赛狐公开 OpenAPI。
2. 它也支持 **stdio 模式**（错误文本自己说了 `SELLFOX_CLIENT_ID` / `SELLFOX_CLIENT_SECRET` 环境变量）→ 存在可本地部署的形态。

---

## 二、⚠️ 工具清单：23 个，其中 11 个是「写」

这是本次最需要你注意的发现。`tools/list` 实测（非文档推断）：

**读（12 个）**

`get_order_detail`、`get_order_page_list`、`get_shop_page_list`、
`get_custom_report_page_list`、`get_online_product_page_list`、`get_ad_download_task_page_list`、
`get_sp_ad_product_list`、`get_sp_campaign_list`、`get_sp_ad_group_list`、
`get_sp_keyword_list`、`get_sp_product_targeting_list`、
`get_sp_negative_keyword_list`、`get_sp_negative_product_targeting_list`

**写（11 个）** ← **能改线上广告**

| 工具 | 说明（摘自工具自述） |
|---|---|
| `create_ad_download_task` | 创建广告报告下载任务 |
| `edit_sp_campaign` | SP 广告活动批量编辑，**单次最多 100 条** |
| `edit_sp_ad_product` | SP 广告产品批量编辑 |
| `edit_sp_ad_group` | SP 广告组批量编辑 |
| `edit_sp_targeting` | SP 投放批量编辑 |
| `close_sp_negative_targeting` | SP 否定投放批量关闭 |
| `create_sp_keyword_targeting` | SP 关键词投放批量创建 |
| `create_sp_negative_keyword_targeting` | SP 否定关键词批量创建 |
| `create_sp_product_targeting` | SP 商品投放批量创建 |
| `create_sp_negative_product_targeting` | SP 否定商品投放批量创建 |

### 与项目既有结论冲突，必须复核

项目记忆里记着一条硬约束：**「赛狐广告无写 API」**（AI 接入载体选型的论据之一，2026-07 裁决）。

**本次实测与该约束直接冲突** —— 官方 MCP v1.30.0 明确暴露了 SP 广告的编辑/创建/否定投放。

两种可能，**尚未分辨**：

1. 2026-07 之后赛狐新增了广告写接口（即该约束已过期）
2. 当时结论针对的是**「私有接口族」**，而 MCP 走的是**公开 OpenAPI**（参见 `docs/research/2026-09-18-sellfox-private-api-terminology.md`）

> **不要直接认定记忆是错的，也不要继续沿用那条约束。** 建议单独开一次核实：用真实凭据调一个只读的 `get_sp_campaign_list`，再对照 `SELLFOX_API/docs/api-reference/` 里广告模块（37 个 md）看写接口是否存在。

### 第三方教程已过时

CSDN 那篇接入教程称「目前工具为查询类，文章称不涉及数据修改」—— 与线上 v1.30.0 实测**不符**。**文档滞后于实现，以实测为准。**

---

## 三、怎么填（各客户端）

统一参数：

```
URL    : https://api-mcp.sellfox.com/mcp
传输   : streamable-http
请求头 : X-Sellfox-Client-Id: <App ID>
        X-Sellfox-Client-Secret: <App Secret>
```

| 客户端 | 做法 |
|---|---|
| **Claude Code** | `claude mcp add --transport http sellfox-api https://api-mcp.sellfox.com/mcp --header "X-Sellfox-Client-Id: ..." --header "X-Sellfox-Client-Secret: ..."` |
| **Claude Desktop** | `claude_desktop_config.json` 加 `{"type":"streamable-http","url":"...","headers":{...}}` |
| **Codex** | 设置 → MCP 服务器 → 添加，传输选「流式 HTTP」，标头加两行 |
| **Cursor** | `~/.cursor/mcp.json` 同结构 |
| **ChatGPT** | 建应用 → 服务器 URL 填端点 → 身份验证选「**访问令牌/API 密钥**」→ 标头方案选「**自定义标头**」→ 填 `X-Sellfox-Client-Id` / `X-Sellfox-Client-Secret` |

> ChatGPT 的「自定义标头」下拉只允许**一个**自定义头 —— 赛狐需要**两个**。这是接 ChatGPT 时**第一个要试的点**，若下拉只能填一个，此路不通（详见「未决」）。

---

## 四、前提条件（不满足就会失败）

1. **开通开放接口**：赛狐后台 → 业务设置 → 全局 → 开放接口
2. **创建 API 账号**取 App ID / App Secret，状态「可用」，有效期设长期
3. **IP 白名单**：把调用方公网 IP 加进白名单（上限 100 个）。**未加白名单会被拒，是第三方教程里最常见的失败原因**
4. 权限**完全继承该 API 账号** —— 建议**为 MCP 单独建账号**，便于隔离与随时禁用

**我们的现状**（来自仓库调研）：白名单里已有一个 VPS IP `82.156.238.248`；赛狐**最多 5 个 API 账号，目前剩 3 个**。

---

## 五、与自有 `sellfox-api-proxy` 的关系

两条路并存，**不冲突**：

| | 官方托管 MCP | 我们的 `sellfox-api-proxy` |
|---|---|---|
| 位置 | 赛狐自己的服务端 | 我们 VPS `api.vilavi.cn/sellfox` |
| 鉴权 | App ID/Secret 请求头 | 自己的 `Bearer sk-...`（钉钉 OIDC 签发） |
| 权限模型 | 继承赛狐 API 账号 | **我们自己**的 per-key 限流与账号映射 |
| 覆盖面 | 23 个工具（广告为主 + 订单/店铺/报表） | **catch-all，任意赛狐路径**（443 端点） |
| 适合 | 开箱即用、广告场景 | 需要自控权限/审计/限流，或要覆盖 MCP 没暴露的端点 |

**判断**：若只要广告+订单+店铺+报表 → 官方 MCP 够用、零部署；若要**更细的权限管控或覆盖更多端点** → 在自有 proxy 上加一层 MCP（仓库里已有两个可抄的骨架：`sellfox_shipping/mcp_tools.py` 的 FastMCP、`tongtool_api/mcp_http.py` 的手写 JSON-RPC）。

---

## 六、未决 / 风险

| # | 问题 | 影响 |
|---|---|---|
| 1 | **IP 白名单对官方托管 MCP 是否生效？** 服务端在赛狐自己的基础设施上，调用方 IP 不是我们的 —— 可能不需要加白名单，也可能仍按 API 账号校验。**只有真实凭据能验证** | 决定要不要把我们出口 IP 加白名单 |
| 2 | **ChatGPT 的「自定义标头」能否填两个头？** 赛狐需要 Client-Id + Secret 两个 | 决定 ChatGPT 这条路通不通 |
| 3 | **写权限的管理风险** —— 11 个写工具能批量改线上 SP 广告（单次 100 条） | 必须限制；见下 |
| 4 | 限流 **1 req/s**（上游），超了报 `40019` | Agent 容易打满，需要节流 |
| 5 | API 账号上限 5 个，**已用 2 剩 3** | 建 MCP 专用账号前先确认余量 |
| 6 | 官方 MCP **自身无细粒度 scope** —— 权限粒度只到「API 账号」 | 想只读，就得建一个**只读 API 账号** |

### 写权限该如何处置（建议）

按项目既有安全偏好（「范围必须先确认、绝不擅自扩大」）：

1. **默认只读**：给 MCP 建一个**权限收窄到只读**的 API 账号。这样即使工具清单里有写工具，调用也会被赛狐侧拒绝 —— **权限在服务端，比在 prompt 里叮嘱可靠**。
2. 若确实需要写：先在**一个测试店铺**上跑，且必须人工确认。
3. 客户端侧也二次设限（Claude Desktop 可把写工具放进需确认的组；ChatGPT 侧同理）。

---

## 参考 URL

**实测**（2026-09-20，可复现）

- `https://api-mcp.sellfox.com/mcp` —— `initialize` / `tools/list` / `tools/call` 三组探测

**官方**

- 赛狐帮助中心 · 业务设置（开放接口入口）：<https://www.sellfox.com/help/features/business-settings>
- 赛狐博客 ·「狐友会」AI 本地部署与 Skill 实战：<https://www.sellfox.com/blog/article/events-huyouhui-ai-local-deployment-skill-amazon-shijiazhuang-qingdao>

**第三方（非官方，需自行甄别）**

- CSDN 接入教程（Codex / Claude Code / Trae / WorkBuddy）：<https://tianqi.csdn.net/6aacf59b5c13c42b539d194c.html>
  - ⚠️ 该文称「工具为查询类、不涉及数据修改」—— **与线上 v1.30.0 实测不符**，已过时
- 社区自建项目 `shuolol/sellfox-mcp`（Node 22+，本地 3100 端口，API Key `sk-xxx`，MIT）：<https://github.com/shuolol/sellfox-mcp>
  - 与官方托管端点是**两回事**，勿混
- LobeHub 收录页：<https://lobehub.com/mcp/shuolol-sellfox-mcp>

**仓库内相关**

- `sellfox-api-proxy/` —— 自有 VPS 代理（catch-all 443 端点）
- `SELLFOX_API/docs/api-reference/` —— 443 个端点 md + `llms.txt` / `llms_parsed.json`
- `sellfox_shipping/mcp_tools.py` —— 现有 FastMCP 骨架（仅发货域，7 工具）
- `docs/research/2026-09-18-sellfox-private-api-terminology.md` —— 私有接口族 vs 公开 OpenAPI
- `.agents/skills/sellfox-api/SKILL.md` —— 自有代理的调用方式与约束
