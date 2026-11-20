---
okf: v0.1
type: Reference
title: Camping World 签约主体资料对照
tags: [campingworld, entity, centrade, daneey, w9, ach, coi]
timestamp: 2026-11-20
---

# 主体资料对照（不含敏感值）

> 目的：在 CW 的 Vendor Name / Ship From / W-9 / ACH / COI 上做一次清醒的选择。
> 本文**只记录"有/无 + 来源路径"**；EIN、银行账号、税号一律不抄进仓库。

## 1. 三个出现在历史资料里的名字

| 名字 | 出现位置 | 角色 |
|---|---|---|
| **Centrade Inc** | PB 的 WSI Vendor Data Form（2023-01）；`D:\Work\美国\Tracy Miller\PB WS 协议\Paula回复\Domestic Vendor Data Form_May2022_1_filled.xlsx` | PB 合同主体；地址 NJ Madison；EIN、CRN、BOA 账户均有档 |
| **Daneey LLC** | `pb_orders/AGENT_HANDOFF.md`（PB 的 SPS 供应商）；标签 `FZH-DANEEY`；`D:\Work\美国\美中USTX\` | 实际发货方（USTX 美中仓） |
| **ICenTrade (C113191)** | SPS 发票邮件抬头 | SPS 账单抬头，**不能证明交易路由或合同主体** |

## 2. 资料齐备情况

| 资料 | Centrade Inc | Daneey LLC |
|---|---|---|
| 法定名称/地址 | ✅ 有档 | ⚠️ 有名称与仓库，缺注册地址文件 |
| EIN / 税表 | ✅ W-9 与 Vendor Data Form 有 | ❌ 未见 |
| 银行 / ACH | ✅ BOA 路由与账号有档 | ❌ 未见 |
| 保险 COI | ⚠️ 未见现行保单 | ❌ 未见 |
| PB 合同关系 | ✅ 已签 | 作为 SPS 供货方出现 |
| 实际发货 | ❌ 现不发货 | ✅ USTX 发货 |

> 敏感值位置（只给路径，供人工取用）：
> - `D:\Work\美国\Tracy Miller\PB WS 协议\Form W-9 (Rev. October 2018).pdf`
> - `D:\Work\美国\Tracy Miller\PB WS 协议\Paula回复\Domestic Vendor Data Form_May2022_1_filled.xlsx`
> - `D:\Work\美国\Tracy Miller\SPS\CENTRADE INC - Williams Sonoma - Fulfillment Agreement -signed.pdf`

## 3. 三种方案与代价

### A. Centrade Inc 签约 + Daneey 仓发货（推荐先走这条）
- 优点：W-9、ACH、EIN 都是现成的；与 PB 主体一致。
- 风险：CW 可能要求 Ship From 与 Vendor Name 一致，或要求把 Daneey 仓库登记为额外发货点；
  保险的 named insured/additional insured 要覆盖 USTX 履约。
- 需要 CW 书面确认：允许第三方仓库履约，且该仓在保险范围内。

### B. Daneey LLC 签约
- 优点：合同与实际发货一致，CW 合规最干净。
- 风险：要重新准备 W-9（EIN）、银行 ACH、COI、注册地址文件；如果 Daneey 没有独立税号/账户，
  这条路走不通。

### C. 双主体（Centrade 收款 + Daneey 发货）
- 只在 CW 明确要求"收款方与发货方可分离"时考虑；否则会增加对账复杂度。

## 4. 待确认清单

1. Daneey LLC 是否有独立 EIN、美国银行账户、注册地址文件？
2. 现有 COI 的 named insured 是谁？是否已覆盖 USTX 仓？
3. CW 是否接受 Vendor Name 与 Ship From 不同主体？由谁书面确认（Kara / vendor compliance）？
4. Tracy 侧是否知道 CW 对主体一致性的偏好？

**结论：在 1-3 有答案前，不在 Vendor Information Form 上锁死公司名。**
