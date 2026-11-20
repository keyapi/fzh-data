---
okf: v0.1
type: Handoff
title: Amazon 账期 txt Tax 管道（本地）
description: 替代 Colab「税账期TXT 挂载Gdrive」Tax 主线 + Phase2 探索 sheet/FBA；读 NAS 同步桶、汇率 gsheet、出 Excel + Tax worksheet
tags: [amazon, tax, txt, colab, gsheet, nas]
timestamp: 2026-11-20
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
- **tab 修复缓存**：`{桶的父目录}/.repair_cache_{桶名}`（**不写在桶内**；桶内目录会被当人名夹扫描。可用 `--repair-dir` 覆盖）
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
| 币种写法 | 原样精确匹配 | `normalize_currency_label`（去零宽/全角转半角）+ `find_unmatched_currency` 告警 |

> 币种是**精确字符串 join**：OA 表单里 `匈牙利福林（HUF）` 曾带 U+200C 与全角括号，导致币种/汇率为空、人民币全 0。新增币种写法先过 `normalize_currency_label`；跑完看 `warnings` 里有没有「币种未匹配汇率」。
> 重跑历史期前先比对「输入定稿 vs 现有原始表」的审批编号多集，后补单据（如 202610 的 11-05 WM 行）不在旧定稿里。
> **附件 schema**：Amazon 结算有 V2（`amount-type/amount-description`）、V1（`price-type/price-amount` 族）和 XML。V1 由 `_normalize_v1_schema` 展开；XML 不直接入口，请提交人改下 **Flat File**。补交 V2 时必须把旧 V1 移出桶，否则双算。
> **源定稿可能有错数/错账号**：生产用 `remediation/20261119/corrected/*.corrected.v1.xlsx`（凭据 `corrections.v1.json`，原件保留）；写表前门禁与 run manifest 在 `phase3_merge.run_phase3`。人民币表已含 `应收金额_人民币/销售额_人民币`。

## 命令

```powershell
cd d:\Work\赛狐\Cursor
uv run python amazon_period_tax/scripts/run_period_tax.py --bucket 账期20261004-20261103 --exchange-month 202610 --dry-run
uv run python amazon_period_tax/scripts/run_period_tax.py --bucket 账期20261004-20261103 --exchange-month 202610 `
  --write-gsheet --sort-gsheet-tabs --upload-nas `
  --out-dir "D:\Work\王忠于\成本核算\dingtalk_oa_approval_data\reports\tax_txt"
# 仅 Tax 三 sheet：加 --phase1-only
```

汇率必须用 `load_exchange_rate_table` 的**第一张**（每个收款币种一行）。别名拆开表按 `收款币种` 合并会把 Tax 乘多遍。见 `docs/solutions/integration-issues/amazon-period-tax-fx-alias-multiplies.md`。

自己重跑只改 `--bucket` / `--exchange-month`。脚本不补 txt；渠道别名读 `channel_account_sync/out/channel_account_gsheet.json` 快照，不是现读 Google 表。见 `docs/solutions/workflow-issues/amazon-period-tax-rerun-without-agent.md`。

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

### FBA 两张表与写表开关（2026-11-19）

`run_phase3` 现在用本地 FBA 管道（结算 txt + `账期FBA费用特例` 规则）生成
`{期}FBA费用扣减后分类汇总` 与 `{期}FBA费用扣减后收款比例运营人员`，**默认只算不写**：

```powershell
# 只算：报告里看 fba_summary_rows / fba_staff_rows / fba_source
uv run python amazon_period_tax/scripts/run_period_phase3.py --in <定稿.xlsx> --bucket 账期... --exchange-month 202610 --dry-run
# 确认后才写这两张表
uv run python amazon_period_tax/scripts/run_period_phase3.py --in <定稿.xlsx> --bucket 账期... --exchange-month 202610 --write-gsheet-fba
```

不给 `--bucket-dir` 时默认 `LOCAL_NAS_PERIOD_ROOT/<bucket>`；目录不存在则退回读表内现有分类汇总。

### 硬关卡与 strict

```powershell
uv run python amazon_period_tax/scripts/verify_period.py --bucket 账期20261004-20261103
uv run python amazon_period_tax/scripts/run_period_tax.py --bucket ... --exchange-month 202610 --dry-run --strict
uv run python amazon_period_tax/scripts/run_period_phase3.py ... --dry-run --strict
```

`verify_period.py` 只读核对 Tax{YYYYMM} 与 Phase3 五张表（合计、账号集合、缺汇率、未匹配、
行级 vs 分组合计），任一项 FAIL 非 0 退出。`--strict` 让 Tax/Phase3 在
`SKIP-DUP` / 读失败 / 行数对不上 / 未匹配渠道账号 / 币种未匹配汇率时非 0。
写表用 `RAW`：`审批编号` 等 ID 列强制文本，数字保留原生类型。


## T2 runtime 加固 R1–R4（2026-11-20，T2 仍关闭）

