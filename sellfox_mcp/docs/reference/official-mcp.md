---
okf: v0.1
type: Reference
title: 赛狐官方托管 MCP — 端点、鉴权、工具清单与实测证据
description: api-mcp.sellfox.com/mcp 的完整操作参考：两条鉴权路径（API 账号 vs 后台 MCP-Key）、23 个工具的三分类、可复现的探测脚本用法、原始实测输出
tags: [sellfox, mcp, reference, ads, auth, oauth]
timestamp: 2026-09-20
---

# 赛狐官方托管 MCP — 操作参考

> 决策与可行性背景见 [`docs/research/2026-09-20-sellfox-official-mcp-feasibility.md`](../../../docs/research/2026-09-20-sellfox-official-mcp-feasibility.md)。
> 本文只记**怎么用、怎么复现**。

---

## 一、端点

| 项 | 值 |
|---|---|
| URL | `https://api-mcp.sellfox.com/mcp` |
| 传输 | `streamable-http`（响应 `content-type: text/event-stream`） |
| 协议版本 | `2025-06-18` |
| 服务端标识 | `{"name":"sellfox-api","version":"1.30.0"}` |
| 会话 | **有状态** —— `initialize` 后必须带 `mcp-session-id` 头 |

### 两个易踩的点（实测）

1. **`initialize` 不校验凭据** —— 无凭据也返回 200。鉴权推迟到 **工具调用** 时。
   所以「能 initialize」≠「有权限」。
2. **`tools/list` 不带 session 会 400**：`{"code":-32600,"message":"Bad Request: Missing session ID"}`。
   正确顺序：`initialize` →（拿 `mcp-session-id`）→ `notifications/initialized` → `tools/list`。

---

## 二、鉴权：两条独立路径

| | **路径 A（推荐/可用）** | **路径 B** |
|---|---|---|
| 请求头 | `X-Sellfox-Client-Id`<br>`X-Sellfox-Client-Secret` | `X-MCP-Key`（单头） |
| 值来源 | 赛狐 **API 账号** 的 App ID / App Secret | 赛狐后台「业务设置 → 全局 → **MCP管理**」生成 |
| 实测状态 | ✅ **可用**（只读工具已验证返回真实数据） | ❌ `code 40027「未启用MCP功能，请联系管理员」` |
| 开通方式 | 已有 API 账号即可 | 需赛狐**单独开通** |

> 两条路都通到同一个端点，**不是二选一的关系，是两条独立通道**。
> 客服答复针对的是 B；A 现在就能用。

### 凭据纪律

- App ID / Secret 是**生产凭证**。**不要写进仓库任何文件**，不要写进命令行历史。
- 本模块脚本一律从**环境变量**读：`SF_ID` / `SF_SECRET` / `SF_MCP_KEY`。
- `.gitignore` 已排除 `.env*`；提交前用 `git grep <片段>` 自查。

---

## 三、工具清单：23 个（13 只读 / 1 非破坏性写 / 9 破坏性写）

### 13 个只读（已确认可用）

```
get_shop_page_list                     get_order_page_list
get_order_detail                       get_online_product_page_list
get_custom_report_page_list            get_ad_download_task_page_list
get_sp_campaign_list                   get_sp_ad_group_list
get_sp_ad_product_list                 get_sp_keyword_list
get_sp_product_targeting_list          get_sp_negative_keyword_list
get_sp_negative_product_targeting_list
```

### 1 个非破坏性写（有公开文档对应）

`create_ad_download_task` —— 对应公开 OpenAPI `/api/cpc/download/createTask.json`，
**建的是报表下载任务，不改广告数据**。

### ⚠️ 9 个破坏性写（会改线上广告）

```
edit_sp_campaign              create_sp_keyword_targeting
edit_sp_ad_product            create_sp_negative_keyword_targeting
edit_sp_ad_group              create_sp_product_targeting
edit_sp_targeting             create_sp_negative_product_targeting
close_sp_negative_targeting
```

**这 9 个的 schema 极薄**：`required=["shop_id","items"]`，`items` 为 `array<object>`，
`additionalProperties: true` —— **没有任何字段级约束**，字段说明只写在工具的散文描述里
（例：`edit_sp_campaign` 自述「单次最多 100 条，每条除 campaignId 外至少传一个编辑字段」）。

**与公开 API 文档的关系**：`SELLFOX_API/docs/api-reference/`（443 篇，2026-09-17 刷新）
的广告模块**只有查询与报表**（`manageData/*` 分页查询、`hourData/*` 报表、
`download/createTask.json` 建报表任务）。**这 9 个写工具在公开文档里没有对应端点。**

→ 差异**未解释**，且**未验证**。可能：私有接口 / 工具已注册但后端未实现 / 文档未覆盖。
**不要据此认定「赛狐广告可写」。**

---

## 四、可复现的探测

