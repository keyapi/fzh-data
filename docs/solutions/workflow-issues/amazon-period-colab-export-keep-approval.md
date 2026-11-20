---
okf: v0.1
type: Reference
title: 账期核算定稿导出须用 keep_approval + 可选迟交 exclude-keys
date: 2026-11-09
category: workflow-issues
module: dingtalk_oa_approval
problem_type: workflow_issue
component: tooling
severity: high
applies_when:
  - "定稿 xlsx 行数明显多于钉钉 Amazon 保留单"
  - "Phase3 / 利润审计与 NAS txt 对不上"
  - "从宽表导出重刷某月定稿（如 8 月）"
tags: [dingtalk-oa, amazon-period, colab, keep-approval, late-submission]
---

# 账期核算定稿：`keep_approval` 与 `--exclude-keys`

## Context

下游 Phase3 与利润审计都吃 **`export_colab_period.py` 产出的核算定稿 xlsx**（sheet `核算行`）。若定稿从「宽表钉钉导出」直接筛账期月、**未**按审批状态/结果过滤，会混入已撤销/非保留单，表现为定稿 **Amazon 行数 > NAS txt 对应单量**（例：旧 8 月定稿 218 行 / 69 Amazon，刷新后 183 / 65）。

## Guidance（本学习沉淀的做法）

1. **保留规则**：与 NAS 上传、附件抓取一致，用 `parse.keep_approval(审批状态, 审批结果)`（`COMPLETED`+`agree` / `RUNNING` 等，见 `tests/test_approval_filter.py`）。
2. **定稿 CLI**：`dingtalk/dingtalk_oa_approval/export_colab_period.py`
   - 过滤：`账期月 == --period` 且 `keep_row` 为真。
   - 亚马逊销售账户：经 `channel_canonical.canonical_account` 对齐运营表「渠道账号」。
   - **迟交剔除**：`--exclude-keys` 指向登记文件（与 `filter_export_by_period.load_exclude_keys` 同格式：每行 `审批编号|账期日期|销售账户|销售额`）。
3. **重刷流程（以 8 月为例）**：宽表 xlsx → `export_colab_period` + `late_exclude_keys_*.txt`（若无命中则 0 剔除）→ 新 `*_colab.xlsx` → `run_period_phase3.py --write-gsheet`。
4. **审计**：`period_profit_audit.py` 文件名解析应用账期桶变量（勿用未定义 `period` 名，否则 8.10 风格路径会报错）。

## Why This Matters

定稿是 Phase3 唯一输入；少过滤一步会在合并表放大误差，且难以从 GSheet 侧反推根因。

## When to Apply

- 每月 Colab 定稿生成、历史定稿纠错、钉钉 vs NAS txt 条数不一致排查。

## Examples

```powershell
uv run python dingtalk/dingtalk_oa_approval/export_colab_period.py `
  --in "...\dingtalk_wide.xlsx" --period 202608 `
  --exclude-keys "...\late_exclude_keys_202608.txt" `
  --out "...\Amazon&新平台成本 ..._20261109_colab.xlsx"
```

## Related

- `dingtalk/dingtalk_oa_approval/docs/reference/late-submission-registry.md`
- `docs/solutions/conventions/amazon-period-file-reconcile.md`
- `amazon_period_tax/AGENT_HANDOFF.md`（Phase3 输入说明）
- `docs/solutions/integration-issues/amazon-period-phase3-gsheet-not-colab-id.md`
