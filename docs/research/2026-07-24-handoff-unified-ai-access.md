---
okf: v0.1
type: Handoff
title: 统一 AI 接入方案调研 — Agent 交接文档
description: 供下一个 Agent（Claude Code / Codex / Cursor）独立接手继续调研和评估。标注了本调研的偏差和开放问题。
date: 2026-07-24
branch: feature/unified-ai-access-research
agent: Claude Agent (Claude Desktop, 3P mode → DeepSeek V4)
---

# HAND_OFF: 统一 AI 接入方案调研

> 供下一个 Agent 独立接手继续调研。本文作者有已标注的偏差，请独立判断。

## 1. 用户原始需求

1. 部分同事 Win10 装不了 Codex/ChatGPT Desktop → 需要浏览器端方案
2. 不仅是 chat — 要能调赛狐 API、执行代码、分析数据
3. 老板要 Amazon 广告优化快速落地
4. 用户搭框架+培训，运营部接手维护
5. 预算 ~¥1,159/年（轻量 4C8G）

## 2. 本调研做了什么

- 深度对比 Open WebUI / Odysseus / IvyeaOps / Dify / n8n / Hermes / Pi（共 7 个平台）
- 发现 SKILL.md 已是跨 20+ Agent 的开放标准
- 发现 IvyeaOps 由深圳跨境电商运营同行打造
- 列出 Amazon 广告相关开源资产（claude-ads / amazon-skills / amazon-ads-mcp 等）

## 3. 本调研的偏差（必读）

本文作者（Claude Agent）存在以下已标注偏差：
1. 倾向 Open WebUI
2. 过度重视 OIDC 和 RAG（用户已能自建 OIDC，RAG 非第一优先级）
3. 以「领星写死」武断否决 IvyeaOps（未算从零造电商逻辑的隐性成本）
4. 所有对比由单一 Agent 完成，未交叉验证

每个偏差在主文档 `docs/research/2026-07-24-fzh-unified-ai-access-research.md` 中有 `[偏差标注 N]` 标记。

## 4. 待你独立调研的开放问题

1. **桌面+Web 双轨文档同步** — Git 仓库的 OKF 文档如何同时服务于桌面端和 Web 端？
2. **IvyeaOps 领星→赛狐实际工作量** — 改 API 端点 vs 从零造电商逻辑
3. **各平台 SKILL.md 兼容度实测**
4. **claude-ads / amazon-skills 等资产的复用价值**
5. **赛狐 API 在各平台的集成难度**

详细清单见主文档第八节。

## 5. 关键文件位置

| 文件 | 说明 |
|------|------|
| `docs/research/2026-07-24-fzh-unified-ai-access-research.md` | **主文档**（完整背景+调研+偏差标注+开放问题） |
| `docs/solutions/integration-issues/fzh-unified-ai-access-conclusion.md` | 阶段性总结 |
| `docs/research/web-agent-platform-comparison-2026.md` | 前期调研（Open WebUI / Hermes / Pi） |
| `docs/ai-agent-desktop-comparison.md` | AI 桌面端对比（2026.6） |
| `docs/enterprise-agent-knowledge-system.md` | 企业 Agent 知识系统分析 |
| `docs/company-context.md` | 公司背景+供应链+三系统 SKU |
| `advertise/docs/specs/2026-07-02-ad-analysis-master-plan.md` | Amazon 广告分析总体规划 |

## 6. 关键人物

- **zach22-1999**: 深圳跨境电商运营负责人，amazon-skills / lingxing-mcp 作者，已在微信群，已加微信
- **Hector-xue**: IvyeaOps 作者，深圳跨境电商运营，用 vibe coding 打造
- **AgriciDaniel**: claude-ads 作者（7.3K⭐），12 广告平台 Skill

## 7. 约束重申

- 用户（张克勇）不承担长期维护
- Level A（模板）先行但兼容 B（Chat 驱动）和 C（规则自定义）
- 平台必须能用 Agent 维护
- 不是所有同事都能装桌面端 → 必须浏览器可用
- 不要和 ERPNext 测试服务器混用
- 知识管理优先 OKF 文档体系，RAG 是补充
