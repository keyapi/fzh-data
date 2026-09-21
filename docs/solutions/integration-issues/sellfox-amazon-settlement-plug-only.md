---
okf: v0.1
type: Reference
title: Amazon 账期报表只能走赛狐「插件获取报告」——API 不可触发，且文件地址 1 小时过期
category: integration-issues
module: SELLFOX_API
problem_type: integration_issue
component: finance_reconciliation
severity: high
date: 2026-09-21
applies_when:
  - "要从赛狐拉 Amazon 账期/结算报表（Transaction、Summary PDF）"
  - "判断某个赛狐报表是服务端生成还是插件抓取，或某端点能否发起抓取"
  - "下载赛狐返回的文件地址时遇到 403/过期"
tags: [sellfox, amazon, settlement, report-center, plugin, finance]
related_components: [SELLFOX_API]
---

# Amazon 账期报表只能走赛狐「插件获取报告」

## Context

财务报税需要各账号的 Amazon 账期报表（原先靠人工读 PDF 计算）。
要判断：赛狐 API 能不能拉？能拉全 90 个账号吗？

赛狐侧有三条 Amazon 报表路径，**只有一条含账期**：

| 路径 | 端点 | 生成方式 | 含账期？ |
|---|---|---|---|
| 亚马逊原报告 | `/api/report/center/{add,pageList}.json` | 赛狐服务端（走 Amazon SP-API） | ✗ 类型枚举里无账期（有 VAT、库存、仓储费…） |
| 自定义报表 | `/api/custom/report/{reportList,pageList}.json` | 赛狐自建报表引擎 | ✗ 是赛狐分析表，非 Amazon 结算文件 |
| **插件获取报告** | `/api/report/center/task/getPlugPageList.json` | **浏览器插件在账号登录态下抓回** | **✓ 唯一** |

## Guidance

1. **账期只有「插件获取报告」这一条路，而它是纯读接口** —— 没有任何参数能发起抓取。
   两条旁证：`创建报告任务`（`task/createTask.json`）的 `reportType` **只支持 `PRODUCT_SALE_REPORT`**；
   亚马逊原报告的类型枚举里没有账期。⇒ **抓取动作只能在赛狐/紫鸟的 UI 侧发生**，API 侧无解。

2. **"拉不到" 的真正含义是「插件侧没抓过」，不是接口坏了。** 先看覆盖度再怀疑代码。

3. **`fileUrls` 是 1 小时有效的临时签名 URL**（腾讯 COS 预签名，路径含 `q-sign-time`）。
   ⇒ **绝对不能存链接**。正确做法是「调 API 拿新 URL → 立刻下载落盘」，归档要存**文件本身**。

4. **reportType 枚举**：3=Transaction(csv/zip)、4=**Summary(pdf)**、5=Deferred transaction、6=FBAInboundConvenience。
   实测线上只存在 3 和 4。`reportDayType` 对 reportType=6 是区间（`yyyy-MM-dd到yyyy-MM-dd`），其余为 `yyyy-MM`
   —— 归档目录务必做非法字符替换，否则含 `:` 会炸 Windows 路径。

5. **判扩展名用魔数，不要信 URL**：`PK\x03\x04`→zip、`%PDF`→pdf。实测同一 reportType 两种形态都有。

## Why This Matters

1. 覆盖度是**人工按店群执行**的结果，不是系统周期性任务 —— 实测 90 店只有 39 店有数据，
   没抓过的 9 个店群（51 店）全空。这直接决定「要不要让运营去插件侧补抓」这个结论。
2. **不要拿赛狐自算口径去替代 Amazon 官方报表。** 曾评估
   `/api/financial/v2/monthProfit/shopSummary.json`（利润报表-店铺汇总）——
   它是服务端生成、不依赖插件，带 `productSales`、支持 `settlement|shipment` 口径，
   且**覆盖包括「插件从未抓过」店群在内的全部店铺**（`Centrade-WOWMAX-US` 一家占全站销售额 56%，
   而它正无插件报表）。**但它是赛狐自己的计算口径、不是 Amazon 官方结算文件** ——
   报税场景已被明确否决（口径可信度）。**留此记录以免将来重复提议。**
3. 若不理解 1 小时过期，容易把"存下来的链接"当数据源，事后全部 403。

## When to Apply

- 用户提到 Amazon 账期/结算报表、Amazon Summary PDF、Transaction 报表、报税要报表。
- 需要判断「赛狐某报表能否用 API 主动生成」。
- 下载赛狐返回的 fileUrls 失败时。

## Examples

```bash
# 覆盖度快查（只打印矩阵，不下文件）
uv run python SELLFOX_API/probe_amazon_reports.py --start 2026-06-01 --end 2026-09-21

# 看缺口不下载
uv run python SELLFOX_API/fetch_amazon_settlement.py --start 2026-06-01 --end 2026-09-21 --dry-run

# 下载归档（默认 <repo_root>/out/amazon_settlement，产出 _manifest.csv / _gaps.csv / _failures.csv）
uv run python SELLFOX_API/fetch_amazon_settlement.py --start 2026-06-01 --end 2026-09-21
```

2026-09-21 实测：90 店 → 有数据 39 店、完全没抓过 51 店；覆盖月份仅 `2026-06`/`2026-07`
（**8/9 月一条都没有**）。下载 79 文件 / 0 失败 / 34MB（26 PDF + 53 ZIP），
抽验 CSV 与 PDF 内容均为真报表。

## Related

- 调研全记录：[`docs/research/2026-09-21-sellfox-amazon-settlement-reports.md`](../../research/2026-09-21-sellfox-amazon-settlement-reports.md)
- 同类「赛狐某功能只能走另一条调用面」的记录：[赛狐成本补录单](sellfox-cost-adjust-api.md)、[赛狐备货单改头程](sellfox-restock-headfee-api.md)
- 对照：Walmart 的账期结算明细走的是**可直拉**的公开 OpenAPI（`financial/walmartReport/queryStatementDetail`），
  与本文「只能靠插件」形成反差 —— 见 `docs/solutions/workflow-issues/walmart-account-period-sellfox-api.md`（另一 PR）。
