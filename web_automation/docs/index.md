---
okf: v0.1
type: Index
title: web_automation — 文档索引
description: fzh-data 网页自动化能力舱（通途/赛狐/通用浏览器）文档导航
tags: [web-automation, tongtu, sellfox, playwright, index]
---

# web_automation 能力舱

把网页自动化能力迁入 fzh-data 后的独立 uv 子项目。入口、安全边界、能力矩阵都在这里。

- **能力矩阵与路由** → [capability-matrix](reference/capability-matrix.md)
- **安全与本地状态** → [security-and-local-state](reference/security-and-local-state.md)
- **Phase B 退役门槛** → [phase-b-retirement-gates](reference/phase-b-retirement-gates.md)
- **架构选型** → [technical-decisions](reference/technical-decisions.md)
- **平台知识**：
  - [通途踩坑](reference/tongtu-pitfalls.md) · [通途验证码 OCR](reference/tongtu-captcha-ocr.md)
  - [赛狐踩坑](reference/sellfox-pitfalls.md) · [ddddocr 安装](reference/ddddocr-setup.md)
- **迁移日志（boil-the-lake）** → [log](log.md)

> 根级 Agent 入口：`uv run python web_automation/scripts/dispatch.py <task> --check`；
> 环境体检：`uv run python web_automation/scripts/doctor.py`。
