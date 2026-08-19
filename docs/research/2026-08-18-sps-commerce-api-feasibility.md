---
okf: v0.1
type: Research
title: SPS Commerce API 自动化可行性调研（Pottery Barn）
description: 验证能否用 SPS Dev Center API 自动化 PB 的订单下载/ASN/发票/库存操作；结论可行，走 Transaction API + M2M client_credentials
tags: [sps-commerce, pottery-barn, edi, transaction-api, oauth, feasibility]
date: 2026-08-18
---

# SPS Commerce API 自动化可行性调研（Pottery Barn）

## 结论摘要

- **可行，且已端到端实测通过**。用 SPS **Transaction API**（HTTPS 版 FTP/AS2）即可自动完成订单下载、ASN 上传、发票交换、库存上报；沙盒里已实测 读/写/删 三个方向全部成功。
- **认证**：新建 **Machine-to-Machine (M2M) App** + `client_credentials` 流，**只需要 App ID + App Secret，不需要 Redirect URI**，完全无头。官方明确推荐"公司代表自己连接 Dev Center"用 M2M。
- **关键前提**：沙盒可立即用；**生产数据必须与 SPS 签约 + 由实施团队开通访问**，且需按 Pottery Barn 的 EDI profile 生成 RSX XML 文件。
- 没有"下载订单按钮"之类的门户 REST API —— 这些操作本质是 EDI 单据（850/856/810/846），走文件交换。

## 背景

FZH 是 Pottery Barn 的供应商，目前在 SPS Commerce **门户**手动操作：下载订单(850)、生成 ASN(856)、下载发票(810)、每天发库存(846，已用 Selenium 自动化，见 `SPS_Selenium_Local/`)。用户想知道能否改用 API。

用户已在 SPS Dev Center 创建 app，最初选了 **Web Service Application** 类型并问是否需要 Redirect URI。

## 调研方法

