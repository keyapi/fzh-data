---
type: skill
name: fedex-track
description: FedEx 官方 Track API 批量查询 + 运营异常报表（完整状态历史/多Sheet/Amazon营业日口径）
version: 0.1.0
triggers:
  - "fedex 跟踪"
  - "fedex tracking"
  - "fedex_track"
  - "fzh_fedex_track"
  - "FedEx 轨迹"
  - "FedEx 单号"
  - "FedEx 跟踪码"
  - "FedEx 批量"
  - "FedEx 报表"
  - "FedEx 异常"
  - "FedEx 迟发"
  - "FedEx 漏发"
  - "FedEx 卡件"
  - "FedEx 延误"
  - "尾程 FedEx"
  - "FedEx 复用跟踪号"
---

# fedex-track Skill

## 这是什么

FedEx 官方 Track API 批量查询（仿 `ups_track`），保留**完整状态历史**（全部 `scanEvents`）+ 关键时点（建标/站点收件/交付），并生成**运营异常报表**（多 Sheet、配色、Amazon 营业日/假日口径）。用于查询 FedEx 尾程轨迹、判断**迟发/漏发/卡件/FedEx延误**（含复用跟踪号多票）。

## 新对话必读

1. `fedex_track/AGENT_HANDOFF.md`（唯一默认入口）
2. 需要细节：`fedex_track/docs/index.md`、`docs/solutions/workflow-issues/fedex-track-batch-query.md`

## 何时触发

提 FedEx 跟踪 / 轨迹 / 单号批量查询、FedEx 运营异常报表、判断 FedEx 单迟到/漏发/卡件/承运延误、复用跟踪号多票等时。
