---
okf: v0.1
type: Reference
title: 消费接口 — 旧 GS 407,898 行 + 10 月 EN 增量
description: en-demand-v1 的快照一致性、双维度分类、拼接/覆盖规则、quarantine 与 manifest
tags: [demand, consumer, gs-orders, en-demand-v1, reference]
date: 2026-10-27
status: verified
---

# 消费接口

## 1. 两段式序列（不要整表替换）

| 时间段 | 来源 | 覆盖口径 |
|---|---|---|
| 发货日 `<= 2026-09-30` | GS 月表（407,898 行 / 400,754 单） | **发货口径**；含自营/3PL/代发多仓 |
| `sale_date >= 2026-10-01` | `en-demand-v1`（EN `Tongtool Order`） | 销售口径，含未发货订单；行级 SKU |

**关键**：GS 的截止是**发货日期**，不是销售日期。所以：

- 9 月下单、10 月发货的订单不在 GS → 由 EN 以 `en_late_legacy` 补入；
- 旧单取消/退款/数量修改 → 由本次增量窗口的 EN 行覆盖 GS（行级），
  GS 原行保留在 `overlap` 里可审计。

固定 `sale_date` 切换本身不足以处理这两类，必须走下面的补洞/覆盖规则。

## 2. 快照一致性（先读 CURRENT）

`D:/Work/fzh-order-store/en-demand-v1/`

```
CURRENT                         # 指向最后一次成功提交的快照
snapshots/<commit_id>/          # 五张表 + commit.json
runs/<run_id>.json              # 每次采集报告
manifest.json                   # 水位、源覆盖、partial 标记
```

- 读取只看 `CURRENT`；指针指向不存在/空目录、缺 `commit.json` 或任一张表
  → `IncompleteSnapshotError`（不会当成空库返回 0 行）。
- 一次消费用 `with store.pinned():` 固定快照目录，orders/lines 不会跨提交混版本。
- 一次采集 `begin(run_id)` → 逐页写同一快照 → `commit(status)`。
  写盘失败 → `abort()`，`CURRENT` 不变，失败批次不会冒充成功。
- 旧版本根目录散文件可用 `python -m self_fulfilled_demand.finalize_store` 收编。

## 3. 两个独立维度

**履约类型** `fulfillment_scope`：`self_fulfilled_candidate` / `fba` /
`third_party_or_dropship` / `unknown`。

**需求有效性** `row_role`：`sale` / `return_adjustment` / `qty_missing` /
`cancelled` / `refunded` / `embedded_component`。

两者分开，所以：

- 代发/unknown 只要有效，仍然**保留**在 `demand_all_non_fba`，
  默认不进主建议时进 `deferred`，并带 `scope_reason`：
  - `third_party_outside_default_scope`
  - `scope_unknown_responsibility_pending`
- 想纳入代发：`build_demand(..., scopes=(SELF, THIRD_PARTY))`，
  `demand` 会包含代发，`scope_reason=included_third_party`；unknown 仍待定。
- FBA 单独进 `fba` 表，既不进主建议也不算 quarantine。

## 4. 返回的帧

```python
from self_fulfilled_demand.consumer import build_demand
frames = build_demand(store_root, gs_path, "2026-09-01", "2026-10-31")
```

| key | 内容 |
|---|---|
| `demand` | 主序列：有效 + scope 在 `scopes` 内 |
| `demand_by_day_sku` | 日期×SKU×需求类型×scope×来源 的总量 |
| `demand_by_day_sku_warehouse` | 再加 `warehouse_name` / `uom` / `uom_status`（补货用） |
| `demand_non_fba` | 所有非 FBA 有效行，带 `in_main_series` / `scope_reason` |
| `deferred` | 有效但不在默认口径（代发/unknown），责任待定 |
| `fba` | FBA 行（含状态），不参与自发货需求 |
| `quarantine` | 非 FBA 的无效行（取消/退款/数量缺失/嵌入组件） |
| `returns` | 负数行（退货调整），单独列出 |
| `date_unknown` | `sale_date` 缺失的行，单列并计入数量对账 |
| `overlap` | GS 全部行 + EN 历史段行的行级对账，含被覆盖行 |
| `summary` | 行数、数量、覆盖/覆盖状态计数 |

