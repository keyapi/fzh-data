---
okf: v0.1
type: Research
title: SPS 联系人 Alison 邮件往来与已发回复
description: 2025-06/07 与 SPS Account Executive Alison Kudrle 的完整邮件线程 + 2026-08-18 已发送的回复要点
tags: [sps-commerce, email, alison-kudrle, icentrade]
timestamp: 2026-08-18
---

# SPS 联系人 Alison 邮件往来与已发回复

## 背景

SPS 账号 **iCenTrade**（联系人 Key，邮箱 `us@mxdeals.com`）在 2025-06/07 与 SPS Commerce **Account Executive Alison Kudrle**（`amkudrle@spscommerce.com`，Direct Line 612-552-7028）有一轮关于"EDI / API 集成"的邮件对话，之后停滞了一年。2026-08-18 已回复邮件，询问是否仍负责 + 自己对接 API 是否额外收费。

## 完整线程（时间线，UTC）

| 时间 | 方向 | 主题 | 要点 |
|---|---|---|---|
| 2025-06-27 21:04 | Alison → Key | `SPS Contact - iCenTrade` | 确认 Key 是否仍是账号正确联系人 |
| 2025-06-30 11:04 | Key → Alison | `YES Re:SPS Contact - iCenTrade` | 确认是 |
| 2025-06-30 12:50 | Alison → Key | `Re: YES Re:SPS Contact - iCenTrade` | 问 3 件事：加 EDI 连接（零售商/Shopify/Amazon）、自动化减少 Fulfillment 门户手动录入、仓库 EDI / 3PL 转介 |
| 2025-07-01 14:15 | Key → Alison | `Re: YES SPS Contact - iCenTrade` | 目前电商软件未接 SPS；问 REST API 是否替代 EDI；能否自己实施 |
| 2025-07-01 17:47 | Alison → Key | `Re: YES SPS Contact - iCenTrade` | 解释 EDI vs REST API、SPS 两者都支持；**"若你们自己处理，可提供工具/文档/指导"**；问所用 ERP/财务系统 |

旁证（同窗口其他邮件）：`SPS Commerce no-reply` 每天发"有 N 份新文档来自 Williams Sonoma OS"通知 —— iCenTrade 通过 SPS 门户收 Williams Sonoma / Pottery Barn 的订单文档；`wsAccountsPayable@wsgc.com` 发 `WSI ACH Remittance` 对账邮件（该流程走 `pb@icentrade.com`，见 pb-reconciliation 技能）。

## 2026-08-18 已发送的回复（要点）

主题沿用 `Re: YES SPS Contact - iCenTrade`，正文要点：
1. 过了一年，确认 Alison 是否仍是 iCenTrade 账号负责人（是否转岗）。
2. **前置商务问题：我们自己对接 API（Transaction API）是否有额外费用**（API 服务费 / 生产数据访问 / 按单费），如有显著费用可能不推进。
3. 现状：SPS 门户手动处理 PB/WS 履约（下载订单、建 ASN、下载发票、手工发库存），ERP 为 ERPNext。
4. 意愿：自己用 API 做，Transaction API 自动化 850/856/810/846；已建 Dev Center M2M App、沙盒全链路实测通过。
5. 请 Alison 协助：文档（Transaction API / RSX / PB 单据 mapping）、开通生产数据访问与交易路由、SPS 侧 onboarding/测试步骤。

> 全文已由用户本人通过 `us@mxdeals.com` 发出（草稿见本会话对话记录）。

## 下一步

- 等 Alison 回复：是否仍负责 + 是否收费。
- 若她不再负责，向她要正确联系人。
- 若收费显著 → 评估是否放弃 API 路线（回到门户 + Selenium）。
- 若推进 → 按其反馈补充文档索取与生产开通流程。
