---
okf: v0.1
type: Log
title: supply_chain_visibility 变更日志
---

# 变更日志

## 2026-10-13
- **Stage 1 v2（一对多展示）**：主表补「生产计划」列；「工单/菲号」做成可点 chip，点开 `frappe.ui.Dialog` 看层级（工单 → 逐道工序(裁剪…) + 菲号(含**开料工单**，非空=已开料)）。依据业界「摘要 + 可下钻」（Frappe 子表只有 2 层、Dialog 子表有只读 bug）。测试机已部署并 Playwright 验证。

- **新开子项目** `supply_chain_visibility/` —— EN 供应链可视化与履约查询。
- **迁移**：`EN_API/docs/research/en-supply-chain-map.md` → `docs/reference/en-supply-chain-map.md`；
  `docs/solutions/architecture-patterns/supply-chain-visibility-forms-research.md` → `docs/research/presentation-forms.md`；
  `EN_API/so_chain_embed/` → `key_test/`（Stage 1/2 落地产物）。
- **新增**：`docs/reference/en-custom-apps-and-deploy.md`（自定义 app 拓扑 + 落地链路 + 实测坑）。
- **背景**：绍兴工厂负责人拟把「下单→出库」整条链的信息呈现/查询做到 EN 上（形式未定）；
  本次完成了事实地图、呈现形式调研、Stage 1（SO 表单内嵌）+ Stage 2（原生报表），均已在**测试机**部署验证，**生产未部署**。
