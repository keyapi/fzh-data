---
name: amazon-period-tax
description: >
  Amazon 账期 NAS txt Tax/附加费写表 + Phase3 合并写回「钉钉OA收款费用Amazon多平台&附加费&Tax」。
  触发词：账期 txt、Tax worksheet、附加费&Tax、run_period_tax、run_period_phase3、
  phase3、核算定稿 colab、PHASE3_SPREADSHEET_ID、export_colab_period、keep_approval、
  税账期TXT、汇率 sheet、WFUK 渠道别名。
---

# amazon_period_tax

目录：`amazon_period_tax/`。先读 `AGENT_HANDOFF.md`。

**新对话必读经验**

- `docs/solutions/integration-issues/amazon-period-phase3-gsheet-not-colab-id.md`
- `docs/solutions/workflow-issues/amazon-period-colab-export-keep-approval.md`
- `docs/solutions/integration-issues/amazon-period-tax-fx-alias-multiplies.md`
- `docs/solutions/workflow-issues/amazon-period-tax-rerun-without-agent.md`
- txt / 迟交惯例：`docs/solutions/conventions/amazon-period-file-reconcile.md`

定稿输入：`dingtalk/dingtalk_oa_approval/export_colab_period.py`（须 `keep_approval`，可选 `--exclude-keys`）。

```powershell
uv run python amazon_period_tax/scripts/run_period_tax.py --bucket 账期YYYYMMDD-YYYYMMDD --exchange-month YYYYMM --write-gsheet --sort-gsheet-tabs
uv run python amazon_period_tax/scripts/run_period_phase3.py --in <核算定稿_colab.xlsx> --bucket ... --exchange-month YYYYMM --write-gsheet --gspread-auth sa
```

GSheet 默认 **服务账号**（`tongtool_order_cost/gsheets.py`）。Phase3 表 id 见 `phase3_constants.PHASE3_SPREADSHEET_ID`。