- SPS Dev Center 是 SPA，WebFetch 抓不到正文 → 用 **Playwright** 渲染读取官方文档（`developercenter.spscommerce.com` 各子页）。
- 用第三方集成商文档（[StackOne](https://docs.stackone.com/connectors/spscommerce/guides/connector-profile/oauth-2-0-authorization-code-web-service)、[Cyclr](https://community.cyclr.com/connector-guides/sps-commerce/sps-commerce-setup)）交叉验证。
- 用用户沙盒密钥实际调用 API 验证（本轮 POC）。

## 关键发现

### 1. 认证：App 类型决定流程（回答 Redirect URI 问题）

SPS 用 Auth0 做 OAuth 2.0，**不同 App 类型用不同流程**：

| App 类型 | OAuth 流程 | 需要 Redirect URI？ |
|---|---|---|
| Web Service Application | Authorization Code | **必须**（/authorize 和 /oauth/token 两步都要） |
| Machine-to-Machine (M2M) | **Client Credentials** | **不需要** |
| Native / SPA | Auth Code + PKCE | 需要 |

- **实测**：用户原 Web Service App 密钥调 client_credentials → `HTTP 403 unauthorized_client: "Grant type 'client_credentials' not allowed for the client"`。即该 App 只允许授权码流，**必须配 Redirect URI**。
- **实测**：新建 M2M App 后，用 `POST https://auth.spscommerce.com/oauth/token` + `grant_type=client_credentials` 直接拿到 token（`expires_in=3600`），成功。
- M2M 官方原文：*"Machine-to-Machine Applications are non-interactive... use the Client Credentials Grant Flow, which allows an application to request an Access Token using only its App ID and App Secret."* 且 *"The M2M application type is best suited for companies connecting directly to the SPS Dev Center on their own behalf."* —— 正是 FZH 场景。
- token 需**缓存复用**（官方限流提示），`expires_in` 决定何时刷新。

### 2. 服务：没有"门户按钮 API"

Dev Center 公开服务只有三类：
1. **Shipping Doc API** —— 生成合规 GS1-128/UCC-128 标签、装箱单
2. **Trading Partner Submission API** —— **买家**（零售商）建连接用，**不适用于供应商 FZH**
3. **Transaction API** —— **HTTPS 版 FTP/AS2**，供应商与 SPS 之间交换 EDI/RSX 文件（这是 FZH 的正路）

订单/ASN/发票/库存本质是 EDI 单据（850/856/810/846），通过 Transaction API 交换文件（多为 RSX XML，支持其他格式）。

### 3. Transaction API 端点（全部实测）

Base: `https://api.spscommerce.com`

| 端点 | 方法 | 用途 | 实测结果 |
|---|---|---|---|
| `/transactions/v5/data/{file-path}` | POST | 发送文件（ASN/发票/库存/PO确认） | 201 成功 |
| `/transactions/v5/data/{directory}/` | GET | 列目录（找可下载文件） | 200 成功 |
| `/transactions/v5/data/{file-path}` | GET | 下载文件 | 200 成功 |
| `/transactions/v5/data/{file-path}` | DELETE | 处理后删除 | 204 成功 |

- 请求头 `Authorization: Bearer <token>`，POST 时 `Content-Type: application/octet-stream`（最大 2GB）。
- **目录约定**（供应商视角）：
  - `out/` 零售商 → 供应商（**订单在这里**，子目录 `out/PO/`、`out/IN/`、`out/SH/` 等）
  - `in/` 供应商 → 零售商（发 ASN/发票/库存/PO 确认）
  - `testout/` `testin/` 为沙盒测试目录（本沙盒实例未创建这两个）
- 文件命名约定：`PO...`（订单）、`IN...`（发票）、`SH...`（发货/ASN）、`PR...`（PO 确认）、`IA...`（库存），后接数字/唯一键。
- 沙盒 `out/PO/` 有 4 个样例订单（CrossDock / MultiStore / BulkImport / DropShip）。

### 4. 与用户 4 个操作的映射

| 用户手动操作 | API 自动化方式 | 状态 |
|---|---|---|
| 下载订单 (850) | `GET out/PO/` 列目录 → `GET` 每个文件（轮询） | 实测可用 |
| 生成/发送 ASN (856) | `POST in/SH<key>` 上传 RSX 发货文件 | 实测可用 |
| 下载发票 (810) | `GET out/IN/` 列目录 → `GET` 文件（若需留档/对账） | 实测可用（同机制） |
| 发送库存 (846) | `POST in/IA<key>` 上传库存文件（替代现有 Selenium） | 实测可用 |

注：发票(810)方向上是供应商→零售商（POST `in/`）；门户"下载发票"若指下载自己生成的副本，两个方向都覆盖。

## 生产环境实测（2026-08-18，只读）

用用户提供的生产 M2M App 密钥做了**只读**测试（token + 列目录，未写任何数据）：

- **token 获取**：成功（`POST https://auth.spscommerce.com/oauth/token`，`client_credentials`，`expires_in=3600`）。
- **生产 Transaction API 根目录**：`{"results": []}` —— **为空**，没有任何目录。
- **`out/PO/`**：`404 Directory not found`。

**结论**：生产 M2M App 认证与 API 通道均可用，但生产环境**尚未绑定 FZH 的贸易伙伴数据**（无 `out/`/`in/` 路由）。与官方文档一致——需要与 SPS 签约 + 实施团队开通并配置交易路由后，数据才会出现。当前无法在生产看到 PB 订单。

## 约束 / 前置条件

1. **生产数据**：Transaction API 官方原文 —— *"production data will not be available until an agreement with SPS Commerce is in place and access to production data is granted by your implementation team."* → **必须联系 SPS account team 签约并开通**。
2. **EDI/RSX 规格**：需按 Pottery Barn 的具体 EDI profile（X12 850/856/810/846 的字段映射）生成/解析文件；SPS 会翻译 RSX ↔ 零售商要求格式。需向 SPS 索取 PB 的文档规格与样例。
3. **文件命名与路由**：官方建议与 SPS 实施团队确认文件路径/命名约定，不同单据类型走不同目录。
4. **token 限流**：必须缓存复用（本 POC 已实现 `token.json` 缓存）。
5. **沙盒限制**：沙盒只有样例数据，没有真实 PB 订单；`testin/testout` 可能不存在，直接写 `in/out` 即可。

## 参考 URL

- 官方 Dev Center 文档（SPA，需浏览器渲染）：
  - Getting Started: https://developercenter.spscommerce.com/#/docs/getting-started
  - Machine-to-Machine: https://developercenter.spscommerce.com/#/docs/new-authentication-docs/machine2machine-applications
  - Web Service Apps: https://developercenter.spscommerce.com/#/docs/new-authentication-docs/web-service-applications
  - Redirect URLs: https://developercenter.spscommerce.com/#/docs/new-authentication-docs/redirect-urls
  - Transaction API 概览: https://developercenter.spscommerce.com/#/docs/transaction-api
  - Transaction API 启动指南（供应商流程/目录约定）: https://developercenter.spscommerce.com/#/docs/transaction-api/startup-guide
  - Create Transaction: https://developercenter.spscommerce.com/#/docs/transaction-api/v5-posting
  - Filter Transactions: https://developercenter.spscommerce.com/#/docs/transaction-api/v5-filtering
  - Get Transaction: https://developercenter.spscommerce.com/#/docs/transaction-api/v5-getting
  - Trading Partner Submission API: https://developercenter.spscommerce.com/#/docs/trading-partner-submission-api
- API 标准/认证规范: https://spscommerce.github.io/sps-api-standards/standards/authentication.html
- 第三方集成商佐证: https://docs.stackone.com/connectors/spscommerce/guides/connector-profile/oauth-2-0-authorization-code-web-service 、 https://community.cyclr.com/connector-guides/sps-commerce/sps-commerce-setup
- 既有调研（PB = EDI 传统模式）: [sellfox-shipping-research-and-architecture.md](../solutions/architecture-patterns/sellfox-shipping-research-and-architecture.md)

## 建议下一步

1. **联系 SPS account team**：确认 Transaction API 对 FZH 是合适方案，签约 + 开通生产访问，并索取 PB 的文档规格（850/856/810/846 mapping）与生产目录/文件命名约定。
2. **确认 PB 的 EDI 需求**：是否要求 ASN 先行（合规罚款）、SSCC 标签（可配 Shipping Doc API）等。
3. **设计自动化流水线**：轮询 `out/PO/` → 解析 RSX 订单 → 对接 ERPNext/赛狐数据 → 生成 ASN/发票 → POST `in/` → 处理完删除。库存上报用 POST `in/IA` 替代 Selenium。
4. **迁移到生产 M2M app**（本轮已建沙盒 M2M app 验证）。
5. 若 PB 走传统 EDI（AS2/SFTP）而非 Transaction API，需与 SPS 确认哪条通道更适合 FZH 的对接形态（两者本质等价，TAPI 是 HTTPS 替代）。

## 附录：POC 脚本

- 模块：`sps_api/`（本轮新增）
  - `config.py` — 从 `.env` 读凭据/端点
  - `oauth.py` — M2M client_credentials 拿 token + 缓存复用
  - `probe.py` — Transaction API 目录探测 / 文件下载（`python probe.py out/PO/ --download`）
  - `.env` — 沙盒密钥（**gitignore，不提交**）
- 实测记录：M2M token 成功；`out/PO/` 列到 4 个样例订单；下载 `PO112853-1-v7.7-CrossDock.xml`（9.8KB RSX）；POST `in/INPOC00001` 201；DELETE 204。
