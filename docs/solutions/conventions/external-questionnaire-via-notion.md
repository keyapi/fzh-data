---
okf: v0.1
type: Reference
title: 把问卷交给非 AI 同事填写：单份仓库 MD + Notion 通道
date: 2026-10-10
category: conventions
module: sellfox_settlement
problem_type: convention
component: documentation
severity: medium
applies_when:
  - "要让仓库外、不用 AI 工具的同事（如财务）填写一份结构化问卷"
  - "在 Notion 里建页并把链接发给外部人填写"
  - "判断该用 Notion 公开页 / 访客页 / 原生表单，还是自建局域网网页"
tags: [notion, questionnaire, documentation, handoff, workflow]
---

# 把问卷交给非 AI 同事填写：单份仓库 MD + Notion 通道

## Context

2026-10 为 Amazon 非 V2 国内报税做了一份给财务负责人 ZJ 的填写底稿。ZJ 不用 AI 工具，需要一个能直接读、直接填的载体。候选：自建局域网网页、Notion 公开页、Notion 访客可编辑页、Notion 原生表单、Google 表单、直接给仓库 MD。

## Guidance（做法）

1. **单一事实源仍放仓库 MD**，不要为"给人看"另做一份副本——两份必然漂。做法是把**同一份 MD** 写成"双向可用"：
   - 填写表用**少列**（4 列：编号 / 待确认事项 / 我的建议 / 你的答复+证据链接），Notion 里好填；
   - **去掉仓库相对链接**，改写成纯文本仓库路径（Notion 不认相对链接）；
   - **`<>` 自动链接改裸 URL**（Notion 会把尖括号显示成字面量）；
   - 表格保持**简单单行单元格**（Notion 不支持列对齐/单元格内换行/合并单元格）。
2. **Notion 只做"填写通道"，不是事实源**；填完由 AI 读回并合并进 Git。
3. **分享方式 = 邀请访客 + `Can edit`**，**不要**"发布到网"。
4. 落地流程：页主在 Notion App 里 `Import → Text & Markdown` 导入 MD 建页（比 MCP 建页稳、页归自己）→ `Share → 访客邮箱 → Can edit` → 对方填写 → AI 用 MCP `fetch` 读回入 Git。

## Why This Matters

- **"公开链接给她"没用**：Notion 公开页是**只读**，要编辑必须登录 Notion；而"公开页 + 允许编辑"会把敏感内容摊在公开链接上，并带来 prompt-injection 风险。
- **Notion 原生表单不适用**：公开表单的回答**一律匿名**，且**"改自己的回答"只支持内部表单**——填完想改做不到；它适合结构化 intake，不适合"完整文档 + 可填写"。**「完整文档 + 可填写」= 访客可编辑单页**。
- **两份副本必漂**：本次一度同时存在底稿与"填充版"两份文件，用户立刻发现并要求合并——**单一源才有唯一真值**。

## When to Apply

- 要让仓库外、不用 AI 工具的同事填结构化问卷时。
- 在 Notion 里为外部人建填写页时。
- 判断"公开页 / 访客页 / 表单 / 自建网页"取舍时。

## Examples

- 落地底稿（§2 即填写区，4 列表 + 纯文本路径 + 裸 URL）：`sellfox_settlement/docs/research/2026-10-09-amazon-non-v2-monthly-tax-analysis.md`
- 选型对比与来源：`sellfox_settlement/docs/research/2026-10-10-zj-questionnaire-collection-options.md`

## 边界（能力与坑）

- **Notion MCP 不能发访客邀请**：本机 Notion MCP 有 `create_pages`/`update_page`/`fetch`/`query_data_sources`，但**没有分享/邀请工具**——"把某人加为访客并给可编辑"必须在 Notion 界面手动做；且**集成建的页归集成**，更稳的是页主自己导入建页再分享。
- **国内访问不稳**：Notion 在大陆时通时不通（GreatFire 记 Mixed），需翻墙兜底。
- **数据出境**：Notion 是境外云；含法人/银行/税务口径的页面**只可私享给单个访客，绝不发布公开链接**。

## Related

- `sellfox_settlement/docs/research/2026-10-10-zj-questionnaire-collection-options.md`（选型调研：Notion 三条路 / 自建 / Google 表单）
- `sellfox_settlement/docs/research/2026-10-09-amazon-non-v2-monthly-tax-analysis.md`（落地底稿）
- `sellfox_settlement/AGENT_HANDOFF.md`（子项目入口）
