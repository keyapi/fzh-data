---
okf: v0.1
type: Reference
title: 把 FAC MCP 接到 ChatGPT（ensh 测试站）
description: ChatGPT 建应用表单每个字段填什么、服务端已实测的 OAuth 能力、报错阶梯与未验证项
tags: [chatgpt, fac, erpnext, mcp, oauth, ensh, reference]
timestamp: 2026-09-20
---

# 把 FAC MCP 接到 ChatGPT（ensh 测试站）

> **前置**：ChatGPT 付费档位 + 已开开发者模式；ensh 测试站账号
> **通用要求**（认证方式、回调地址、与 Claude Desktop 的差异）见 [connector-requirements.md](connector-requirements.md)
> **状态**：服务端能力已实测通过；**ChatGPT 侧端到端尚未验证**（需人工点授权，见文末）

---

## 表单怎么填

| 字段 | 填什么 |
|---|---|
| 名称 | `EN MCP 测试环境`（随意） |
| 描述 | `EN 测试环境`（随意） |
| 连接 | **服务器 URL**（不是「隧道」） |
| URL | `https://ensh.vilavi.cn/api/method/frappe_assistant_core.api.fac_endpoint.handle_mcp` |
| 身份验证 | **`OAuth`** |
| 「标头方案」下拉 | 选 OAuth 后**不出现**，无需理会 |
| 「我了解并希望继续」 | 勾上 |

点「创建」→ 弹出浏览器跳 `ensh.vilavi.cn` → 用**你自己的 ERPNext 账号**登录 → 授权。

工具权限跟随授权账号在 ERPNext 里的角色权限（与 Claude Desktop 一致）；ChatGPT 不会拿到超出该账号的能力。

### 为什么不能选另外两个

- ❌ **「访问令牌/API 密钥」** —— FAC 端点只认 OAuth，没有静态 token 方案。
  选了它才会冒出「标头方案（持有者/基本/自定义标头）」下拉；**那个下拉本身就是误导**。
- ❌ **「无身份验证」** —— 端点实测返回 `401 unauthorized / Authentication required`。

---

## 服务端能力实测（ensh.vilavi.cn，2026-09-20）

全部为直接探测结果，**非文档推断**：

| 检查项 | 结果 |
|---|---|
| MCP 端点无鉴权访问 | `401` + `WWW-Authenticate: Bearer realm="Frappe Assistant Core", resource_metadata="..."` |
| 传输方式 | `StreamableHTTP`，MCP 协议版本 `2025-06-18`（`/.well-known/openid-configuration` 的 `mcp_transport` / `mcp_protocol_version`） |
| `/.well-known/oauth-authorization-server` | ✅ 200，字段完整 |
| `/.well-known/oauth-protected-resource` | ✅ 200，`bearer_methods_supported: ["header"]` |
| `/.well-known/openid-configuration` | ✅ 200（FAC 另发布，与上者互补） |
| `code_challenge_methods_supported` | `["S256"]` —— 满足 ChatGPT 强制 PKCE 要求 |
| `token_endpoint_auth_methods_supported` | `["none","client_secret_basic","client_secret_post"]` —— 含 `none`，即支持公开客户端 |
| `registration_endpoint`（DCR / RFC 7591） | ✅ 已发布，**且服务端已开启**（空 body 返回 pydantic 校验错，而非 404 `Dynamic client registration is not enabled`） |
| **拿 ChatGPT 真实 redirect_uri 实测注册** | ✅ **`HTTP 201 Created`**，`client_id: co3m2l4e7h`（探针记录测完即删） |

最后一行是关键证据：ChatGPT 的回调地址
`https://chatgpt.com/connector_platform_oauth_redirect` **能通过 FAC 的 DCR 校验**。

依据（FAC 上游 `frappe_assistant_core/utils/oauth_compat.py::validate_dynamic_client_metadata`）：DCR **只校验 scheme** ——
非 `https` 且非 `localhost` 才拒，**不限制域名**，所以任何 https 回调都能注册。

### 一个观察：`token_endpoint_auth_method: none` 也返回了 client_secret

实测响应里带 `client_secret: 1a70...`，即便请求声明了 `none`。

这是**有意行为**，源码写明（FAC 上游 `frappe_assistant_core/utils/oauth_compat.py::create_oauth_client` 的 v15 分支）：

```python
# Build response - always include client_secret
# Even if token_endpoint_auth_method is "none", the client should receive
# the secret. They may choose not to use it for authentication, but should have it.
```

ChatGPT 在 `none` 模式下不会用它。**不构成问题**，仅记录以免日后误判为「注册出错」。

### 另一个佐证：授权页一定会弹

同处源码写死 `doc.skip_authorization = False` —— FAC 不跳过授权确认。
点「创建」后**必定**会看到 `ensh.vilavi.cn` 的同意页让你选账号授权；看不到就是流程没走到那一步。

### 「Allowed Public Client Origins」不用动

`Assistant Core Settings → OAuth → Allowed Public Client Origins` 在源码里（FAC 上游 `frappe_assistant_core/api/oauth_cors.py`）
只是把值写进 `frappe.conf.allow_cors` / `frappe.local.allow_cors` —— **纯 CORS**，只约束浏览器侧 XHR。

ChatGPT 的流程里：注册请求来自 OpenAI 服务端（无 `Origin` 头）、授权是浏览器**顶层跳转**（不受 CORS 约束）。
所以该字段**预期无需修改**。仅在真的报 CORS 错时才去加 `https://chatgpt.com`。

