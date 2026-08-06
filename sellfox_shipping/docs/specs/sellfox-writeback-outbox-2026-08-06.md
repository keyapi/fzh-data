---
okf: v0.1
type: Spec
title: 赛狐可靠回写 Outbox 设计
description: 订单级候选、事务边界、状态机、CLI 授权与能力探针规范
timestamp: 2026-08-06
---

# 赛狐可靠回写 Outbox 设计

## 目标

当本地已有可信 tracking 时，可靠记录每个赛狐订单的待回写事实。回写失败或结果不确定时只恢复赛狐写入，不调用 carrier create。

## 数据模型

- shipping_sellfox_outbox：账户、包裹、订单、tracking、generation、状态、intent、租约、错误和冲突。
- shipping_sellfox_outbox_sources：追加保存 api_label 或 excel_tracking_import 来源。
- shipping_sellfox_writeback_policies：账户级 DISABLED/PROBE_ONLY/SCOPED_BATCH 与能力结论。默认 DISABLED + UNVERIFIED。

候选键由 account_key + package_sn + external_order_id + tracking_number 的 canonical JSON 计算 SHA-256，不含随机值。

## PR 1 已实现边界

- migration 0020_sellfox_writeback_outbox。
- 一包 N 个订单生成 N 个候选。
- API label finalizer 同事务完成 package tracking、operation SUCCEEDED 与候选来源。
- Excel 每个成功匹配行同事务完成 tracking、成本与候选来源。
- 相同 tracking 复用候选并追加来源。
- 未发送旧 tracking 被 SUPERSEDED；已发送、不确定或已验证记录遇到新 tracking 时生成 CONFLICT。
- sellfox-outbox-list/show/scan-candidates；历史扫描必须指定账户和单个 package，默认 dry-run。
- PR 1 不调用赛狐 HTTP，不确认 intent，不领取 lease。

## PR 2 已实现边界

- migration 0021 增加 `lease_origin_status`，过期 LEASED 恢复到 PENDING/RETRYABLE/VERIFY_PENDING 原状态。
- `OutboxService`：确认、账户 Policy、能力证据、租约执行与 packageDetail 回读。
- `BEGIN IMMEDIATE` 原子 claim + lease token fencing；发送前落 `IN_FLIGHT`；崩溃恢复一律 `UNKNOWN_BLOCKED`。
- 错误分类 `SubmissionFailure`：`not_sent_retryable` / `configuration_blocked` / `rejected_final` / `ambiguous` / `accepted_verify_pending`。
- 退避固定为 1m/5m/15m/1h/6h，5 次后进入 MANUAL_REVIEW；VERIFY_PENDING 回读间隔 30s/2m/5m/15m。
- 回读匹配 → VERIFIED；暂空或 package_sn 占位 → VERIFY_PENDING；不同真实值 → CONFLICT。
- 门禁：DISABLED 阻断真实发送；PROBE_ONLY 仅显式单包；SCOPED_BATCH 最多 50；SAFE_TRACKNO_ONLY 证据才可切换。
- PR 2 全部测试使用 mock，不真实调用赛狐 HTTP；不修改 label operation、活动 label 或本地 tracking。

## 候选前置条件

- tracking 非空且不等于 package_sn。
- local_review_status 等于 approved。
- package status 不是 has_shipped/has_canceled。
- API 来源存在匹配 tracking 的活动 label。
- 每个订单都有合法 order item 与正数量。

不满足条件时必须输出 skipped/failed 原因，不得静默丢弃。标签已成功但订单映射缺失时，label 与 operation 仍成功，Outbox 报告 package_has_no_orders skipped。

## 后续状态机

PR 2 实现：AWAITING_CONFIRMATION -> PENDING -> LEASED -> IN_FLIGHT -> VERIFY_PENDING -> VERIFIED。

异常状态为 RETRYABLE、MANUAL_REVIEW、UNKNOWN_BLOCKED、CONFLICT、FAILED_FINAL、SUPERSEDED。IN_FLIGHT 后崩溃必须进入 UNKNOWN_BLOCKED。VERIFY_PENDING 只能回读，不能再次 submit。

## CLI 边界

PR 1 命令：

- uv run python -m sellfox_shipping.cli sellfox-outbox-list --json
- uv run python -m sellfox_shipping.cli sellfox-outbox-show --outbox-id N --json
- uv run python -m sellfox_shipping.cli sellfox-outbox-scan-candidates --account-key sellfox-main --package-sn SN --json

扫描写入必须额外提供 --apply --actor operator。PR 2 命令：

- uv run python -m sellfox_shipping.cli sellfox-outbox-confirm --outbox-id N --actor operator --json
- uv run python -m sellfox_shipping.cli sellfox-outbox-confirm-batch --outbox-ids 1,2,3 --actor operator --json
- uv run python -m sellfox_shipping.cli sellfox-outbox-run-once --outbox-id N --actor operator --json（默认 dry-run）
- uv run python -m sellfox_shipping.cli sellfox-outbox-verify --outbox-id N --actor operator --json（仅回读）
- uv run python -m sellfox_shipping.cli sellfox-outbox-policy-show/set 与 sellfox-outbox-capability-record

在能力探针完成前不得真实发送；真实发送必须显式 --no-dry-run --i-understand-side-effects 且账户模式允许。

## 验收不变量

input = created + existing + skipped + conflict + failed。

任何 Outbox 失败不得改变活动 label、label operation 的 carrier 事实或再次购标。
