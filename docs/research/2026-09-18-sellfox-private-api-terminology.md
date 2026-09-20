---
okf: v0.1
type: Reference
title: 赛狐「私有接口」与公开 OpenAPI 的区分——术语、判据与用词约定
date: 2026-09-18
category: research
module: web_automation
tags: [sellfox, api, terminology, shadow-api, private-api, openapi]
applies_when:
  - "要在文档/对话里描述赛狐的接口，需要区分『真 OpenAPI』和『页面内部接口』"
  - "看到『浏览器 API』这种说法，不确定指什么"
  - "判断某个赛狐能力是否有稳定合同可用"
---

# 赛狐「私有接口」与公开 OpenAPI 的区分

## Context

同一个赛狐站点上并存两套完全不同的调用面：

| | **公开 OpenAPI** | **私有接口** |
|---|---|---|
| 入口 | `openapi.sellfox.com`（代理 `api.vilavi.cn/sellfox`） | `www.sellfox.com/api/...`，需站点 cookie |
| 文档 | Apifox 有，443 端点，本地镜像 `SELLFOX_API/docs/api-reference/` | **无文档**，只能抓包/挖打包产物 |
| 鉴权 | OAuth2 + HMAC 签名（或代理 Bearer Key） | 浏览器登录态 |
| 权限 | App 级授权，**字段可逐个受限** | 跟登录用户权限走 |
| 稳定性 | 有版本承诺 | **无承诺，随时可能改** |

实际踩过的混淆：说「API 没有写入口」时，指的是公开 OpenAPI；但同一功能在私有接口上**有**写入口。
两者都说「API」，结论却相反。Agent 之间传递这个结论时极易走样。

## 调研结论：业界怎么称呼

**没有唯一权威说法。最接近的行业术语是 Shadow API（影子 API），但对赛狐这批接口语义有偏差。**

| 说法 | 出处 | 评价 |
|---|---|---|
| **Shadow API / 影子 API** | 安全行业标准术语；OWASP **API9:2023 Improper Inventory Management** | 最接近，但定义强调「**归属方**不知道、失去管控」——赛狐这些接口是赛狐自己前端在用、自己维护的，只是在公开 OpenAPI 之外。**不严格成立** |
| Zombie API | 同上 | ✗ 指废弃但仍可达的端点 |
| Rogue API | 同上 | ✗ 指未经授权部署 |
| undocumented internal API / 内部接口 / 私有接口 | 通用说法 | ✓ 中性、准确 |
| reverse-engineering a website's internal API | `hamelsmu/website-to-api` 等工具 | ✓ 描述**做法**，非接口称呼 |
| website-to-API / browser-derived automation | Tyk | ✓ 描述产物/模式 |

Tyk 那篇对**本场景**（Agent 抓站点自己的 XHR 端点）描述最贴切：

> Your web application already contains a programmable surface whether you documented it or not.
> The UI is not the opposite of an API. The UI is an API with worse ergonomics and fewer adult
> supervision mechanisms.

### 用词约定（本仓库）

- **正文用**：「**私有接口**」或「**非公开内部接口**」——`web_automation/docs/reference/sellfox-pitfalls.md`
  已在用「私有接口」，保持一致。
- **首次出现时补一句**：「（undocumented internal API，业界亦称 shadow API 影子 API）」——兼顾检索。
- **不要**用「浏览器 API」——歧义大，容易被读成 Playwright/浏览器自动化本身，
  而不是「借浏览器登录态调用的 HTTP 端点」。

## 判据：怎么快速分辨

1. **路径前缀**：`/api/gw/sellfox/...` 或直接 `/api/<业务>/...` 且能在浏览器 Network 里看到 → 私有接口。
   公开 OpenAPI 的路径同样形如 `/api/xxx.json`，**光看路径分不出来**。
2. **调用方式**：公开 OpenAPI 需要 `access_token`/`client_id`/`nonce`/`timestamp`/`sign` 五个 query 参数；
   私有接口只要 cookie。
