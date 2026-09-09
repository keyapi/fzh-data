---
title: 赛狐自动拉取 Amazon 账期（结算中心V2 + 紫鸟插件列式报表）与两报表口径取舍
date: 2026-09-09
category: tooling-decisions
module: sellfox_settlement
problem_type: tooling_decision
component: tooling
severity: medium
applies_when:
  - 需要为 Amazon/多平台 账期费用做自动取回、科目解析、与钉钉运营提交值对账
  - 需要在 赛狐「结算中心V2」与 Amazon「自定义交易报表」之间做数据源取舍或交叉核对
  - 需要把赛狐店铺名 mapped 到「渠道账号」，更新共享表
tags: ["sellfox", "amazon", "settlement", "settlement-v2", "custom-transaction", "account-period", "dingtalk", "reconciliation", "currency", "crosswalk", "subject-mapping"]
related_components: [tooling]
---

# 赛狐自动拉取 Amazon 账期（结算中心V2 + 紫鸟插件列式报表）与两报表口径取舍

## Context

财务每月只靠运营在钉钉手动提交「销售收款确认单」（Amazon 金额来自后台截图 + 附件 txt），并依赖「渠道账号」表映射账号。问题：
- 运营须 3 号前按时提交、金额靠人填易错；审批有 完成/审批中/撤销/拒绝 不确定性（代码只假设 `审批状态∈[完成,审批中] & 审批结果≠拒绝`）。
- Amazon 结算 txt 欧洲/美国 小数点和分隔符不同、SKU 空格会错列、同事下错格式；2 年前的解析只能可靠提取 **Tax**。
- 其它多平台无固定格式、无 API。
而**赛狐 OpenAPI 已把 Amazon 结算结构化存好**，若核对偏差可接受，Amazon 理论上可不再依赖运营提交。

本次产出一个可跑原型（`sellfox_settlement/reconcile_amazon.py`）+ 两份文档 + 交叉表；本文档是**知识沉淀 + 交接**，记录 背景/调研/结论/风险/后续，供后续（含更强模型继续做 V2 报表解析比对）直接接手。

## Guidance

### 数据源与口径（核心结论）

| 报表 | 口径 | 赛狐 OpenAPI 是否可得 | 用途 |
|---|---|---|---|
| **结算中心V2 明细** `POST /api/financial/v2/settlementSummary/detailPage.json` | **payout（打款）** | ✅ 原生结构化，`transactionType/amountType/amountDescription/amount/sku/postedDateTimeStr/currency` | 费用/回款率自动化 |
| **结算中心V2 汇总** `…/settlementSummary/groupPage.json` | payout | ✅ `groupStartStr/groupEndStr/accountIncome/accountExpenditure/accountNetIncome/accountRefund/beginningBalance/endingBalance/transferAmount/accountTail/arrivalStatus/currency` | 对账截图「净收入」页 |
| **列式 Custom Transaction**（紫鸟插件已抓）| **activity/posted（含 deferred）**、原币、列式 | ⚠️ **非原生**；但 `POST /api/report/center/task/getPlugPageList.json`（`reportTypeList=3`=Transaction、`=4`=Summary）返回 `fileUrls`(ZIP→csv)，**已实测拿通** | 税务报税 / 明细核对 / 科目列直给 |

- `结算中心V2 明细` **默认 `currency`=CNY**（赛狐按当日汇率折算）；**传 `currency` 参数可返回原币**（实测 `currency=USD` → USD 金额）。要原币需**按币种分别拉**（一结算一种币，跨月多币种循环）。
- `groupEndStr` 格式为**斜杠** `2026/06/16 06:16:48`；解析日期要先 `replace('/','-')`。`pageSize` 上限 **200**（>200 报 `分页数量不能超过200`）；`reportTypeList` **一次传一个**（传多个报「报告类型参数错误」）。
- **官方 SP-API**：结算报告 = `GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE_V2`（payout，**不能由 API 主动请求/定时**，只能取 ~90 天/14 天历史）＝赛狐 V2 明细同源。**列式 Custom/Date Range 报告官方 API 无对应 reportType**（MWS `GET_DATE_RANGE_FINANCIAL_TRANSACTION_DATA` 也被拒），**只能 Seller Central 浏览器 UI**（紫鸟+赛狐插件）→ 这就是「紫鸟插件」必要性的来源。

