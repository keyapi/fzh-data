---
okf: v0.1
type: Log
title: Camping World 模块变更日志
description: 时序变更记录
tags: [campingworld, cw, changelog]
---

# 变更日志

## 2026-11-20

- **新建模块**：`camping_world/`，承接 Tracy 2026-11-19 转发的 CW 入驻包。
- **附件**：`fetch_attachments.py` 通过 IMAP 下载 17 个附件到
  `D:\Work\美国\Tracy Miller\Camping World\2026-11-19 入驻包\`（11,950,200 字节）。
- **文档**：
  - `reference/cw-onboarding-checklist.md`：商务条款、文件矩阵、EDI 时限、运输标签、保险、罚款表
  - `reference/cw-reply-draft.md`：英文回信草稿 + 中文备注
  - `reference/cw-entity-dossier.md`：Centrade Inc / Daneey LLC / ICenTrade 主体对照（不含敏感值）
  - `reference/cw-assortment-pricing.md`：CW/Amazon/Wayfair/PB 价格锚点、11 行报价、8-12 SKU 建议、试价设计
  - `reference/cw-order-ops.md`：EDI 时窗、FedEx 选路与标签三方案、逐箱检查、YTQ 先例
  - `reference/cw-forms-and-docs.md`：COI/W-9/ACH 要求与责任人
- **脚本**：`build_vendor_forms.py` 生成两份预填草稿（仓库外）：
  `Vendor Information Form_草稿.xlsx`、`2026 Item Set UP_草稿.xlsx` + `缺项清单.md`（23 条）。
- **关键结论**：
  - CW 走 SPS EDI，855 需 1 个工作日内确认、846 每 72 小时、ASN 先于 810。
  - 尾程 FedEx，3rd Party Bill To 到 CW 账号，不支持 UPS。
  - 保险 Category 1 $1,000,000，additional insured 写 CWGS/Camping World。
  - 签约主体 Centrade Inc vs Daneey LLC 未定；SPS 能否出 FedEx 标签未确认。
