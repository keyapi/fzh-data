---
okf: v0.1
type: Reference
title: Amazon 账期 Phase3 写表须用 Spreadsheet ID，勿与 Colab notebook 文件 ID 混用
date: 2026-11-09
category: integration-issues
module: amazon_period_tax
problem_type: integration_issue
component: tooling
severity: high
applies_when:
  - "本地 `run_period_phase3.py --write-gsheet` 报 gspread 400 invalid argument"
  - "已给 SA 共享编辑但仍打不开表"
  - "从 Colab notebook 链接或 Drive 文件列表抄 ID"
tags: [gspread, phase3, colab, google-sheets, amazon-period]
---

# Amazon 账期 Phase3：Spreadsheet ID ≠ Colab notebook 文件 ID

## Context

Phase3（`钉钉OA收款费用Amazon多平台&附加费&Tax`）要把合并结果写回五张 worksheet。本地移植对齐 Colab `钉钉OA收款费用Amazon多平台&附加费&Tax 20250704.ipynb`。gspread 用服务账号 `open_by_key` 时若 ID 填错，常见是 **400 The request failed: invalid argument**，容易被误判为「SA 没权限」（403 才是典型权限问题）。

## Guidance（本学习沉淀的做法）

1. **写表目标**是 Google **Spreadsheet**，不是同名 Colab **.ipynb** 的 Drive 文件。
   - 正确表：[钉钉OA收款费用Amazon多平台&附加费&Tax](https://docs.google.com/spreadsheets/d/18e64bl51Sdon-StokTnMc2CCcXyEFASdd7bjtyrdp38/)
   - 常量：`amazon_period_tax/phase3_constants.py` → `PHASE3_SPREADSHEET_ID = 18e64bl51Sdon-StokTnMc2CCcXyEFASdd7bjtyrdp38`
2. **勿用** Colab notebook 的 Drive file id（历史上误写过 `1tyBOhVCG5uEQ90RMUyV4rN_JRURW_aeh`——那是 notebook，不是 spreadsheet）。
3. **鉴权**：日常写表用 **服务账号 JSON**（`tongtool_order_cost/gsheets.py`，与「附加费&Tax」表相同套路）。用户 OAuth 仅用于给 SA 加协作等 Drive 脚本，**不是** Phase3 每跑必走步骤。
4. **共享**：与「和财务部共享」一致，给 `colab-gsheets@gsheets-351101.iam.gserviceaccount.com` **编辑者**即可。
5. **运营渠道别名**：Phase3 未匹配 `销售账户` 时，在「和运营部共享」`渠道账号（20260521起在此维护）` 的 **渠道账号别名** 列补英文逗号别名（例：**WFUK** 挂在 **WFEU**）。

## Why This Matters

Drive 上 notebook 与 spreadsheet 都是「文件」，URL 形态相似；抄错 ID 时 API 在「打开对象」阶段就失败，排权限会白费时间。

## When to Apply

- 任何 Phase3 gsheet 写入、常量审查、Colab→本地 ID 对照。
- 看到 400 invalid argument 时 **先核对 ID 类型**，再查 SA 共享。

## Examples

```powershell
uv run python amazon_period_tax/scripts/run_period_phase3.py `
  --in "...\核算定稿_..._colab.xlsx" `
  --bucket 账期20260804-20260903 --exchange-month 202608 `
  --write-gsheet --gspread-auth sa
```

## Related

- `amazon_period_tax/AGENT_HANDOFF.md`
- 附加费&Tax 独立表：`amazon_period_tax/gsheet_tax.py` → `ADDITIONAL_FEE_TAX_SPREADSHEET_ID`
- 钉钉定稿导出：`docs/solutions/workflow-issues/amazon-period-colab-export-keep-approval.md`
