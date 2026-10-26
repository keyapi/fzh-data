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
| 2026-10-26 | 同事通途报表备份（20261026）可用性评审 — 70 个销售及库存报表覆盖 2026-04→10 共 22 天；有货 SKU 覆盖约 94%、零库存 SKU 仅约 5%，可看库存水平但不能单独判断货 | [2026-10-26-pengjian-inventory-backup-review.md](2026-10-26-pengjian-inventory-backup-review.md) |
| 2026-10-26 | 钉钉 DWS CLI 读群消息 — 官方 `dws chat +chat-messages` 可读历史；需组织授权 + 应用消息 scope + 重定向 URL（127.0.0.1 / login.dingtalk.com）；含 NEW-API 报错修复与只读试跑 | [2026-10-26-dingtalk-dws-cli-group-messages.md](2026-10-26-dingtalk-dws-cli-group-messages.md) |
| 2026-10-23 | 通途库存「当前记录 + 每日历史」放哪：EN 只读最新快照 + 上海云盘/OSS 历史 + DuckDB；实测 EN 规格、`/mnt/nas` 非挂载、DFP S3 香港桶存在但跨区、生产 internal 端点超时、Jack PR #309 | [2026-10-23-inventory-history-storage-architecture.md](2026-10-23-inventory-history-storage-architecture.md) |
| 2026-10-23 | 通途历史库存用于销量预测：断货/停售/退货/手工调整判定；现有 `stockout_observed` 是按仓 `available=0` 的朴素标记；历史数据：EN 10/20–10/23、WX 6/26+7 月检查点+8/24–10/19、PB check0stock 2023-08 至今 | [2026-10-23-stockout-censoring-model.md](2026-10-23-stockout-censoring-model.md) |
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
