---
okf: v0.1
type: Log
title: AI 运营试点评估变更日志
description: docs/ai-ops-pilot 目录变更历史
---

# 变更日志

## 2026-09-16

- **新增平台调研**：`assistant-platform-research-2026-09.md`，基于官方资料复核 ChatGPT Business Workspace Agents、Company Knowledge、远程 MCP app，以及 Dify、n8n、Copilot Studio、Google Agent Platform、Open WebUI 的能力边界。
- **修正载体判断**：Workspace Agent 并非天然不能连接赛狐；可通过远程 MCP/API 调用只读窄工具。但 Git 仓库和上传的 Python 脚本不能直接作为生产运行时，必须服务化。
- **形成分级方案**：30 天只承诺 L1 知识助手 + L2 工具助手；推荐产品表达 Agent（L1）与广告复盘 Agent（L2），L3 业务 Agent 留待第二阶段。
- **修正资料现状**：NAS `/产品信息/` 已按 ERPNext 物料组建立 404 个目录，并有「调研报告 / 设计稿 / 图片 / 视频」标准子目录和只读扫描能力。历史资料可能存在，但尚未盘点 Owner、时效、格式、重复、可解析性与事实可信度。
- **更新落地架构**：推荐「ChatGPT Workspace Agent 前台 + Git 真源 + FZH 只读 MCP 薄适配层」；Open WebUI/IvyeaOps 保留为专用板、隔离执行、工程调试或备用前台。
- **同步修订**：更新 `assessment.md` 与 `counter-proposal.md`，删除「四类资料为空」「平台助手连不上赛狐」等不再成立的表述；W1 改为抽样的「资料资产与缺口表」。

## 2026-09-15

- **新增 bundle**: `docs/ai-ops-pilot/`（`index.md` / `log.md` / `assessment.md` / `counter-proposal.md`）。
- **背景**: 黄总 2026-09-15 出《FZH AI运营试点计划 1.0 — 30天落地行动方案》（10 页 PDF）。用户 2026-09-16 与老板面谈可行性，需完整评估 + A4 一页纸反提案两份材料。
- **写作过程中的关键发现**（决定了文档结构）:
  - 项目已有 `docs/research/2026-07-24-*` 统一 AI 接入调研 + 独立复审，已对载体选型做过证据加权裁决（C′ 门户融合）；老板计划未引用。
  - `docs/research/2026-07-24-unified-ai-access-independent-review.md` §8.1 **已撤销「advertise/ 已验证」论据**；本评估据此不再主张 advertise/ 为可靠资产。
  - 同文档 §8.2：**赛狐广告无写 API**（用户确认 + 文档核对）→「不做写回」是硬约束而非选择。
  - `ai_access_poc/` 壳 #113 + 板 #116 技术验收已绿，**卡在运营审**（`board/docs/specs/ops-review-brief.md`）。
  - 既有裁决**从未评估 ChatGPT Business / OpenAI Workspace**（全库检索零命中）→ 本评估将其明确标为真空，不引用上游作为支持或反对。
  - 外部市场/竞品数据源为付费门槛：卖家精灵 MCP 未开通、Sorftime 仅个人试用一个月已到期、优麦云仅 Excel 无 API。
