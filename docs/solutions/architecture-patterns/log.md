---
okf: v0.1
type: Log
title: architecture-patterns — 变更日志
tags: [solutions, architecture-patterns, log]
---

# architecture-patterns 变更日志

## 2026-10-12

- **修复**：助手删除不误查数值、修改只传变化字段；面板开合/拖宽/岗位隔离刷新记忆与旧响应保护，80项回归通过。

- **更新**：参数助手增加终端/注册参数/IP三功能页，沉淀统一批准、实时状态、界面上下文与操作动画防误点；76项回归及真实模型浏览器验收。

- **更新**：参数助手现役状态读取、上下文隔离、工具反馈、对话批准、动画预算及窄窗遮挡复核；44项回归，补齐观众体验与模拟登录边界。

- **更新**：网点参数台现役流程统一后台会话、工作区隔离、确认与SQLite执行核验；page-agent降为历史调研，补上模块交接入口。

## 2026-10-11

- **新增**: `branch-param-desk-read-then-guard.md` — 网页内助手先读限额再提案；护栏看动作不看原话。
- **更新**: 同上 — 公开配置只保留 OpenAI 兼容的 base URL 和 Key，真实值只放运行机器的 `.env`。
- **更新**: 同上 — 借用 page-agent 点新字段。允许没点通不要对外演示。遮罩盖住侧边栏，刷新后按钮无点击。

## 2026-09-22

- **新增**: `public-private-agent-knowledge-split.md` — 公开仓、私有 Markdown 知识仓与 secret manager 三层分离；普通 clone + bootstrap 代替 submodule，保留 Agent 检索和非技术同事使用体验。
