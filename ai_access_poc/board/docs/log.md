---
okf: v0.1
type: Log
title: board PoC 变更日志
---

# 变更日志

## 2026-07-28

- **Phase2 ingest 落地**：`ingest_sellfox_phase2.ps1` → 实体(spKeyword/spCampaign/spAdProduct) + Targeting/Campaign/SearchTerm + asin_profit；`fetch_dataset` PoC 已读 cache。标定店 `run_store(596841)` 候选 35（含降/加 bid）。计划见 `docs/superpowers/plans/2026-07-28-phase2-sellfox-ingest.md`。
- **词汇澄清**：五杠杆（IvyeaOps 否词/收割/降bid/加bid/加预算）≠ 五桶（advertise Harvest/Negate/Monitor/Protect/Ignore）；写入 `CONCEPTS.md` + `specs/phase2-dataset-gap.md`。
- **煮湖**：领星 READ_DATASETS 全表 + 赛狐下载中心/manageData/利润全量目录映射；`monthProfit/asin` 权限重测 **OK**（`grossProfitRate` 可用，数值 caveat）。
- **SP7 × IvyeaOps 缺口调研**：标定店 BJRYECLTD-US 七表独立复验；缺口矩阵 `specs/phase2-dataset-gap.md`（白话：报表 vs 实体）；D3 更新为「可拉未 ingest」（同日已接线后见上）。

## 2026-07-27

- **E2E 闭环**：浏览器实测 AI 问答；`deepseek-chat` 在 api.vilavi.cn 无渠道 → 503；默认模型改为 `deepseek-v4-flash` 后问答打通；资讯刷新约 60 条；知识库仍依赖未启动的 IvyeaAgent。
- **品牌化 + 凭证 + 兜底 LLM**：侧栏「赛狐 ERP」；status Chip 显示赛狐 Proxy；默认 light；`seed_ivyeaops_hub_from_owui.ps1` → assistant_* = api.vilavi.cn。
- **可体验工作台**：`uv` 装 IvyeaOps `server\.venv` + 构建 `client/dist`；启动/ingest 脚本；Optimizer 对 TOODDLY-Daneey-US 跑通；主体验 `:8001`。
- 文档：`hands-on-ivyeaops-sellfox.md`、`phase2-backlog.md`。

## 2026-07-24

- **双 PoC 合并后收口**：#116 已合 main；新增运营审简报 `specs/ops-review-brief.md`；main 复跑 runner 确认 99 店 / 1922 行 / 候选 19。
- **B1–B6 跑通**：独立 runner 产出否词 17 + 收割 2；IvyeaOps `sellfox-readonly-poc` 提交适配层（openapi/ingest/关写）。
- **启动板 PoC**：OKF 骨架、落点约定、B1–B6 checklist；外部分支 `IvyeaOps-sellfox` / `sellfox-readonly-poc`。
