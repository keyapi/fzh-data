---
okf: v0.1
type: Lesson
title: sellfox_settlement 踩坑清单
description: 2026-09 试点实测踩坑：斜杠日期、分页、别名 explode、两口径不对等、迟交两种工具
tags: [sellfox, amazon, settlement, lessons, dingtalk, gsheet]
timestamp: 2026-09-09
resource: sellfox_settlement/reconcile_amazon.py
---

# sellfox_settlement 踩坑清单

## API / 解析

1. **`groupEndStr` 是斜杠日期**（如 `2026/06/16 06:16:48`）。按 `-` 解析会得到 0 条；先 `replace('/','-')`。
2. **结算汇总必须带 `timeType`**（如 `settlementEndTime`）；`pageNo`/`pageSize` 是**字符串**；`pageSize≤200`，超限报错。
3. **明细默认 CNY**（赛狐当日汇率）；要原币传 `currency`（按币种分别拉）。汇总侧 `currency` 才是站点币。
4. **`reportTypeList` 一次只能传一个**（传多个 →「报告类型参数错误」）。
5. **插件 API 只能列已抓文件**，不能触发生成新 Date Range；需运营紫鸟+赛狐插件先抓当月。`fileUrls` 是 ZIP（1h 有效），内含 CSV。
6. **财务手工 Custom CSV 常有 preamble**，真表头约在第 9 行；插件下的 MonthlyTransaction 通常无 preamble、32 列。

## 口径 / 比对

7. **结算 V2 = payout，Custom = activity/posted（含 deferred）**，总额天然不同，禁止对总额。做费用用列式，做回款率/打款用结算。
8. **钉钉文件 Amazon 与新平台混排**；未滤 `选择平台==亚马逊` 会把新平台销售额算进 Amazon。
9. **税净≈0**（MarketplaceFacilitator 代收代缴）；off-account 广告不进结算 → TACoS 低估。
10. **`approval_filter`**：`(审批状态∈[完成,审批中]) & 审批结果≠拒绝`。

## 渠道账号 / gsheet

11. **`渠道账号别名` 会 explode+去重作匹配键**；别名必须是完整账户标识，**不能**含裸地区（`CA`）或品牌 token（`LELEFIDO`）。
12. 赛狐店名中间段是品牌/随意填写，匹配用**收款主体→账号族 + 站点**，忽略品牌后缀。
13. gspread 6.x `insert_cols` 易踩坑；列移动用 Sheets API **`moveDimension`**。
14. 交叉表计数：「自动匹配 61 + 新增 2 行」与「赛狐店铺列非空约 73 行」是同一落地的不同切面，不要当成两套结果。

## 迟交审计

15. **两种工具口径不同、都正确**：逐月定稿 `_合并汇率&账号_`（`_run_账期提交异常分析.py`，仓库外）vs 单文件全量最新审批（`audit_late_submission.py`）。数字不可直接横向对等。
16. 日期解析要兼容 `2026-06-13` 与 `2026/6/13`（单数字月份）。
17. 去重键：`审批编号 + 账期日期 + 渠道账号 + 应收金额`。

## 工程 / 发现

18. Skill 必须放 **`.agents/skills/`**（git 追踪）；用户级 `~/.claude/skills/` clone 后不可用。
19. 新建子项目必须 OKF：`docs/index.md` + `log.md` + frontmatter `type`；调研文缺 frontmatter 则根 `update_index.py` 扫不到。
20. Amazon Settlement Flat File / XML 官方弃用日约 **2026-11-11**；赛狐 V2 同源，关注迁移。
