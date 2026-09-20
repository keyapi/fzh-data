---
type: Research
title: 赛狐官方 MCP 可行性 — 端点在但当前「未启用」；鉴权用 X-MCP-Key；工具清单有 11 个写工具但与公开 API 文档对不上
description: 实测 api-mcp.sellfox.com/mcp 结构可用（protocol 2025-06-18），但当前返回 40027「未启用MCP功能」与后台「不可用」一致。鉴权以官方后台给出的单头 X-MCP-Key 为准。tools/list 暴露 11 个 SP 广告写工具，而公开 API 文档（443 篇，09-17 刷新）广告模块只有读 —— 差异未解释，启用后须复核
tags: [sellfox, mcp, research, ads, feasibility, oauth]
timestamp: 2026-09-20
---

# 赛狐官方 MCP 可行性调研（2026-09-20）

## 一句话结论

**有官方托管 MCP，协议层已经通了，但当前功能未启用 —— 现在还不能用，等赛狐开通。**

| 项 | 值 | 证据强度 |
|---|---|---|
| 端点 | `https://api-mcp.sellfox.com/mcp` | **实测** |
| 传输 | `streamable-http` | 实测（`content-type: text/event-stream`） |
| 协议版本 | `2025-06-18` —— **与 FAC 相同** | 实测 `initialize` |
| 服务端标识 | `{"name":"sellfox-api","version":"1.30.0"}` | 实测 |
| 鉴权 | **单头 `X-MCP-Key`**（官方后台生成） | 官方后台 + **实测** |
| 当前状态 | ❌ **未启用** → `code 40027「未启用MCP功能，请联系管理员」` | **实测** |
| OAuth | 不需要 | 实测 |

> **注意**：赛狐官方是**主动提供**这个功能的（后台有「业务设置 → 全局 → MCP管理」页面，状态显示「不可用」）。
> 所以这是「**等客服开通**」的问题，不是「有没有」的问题。

### 一、当前不可用 —— 已实测确认

用官方后台给出的 `X-MCP-Key` 调一个**只读**工具：

```
initialize  : HTTP 200   (session 建立成功)
tools/list  : HTTP 200   → 23 个工具
tools/call get_shop_page_list → HTTP 200，但返回:
  {"error":"HTTP 401","detail":"{\"code\":40027,\"msg\":\"未启用MCP功能，请联系管理员\"}"}
```

**结论**：协议握手、鉴权头、工具列举全部正常，**卡在「功能未启用」这一层**。与后台显示「不可用」一致。

→ 在赛狐开通前，**任何接入都不必做**（本机/客户端侧改了也不会生效）。

---

## 二、鉴权：以官方后台为准，用 `X-MCP-Key` 单头

官方后台「业务设置 → 全局 → MCP管理」给出的是**单个**请求头：

```json
{
  "mcpServers": {
    "Sellfox-MCP": {
      "type": "streamableHttp",
      "url": "https://api-mcp.sellfox.com/mcp",
      "headers": { "X-MCP-Key": "<后台生成的 key>" }
    }
  }
}
```

**CSDN 那篇教程给的是另一套**：`X-Sellfox-Client-Id` + `X-Sellfox-Client-Secret`（两个头，用 API 账号的 App ID/Secret）。

两者关系（据实测推断，**未完全确认**）：

| 头 | 来源 | 实测表现 |
|---|---|---|
| `X-MCP-Key` | 官方后台 MCP 管理页 | 能过认证层，直达「未启用」判断 |
| `X-Sellfox-Client-Id`/`Secret` | API 账号的 App ID/Secret | 服务端会拿去 `openapi.sellfox.com/api/oauth/v2/token.json` 换 token；假值得 401 |

服务端自己的错误文本提示的是 Client-Id/Secret 那套 —— 说明**两套都认**。
**但接入时应以官方后台给的 `X-MCP-Key` 为准**（那是赛狐为 MCP 专门生成的，权限与审计都挂在它上面）。

