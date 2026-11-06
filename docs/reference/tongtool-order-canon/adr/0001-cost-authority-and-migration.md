---
okf: v0.1
type: Decision
title: ADR-0001 通途订单成本权威口径与五链路迁移
date: 2026-11-06
status: accepted
module: tongtool_order_cost
tags: [adr, tongtool, cost, authority, migration]
---

# ADR-0001 通途订单成本权威口径与五链路迁移

## 背景

同一通途订单在五条链路会得到不同成本（2026-11-06 审计，C2）：

| 链路 | 角色 | 后缀处理现状 |
|---|---|---|
| OS `order_sync` | EN 自动写订单行 `sx_shipping_cost`/`first_freight`，影响毛利 | `-FOAM` 成品档判错列、不乘拆单系数、不 clamp |
| CR `tongtool_cost_review` | EN 人工成本复核导入 | 后缀分支正确、乘系数、`max(0)` |
| DN `doc_event` | 销售出库写 `custom_valuation_rate` | 不认后缀 |
| DNF `delivery_note_filling_cost` | 送货单成本展示 | 不认后缀 |
| LOCAL `tongtu_cost_engine` | 本地引擎 | 按 38 矩阵；合并组不套后缀；FBA 绕过；负值阻断 |

拆单系数在 OS 恒为 1（`Tongtool Order Item` 无 `warehouse_name`，DB 已证实），CR 生效。

## 决定

1. **权威=本地 38 矩阵**（`03-price-matrix.md` + `rules.yaml`），作为唯一「应然口径」，由本 ADR 冻结。
   - 理由：它覆盖订单身份、分组合并、后缀、FBA、单位/数量口径，规则可测试、可审计；OS 不能因为「自动运行」就自动成为权威。
2. **OS 与 CR 完全对齐**到该矩阵：
   - OS 优先修（自动写单、影响毛利）：`-FOAM` 取列、拆单系数、负值策略、FBA 分支。
   - CR 不再独立解释规则，只做同一矩阵的 EN 复核入口。
3. **DN / DNF 只读复用权威成本**，不再各自计算：
   - DN 保留 `custom_valuation_rate` 输出字段差异，并标注用途。
   - DNF 仅负责送货单展示，不引入独立口径。
4. **FBA 判据统一为 `Tongtu Shipping Warehouse.warehouse_classification`**（C3），其余关键字/`order_type` 判据降为辅助或删除。

## 迁移顺序

1. ADR + `rules.yaml` 冻结（本文件）。
2. 本地 golden tests：每条 canon 规则至少一个断言。
3. OS 双跑修复：保留差异表与回滚点。
4. CR 对齐。
5. DN / DNF 改为只读复用。
6. 月度回放验收（202608/202609 + 历史月）。

## 风险

- OS 修正后，当前/历史毛利与系数会发生批量变化。**必须**保留逐月差异表、写前备份与可回滚点；先双跑、后切换。
- 拆单系数改为生效后，拆单订单成本会上升；需与财务确认口径生效月份（建议新月份生效，历史月不回写）。

## 后果

- 五条链路不再各自定义成本；规范与实现不一致时，按 `07-conflicts.md` 的流程落到「改代码」或「改规范」二选一。
- 任何口径变更必须：改 `rules.yaml` + 新增/更新 ADR + 更新 `log.md`。
