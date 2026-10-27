---
okf: v0.1
type: Reference
title: 刷新预测输入（forecast-20261027-r2）
description: CURRENT 版本校验、窗口 p50 换桶规则、预测资格与去向
tags: [forecast, demand, netting, qualification]
date: 2026-10-27
status: implemented
---

# 刷新预测输入

入口：`supply_netting.forecast`。预测产物在
`D:/Work/fzh-order-store/en-demand-v1/forecast/`，`CURRENT` 指向唯一生效 run。

## 1. 版本契约

| 检查 | 行为 |
|---|---|
| `CURRENT` 存在且非空 | 否则 `ForecastContractError` |
| `CURRENT == manifest.run_id` | 否则报错 |
| `schema_version == en-demand-forecast-v1` | 否则报错 |
| CLI `--forecast-run-id` 与 CURRENT 一致 | 不一致报错，静默换版本被禁止 |
| 窗口表必需列 | 缺列报错 |

manifest 至少记录：run_id、manifest/窗口文件 sha256、decision_date、data_cutoff、
窗口起止、lead_days、使用/排除行数、预测总量、摊分规则、预测代码 commit。

## 2. 资格：预测 ≠ 需求净额

- 预测用自己的 `netting_eligible` + `netting_block_reason`；
- 需求净额用 `demand_netting.netting_allowed`；
- **两套字段不互相替代**：通过预测资格不等于通过需求净额资格，反之亦然。
- 预测是 `tongtool_sku × canonical_warehouse` 口径；进净额前还要过唯一 `sku_map`
  映射与已证 UOM，否则留证。

## 3. 换桶规则

窗口 `p50` 在 `window_start..window_end` 的天数上均摊，每个桶只拿重叠天数：

```
daily = p50 / (window_end - window_start).days
bucket_qty = daily × 桶与窗口的重叠天数
```

视界外的天数不提前摊、不丢弃也不记 0。规则写进 manifest 的 `allocation_rule`。

## 4. 去向

| 去向 | 原因 |
|---|---|
| 计入 | 资格通过 + 身份唯一 + UOM 已证 + p50 有效 |
| `forecast_netting_ineligible` | 预测资格未通过（附 block reason） |
| `forecast_quantity_unproven` | p50 缺失/负值（多为 `no_recent_sales` 仓库摊分） |
| `forecast_identity_unproven` | 通途 SKU 未映射或一对多 |
| `forecast_uom_unproven` | 预测单位未知 |
| `forecast_window_unproven` | 窗口日期缺失或非法 |
| `forecast_overlap_with_actuals` | 同键已有实际订单覆盖该窗口；实际优先 |
| `forecast_zero` | p50 = 0（合法零需求，不产生行） |

## 5. 与历史需求的关系

历史需求（`demand_netting`）仍决定过去与「有实际订单」的部分；预测只补未来。
两者在逐桶明细里分列：`forecast_demand` / `historical_demand`。
若实际订单日期落入预测窗口，该键的预测整体留证（`forecast_overlap_with_actuals`），
绝不叠加。