> ⚠️ **key 是凭证，不要写进任何提交的文件或文档。** 本文不记录其值。

---

## 三、⚠️ 工具清单有 11 个「写」，但与公开 API 文档对不上

`tools/list` 实测（**无凭据也返回，清单是静态的**）：**23 个工具**。

**读（12）**：`get_shop_page_list`、`get_order_page_list`、`get_order_detail`、`get_online_product_page_list`、`get_custom_report_page_list`、`get_ad_download_task_page_list`、`get_sp_campaign_list`、`get_sp_ad_group_list`、`get_sp_ad_product_list`、`get_sp_keyword_list`、`get_sp_product_targeting_list`、`get_sp_negative_keyword_list`、`get_sp_negative_product_targeting_list`

**写（11）**：`edit_sp_campaign`（自述单次最多 100 条）、`edit_sp_ad_product`、`edit_sp_ad_group`、`edit_sp_targeting`、`close_sp_negative_targeting`、`create_sp_keyword_targeting`、`create_sp_negative_keyword_targeting`、`create_sp_product_targeting`、`create_sp_negative_product_targeting`、`create_ad_download_task`

### 但公开 API 文档里广告模块**只有读**

核对本地镜像 `SELLFOX_API/docs/api-reference/`（**443 篇，2026-09-17 刷新，不陈旧**），广告模块全部端点路径去重后：

```
/api/cpc/manageData/{sp,sb,sd}{Campaign,Group,AdProduct,Target,Keyword,...}.json   ← 查询
/api/cpc/hourData/*.json                                                          ← 小时报表
/api/cpc/searchTerms/pageList.json                                                ← 查询
/api/cpc/download/createTask.json                                                 ← 创建「报表下载任务」
```

- `manageData/*` **是查询不是写** —— 逐个看过参数（`运行状态: enabled/paused/archived`、`不传默认查询全部`、`pageSize`），是分页查询语义。
- 唯一含 `create` 的 `download/createTask.json` 建的是**报表下载任务**，不改广告数据。

**即：公开 OpenAPI 里没有「改广告实体」的端点**，与项目既有约束「赛狐广告无写 API」一致。

### 差异如何解读 —— **未解释，也不该现在下结论**

MCP 的 11 个写工具**在我们手上的公开 API 文档里没有对应端点**。至少三种可能，**当前无法分辨**：

1. MCP 调的是**未公开的内部接口**（参见 `docs/research/2026-09-18-sellfox-private-api-terminology.md` 对「私有接口族 vs 公开 OpenAPI」的区分）
2. 工具**已注册但后端未实现** —— 调了会报错
3. 赛狐新增了广告写 API，**但文档镜像还没覆盖**（09-17 刷新，理论上应已覆盖，故可能性偏低）

**在 MCP 启用前无法验证**（现在连只读调用都被 `40027` 挡住）。

> **纠正一处早先的过度结论**：本次调研过程中曾据 `tools/list` 断言「推翻项目既有约束『赛狐广告无写 API』」。
> 对照公开 API 文档后，**该断言不成立** —— 约束在 OpenAPI 层面仍然有效，真正的情况是「存在未解释的差异」。
> **不要**据此修改任何既有结论或放开写权限。

---

## 四、前置条件（来自官方后台与第三方教程）

1. 赛狐后台开通「开放接口」与 **MCP 功能**（当前卡在这一步）
2. 拿到 MCP 管理页生成的 `X-MCP-Key`
3. 视情况配置 IP 白名单（第三方教程强调这是最常见的失败原因）
4. 权限继承自 API 账号 —— 建议**为 MCP 单独建账号**，便于隔离与随时禁用

**我们的现状**（仓库既有记录）：白名单已有 VPS IP `82.156.238.248`；赛狐最多 5 个 API 账号，**剩 3 个**。

---

## 五、与自有 `sellfox-api-proxy` 的关系

