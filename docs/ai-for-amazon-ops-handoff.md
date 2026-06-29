---
okf: v0.1
type: Handoff
title: AI 赋能 Amazon 运营分享 — 制作交接文档
description: 记录本次任务的需求、分析、执行过程、问题及参考资料，供 Claude 接手继续搜索和优化。
date: 2026-06-29
branch: codex/ai-for-amazon-ops-presentation
agent: Codex CLI (OpenAI Codex Desktop)
---

# HAND_OFF: AI 赋能 Amazon 运营分享制作

> 供 Claude Desktop Agent 接手继续搜索优化时参考。

## 1. 用户原始需求

1. 为 Amazon 运营同事准备一份 **15 分钟**的 MD 分享材料
2. 普及 2026 年 AI 应用变化（vs 2025 年"以 chat 为主"）
3. 结合公司背景（FZH 跨境电商，家居纺织品，Amazon 北美+欧洲）
4. 总结已有项目（广告分析、数据管道、图片上传等）
5. 侧重点：**Amazon Listing 优化 + 广告优化**（运营同事最关注）
6. 次要补充：供应链 AI 应用（老板会参加）
7. 需要：业界概述 + 成熟用法 + 行业建议 + 项目实战演示
8. 输出到 `docs/` 目录，走 git 分支

## 2. 关键决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 受众覆盖面 | 广告+Listing 为主，供应链为辅 | 运营关心前两者，老板关心全局 |
| 内容深度 | 中高层概述，不深入技术细节 | 受众是非技术运营同事 |
| 广告部分重点 | 已实现的 advertise 工具 | 有真实数据，说服力强 |
| Listing 部分重点 | AI 文案/图片/视频 + Rufus 趋势 | 目前我们缺落地，展示业界方向 |
| 供应链部分 | 轻量展示三系统对账 | 老板感兴趣，但非运营日常 |
| 长度 | 15 分钟（244 行 MD） | 用户说可适当拉长到 15 分钟 |

## 3. 文档结构（5 Part）

```
Part 1: 2026 AI 大趋势 (3分钟)
  - Agentic AI vs Chat AI
  - MCP 协议 / Coding Agent / Desktop Agent
  - MIT CTL 2026 行业数据

Part 2: AI + 广告优化实战 (4分钟)
  - 已落地广告分析工具 + 真实数据
  - 业界 AI 广告工具对比
  - 2026 新玩法（视频广告、分时竞价、跨市场预算）

Part 3: AI + Listing 优化 (3分钟)
  - Rufus 对 Listing 的影响
  - AI 文案/图片/视频/多语言

Part 4: 项目全景 + 未来方向 (3分钟)
  - FZH AI 应用全景图
  - 供应链三系统对账示例
  - 下一步路线图

Part 5: 行动建议 (2分钟)
  - 3 件今天能开始的事
  - 总结 + QA
```

## 4. 执行过程中的问题

### 问题 1: Codex 的 web_search / deep_search 质量差
- **现象**: 中文搜索几乎全返回百度百科、央视网等无关结果
- **现象**: 英文搜索仅 Bing 后端工作，DDG/Mojeek/Startpage 全部失败
- **现象**: deep_search 同样效果差，未能获取具体 ecommerce AI 工具内容
- **原因**: free-web-tools MCP 的搜索后端在中国网络环境下效果不佳
- **缓解措施**:
  1. 用了两个 sub-agent (explorer) 并行搜索
  2. 直接 fetch_url 抓取已知高质量源（Anthropic Blog, Claude.com）
  3. 部分内容依赖 training knowledge 补充
- **建议**: Claude 接手后，用 Claude 内置搜索重新验证和补充

### 问题 2: apply_patch 工具不可用
- **现象**: `apply_patch` 返回 "unsupported call"
- **缓解措施**: 改用 PowerShell `Out-File` 创建文件

### 问题 3: sub-agent 超时
- **现象**: 第二个 explorer (019f1225-d7fc-7101-b0d2-22a888aac052) 首次 wait 超时
- **原因**: 多个并行搜索响应慢
- **缓解措施**: 使用 send_input 要求重新输出完整报告，第二次成功获取

### 问题 4: update_plan 在 Plan Mode 不可用
- **现象**: 文件写完后调用 update_plan 报错 "not allowed in Plan mode"
- **影响**: 无法更新 checklist，但不影响文件内容

