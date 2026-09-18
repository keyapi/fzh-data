---
okf: v0.1
type: Reference
title: Phase B 退役门槛
description: 后续清理/删除旧脚本前必须满足的证据门槛；本轮不删除
tags: [phase-b, retirement, cleanup, gates]
---

# Phase B 退役门槛

本轮（Phase A）只迁移不改删。下列候选未来是否退役，必须**同时**满足全部条件，且由用户单独批准 Phase B 后才执行。

| 候选 | 状态 | 说明 |
|------|------|------|
| `click-based/` 重复入口（inbound/outbound/restock/update） | KEEP_PENDING_EVIDENCE | 与正式 Sellfox OpenAPI 能力对照后才可考虑去重 |
| `legacy-compatible/sellfox_restock_api.py` | KEEP_PENDING_EVIDENCE | 私有 cookie API，合同不稳定，不与 SELLFOX_API 混用 |
| 根级兼容脚本（legacy-compatible/ 同源复制） | KEEP_PENDING_EVIDENCE | 先建调用清单 + smoke test |
| OCR / CDP 探索脚本（ddddocr_login 等） | KEEP_PENDING_EVIDENCE | OCR 是可选能力，不是退役项 |

## 删除条件（全部满足）

1. `git grep` 无调用者，或调用者已迁移到 dispatcher/正式 API；
2. `--help`/import smoke 与业务样本闭环通过；
3. API 与浏览器输出的 sheet、列、行数与关键汇总一致（对照证据）；
4. 写操作只在测试商品/明确范围内验证通过；
5. 有回滚路径和最近验证日期；
6. 用户单独批准 Phase B（另开计划和 PR）。

**不得**仅因"看起来重复"删除 click-based、OCR、私有 API 或通用 Playwright 能力。
