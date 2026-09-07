---
type: skill
name: gls-track
description: GLS（波兰分公司自发货）单号批量跟踪 + FedEx 风格运营异常表（公开无鉴权 REST，免开发者账号/免 GLS 登录）
version: 0.1.0
triggers:
  - "GLS 跟踪"
  - "gls tracking"
  - "gls_track"
  - "GLS 单号"
  - "GLS 轨迹"
  - "GLS 波兰"
  - "波兰自发货"
  - "GLS-Poland"
  - "gls-poland"
  - "GLS 批量"
  - "GLS 异常"
  - "GLS 迟发"
  - "GLS 卡件"
  - "GLS 运营异常表"
  - "欧洲尾程"
  - "尾程 GLS"
---

# gls-track Skill

## 这是什么

GLS（波兰分公司经 GLS 波兰自发货）跟踪码批量查询 + FedEx 风格运营异常报表。
**不需要开发者账号 / 不需要波兰 GLS 登录**——走 GLS 消费级网页底层的**公开无鉴权 REST**
（`rstt029` 摘要、`rstt028` 明细需目的邮编），免登录即可拿全量 history。

## 新对话必读

1. `gls_track/AGENT_HANDOFF.md`（唯一默认入口）
2. 调研与口径：`docs/research/2026-09-07-gls-poland-track-feasibility.md`
3. 已解决坑：`docs/solutions/integration-issues/gls-track-public-rest-calendar.md`

## 何时触发

提到 GLS 跟踪/轨迹/单号批量、GLS 运营异常、波兰分公司自发货、欧洲尾程判断
迟发/漏发/卡件/承运延误等时。多承运商统一(含 UPS/FedEx/GLS)归 Cursor 的
`parcel_track` 管，本 skill 负责 GLS 侧。
