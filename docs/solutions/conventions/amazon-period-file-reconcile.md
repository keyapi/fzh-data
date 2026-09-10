---
okf: v0.1
type: Reference
title: Amazon 账期按账号对账（NAS + 钉钉 + 赛狐结算组）
date: 2026-09-10
last_updated: 2026-09-10
category: conventions
module: dingtalk_oa_approval
problem_type: convention
component: tooling
severity: high
applies_when:
  - "对 Amazon 账期判断漏交、迟交或 NAS 缺 txt"
  - "用赛狐结算组对照钉钉销售收款确认单"
  - "渠道账号表店名与账期文件名前缀对不上"
  - "离职发起人附件 API 返回 userNotExist"
tags:
  - "amazon-settlement"
  - "dingtalk-oa"
  - "nas-period-bucket"
  - "sellfox-grouppage"
  - "channel-account-alias"
  - "departed-originator"
---

# Amazon 账期按账号对账（NAS + 钉钉 + 赛狐结算组）

## Context

财务要核对某自然月 Amazon 账期是否已经交钉钉、附件是否进了对应 NAS 账期桶。容易走错的三条路：按 NAS **人名文件夹**当店负责人；用赛狐 **店名拆 brand** 去对 txt 前缀；把赛狐 `groupPage` 结算组当成 Amazon txt 原件，再把「有 NAS 或有核算行」说成「钉钉和附件都齐」。

2026-09-10 对 7 月做过一轮（赛狐结算结束日落在该月的组）。公开叙述用人名拼音首字母；NAS 文件夹真名只在 gitignore 的 `person_folders.local.json`。

## Guidance

**1. 负责人看渠道账号表，不看人名夹。**

NAS `{账期桶}/{人名}/` 是钉钉**提交人**。店负责人是 Google 表「渠道账号」的 `运营人员YYYYMM`。助手、离职交接、换人会使同一 `AMZ*` 账号出现在多个人名夹。只扫现任负责人文件夹会把前任交的第一期当成漏交。

**2. 赛狐店名必须经别名对到账期文件名。**

`渠道账号别名` 和 `赛狐店铺` 列是匹配键。店名 `北京如森-Rucener-*` = 账号 `AMZRosoon*`（别名如 `RSUS,RosoonUS`）；`云途汇德-Novelledo-US` = `AMZYTHDUS`（别名 `Novelledo-US,AMZNovelledoUS`）。按店名拆出 `RUCENER` / `YUNTU` 会对不上 `ROSOON` / `YTHD`，假报「表上没账号」。代码别名在 `dingtalk/dingtalk_oa_approval/sellfox_amz_settlements.py` 的 `BRAND_ALIASES`。

**3. 赛狐查的是结算组 API，不是后台 txt。**

`/api/financial/v2/settlementSummary/groupPage.json`（`timeType=settlementEndTime`，`isSite=true`）列出结算结束日在窗口内的组。不是 Amazon 结算报告原件，也不是点开每个店铺后台。没有结算组的渠道账号行不会出现。打款金额可以为 0。

**4. 「有文件或有表行」不是「这一期钉钉且附件都齐」。**

按账号对照脚本（`july_amz_by_account.py`）先用日期近的文件，对不上就把该 brand+site 的全部 7 月 txt 挂上。结论列「有附件或核算行」是 **或**。严口径要用文件日期 / 表单账期日期去对 `groupEnd`（人工命名可能差几天，例如 `AMZJohnaUS-7.13.txt` 对结算结束 7/10）。

**5. Amazon 账期只认 `.txt`。** 结算周期 csv、桶里已有同茎 csv 的 zip，不算。

**6. 木已成舟。** 已经在上一提交窗核算过的单（例如发起日 ≤ 该月 3 日且已进上月桶），不要再改归本月。误传到本月桶的副本删掉，上月原件保留。

**7. 离职发起人：实例可读，标准下载常 `userNotExist`。** 先看 NAS 全员扫描和核算 Excel。钉钉上可能已经传了 txt，只是 API 拿不下来（7 月如森 SE 第二期：单上有 `AMZRosoonSE-2026-07-18.txt`，标准 Grant 失败）。专享下载见模块 research；未开通时下一步是浏览器走管理后台。操作手册：`dingtalk/dingtalk_oa_approval/docs/research/browser-admin-download.md`。必须先 `web_automation/scripts/dispatch.py <task> --check`；当时没有钉钉 capability 就停，不要绕过。

**8. 21 位审批编号当文本。** Excel 会收成科学计数或错号。

**9. 本机路径和真名不进 git。** 缓存/核算目录用 `DINGTALK_OA_DATA`、`DINGTALK_OA_WORK`；NAS 根用 `NAS_FINANCE_PERIOD_ROOT`。不要把含人名的磁盘路径或 FileStation 路径写进脚本。

## Why This Matters

按人名夹或按店名硬拆，会把已交的店报成漏交（7 月曾把如森/云途 11 笔有打款的结算组写成「表上没账号」），也会漏掉真缺口。把「或」说成「且」，会让财务以为只剩 1 笔，实际还有「钉钉有、NAS 无」和打款为 0 未交的组。

## When to Apply

- 月度 Amazon 账期漏交 / NAS 缺件审计
- 赛狐结算组次数和钉钉 txt 对不上
- 渠道账号表有行、脚本却报无账号
- 计划用浏览器补离职附件或管理后台 Excel

## Examples

**假漏交（匹配洞）。** 赛狐 `北京如森-Rucener-US` 结算结束 7/6、7/20 有打款；NAS 与核算都是 `AMZRosoonUS`，提交人 LYX。对上别名后不是漏交。

**真漏交。** `AMZRosoonIT` / 赛狐如森-IT / 结算结束 2026-07-08 有打款；7 月核算无行、NAS 5–8 月桶无该站 txt。缺钉钉提交。202607 表负责人 LYX（已离职），202608 是 SYX，补交找现任。

**钉钉有、NAS 无。** 审批 `202607231544000528489`，账期日期 2026-07-18，账户 `AMZRosoonSE`，附件名 `AMZRosoonSE-2026-07-18.txt`；标准 API `userNotExist`；7 月桶只有 7/4 那份。不是忘传。

**木已成舟。** `AMZDANEEYES-2026-07-01.txt` 在 6 月桶，发起 ≤ 7/3，已算进 6 月；VERCART-SE 7/1 txt 同样在 6 月桶。本轮 7 月漏交清单不再列。

**人工文件名。** 君缘 Johnear-US 赛狐结束日 7/10；核算审批 `202608061717000057610`（LTZ）三行 7/11、7/22、7/29；NAS 7 月桶已有 `AMZJohnaUS-7.13.txt` 等。计入 7 月即视为齐。

## Related

- [离职发起人附件 userNotExist](../../dingtalk/dingtalk_oa_approval/docs/research/departed-originator-download.md)
- [2026-09-10 7 月对照过程](../../dingtalk/dingtalk_oa_approval/docs/research/2026-09-10-july-amazon-period-reconcile.md)
- [浏览器补下载钉钉管理后台](../../dingtalk/dingtalk_oa_approval/docs/research/browser-admin-download.md)
- [渠道账号表同步 EN](../workflow-issues/en-channel-account-gsheet-sync.md)
- [网页任务必须先 dispatch --check](../workflow-issues/search-first-before-implementing.md)
