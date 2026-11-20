---
okf: v0.1
type: Handoff
title: Camping World 入驻 — 子项目交接
tags: [campingworld, cw, dropship, sps, edi, fedex, handoff]
timestamp: 2026-11-20
---

# Camping World 入驻交接

> 先读 [文档索引](docs/index.md) 与 [入驻评估清单](docs/reference/cw-onboarding-checklist.md)。

## 1. 业务背景

- **渠道**：Camping World（CWI / Camping World Holdings），RV 与户外零售，
  线上 dropship 由供应商直发消费者。
- **中间人**：Tracy Miller（tracy@inventivesleep.com，品牌 Inventive Sleep / Skyroom）。
- **合同主体**：`Camping World, LLC`（Kentucky），地址 650 Three Springs Road,
  Bowling Green, KY 42104。
- **品类经理**：Kara Schwichtenberg（Housewares / Picnic & BBQ / Bath & Laundry /
  Textiles & Interior Décor / Grills）。
- **商务**：Net 30；3% co-op + 1% defective（% off invoice）；Freight Collect /
  FOB Destination（实际 3rd Party Bill To CW 的 FedEx 账号）。

## 2. 文件位置（均在仓库外）

| 角色 | 路径 |
|---|---|
| 原始附件 | `D:\Work\美国\Tracy Miller\Camping World\2026-11-19 入驻包\` |
| 填表草稿 | `D:\Work\美国\Tracy Miller\Camping World\填表草稿\` |
| PB 历史资料 | `D:\Work\美国\Tracy Miller\PB WS 协议\`、`SPS\`、`产品报价\` |
| 美中仓订单要求 | `D:\Work\美国\美中USTX\美中 每日订单处理要求 20260224.docx` |

## 3. 运行

```bash
# 下载附件（IMAP 凭据从父仓库 .env 读）
uv run python camping_world/fetch_attachments.py
uv run python camping_world/fetch_attachments.py --list-only

# 生成填表草稿（只写有把握的字段，其余进缺项清单）
uv run python camping_world/build_vendor_forms.py
```

## 4. 当前状态

| 项 | 状态 |
|---|---|
| 附件 | ✅ 17 个已下载 |
| 入驻评估清单 | ✅ |
| 回信草稿 | ✅ 待人工确认后发送 |
| 主体对照 | ✅ 方案待用户拍板 |
| 选品定价 | ✅ 初步；待 CW 零售价带确认 |
| 填表草稿 | ✅ 已生成（仓库外），23 条缺项 |
| 订单模块 | ⬜ 未开始；等 SPS 规格与首批订单 |

## 5. 硬约束（不要写错）

1. **855 一个工作日内**；846 每 72 小时；856 早于 810、早于到货。→ 不能沿用 PB 每周 2-3 次。
2. **FedEx，不支持 UPS**；住宅 Home Delivery，商业 Ground。
3. **3rd Party Bill To CW 账号**；禁用 Collect / Payor Recipient；reference 必须带 CW PO#。
4. 保险 **Category 1 = $1,000,000**；additional insured 写 CWGS Group / Camping World LLC。
5. UPC 必须是 12-13 位；下单后改 UPC/属性罚 $50/SKU。
6. **W-9、EIN、银行、COI 不进仓库。**

## 6. 待确认（阻塞上线）

- 签约主体：Centrade Inc（资料齐）vs Daneey LLC（实际发货）。
- SPS 能否为 CW 出 FedEx 标签；若不能，走 FedEx Ship Manager（YTQ 先例）。
- CW 可接受零售价带与促销资源。
- 两个住宅 FedEx 账号 `#278463419` / `#908562305` 的用途区分。

## 7. 经验教训

- 不要从"PB 能这样"直接推"CW 也能这样"：EDI 时限、承运商、标签来源都不同。
- 不要把邻品价格当同款结论：CW 23×24×7 楔形与我们的长条三角不是同一规格。
- 新旧报价锚会失效：2023 年的 Wowmax Amazon 价不能直接用于 2026 年的 CW。
