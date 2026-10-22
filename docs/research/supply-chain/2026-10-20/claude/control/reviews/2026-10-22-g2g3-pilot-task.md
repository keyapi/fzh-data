---
okf: v0.1
type: Plan
title: G2+G3 窄范围供需与补货决策报告 V0（只读试点）
date: 2026-10-22
owner: claude-worker
---

# G2+G3 窄范围供需与补货决策报告 V0

## 决策依据

codex2 已放行（decision7）：不等 Jack 在途、不等每日历史、不等 28 项裁决；
先交窄范围可检查的业务版本，不输出可直接下单的结论。

## 范围

- 限 EN 链完整的 **10 个 SKU**（phase1 已验收：C1/C2/C3 完整）。
- 仅纳入身份明确、库存可对账者；身份不明者排除并列出销量占比。
- 销量截止 2026-09-30；库存取 10-21/22 最新；单据截止 2026-10-22 12:40。

## 数据（只读）

`D:/Work/fzh-order-store/order_store.duckdb`：
`gs_orders`、`fba_demand`、`sku_map`、`stock_latest`、`stock_history`、
`tongtool_po_open`、`replenishment_v3`、`bom`/`bom_item`、`three_pl_stock`；
EN 单据证据：`out/dn_wo_jc_se_expand10_phase1/association_manifest.json`（10 SKU 的 SO/DN/WO/SE）。

## 预测（G2）

- 未来 3 个月；基准 seasonal naive，候选 ETS；输出 P50/P90。
- 回测最近 6 个起点，评 1/3 月 WAPE、bias、P90 覆盖率；禁止泄漏。
- 全零不参与 WAPE；历史 <24 月标低置信，退化为近 3 月均值，不声称季节性。
- 断货删失：当前 3 天库存不足以校正，明确标“未校正”，不假装已处理。

## 补货（G3）

- 净供给 = 可用库存 + 去重未结 PO + 未包含于 PO 的在产 + 独立在途。
- 需求 = 预测 + 已开未发 SO；DN/SE 只用于核销，禁止重复加减。
- 情景 A：无在途、PO 不计到货；情景 B：仅 PO 按假设在提前期内到货。
- ETA 空不得视为及时到货；提前期 60/90/120 天、复核 30 天、服务水平 90%。
- ROP = 提前期需求 P90；建议量 = max(0, P90(提前期+30天) − 同期净供给)。
- 包装倍数未验则输出未取整量；不输出可直接下单的结论。

## 映射与 unknown

- 同物料且可互换者聚合；身份不明/单位不明者排除 G3，保留销量与原因。
- Cover 可替代未证：单列情景，不并入主建议。
- 所有未知项分开展示：已确认库存 / 数量已知但到货时间未知 / 单位或身份不明。

## 交付

1. **60 分钟内**：2 个代表 SKU 的端到端样例（历史需求、预测、库存、PO/生产、情景、证据链接）。
2. 今日内：10 个 SKU 的完整 V0 报告 + 证据 JSON。
- `control/reviews/2026-10-22-supply-demand-replenishment-v0.md`
- `out/replenishment_v0/evidence.json`（聚合，不含原始订单行）
- 产出提交固定 commit；不访问生产、不下单、不扩样、不合并 PR。

## 验收

- 入 N 行 → 出 M 行，差数逐项解释；库存/PO/生产不重复加减。
- 回测无泄漏；低置信显式；P50/P90 可复算。
- 每个数字可追溯到表/字段/查询；unknown 不写 0。
- Codex1 复审：先审样例与供给去重，再审回测与建议。