### 科目映射（两套，方向一致）

**列式 CustomTransaction（最干净，列即科目）：**

| 钉钉科目 | CustomTransaction 列/规则 |
|---|---|
| 销售额 | `product sales`（Refund 行取负）+ `promotional rebates` |
| 税 | `product sales tax + shipping credits tax + giftwrap credits tax + Tax On Regulatory Fee + marketplace withheld tax` |
| 佣金 | `selling fees` |
| FBA/仓库费 | `fba fees` |
| 广告费 | `description=='Cost of Advertising'` 行 |
| 退款 | `type in (Refund, Refund_Retrocharge)` |
| 其他费用 | `other transaction fees + other` |
| 净额 | `total` |

**结算中心V2 amount-description（行式）：** `Principal↔销售额`、`Commission/RefundCommission↔佣金`、`Tax/MarketplaceFacilitatorTax-Principal/…-Shipping/VAT-*↔税`、`amountType=='Cost of Advertising'↔广告`、`FBAPerUnitFulfillmentFee/Storage Fee/…↔FBA`、`Subscription Fee↔平台月租`、`Refund↔退款`。

**已验证的量/口径差（Novelledo-US 2026-06）：**
- **税净≈0**（MarketplaceFacilitator，Amazon 代收代缴；`product sales tax`(收集) ≈ `marketplace withheld tax`(代扣) → 净为 0）。报税时要理解这点，别把「收到的税」当利润。
- **两表总额不等**：A=Custom total USD −119.89 vs B=结算明细 CNY −7867.45；差距来自 ①口径(activity vs payout) ②币种(USD vs CNY) ③结算明细侧「其他/未识别」大(大量 amountDescription 未映射)。→ **做费用/科目用列式；做回款率/打款用结算；不要混同一个口径对等**。

### storeName↔渠道账号 交叉表（自动）

- 赛狐店名 = `收款主体-账号别-站点`(账号别是随便填的品牌，忽略)。用 **收款主体(实体)→账号族 code** + **站点** 命中共享表「和运营部共享/渠道账号（20260521起在此维护）」（读自 `D:\Work\赛狐\Cursor\secrets\gsheets-service-account.json` SA——父仓库 gitignored，gspread）。
- 已确认：北京熙锦(XJ)=`AMZBJXJ`、Daneey-LELEFIDO-CA=`AMZDANEEYCA`、VERCART=`AMZVer`、CA=加拿大、TR=土耳其、IE=爱尔兰、**北京固祥-* 未启用→排除**。
- 写入 gsheet：**`赛狐店铺` 列已用 Sheets API `moveDimension` 移到 `渠道账号别名` 右侧**；新增 2 行 `AMZDANEEYCA`(事业三部/荆春雨)、`AMZBJRYECLTDCA`(事业二部/刘小菁)；`VERCART-{region}` 填入对应 `AMZVer{region}`。
- **别名坑**（colab cell 1.2/1.2.1）：`渠道账号别名` 会被 **explode 成独立账号标识**并**去重**后作匹配键——所以别名必须是**完整账户标识**；**不能**含裸地区(`CA`)/品牌(`LELEFIDO`)token。此前误填 `DANEEYCA,LELEFIDO,CA` 即错。

### 工具/脚本

`sellfox_settlement/reconcile_amazon.py`（stdlib + 仓库内 `SELLFOX_API/client.py` 的 `SellfoxClient`，代理/直连、限流、重试）：
- `shops` 列店；`fetch`（拉汇总+明细，`--currency` 取原币，`--month` 按 `groupEndStr` 归属）；`candidates`（打印未识别科目）；`reconcile`（赛狐科目 vs 钉钉定稿逐账号比对）；`fetch-custom`（拉紫鸟插件列式报表 type=3/4 → ZIP→csv）。
- 比对：取回数据在 `data/saihu_amazon_202606/`（生成数据，未入库）；`sellfox_settlement/out/amazon_june_compare.xlsx`、`sellfox_settlement/out/storeName_to_account_candidates.csv`。

## Why This Matters

- 不解决科目/口径，财务就得一直靠运营肉眼 + 手动对账，慢且错；两报表口径不区分会把不同期间的钱混算。
- 把「赛狐店名→渠道账号」映射落进共享表，后续自动取回的每笔回款才能归到正确账号/运营，回款率考核才有意义。
- 记录「紫鸟插件确实能抓、赛狐 API 能取回文件」这一事实，推翻「赛狐拿不到列式表」的旧结论，让自动化的路能走通。

