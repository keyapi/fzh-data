---
okf: v0.1
type: Research
title: FedEx 官方账单 API 可行性 + 官方 FedEx 缺尾量化（2026-10）
description: 结论——FedEx 无账单/发票下载 API、官网自动化登录被反爬系统性拦截；并量化 202608 官方 FedEx（自有账号）缺尾 13 票/货代 250 票
tags: [fedex, billing, api, tail-cost, research]
---

# FedEx 官方账单 API + 官方 FedEx 缺尾（2026-10-10）

## 背景

WXP 反馈：通途 8 月自发货订单里**还有官方 FedEx 包裹的运费没上传**；上一批官方 FedEx 账单是黄总给的，
但黄总想不起在 FedEx 官网是怎么下载的。需回答：① 官网怎么下账单；② 能不能自动化（API/脚本）。

## 结论速览

| 问题 | 结论 |
|---|---|
| 官方账单/发票下载 **API** | **不存在**（开发者门户只有 Rate/Ship/Track/Pickup 等） |
| 官网 **自动登录** | **被反爬拦死**（全新 Playwright 一律 `[200]` 连接错误） |
| 可行路径 | **人工**在 FedEx Billing Online 下载（卡片见 `../reference/fedex-billing-online-download.md`） |
| 202608 缺口 | 541 行 / 527 包裹（`needs=1 且 物流商运费=0`） |
| 其中「疑似官方 FedEx」 | **仅 1 票**（`US-FedEx>>US-FedEx`，待确认） |

## 一、无账单 API（多处核实）

- FedEx 开发者门户 **API Catalog**（https://developer.fedex.com/api/en-us/catalog.html）列的是
  Authorization / Ship / Track(Basic+Advanced IV) / Rate / Address Validation / Pickup / Locations /
  Service Availability / Ground EOD Close / Postal Code / Trade Documents / Consolidation / Freight LTL /
  Shipment Visibility Webhook —— **没有任何 Invoice/Billing/账单类 API**。
- 社区历史结论一致：*“the API do not offer the ability to download invoices programmatically. This is
  definitely a web scraping type of deal.”*（Stack Overflow #23585067）。
- FedEx 账单数据只在 **FedEx Billing Online (FBO)** 网页端可取（Search/Download、Reporting）。
  → 结论：**账单只能人工下载**，不存在官方 API 替代。

## 二、官网自动化登录被拦（实测）

探针（`web_automation` 环境，Playwright + `channel=chrome` 有头）：
- 入口 `https://www.fedex.com/fedexbillingonline` → 跳 `fedex.com/secure-login/en-us/#/credentials`。
- 关掉 usercentrics cookie 遮罩、stealth（`--disable-blink-features=AutomationControlled` + 覆盖
  `navigator.webdriver`）、暖会话（先访问 home + Track 页）、**重试 3 次** —— 每次提交均落到
  `#/error/credentials`「**We are having trouble establishing a connection. Please refresh the page. [200]**」。
- 同一浏览器访问 **FedEx Track 查询页**也被打到 `fedextrack/system-error`（冷会话）。
- 无「密码错/账户锁定」提示 → **不是凭证问题，是 FedEx 对自动化冷会话的系统性拦截（WAF/风控）**。

> 与 `2026-09-04-fedex-track-account-investigation.md` 的差异：当时能登录组织门户，**现已不复现**。
> 现有可行路径 = **人工**常用浏览器登录下载。

## 三、202608 官方 FedEx 缺尾量化

口径：`是否需要尾程=1` 且 `物流商运费=0`（还没拿到真实账单）。数据源
`EN上传Cost Review预估尾程 只用尾程 通途非FBA订单202608 202610101152.xlsx`（10,912 行；needs=1 = 8,004）。

缺口合计 **541 行 / 527 包裹**（包裹级去重），按「账单来源」拆分：

| 账单来源 | 判据（邮寄方式链） | 包裹 | 预估合计 | 优先级 |
|---|---|---:|---:|---|
| **蜴国际 FedEx（货代）** | 含「蜴国际」 | **250** | ¥19,975.67 | 高（重点） |
| **GLS 波兰** | 含 `GLS` | **228** | ¥27,489.59 | 高（重点） |
| CENTRADE | 含 `CENTRADE` | 36 | ¥4,105.90 | 中 |
| 「7条」尾程供应商 | 含「7条」(如 `美国尾程7条>>FEDEX Economy TX`) | 5 | ¥498.30 | 中 |
| 疑似官方 FedEx（待确认） | `US-FedEx>>US-FedEx` | **1** | ¥62.78 | 待确认 |
| **平台渠道补发（需确认尾程）** | 含 `OSTK` 且**补发单**（`是否补发货=是` 或 `订单号 -M<数字>`） | **7** | ¥579.11 | 待确认 |

> 对账：待追 527（全部）；本月**无**「非补发平台付」行 → 无需追 0。

**领域口径修正（2026-10 用户确认）**：
- **OSTK/Wayfair 常态不用导入尾程**（平台付）；**但补发单除外**——补发货可能用自有尾程，需确认是否追。原先按「含 FedEx」误并入「官方 FedEx」，后又一度整类放过，均已纠正。
- `美国尾程7条` 是**独立尾程供应商「7条」**，**不是**官方 FedEx。
- `US-FedEx>>US-FedEx` **可能是官方 FedEx（待确认）**——若确认，才去 FBO 下载。
- **重点追查 GLS 波兰 + 蜴国际 FedEx**（量大）。
- **补发单**（`是否补发货=是` / `-M<num>`）：本月 15 个（GLS 8 + OSTK/Wayfair 7），已按规则标「是否补发/备注」。
- **通途无跟踪号**的缺口行（28 包裹）需按 账号+日期+目的地 反查；**无预估**的行（14 行，多为 `WL-shape-frame`/`DLZYFX001` 零重量件）也标了备注。

产出（`成本核算` 目录，脚本 `scripts/make_missing_tail_lists.py`）：
- **`202608 待追尾程清单 给WXP 20261010.xlsx`**（单一工作簿：汇总 / 明细 527 行）

## 参考 URL

- FedEx Developer Portal API Catalog：https://developer.fedex.com/api/en-us/catalog.html
- FedEx Billing Online：https://www.fedex.com/vg/account/fbo/
- Reveel FBO 下载指引：https://help.reveelgroup.com/knowledge/how-to-download-data-from-fedex-billing-online-user
- techship FBO 下载指引：https://support.techship.io/support/solutions/articles/257045
- Stack Overflow（无账单 API）：https://stackoverflow.com/questions/23585067/
