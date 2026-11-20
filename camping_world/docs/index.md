---
okf: v0.1
type: Index
title: Camping World 入驻模块 — 文档索引
description: 渐进式加载入口
tags: [campingworld, cw, onboarding, index]
---
# Camping World 入驻模块 — 文档索引

> Agent 接手先读 [`../AGENT_HANDOFF.md`](../AGENT_HANDOFF.md)；需要细节按下面索引深入。

## 快速导航

| 你需要… | 读这个 |
|---|---|
| 快速了解模块与当前状态 | [`../AGENT_HANDOFF.md`](../AGENT_HANDOFF.md) |
| 怎么跑脚本 | [`../README.md`](../README.md) |
| 每份要交什么、谁负责、罚款项 | [reference/cw-onboarding-checklist.md](reference/cw-onboarding-checklist.md) |
| 回 Tracy 的邮件 | [reference/cw-reply-draft.md](reference/cw-reply-draft.md) |
| 签约主体怎么选 | [reference/cw-entity-dossier.md](reference/cw-entity-dossier.md) |
| 选品、报价、毛利 | [reference/cw-assortment-pricing.md](reference/cw-assortment-pricing.md) |
| 订单怎么处理（EDI/标签） | [reference/cw-order-ops.md](reference/cw-order-ops.md) |
| W-9 / ACH / COI 要什么 | [reference/cw-forms-and-docs.md](reference/cw-forms-and-docs.md) |
| 美国商超入驻的经验与坑 | [reference/cw-pitfalls-and-lessons.md](reference/cw-pitfalls-and-lessons.md) |
| 还要向 CW 确认什么 | [reference/cw-open-questions.md](reference/cw-open-questions.md) |

## 目录结构

```
camping_world/
├── README.md                 人读入口
├── AGENT_HANDOFF.md          Agent 入口
├── fetch_attachments.py      IMAP 下载 Tracy 邮件附件
├── build_vendor_forms.py     生成 Vendor Info Form / Item Set Up 草稿
└── docs/
    ├── index.md              本文件
    ├── log.md                变更日志
    └── reference/            入驻要求、主体、定价、SOP、表单
```

## 当前状态

- 已下载 17 个附件；已生成两份填表草稿与缺项清单（仓库外）。
- **未开始**：订单模块代码（等 SPS 规格与首批真实订单）。
- **阻塞**：签约主体未定；SPS 能否出 FedEx 标签未确认。
