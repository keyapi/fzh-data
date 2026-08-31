---
okf: v0.1
type: Research
title: sellfox_shipping 长分支 PR 切片指南（2026-07-20）
description: 相对 main 的主题切片与审阅顺序；app.py 耦合导致代码不宜硬拆多 PR
timestamp: 2026-07-20
tags: [sellfox-shipping, pr, review]
---

# PR 切片指南

`feature/sellfox-shipping-p1a-rest` 相对 `main` 约 100+ 文件，业务集中在 [`app.py`](../../app.py) / CLI / 同一 SQLite schema，**硬按目录拆成互不依赖的多 PR 会导致中间态 pytest 失败**。

## 实际开 PR 策略

1. **Docs / 探针口径**（小 PR）：research 边界文档 + session-progress / HANDOFF 口径  
2. **代码一体 PR**：P1A–P1C + 承运商 API + OIDC 就绪（同一分支 tip）  
3. 审批按下面 **三遍审阅**（等同计划中的 3 个主题切片）

## 审阅遍次（代码 PR）

### Pass 1 — P1A / P1B 核心

- 包裹模型 / repository / sync / 本地审核  
- 蜥蜴 Excel：`lizard_batch`、`carriers/lizard/spreadsheet|dims|cascade|…`  
- Batch / Artifact / migrations `0001`–`0005`  
- Web：`/packages`、`/lizard/export|import|batches|artifacts`

### Pass 2 — P1C 提交骨架

- `submission_state` / `submission_service` / rate gate  
- migrations `0006`–`0007`  
- CLI `packages-prepare-submit` / `packages-submit-intent`（默认 dry-run）  
- **默认不** live 推销售平台（通途写平台；见 submit vs autopush 文）

### Pass 3 — 承运商 API + 凭证 + OIDC

- VITE httpx、蜴国际 `api_client` / `order_adapter` / `api_shipment`  
- `.env.example`、`env_loader`  
- `auth_oidc`（默认 `auth.enabled: false`）

## 凭证扫描（每 PR）

按根目录 `AGENTS.md` §9 四条 `git diff origin/main...HEAD | grep …` 须零输出。
