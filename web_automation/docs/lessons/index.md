---
okf: v0.1
type: Index
title: web_automation — 经验教训
description: 网页自动化踩坑教训索引
tags: [web-automation, lessons, index]
---

# Lessons

- [ddddocr-login-pitfalls](ddddocr-login-pitfalls.md) — 验证码识别 + Playwright 登录踩坑
- [login-fallback-design](login-fallback-design.md) — 登录降级设计：OCR 不可用时自动填账号密码、验证码留人工（只覆盖通途/赛狐的**图形**验证码；钉钉 aflow 是账号密码 + **短信**验证码，见 `docs/reference/aflow-receipt-export.md`）