脚本：[`sellfox_mcp/scripts/probe_mcp.py`](../../scripts/probe_mcp.py)（标准库，无依赖）

```bash
# 1) 验证凭据有效性 + IP 白名单（直连公开 OpenAPI 取 token，不发 MCP 请求）
SF_ID=... SF_SECRET=... uv run python sellfox_mcp/scripts/probe_mcp.py --check-token

# 2) 建立 MCP 会话并列出工具（按只读/非破坏性写/破坏性写三分类）
SF_ID=... SF_SECRET=... uv run python sellfox_mcp/scripts/probe_mcp.py --list-tools

# 3) 调只读工具
SF_ID=... SF_SECRET=... uv run python sellfox_mcp/scripts/probe_mcp.py \
    --call get_shop_page_list --args '{"page_no":"1","page_size":"5"}'

# 4) 强制走路径 B
SF_MCP_KEY=... uv run python sellfox_mcp/scripts/probe_mcp.py --list-tools --auth mcp-key
```

### 内置安全护栏

脚本**默认拒绝**调用任何写工具（`edit_*` / `create_*` / `close_*` / `delete_*` / `update_*` /
`remove_*` / `set_*`），以及任何不在已知只读白名单里的工具 —— 除非显式加 `--allow-write`
（拒绝时退出码 2）。

> **为什么默认拒绝**：这些工具会改**线上广告**（`edit_sp_campaign` 单次可改 100 条）。
> 加 `--allow-write` 前请确认已在隔离店铺上验证过，并已获得明确授权。

---

## 五、实测证据（原始输出）

### 5.1 凭据 + IP 白名单

```
GET https://openapi.sellfox.com/api/oauth/v2/token.json?client_id=<id>&client_secret=…&grant_type=client_credentials
→ HTTP 200 | code=0 msg=success | 取到 access_token: True
```

### 5.2 MCP 握手与工具清单（路径 A）

```
initialize : HTTP 200 | session: 有
tools/list : HTTP 200 | 工具数: 23
只读 13 / 非破坏性写 1 / 破坏性写 9
```

### 5.3 只读调用成功

```
tools/call get_shop_page_list {"page_no":"1","page_size":"2"}
→ HTTP 200
  {"code":0,"msg":"success","data":{"pageNo":1,"pageSize":2,"totalPage":45,"totalSize":90,
    "rows":[{"id":"596737","name":"...","sellerId":"...","region":"na",...}]}}
```

> **业务数据不入库** —— 上例只留结构（字段名与分页形状），店铺名/ID 已省略。

### 5.4 路径 B 被挡（对照）

```
X-MCP-Key: <后台生成的 key>
tools/call get_shop_page_list → HTTP 200，内容为:
  {"error":"HTTP 401","detail":"{\"code\":40027,\"msg\":\"未启用MCP功能，请联系管理员\"}"}
```

---

## 六、与自有 `sellfox-api-proxy` 的取舍

| | 官方 MCP | 自有 `sellfox-api-proxy` |
|---|---|---|
| 位置 | 赛狐服务端 | 我们 VPS `api.vilavi.cn/sellfox` |
| 鉴权 | 直接用**生产 App ID/Secret** | 签发自己的 `Bearer sk-...`（钉钉 OIDC） |
| 凭证暴露 | **客户端拿到赛狐凭证** | **客户端拿不到赛狐凭证** |
| 权限模型 | 继承 API 账号 | 自有 per-key 限流 / 账号映射 / 可吊销 |
| 覆盖面 | 23 个工具 | catch-all，任意赛狐路径（443 端点） |
| 当前 | ✅ 可用 | ✅ 已在用 |

**取舍结论**：多人 / 多 Agent 场景**优先走 proxy**（凭证可控、可吊销、可审计）；
官方 MCP 更适合单人自用。

---

## 七、未决

| # | 问题 | 怎么解 |
|---|---|---|
| 1 | 9 个破坏性写工具是真是假 | ① 问赛狐客服「MCP 是否包含 SP 广告写操作」；② 或在**明确指定的测试店铺**上用无副作用载荷验证（**需显式授权**） |
| 2 | 路径 B 何时开通 | 等客服 |
| 3 | 限流（上游 1 req/s）在 MCP 侧是否同样生效 | 高频调用时实测 |

---

## 相关

- [可行性调研](../../../docs/research/2026-09-20-sellfox-official-mcp-feasibility.md) — 决策背景与结论演变
- [`sellfox-api-proxy/`](../../../sellfox-api-proxy/) — 自有 VPS 代理
- [`SELLFOX_API/docs/api-reference/`](../../../SELLFOX_API/docs/api-reference/) — 443 篇公开端点文档
- [`docs/research/2026-09-18-sellfox-private-api-terminology.md`](../../../docs/research/2026-09-18-sellfox-private-api-terminology.md) — 私有接口族 vs 公开 OpenAPI
