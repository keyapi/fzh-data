---
okf: v0.1
type: Index
title: 赛狐尾程打单 — 调研索引
description: 汇总尾程打单需求简报、既有调研与当前推荐的独立综合规划入口
timestamp: 2026-08-04
---

# 赛狐尾程打单 — 调研索引

## 当前推荐入口

| 你要做什么 | 先读 |
|------------|------|
| **接手继续实现**（新对话 / 换 Agent） | [AGENT_HANDOFF.md](../../AGENT_HANDOFF.md) → 细节经本 index / [docs/index.md](../index.md) |
| **读目标架构与阶段规划** | [research-synthesis-2026-07-16.md](research-synthesis-2026-07-16.md) — **先看文首裁决框**；现行状态以 HANDOFF 为准 |
| **读生产可靠性完成态** | [../specs/production-reliability-blueprint-2026-08-04.md](../specs/production-reliability-blueprint-2026-08-04.md) → [../roadmap.md](../roadmap.md) |
| **过程日记（冷档案）** | [session-progress-2026-07-16.md](session-progress-2026-07-16.md) — 勿当现状 |
| **从零独立再调研**（刻意不看结论） | [ONBOARDING.md](ONBOARDING.md) → [briefing-for-independent-agent.md](briefing-for-independent-agent.md) |

- [session-progress-2026-07-16.md](session-progress-2026-07-16.md) — 2026-07-16 会话全过程 + **§11–13 P1B 快照 / Batch 操作记录（2026-07-17）**（冷档案，勿当现状）。
- [research-synthesis-2026-07-16.md](research-synthesis-2026-07-16.md) — 独立综合调研与架构判断；包裹批次主线；蜴国际 Excel 与 VITE/Karrio 分阶段规划。
- [lizard-p0-column-mapping-2026-07-17.md](lizard-p0-column-mapping-2026-07-17.md) — P0 真实样例列映射（匹配键、单位陷阱、批次关系）。
- [colab-notebook-legacy-summary-2026-07-17.md](colab-notebook-legacy-summary-2026-07-17.md) — 通途/FedEx/蜴国际 Colab notebook 遗产逻辑摘要。
- [sellfox-carton-dims-source-2026-07-17.md](sellfox-carton-dims-source-2026-07-17.md) — 重尺来自商品 pageList，非包裹 API。
- [local-vs-sellfox-status-2026-07-17.md](local-vs-sellfox-status-2026-07-17.md) — 赛狐状态 vs 本地审核；通过/驳回含义。
- [pnumber-to-sellfox-trace-2026-07-17.md](pnumber-to-sellfox-trace-2026-07-17.md) — 通途 P 号→赛狐订单追溯；§6 PDF 面单替换。
- [artifact-vs-erpnext-file-2026-07-17.md](artifact-vs-erpnext-file-2026-07-17.md) — Artifact 扁平 private/files；content_hash = MD5（对齐 ERPNext File）
- [lizard-api-vs-excel-2026-07-17.md](lizard-api-vs-excel-2026-07-17.md) — 蜴国际 API PR#90/#91；负余额下 create/getLabel/cancel 已验；Excel 仍生产默认
- [async-label-and-webhook-2026-07-17.md](async-label-and-webhook-2026-07-17.md) — VITE/蜴国际 Hook URL 空置 + 异步面单轮询（IT：约 30s）
- [vite-httpx-vs-karrio-decision-2026-07-17.md](vite-httpx-vs-karrio-decision-2026-07-17.md) — VITE：采用 httpx；近期不做 Karrio custom connector
- [oidc-and-submit-rate-gate-2026-07-17.md](oidc-and-submit-rate-gate-2026-07-17.md) — 可选钉钉 OIDC + SQLite 跨进程 submit 限流
- [submit-to-platform-vs-autopush-2026-07-20.md](submit-to-platform-vs-autopush-2026-07-20.md) — submitToPlatform vs 通途写平台/自动推送关；trackNo 探针协议（solutions 固化：[sellfox-trackno-write-path-vs-local-import.md](../../../docs/solutions/architecture-patterns/sellfox-trackno-write-path-vs-local-import.md)）
- [pr-slice-guide-2026-07-20.md](pr-slice-guide-2026-07-20.md) — 长分支 PR 切片与三遍审阅
- [sellfox-native-lizard-fixture-2026-07-17.md](sellfox-native-lizard-fixture-2026-07-17.md) — 赛狐原生夹具 00/02/03/04（上传·追踪号·面单）。
- [tongtool-carrier-analysis-2026-07-22.md](tongtool-carrier-analysis-2026-07-22.md) — **通途 US 仓库实际承运商分析**：9,646 条自发货订单，VITE/蜴国际/US-FedEx 分布、包裹尺寸、多SKU合并算法。
- [routing-rules-design-2026-07-22.md](routing-rules-design-2026-07-22.md) — **路由规则设计方案**：5 层决策流 + 规则数据结构 + 集成方案。
- [erpnext-zlmb-dims-v2-2026-07-23.md](erpnext-zlmb-dims-v2-2026-07-23.md) — EN ZLMB# 重尺 V2：跨面料 sibling 借用 + weight/dims 独立决策。
- [routing-engine-v1-2026-07-24.md](routing-engine-v1-2026-07-24.md) — **规则引擎 V1**：YAML 驱动路由 + 10 种运算符 + 排除店铺。
- [sku-label-back-sticker-analysis-2026-07-28.md](sku-label-back-sticker-analysis-2026-07-28.md) — **SKU 背贴 PDF 生成**：Colab notebook 逻辑拆解 + Google Sheets 中/西语名称获取 + sellfox_shipping 集成方案。
- [mature-shipping-systems-2026-08-04.md](mature-shipping-systems-2026-08-04.md) — **成熟系统与开源方案调研**：商业工作流、Karrio/托管 API 比较和 FZH 采用结论。

## 全部调研文档

- [session-progress-2026-07-16.md](session-progress-2026-07-16.md) — 会话进度与交接（过程事实，非目标架构原文）
- [lizard-p0-column-mapping-2026-07-17.md](lizard-p0-column-mapping-2026-07-17.md) — 2026-07-17 蜴国际四文件结构与列映射
- [colab-notebook-legacy-summary-2026-07-17.md](colab-notebook-legacy-summary-2026-07-17.md) — Colab 通途/FedEx/蜴国际/背贴遗产摘要
- [ONBOARDING.md](ONBOARDING.md) — 新 Agent 的独立调研开局指南，说明阅读顺序、背景资料和预期产出
- [briefing-for-independent-agent.md](briefing-for-independent-agent.md) — 仅陈述业务背景、已知需求与待确认问题的独立调研简报
- [comprehensive-research-2026-07-15.md](comprehensive-research-2026-07-15.md) — 2026-07-15 完整调研过程，保留搜索方法、来源、排除方案与早期架构结论
- [research-synthesis-2026-07-16.md](research-synthesis-2026-07-16.md) — 基于业务澄清、赛狐包裹 API、VITE API、Karrio 和现有骨架重新推导的综合结论与验证路线

独立综合文档是规划底稿（先看文首裁决框）；实现交接以 HANDOFF 为准；session-progress 为冷档案；较早的简报与完整调研继续保留，用于追溯来源和对照结论。