## When to Apply

- 每月账期费用 自动取回/回款率计算、税报资料（Custom Summary/Transaction）、`渠道账号` 表维护、`渠道账号`↔店名 归一化。
- 任何用到 Amazon 结算金额的代码，先确认「用哪个口径、什么币种、是否含税/广告 on-account」。

## Examples

```bash
# 1) 建映射
uv run python sellfox_settlement/reconcile_amazon.py shops
# 2) 拉某账期月结算（加 --currency 取原币）
uv run python sellfox_settlement/reconcile_amazon.py fetch --start 2026-06-01 --end 2026-07-10 --month 202606 --out data/saihu_amazon_202606 --currency USD
# 3) 拉紫鸟插件已抓的列式报表(月度)
uv run python sellfox_settlement/reconcile_amazon.py fetch-custom --start 2026-04-01 --end 2026-06-30 --month 2026-06 --report-type 3 --out data/saihu_custom_202606
# 4) 与钉钉定稿比对
uv run python sellfox_settlement/reconcile_amazon.py reconcile --settlement data/saihu_amazon_202606 --dingtalk "D:/Work/王忠于/成本核算/…_合并汇率&账号_….xlsx" --month 202606 --out out/amazon_compare_202606.xlsx
```

## Handoff / 下一步（留给后续继续做「V2 报表解析+比对」）

背景/调研/结果全录见 `docs/research/saihu-amazon-settlement-autofetch-2026-09-09.md`（§10 试点实测、§11 科目/币种/自定义表、§12 赛狐可否拿 + storeName 落地、§13 实测+两表对比+gsheet）。可直接接手点：

1. **V2 明细 → 钉钉列（含人民币列）**：V2 明细已是 CNY 或 `currency` 原币；把 `amountType/amountDescription`→钉钉科目映射做成**表驱动**（放 gsheet `附加费&Tax` 或本地 constants，勿硬编码），优先用列式 CustomTransaction 的列直给做核对。
2. **逐账号比对**：核心依赖已具备（`sellfox_settlement/out/storeName_to_account_candidates.csv` + gsheet `赛狐店铺` 列），可把两表 join 到 `渠道账号` 做逐账号差异（赛狐 vs 运营提交）。
3. **币种/汇率**：取原币 + 财务固定月汇率（colab 用 `和财务部共享-汇率` 表），避免赛狐当日变动汇率。
4. **时点**：Amazon 打款在周期结束 3-5 天后、赛狐同步再滞后——需测「4 号前能否取全上月」。
5. **广告**：on-account 广告在结算；off-account 不进结算 → 结算口径 TACoS 低估，需另取 Amazon Ads API / SKU Economics。
6. **多平台**：Temu/TikTok/Walmart/eBay/AliExpress/MercadoLibre/SHEIN/Shopify 赛狐有账单；**Wayfair、Home24/Mano/Allegro/Cdiscount/EMAGRO/HOUZZ/Worten/ePrice 无 → 短期仍人工**。

## Related

- 调研全录：`docs/research/saihu-amazon-settlement-autofetch-2026-09-09.md`
- 脚本/交叉表：`sellfox_settlement/`（`reconcile_amazon.py`、`out/*.csv|xlsx`、`data/saihu_amazon_202606/`）
- 官方来源：SP-API [Report Type Values — Settlement](https://developer-docs.amazon.com/sp-api/docs/report-type-values-settlement)、[Report Type Values](https://developer-docs.amazon.com/sp-api/docs/report-type-values)、[Reports API](https://developer-docs.amazon.com/sp-api/docs/reports-api-v2021-06-30)、[弃用公告](https://developer-docs.amazon.com/sp-api/lang-zh_CN/changelog/deprecation-reminders-december-2025)、[Seller Central Date Range 报表](https://sellercentral.amazon.ie/help/hub/reference/external/G200989190)、[Seller 论坛-无 SP-API 替代](https://sellercentral.amazon.com/seller-forums/discussions/t/0e7773720b46d9bf166068ee6d85e1e8)、[积加插件(紫鸟/Chrome)](https://help.jijiaerp.com/docs/t90yg8Sf)、[Amazon Ads API](https://advertising.amazon.com/API/docs)
