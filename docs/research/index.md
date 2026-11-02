---
okf: v0.1
type: Index
title: 调研记录
description: 项目级调研记录索引
tags: [research, index]
---

# 调研记录

| 日期 | 标题 | 文件 |
|------|------|------|
| 2026-10-29 | 跨仓直接发货更正 + 双仓销售 — 美东/美中不互调改直发；归属表 v6：双仓 25/实质 11，按两仓分别补/核 | [2026-10-29-direct-ship-and-dual-warehouse.md](2026-10-29-direct-ship-and-dual-warehouse.md) |
| 2026-10-29 | 48 待定量人工决策草稿（DRAFT）— 5 列格式，48 行全覆盖；47 行近端、表内可调 0、8 行近零、全部未释放 | [2026-10-29-48-key-decision-draft.md](2026-10-29-48-key-decision-draft.md) |
| 2026-10-28 | 近端缺口调拨候选 — 48 行近端兜底：仅 1 行可同国调 2 个；47 行无可调（波兰 32 不可跨洲 + 美东 15 无美中货源）；潜在改配 0 | [2026-10-28-near-gap-transfer-candidates.md](2026-10-28-near-gap-transfer-candidates.md) |
| 2026-10-28 | 48 待定量键 97/157 天原型 **v2** — 真实周桶积分（不按 35 天放大）：精确 97/157 不可得（周桶）、按桶界 102/158 天 48 行可算；Q 441.82/662.26（全精度）；SS 政策只 8 行（历史销量波动代理，未校准）；2.779 天需求盲区未估算；最晚下单日 48/48 已过 | [2026-10-28-48-key-97-157-prototype.md](2026-10-28-48-key-97-157-prototype.md) |
| 2026-10-28 | PO ↔ DN 候选匹配 v3 — 28 张 DN：正式链接 9（EN 字段，含 DN-00114）/ 有候选 18 / 纯内胆 1 / FBA 0 / 无候选 0；27 首选与 v2 全等、9/9 rank1；v2 复审 5 项小修（归属措辞、FBA 分支、UOM、边界、raw 别名） | [2026-10-28-po-dn-candidate-matching.md](2026-10-28-po-dn-candidate-matching.md) |
| 2026-10-28 | Wayfair CG 仓来源归类（worker E，给 YTQ）— 8/1–10/28 自发货 593 单/677 件/49 SKU，26 SKU 判美东、23 判美中、0 无法判断；Wayfair dropship NJ/TX 旁证 39/39 一致；无调拨凭证（API 只 7 天） | [2026-10-28-wayfair-cg-source-map.md](2026-10-28-wayfair-cg-source-map.md) |
| 2026-10-08 | key_test 生产线 vs 测试线逐文件评审清单 — 22 个冲突文件分档 + 引用关系实测（哪些真在跑/哪些死代码）+ 生产 Error Log 里的真 bug + 已建 `main-new`（以生产为基线）与备份分支 | [2026-10-08-key-test-branch-unification-review.md](2026-10-08-key-test-branch-unification-review.md) |
| 2026-09-21 | 赛狐 API 拉 Amazon 账期报表 — **只有「插件获取报告」一条路且 API 不可触发**；90 店仅 39 店有数据、只有 6/7 两个月；fileUrls 为 1 小时签名 URL | [2026-09-21-sellfox-amazon-settlement-reports.md](2026-09-21-sellfox-amazon-settlement-reports.md) |
| 2026-09-21 | 赛狐 Walmart 账期 API 实测 — `periodStartDate`/`periodEndDate` 真实可用，`purchaseOrder` 与 EN `Tongtool Order.platform_order_id` 100% 匹配；Wayfair/Overstock 无此路径 | [2026-09-21-sellfox-walmart-settlement-api.md](2026-09-21-sellfox-walmart-settlement-api.md) |
| 2026-09-21 | 群晖 NAS 接入 ChatGPT — **部署在 VPS 而非 NAS**（实测 443 不通、只开 11024）；含**第三方方案深度对比**（mrquj 支持 Streamable HTTP + Bearer、Tailscale 私网优于公网端口）、鉴权两条路线，以及两处对早先结论的更正 | [2026-09-21-nas-mcp-chatgpt-feasibility.md](2026-09-21-nas-mcp-chatgpt-feasibility.md) |
| 2026-09-20 | 赛狐官方 MCP 可行性 — **用 API 账号凭证实测可用**（只读工具返回真实数据）；后台 `X-MCP-Key` 是另一条路仍「未启用」；23 工具 = 13 读 + 1 报表任务 + **9 个 SP 广告写（无公开文档对应，未调用）** | [2026-09-20-sellfox-official-mcp-feasibility.md](2026-09-20-sellfox-official-mcp-feasibility.md) |
| 2026-09-18 | 赛狐「私有接口」与公开 OpenAPI 的区分 — 术语（undocumented internal API，业界亦称 shadow API 影子 API）、判据、用词约定 | [2026-09-18-sellfox-private-api-terminology.md](2026-09-18-sellfox-private-api-terminology.md) |
| 2026-09-18 | 赛狐成本口径与 FIFO 批次 — 成本挂在批次上、调整单按先进先出吃批次 | [2026-09-18-sellfox-cost-accounting-fifo.md](2026-09-18-sellfox-cost-accounting-fifo.md) |
| 2026-09-07 | GLS 跟踪可行性 — 公开无鉴权 API 免登录实测可行（明细需目的邮编）；官方 ShipIT/MyGLS 需 GLS 波兰客户号 + WebAPI 开通，纯开发者账号替代不了 | [2026-09-07-gls-poland-track-feasibility.md](2026-09-07-gls-poland-track-feasibility.md) |
| 2026-08-18 | SPS Commerce API 自动化可行性（Pottery Barn）— 走 Transaction API + M2M，已实测读/写/删 | [2026-08-18-sps-commerce-api-feasibility.md](2026-08-18-sps-commerce-api-feasibility.md) |
| 2026-07-24 | 统一 AI 接入 C′ — 双 PoC 实施计划（壳 OWUI + 板 IvyeaOps 赛狐只读） | [2026-07-24-unified-ai-access-poc-plan.md](2026-07-24-unified-ai-access-poc-plan.md) |
| 2026-07-24 | FZH 统一 AI 接入 — 独立复审与平台裁决 | [2026-07-24-unified-ai-access-independent-review.md](2026-07-24-unified-ai-access-independent-review.md) |
| 2026-07-24 | FZH 统一 AI 接入方案 — Agent 交接文档 | [2026-07-24-handoff-unified-ai-access.md](2026-07-24-handoff-unified-ai-access.md) |
| 2026-07-24 | FZH 统一 AI 接入方案 — 完整调研报告（Open WebUI / Odysseus / IvyeaOps 对比） | [2026-07-24-fzh-unified-ai-access-research.md](2026-07-24-fzh-unified-ai-access-research.md) |
| 2026-07-10 | Google AI — 知识库管理方案调研（OKF 替代方案 + 银行级知识库设计） | [2026-07-10-google-ai-knowledge-management-research.md](2026-07-10-google-ai-knowledge-management-research.md) |
