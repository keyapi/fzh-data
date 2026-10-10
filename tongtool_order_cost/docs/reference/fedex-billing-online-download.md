---
okf: v0.1
type: Reference
title: FedEx 官方账单下载指引（FedEx Billing Online）
description: 从 FedEx Billing Online 下载「账单明细（Invoice Detail）」给财务补尾程的操作卡片；含登录入口、两条下载路径、格式/限额、按跟踪号查票、以及「自动化不可行」的现状
tags: [fedex, billing, invoice, tail-cost, reference, guide]
---

# FedEx 官方账单下载指引

> 用途：公司自有的官方 FedEx 账号出的包裹，尾程（运费）**不会**自动进通途/EN；要向 FedEx 官网
> 下载账单明细，再按跟踪号把真实运费补进月度订单表。本卡片给运营（WXP）/财务/黄总照做。

## 1. 账号信息

| 项 | 值 |
|---|---|
| 发货账号（Account Number） | **879197228**（别名 `CentradeFedex01`） |
| 登录 User ID | `lihui@vilavidress.com`（FedEx.com 账号，非邮箱登录；密码见管理员/`.env`） |
| 归属开发者组织 | Centrade (org `10548976`)，管理员 PAULA MA |

> ⚠️ 这不是货代（蜴国际/VITE）账号——**货代出的 FedEx 单要走货代账单**，不走这里。本卡只解决**公司自有账号**出的 FedEx 单。

## 2. 登录入口

- 直达：**https://www.fedex.com/fedexbillingonline** → 自动跳到 `fedex.com/secure-login` → 输 User ID + 密码。
- 或：fedex.com 首页 → **Account（登录）** → 登入后 → 主菜单 **View & Pay bill**（看账单/付款）。

## 3. 下载账单明细（两条路径，任选）

**路径 A：View & Pay bill → Search/Download（推荐，直接出 Excel/CSV）**
1. 登录后进 **View & Pay bill**。
2. 切到 **Search/Download** 标签 → **New Search or Download**。
3. 检索条件任选：**Invoice Number / Air Waybill(跟踪号) / 付款参考号**；或按 **日期范围 + 账号 + 状态=All** 批量。
4. 点 **Download data / Create Download File** → 起文件名 → 选格式 **Excel / CSV / XML** → 确定。
5. 到 **Download Center**，状态 `Completed` 后点下载。文件保留 **14 天**。

**路径 B：Reporting → Create Report**
1. 登录 → **Reporting** → **Create Report**。
2. Filter Set 选 **Invoice** → 选账号 `879197228` + 日期范围 + Status=All → 勾 **All Columns**。
3. **Prepare Download** → 起名 → 选 **CSV** → **Download** → Download Center 里 `Completed` 后下载。

## 4. 关键限制（会踩的坑）

- **单文件 ≤ 30 MB**：超了状态显示 `Exceeds Limit` → 用日期范围/筛选缩小后重下。
- **某些账单只有 PDF**：含 **SmartPost** 的账单常常**不给 CSV**（点了报 `No Data`）→ 只能下 PDF 人工看。
- Download Center 里文件**只留 14 天**，要就尽快下载/归档。
- 下载 **不要直接打开**，先存本地再打开（浏览器打开大文件易卡）。

## 5. 拿到明细后怎么用（补尾程）

1. 打开月度「待追尾程清单 给WXP」工作簿（`scripts/make_missing_tail_lists.py` 产出，见 `monthly-tail-cost-pipeline.md`），
   看 **`疑似官方 FedEx（待确认）`** 那几票（"账单来源"列 / 明细 sheet 备注）。
2. 在 FedEx 账单明细里按 **跟踪号（Tracking / Air Waybill No.）** 找到对应票 → 取**实际运费**。
   - 缺跟踪号的票：按 **Account + 日期 + 目的地/收件人** 在 FBO 反查。
3. 按跟踪号/包裹号把真实运费回填月度订单表（键值合并，勿按位置粘）。金额口径与通途/货代账单统一后再上 Google Sheet。

> **哪些不从这里走**：`OSTK/Wayfair`（平台付尾程，**不用导入尾程**）；`美国尾程7条`（独立供应商「7条」结算）；
> `蜴国际 FedEx` / `GLS 波兰`（各走货代/GLS 账单）。本卡**只服务公司自有官方 FedEx 账号**出的单。

## 6. 自动化现状（重要：目前不行）

- **没有官方「账单/发票 API」**。FedEx 开发者门户只提供 Rate / Ship / Track / Pickup 等，**无 Invoice/Billing 下载 API**（见 `docs/research/2026-10-10-fedex-invoice-api-and-official-parcels.md`，含出处）。账单数据只能**人工在 FBO 网页下载**。
- **脚本自动登录被 FedEx 反爬拦死**（2026-10-10 实测）：全新 Playwright 浏览器（含 stealth、暖会话、重试 3 次）提交登录一律落到
  `#/error/credentials`「We are having trouble establishing a connection [200]」；同一浏览器**连 FedEx Track 查询页**也被拦到 `system-error`。
  → 结论：**FedEx 官网对自动化冷会话是系统性拦截**，不是密码错（无「密码错」提示、亦无锁定）。
- 可行替代：**人工**用常用浏览器登录下载（本卡第 3 节）；或用**已长期登录的固定浏览器 profile**再试。
  （本项目曾有 2026-09 用 Playwright 成功登录组织门户的记录，现已不复现。）

## 关联

- 月度链路与缺尾清单口径：`monthly-tail-cost-pipeline.md`
- 缺尾清单脚本：`scripts/make_missing_tail_lists.py`
- 调研（无 API + 自动化拦截 + 官方 FedEx 缺尾量化）：`docs/research/2026-10-10-fedex-invoice-api-and-official-parcels.md`
- FedEx 账号拓扑与 Track：`docs/research/2026-09-04-fedex-track-account-investigation.md`（根仓 `docs/research/`）

## 参考出处

- FedEx Billing Online（下载中心/格式/限额）：https://www.fedex.com/vg/account/fbo/
- Reveel：How to Download Data from FedEx Billing Online：https://help.reveelgroup.com/knowledge/how-to-download-data-from-fedex-billing-online-user
- techship：How to get FedEx invoices（View&Pay → Search/Download）：https://support.techship.io/support/solutions/articles/257045
- Contax：View and Download FedEx Invoice Files：https://contax.zendesk.com/hc/en-us/articles/23086437755543
- Stack Overflow（无账单 API 的历史结论）：https://stackoverflow.com/questions/23585067/
- FedEx Developer Portal API Catalog：https://developer.fedex.com/api/en-us/catalog.html
