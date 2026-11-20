---
okf: v0.1
type: Reference
title: 通途订单 E2E 门禁：把静默 fallback 变成可解释的失败
description: 从 GS 源表到成本写回的逐步骤审计；汇率/仓库/渠道/FBA 国家/空键/非有限值/输入哈希/回读等门禁设计
date: 2026-11-18
category: best-practices
module: tongtool_order_cost
problem_type: best_practice
component: tooling
severity: high
applies_when:
  - "数据管道出现缺失/异常但仍继续产出"
  - "加入新输入源或新 join/merge 时需要决定哪些情况必须 fail"
  - "财务/运营质疑成本表为何某些行成本为 0"
tags: [tongtool, data-quality, gates, fail-closed, join, silent-failure]
related_components: [tongtool_order_cost]
---

# 通途订单 E2E 门禁：把静默 fallback 变成可解释的失败

## Context

通途订单成本链路（GS 源表 → 特殊订单 → EN 解析/拆单合并 → BOM 成本 → self/FBA/merged → GS 写回）里，多次出现“数据缺失但流程继续”的问题：

- 汇率缺失按隐含汇率或 `or 1.0` 继续；
- 仓库模糊匹配取第一个候选；
- 渠道账号别名缺失（如 `WFDANEEYUS` vs `WFUS-Daneey`）无人报错；
- FBA 站点无法识别国家时默认按欧洲 FBA 算；
- 皮壳商品目的地 BOM 缺失，二次加工=0 仍标记 ok；
- GS 写回只打印回读差异，仍可能继续写下一张表。

这些问题不一定立刻让总额异常，但会在后续运营/财务口径中静默丢数。

## Guidance

### 必须 fail（输入/映射）

- 汇率文件：必须唯一、有限、>0；重复不一致/0/负/缺失 → fail；
- 发货仓库：精确或模糊匹配必须唯一；多候选按未映射 fail，禁止取 first；
- 渠道账号：空值 fail（别名/运营人员关系应在渠道账号主数据侧另行 fail-closed）；
- FBA 国家：GS 站点/EN FBA 仓无法识别国家 → fail，不能默认 EUFBA；
- 关键业务键：`订单号`、`通途SKU` 空值 fail；数值非有限（Inf/NaN/不可解析）fail；
- 特殊订单清单：写回时必须有；`order_flags` 缺失禁止写回。

### 必须 fail（产物/写回）

- Phase1/Phase2 的 fail 断言汇总进最终结果，不能只看最终公式自洽；
- `gs_full_replace` apply 要求 manifest 存在、月份一致、无 fail 断言；
- 待写 CSV 的 sha256 必须匹配 manifest `outputs_sha256`；构建输入（raw/EN/ref/flags/BOM/仓库/汇率/特殊订单）必须匹配 `inputs_sha256`；
- self/FBA 键集合漂移默认 fail（人工确认才 `--allow-key-drift`）；
- 回读错误返回非零并停止后续表；备份目录可用于人工恢复。

### 只报告 / 人工确认后放行

- 同包裹合法重复明细（订单号+SKU+包裹号）只报告，不去重；
- 皮壳非组件行“有成本但目的地加工=0” → warn；确认后把 `item_fg` 加入 `config/known_zero_processing_allowlist.csv`；
- 零售价异常告警，不普遍阻断（退货/补发/赠品可能合法）；
- merged 78 键级 95↔78、self/FBA 互斥：同账号同 SKU 可合法并存，保留总计对账；
- 旧写回兜底只在同键值冲突且影响金额时报告。

## Why This Matters

- 静默 fallback 会把“缺失”伪装成“零成本/正常值”，后续很难追；
- 成本表一旦写回，下游（特殊规则、透视表、定价）会继续消费；
- 显式 fail/warn 让人能在写回前决定补数据、登记别名或确认业务口径。

## When to Apply

- 新增输入源、join/merge、映射表；
- 月度运行前检查门禁输出；
- 财务/运营发现“某些行成本为 0”时先看 warn/审计清单，而不是直接改数。

## Examples

- USTX 系数：只写 `二次加工成本系数`，`*系数` 列派生；基数列不动；
- FBA 未知国家：`FBA 国家识别=0` fail，避免默认欧洲 FBA 成本；
- GS 写回：manifest + 输入/输出哈希 + 回读错误非零，避免半完成状态被当成功。

## Related

- `docs/solutions/architecture-patterns/tongtu-branch-processing-cost-and-coefficients.md`
- `docs/solutions/workflow-issues/tongtu-multicolor-cover-shared-foam-attribution.md`
- `tongtool_order_cost/docs/reference/build-order-tabs.md`
- `tongtool_order_cost/docs/reference/tongtool-order-pipeline.md`
