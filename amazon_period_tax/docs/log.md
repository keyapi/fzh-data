---
okf: v0.1
type: Log
title: amazon_period_tax 变更日志
---

# log

## 2026-11-20

- **T2 runtime 加固 R1–R4（只改代码/测试，未写任何表；T2 仍关闭）**：
  - **R1 人民币预算**：`correction_policy` 新增 `FxTable` / `load_fx_table` / `resolve_impact_budget`；
    单条与批次上限改按 **CNY** 判定（原币差 × 已确认目标月 FX）；纯文本（账号/日期/币种）
    修正按 `affected_amount`（受影响金额规模）计价，缺该字段直接阻断而不是按 0 通过；
    批次按 `abs(impact_cny)` 累加并叠加同期间/同源版本历史（`prior_runs`），正负不抵消、防拆 run。
  - **R2 授权链**：新增 `authorization_receipt_problems`——`approved` 必须带
    `authorization{proposal_hash, authority_ref, role, decided_by, decided_at, scope}`，
    绑定当前 proposal hash；硬身份/有效期/期间检查前置于任何批准捷径。三个正式写入口
    （`apply_remediation.py`、`run_period_phase3.py`、`run_period_tax.py`）强制声明
    `--correction-policy` + `--corrections` + `--fx`。
  - **R3 PREPARED/回读**：新增 `publish_guard.py`——首个 clear 前保存目标全集快照、write_set、
    输入/输出预期、权限探针与恢复方案；逐表完整回读，失败即 `partial` 并停后续批次；
    `recover_prepared` 在检测到外部并发改动时 `attempts=0` 并拒绝恢复。
  - **R4 hash 失效与幂等**：`write_gate_errors` 用**当前**政策重判已存授权（旧 `auto_allowed`
    遇 T2=false 必须失效）；`stale_pass_problems` 增加 fx/dependencies/目标基线比对；
    `apply_corrections(idempotent=True)` 让同一 correction 重复运行经济应用次数=1。
  - 测试：`amazon_period_tax` 399 → **464 passed**（新增 65 个边界/失败场景，0 回归）。
  - 报告：仓库外 `reports/t2_hardening_20261120.md`。

## 2026-11-19

- **E2E 修正与落表**：独立复核发现 7 月 `AMZJohnaSE` 金额 100 倍、4 条账号错归属、7 月 FBA 旧基数、10 月 3 份 V1 附件漏 Tax/FBA。新增 `remediation.py`（凭据 + corrected 副本）、V1 schema 解析、人民币表补 `应收/销售` 两列、写前硬门禁与 run manifest（Phase3 + Tax）。四期已重写并通过 verify；独立终审 ACCEPT。详见两篇新经验文档。
- **第二轮修复（Codex 复核 REJECT 后）**：跨期错放拦截（解析 `settlement-id`+内部区间，`OUT-OF-PERIOD` 默认排除）、跨桶 `settlement_ledger`、Tax/附加费缺列硬失败、桶月/汇率月一致、附加费别名（BasePPPL→BASEPPPL）、FBA 分摊守恒、merge 唯一性、日期合法性、审批中占比报告。测试 100 passed。未写任何表。
- **审计修复（15 项，只改代码/测试，未写表）**：
  - `read_amz_txt`：按内容 md5 去重（`SKIP-DUP`）、修复缓存移出桶外（`{桶父目录}/.repair_cache_{桶}`）、
    跳过 `.` 开头目录、逐文件行数对账（`FAIL rows-mismatch`）、`stats_out` 对账数字。
  - `fba_adjust`：过滤键修复（`rule.get(column, "")`，不再回取已改名的 `平台SKU`），空白无关匹配。
  - `phase3_merge`：原始表补 `渠道账号正确提交次数`；`收款比例运营人员` 列序与 Colab 一致
    （比例列插源列右侧、销售额_人民币 紧跟运营人员、去掉多余的收款费用累加人民币）；
    Tax 别名→规范账号（大写 + 别名表 + 快照兜底）；
    新增 `build_fba_summary` / `build_fba_staff`（Colab 39-47），`--write-gsheet-fba` 才写。
  - `phase3_gsheet`：写表改 `RAW`，ID 列强制文本、数字保留原生类型（格式不被破坏）。
  - `tax_aggregate`：汇率 join 两侧 `normalize_currency_label`。
  - 新增 `scripts/verify_period.py` 硬关卡；`run_period_tax` / `run_period_phase3` 加 `--strict`。
  - 实测：8 月 Tax 去重后 394,668.06（旧表 396,601.69，多算 1,933.63）；FBA 调整前-后
    旧算法多扣 68,340.24；本地 FBA 两张表与 202608 现表逐行一致。
- 详见 `docs/solutions/workflow-issues/amazon-period-pipeline-audit-fixes.md` 与仓库外
  `reports/fixes_report_20261119.md`。**需写表的数据动作未执行**。

## 2026-11-19

- **修复**: 币种字符串先归一化（去零宽/格式字符、NFKC 全角转半角）再和汇率表 join；新增 `find_unmatched_currency()` 对「外币有值但汇率为空」告警。根因：OA 表单币种选项 `匈牙利福林（HUF）` 带 U+200C + 全角括号。
- **回填**: `20260704-20260803`、`20261004-20261103` 两期 AllegroHU 相关单元格（汇总/原始/人民币/收款比例×2）逐格回填并复读校验，未整表重写。

## 2026-11-11

- **修复**: Tax 汇率合并改用每个收款币种一行，`enrich_with_fx` 按收款币种去重。重写 `Tax202608` 396,601.69、`Tax202609` 292,240.89、`Tax202610` 192,773.60。

## 2026-11-09

- **新增**: Phase3 本地 `run_period_phase3.py` / `phase3_merge.py` / `phase3_gsheet.py`；`PHASE3_SPREADSHEET_ID` 纠正为 Google 表 id（非 Colab notebook）。
- **验证**: 202608–202610 Tax + Phase3 五 worksheet 写回；WFUK 渠道别名对账。

## 2026-11-04

- 新建子项目：Colab「税账期TXT 挂载Gdrive」Tax 主线本地移植（read + df6 + gsheet + 可选 NAS 上传 xlsx）。
