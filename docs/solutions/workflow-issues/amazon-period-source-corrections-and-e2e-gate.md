---
okf: v0.1
type: Reference
title: 账期定稿源数据错误：独立对账、修正凭据与写前硬门禁
date: 2026-11-19
category: workflow-issues
module: amazon_period_tax
problem_type: workflow_issue
component: tooling
severity: high
symptoms:
  - "四期主表算术逐项对平、verify 全 PASS，但运营业绩数字仍不可用"
  - "OA 定稿某行金额是附件/结算的 100 倍"
  - "同一审批下不同站点的附件被挂到错误渠道账号"
  - "重写主表后旧 FBA 人员表仍用旧基数"
root_cause: source_data_error
resolution_type: code_fix
tags: [amazon-period, audit, oa-source, correction-voucher, pre-write-gate, manifest]
---

# 账期定稿源数据错误：独立对账、修正凭据与写前硬门禁

## Problem

把「账期数据」从费用口径升级为运营业绩基准后，仅靠管道内部合计自洽不够。对 7–10 月做完整
E2E 独立复核（Decimal 从定稿/附件重算，不调用项目聚合函数）后发现：四期表内算术全部正确，
但**源定稿本身有错**，因此当时的生产表被判定 REJECT。

## Symptoms

- 7 月一条 OA 行（`AMZJohnaSE`）的销售/应收/佣金是附件与赛狐结算的 **100 倍**；
  比例列恰好同倍放大，只看比例发现不了。
- 4 条记录的**渠道账号归属**与附件结算身份不符（同审批多站点行被填错账号）。
- 7 月 FBA 人员表在五表重写后仍是旧基数（漏掉后续按币种修复的金额）。
- 10 月 3 份**旧版 V1** 附件被按 V2 读取，金额变 NaN，Tax/FBA 静默少算（见另一篇）。

## What Didn't Work

- **只对表内合计/比例做对账**：错数同倍放大、错账号在总额内互相抵消时完全看不出来。
- **信任 OA 定稿**：OA 是人工填报，附件才是结算身份；金额必须回到附件 `settlement-id` 核对。
- **只按总和认账**：人员/账号级归属错位总额守恒，绩效会串人。
- **边写边校验**：先写后报会让错误值已经落在生产表。

## Solution

1. **不可变原件 + 修正凭据**：`remediation/20261119/corrections.v1.json` 记录每条修正的
   审批编号、行指纹（日期/账户/金额）、原值→修正值、附件路径+md5、settlement-id、授权与状态。
2. **修正副本**：`amazon_period_tax/remediation.py` 从原件生成 `*.corrected.v1.xlsx`，
   原件不动；行匹配必须恰好命中 1 行，否则失败。
3. **写前硬门禁**（`run_phase3`）：币种/账号未匹配、分组合计、Tax/附加费合计任一项不平，
   在写入前直接抛错；写表后生成 run manifest（输入 md5、别名/白名单 md5、行数、合计、写入表）。
4. **人民币表补列**：`应收金额_人民币`、`销售额_人民币` 与主表同口径，避免下游再跳表。
5. **复验**：修正后四期 `verify_period` 全 PASS，且独立终审 ACCEPT、零回归。

## Why This Works

把「输入是否正确」和「管道是否算对」分开验证：附件结算号/金额是唯一可信身份，
修正凭据让每一次改数可重放、可审计；写前门禁保证错误输入进不了生产表。

## Prevention

- 每月写表前：先 `--dry-run --strict` + `verify_period`，再做独立抽样（至少覆盖当月最大金额与
  币种特殊的账号）。
- 任何与历史已发布数不同的修正，必须留凭据并单独向财务说明差额构成。
- OA 原件保留；生产只用 corrected 副本或运营正式确认后的新定稿。
- 人工步骤（OA 填报、附加费占位、附件归档）要有审批/修订台账，不以「脚本跑成功」代替。

## Related

- `amazon_period_tax/remediation.py`、`scripts/apply_remediation.py`
- `amazon_period_tax/phase3_merge.py`（写前门禁 / manifest / 人民币补列）
- `docs/solutions/workflow-issues/amazon-period-pipeline-audit-fixes.md`
- `docs/solutions/integration-issues/amazon-settlement-v1-v2-flatfile.md`