3. **文档**：能在 `SELLFOX_API/docs/api-reference/llms.txt` 里 grep 到的 → 公开 OpenAPI。
4. **最可靠**：直接查 Apifox 镜像索引。查不到而页面在用 → 私有接口。

## 实证：赛狐成本补录单的两面性

同一功能在两侧的存在性完全不同：

| 操作 | 公开 OpenAPI | 私有接口 |
|---|---|---|
| 查询列表 `pageList` | ✅（但 `searchField=sku`/`status`/`warehouseIds`/`createTime` 报 `40021 暂无权限`） | ✅ 无限制 |
| 创建 `create` | ❌ 不存在 | ✅ |
| 审核 `audit` | ❌ 不存在 | ✅ |

详见 [`../solutions/integration-issues/sellfox-cost-adjust-api.md`](../solutions/integration-issues/sellfox-cost-adjust-api.md)。

## 私有接口的定位：价值在「修」，不在「批量」

| 场景 | Excel 上传 | 私有接口 |
|---|---|---|
| 批量创建（成本补录单、海外仓备货单创建） | ✅ 更优（模板先校验、一次数千条） | 无优势 |
| **修改已存在单据，且没有 Excel 入口** | ❌ 做不到 | ✅ **唯一自动化路径** |
| 单张操作、需即时校验/回读 | 笨 | ✅ |

典型反例：**海外仓备货单改「单个头程费用」没有上传入口**，只能页面点击编辑 ——
这正是私有接口唯一有增量价值的场景。

## 风险与纪律

- **无稳定性承诺**：私有接口变更不通知，不能写进长期自动化而不留兜底。
- **必须另行批准并验证后才用**（`sellfox-pitfalls.md` 已记此约定）。
- 抓 payload 用**「截获后挡掉」**：Playwright `page.route` 截获请求体后 `fulfill` 假响应，
  请求不到服务端 → **零写入拿到契约**。这是唯一安全的取证姿势。
- 写操作走 `web_automation/sellfox-profile`，**不要用跨 worktree 共享的 MCP Playwright 浏览器**。

## Sources

- [What Is A Shadow API? Security Risks, Detection, & Prevention — Wiz](https://www.wiz.io/es-es/academy/api-security/shadow-api)
- [If you don't give agents an API, they'll make one out of your UI — Tyk](https://tyk.io/blog/if-you-dont-give-agents-an-api-theyll-make-one-out-of-your-ui/)
- [The Risks of Shadow APIs — Nordic APIs](https://nordicapis.com/the-risks-of-shadow-apis-how-unmanaged-endpoints-bypass-your-ci-cd-checks/)
- [What Is a Shadow API? Risks and Real-World Examples — Invicti](https://www.invicti.com/blog/web-security/what-is-shadow-api-risks-and-real-world-examples)
- [How to Discover Shadow and Undocumented APIs — safeguard.sh](https://safeguard.sh/resources/blog/api-discovery-and-shadow-api-risk)
- [website-to-api — 逆向站点内部 API 的四步模式](https://github.com/hamelsmu/website-to-api)

## Related

- [`../solutions/integration-issues/sellfox-cost-adjust-api.md`](../solutions/integration-issues/sellfox-cost-adjust-api.md) — 成本补录单私有接口完整契约
- [`../solutions/integration-issues/sellfox-adjust-order-write-chain.md`](../solutions/integration-issues/sellfox-adjust-order-write-chain.md) — 库存调整单写链路实测
- [`../solutions/conventions/sellfox-apifox-api-docs-mirror-refresh.md`](../solutions/conventions/sellfox-apifox-api-docs-mirror-refresh.md) — 公开 OpenAPI 文档镜像
- [`../../web_automation/docs/reference/sellfox-pitfalls.md`](../../web_automation/docs/reference/sellfox-pitfalls.md) — 页面侧踩坑
