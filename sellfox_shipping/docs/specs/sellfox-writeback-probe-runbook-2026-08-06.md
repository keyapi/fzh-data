---
okf: v0.1
type: Spec
title: 赛狐 trackNo 单包能力探针运行手册
description: 用户授权单个测试包裹后，由 Jack 执行 Outbox 真实回写探针、收集证据并记录能力结论
timestamp: 2026-08-06
---

# 赛狐 trackNo 单包能力探针运行手册

## 目标

在 PR 1/PR 2 代码就绪后，用**一个用户指定的真实测试包裹**验证 `submitToPlatform` 回写行为，判定账户能力结论，再决定是否开放 `SCOPED_BATCH`。探针只处理已有 Outbox 候选，绝不重新购标，也不调用 carrier create。

## 前置条件

- PR #145、#146、#147 已合并，本地为最新 `origin/main`。
- 用户指定一个 `to_process` 测试包裹，且同意真实回写副作用。
- 该包裹已 `approved`、已有可信 tracking、已生成订单级 Outbox 候选并逐条确认。
- 账户默认 `DISABLED + UNVERIFIED`，执行前显式切为 `PROBE_ONLY`。
- 使用数据库备份副本；不在生产主库上直接测试，除非用户明确允许。

## 探针流程

### 1. 准备与只读检查

```bash
uv run pytest tests/sellfox_shipping -q

uv run python -m sellfox_shipping.cli sellfox-outbox-policy-show \
  --account-key sellfox-main --json

uv run python -m sellfox_shipping.cli sellfox-outbox-list \
  --package-sn <SN> --json

uv run python -m sellfox_shipping.cli sellfox-outbox-show \
  --outbox-id <N> --json
```

检查项：

- outbox 状态为 `AWAITING_CONFIRMATION`，tracking 与本地 package tracking 一致。
- 订单 items 完整映射，scope 未被阻塞。
- 未发现同一订单已有 `PENDING/IN_FLIGHT/VERIFY_PENDING/UNKNOWN_BLOCKED/VERIFIED` 的旧候选。

### 2. 确认候选（无 HTTP）

```bash
uv run python -m sellfox_shipping.cli sellfox-outbox-confirm \
  --outbox-id <N> --actor <operator-id> --json
```

确认后记录：

- `submission_intent_id`
- `request_hash`
- 确认人、确认时间

### 3. 切到探针模式

```bash
uv run python -m sellfox_shipping.cli sellfox-outbox-policy-set \
  --account-key sellfox-main --mode PROBE_ONLY --actor <operator-id> --json
```

只有该账户仍为 `UNVERIFIED` 时允许此步；`PROBE_ONLY` 强制单包、单次执行。

### 4. Dry-run 预览

```bash
uv run python -m sellfox_shipping.cli sellfox-outbox-run-once \
  --outbox-id <N> --actor <operator-id> --json
```

必须满足：

- 外部 HTTP 调用为零。
- outbox 仍为 `PENDING`，`lease_owner` 为空，`attempt_count` 不变。

### 5. 真实单包执行

```bash
uv run python -m sellfox_shipping.cli sellfox-outbox-run-once \
  --outbox-id <N> --actor <operator-id> \
  --no-dry-run --i-understand-side-effects --limit 1 --json
```

记录：

- 出站时间、HTTP 状态、响应耗时。
- 返回业务 code/msg（脱敏后）。
- outbox 终态：`VERIFIED`、`VERIFY_PENDING`、`RETRYABLE`、`MANUAL_REVIEW`、`UNKNOWN_BLOCKED`、`CONFLICT` 或 `FAILED_FINAL`。
- intent/attempt 的新状态与 `request_hash`。

### 6. 回读核验

```bash
uv run python -m sellfox_shipping.cli sellfox-outbox-verify \
  --outbox-id <N> --actor <operator-id> --json
```

按 30 秒、2 分钟、5 分钟、15 分钟执行；只允许 `fetch_package_detail` 回读，不得再次 submit。

核验判定：

- 回读 `trackNo` 与本地 tracking 一致 → `VERIFIED`。
- `trackNo` 仍为空或等于 `packageSn` → `VERIFY_PENDING`，继续等待。
- `trackNo` 为另一个真实值 → `CONFLICT`，停止并人工核对。

### 7. 人工业务核验

同时检查赛狐 UI 与相关系统：

- 赛狐 packageDetail/UI 是否显示 `trackNo`。
- 包裹状态是否被修改为预期值。
- Amazon 或其他销售平台是否产生新推送。
- 通途是否出现重复运单、状态变化或重复发货。
- 与 HTTP 回写、回读之间的时间差。

### 8. 记录能力结论

```bash
uv run python -m sellfox_shipping.cli sellfox-outbox-capability-record \
  --account-key sellfox-main \
  --capability-status SAFE_TRACKNO_ONLY \
  --evidence-ref <artifact-or-doc-ref> \
  --actor <approver> --json
```

结论只允许三种：

| 结论 | 含义 | 后续动作 |
|---|---|---|
| `SAFE_TRACKNO_ONLY` | trackNo 正确显示且无不可接受副作用 | 模式自动设为 PROBE_ONLY；后续可切 `SCOPED_BATCH` |
| `UNSAFE_PLATFORM_SIDE_EFFECT` | trackNo 可见但触发不可接受平台推送/状态副作用 | 模式自动回到 DISABLED，永久禁止该接口自动填号 |
| `INEFFECTIVE` | 回读窗口后 trackNo 仍未变化 | 保留本地 Outbox 审计，但不再执行真实发送 |

## 停止条件

出现以下任一情况立即停止，不再调用 `submitToPlatform`：

- 401/403 或权限类错误。
- 提交后进入 `UNKNOWN_BLOCKED`。
- 回读出现 `CONFLICT`。
- 5xx、超时、连接中断或无法解释的响应。
- 用户取消授权或发现通途/销售平台出现异常推送。

停止后执行 `sellfox-outbox-show` 保留现场，并把调查、证据和人工结论写入私有 artifact 或外部工单；真实凭证、地址、电话和原始响应不得入仓。

## 证据清单

探针完成后至少保留：

- `outbox_id`、`package_sn`、`external_order_id`、`generation`。
- `submission_intent_id`、`request_hash`、`attempt_count`。
- HTTP 状态与耗时、业务 code/msg（脱敏）。
- 各次回读结果与时间。
- 赛狐 UI/packageDetail 截图或可引用 artifact。
- Amazon/通途检查结果与时间。
- 最终能力结论、证据引用、批准人和批准时间。

## Readiness Matrix 更新

探针结果落地后，把生产验收矩阵中“赛狐 trackNo 回写”一行更新为：

- `SAFE_TRACKNO_ONLY` → `implemented_not_live_validated` 改标 `complete`（仅限单包证据范围内）。
- 其他结论 → 保持 `blocked_by_approval` 或 `deferred`，并写明原因。

只有 `SAFE_TRACKNO_ONLY` 才允许：

```bash
uv run python -m sellfox_shipping.cli sellfox-outbox-policy-set \
  --account-key sellfox-main --mode SCOPED_BATCH --actor <approver> --json
```

`SCOPED_BATCH` 每次执行仍需显式确认批次，单次 `limit` 不超过 50，且不提供无范围全量发送。
