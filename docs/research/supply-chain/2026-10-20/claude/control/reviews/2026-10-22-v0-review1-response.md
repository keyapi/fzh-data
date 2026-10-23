---
okf: v0.1
type: Review
title: G2+G3 V0 对 Codex1 review1 的修复响应
date: 2026-10-22
owner: claude-worker
reviewed_commit: 7c1102d4
verdict: fixed_pending_review
---

# G2+G3 V0 对 Codex1 review1 的修复响应

> 本文件逐条回应 `2026-10-22-v0-review1.md`（reviewed commit `7c1102d4`）。
> 修复提交是本文件所在 commit；产品/证据路径不变：
> `control/reviews/2026-10-22-sample-2sku.md`、
> `control/reviews/2026-10-22-supply-demand-replenishment-v0.md`、
> `out/replenishment_v0/evidence.json`。

## 逐条处理

| # | Review finding | 本版修复 | 复算证据 |
|---:|---|---|---|
| 1 | Blocking：其他 SO 的超发冲抵了正向未发（White 26→20，Natural-194 631→615；合计 2,924 vs 2,017） | `open_so.live_open` 改为**逐行正向余额求和**；超发 -907 单列、不冲抵；净额 2,017 只作对照。 | `evidence.json` 每 SKU `open_so.positive_open / negative_over_delivery / live_open_net`；聚合 `open_so_live_total=2924`、`negative_over_delivery_total=-907` |
| 2 | Blocking：等量扣 PO、max(WO−PO,0) 只是重叠假设，不能叫“已去重” | 不再发单点。A：`available`→`available+在产`；B：`available+max(原始PO,在产,在途)`（最大重叠）→`available+原始PO+全部在产+在途`（完全不重叠）；PO 重复候选只作单独敏感性（去重口径 3,680–5,573）。 | 每 SKU `supply.A_low/A_high/B_min/B_max/B_mid_intransit_in_po/B_min_po_dedup/B_max_po_dedup`；聚合 A 1,015–3,205、B 3,953–5,854 |
| 3 | Major：提前期需求与 10-22 库存时点、季节路径脱节 | 固定决定时点 `2026-10-22`；ROP/建议量按 `[10-22, 10-22+horizon]` 日历窗口积分月度预测（10 月剩余 10/31；11/12 月按整月；1 月以后用 3 月均率外推）。SO/WO 10-20/21 与库存 10-22 的 1–2 天差**未桥接**，单列时点情景。 | 每 SKU `lead_time.L*/buckets` 有逐月权重；报告 §5 注 |
| 4 | Major：月度 P90 按 √h、累计按 √3，不一致；且覆盖率 70% 未校准 | 统一随机游走：月 h 方差 `h·σ²`，3 月累计 `√6`；σ 用全部可用滚动起点一步误差校准（`σ_used=max(σ_train, σ_roll)`）；`target_service_level=0.90` 与回测实现覆盖率分开记录；覆盖率不足即标 estimate，不承诺 90%。 | 每 SKU `forecast.p90_3m` 可复算；`backtest.calibration`；聚合覆盖 88.3% / 80.0% |
| 5 | Minor：零需求单元被剔除 | 指标保留全部单元；只有全零分母使 WAPE/bias 为空；覆盖率也含零单元。本轮零需求单元为 0，指标数值不变。 | `metrics()`；`zero_actual_cells` 字段；报告“零需求单元（保留）”列 |

## 修复后的关键数字

- 正向 live SO **2,924**（原净额 2,017；差 907 = 超发绝对值）；死单 1,675 未计。
- 3 月 P50 **1,457** / P90 **4,811**（逐 SKU 相加，非组合 P90）。
- 供给：available **1,015**；PO 原始 **1,465** / 去重 **1,184**；在产剩余 **2,190**；
  A 边界 **1,015–3,205**；B 边界 **3,953–5,854**（B_min 最大重叠 / B_max 完全不重叠）；PO 去重敏感性 3,680–5,573；B 中间情景 3,953。
- 回测：1 月 WAPE **60.5%**、3 月 **52.6%**；P90 覆盖 **88.3% / 80.0%**（目标 0.90；σ 已用滚动起点校准，但实现覆盖率仍不足，P90 标 estimate，不承诺 90%）。
- 决定时点 2026-10-22；窗口 60/90/120 天 + 30 天复核，逐 SKU 区间见报告 §5。

## 仍未关闭（不是本次修复能证明的）

1. PO↔在产、PO↔在途的逐笔关联键不存在；本轮只发边界，不发单点。
2. 13 行未结 PO 的 `will_arrive_date` 全空；B 的“提前期内到货”是假设。
3. 在产 WO 的 `planned_end_date` 全空；PK# 皮壳→KS 成品 1:1 未证；ND# 内胆可用性未建模。
4. 库存 UOM=unknown；Cover 可替代未证；断货删失未校正（仅 3 天库存历史）。
5. `gs_orders` 无状态字段，取消/退货未剔除；SO/WO 10-20/21 与库存 10-22 的 1–2 天差未桥接。
6. P90 覆盖率 80%（3 月）< 90%；σ 已用滚动起点校准，但仍标 estimate，不承诺 90%。

## 复审建议

先看 2-SKU 样例与 `supply` 边界字段；再复算 `open_so.positive_open`、`forecast.p90_3m`、
`lead_time` 窗口权重。若接受“边界 + 未知单列”的口径，可进入下一轮；若要求 PO↔在产逐笔证据，
需业务/系统提供单据键，属外部输入，不是本脚本可补。
