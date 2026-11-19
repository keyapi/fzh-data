---
okf: v0.1
type: Reference
title: 账期管道审计修复：去重、FBA 过滤键、Tax 别名与写表口径
date: 2026-11-19
last_updated: 2026-11-19
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

## 第二轮（Codex 复核后，2026-11-19）

Codex 独立复核给出 REJECT：主表三项金额算术通过，但源头完整性/可复现性不通过。据此追加：

1. **跨期错放拦截**：解析 txt 的 `settlement-id` + 内部结算区间，不在桶窗口内记
   `OUT-OF-PERIOD` 并默认排除；实测案例见
   [`amazon-period-cross-bucket-attachment-misfile.md`](amazon-period-cross-bucket-attachment-misfile.md)。
2. **结算台账**：`settlement_ledger` 跨全部账期桶按结算号查重，只报告不删。
3. **Tax 缺列硬失败**：`load_tax_grouped` / `load_additional_fee_grouped` 缺必需列直接抛错，
   不允许用空 DataFrame 冒充“本月无 Tax”。
4. **桶月/汇率月一致**：`--exchange-month` 默认从 `--bucket` 推导，显式不一致时读写前报错。
5. **附加费 alias→canonical**：`BasePPPL` 归到 `BASEPPPL`，修复 7 月 6,428.80 附加费挂空运营人员的问题。
6. **FBA 分摊守恒**：同一账号在组表多行时不允许每行各加一份账号级差额；不平即 raise。
7. **merge 唯一性**：汇率/账号/附加费/Tax 连接使用 `validate='many_to_one'` 或等价断言。
8. **日期合法性**：拒绝 `2026-02-31` 这类非法日期。
9. **审批中占比报告**：`verify_period` 输出每月审批中行数/应收/销售及占比（只报告，不阻断）。

测试：`uv run python -m pytest amazon_period_tax/tests dingtalk/dingtalk_oa_approval/tests -q`
→ **100 passed**（第一轮 55 + 第二轮 45）。

## 硬关卡
```powershell
uv run python amazon_period_tax/scripts/verify_period.py --bucket 账期20260804-20260903
```

检查项：Tax 合计 == 本地重算、账号集合/行数、每账号金额；Phase3 的 Tax/附加费合计、
原始「外币>0 且汇率空」、渠道账号未匹配、分组表合计 == 行级过滤后合计、原始含
`渠道账号正确提交次数`。任一项 FAIL 非 0 退出。202609/202610 目前唯一 FAIL 是原始表缺
`渠道账号正确提交次数`（历史表是修复前写的），需重写该列后才转 PASS。

## 仍需写表才能生效的数据动作（未执行）

> 2026-11-19 决定：**所有生产表写入暂停，等 8 月真实附件补齐后再一次性写**。

- **8 月 Tax 暂不能定稿**：394,668.06 里仍含 1,854.29 来自 7 月 JohnaUS 副本；
  真实 8/11 结算 `27171210801`（752.64 USD）的报告缺失，已请人在 Amazon 后台下载。
- 重写 8 月 `人民币20260804-20260903` 的 `Tax amount人民币` 列，保持与 Tax 表一致。
- 9/10 月补 `{期}FBA费用扣减后分类汇总` 与 `{期}FBA费用扣减后收款比例运营人员`
  （`--write-gsheet-fba`；dry-run 已算出 21/16 与 13/13 行）。
- 9/10 月（及 8 月）重写五张主表以带出 `渠道账号正确提交次数`、`收款比例运营人员` 列序。

## 环境坑

- 本地同步桶已清理：8 月 67 → 65 个 txt（两组同内容副本已删，保留副本改名规范）；
  跨桶 JohnaUS 7 月副本已从 8 月桶删除；7 月 RosoonIT 副本按 OA 发起人保留苏燕星、删尹天强。
  复现 `SKIP-DUP` 需用历史运行日志或合成用例。
- `channel_canonical` 读取快照时打印 mtime + 行数，>30 天 WARN；同一别名指向不同账号时
  `raise`。`美国站-DaneeyUS` / `美国站-DANEEYUS` 的重复别名已由业务在渠道账号表删除
  （保留 `AMZDANEEYUS`），快照已重新导出（221 行，含 `WFUK`）。
