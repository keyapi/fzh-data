---
title: SPS Commerce API 自动化（Pottery Barn）— Transaction API + M2M client_credentials
date: 2026-08-18
category: docs/solutions/architecture-patterns/
module: sps_api
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - 需要自动化 SPS Commerce 门户操作（下载订单/发 ASN/发票/库存）时
  - 评估用 API 替代 SPS 门户人工操作或 Selenium 脚本时
  - 接入 SPS Dev Center 认证（App 类型选择、Redirect URI）时
tags:
  - sps-commerce
  - transaction-api
  - edi
  - oauth
  - m2m
  - pottery-barn
---

# SPS Commerce API 自动化（Pottery Barn）— Transaction API + M2M client_credentials

## Context

FZH 是 Pottery Barn 的供应商，所有操作在 SPS Commerce **门户**手动完成：下载订单(850)、生成 ASN(856)、下载发票(810)、每天发库存(846，已用 Selenium 自动化)。想验证能否改用 API。本会话完成外部调研 + POC 实测，结论：**可行**，正路是 **Transaction API**（HTTPS 版 FTP/AS2）交换 EDI/RSX 文件 + **Machine-to-Machine** 认证。

## Guidance

### 1. 认证：选 M2M，别用 Web Service

SPS 用 Auth0 做 OAuth 2.0，**App 类型决定流程**：

- **Web Service Application** = 授权码流，`/authorize` 和 `/oauth/token` 两步 **Redirect URI 都必填**。
  - 实测：用 Web Service App 密钥调 client_credentials → `403 {"error":"unauthorized_client","error_description":"Grant type 'client_credentials' not allowed for the client."}`
- **Machine-to-Machine (M2M)** = client_credentials 流，**只需 App ID + App Secret，无 Redirect URI，完全无头**。官方明确推荐"公司代表自己连接 Dev Center"用 M2M。

token 端点：
```
POST https://auth.spscommerce.com/oauth/token
Content-Type: application/json
{"grant_type": "client_credentials", "client_id": "<APP_ID>", "client_secret": "<APP_SECRET>", "audience": "https://spscommerce.com"}
→ {"access_token": "...", "expires_in": 3600}
```
token **必须缓存复用**（官方限流），按 `expires_in` 刷新。

### 2. 服务面：没有"门户按钮 API"

Dev Center 公开服务只有三类：Shipping Doc API（标签/装箱单）、Trading Partner Submission API（**买家用**，不适用供应商 FZH）、**Transaction API**。订单/ASN/发票/库存本质是 EDI 单据（850/856/810/846），用 Transaction API 交换文件（多为 RSX XML，支持其他格式）。

### 3. Transaction API 端点（base `https://api.spscommerce.com`，全部实测）

| 端点 | 方法 | 用途 | 实测 |
|---|---|---|---|
| `/transactions/v5/data/{file-path}` | POST | 发送文件（ASN/发票/库存/PO确认） | 201 |
| `/transactions/v5/data/{directory}/` | GET | 列目录（找可下载文件，支持 limit/cursor/entryNamePrefix 分页） | 200 |
| `/transactions/v5/data/{file-path}` | GET | 下载文件 | 200 |
| `/transactions/v5/data/{file-path}` | DELETE | 处理完删除 | 204 |

- 头：`Authorization: Bearer <token>`；POST 时 `Content-Type: application/octet-stream`（最大 2GB）。
- **目录约定**（供应商视角）：`out/` 零售→供应商（订单在 `out/PO/`）；`in/` 供应商→零售。`testout/`/`testin/` 为沙盒测试目录（本次沙盒实例未创建，直接写 `in/` 即可）。
- 文件命名约定：`PO...`/`IN...`/`SH...`/`PR...`/`IA...` + 数字/唯一键。

### 4. 生产数据前提（沙盒 vs 生产）

沙盒立即可用，`out/PO/` 有 4 个样例订单。**生产数据必须与 SPS 签约 + 实施团队开通访问并配置交易路由**，否则根目录为空（本次实测生产根目录 `{"results":[]}`，`out/PO/` 404）。

## Why This Matters

4 个手动流程（下载订单/ASN/发票/库存）本质是文件交换脚本，可完全替代门户人工 + Selenium。认证无头（M2M）、通道是标准 HTTPS，工程上简单。**主要瓶颈在商务/开通流程**（SPS 签约 + 实施团队），不在技术，需提前规划并与 account team 沟通。

## When to Apply

- 供应商需要自动化 SPS Commerce 与零售商的 EDI 单据交换（订单入、ASN/发票/库存出）。
- 需要给 SPS Dev Center app 选类型 / 纠结 Redirect URI 时——自用选 M2M，省掉整套回调。
- 评估"门户 + Selenium"是否值得迁移到 API。

## Examples

```bash
# 拿 token（M2M，无 Redirect URI）
curl -s -X POST https://auth.spscommerce.com/oauth/token \
  -H 'Content-Type: application/json' \
  -d '{"grant_type":"client_credentials","client_id":"<APP_ID>","client_secret":"<APP_SECRET>","audience":"https://spscommerce.com"}'

# 下载沙盒样例订单
curl -s -H "Authorization: Bearer <token>" \
  https://api.spscommerce.com/transactions/v5/data/out/PO/PO112853-1-v7.7-CrossDock.xml

# 发送库存/ASN/发票（写路径）
curl -s -X POST -H "Authorization: Bearer <token>" \
  -H 'Content-Type: application/octet-stream' \
  --data-binary '<InventoryAdvice>...</InventoryAdvice>' \
  https://api.spscommerce.com/transactions/v5/data/in/IA<key>
```

- 反例：Web Service App 调 client_credentials → 403 unauthorized_client（必须换 M2M App 或配 Redirect URI 走授权码）。
- 反例：POST 到不存在的目录（如 `testin/`）→ 404 "Parent directory not found"（先确认目录存在）。

## Related

- 详细调研报告（含全部官方文档 URL）：[2026-08-18-sps-commerce-api-feasibility.md](../../research/2026-08-18-sps-commerce-api-feasibility.md)
- POC 脚本模块：[sps_api/](../../../sps_api/AGENT_HANDOFF.md)
- 既有 EDI 调研（PB = EDI 传统模式）：[sellfox-shipping-research-and-architecture.md](sellfox-shipping-research-and-architecture.md)
