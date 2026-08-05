---
okf: v0.1
type: Spec
title: sellfox_shipping 生产可靠性蓝图
description: 事实边界、状态机、购标安全、恢复、安全和完成态架构
timestamp: 2026-08-04
tags: [sellfox-shipping, reliability, label, sqlite]
---

# sellfox_shipping 生产可靠性蓝图

## 目标架构

赛狐 OMS（订单事实）→ package snapshot / local review → label acquisition operation → API Carrier Adapter 或 Spreadsheet Carrier Adapter → immutable label artifact / tracking → outbox 回写赛狐并回读核验 → print / manifest / first scan / invoice reconciliation。

当前采用模块化 FastAPI 单体、SQLAlchemy、SQLite WAL 和后续后台 Worker。日量低于 500 包时不引入 Kafka、服务拆分或双数据库。

## 事实边界

| 事实 | 权威来源 |
|---|---|
| 订单、包裹、取消要求和收件信息 | 赛狐 OMS |
| 本地审核、执行 generation 和工作流 | sellfox_shipping |
| 是否买到标签、追踪号和承运状态 | 承运商 |
| 文件是否可下载 | 本地 Artifact 存储 |
| 是否贴到正确包裹 | 后续双扫码确认 |
| 最终运费、调整费和退款 | 承运商账单 |

外部副作用可能已成功但本地不知道。任何 timeout、连接中断或模糊 5xx 都不得等同于失败并直接重试。

## 购标前置校验

LabelPreflightResult 在任何承运商 HTTP 前统一验证：

- 本地包裹存在且 local_review_status 为 approved。
- actor 非空。
- carrier / service 合法。
- 重量和长宽高完整且均大于零。
- 收件人名称、地址一、城市、州、邮编、电话完整，不允许虚构兜底值。
- VITE 发件仓精确匹配配置，名称、地址一、城市、州、邮编和电话完整。

校验失败必须返回逐项错误，并保证承运商调用次数为零。

## Label Acquisition 状态机

主路径为 RESERVED → SENT → ACCEPTED → (LABEL_PENDING?) → SUCCEEDED。异常状态为 FAILED_SAFE、FAILED_FINAL、UNKNOWN_BLOCKED、CANCELLED。

- RESERVED：SQLite 原子 claim 成功，尚未发送。
- SENT：发送前已提交 operation；此后崩溃不能假设未创建。
- ACCEPTED：承运商返回 provider order ID 后**立即**落库（在适配层，不等 poll/PDF 完成）。
- LABEL_PENDING：create 已成功但 poll/下载/artifact 未完成；只允许查询标签、下载文件和本地落库，**禁止再次 create**。
- SUCCEEDED：存在活动 label 和 artifact。**SUCCEEDED 不占用**「活跃 operation」唯一索引槽；挡住再购标的是活动 label。
- FAILED_SAFE：本地校验或明确未发送，可创建新 generation。
- FAILED_FINAL：承运商确定性拒绝，需修改输入后创建新 generation。
- UNKNOWN_BLOCKED：可能已创建但无足够证据（尚无 provider ID），普通 create 永久阻断，转人工恢复。
- CANCELLED：承运商取消确认后，由 ACCEPTED / LABEL_PENDING / SUCCEEDED 转入；崩溃窗口下仅当已有关联 label 时允许 SENT → CANCELLED。

活动 **operation** 状态（占唯一索引）为 RESERVED、SENT、ACCEPTED、LABEL_PENDING、UNKNOWN_BLOCKED。
活动 **label** 由 `is_active=1` 唯一索引保证同一包裹最多一张。

## 数据模型

shipping_label_operations 保存：账户、包裹、generation、carrier、service、idempotency key、canonical request hash、状态、provider order ID、tracking、attempt count、错误分类、actor 和时间。

shipping_labels 增加 operation_id 与 is_active。标签是不可变制品；重新购标创建新 generation，并在承运商确认取消旧标签后才能释放活动约束。

canonical request hash 使用内部 snake_case DTO，至少包含：包裹业务键、收发地址、重量尺寸、carrier、service 和 channel。wire camelCase 不进入 hash 契约。

## 原子性与恢复

- claim 使用 SQLite BEGIN IMMEDIATE：检查活动 label/operation、分配 generation、插入 RESERVED 必须在同一写事务内。
- 发送前更新 SENT；收到 provider order ID 后立即更新 ACCEPTED。
- label 轮询超时、PDF 下载或 Artifact 失败进入 LABEL_PENDING，恢复不得调用 create。
- 发送后无 provider ID 的网络不确定性进入 UNKNOWN_BLOCKED；首批只读展示，不提供盲重试命令。
- label-operation-resume 仅接受带 provider ID 的 ACCEPTED/LABEL_PENDING。
- 取消 API 只有收到确定成功响应后才令 label 非活动；取消未知时保持阻断。

## 安全与审计

- 公网部署必须启用 OIDC、Secure/HttpOnly/SameSite Cookie 和 CSRF。
- 角色至少区分操作员、主管、财务、集成管理员和只读审计。
- 地址、电话、标签属于 PII；日志仅保存脱敏错误分类，原始响应也必须脱敏。
- actor、claim、发送、状态转换、恢复和取消均写审计事件。

## 明确延期

- 赛狐 outbox 回写、Webhook inbox 和 Worker在后续任务包实现。
- 装箱算法、软体数量曲线和 3D cartonization 延期；本阶段不改变当前尺寸公式。
- PostgreSQL、Karrio、AI 路由、消费者追踪页和完整 TMS 不属于首批范围。
