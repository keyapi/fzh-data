---
okf: v0.1
type: Reference
title: ChatGPT 自定义连接器对 MCP 服务器的硬性要求
description: ChatGPT 做 MCP 客户端时对服务端的要求 — 只支持 OAuth 2.1+PKCE、需 DCR 或 CIMD、无本地进程；含与 Claude Desktop 的差异
tags: [chatgpt, mcp, oauth, dcr, connector, reference]
timestamp: 2026-09-20
---

# ChatGPT 自定义连接器对 MCP 服务器的硬性要求

> **适用**：任何要接到 ChatGPT 的 MCP 服务器。服务器专有的填写步骤见同目录专文。
> ⚠️ **证据分级**：本文分「我们实测」与「检索所得」两类。OpenAI 侧的行为我们拿不到一手文档，
> 相关结论来自第三方来源，**已在每处标注**。参见 `docs/solutions/documentation-gaps/unverified-external-api-claims-in-docs.md`。

---

## 一、最关键的一条：ChatGPT 是服务端直连，没有本地进程

这是与 Claude Desktop 的**根本差异**，也是最多人踩坑的地方：

| | Claude Desktop | ChatGPT |
|---|---|---|
| 连接方式 | 本地 `mcp-remote` 桥接（stdio ↔ StreamableHTTP），或裸 `url` 字段 | OpenAI 服务端**直连** MCP endpoint |
| 本机进程 | 有（`npx mcp-remote`） | **无** |
| 客户端注册时机 | 本机首次 OAuth 时注册 | OpenAI 服务端建应用时注册 |
| 注册出的回调 | `http://localhost:5535/oauth/callback` | `https://chatgpt.com/connector_platform_oauth_redirect` |
| Token 缓存 | 本机 `~/.mcp-auth/` | OpenAI 侧托管 |
| endpoint 可达性 | 可以是 localhost | **必须公网可达** |

**推论**：`docs/fac-mcp-setup.md`（Claude Desktop 版）里的排错条目 —— `~/.mcp-auth` 清理、
`taskkill /F /IM node.exe`、`EADDRINUSE` 端口冲突、「URL 必须写在 `--transport` 前面」——
**在 ChatGPT 场景全部不适用**。别照搬。

---

## 二、认证：只支持 OAuth

*（检索所得 —— 非 OpenAI 一手文档）*

ChatGPT 自定义连接器按 MCP 授权规范（2025-06-18 revision）走 **OAuth 2.1**，要求：

| 要求 | 说明 |
|---|---|
| **PKCE + S256** | 授权服务器 metadata 的 `code_challenge_methods_supported` 必须含 `S256`。隐式流已移除，必须有 authorization_code |
| **DCR（RFC 7591）或 CIMD** | 必须发布 `registration_endpoint`；DCR 关闭时 ChatGPT 报「MCP server does not implement OAuth」 |
| **`/.well-known/oauth-protected-resource`**（RFC 9728） | 返回 `resource` 与 `authorization_servers`。401 响应的 `WWW-Authenticate: Bearer resource_metadata="…"` 也能告知 |
| **`/.well-known/oauth-authorization-server`**（RFC 8414）或 `openid-configuration` | 含 `issuer` / `authorization_endpoint` / `token_endpoint` / `registration_endpoint` 等 |
| **resource 参数**（RFC 8707） | ChatGPT 会带 `resource`，服务器应把它回显到签发的 token 里 |
| **不支持** | API Key、client_credentials、service account、JWT bearer assertion、自定义 mTLS 证书 |

### 关于界面上的「访问令牌/API 密钥」

ChatGPT 的建应用界面**确实提供**「访问令牌/API 密钥」选项（带「标头方案：持有者 / 基本 / 自定义标头」下拉）。
但那只是「往请求头塞个静态值」，**能不能用取决于你的服务器认不认静态 token** ——
文档层面的要求仍是 OAuth。

**判断方法**：拿目标 endpoint 无凭据打一次，看返回。
- `401` + `WWW-Authenticate: Bearer ... resource_metadata="…"` → 该服务器要 OAuth，**必须选 OAuth**
- 返回正常 → 才可能走得通静态 token