> FAC 官方 quick start 让人加 `http://localhost:6274` 是说给 **MCP Inspector** 那种浏览器 XHR 客户端的，
> **不要照搬**。

**真要改时的正确位置**：源码 `oauth_cors.py` 里配置有优先级 ——
① `site_config.json` 的 `oauth_cors_allowed_origins`（注释标注为 **RECOMMENDED**）
优先于 ② Assistant Core Settings 的同名字段（注释标注为 **EXPERIMENTAL**）。
即 site_config 一旦设了值就直接 return，**UI 里改将被忽略**。改之前先确认 site_config 有没有设过。

---

## 报错阶梯

| 现象 | 原因 | 处理 |
|---|---|---|
| 提示服务器不支持 OAuth / 建应用直接失败 | 未开开发者模式；或 OpenAI 服务端取不到 metadata | 开开发者模式；确认两个 `.well-known` 公网可达 |
| 建应用时要求**手填 Client ID / Secret / 授权 URL / Token URL** | ChatGPT 没走 DCR，回落手工客户端 | 在 ERPNext 建 `OAuth Client`（Setup → Integrations → OAuth Client）：redirect uri 填 `https://chatgpt.com/connector_platform_oauth_redirect`，grant type `Authorization Code`，把 client_id / secret 填回 ChatGPT |
| 授权报 `redirect_uri_mismatch` / `invalid_client` | redirect_uri 与注册值不一致 | 从 ChatGPT 弹窗**照抄**实际回调地址后重新注册 |
| CORS 报错 | 少见（见上文） | 才去 `Allowed Public Client Origins` 加 `https://chatgpt.com` |
| 授权页 400 / scope 相关错 | FAC metadata 未发布 `scopes_supported` | 授权 URL 去掉 scope；手工客户端把 scope 设为 `all openid` |
| 连上了但工具调用 403 | 授权账号 ERPNext 角色权限不足 | 换有权限的账号授权 |

---

## 尚未验证

**ChatGPT 侧的完整端到端流程没做**（需要你的 ChatGPT 会话 + ERPNext 登录，本地无法代劳）。
已验证的止于「服务端接受 ChatGPT 的注册参数并签发 client_id」。
授权跳转、token 交换、`tools/list` 拉取、工具实际执行，都要实际点一次才算数 —— 若卡住，按上表定位。

---

## 运维附注：OAuth Client 会累积

测试站 `OAuth Client` 里累积了 7 条同名 `MCP CLI Proxy` 记录（`localhost:5535` / `127.0.0.1:5535`），
时间跨度 2026-06-08 → 2026-08-27 —— 说明 **Claude Desktop 每次重新授权都会新建一条 OAuth Client 行，旧的不回收**。
不紧急，但列表会持续变长；清理时按 `creation` 排序删旧即可。

---

## 原始来源

**服务端实测**（本次，2026-09-20）

- `https://ensh.vilavi.cn/api/method/frappe_assistant_core.api.fac_endpoint.handle_mcp` — 401 与 metadata
- `https://ensh.vilavi.cn/.well-known/oauth-authorization-server`
- `https://ensh.vilavi.cn/.well-known/oauth-protected-resource`
- `https://ensh.vilavi.cn/.well-known/openid-configuration`
- `https://ensh.vilavi.cn/api/method/frappe_assistant_core.api.oauth_registration.register_client`

**FAC 源码与文档**（GitHub: [buildswithpaul/Frappe_Assistant_Core](https://github.com/buildswithpaul/Frappe_Assistant_Core)）

- [docs/getting-started/GETTING_STARTED.md](https://github.com/buildswithpaul/Frappe_Assistant_Core/blob/main/docs/getting-started/GETTING_STARTED.md) — Option C: ChatGPT Integration
- [docs/getting-started/oauth/oauth_setup_guide.md](https://github.com/buildswithpaul/Frappe_Assistant_Core/blob/main/docs/getting-started/oauth/oauth_setup_guide.md) — DCR 与 Allowed Public Client Origins 场景
- [docs/getting-started/oauth/oauth_quick_start.md](https://github.com/buildswithpaul/Frappe_Assistant_Core/blob/main/docs/getting-started/oauth/oauth_quick_start.md)
- [frappe_assistant_core/api/oauth_registration.py](https://github.com/buildswithpaul/Frappe_Assistant_Core/blob/main/frappe_assistant_core/api/oauth_registration.py) — RFC 7591 实现
- [frappe_assistant_core/utils/oauth_compat.py](https://github.com/buildswithpaul/Frappe_Assistant_Core/blob/main/frappe_assistant_core/utils/oauth_compat.py) — redirect_uri 校验规则、client_secret 行为
- [frappe_assistant_core/api/oauth_cors.py](https://github.com/buildswithpaul/Frappe_Assistant_Core/blob/main/frappe_assistant_core/api/oauth_cors.py) — 证明 origins 字段是纯 CORS

**ChatGPT 侧要求** —— 见 [connector-requirements.md](connector-requirements.md#原始来源)（检索所得，非一手文档）

---

## 相关文档

- [connector-requirements.md](connector-requirements.md) — 通用要求与与 Claude Desktop 的差异
- `docs/fac-mcp-setup.md` — FAC 在 Claude Desktop 的接入（本文的对照路径）
- `docs/mcp-setup.md` — MCP 选型与安装指南（canonical 入口）
