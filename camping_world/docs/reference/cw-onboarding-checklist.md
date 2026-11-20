---
okf: v0.1
type: Reference
title: Camping World 入驻评估清单
tags: [campingworld, onboarding, edi, compliance, checklist]
timestamp: 2026-11-20
---

# CW 入驻评估清单

来源：Kara Schwichtenberg 2026-11-19 邮件 + 17 个附件（已落盘到
`D:\Work\美国\Tracy Miller\Camping World\2026-11-19 入驻包\`）。

## 1. 商务条款（Kara 原文）

| 条款 | CW 标准 | dropship |
|---|---|---|
| Payment Terms | Net 60 | **Net 30（已批准）** |
| Co-op / Advertising | 3% Percent Off Invoice | 同 |
| Defective Allowance | 1% Percent Off Invoice | 同；若要退回残次品则填退货地址与 RA 方式 |
| New Store Allowance | 20% | **不适用，可忽略** |
| Freight Terms | Collect / FOB Destination | 同（但实际是 3rd Party Bill To CW 的 FedEx 账号） |

## 2. 文件矩阵

| 文件 | 谁填 | 我们能做的 | 缺口 | 责任方 |
|---|---|---|---|---|
| Vendor Information Form | 供应商 | 公司、联系人、发货仓、EDI、折扣条款 | 签约主体未定 | 我方 + 管理层 |
| ACH Authorization | 供应商 | 账户信息现成（Centrade） | 主体确认；收款人必须一致 | 财务 |
| Vendor Agreement（含保险） | 供应商签署 | 可审阅 | COI、签字 | 法务 + 保险经纪 |
| Vendor Participation Agreement | 供应商签署 | 可审阅 | 3%/1% 确认、签字 | 管理层 |
| New Store Contribution | — | — | **忽略** | — |
| 2026 Item Set Up | 供应商 | 产品描述、成本、MSRP、重量尺寸 | UPC、HTS、原产地、Prop 65、Vendor # | 我方 + Tracy/CW |
| W-9 | 供应商 | Centrade 版现成 | 若签 Daneey 则需新表 | 财务 |
| CWI 合规指南 | 阅读 | 已提取约束条款 | — | — |
| COI 样例 | 保险经纪 | 按样例出证 | 现行保单 | 保险经纪 |
| EDI Overview | 阅读 | 已读 | — | — |

## 3. EDI（CW 指定 SPS Commerce）

**必做文档**：850（PO）、855（PO 确认）、860（PO 变更）、856（ASN）、810（发票）、846（库存）。

**时限（来自 SPS 官方 CW EDI Operations Guide）**：

| 文档 | 时限 |
|---|---|
| 855 PO 确认 | **1 个工作日内** |
| 846 库存 | **至少每 72 小时** |
| 856 ASN | 发货后 **1 个工作日内**，且必须早于 810、早于到货 |
| 810 发票 | 发货后 |
| 850 PO | CW 每天 7:00 / 8:00、11:30 / 12:30、16:00 / 17:00（中部时间）发送 |

> 这意味着**不能再沿用 PB 的"每周 2-3 次"节奏**：至少要有每日检查新单与当日回 855 的动作。

**规格与资源**：
- 文件规格：`https://community.spscommerce.com/camping-world/`
- 供应商 wiki：`https://supplierwiki.supplypike.com/supplier-site/camping-world-oso`
- EDI 指南 PDF：`https://community.spscommerce.com/wp-content/uploads/2024/02/Camping-WorldEDIOperationsGuide.pdf`

## 4. 运输与标签

