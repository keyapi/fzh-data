---
okf: v0.1
type: Roadmap
title: sellfox_shipping 生产化路线图
description: 从购标安全核心到回写、打印、对账和承运商扩展的任务包
timestamp: 2026-08-04
---

# sellfox_shipping 生产化路线图

## Must

| 顺序 | 任务包 | 完成标准 |
|---|---|---|
| 1 | 购标安全核心 | preflight、SQLite 原子 claim、operation journal、活动标签唯一约束、UNKNOWN_BLOCKED、ACCEPTED 即时持久化、LABEL_PENDING、取消一致性、并发和崩溃窗口测试。**仍缺**：只查询恢复 CLI、carrier error taxonomy |
| 2 | 赛狐可靠回写 | 标签落库后 outbox 回写；失败只重试回写；回读核验；冲突进入人工队列 |
| 3 | 取消与退款分离 | 标签失效、取消请求、承运商确认和退款到账分开记录 |
| 4 | 认证与审计收口 | 公网 OIDC/CSRF/RBAC、PII 脱敏、所有危险操作审计 |
| 5 | 每日三方对账 | 输入、标签、追踪号、赛狐回写逐项计数；未匹配和失败全部保留 |

任务包 1 是当前开发范围。每个任务包独立分支、独立 PR，禁止直接 push main。

## Should

- SQLite job lease + 后台 Worker。
- Webhook inbox：验签、去重、允许乱序、死信和轮询兜底。
- API/Excel 共用 attempt、artifact、tracking、audit 模型；Excel 重复导入幂等。
- 波次逐件状态、打印任务去重、重印理由、包裹码与 tracking 双扫。
- Manifest/End-of-Day 与首扫状态分离。
- quoted / purchased / invoiced / credited 成本账本和附加费差异队列。

## Later

- 当持续出现 SQLite 写竞争、多实例任务争用或恢复目标不满足时迁 PostgreSQL。
- API 承运商约 5 个，或至少两个标准承运商能复用 connector 时做 Karrio 独立服务 POC。
- 有真实打包和账单数据后，再做软体数量曲线、置信度尺寸和刚性件 3D cartonization。
- 有准确成本、首扫和准时率后，再做智能选服。

## 非目标

- 不扩成 WMS，不负责库存预占、库位、采购补货。
- 不建设全球承运商市场、消费者追踪页、保险索赔中心或完整 TMS。
- 不废除 Excel；它是自有物流商的一级生产通道。
- 不因未来规模假设提前拆微服务或引入消息代理。

## Agent 交接协议

新 Agent 依次阅读 AGENT_HANDOFF.md、生产可靠性蓝图、本路线图。开始任务前 fetch origin/main、检查开放 PR 与文件重叠、建立独立 worktree。每个 PR 必须包含测试、对账报告契约、凭证扫描和文档日志更新。
