---
okf: v0.1
type: Reference
title: 钉钉账期月收尾——宽窗导出、赛狐转账、NAS 桶与 Colab 定稿文件名
date: 2026-10-14
category: workflow-issues
module: dingtalk_oa_approval
problem_type: workflow_issue
component: tooling
severity: medium
applies_when:
  - "用发起时间窗导出的 OA xlsx 切某一自然月账期定稿"
  - "对照赛狐 siteGroupEndStr + fundTransferStatusStr 与钉钉账期收款额"
  - "判断 NAS 账期桶 Amazon txt 是否与相邻月桶重复"
  - "Colab 步骤 2.1 要求定稿 xlsx 文件名含 YYYYMMDD-YYYYMMDD"
tags:
  - dingtalk-oa
  - sellfox-settlement
  - nas-period-bucket
  - period-closeout
  - colab-filename
---

# 钉钉账期月收尾——宽窗导出、赛狐转账、NAS 桶与 Colab 定稿文件名

## Context

财务按月关账时要同时满足四条线：**钉钉销售收款确认单**（按 `账期日期` 自然月）、**赛狐结算中心**转账金额、**NAS 账期桶**里的 Amazon `.txt`、以及 **Colab** 透视表/Tax 流水线。发起时间窗导出与账期月不一致；赛狐店名与钉钉 `AMZ*` 列、附件文件名前缀也不总是一一对应。2026-09 在宽窗导出 `20260801–20261013` 上跑通了一套可重复的核对口径。

## Guidance

### 1. 定稿行：先 `filter_export_by_period`，再视情况 `--exclude-keys`

- 宽窗 Excel → `filter_export_by_period.py --period YYYY-MM` 只保留 `账期月` 列。
- `late_submission_keys.py` 导出的是**发起在当月窗、账期日期在上月**的键；若定稿已按账期月过滤，这些键常 **命中 0**（仍建议生成登记文件备查）。
- 手工改定稿时只改对应品牌列（如 `AMZStrusery账户`），并写外部修订记录（不进 git 的 `DINGTALK_OA_WORK/reports/` 即可）。

### 2. 钉钉完整性：导出 vs API probe

对 Amazon + `keep_approval` 行，用 `unique_key` 与 `probe_*.jsonl`（`get_instance` 扫发起窗）对账。**导出缺行**才算钉钉缺口；与赛狐/NAS 无关。

### 3. 赛狐：字段名与「一行一笔转账」

- 用 `siteGroupEndStr` / `groupEndStr`、`fundTransferStatusStr`（`转账成功`）、`transferAmount`、`storeName`；不要用旧字段 `groupEnd` / `fundStatus`。
- 同一站 **一月多结**：钉钉会有**多行**（可能账期日期相同），每行 `账期收款额` 对应一笔 `transferAmount`。例：Rosoon SE 两笔 `1634.13`（groupEnd 09-12）与 `1285.58`（09-26）——**定稿无需改数**，勿用「一行只能配一笔赛狐」的脚本结论否定数据。
- 店名别名：钉钉 `AMZBJXJUS` ↔ 赛狐 `Jalnoddsa`（熙锦），按渠道账号表映射，金额仍可对上。
- 表单账户填错站点：如 Strusery 行填 `AMZStruseryBE` 而赛狐为 **US** 1280.44 → 改定稿列为 `AMZStruseryUS`（与赛狐一致），不是删行。

### 4. NAS：核算桶 vs 提交桶；相邻月 stem 互斥

- Tax/核算读 **`账期日期` 自然月桶**（如 9 月 → `账期20260904-20261003`），不是 DRM 按发起时间的提交桶。
- 相邻两月桶内按 `stem_key` 做交集：**应为 0**。2026-08/09 实测 67 vs 72 文件、交集 0 → 用 8 月桶重算 Tax 不会吃到 9 月文件。
- 文件名 `AMZJohnaUS-0903.txt`、`AMZStrusery-US-0907.txt` 等会导致 `parse_amz_channel` 解析不出 `period_month`；应在 NAS 上规范为 `…-2026-09-03.txt` 并记修订 JSON。
- 刘小菁类 **账期明细仍是 csv、txt 在评论附件**：核算只认 `.txt`；需 `withCommentAttatchment=true` 或备注补传后再 DRM 入桶。

### 5. Colab 主 notebook 与 `excel_filename`

- 主流程 notebook（Google Drive `Colab Notebooks/成本核算/透视表订单/`）：`钉钉OA收款费用Amazon多平台&附加费&Tax 20250704.ipynb`。
- **Cell 6**：`OA_PERIOD_RE = (\d{8})-(\d{8}|\d{4})` → `accounting_yyyymm` 取区间**起始**八位的前 6 位（`20260904` → `202609`）。
- 上传 `/content` 的文件名须含区间，建议与 8 月示例同构：  
  `Amazon&新平台成本 20260904-20261003 核算定稿_20260904-20261003_销售收款确认单_<stamp>.xlsx`
- **2.1 不会自动改** GSheet 的 `worksheet_name_yearmonth*`、步骤 6 的 `Tax202609`、1.2 的 `运营人员202609`——跑新月须手改。
- Tax 从 NAS txt 汇总：`税账期TXT 挂载Gdrive.ipynb` 的 `global_working_dir` 指向对应 `账期YYYYMMDD-YYYYMMDD` 目录。

## Why This Matters

混用「发起窗」「账期月」「赛狐 groupEnd」三者之一当唯一真相，会在关账周产生假缺口或假重复；Colab 文件名不含 8 位区间会在步骤 2.1 直接报错。

## When to Apply

- 每月 Amazon/多平台关账前；
- 宽窗导出换新文件后复核某月；
- NAS 重命名或 DRM 重下后验证桶内 stem；
- 新同事接 Colab 定稿上传。

## Examples

**Rosoon SE（2026-09）**：两行同账期日期、两个 `账期收款额`，各对赛狐一笔转账 → 定稿保留两行。

**Strusery（2026-09-07）**：`202610091112000258547` 账期收款 1280.44，列由 BE 改为 US。

## Related

- [amazon-period-file-reconcile.md](../conventions/amazon-period-file-reconcile.md)
- [late-submission-registry.md](../../../dingtalk/dingtalk_oa_approval/docs/reference/late-submission-registry.md)
- `dingtalk/dingtalk_oa_approval/filter_export_by_period.py`
- `dingtalk/dingtalk_oa_approval/AGENT_HANDOFF.md`（8/9 月收尾摘要）
- [colab-notebook-drive-api-editing.md](../developer-experience/colab-notebook-drive-api-editing.md)
