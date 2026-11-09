---
okf: v0.1
type: Handoff
title: Amazon 账期 txt Tax 管道（本地）
description: 替代 Colab「税账期TXT 挂载Gdrive」Tax 主线 + Phase2 探索 sheet/FBA；读 NAS 同步桶、汇率 gsheet、出 Excel + Tax worksheet
tags: [amazon, tax, txt, colab, gsheet, nas]
timestamp: 2026-11-04
---

# amazon_period_tax

## 目标

与 Colab **`税账期TXT 挂载Gdrive.ipynb`** 对齐：

| Phase | 内容 |
|-------|------|
| **1** | txt → 汇率 → **账号Tax汇总** → `附加费&Tax` / `Tax{YYYYMM}`（**每渠道账号一行**） |
| **2** | 探索用 Excel 多 sheet（金额分类、订单/退款、**FBA 特例**）；`posted-date` **dateparser** |
| **3** | `钉钉OA收款费用Amazon多平台&附加费&Tax 20250704.ipynb` | ✅ `run_period_phase3.py` → `phase3_merge.py`（需 SA 有 Phase3 表协作权） |

## 产出路径

- **定稿 xlsx**：`{LOCAL_NAS_PERIOD_ROOT}/账期YYYYMMDD-YYYYMMDD/合并Amazon_{桶}_{ts}.xlsx`（桶根目录，**不**用 `_tax_pipeline/`）
- **tab 修复缓存**：`{桶}/.repair_cache/`（不写人名子目录 `自动修复sku/`）
- **可选镜像**：`--out-dir`（如 `dingtalk_oa_approval_data/reports/tax_txt`）
- **NAS 上传**：`{NAS_FINANCE_PERIOD_ROOT}/{桶}/{同名 xlsx}`（`--upload-nas`）

## GSheet

- **`附加费&Tax`**：`open_by_key` → `ADDITIONAL_FEE_TAX_SPREADSHEET_ID`（`gsheet_tax.py`），避免按标题搜索失败
- 写 **`df6_gsheet`**：`tax_summary_for_gsheet()` — 按 `渠道账号` 聚合；无 Tax 行的账号补 0（避免 Phase3 缺行/重复行）
- **`--sort-gsheet-tabs`**：Colab cell 25 — `sort_additional_fee_tax_tabs`：`附加费` 在同月 `Tax` 前，**YYYYMM 降序**；可选 `pin_worksheet` 把刚写的 **Tax** 或新建的 **附加费** 钉到该区块**最左**
- **附加费占位**：财务未填时 Phase3 按 **0** 合并；缺 ws 则 `ensure_zero_additional_fee_worksheet`（表头抄上一月 `附加费{YYYYMM-1}`，数值列 0，渠道行来自 `Tax{YYYYMM}`）

```powershell
uv run python amazon_period_tax/scripts/ensure_additional_fee_worksheet.py --exchange-month 202610 --bucket 账期20261004-20261103
uv run python amazon_period_tax/scripts/ensure_additional_fee_worksheet.py --exchange-month 202610 --sort-only
```

## 与 Colab 差异（改进）

| 项 | Colab | 本地 |
|----|-------|------|
| 渠道账号 | 文件名 `split('-')[0]` | `channel_canonical` + `amz_txt_naming` |
| df6 写表 | 可能多行/币种 | **强制每账号一行** |
| 数据源 | Drive MyPC | `LOCAL_NAS_PERIOD_ROOT` |
| 探索 sheet | notebook | `explore_tables.build_exploration_tables`（仅供参考） |

## 命令

```powershell
cd d:\Work\赛狐\Cursor
uv run python amazon_period_tax/scripts/run_period_tax.py --bucket 账期20261004-20261103 --exchange-month 202610 --dry-run
uv run python amazon_period_tax/scripts/run_period_tax.py --bucket 账期20261004-20261103 --exchange-month 202610 `
  --write-gsheet --sort-gsheet-tabs --upload-nas `
  --out-dir "D:\Work\王忠于\成本核算\dingtalk_oa_approval_data\reports\tax_txt"
# 仅 Tax 三 sheet：加 --phase1-only
```

环境：`dingtalk/dingtalk_oa_approval/.env` → `LOCAL_NAS_PERIOD_ROOT`；`NAS_API/.env` → `NAS_ADMIN_USER` + `NAS_FINANCE_PERIOD_ROOT`。

```powershell
uv run python amazon_period_tax/scripts/run_period_phase3.py `
  --in "D:\...\核算定稿_..._colab.xlsx" `
  --bucket 账期20261004-20261103 --exchange-month 202610 --dry-run
uv run python amazon_period_tax/scripts/run_period_phase3.py ... --write-gsheet
```

Phase3 写 **Google 表** [`钉钉OA收款费用Amazon多平台&附加费&Tax`](https://docs.google.com/spreadsheets/d/18e64bl51Sdon-StokTnMc2CCcXyEFASdd7bjtyrdp38/)（`PHASE3_SPREADSHEET_ID`）。**不是**同名 Colab notebook（`1tyBOhVCG5uEQ90RMUyV4rN_JRURW_aeh`）。默认 **SA**，表已与「和财务部共享」同样给 `colab-gsheets@…` 编辑者即可。

未匹配 `销售账户`（如多平台缩写与别名表不一致）→ 在「和运营部共享 / 渠道账号（20260521…）」**渠道账号别名**补英文逗号分隔别名（例：**WFUK** 挂在 **WFEU** 行）。

产出 ws（账期区间来自桶名）：

| Worksheet | 内容 |
|-----------|------|
| `{YYYYMMDD-YYYYMMDD}` | 按渠道账号/收款归属/币种分组 |
| `{…}原始` | 行级 OA + 汇率 + 运营人员 |
| `人民币{…}` | 收款费用 + 附加费 + Tax 按账号 |
| `{…}收款比例收款归属` / `{…}收款比例运营人员` | Colab 4.1.2 / 4.1.3 |

输入：**核算定稿 xlsx**（`export_colab_period.py` 的 `核算行` sheet）。运营渠道表 20260521 布局第 3 列即账号（表头可能不是「渠道账号」字面）。

## 相关

- Colab 调研：`sellfox_settlement/docs/research/saihu-amazon-settlement-autofetch-2026-09-09.md` §1
- txt 命名：`docs/solutions/conventions/amazon-period-file-reconcile.md`
- Phase3 写表 id：`docs/solutions/integration-issues/amazon-period-phase3-gsheet-not-colab-id.md`
- 定稿 `keep_approval`：`docs/solutions/workflow-issues/amazon-period-colab-export-keep-approval.md`
- 下游 Phase3 Colab：`钉钉OA收款费用Amazon多平台&附加费&Tax 20250704.ipynb`
