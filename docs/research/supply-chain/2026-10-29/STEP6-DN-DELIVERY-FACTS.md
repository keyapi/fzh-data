---
okf: v0.1
type: Spec
title: 第六步：DN 实际交付事实层（A–E，第二版）
date: 2026-10-30
updated: 2026-10-30
owner: claude-worker
status: implemented locally + test-station read-only scan; scope/integrations pending
scope: read-only; no writes; no auto-linking; no auto-ordering; production not deployed
tags: [supply-chain, delivery-note, actual-delivery, reconciliation]
---

# 第六步：DN 实际交付事实层

## 0. 范围与权威输入（修正）

- 冻结 9-SKU 只是**验收 fixture**，不是业务批准目标全集。
- 正式 scope 必须由 warehouse_restock 注入：`source`、`version`、`hash`、`items`；
  API 校验 hash，导出通过 `--delivery-scope-json` 注入。
- 没有业务 scope 时 relevance 全部 `unknown`，E 阶段 `scope_pending`，不生成补货建议。
- 未列入 scope → `out_of_scope`；缺 item_code → `unknown`；不使用前缀/BOM 扩围。

## A. 真实基线（测试站，2026-10-30 只读）

全部可读 DN（`include_inactive=1`）：

| 项 | 行数 |
|---|---:|
| DN 头 | 345（提交 268 / 草稿 23 / 取消 54；退货 0；amended 16） |
| DN 行 | 1,264（提交 1,038 / 草稿 55 / 取消 171；退货 0；amended 56） |
| linked | 57（提交 10） |
| so_header_only / ambiguous / conflict / restricted | 0 / 0 / 0 / 0 |
| unlinked | 1,207（提交 1,028；有运单 39；PO 代码 0） |
| relevance（无业务 scope） | unknown 1,264；E pending |
| relevance（仅验收 fixture 回归，不算业务结论） | in_scope 9 / out 1,255 |

未关联行按客户只报行数：裁剪部 362、生产车间 259、CENTRADE 178、物流包装部 85、
技术科 103、波兰公司 40、美国FBA仓 1。**不输出跨商品数量总和**。

数量守恒只按 `item×UOM×customer×warehouse×channel` 分组：
`conservation.groups[]` 逐组输出 gross/return/actual/unknown；全局只报行数
（total/submitted/inactive/returns/unknown_quantity），不把 224,972.5 当作业务守恒量。

验收 fixture 下 9 行均来自 `DN-26-00058`，合计实际交付 131（仅 fixture 回归）。

## B. 退货账（修正）

- 支持 ERPNext 负数 qty；保留 `raw_signed_qty` 与 `qty_magnitude=abs(qty)`；
  正数退货与负数退货结果等价。
- 严格校验：`return_against`、`dn_detail`、原单 docstatus=1、item/UOM/customer/warehouse；
  原单草稿/取消/缺失/受限分别留痕，不抵扣。
- 原行 `actual_qty` 保持毛额，退货行 `actual_qty=-匹配量`；净额只扣一次，
  不再“原行净额 + 负向退货”双重抵扣。
- 超退单独 `excess_return_qty`；原单无 SO 时退货保持 unlinked。

## C. 三本账（修正）

- **实际交付账**：`delivery_lines`（毛额 + 已匹配退货负向行，净额一次）。
- **SO 履约账**：`so_fulfillment` 只输出 `so_open_qty` / `unresolved_demand_qty`；
  **不再把 SO 余额当 confirmed additional supply**。
- **补货供应账**：`supply_ledger` 只有 linked fulfilled、unresolved demand、
  unlinked delivery；无独立物理证据时 potential overlap 不转成确定供应。
- `ambiguity_pools` 按 `item×UOM×customer×warehouse×channel` 汇总未关联池，
  只做组级 min(open, pool)，不把池贪心分配给某条 SO 行，结果与输入顺序无关。
- `physical_chain`：多运单 qty=null；PO code_only；receipt/inventory not_integrated。

## D. API / 页面 / 导出（修正）

- `get_delivery_facts(filters, scope)`：父单权限优先，再读子表；
  受限 SO 不泄露名称/明细/计数。
- 筛选/分页同步裁剪 `delivery_lines / association_edges / coverage_exceptions /
  so_fulfillment / ambiguity_pools / supply_ledger / physical_chain` 与 counts；
  `coverage.global` 为全量、`coverage.query` 为当前筛选/页面，聚合标注 `query_page`。
- SO 页面「本 SO 实际交付」只查该 SO；另设「全局实际交付」入口，200 行/页可翻页。
- 导出跨页校验 schema/rule/implementation/scope/as_of/source status/snapshot_id；
  混版本、并发漂移、重复稳定键、写盘失败均不创建 run、不切 latest。

## E. warehouse_restock 适配（修正）

- 必须先通过 snapshot gate：`pagination.exhausted=true`、非 partial、版本齐全、
  scope 已提供且 hash 匹配；否则 `scope_pending` 或拒绝。
- 行粒度：`item×UOM×channel×destination`；同 SKU 双渠道、双 UOM、双仓分行，
  不跨单位/渠道合计。
- 输出 actual/linked/unlinked/unresolved/potential；unknown 不写 0；
  `eligible_for_restock=false`、`auto_order=false`。

## 回归与 pending

已覆盖：负数退货、正负等价、双重抵扣、跨 item/仓/UOM 退货、草稿/取消原单、
缺失/NaN/Infinity、多运单、同 SKU 双渠道、多 SO 顺序不变、筛选聚合隔离、
混版本/快照漂移/重复键/写盘失败、导出分页与 latest 保护、SO 页面范围。

仍 pending：普通受限用户真实 HTTP 权限、浏览器会话、真实通途入库/QI、
生产部署、权威业务 scope 注入后的 A/E 分布。不得把 fixture 结果写成业务批准。
