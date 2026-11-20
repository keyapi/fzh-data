---
okf: v0.1
type: README
title: Camping World 入驻与订单履约（规划中）
tags: [campingworld, cw, dropship, sps, edi, fedex, onboarding]
timestamp: 2026-11-20
---

# Camping World（CW）入驻

> 2026-11-19 Tracy 转发 CW 品类经理 Kara 的招商邮件与 17 个附件，启动**线上 dropship** 入驻。
> 当前阶段：资料评估、回信、填表草稿、选品定价、订单 SOP。**尚未收到 CW 订单，订单模块代码未开始。**

## 现状

| 项 | 状态 |
|---|---|
| 邮件与附件 | 已下载到 `D:\Work\美国\Tracy Miller\Camping World\2026-11-19 入驻包\` |
| 商务条款 | Net 30；3% co-op + 1% defective（% off invoice）；Freight Collect / FOB Destination |
| EDI | 必须走 SPS Commerce（CW 指定）；855/846/856/810/850/860 |
| 尾程 | FedEx；3rd Party Bill To CW 账号；**不支持 UPS** |
| 签约主体 | **待定**：Centrade Inc（NJ）vs Daneey LLC（USTX 发货） |
| 保险 | Category 1 产品责任险 $1,000,000；additional insured 写 CWGS/Camping World |
| 选品 | 初步锁定 Personal Wedge / Gap Filler 两类，8-12 SKU；大号 Headboard 暂缓 |

## 文档

- [入驻评估清单](docs/reference/cw-onboarding-checklist.md)
- [回复 Tracy 邮件草稿](docs/reference/cw-reply-draft.md)
- [主体资料对照](docs/reference/cw-entity-dossier.md)
- [选品与定价](docs/reference/cw-assortment-pricing.md)
- [订单操作 SOP](docs/reference/cw-order-ops.md)
- [COI / W-9 / ACH 资料清单](docs/reference/cw-forms-and-docs.md)

## 脚本

```bash
# 下载 Tracy 邮件的 17 个附件到仓库外目录
uv run python camping_world/fetch_attachments.py

# 生成 Vendor Information Form / Item Set Up 预填草稿（仓库外）
uv run python camping_world/build_vendor_forms.py
```

## 重要边界

- 填好的表格、W-9、银行、保险只落 `D:\Work\美国\Tracy Miller\Camping World\`，**不进仓库**。
- 回信必须人工审阅后发送，脚本不直接发邮件。