> 只改代码与测试，未写任何 GSheet/NAS/Excel；生产 11-19 已验收结果未重写。
> 依据：仓库外 `reports/next_steps_20261120.md` §2；实施报告 `reports/t2_hardening_20261120.md`。

| 单元 | 行为 | 落点 |
|------|------|------|
| **R1 人民币预算** | 单条/批次上限按 **CNY**：原币差 × 已确认目标月 FX；纯文本（账号/日期/币种）修正按 `affected_amount` 计价，不能为 0；同期间+同源版本历史累加（`prior_runs`），每条取绝对值（正负不抵消），防拆 run；缺 FX/币种未确认 → 阻断（writer=0） | `correction_policy.{FxTable,load_fx_table,resolve_impact_budget,cumulative_prior_impact,evaluate_batch}` |
| **R2 授权链与入口** | `approved` 必须绑定 proposal hash / 授权依据 / 角色 / 时间 / scope（`authorization` 对象）；硬身份/有效期/期间检查先于批准捷径；三个写入口强制声明 policy + corrections + fx | `correction_policy.authorization_receipt_problems`；`scripts/{apply_remediation,run_period_phase3,run_period_tax}.py` |
| **R3 PREPARED/回读** | 首个 clear 前保存目标全集快照、write_set、输入/输出预期、权限探针、恢复方案；逐表完整回读 → `published`；失败 `partial` 且停后续批次；外部并发改动时恢复 `attempts=0` | `publish_guard.{prepare_publish,publish_prepared,recover_prepared}`；`phase3_gsheet.Phase3GsheetGateway`；`gsheet_tax.TaxGsheetGateway` |
| **R4 hash 失效/幂等** | 写入口用**当前**政策重判已存授权（旧 `auto_allowed` 遇 T2=false 拒绝）；`stale_pass_problems` 比对 fx/dependencies/目标基线；`idempotent=True` 让同一 correction 重复运行经济应用=1 | `correction_policy.write_gate_errors`、`remediation.apply_corrections` |

**正式发布命令（三个开关缺一不可）**：

```powershell
uv run python amazon_period_tax/scripts/run_period_phase3.py --in <定稿.xlsx> --bucket 账期... --exchange-month 202611 `
  --correction-policy <policy.json> --corrections <corrections.json> --fx <fx.json> `
  --prior-manifest <上次 manifest.json> --write-gsheet
uv run python amazon_period_tax/scripts/run_period_tax.py --bucket 账期... --exchange-month 202611 `
  --correction-policy <policy.json> --corrections <corrections.json> --fx <fx.json> --write-gsheet
uv run python amazon_period_tax/scripts/apply_remediation.py --corrections <c.json> --period 202611 `
  --in <原件.xlsx> --out <corrected.xlsx> --evidence-root <附件目录> --policy <policy.json> --fx <fx.json> [--idempotent]
```

FX 文件格式（JSON 或 CSV，月份必须等于目标账期月）：

```json
{"month": "202611", "rates": {"USD": "7.12", "EUR": "7.80", "SEK": "0.72"}}
```

> **没有「修正也要空跑」的旁路**：`--corrections` 可以是该期空清单，但必须与
> `--prior-manifest` 的输入 hash 一致，否则按「空 proposal 但输入与批准源不符」拒绝。
> 不带政策/FX 只能 `--dry-run`；Phase3 的目标快照 `.prepared.json` 在首个 clear 前落盘，
> `partial` 时 manifest 绝不写 `published`。

## 相关

- Colab 调研：`sellfox_settlement/docs/research/saihu-amazon-settlement-autofetch-2026-09-09.md` §1- txt 命名：`docs/solutions/conventions/amazon-period-file-reconcile.md`
- Phase3 写表 id：`docs/solutions/integration-issues/amazon-period-phase3-gsheet-not-colab-id.md`
- 定稿 `keep_approval`：`docs/solutions/workflow-issues/amazon-period-colab-export-keep-approval.md`
- Tax 汇率别名：`docs/solutions/integration-issues/amazon-period-tax-fx-alias-multiplies.md`
- 币种全角/零宽字符：`docs/solutions/integration-issues/amazon-period-fx-currency-label-invisible-chars.md`
- 自己重跑 Tax：`docs/solutions/workflow-issues/amazon-period-tax-rerun-without-agent.md`
- 管道审计修复（去重/FBA 过滤/Tax 别名/RAW/verify）：`docs/solutions/workflow-issues/amazon-period-pipeline-audit-fixes.md`
- 跨桶错放/结算号台账：`docs/solutions/workflow-issues/amazon-period-cross-bucket-attachment-misfile.md`
- 源定稿修正与写前门禁：`docs/solutions/workflow-issues/amazon-period-source-corrections-and-e2e-gate.md`
- 结算报告 V1/V2 与 XML：`docs/solutions/integration-issues/amazon-settlement-v1-v2-flatfile.md`
- 钉钉 aflow 导出 UI 漂移：`docs/solutions/developer-experience/dingtalk-aflow-export-ui-drift.md`
- 下游 Phase3 Colab：`钉钉OA收款费用Amazon多平台&附加费&Tax 20250704.ipynb`
