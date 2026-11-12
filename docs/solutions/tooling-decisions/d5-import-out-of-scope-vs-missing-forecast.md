---
okf: v0.1
type: Reference
title: D5 导入的四分法：接受 / 范围外 / 缺预测 / 非法，不要一律当拒收
date: 2026-11-12
category: docs/solutions/tooling-decisions/
module: demand_collaboration
problem_type: tooling_decision
component: tooling
severity: high
applies_when:
  - "导入 D5/预测表，源里混着范围外仓池、缺预测和非法值"
  - "整批拒绝让合法基准永远生成不了"
  - "需要在报告里保留每一条未入基准的去向"
tags: [d5, import, reconciliation, out-of-scope, missing-forecast, zero-fill]
---

# D5 导入的四分法

## Context

D5 v6.8 共 3,498 行；97 天口径选中 1,749 行。其中 1,513 行可用，185 行是范围外仓池（`CG` / `CG-USNJ` / `CG-USTX` / `其他`），51 行 `point_forecast` 为空。首版适配器把这 236 行都记为 `rejected`，`make_baseline` 只要 `rejected_count > 0` 就整批失败——结果是**真实基准一行也生成不了**，而 185 行根本不是数据错误。

## Guidance

把“未入基准”拆成四类，各走各的路：

| 类别 | 判定 | 是否阻断基准 | 报告 |
|---|---|---|---|
| `accepted` | 在范围内、量值合法 | 否 | 进基准 |
| `out_of_scope` | 池不在本模块三家公司（CG/其他） | **否** | 保留在 `out_of_scope`，仍参与对账 |
| `missing_forecast` | 范围内、`point_forecast` 为空 | **默认阻断**；显式 `--allow-missing-forecast` 才排除 | 保留在 `missing_forecast`，不填 0 |
| `invalid` | 范围内、负数/NaN/重复键/horizon 不一致 | **是** | 保留在 `rejected` |

对账等式：

```
input = selected + skipped
selected = accepted + out_of_scope + missing_forecast + rejected
```

实现要点：

- 先判池，再判 horizon；范围外行的 horizon 异常不应污染 `rejected`。
- `point_forecast is None or str.strip()==""` 才归 `missing_forecast`；`-1` / `"NaN"` 仍是 `invalid`。
- 缺预测**绝不补 0**；显式允许时也只是把该行排除出基准，报告仍保留源行号和原因。
- 报告带源文件 SHA256、`reconciled` 布尔值；转换后 `status` 明确写 `converted_with_missing`。

## Why This Matters

“范围不适配”和“数据缺失”是两种责任、两种处置：前者是模块边界，后者要补数。混成一个 `rejected` 会让合法基准永远生成不了，也会把 185 个边界行误报成 185 个预测错误。四分法让 1,513 行先能上线，同时把 51 行缺数摆在报告里等补。

## When to Apply

- 任何“源表包含多个业务范围 + 空值/非法值”的导入。
- 任何“整批拒绝”策略导致正常数据被少数边界行拖死的场景。
- 不适用于源表已经按目标范围干净的场景（此时保留简单校验即可）。

## Examples

```bash
# 只审计：rejected=0, out_of_scope=185, missing=51, accepted=1513
uv run python -m demand_collaboration.adapter \
  --source D5_v6_8.xlsx --inspect --out <private>

# 严格转换：有缺预测就失败
uv run python -m demand_collaboration.adapter \
  --source D5_v6_8.xlsx --forecast-start 2026-11-02 --as-of 2026-11-11 --out <private>

# 试点：显式排除缺预测，保留去向
uv run python -m demand_collaboration.adapter \
  --source D5_v6_8.xlsx --forecast-start 2026-11-02 --as-of 2026-11-11 \
  --allow-missing-forecast --out <private>
```

## Related

- `demand_collaboration/adapter.py`、`demand_collaboration/docs/implementation.md`
- `architecture-patterns/side-ledger-row-scope-default-deny.md` — 基准只装范围内商品
- `best-practices/scanner-silent-data-loss-guard.md` — 不静默丢数的同族原则