> 实测例（FAC）：401 + `resource_metadata` → 必须 OAuth。详见 [fac-mcp-oauth-connect.md](fac-mcp-oauth-connect.md)。

---

## 三、回调地址

*（检索所得）*

`https://chatgpt.com/connector_platform_oauth_redirect`

**不要从记忆或本文档抄死值** —— 该域名变更过。正确做法是**从 ChatGPT 建应用界面照抄实际显示的回调地址**。

已知的历史/变体值（配白名单时可能见到）：`https://chatgpt.com/aip/oauth/callback`、
`https://chat.openai.com/aip/oauth/callback`。

> 无论走 stable 回调还是 legacy 回调，**域名都是 `chatgpt.com`**，所以按 origin 配白名单时值相同。

---

## 四、连接方式：服务器 URL 还是隧道

建应用时「连接」有两个选项：

- **服务器 URL** —— OpenAI 直接连你的公网 endpoint。**多数情况选这个**
- **隧道** —— 走 OpenAI 的 Secure MCP Tunnel，需要你在自己侧跑 tunnel 客户端。仅当 endpoint **不能**公网暴露时才需要

---

## 五、前置条件

*（检索所得，一致性较高）*

- **付费档位** —— 自定义 MCP 不对免费用户开放（Business / Enterprise / Edu / Plus / Pro 可用性随版本变动）
- **开发者模式** —— 设置 → 应用和连接器 → 高级设置

---

## 六、通用失败模式

| 现象 | 常见原因 |
|---|---|
| 报「服务器不支持 OAuth」 | 服务器没发布 `registration_endpoint`，或两处 `.well-known` 取不到 |
| 建应用时要求手填 Client ID / Secret | ChatGPT 没走 DCR，回落手工客户端 → 去服务器侧手工建一个 OAuth Client 填回来 |
| `redirect_uri_mismatch` / `invalid_client` | 注册的 redirect_uri 与实际回调不一致 → 从界面照抄后重新注册 |
| CORS 错误 | 少见。ChatGPT 服务端注册不带 `Origin` 头、授权是浏览器顶层跳转，**都不受 CORS 约束**；真报了再去服务器侧加 origin 白名单 |
| 授权页 scope 报错 | 服务器 metadata 未发布 `scopes_supported` → 去掉 scope 或用服务器默认 scope |
| 连上但工具调用 403 | 授权账号在服务器侧的权限不足 |

服务器专有的定位表见对应专文。

---

## 原始来源

**我们实测**（2026-09-20，针对 FAC）

- `https://ensh.vilavi.cn/api/method/frappe_assistant_core.api.fac_endpoint.handle_mcp` — 401 与 `WWW-Authenticate`
- `https://ensh.vilavi.cn/.well-known/oauth-authorization-server` / `oauth-protected-resource` / `openid-configuration`

**检索所得**（非一手文档）

- [OpenAI — Authentication (Plugins build)](https://developers.openai.com/plugins/build/auth)
- [SigilDERG-Custom-MCP — CHATGPT_OAUTH_CONFIG.md](https://github.com/Superuser666-Sigil/SigilDERG-Custom-MCP/blob/main/docs/CHATGPT_OAUTH_CONFIG.md) — 回调地址
- [springai-mcp-gateway — CHATGPT.md](https://github.com/oalles/springai-mcp-gateway/blob/main/CHATGPT.md)
- [Microsoft Learn — 在 ChatGPT 或 Claude 中使用 Sentinel MCP 连接器](https://learn.microsoft.com/en-us/azure/sentinel/datalake/sentinel-mcp-chatgpt-claude-connector) — 回调地址、开发者模式步骤
- [Sentry MCP #742 — Investigate ChatGPT MCP authentication requirements](https://github.com/getsentry/sentry-mcp/issues/742)

**协议规范**

- [MCP Streamable HTTP 规范（2025-06-18）](https://spec.modelcontextprotocol.io/specification/2025-06-18/basic/transports/#streamable-http)
- [MCP 授权规范](https://spec.modelcontextprotocol.io/specification/2025-06-18/basic/authorization/)