## 5. 交叉与覆盖规则

- 交叉键 = `(完整单据名, 通途SKU)`；不按订单号整单覆盖，不按 `base_order_id` 合并。
- GS 行状态：
  - `en_match`：EN 有同行且数量一致（GS 保留，不双计）
  - `en_match_qty_diff`：数量不一致但 EN 不是本次增量（GS 保留，待复核）
  - `superseded_qty_change`：EN 本次增量改了数量 → GS 行不进需求，EN 行进 `en_override`
  - `superseded_cross_cutover`：同订单同 SKU 同量，但 GS 销售日 < 切点 ≤ EN 销售日
    → 同一业务行只算一次，EN 优先，GS 行保留审计
  - `superseded_cancelled`：EN 本次增量取消/退款 → GS 行不进需求，EN 行入 `quarantine`
  - `gs_only_en_gap`：GS 有、EN 无（历史权威，保留）
- EN 历史段行（`sale_date < cutover`）：
  - GS 无对应行 → `en_late_legacy`，补入需求
  - 取消/改量 → `en_override`
  - GS 已有且一致 → 跳过（不双计）
- 只允许 `ingest_scope in (sale_window, modified_window)` 的单据覆盖 GS；
  `validation_sample` 不覆盖。
- 先按业务行身份 `(完整单据名, 通途SKU)` 裁定来源，再看数量/日期：
  同量同业务行绝不因跨日期段而双计。真正同单多行（EN 多 `idx`、GS 多包裹）
  各自保留，只在合计一致时合并为「同一业务行集合」。

## 6. 需求与单位

- 计入 `demand`：有效 + `quantity > 0` + `demand_kind != embedded_component` + scope 匹配。
- `demand_kind`：`finished_good` / `cover` / `semi_finished` / `embedded_component` /
  `unknown`。皮壳/半成品不合成成品需求。
- **单位（UOM）**：订单行没有单位字段，本模块**不猜**；所有行 `uom=null`、
  `uom_status=unknown`、`uom_basis="order_line_has_no_uom; EN Item.stock_uom not joined"`。
  数量按「件」解释，`demand_by_day_sku_warehouse` 已按 SKU×仓×日给出，UOM 待后续
  用 EN `Item.stock_uom` 补全；不确定性不回填 0。
- 数量缺失：`quantity is None` → `quarantine` + `row_role=qty_missing`。
- 负数量 → `returns`。
- 取消：`invalid=1` → `lifecycle_state=cancelled_invalid` → `quarantine`。

## 7. 增量与水位

- 水位：`manifest.watermarks.modified_max`；下次 `modified_since = modified_max - lookback_hours`（默认 72h）。
- 首次窗口：`modified >= 2026-10-01`（27,503）∪ `sale_time >= 2026-10-01`（6,800）。
- `partial`（分页预算耗尽、子表失败、写盘失败、计数审计不符）→ **水位不前移**，
  `manifest.partial=true`，原因写在 `runs/<id>.json.failures`。
- 9 月末交集是抽样（`coverage_status=sample`），只能验证字段/数量一致性。

## 8. GS 输入校验

`load_gs_orders()` 要求以下列存在，缺列直接 `ValueError`，不再静默填 `None`：

`order_id`、`sku_tongtool`、`platform_sku`、`qty`、`sale_date`、`despatch_date`、`warehouse`。

## 9. 已知缺口

1. EN 只有 154,632 单，`creation` 从 2025-12 起回填；9 月以前不要拿 EN 当完整序列。
2. 旧产物 `en_orders.parquet` 只有 2,733 行订单头抽样、无 SKU 明细，不能当 10 月需求。
3. EN 无「行→包裹」映射，一单多包裹无法行级归属。
4. GS 无 `shipping_method`，历史段 `demand_kind=unknown`。
5. 时间均为朴素本地时间，未做时区换算。
6. 本次真实采集由分页/快照修复前的进程启动，完整性必须靠独立计数与离线审计验证，
   不能用修复后的单元测试背书。
