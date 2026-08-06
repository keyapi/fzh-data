---
okf: v0.1
type: Roadmap
title: sellfox_shipping 生产化路线图
description: 从购标安全核心到回写、打印、对账和承运商扩展的任务包
timestamp: 2026-08-06
---

# sellfox_shipping 生产化路线图

## 当前裁决

- **购标安全与恢复核心已完成。** PR #132、#134、#136、#137、#142、#143、#144 已覆盖 preflight、原子 claim、provider ID 持久化、resume、carrier error taxonomy、UNKNOWN_BLOCKED 证据化结案和 resume fencing。
- **Migration 0019 是合并后发现的必须修复项。** 它修复历史 SQLite 库从 0015 连续升级时 0018 直接新增外键失败，以及已被半应用 0018 标记但缺少外键的数据库。
- **赛狐可靠回写已重新授权并按三 PR 串行实施。** PR 1 建立候选事实层；PR 2 实现确认、租约、执行与回读；PR 3 实现能力探针和运营门禁。
- **当前下一阶段是生产验收，不是继续扩功能。** 验收矩阵和 Jack Agent 接手步骤见 [生产验收与交接规范](specs/production-acceptance-and-jack-handoff-2026-08-05.md)。

## Must

| 状态 | 顺序 | 任务包 | 完成标准 |
|---|---:|---|---|
| 完成 | 1 | 购标恢复控制面 | operation CLI、carrier error taxonomy、带 provider ID 的 resume、无 provider ID 的证据化人工结案；恢复路径不得再次 create |
| 当前 | 2 | 生产验收与迁移可靠性 | 全量自动化测试；空库、历史库、半迁移库；CLI 契约；Excel 幂等；无副作用验收报告 |
| 待规划 | 3 | 每日三方对账 | 输入、标签、追踪号、赛狐回写逐项计数；未匹配和失败全部保留 |
| 部分完成 | 4 | 取消与退款分离 | 已有安全取消和活动槽释放；仍需把承运商取消确认与退款到账独立记录 |
| 部署前 | 5 | 认证与审计收口 | 公网 OIDC/CSRF/RBAC、secure cookie、PII 脱敏、所有危险操作审计 |
| 进行中 | 6 | 赛狐可靠回写 | PR 1 候选层完成后，继续 PR 2 执行器与 PR 3 能力探针；真实测试默认单包且需用户授权 |

每个任务包独立分支、独立 PR，禁止直接 push main。
实现级拆分、CLI 契约和验收场景见 [恢复 CLI、错误分类与 Outbox 计划](specs/recovery-cli-error-taxonomy-outbox-plan-2026-08-05.md)。

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

新 Agent 依次阅读 AGENT_HANDOFF.md、生产验收与交接规范、生产可靠性蓝图、本路线图。开始任务前 fetch origin/main、检查开放 PR 与文件重叠、建立独立 worktree。每个 PR 必须包含测试、对账报告契约、凭证扫描和文档日志更新。
