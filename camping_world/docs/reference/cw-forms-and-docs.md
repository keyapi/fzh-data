---
okf: v0.1
type: Reference
title: COI / W-9 / ACH 资料清单
tags: [campingworld, insurance, coi, w9, ach, compliance]
timestamp: 2026-11-20
---

# COI / W-9 / ACH 资料清单

> 全部是**外部出具 + 本地保存**，不进仓库。本文只写要求与责任人，不抄敏感值。

## 1. COI（保险凭证）

**要求（Vendor Agreement §8 + VLI Matrix）**

| 项 | 要求 |
|---|---|
| 品类 | Category 1（家纺/抱枕/家具座椅） |
| 保额 | $1,000,000 产品责任与完工责任 |
| 覆盖 | 人身伤害（含死亡）、财产损失（含使用损失）、个人/广告伤害 |
| Additional Insured | `CWGS Group, LLC, Camping World, LLC and each of their parent companies, subsidiaries, and affiliates` |
| 保险人评级 | A.M. Best **A- Class VII** 或以上 |
| 性质 | primary and non-contributory |
| 提交时点 | 签约前；新增更高品类；每年续保 |

**需要确认**：
- 现行保单的 named insured 是 Centrade Inc 还是 Daneey LLC？
- 保单是否覆盖 USTX 履约仓（Daneey LLC / Texas）？
- 若签约主体与发货方不一致，保单是否要同时列两个实体？

**责任人**：保险经纪（出证）+ 财务/管理层（提供主体与地址）。

## 2. W-9

**要求**：
- Line 1 法定名称必须与签约主体一致
- Line 2 商业名称（如与 Line 1 不同）
- Line 3a 税务分类（LLC 需填 C/S/P；单成员 LLC 需特别处理）
- TIN 与 Centrade 现有 W-9 一致（若签 Centrade）

**现状**：
- Centrade Inc 的 W-9 有档：`D:\Work\美国\Tracy Miller\PB WS 协议\Form W-9 (Rev. October 2018).pdf`
- Daneey LLC 的 W-9 **未见**；若签 Daneey，需先确认其 EIN 与税务分类。

**责任人**：财务。

## 3. ACH Authorization

**表单字段（从 `3 - ACH Payment Authorization Agreement 10.22.24.doc` 抽取）**：
- Company Name / Address / City-State-Zip / **Federal ID #**
- Contact Name / Phone / Fax / E-Mail
- Bank Name / Bank Address
- **Routing Number / Account Number**
- 授权人签字；建议附 voided check

**约束**：
- 收款人名称必须与签约主体一致（Vendor Name = ACH Beneficiary）。
- 只接受**美国银行账户**。
- 若签 Centrade，现有 BOA 账户可用；若签 Daneey，需确认其美国账户。

**责任人**：财务。

## 4. Vendor Information Form 中的相关信息

| 区块 | 需要填什么 | 数据来源 |
|---|---|---|
| Corporate Information | 公司名、地址、联系人、电话、邮箱、网站 | 主体档案 |
| Remit Payment To | 收款地址（可与公司地址不同） | 财务 |
| Purchase Order Information | 接收 PO 的地址与联系人 | 我方 |
| Ship From Information | USTX 仓库地址与联系人 | 美中仓 |
| Sales Representative | Tracy 的公司、地址、联系方式 | Tracy |
| Store to Vendor Questions | 退货地址与联系人 | 我方 |
| EDI | 联系人、电话、邮箱、是否收 dropship 费 | 我方 |
| Discounts & Allowances | 3% co-op / 1% defective / 新店 0 / 量返不适用 | Kara 已给 |
| Terms & Conditions | Net 30；Freight Collect / FOB Destination；Incoterm | Kara 已给 |

## 5. 提交顺序

1. 主体确认 → W-9 + ACH 可出。
2. COI 经纪出证（可与 1 并行，但 named insured 要等主体定）。
3. Vendor Info Form + Item Setup 交 Kara。
4. Vendor Agreement / Participation Agreement 签字。
5. SPS onboarding（EDI 认证）。

## 6. 禁止

- 不把 W-9、EIN、银行账号、COI 扫描件放进 git 仓库。
- 不在聊天/文档里贴完整账号；需要时只写"见本地路径"。
