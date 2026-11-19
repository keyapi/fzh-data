---
okf: v0.1
type: Log
title: amazon_period_tax 变更日志
---

# log

## 2026-11-19

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
