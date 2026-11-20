---
okf: v0.1
type: Reference
title: Phase 4.0 生产写回演练（run 包 + 单月 canary，不写 GS）
description: 固化输入 manifest/hash 与月末/bundle 版本，写入不可变 out/runs/<run_id>/；202608 + USNJ 单仓桶 canary 逐行/逐列 diff、金额分层、写前门禁与写后回读
date: 2026-11-05
module: tongtool_order_cost
tags: [cost, writeback, phase4, canary, run-package, gate, readback]
---

# Phase 4.0 生产写回演练

> 落地：`domain/run_package.py`；CLI `writeback-run`。**只生成本地文件，绝不写 GS/EN。**

## 1. run 包（不可变）

- 输入 manifest/hash：raw 订单、EN 明细、BOM with kits、product_bundles、仓库映射、item_refcode、
  flags、旧写回、kit 报表、branch map。
- 版本：`month_end=2026-08-31`；`bundle_versions`（263 个）；每个输入 sha256/bytes/mtime。
- 输出目录 **`out/runs/<run_id>/`**：`manifest.json`、`audit.log`、`summary.md`、`diff.xlsx`、
  `writeback_canary_<month>_<bucket>.csv`、`readback.json`。
- 门禁：
  - 输入完整性 + 版本锁（缺 `bundle_version` 直接拒绝）；
  - 非空 run 目录拒绝覆盖（先写临时目录再原子改名）；
  - `_written_index.json` 按输入 fingerprint 检测重复写入（同指纹已完成 → 拒绝，除非 `--allow-duplicate`）。
- 只有门禁与回读全部通过才登记为 completed。

## 2. Canary（202608 / USNJ）

- 选 USTX/USNJ 中行数较小者：**USNJ 4,138 行**（USTX 5,465）。
- `writeback_canary_202608_USNJ.csv`：166 列合同 + 血缘/标注列；非商品配件标
  **`cost_status=excluded_non_product`**，四列显式 `0`。
- 旧写回按 `(订单号, 平台SKU_统一, 通途SKU, 同键序号)` 逐行匹配；`diff.xlsx`：
  汇总/行匹配/列差异/金额分层/门禁/回读。
- 金额分层：method（皮壳/半成品/成品）、套件、非商品配件、利润空白。

## 3. 2026-11-05 结果

| 指标 | 202608 / USNJ |
|---|---:|
| canary 行数 | 4,138 |
| 行匹配 / canary_only / old_only | 4,138 / 0 / 0 |
| 皮壳成本 / 头程 / 二次加工 / 绍兴二次 | 242,735.26 / 30,363.86 / 748,411.06 / 801.05 |
| 非商品配件（canary / 全月） | 7 / 14（四列全 0） |
| 利润空白（canary / 全月） | 7 / 17（只写 reason，不填 0） |
| 门禁 | 5/5 pass |
| 写后回读 | 6/6 pass（行数/键唯一/键 hash/四列金额/行 hash/摘要 hash） |

**金额分层（我方 − 旧；层可重叠）**

| 层 | 行数 | 皮壳 | 头程 | 二次 | 绍兴二次 |
|---|---:|---:|---:|---:|---:|
| method:半成品 | 1 | -13.59 | 0 | -0.004 | ~0 |
| method:成品 | 107 | +4,131.25 | 0 | 0 | -6.28 |
| method:皮壳 | 4,023 | -40,674.69 | +107.84 | -169.91 | 0 |
| 非商品配件 | 7 | 0 | 0 | 0 | 0 |
| 利润空白 | 7 | 0 | 0 | 0 | 0 |
| 套件 | 0（USNJ；全月 5 个套件在 USTX） | — | — | — | — |

**成本列差异行数**：皮壳 4,128 / 二次加工 4,024 / 头程 72 / 绍兴二次 12（匹配 4,138）。
`品类`、`订单总成本`、`订单利润`、`sku_base` 等派生/标识列差异为预期（Phase1/2 重新派生），
不代表成本错误。

**run 包**：`out/runs/202608-USNJ-<timestamp>-d1435eeb/`（含 `diff_explain.xlsx` / `diff_explain.md`）

## 4.1 行级差异解释（Phase 4.1）

- 覆盖率 **100%**（未解释 0）；随机 10 行 BOM 手算 **40/40** 列通过。
- 目标解释：

| 目标 | 总差 | 主要原因 |
|---|---:|---|
| 皮壳成本 / method:皮壳 | -40,674.69 | 旧写回陈旧 -20,373.01（50.0%）；BOM 月末版本变化 -19,820.73（48.7%）；旧值含包装口径 -406.38（1.0%）；method 兜底 -74.57（0.2%） |
| 成品皮壳 / method:成品 | +4,131.25 | method 兜底 +4,128.00（99.9%，铁架 TT0312701K0064561）；BOM 月末版本变化 +3.25 |
| 二次加工 / 全部 | -169.91 | 旧写回陈旧 -162.73；其余为 <0.01 舍入残差 |
| 头程运费 / 全部 | +107.84 | 旧写回陈旧 100% |

- `disabled 物料` / `变体映射` 在 USNJ canary 中为 0 行；类别已保留（无差异时显示 0）。
- Top 物料样例：`KS0001-PR-100-WHITE` -2,639.11（旧写回陈旧）、
  `KS0001-CMKTR-100-DEEPBLUE` -2,093.08（BOM 月末版本变化）、
  `ZTGJ5525-SOFALSHAPEDBRACKET-IRON-55x45x45` +4,128.00（method 兜底）。
- 写前要求：覆盖率 100% ≥ 95%，手算 40/40，门禁 5/5、回读 6/6 通过 → **达到写前要求**（仍未写 GS）。

## 4. 约束

- 不写 GS/EN；canary 仅本地 CSV/xlsx/md。
- 非商品配件 `excluded_non_product` 单独对账；利润空白只写原因。
- 任何门禁/回读失败即不登记完成，run 包保留供审计。
