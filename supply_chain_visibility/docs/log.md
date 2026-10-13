---
okf: v0.1
type: Log
title: supply_chain_visibility 变更日志
---

# 变更日志

## 2026-10-13
- **Stage 1 v5**：主表合并「工单/菲号」为「链条」列（`N张·M菲号 工序 d/t`）+ **行内展开(accordion)**；菲号默认展开；保留弹窗。调研结论：**不做 hover**（触屏失效/WCAG 1.4.13/v15 无官方 hover 卡）；**不用树表**（父子字段异构）；正解=摘要+行内展开+弹窗深钻。
- **Stage 1 v4**：弹窗层级按菲号语义重构为 **工单 → 菲号(可折叠) → 逐工序 Job Card**（原「工单→工序→工序卡」是转置投影，丢菲号物证）；状态值过 `__()` 取中文翻译。菲号语义实测见 [docs/reference/en-tracking-number-semantics.md](reference/en-tracking-number-semantics.md)。
- **Stage 1 v3**：全加单据跳转链接（物料/计划/工单/工序卡/菲号/开料工单）；弹窗列工序卡明细；主表加「交期」列 + 逾期红字、阶段色块、未发合计行。
- **基数核实（生产实测）+ 连接键修正**：`(sales_order, production_item)` 复合键**有冲突** —— 同 SO 内同 item_code 最多 40 行，导致 **1464 张工单重复挂、139 张漏挂**。改用 ERPNext 原生行级外键 **`Work Order.sales_order_item`**（悬空 0）并加兜底；同步修 `so_chain.py`/报表/`EN_API/item_shipment_status.py` 的 `wos_for_line`（同 bug）。新增文档 [docs/reference/en-chain-cardinality.md](reference/en-chain-cardinality.md)。报表加「工单数/菲号数」列。
- **Stage 1 v2（一对多展示）**：主表补「生产计划」列；「工单/菲号」做成可点 chip，点开 `frappe.ui.Dialog` 看层级（工单 → 逐道工序(裁剪…) + 菲号(含**开料工单**，非空=已开料)）。依据业界「摘要 + 可下钻」（Frappe 子表只有 2 层、Dialog 子表有只读 bug）。测试机已部署并 Playwright 验证。

- **新开子项目** `supply_chain_visibility/` —— EN 供应链可视化与履约查询。
- **迁移**：`EN_API/docs/research/en-supply-chain-map.md` → `docs/reference/en-supply-chain-map.md`；
  `docs/solutions/architecture-patterns/supply-chain-visibility-forms-research.md` → `docs/research/presentation-forms.md`；
  `EN_API/so_chain_embed/` → `key_test/`（Stage 1/2 落地产物）。
- **新增**：`docs/reference/en-custom-apps-and-deploy.md`（自定义 app 拓扑 + 落地链路 + 实测坑）。
- **背景**：绍兴工厂负责人拟把「下单→出库」整条链的信息呈现/查询做到 EN 上（形式未定）；
  本次完成了事实地图、呈现形式调研、Stage 1（SO 表单内嵌）+ Stage 2（原生报表），均已在**测试机**部署验证，**生产未部署**。
