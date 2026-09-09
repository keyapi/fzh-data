---
name: sellfox-amazon-settlement
description: >
  赛狐自动拉取 Amazon 账期（结算中心V2 + 紫鸟/赛狐插件列式报表）与两报表口径取舍、科目映射、
  赛狐店名↔渠道账号交叉表。当用户提到"赛狐账期"、"Amazon结算"、"settlement"、"结算中心V2"、
  "Custom Transaction"、"列式报表"、"紫鸟插件报表"、"科目映射"、"两报表对比"、"账期费用自动取回"、
  "回款率"、"赛狐店铺↔渠道账号"、"sellfox settlement"、"账期对账"时触发。
  不要用于赛狐Excel导入(category/item-cost/item-weight/stock-init/warehouse-restock/multi-attr/other-outbound)或纯广告报告(fetch_ad_reports)。
metadata:
  module: sellfox_settlement
  updated: 2026-09-09
---

# 赛狐 Amazon 账期（settlement + 列式报表）

## 用途
自动取回 Amazon 账期费用、做科目解析、与钉钉运营提交值对账；判断赛狐与亚马逊官方报表的数据源取舍。
**完整调研与结论见（仓库内，已提交）：**
- `docs/solutions/tooling-decisions/amazon-settlement-autofetch-sellfox.md`（知识沉淀+交接：口径/科目/风险/后续）
- `sellfox_settlement/docs/research/saihu-amazon-settlement-autofetch-2026-09-09.md`（§10 试点实测、§11 科目/币种/自定义表、§12 赛狐可否拿+storeName 落地、§13 实测+两表对比+gsheet）
- `sellfox_settlement/AGENT_HANDOFF.md`（子项目入口/交接）；脚本：`sellfox_settlement/reconcile_amazon.py`；交叉表：`sellfox_settlement/out/storeName_to_account_candidates.csv`
- 脚本：`sellfox_settlement/reconcile_amazon.py`；交叉表：`sellfox_settlement/out/storeName_to_account_candidates.csv`

## 关键事实（速查，别再踩）
- 赛狐「结算中心V2」：汇总 `…/settlementSummary/groupPage.json`、明细 `…/settlementSummary/detailPage.json`。
  明细**默认 CNY**（赛狐当日汇率）；**传 `currency` 可返回原币**。`groupEndStr` 用**斜杠**日期；`pageSize≤200`；`reportTypeList` **一次传一个**。
- **列式 Custom Transaction**：紫鸟/赛狐插件抓，`POST /api/report/center/task/getPlugPageList.json`（`reportTypeList=3`=Transaction,`=4`=Summary）→ `fileUrls`(ZIP→csv)，**已实测拿通**（32 列：product sales/tax/selling fees/fba fees/other/total…）。
- **官方 SP-API**：结算=`GET_V2_SETTLEMENT_REPORT_DATA_FLAT_FILE_V2`(payout，不能主动请求/定时)；**列式 Date Range 报告无 API 类型，UI-only**（需紫鸟插件）。
- **口径**：结算=payout、Custom=activity/posted(含 deferred)；两表**总额不等**；**税净≈0**(Amazon 代收代缴)；off-account 广告不进结算→TACoS 低估；**做费用用列式、做回款率用结算，别对等**。
- **科目映射**：列式列即科目（product_sales↔销售额、selling_fees↔佣金、fba↔FBA、Cost of Advertising↔广告、tax 列↔税）；结算 amount-description 同向。
- **赛狐店名↔渠道账号**：用「收款主体→账号族 code」+「站点」匹配共享表「和运营部共享/渠道账号（20260521起在此维护）」；`赛狐店铺` 列已加在「渠道账号别名」右侧；北京熙锦(XJ)=AMZBJXJ、VERCART=AMZVer、Daneey-CA=AMZDANEEYCA、如泱-CA=AMZBJRYECLTDCA、**北京固祥未启用→排除**。
- **别名坑**：`渠道账号别名` 会被 explode+去重作匹配键，必须是**完整账户标识**，**不能含裸地区/品牌 token**（colab cell 1.2/1.2.1）。

## 用法
```bash
uv run python sellfox_settlement/reconcile_amazon.py shops
uv run python sellfox_settlement/reconcile_amazon.py fetch  --start 2026-06-01 --end 2026-07-10 --month 202606 --out data/saihu_amazon_202606 --currency USD
uv run python sellfox_settlement/reconcile_amazon.py fetch-custom --start 2026-04-01 --end 2026-06-30 --month 2026-06 --report-type 3 --out data/saihu_custom_202606
uv run python sellfox_settlement/reconcile_amazon.py reconcile --settlement data/saihu_amazon_202606 --dingtalk "<钉钉定稿xlsx>" --month 202606 --out out/amazon_compare_202606.xlsx
```
凭证：`SELLFOX_PROXY_API_KEY`(或 APP_ID/SECRET) 在 `D:\Work\赛狐\Cursor\.env`；gsheet 用 `secrets/gsheets-service-account.json`(gspread, 用父仓库 `.venv`)。**勿泄露 Key。**

## 后续（更强模型继续）
V2 明细→钉钉列做成表驱动；逐账号 join `渠道账号` 对账；原币+固定月汇率；测 4 号前能否取全上月；广告 ad 另取 Ads API；多平台仅 Temu/TikTok/Walmart/eBay/AliExpress/MercadoLibre/SHEIN/Shopify 有账单，Wayfair 及小平台仍人工。
