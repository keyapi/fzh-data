---
okf: v0.1
type: Reference
title: 账期附件跨桶错放：同一结算文件出现在另一账期桶
date: 2026-11-19
category: workflow-issues
module: amazon_period_tax
problem_type: workflow_issue
component: tooling
severity: high
symptoms:
  - "某账号某月 Tax 偏高，但 OA 行数与附件数看起来一致"
  - "同一 md5 的 txt 出现在两个账期桶"
  - "OA 的账期收款额与桶内 txt 的 total-amount 对不上"
root_cause: attachment_misfiled_across_periods
resolution_type: code_fix
tags: [amazon-period, tax, attachment, dedupe, settlement-id, nas, audit]
---

# 账期附件跨桶错放：同一结算文件出现在另一账期桶

## Problem

2026-08 桶里的 `卢天姿/AMZJohnaUS-8.11.txt` 与 2026-07 桶的
`卢天姿/AMZJohnaUS-7.29.txt` **逐字节相同**（md5 `67621a0e…`）。文件内部字段：

- `settlement-id = 27080868331`
- `settlement-start-date = 2026-07-20`，`settlement-end-date = 2026-07-28`
- `total-amount = 2034.72 USD`

它对应的是 7 月 OA 的 7/29 行（2034.72）。8 月 OA 的 8/11 行是 **752.64**，属于另一个结算
`27171210801`（7/28–8/11），而这份报告**全 NAS 都不存在**。

进一步用浏览器进钉钉后台下载该单附件后确认：**OA 里上传的 8/11 附件本身就是 7 月那份**，
不是 NAS 归档放错，也不是 Synology 同步副本。赛狐 V2 结算组接口（`transferAmount`，原始币种）
交叉验证了 8/11 的真实结算确实存在且为 752.64 USD。

## Symptoms

- 8 月 Tax 合计含 1,854.29 元来自这份 7 月副本（同一外币基数乘 8 月汇率）；
- 真实的 8/11 结算 Tax 缺失，8 月 Tax 无法定稿；
- 只看文件名（`-8.11`）会误判为命中，按月内 md5 去重也发现不了。

## What Didn't Work

- **按文件名/日期匹配**：文件名日期是提交人手工写的，不是结算身份。
- **同桶 md5 去重**：两份文件在不同桶，各自桶内都唯一。
- **信任「OA 金额与附件能对上」**：只有金额、不校验结算号时，7 月副本恰好与 7 月 OA 对得上，
  但被放进了 8 月桶。
- **钉钉附件 API**：离职发起人返回 `userNotExist`，只能用浏览器下载；下载后才发现原件就是错的。

## Solution

1. `read_amz_txt` 解析每个 txt 的 `settlement-id`、`settlement-end-date`、`deposit-date`，
   取桶名（`账期YYYYMMDD-YYYYMMDD`）前 6 位作为**账期自然月**，要求内部 `settlement-end-date`
   的月份等于它（缺失退回 `deposit-date`）；不等记 `OUT-OF-PERIOD <rel> month=...`，
   **默认排除**（`--allow-out-of-period` 才纳入）。
   注意不能用「4 号→次月 3 号」窗口套打款日：`AMZRosoonSE-2026-08-01`（结算 8/1、打款 8/3）
   是正常的 8 月账期，曾被误杀。
2. 新增 `settlement_ledger`：扫描全部账期桶，按 `settlement-id`/内容找跨桶重复，输出
   「同一结算出现在 A桶/B桶」清单；只报告、不自动删。
3. `run_period_tax --strict`：`OUT-OF-PERIOD` / `SKIP-DUP` / `FAIL` 任一 > 0 即非 0 退出。
4. `verify_period.py` 增加对应检查，写表前必须通过。

## Why This Works

结算号 + 内部结算区间是文件身份的唯一可信来源；把它们和桶窗口绑定后，
「同一份结算被放到另一个账期」会在读取阶段暴露，而不是在 Tax 合计里静默偏移。

## Prevention

- 每月写表前先跑 `settlement_ledger` + `verify_period --strict`。
- 附件命名统一为 `{渠道账号}-{结算结束日 YYYY-MM-DD}.txt`，命名只作展示，身份仍以内部字段为准。
- 归档时先按结算号台账查重，再落桶；DRM/人工整理环节发现的同名同内容只保留一份。
- 已清理：8 月两组同内容副本、跨桶 JohnaUS 副本、7 月 RosoonIT 副本（按 OA 发起人保留主人文件夹）。

### 官方附件确实拿不到时：赛狐明细只能做「待核验补录」，不能冒充原件

赛狐 V2 `settlementSummary/detailPage.json` 有逐笔明细，可映射成 Amazon flat-file
（`amazon_period_tax/scripts/sellfox_synth_txt.py`）。用有官方 txt 的 7 月结算验证：
171 行、2034.72、Tax 273.10，与官方逐行多重集完全一致。8/11 据此得到 214 行、752.64、
Tax 259.53 USD。

但 Codex 复核结论是 **CONDITIONAL**：合成列缺 `shipment-id/order-item-code/adjustment-id`，
`posted-date` 时区与 `deposit-date` 与官方不同；**不能放进官方附件扫描路径**（否则官方原件
到达后会两份都计 Tax）。正确做法是作为「赛狐来源、待官方核验」的 Tax 调整凭据，
由财务确认后再补录；文件名/目录必须隔离，不进正常桶。

## Related

- `amazon_period_tax/read_amz_txt.py`、`amazon_period_tax/settlement_ledger.py`
- `amazon_period_tax/scripts/verify_period.py`
- `docs/solutions/workflow-issues/amazon-period-pipeline-audit-fixes.md`
- `docs/solutions/integration-issues/amazon-period-fx-currency-label-invisible-chars.md`
