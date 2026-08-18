---
okf: v0.1
type: Log
title: sps_api 变更日志
description: sps_api 子项目变更历史
tags: [sps-api, changelog]
---

# 变更日志

## 2026-08-18

- **初始化 OKF bundle**：`docs/index.md` + `docs/log.md`，子项目文档按 OKF v0.1 维护。
- **新增 AGENT_HANDOFF.md**：Agent 入口，记录背景/过程/经验教训/阶段性结果/脚本/下一步。
- **新增 POC 脚本**：`config.py`、`oauth.py`（M2M client_credentials + token 缓存）、`probe.py`（只读探测/下载）；`.env` + `token.json` gitignore。
- **调研报告**：`docs/research/2026-08-18-sps-commerce-api-feasibility.md`（另见仓库级 `docs/research/`）。
- **解决方案**：`docs/solutions/architecture-patterns/sps-commerce-api-automation.md`。
- **关键实测**：Web Service App 不支持 client_credentials（403）；M2M App token 成功；沙盒 Transaction API 读/写/删全链路通过；生产只读探测根目录为空（未开通，待 SPS 签约 + 实施团队配置路由）。
