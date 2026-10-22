---
okf: v0.1
type: Reference
title: Codex1 审核负责人 — 项目简报（Lead Brief）
date: 2026-10-22
last_seen_commit: ae8bcc55
---

# Codex1 审核负责人 — 项目简报

## 角色

持续跟踪验收合同、前轮缺陷与跨模块风险；小修复直接审，复杂任务派局部 probe；
只有拿到本轮新证据才给 PASS/FAIL。不是所有任务的开工审批人。

## 项目地图

- G1 SO 证据门 v5：`9a04741e` / `d027f981`，仅 current_structure_only，历史 pending。
- R1/R2 审计门：`d8c473fe`。
- BOM 历史边界：`d3fc4c8d`。
- DN/WO/JC/SE 窄样本 v4：`4b7ec55f` PASS（5 SKU）。
- 10 SKU 第一阶段：`ca27163c` 闸门 PASS；3,416 行，C1/C2/C3 完整，SE 663/663。
- 库存历史：3 天入 `stock_history` 15,820 行；归档器 1.3 PASS；次日 05:17 验证。
- R290：5/5 接收，accept 3 / scenario 1 / blocker 1；ETA/Cover/UOM 仍缺。
- SKU 匹配审计 C：`c583ace9`；GS 侧 4,115 行 / 297 SKU；四类 61/2/228/6；PASS。
- B（ETA/Cover/UOM 证据）：v1 两轮 FAIL；v2 `611d9066` 双审 PASS
  （5 trace 主口径 + 10 expand10 扩展；null/0 分离；PO 行键、215 SO、1,465 可复算）。
  v2.1 仅修 UOM 注记（`a8b83618…`），待定向复核。

## 审核标准

- 固定 commit + 证据哈希 + 可复现命令；零静默丢弃；缺失标 unknown，不写 0。
- 业务约束必须进入审核：部分产品无内胆、cover 同池未证、UOM 不是处处为件。
- 小修直接判；涉及跨模块/业务口径时派 probe，不只读协调者摘要。
- 生产授权只能由用户给，不由审核/决策角色新增。

## 输入入口

- `control/CONTROL.md`、`control/state.json`
- `control/DECISIONS.md`、`control/REVIEW_LOG.md`
- `control/reviews/`（按日期）
- 证据目录：`experiments/g1_contract/out/`

## 更新协议

每次审核前先记录“上次看到的 commit/state 版本 → 本次版本”；只读增量与相关文件。
上下文过长时，以本简报 + 决策/审核日志重启，不硬撑旧会话。