## 5. 参考文献原始 URL

### 已抓取到完整内容的 URL
1. Anthropic Blog (Claude 功能列表):
   https://claude.com/blog
   - Claude Code artifacts, Managed Agents, MCP tunnels, multi-agent, memory, etc.

2. Claude Managed Agents 发布文 (2026-04-08):
   https://claude.com/blog/claude-managed-agents
   - 生产级 Agent、沙箱执行、多 Agent 编排、Notion/Rakuten/Asana 案例

3. Anthropic Newsroom - Claude Opus 4.8 发布:
   https://www.anthropic.com/news/claude-opus-4-8
   - Dynamic workflows, effort control, Messages API system entries
   - Opus 4.8 评测：CursorBench、Legal Agent、Online-Mind2Web 等

4. MIT CTL 2026 Omnichannel Report:
   https://ctl.mit.edu/news/ai-not-optional-anymore-omnichannel-supply-chains-new-mit-ctl-research-finds
   - 81% 企业电商增长, 60% 全渠道, 35% AI 降低退货率

5. CETA International PPC Guide 2026:
   https://www.cetainternational.com/insights/amazon-ppc-advertising-optimization-2026
   - US CPC $1.15, 视频广告 ACOS 16%, 分时竞价策略

### 搜索结果中有用但内容被截断的 URL
6. Anthropic Newsroom (项目列表):
   https://www.anthropic.com/news
   - Claude Tag, Claude Corps, Opus 4.8, 安全研究等

### 搜索失败但值得 Claud 重新搜索的主题
7. Amazon PPC AI 优化工具对比:
   - 搜索词: "Amazon PPC AI optimization tools Perpetua Quartile Teikametrics 2026"
   - 状态: Bing 后端未返回有效结果

8. AI listing 优化和 Rufus:
   - 搜索词: "Amazon Rufus AI shopping assistant listing optimization 2026"
   - 搜索词: "Amazon seller AI listing optimization tool 2026"
   - 状态: 均未返回有效结果

9. 跨境电商 AI 应用案例:
   - 搜索词: "cross border ecommerce AI automation 2026 case study"
   - 状态: 未尝试英文版

### 项目内部参考文件
10. `docs/company-context.md` — 公司背景、供应链、三系统 SKU
11. `advertise/AGENT_HANDOFF.md` — 广告分析模块完整文档
12. `advertise/docs/reference/tools-ecosystem.md` — 优麦云/卖家精灵/Perpetua 对比
13. `advertise/docs/roadmap.md` — 广告工具路线图 (Phase 1-4)
14. `docs/onboarding.md` — 非技术同事上手指南

## 6. 已知不足（待 Claude 补充）

1. **Listing 优化部分偏弱**: 目前主要是方向性建议，缺乏具体工具实测对比和案例
2. **Rufus 优化缺乏深度**: Amazon Rufus 对搜索的影响值得单独展开
3. **竞品情报工具**: 卖家精灵以外的工具（Helium10, Jungle Scout, DataHawk）2026 更新未覆盖
4. **AI 视频生成**: Sponsored Brands Video 的工具对比和成本分析缺失
5. **COSMO 算法**: Amazon 2026 新搜索算法的 Listing 优化策略未涉及
6. **实际案例**: 缺少其他跨境电商公司 AI 落地的具体案例
7. **成本估算**: 各 AI 工具的实际花费对比（Perpetua $250/mo vs 自建 $0 边际成本等）

## 7. 给 Claude 的接手建议

1. **首先搜索补充 Listing 和 Rufus 部分**: 这是运营同事最关心的
2. **验证行业数据**: MIT CTL 和 CETA 的数据是否最新，有无更新
3. **添加实操案例**: 如果能找到跨境电商 AI 落地的具体案例会很有说服力
4. **优化演示结构**: 目前是 MD 文档，如需转 PPT 可进一步调整
5. **隐私检查**: 文中已确认无凭证/token/手机号，但"张克勇"和"如森 US"需确认是否要匿名
6. **图片/视频演示**: 可以考虑用 AI 生成 lifestyle 图作为现场演示素材

## 8. Git 状态

- **分支**: `codex/ai-for-amazon-ops-presentation`
- **新增文件**: `docs/ai-for-amazon-ops-2026.md` (244 行)
- **状态**: 已创建，待 commit 和 PR
- **目标 base**: `main`
