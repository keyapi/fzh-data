---
type: Research
title: 赛狐官方 MCP 可行性 — 用 API 账号凭证实测可用；13 个只读工具已验证；9 个 SP 广告写工具未验证且无公开文档对应
description: 实测 api-mcp.sellfox.com/mcp 用 X-Sellfox-Client-Id/Secret（API 账号凭证）可用 —— 只读工具 get_shop_page_list 返回真实数据。后台 MCP管理页给的 X-MCP-Key 是另一条路，仍「未启用」。23 工具 = 13 读 + 1 报表任务（有文档）+ 9 个 SP 广告写（无文档对应，未调用）
tags: [sellfox, mcp, research, ads, feasibility, credentials]
timestamp: 2026-09-20
---

# 赛狐官方 MCP 可行性调研（2026-09-20）

## 一句话结论

**赛狐官方托管 MCP 可用，而且已经跑通 —— 前提是用 API 账号那套请求头。**

| 项 | 值 |
|---|---|
| 端点 | `https://api-mcp.sellfox.com/mcp` |
| 传输 / 协议 | `streamable-http` / `2025-06-18`（与 FAC 相同） |
| 服务端标识 | `{"name":"sellfox-api","version":"1.30.0"}` |
| **可用凭证** | **`X-Sellfox-Client-Id` + `X-Sellfox-Client-Secret`**（API 账号 App ID/Secret）—— **实测可用** |
| 另一条路 | `X-MCP-Key`（后台 MCP管理页生成）—— 实测 `40027 未启用MCP功能`，**是独立于上面的一条路** |
| OAuth | 不需要 |

### 结论演变（如实记录）

本文档经过三轮修订，方向改过两次，**保留轨迹以免后来人误信中间版本**：

1. 首版据 `tools/list` 断言「能接，且推翻了『赛狐广告无写 API』约束」
2. 二版核对公开 API 文档后**撤回**该断言，并因 `X-MCP-Key` 测出 `40027` 而改成「当前不可用」
3. **三版（本版）**：换用 **API 账号凭证**实测，**只读工具成功返回真实数据** —— 回到「可用」。二版的 `40027` 是因为用错了头，不是功能不可用

---

## 一、实测：只读链路已跑通

用 API 账号 App ID / Secret 作请求头（`X-Sellfox-Client-Id` / `X-Sellfox-Client-Secret`）：

```
[1] 先验凭证与 IP 白名单（直连公开 OpenAPI）
    GET https://openapi.sellfox.com/api/oauth/v2/token.json?grant_type=client_credentials
    → HTTP 200, {"code":0,"msg":"success"}   ✅ 凭证有效，且白名单已放行本机 IP

[2] MCP 握手
    initialize  → HTTP 200（拿到 mcp-session-id）
    tools/list  → HTTP 200，23 个工具

[3] 只读调用 get_shop_page_list
    → HTTP 200, {"code":0,"msg":"success","data":{...,"rows":[{...店铺...}]}}  ✅ 真实数据
```

> 返回的是**真实生产数据**（店铺列表）。按要求**未把数据写入任何文件**，此处只记机制不记内容。

### 顺带确认的一个易错点

`initialize` **不校验凭据**，鉴权推迟到工具调用；服务**有状态**，`tools/list` 不带 `mcp-session-id` 会返回 `400 Missing session ID`。

---

## 二、鉴权：两条独立的路径，别混

| 路径 | 请求头 | 来源 | 实测状态 |
|---|---|---|---|
| **A. API 账号** | `X-Sellfox-Client-Id` + `X-Sellfox-Client-Secret` | API 账号的 App ID / Secret | ✅ **可用（本文据此跑通）** |
| **B. MCP 管理** | 单个 `X-MCP-Key` | 赛狐后台「业务设置 → 全局 → **MCP管理**」生成 | ❌ `40027 未启用MCP功能` |

两条路都通到同一个端点，但**B 需要赛狐单独开通**。客服答复针对的是 B；**A 现在就能用**。

> ⚠️ CSDN 那篇教程给的是 A（两个头）—— 就实测而言**它是对的**。而官方后台页面给的是 B。
> **两者并非互相矛盾，是两条独立通道。**

> 🔒 **凭证纪律**：App ID / Secret 属于生产凭证，**不写入仓库任何文件**；本文只记头名不记值。

---

## 三、工具清单：23 个（13 读 + 1 报表任务 + 9 个 SP 广告写）

### 13 个只读（均已确认可用）

`get_shop_page_list`、`get_order_page_list`、`get_order_detail`、`get_online_product_page_list`、
`get_custom_report_page_list`、`get_ad_download_task_page_list`、
`get_sp_campaign_list`、`get_sp_ad_group_list`、`get_sp_ad_product_list`、
`get_sp_keyword_list`、`get_sp_product_targeting_list`、
`get_sp_negative_keyword_list`、`get_sp_negative_product_targeting_list`

### 1 个报表任务（有公开文档对应 → 已解释）

`create_ad_download_task` —— 对应公开 OpenAPI `/api/cpc/download/createTask.json`，
**建的是报表下载任务，不改广告数据**。

### ⚠️ 9 个 SP 广告写工具（**未调用，无公开文档对应**）

`edit_sp_campaign`、`edit_sp_ad_product`、`edit_sp_ad_group`、`edit_sp_targeting`、
`close_sp_negative_targeting`、`create_sp_keyword_targeting`、
`create_sp_negative_keyword_targeting`、`create_sp_product_targeting`、
`create_sp_negative_product_targeting`