| 项 | 要求 |
|---|---|
| 承运商 | FedEx；住宅 Home Delivery，商业 Ground；**UPS 不支持** |
| 计费 | **3rd Party Bill To CW 的 FedEx 账号**；不可 Collect / Payor Recipient |
| dropship 住宅账号 | `#278463419` / `#908562305`（两个账号用途需向 CW 确认） |
| 标签 reference | **CW PO# 必须出现在参考字段** |
| 包裹上限 | 单箱 ≤150 lb；≤20 箱或 ≤300 lb 走 FedEx，>301 lb 走 LTL |
| 申报价值 | 单箱 >$500 必须申报 |
| 合规标签 | GS1-128/UCC-128，4×6；含 PO#、承运商、SSCC-18、SKU、颜色/尺码、供应商/收货地址、箱号、原产国、ASN# |
| 装箱单 | **branded packing slip**，dropship 每单必需；可自建，但要在 SPS onboarding 提交并获批 |

**标签链路三选一（待 SPS 确认）**：
1. SPS Fulfillment 出 FedEx 标签（最省事，与 PB 模式最接近）
2. FedEx Ship Manager 网页手动（YTQ 做 Wayfair/Overstock 的现成路径）
3. FedEx Ship API（量大后再上）

## 5. 保险（Vendor Agreement §8 + VLI Matrix）

| 项 | 要求 |
|---|---|
| 品类 | 抱枕/家纺属 **Category 1** |
| 保额 | **$1,000,000**（产品责任、人身伤害、财产损失、产品与完工责任） |
| Additional Insured | **CWGS Group, LLC、Camping World, LLC 及其母公司/子公司/关联公司** |
| 保险人评级 | A.M. Best **A- Class VII** 以上 |
| 其他 | 保单为 primary and non-contributory；不得要求 CW 的其他保单分摊 |
| 提交时点 | 签约前；新增更高品类时；每年续保时 |

## 6. Item Setup 缺项

| 字段 | 状态 |
|---|---|
| Supplier / Brand | 可填（SKYROOM by Tracy Miller） |
| Description / Long Description | 可填 |
| Unit Cost / MSRP / MAP | 成本与 MSRP 可从报价表推；MAP 待定 |
| **UPC / EAN（12-13 位）** | ❌ 缺；需确认 GS1 归属与现有编码 |
| Inner/Case Pack、MOQ | 可给建议值（1 / 待定 / 待定） |
| Weight / Dimensions | 报价表已有；需与实际包装核对 |
| HTS（至少 8 位） | ❌ 缺 |
| Country of Origin | 疑为 CN（绍兴工厂），需确认 2 位代码 |
| Prop 65 | ❌ 需按材质判断并选择警告条 |
| Warranty Terms | ❌ 待定 |
| Freight Class | ❌ 待定 |

## 7. 罚款矩阵（合规指南）

| 代码 | 违规 | 罚款 |
|---|---|---|
| PI-02 | 下单后改 UPC/颜色/属性 | $50 / SKU |
| PO-02 | 早于需求日 10 天以上到货 | $350 |
| PO-03 | 迟于最晚收货日 | $350 + 退运费 |
| PO-04 | 发了 PO 外的商品/替代品 | $400 + 运费 |
| PO-05 | 超发 | $300 + 运费 |
| RS-01 | 未预约送货 | $400 + 超额运费 |
| RS-04 | 用未授权承运商/UPS/Collect | $600 + 全额运费 |
| RS-07 | 多 PO 未合并发运 | $400 + 超额运费 |
| RS-11 | LTL 未走 Redwood | $400 + 差额 |
| RS-16 | FedEx 服务类型用错（Ground vs Home Delivery） | $200 + 差额 |
| RS-17 | 滥用 CW 账号发非 CW 货 | $400 + 超额费用 |
| CC-04 | 非标流程产生的额外费用 | $400 + 费用 |

## 8. 下一步（按顺序）

1. 用户拍板签约主体（见 `cw-entity-dossier.md`）。
2. 回信 Tracy，索取：CW Vendor #、可接受零售价、促销资源、标签链路确认。
3. 申请 SPS 增加 CW 交易伙伴（30 天内决定，认证 3 天-6 周）。
4. 保险经纪出 COI（$1M、additional insured 按原文）。
5. 价格调研定稿后填 Item Setup，交 Kara。
6. 收到 SPS 测试规格后再启动订单模块。
