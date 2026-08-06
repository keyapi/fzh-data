---
okf: v0.1
type: Research
title: 赛狐回写 Outbox 成熟方案调研
description: 对 Transactional Outbox、CDC、任务队列与 Python 开源实现的比较和采用结论
timestamp: 2026-08-06
---

# 赛狐回写 Outbox 成熟方案调研

## 问题定义

本地购标或 Excel 导入已经得到可信 tracking 后，赛狐 submitToPlatform 可能失败、超时或返回不确定结果。失败后的恢复只能重试赛狐回写，不能重新购标。

## 成熟模式共识

| 来源 | 可复用原则 | 本项目结论 |
|---|---|---|
| [Microservices.io Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html) | 业务事实与待发送消息同事务提交；relay 可能重复发送 | tracking、label operation 与候选必须原子提交；不宣称 exactly-once |
| [AWS Transactional Outbox Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html) | 消费者幂等、顺序与故障恢复必须显式设计 | 使用稳定 candidate key、generation、状态机、租约和回读 |
| [Debezium Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html) | CDC 可把数据库日志可靠转为事件流 | 当前 SQLite 单机、低于 500 包/日，不引入 Kafka/Debezium |
| [Huey](https://github.com/coleifer/huey) | SQLite/Redis 任务调度成熟，适合常驻 worker | 未来可作调度外壳，但不能代替领域 Outbox、UNKNOWN 阻断和授权 |
| [outbox-streaming](https://github.com/hyzyla/outbox-streaming) | 展示 Python Outbox 与 broker 集成 | 偏 Kafka/通用消息，不能直接表达赛狐订单回写语义 |

## 采用结论

1. 使用本地 Transactional Outbox，业务数据与候选在同一 SQLite 事务提交。
2. 首版使用 CLI 单次 polling publisher，不运行常驻 worker。
3. 调度语义为 at-least-once；通过 intent、dedupe、lease fencing、UNKNOWN_BLOCKED 与回读避免危险重发。
4. API label 与 Excel tracking 是同等级可信来源，统一进入订单级 Outbox。
5. 不假设 submitToPlatform 幂等；真实能力仍需用户指定单包探针。

## 排除方案

- 不引入 Kafka、Debezium、RabbitMQ、Redis、Celery 或 PostgreSQL。
- 不直接采用通用 Python Outbox 库；领域状态和人工恢复仍需自行保存。
- 不让 migration 自动扫描历史 tracking；历史候选必须显式、限范围、默认 dry-run。
- 不用 Outbox 替代通途向 Amazon 等销售平台回写。

## 风险边界

历史真实探针曾返回 HTTP 401，且 submitToPlatform 是否触发平台侧推送仍未验证。因此 PR 1 只建立候选事实层，不包含任何赛狐写 HTTP。
