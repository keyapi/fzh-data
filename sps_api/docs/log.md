---
okf: v0.1
type: Log
title: sps_api 变更日志
description: sps_api 子项目变更历史
tags: [sps-api, changelog]
---

# 变更日志

## 2026-08-18（第二次）

- **新增脚本** `read_sps_mail.py`：IMAP 读邮件，凭据从环境变量读，不写进代码。
- **新增 reference/tencent-imap.md**：腾讯企业邮箱 IMAP 检索特性 —— FROM/SUBJECT 被服务端静默忽略、日期条件可用；正确姿势 = 服务端日期过滤 + 客户端字段过滤；记录序号/UID、范围 fetch、文件夹引号、登录频率限制等坑。
- **新增 research/2026-08-18-sps-alison-email-thread.md**：与 SPS Account Executive Alison Kudrle 的完整邮件线程（2025-06/07）+ 2026-08-18 已发回复要点。
- **邮件已发送**：给 Alison 的回复已发出（确认是否仍负责 + 自己对接 API 是否额外收费）。
- **状态澄清**：`pb@icentrade.com` 仅用于接收 PB 对账邮件（Google Colab 上脚本可跑）；SPS 往来邮件在 `us@mxdeals.com`。
- **更新** docs/index.md（新增 reference/research 导航）、AGENT_HANDOFF.md（脚本与状态）。

## 2026-08-18

- **初始化 OKF bundle**：`docs/index.md` + `docs/log.md`，子项目文档按 OKF v0.1 维护。
- **新增 AGENT_HANDOFF.md**：Agent 入口，记录背景/过程/经验教训/阶段性结果/脚本/下一步。
- **新增 POC 脚本**：`config.py`、`oauth.py`（M2M client_credentials + token 缓存）、`probe.py`（只读探测/下载）；`.env` + `token.json` gitignore。
- **调研报告**：`docs/research/2026-08-18-sps-commerce-api-feasibility.md`（另见仓库级 `docs/research/`）。
- **解决方案**：`docs/solutions/architecture-patterns/sps-commerce-api-automation.md`。
- **关键实测**：Web Service App 不支持 client_credentials（403）；M2M App token 成功；沙盒 Transaction API 读/写/删全链路通过；生产只读探测根目录为空（未开通，待 SPS 签约 + 实施团队配置路由）。