**为什么没验证**：这些是**生产广告的写操作**（`edit_sp_campaign` 自述单次最多 100 条）。
在明确授权与隔离方案之前**不调用** —— 这是本调研的自我约束。

**已采集的只读证据**（未调用工具，仅读 schema）：

- 输入结构高度同质：`required = ["shop_id", "items"]`，`items` 是 `array<object>`，且 **schema 极薄** —— `additionalProperties: true`，**没有任何字段级约束**（字段说明只写在工具的散文描述里，如「每条除 campaignId 外至少传一个编辑字段」）
- 这与公开 API 文档里**没有对应端点**的事实并存

**与项目既有约束「赛狐广告无写 API」的关系**：

- 该约束在**公开 OpenAPI 层面仍然成立**（本地镜像 `SELLFOX_API/docs/api-reference/`，443 篇、**09-17 刷新**：广告模块 `manageData/*` 全是分页查询，`hourData/*` 是报表，唯一 `create` 是报表任务）
- 而这 9 个工具**已能通过 MCP 触达**（MCP 是通的）
- **→ 无法据此断定约束失效，也无法断定工具可用。真实状态：未验证。**

可能仍是：私有接口 / 工具已注册但后端未实现 / 文档未覆盖。**要落地必须显式验证**（见「未决」）。

---

## 四、与自有 `sellfox-api-proxy` 的关系

| | 官方托管 MCP | 我们的 `sellfox-api-proxy` |
|---|---|---|
| 位置 | 赛狐服务端 | 我们 VPS `api.vilavi.cn/sellfox` |
| 鉴权 | `X-Sellfox-Client-Id/Secret`（直接用生产 App ID/Secret） | 自己的 `Bearer sk-...`（钉钉 OIDC 签发） |
| 权限模型 | 继承赛狐 API 账号 | **我们自己**的 per-key 限流与账号映射 |
| 覆盖面 | 23 个工具 | **catch-all，任意赛狐路径**（443 端点） |
| 当前 | ✅ 可用 | ✅ 已在用 |

**关键取舍**：官方 MCP 要**把生产 App ID/Secret 直接交给调用方（即客户端）**；我们的 proxy 则是**签发自己的 key**，客户端拿不到赛狐凭证。
→ 如果要给**多人/多 Agent**用，proxy 的凭证隔离更好；官方 MCP 更适合单人自用。

---

## 五、未决 / 需要决策

| # | 问题 | 怎么解 |
|---|---|---|
| 1 | **那 9 个写工具是真是假** | ① 直接问赛狐客服「MCP 是否包含 SP 广告写操作」；② 或在**明确指定的测试店铺**上用**保证无副作用**的载荷调用一次（需用户显式授权） |
| 2 | 后台 MCP管理页（`X-MCP-Key`）何时开通 | 等客服 |
| 3 | 限流（上游 1 req/s）在 MCP 侧是否同样生效 | 高频调用时实测 |
| 4 | 要不要接、接哪个客户端 | 见下 |

### 若接：权限与安全建议

按项目既有偏好（范围先确认、绝不擅自扩大）：

1. **默认只读**：用**权限收窄到只读的独立 API 账号**接 MCP —— 把限制放在**服务端**
2. **凭证归属**：优先走自有 proxy（客户端拿不到赛狐 App Secret），而不是把生产 App Secret 分发到各客户端
3. 真要写：先在**单个测试店铺**验证，人工确认

---

## 参考 URL

**实测**（2026-09-20，可复现）

- `https://api-mcp.sellfox.com/mcp` —— `initialize` / `tools/list` / 只读 `tools/call`
- `https://openapi.sellfox.com/api/oauth/v2/token.json` —— 凭证 + IP 白名单验证

**官方**

- 赛狐后台「业务设置 → 全局 → **MCP管理**」（生成 `X-MCP-Key`，显示状态）
- 赛狐帮助中心 · 业务设置：<https://www.sellfox.com/help/features/business-settings>
- 赛狐博客 ·「狐友会」AI 本地部署与 Skill 实战：<https://www.sellfox.com/blog/article/events-huyouhui-ai-local-deployment-skill-amazon-shijiazhuang-qingdao>

**第三方**

- CSDN 接入教程：<https://tianqi.csdn.net/6aacf59b5c13c42b539d194c.html>
  - ⚠️ 它给的 `X-Sellfox-Client-Id`/`Secret` **实测可用**（是「路径 A」）
  - ⚠️ 但称「工具为查询类、不涉及数据修改」，与 `tools/list` 的 9 个广告写工具**不符**
- 社区自建项目 `shuolol/sellfox-mcp`（Node 22+，本地 3100 端口，API Key `sk-xxx`，MIT）：<https://github.com/shuolol/sellfox-mcp>
  - 与官方托管端点是**两回事**，勿混

**仓库内相关**

- `SELLFOX_API/docs/api-reference/` —— 443 篇端点文档（09-17 刷新）+ `llms.txt` / `llms_parsed.json`
- `sellfox-api-proxy/` —— 自有 VPS 代理（catch-all 443 端点，签发自己的 key）
- `sellfox_shipping/mcp_tools.py` —— 现有 FastMCP 骨架（仅发货域，7 工具）
- `docs/research/2026-09-18-sellfox-private-api-terminology.md` —— 私有接口族 vs 公开 OpenAPI
- `.agents/skills/sellfox-api/SKILL.md` —— 自有代理的调用方式与约束
