---
okf: v0.1
type: Spec
title: 第六步：DN 实际交付事实层（A–E）与真实基线
date: 2026-10-30
updated: 2026-10-30
owner: claude-worker
status: implemented locally + test-station read-only scan; runtime integrations pending
scope: read-only; no writes; no auto-linking; no auto-ordering; production not deployed
tags: [supply-chain, delivery-note, actual-delivery, reconciliation]
---

# 第六步：DN 实际交付事实层

## A. 范围与真实基线（测试站，2026-10-30）

范围基准：`jack_w1_sample9_2026-10-26`（9 个已冻结代表 SKU，非业务批准清单）。
`APPROVED_TARGET_ITEMS` 明确列出 9 个 item_code；未列入一律 `out_of_scope`，
缺 item_code 记 `unknown`。分公司映射未证 → `branch_status=unknown`。

只读扫描（`include_inactive=1`，全部可读 DN）：

| 项 | 数量 |
|---|---:|
| DN 头 | 345（已提交 268 / 草稿 23 / 取消 54；退货 0；amended 16） |
| DN 明细行 | 1,264（已提交 1,038 / 草稿 55 / 取消 171；退货 0；修订 56） |
| linked | 57（已提交 10） |
| so_header_only / ambiguous / conflict / restricted | 0 / 0 / 0 / 0 |
| unlinked | 1,207（已提交 1,028） |
| in_scope / out_of_scope / unknown | 9 / 1,255 / 0 |
| restricted | false |

数量守恒（全部可读）：

- 输入毛量 224,972.5 + 未提交草稿/取消 23,620.52
- 已提交退货 0，匹配退货 0，超退 0
- 实际交付 224,972.5；`conservation_ok=true`

未关联 DN 行去向（已提交 1,028 行 / 数量 224,928.5）：

- 内部客户：裁剪部 362 行 / 121,346.8、生产车间 259 / 70,387.0、
  物流包装部 85 / 11,270.0、技术科 103 / 1,840.7；
- 外部客户：CENTRADE 178 / 19,254.0、波兰公司 40 / 829.0、美国FBA仓 1 / 1.0；
- 有运单 39 行，有通途 PO 代码 0 行；receipt/inventory 全部 `not_integrated`；
- 全部保留 DN 明细、物流/PO 追踪资格，不猜 SO、不按同物料分配。

目标 9 行明细全部来自 `DN-26-00058`（CENTRADE），均 unlinked，合计实际交付 131：

| item_code | 行数 | 实际数量 |
|---|---:|---:|
| PK#KS0001-CMKTR-100-WHITE | 1 | 10 |
| PK#KS0001-XMMBS-100-HEMPNATURAL | 8 | 121 |

其余 7 个目标 item 本轮无已提交 DN 记录 → `no_observed_delivery`，不写 0。

## B. 独立 DN 实际交付账

入口：`key_test.delivery_facts.get_delivery_facts`（schema `supply-facts/v3`）。

- 稳定身份：`source_instance + delivery_note + delivery_note_item`；
- 每行保留原始 DN/明细、docstatus、is_return、return_against、amended_from、
  source_modified；实际 item_code/qty/uom/stock_qty/stock_uom/换算依据；
  客户、公司、来源仓/目标仓及证据状态；过账日期/时间、时区状态、采集时间；
  SO/SO 行与关联状态；范围/数量/身份/目的仓/物流/入库/库存状态；原始来源与版本。
- 仅已提交 DN 计入当前实际交付；草稿/取消留痕但不累加；修订字段保留；
- 退货按 `return_against + dn_detail` 逐原明细容量抵扣；超退/缺失/受限/退货的退货
  分别留痕；无 SO 原单的退货保持 unlinked；
- 没有 SO 的有效 DN 行完整保留；
- 不同 item/UOM/仓库不串量；权限受限写 `restricted`，不伪装为空。

## C. 三本账与防重复

- **实际交付账**：`delivery_lines`（原发 + 匹配退货，净额只出现一次）。
- **SO 履约账**：`so_fulfillment`（仅 linked 行；含 SO 量、已关联交付、SO 余额、
  未关联候选、potential_overlap、confirmed_additional_supply、association_gap）。
- **补货供应账**：`supply_ledger`（SO 行 + unlinked delivery；未关联只作 unknown，
  不确认额外供应）。
- `association_edges` 含 linked/header-only/ambiguous/conflict/restricted/unlinked
  以及 `candidate` 边；候选只供人工审核，不写回。
- 物理链：`physical_chain` 输出 DN→Shipment→Tongtool PO→receipt→inventory；
  多运单 qty=null/allocation_unknown，PO 仅 code_only，receipt/inventory
  `not_integrated`；同一物理货不在供应账重复出现。

关键反例：SO 100、linked DN 70、unlinked 10 → 实际交付 80、明确 SO 履约 70、
SO 余额 30、potential_overlap 10、confirmed additional supply 20。

## D. 页面 / API / 导出

- API：`get_delivery_facts(filters)`，支持 customer/item/date/association/relevance/
  include_unlinked/include_inactive/limit/offset；稳定排序与 exhausted/partial。
- 人工视图：SO 链条面板「实际交付 / 未关联 SO」弹窗，同源调用上述 API；
  未关联行高亮，展示候选 SO 仅作审核。
- 导出：`--delivery-all [--delivery-include-inactive]` 生成
  `delivery_lines / association_edges / coverage_exceptions / so_fulfillment /
  supply_ledger / physical_chain` 六类 JSON + Excel + manifest；SHA-256、原子
  latest、失败不切换；manifest 记录 schema/rule/implementation、覆盖与分页。

## E. 补货程序适配

`warehouse_restock/delivery_facts_adapter.py`：

- 只输出每个目标 SKU 的实际交付/未关联/未知与行动建议，`auto_order=false`；
- 未关联、渠道未知、UOM 未知、无观察记录都不会写成 0；
- FBA 与 in-house 分渠道行，不跨渠道求和；
- receipt/inventory 仍 `not_integrated`，`eligible_for_restock=false`；
- 棉花、扣子、独立内胆等不在 9-SKU 清单 → `out_of_scope`，不扩大范围。

## 验证与 pending

- 12 组反例已转自动测试（key_test `test_delivery_facts.py` + fzh adapter/export）。
- 真实 API 分页/过滤：1,038 已提交行，limit/offset、linked/in_scope/include_unlinked
  均通过；全量扫描 1,264 行 exhausted。
- pending：普通受限用户 HTTP 权限、浏览器会话、真实通途入库/QI、生产部署；
  目标分公司映射、海外可售、库存可售口径仍未证，不写成通过。
