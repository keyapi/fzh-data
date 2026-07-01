---
okf: v0.1
type: Log
title: SELLFOX_API 变更日志
description: 赛狐 API 模块的所有变更记录
tags: [sellfox, saihu, API]
timestamp: 2026-07-01
---

# 变更日志

## v0.1 — 2026-07-01: 初始创建

- 从 `advertise/docs/sellfox-api/` 独立为根目录 `SELLFOX_API/`
- 用 Playwright 浏览器自动化从 `sellfoxapi.apifox.cn` 下载全部 419 个 API .md 文档
- 文档按赛狐原始模块结构组织: 16 个模块、3 级层级
- 创建 `download_docs.py` — 可增量更新、记录下载时间戳
- 从 `advertise/docs/` 迁移 sellfox 相关 research + lessons 文档
- 新建 AGENT_HANDOFF.md + OKF 文档骨架

### 数据源

- llms.txt: `https://sellfoxapi.apifox.cn/llms.txt` (77,594 字符, 858 行)
- 认证方式: Apifox 密码 (VZKGdd0Q) → browser cookie → requests
- 下载时间: 2026-07-01T03:09:45Z
- 成功率: 419/419

### 已知限制

- Cookie 有时效性，重新下载需先更新 cookie
- 部分文档极短（如 `申请API权限` 仅一行提示），属 Apifox 原文内容
- `?nav=` 参数对 .md 内容无影响，llms.txt 中有大量重复链接