| | 官方托管 MCP | 我们的 `sellfox-api-proxy` |
|---|---|---|
| 位置 | 赛狐自己的服务端 | 我们 VPS `api.vilavi.cn/sellfox` |
| 鉴权 | `X-MCP-Key` | 自己的 `Bearer sk-...`（钉钉 OIDC 签发） |
| 权限模型 | 继承赛狐 API 账号 | **我们自己**的 per-key 限流与账号映射 |
| 覆盖面 | 23 个工具 | **catch-all，任意赛狐路径**（443 端点） |
| 当前 | ❌ 未启用 | ✅ 已在用 |
| 适合 | 开箱即用、广告场景 | 自控权限/审计/限流，或要覆盖 MCP 没暴露的端点 |

**不冲突，可并存。**

---

## 六、未决 / 风险

| # | 问题 | 状态 |
|---|---|---|
| 1 | **MCP 何时启用** | 等赛狐客服答复 |
| 2 | **11 个写工具到底是真是假** | 启用后用一个写工具在**测试店铺**上验，或先问客服「MCP 是否包含广告写操作」 |
| 3 | IP 白名单对官方托管 MCP 是否生效 | 启用后实测 |
| 4 | `X-MCP-Key` 单头在 ChatGPT 里够不够用 | ChatGPT「自定义标头」只能填一个头 —— 赛狐正好只要一个 ✅（比 FAC 简单） |
| 5 | 限流 1 req/s | 启用后实测 |

### 若将来启用，写权限怎么处置（建议）

按项目既有安全偏好（范围先确认、绝不擅自扩大）：

1. **默认只读**：给 MCP 建权限收窄到只读的独立 API 账号 —— **把限制放在服务端**，比在 prompt 里叮嘱可靠
2. 若确认要写：先在**一个测试店铺**上跑，人工确认
3. 客户端侧再设一层确认（Claude Desktop 可把写工具归入需确认组）

---

## 参考 URL

**实测**（2026-09-20，可复现）

- `https://api-mcp.sellfox.com/mcp` —— `initialize` / `tools/list` / `tools/call`（只读工具）三组探测

**官方**

- 赛狐后台「业务设置 → 全局 → **MCP管理**」（给出 `X-MCP-Key` 与状态）
- 赛狐帮助中心 · 业务设置：<https://www.sellfox.com/help/features/business-settings>
- 赛狐博客 ·「狐友会」AI 本地部署与 Skill 实战：<https://www.sellfox.com/blog/article/events-huyouhui-ai-local-deployment-skill-amazon-shijiazhuang-qingdao>

**第三方（非官方，需甄别）**

- CSDN 接入教程：<https://tianqi.csdn.net/6aacf59b5c13c42b539d194c.html>
  - ⚠️ 给的是 `X-Sellfox-Client-Id`/`Secret` **两个头**，与官方后台给的单头 `X-MCP-Key` **不一致**
  - ⚠️ 称「工具为查询类、不涉及数据修改」，与线上 `tools/list` 的 11 个写工具**不符**
- 社区自建项目 `shuolol/sellfox-mcp`（Node 22+，本地 3100 端口，API Key `sk-xxx`，MIT）：<https://github.com/shuolol/sellfox-mcp>
  - 与官方托管端点是**两回事**，勿混

**仓库内相关**

- `SELLFOX_API/docs/api-reference/` —— 443 篇端点文档（09-17 刷新）+ `llms.txt` / `llms_parsed.json`
- `sellfox-api-proxy/` —— 自有 VPS 代理（catch-all 443 端点）
- `sellfox_shipping/mcp_tools.py` —— 现有 FastMCP 骨架（仅发货域，7 工具）
- `docs/research/2026-09-18-sellfox-private-api-terminology.md` —— 私有接口族 vs 公开 OpenAPI
- `.agents/skills/sellfox-api/SKILL.md` —— 自有代理的调用方式与约束
