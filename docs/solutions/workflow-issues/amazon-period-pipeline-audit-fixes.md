---
okf: v0.1
type: Reference
title: 账期管道审计修复：去重、FBA 过滤键、Tax 别名与写表口径
date: 2026-11-19
category: workflow-issues
module: amazon_period_tax
problem_type: workflow_issue
component: tooling
severity: high
applies_when:
  - "重跑 Tax{YYYYMM} / Phase3 五张表"
  - "同一账期桶里有人重复上传了同内容 txt"
  - "FBA 费用扣减后分类汇总 / 收款比例运营人员 与 Colab 对不上"
  - "9/10 月缺 FBA 两张表"
  - "审批已撤销/拒绝的单据混进定稿导出"
tags: [amazon-period, tax, phase3, fba, dedupe, channel-alias, gsheet, audit]
---

# 账期管道审计修复（2026-11-19）

## Context

对本地 Tax / Phase3 管道做逐项审计，发现会**写错数或静默丢数**的 15 个问题。全部修复在
`feature/amazon-period-audit-fixes` 分支，只改代码与测试，**未写任何 Google Sheet / NAS 文件**。
完整逐项报告见仓库外
`D:\Work\王忠于\成本核算\dingtalk_oa_approval_data\reports\fixes_report_20261119.md`。

## 关键结论

1. **同内容 txt 会双算 Tax**。8 月桶里 `李雨欣/AMZRosoonFR-2026-08-05.txt` 与
   `苏燕星/AMZRosoonFR-2026.08.05.txt` md5 相同，`AMZRosoonSE` 也有一份 `(1)` 副本；
   Tax 曾多算 **1,933.63**（FR +1,789.01 / SE +144.62）。`read_bucket_amz_txts` 现在按内容
   md5 去重，报告 `SKIP-DUP <path> == <first>`；`--strict` 时有重复即非 0 退出。
   修复后重算 394,668.06（= 表内 396,601.69 − 1,933.63）。
2. **FBA 规则过滤键错位**。`process_fba_orders` 已把 `平台SKU` 改名 `sku`，过滤却回取
   `平台SKU` → 取空 → 规则退化为**整账号**匹配。202608 实测：调整前-后 amount人民币
   旧算法 −84,431.99，正确值 **−16,091.76**，多扣 **68,340.24**。修好后与 GSheet 现表逐行一致。
3. **Tax 别名未归一**会静默变成独立账号行；现在按（大写后的）别名映射回规范渠道账号，
   未匹配的收集到 `tax_unmatched_accounts` 并进 warnings。
4. **定稿导出漏审批过滤**：`filter_export_by_period.py` 之前只按账期月 + 迟交键过滤。
   2026-09 实跑：旧 171 行 → 新 168 行，剔除 3 张已撤销（销售额 2,833.99 / 3,775.07 / 2,753.94）。
5. **写表口径改 RAW**：`审批编号` 等 ID 列强制文本，数字保留原生类型；`ws.clear()` 只清值，
   `_人民币` / `_比例` 的数字格式不会被破坏。

## 硬关卡

```powershell
uv run python amazon_period_tax/scripts/verify_period.py --bucket 账期20260804-20260903
```

检查项：Tax 合计 == 本地重算、账号集合/行数、每账号金额；Phase3 的 Tax/附加费合计、
原始「外币>0 且汇率空」、渠道账号未匹配、分组表合计 == 行级过滤后合计、原始含
`渠道账号正确提交次数`。任一项 FAIL 非 0 退出。202609/202610 目前唯一 FAIL 是原始表缺
`渠道账号正确提交次数`（历史表是修复前写的），需重写该列后才转 PASS。

## 仍需写表才能生效的数据动作（未执行）

- 重写 `Tax202608`（396,601.69 → 394,668.06，去掉双算）。
- 重写 8 月 `人民币20260804-20260903` 的 `Tax amount人民币` 列，保持与 Tax 表一致。
- 9/10 月补 `{期}FBA费用扣减后分类汇总` 与 `{期}FBA费用扣减后收款比例运营人员`
  （`--write-gsheet-fba`；dry-run 已算出 21/16 与 13/13 行）。
- 9/10 月（及 8 月）重写五张主表以带出 `渠道账号正确提交次数`、`收款比例运营人员` 列序。

## 环境坑

- 本地同步桶在修复过程中被别人规范化过（8 月 67 → 65 个 txt、重命名完成），
  复现 `SKIP-DUP` 需用历史运行日志或合成用例；2026-07 桶仍有一份跨注释目录的重复。
- `channel_canonical` 读取快照时打印 mtime + 行数，>30 天 WARN；同一别名指向不同账号时
  `raise`。已知 `美国站-DaneeyUS` / `美国站-DANEEYUS` 仅大小写不同，保留第一条并醒目 WARN
  （与 Colab `drop_duplicates(keep='first')` 一致）；其它真歧义直接报错。
