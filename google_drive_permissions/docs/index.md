---
okf: v0.1
type: Index
title: Google Drive 权限管理 — 文档索引
---

# Google Drive 权限管理（google_drive_permissions）

> 本项目**不是一个业务模块**，而是一套**跨领域的 Google Drive / Google Sheet 权限管理能力**。
> 用于：审计现有共享、给同事加/取消权限、清理离职账号、把文件托管给服务账号以解绑「7 天过期」的用户 OAuth。

## 权威数据源

一切以 **Google Sheet 权限台账** 为准（含员工邮箱 PII，**不落到 git**）：
- sheet_id: `1TTVVHQOe5VCmdLZynGFAKXSPUVIvtlB6kOOqgszIqD0`
- https://docs.google.com/spreadsheets/d/1TTVVHQOe5VCmdLZynGFAKXSPUVIvtlB6kOOqgszIqD0
- worksheet：「账号主清单」+「现状明细」

脚本从该 Sheet 读数据，而非本地 CSV。本地 CSV（`*_ledger.csv`、`*_audit.csv`、`accounts_master.csv`）仅为逐次运行产物且**已被 .gitignore 排除**。

## 文档导航

| 你想了解... | 读这个 |
|-------------|--------|
| 这套能力怎么用（人读指南） | [../README.md](../README.md) |
| Agent 快速上手（凭证、sheet_id、脚本函数表、API 机制、边界） | [../AGENT_HANDOFF.md](../AGENT_HANDOFF.md) |
| 踩过的坑与正确姿势 | [lessons.md](lessons.md) |
| 本次操作时间线（背景/过程/结果/残留） | [log.md](log.md) |
| 可复用脚本 | [../scripts/](../scripts/) |

## 关键结论速览

- 加/删共享权限 = **Google Drive API `files/{id}/permissions`**，与文件类型无关（spreadsheet / Colab 都能用）。只有**改内容**才分 Sheets API（表） / Drive files（.ipynb）。
- 全局审计用 **用户 OAuth**（看全 989 表+134 Colab）；服务账号只看显式共享给它的文件（130）。
- 「仅属主可改共享」的开关是 `writersCanShare`（file update），不是 `capabilities.canShare`。
- 服务账号私钥**永不过期**；用户 OAuth refresh token 在 Testing 状态**7 天过期**（access token 本身约 1 小时）。
