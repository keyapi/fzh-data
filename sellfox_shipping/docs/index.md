---
okf: v0.1
type: Index
module: sellfox_shipping
created: 2026-07-15
updated: 2026-08-07
---

# sellfox_shipping — 文档索引

## 概述

赛狐尾程打单系统，支持从赛狐获取订单、多承运人标签生成、追踪号回写。

## 文档

- [README.md](../README.md) — 项目概述与快速开始
- [AGENT_HANDOFF.md](../AGENT_HANDOFF.md) — **默认接手入口**（全貌七块）
- [log.md](log.md) — 变更日志
- [roadmap.md](roadmap.md) — **生产化路线图与 Agent 任务包**
- [specs/index.md](specs/index.md) — **生产可靠性设计规范**
- [specs/recovery-cli-error-taxonomy-outbox-plan-2026-08-05.md](specs/recovery-cli-error-taxonomy-outbox-plan-2026-08-05.md) — **恢复 CLI、错误分类、UNKNOWN 人工结案与赛狐 Outbox 实施计划**
- [specs/production-acceptance-and-jack-handoff-2026-08-05.md](specs/production-acceptance-and-jack-handoff-2026-08-05.md) — **生产验收矩阵、剩余边界与 Jack Agent 接手规范**
- [specs/sellfox-writeback-outbox-2026-08-06.md](specs/sellfox-writeback-outbox-2026-08-06.md) — 订单级候选、事务边界和后续执行器规范。
- [specs/sellfox-writeback-probe-runbook-2026-08-06.md](specs/sellfox-writeback-probe-runbook-2026-08-06.md) — **单包能力探针执行手册、证据清单与能力结论门禁**。

## 调研 / 交接

- [research/index.md](research/index.md) — 调研文档导航
- [research/mature-shipping-systems-2026-08-04.md](research/mature-shipping-systems-2026-08-04.md) — 成熟商业系统、Karrio 与 API 方案调研
- [research/sellfox-writeback-outbox-systems-2026-08-06.md](research/sellfox-writeback-outbox-systems-2026-08-06.md) — Outbox 成熟方案与采用结论。
- [research/session-progress-2026-07-16.md](research/session-progress-2026-07-16.md) — 过程日记（冷档案，勿当现状）
- [research/research-synthesis-2026-07-16.md](research/research-synthesis-2026-07-16.md) — 规划底稿；先看文首裁决框，现行以 HANDOFF 为准
- [research/lizard-p0-column-mapping-2026-07-17.md](research/lizard-p0-column-mapping-2026-07-17.md) — 蜴国际 P0 样例列映射（匹配键 / 单位）
- [research/colab-notebook-legacy-summary-2026-07-17.md](research/colab-notebook-legacy-summary-2026-07-17.md) — Colab 通途/蜴国际/背贴 notebook 摘要
- [research/sellfox-carton-dims-source-2026-07-17.md](research/sellfox-carton-dims-source-2026-07-17.md) — 重尺：商品 pageList carton* 字段
- [research/local-vs-sellfox-status-2026-07-17.md](research/local-vs-sellfox-status-2026-07-17.md) — 赛狐状态 vs 本地通过/驳回
- [research/pnumber-to-sellfox-trace-2026-07-17.md](research/pnumber-to-sellfox-trace-2026-07-17.md) — 通途 P 号追溯赛狐；§6 PDF 面单替换
- [research/sellfox-native-lizard-fixture-2026-07-17.md](research/sellfox-native-lizard-fixture-2026-07-17.md) — 赛狐原生夹具 00/02/03/04（上传·追踪号·面单）
- [research/lizard-api-vs-excel-2026-07-17.md](research/lizard-api-vs-excel-2026-07-17.md) — 蜴国际 API PR#90/#91；Excel 仍生产默认
- [research/vite-httpx-vs-karrio-decision-2026-07-17.md](research/vite-httpx-vs-karrio-decision-2026-07-17.md) — VITE：采用 httpx；近期不做 Karrio custom connector
- [research/submit-to-platform-vs-autopush-2026-07-20.md](research/submit-to-platform-vs-autopush-2026-07-20.md) — submitToPlatform vs 通途写平台/自动推送关；trackNo 探针协议
- [research/pr-slice-guide-2026-07-20.md](research/pr-slice-guide-2026-07-20.md) — 长分支 PR 切片与三遍审阅
- [research/tongtool-carrier-analysis-2026-07-22.md](research/tongtool-carrier-analysis-2026-07-22.md) — **通途 US 仓库实际承运商分析**：9,646 条自发货订单，VITE/蜴国际/US-FedEx 分布、包裹尺寸、多SKU合并算法
- [research/routing-rules-design-2026-07-22.md](research/routing-rules-design-2026-07-22.md) — **路由规则设计方案**：5 层决策流 + 规则数据结构 + 集成方案
- [research/erpnext-zlmb-dims-v2-2026-07-23.md](research/erpnext-zlmb-dims-v2-2026-07-23.md) — EN ZLMB# 重尺 V2：跨面料 sibling 借用
- [research/sku-label-back-sticker-analysis-2026-07-28.md](research/sku-label-back-sticker-analysis-2026-07-28.md) — **SKU 背贴 PDF 生成**：Colab notebook 逻辑分析 + sellfox_shipping 集成方案

## 已解决问题

- [solutions/index.md](solutions/index.md) — 已解决问题索引
- [solutions/tiktok-exclude-shops-2026-08-07.md](solutions/tiktok-exclude-shops-2026-08-07.md) — **TikTok 排除店铺**：赛狐 API 核实真实 shop_name + `exclude_shops` 单点配置驱动列表过滤与路由建议
- [solutions/reliability-hardening-and-lizard-chain-2026-08-06.md](solutions/reliability-hardening-and-lizard-chain-2026-08-06.md) — **可靠性收口与蜴国际面单链路全部问题**：分页count、resume并发、证据化结案、蜴国际API、报价展示、赛狐回写、批量面单、async阻塞、参考号重复
