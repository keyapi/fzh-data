---
okf: v0.1
type: Spec
title: sellfox_shipping 恢复 CLI、错误分类与赛狐 Outbox 实施计划
description: 面向 AI 操作的购标恢复控制面、无 provider ID 人工结案和可靠赛狐回写任务包
timestamp: 2026-08-05
tags: [sellfox-shipping, cli, recovery, error-taxonomy, outbox]
---

# sellfox_shipping 恢复 CLI、错误分类与赛狐 Outbox 实施计划

## 目标与边界

本计划承接 PR #132-#136 已完成的购标安全核心。下一阶段仍以 Typer CLI 为第一操作界面，保证 AI Agent 可以通过稳定 JSON 输入输出完成查询、恢复、调查和赛狐回写；FastMCP 与 Web 操作面在 CLI 契约稳定后再映射，不先行定义第二套业务逻辑。

本阶段不做装箱算法、Worker 常驻进程、真实批量购标、自动解除无证据阻断或未经确认的生产赛狐回写。所有外部副作用都必须经过显式开关、actor、审计和范围确认。

## 设计裁决

1. **查询与副作用分离。** `label-operations-list/show` 永远只读；`resume` 只查询既有 provider order，绝不调用 create；人工结案命令不调用承运商。
2. **错误分类由适配器提供证据。** HTTP 状态只是证据之一，不能直接决定 `FAILED_FINAL`。VITE 与蜴国际客户端应抛出结构化 carrier failure，LabelService 只按统一语义映射状态。
3. **无 provider ID 不允许“重试”。** `UNKNOWN_BLOCKED` 只能通过承运商后台、客服、账单或其他权威查询得到“已创建”或“确定未创建”的证据后人工结案。
4. **赛狐回写与购标解耦。** 标签成功落库只创建 outbox 工作项；回写失败只重试赛狐投递，不重新购标、不修改 carrier operation。
5. **复用 SubmissionIntent 领域规则，不冒充 Outbox。** 现有 intent/attempt/scope guard、canonical request、CAS 与回读核验继续保留；新增 outbox 负责可靠调度、lease、退避和投递审计。

## CLI 通用契约

- 所有新命令支持 `--json`，JSON 字段使用 `snake_case`，时间使用带时区 ISO 8601。
- 不使用交互式 prompt，避免 Agent 卡住；危险操作依赖显式确认参数。
- 成功退出码为 `0`；输入/前置条件错误为 `2`；阻断或冲突为 `3`；外部系统不确定为 `4`；确定性外部失败为 `5`。
- 每次输出都包含 `command`、`ok`、`counts`、`results`、`errors`；列表命令还包含 `filters` 和 `next_cursor` 或明确的 `limit`。
- 错误输出至少包含 `code`、`message`、`operation_id`、`package_sn`、`recommended_action`，不得输出完整地址、电话、token 或原始未脱敏响应。
- 所有写命令要求非空 `--actor`；审计记录 actor、命令、目标、前状态、后状态、证据摘要和时间。

## PR 1：只读购标操作控制面

### 命令

```bash
uv run python -m sellfox_shipping.cli label-operations-list \
  --status UNKNOWN_BLOCKED --carrier vite --limit 50 --json

uv run python -m sellfox_shipping.cli label-operation-show \
  --operation-id 123 --json
```

`list` 支持 `--status`、`--package-sn`、`--carrier`、`--account-key`、`--limit`；`show` 返回 operation、关联 package 摘要、关联 label/artifact 摘要和允许的下一动作。地址与原始 carrier response 不进入输出。

### 文件与实现边界

- `sellfox_shipping/cli.py`：命令和稳定 JSON envelope。
- `sellfox_shipping/package_repository.py`：补 account 过滤、operation + label/artifact 只读投影；不在 CLI 拼 SQL。
- `sellfox_shipping/label_service.py`：可选的只读 facade，用于集中计算 `allowed_actions`。
- `tests/sellfox_shipping/test_label_operation_cli.py`：CLI runner、过滤、PII 脱敏、退出码。

### 验收场景

- 空结果仍返回完整 counts，不报错。
- 多账户同 package_sn 不串数据。
- `UNKNOWN_BLOCKED` 无 provider ID 显示 `investigate`，不显示 `resume` 或 `retry_create`。
- `ACCEPTED/LABEL_PENDING` 且有 provider ID 显示 `resume`。
- `SUCCEEDED/CANCELLED/FAILED_*` 不提供恢复动作。

## PR 2：Carrier Error Taxonomy

### 统一模型

新增承运商无关的 `CarrierFailure`，建议字段：

| 字段 | 含义 |
|---|---|
| `phase` | `preflight/auth/create/query/download/cancel/artifact` |
| `outcome` | `not_sent/rejected/retryable_query/ambiguous/accepted_pending` |
| `category` | `configuration/authentication/validation/service_rejected/rate_limited/transport/timeout/provider_5xx/protocol/local_storage` |
| `provider_code` | 脱敏后的业务码，可空 |
| `http_status` | 仅作为诊断证据，可空 |
| `provider_order_id` | 已知时必须携带 |
| `tracking_number` | 已知时携带 |
| `safe_to_create_again` | 只允许适配器在证明未发送或确定未创建时设为 true |
| `summary` | 脱敏、限长的人类可读摘要 |

状态映射固定为：

- HTTP 前本地配置/校验失败，或适配器明确证明请求未发送：`FAILED_SAFE`。
- 承运商明确拒绝且确认未创建 shipment：`FAILED_FINAL`。输入修改后可创建新 generation。
- create 已返回 provider ID：至少 `ACCEPTED`；后续 query/download/artifact 问题为 `LABEL_PENDING`。
- create 发送后的 timeout、连接断开、不可解释 5xx、响应解析失败且不能证明未创建：`UNKNOWN_BLOCKED`。
- 401/403 默认表示认证失败，但在请求已发送的 create 阶段仍需看适配器证据；不能仅凭状态码自动判定可重购。
- 429 在 create 阶段若无 provider 幂等保证则为 `UNKNOWN_BLOCKED`；在 getLabel/query 阶段为可恢复查询错误，保持 `ACCEPTED/LABEL_PENDING`。

### 文件与测试

- `sellfox_shipping/carriers/errors.py`：统一异常和枚举。
- `sellfox_shipping/carriers/vite/client.py`、`carriers/lizard/api_client.py`：保留 provider 证据并映射统一异常。
- `sellfox_shipping/label_service.py`：删除按 HTTP 状态的 `_fail_operation` 推断，改按 `CarrierFailure.outcome`。
- `tests/sellfox_shipping/test_carrier_error_taxonomy.py`：表驱动覆盖 phase × outcome。
- 扩展 VITE/蜴国际 client 与 recovery 测试，断言状态、provider ID、create 次数和脱敏摘要。

## PR 3：带 Provider ID 的 Resume CLI

### 命令

```bash
uv run python -m sellfox_shipping.cli label-operation-resume \
  --operation-id 123 --actor agent-name --json
```

仅接受 `ACCEPTED` 或 `LABEL_PENDING` 且 `provider_order_id` 非空。恢复路径调用 carrier 的 query/getLabel，必要时下载 PDF、登记 artifact、插入或补齐 label，再原子转 `SUCCEEDED`。该命令的依赖接口不得暴露 create 方法，从类型和测试两层保证不会二次购标。

并发 resume 使用 SQLite claim/lease 或条件更新，确保同一 operation 同时只有一个恢复者；短期可新增 `recovery_started_at/recovery_actor`，过期 lease 可被后续命令接管。每次执行增加 `attempt_count` 并写审计。

### 验收场景

- VITE poll pending、PDF 下载失败、artifact 写入失败分别可继续恢复，create mock 恒为零次。
- 蜴国际可用 `order_code + package_sn/reference_no` 查询并完成。
- provider 仍未就绪时保持 `LABEL_PENDING`，退出码 `4`，输出建议稍后 resume。
- `UNKNOWN_BLOCKED`、无 provider ID、终态 operation、已有活动 label 的不一致情况均拒绝。
- 两个进程并发 resume 时只有一个执行外部查询/写 artifact。
- 重复 resume 已完成 operation 返回幂等结果，不重复插 label。

## PR 4：UNKNOWN_BLOCKED 人工调查与结案

### 原则

人工动作是“记录权威结论”，不是技术重试。必须保留证据类型、外部引用、调查者、时间和备注；原始截图或文件作为 private artifact 保存，CLI 只记录 artifact ID，不把 PII 写进日志。

### 命令

```bash
# 仅登记调查信息，不释放阻断
uv run python -m sellfox_shipping.cli label-operation-investigation-add \
  --operation-id 123 --evidence-type carrier_portal \
  --external-reference CASE-456 --actor supervisor --json

# 查到已创建：先补 provider ID，随后只能走 resume
uv run python -m sellfox_shipping.cli label-operation-resolve-created \
  --operation-id 123 --provider-order-id ORDER-789 \
  --evidence-id 45 --actor supervisor \
  --i-understand-side-effects --json

# 权威确认未创建：释放阻断，但不自动 create
uv run python -m sellfox_shipping.cli label-operation-resolve-not-created \
  --operation-id 123 --evidence-id 46 --actor supervisor \
  --i-understand-side-effects --json
```

建议新增终态 `CONFIRMED_NOT_CREATED`；`resolve-created` 将原 operation 转 `ACCEPTED` 或 `LABEL_PENDING` 并保存 provider ID，随后由 resume 完成。上述两条边不能加入通用 `transition_label_operation()` 的开放边表，必须通过校验证据归属、actor 和确认参数的 repository 专用事务完成。`resolve-not-created` 只有在明确证据下转终态并释放活动 operation 唯一约束，但不会自动创建下一 generation。仅“已升级客服”“暂未查到”不能结案，operation 继续 `UNKNOWN_BLOCKED`。

### 数据与测试

- migration 新增 `shipping_label_operation_investigations`；每条记录不可覆盖，只能追加。
- 状态转换与证据记录在同一事务；`resolve-created/not-created` 要求 evidence 归属同一 operation。
- 测试错误 evidence、重复结案、并发结案、无确认参数、审计内容和结案后 generation 2 claim。

## PR 5：赛狐回写 Outbox 基础设施

### 数据模型

新增 `shipping_sellfox_outbox`，每个 package-order 一条逻辑投递记录，关联现有 `submission_intent_id` 和成功 label/operation。建议状态：

`AWAITING_CONFIRMATION -> PENDING -> LEASED -> SENT -> VERIFIED`，异常为 `RETRYABLE`、`UNKNOWN_BLOCKED`、`CONFLICT`、`FAILED_FINAL`。

至少保存 `dedupe_key`、`request_hash`、`attempt_count`、`next_attempt_at`、`lease_owner/lease_expires_at`、`last_error_class/summary`、`created_at/updated_at`。唯一键覆盖逻辑 intent，避免标签成功回调或重复扫描创建两条工作项。

### 事务边界

- label operation 转 `SUCCEEDED` 时，在同一本地事务中创建不可执行的 `AWAITING_CONFIRMATION` outbox candidate；崩溃后由恢复流程执行同一 finalizer，避免成功标签没有回写候选。
- 操作者用明确 package/order 范围确认后，才构建或复用 SubmissionIntent、记录 confirmed_by，并把 candidate 转为 `PENDING`。标签成功本身不等于用户授权赛狐回写。
- 外部赛狐 HTTP 不放进数据库事务。Worker/CLI 先原子 lease，再调用现有 `SubmissionService.submit_intent()`。
- 网络不确定继续使用现有 submission scope `UNKNOWN_BLOCKED`，禁止自动重试。
- 明确重试类错误按有上限的指数退避进入 `RETRYABLE`；认证/配置问题停止自动重试并提示人工处理。
- HTTP 成功后必须 `packageDetail` 回读；tracking 匹配才 `VERIFIED`。不匹配进入 `CONFLICT`，不得覆盖本地 tracking 或重新购标。

### AI 优先 CLI

第一版不启常驻 Worker，先提供可由 Agent/计划任务调用的单次命令：

```bash
uv run python -m sellfox_shipping.cli sellfox-outbox-list --status PENDING --json
uv run python -m sellfox_shipping.cli sellfox-outbox-confirm --outbox-id 123 --actor supervisor --json
uv run python -m sellfox_shipping.cli sellfox-outbox-run-once --limit 10 --actor agent-name --dry-run --json
uv run python -m sellfox_shipping.cli sellfox-outbox-run-once --limit 1 --actor colleague-test \
  --package-sn <confirmed-test-package> --no-dry-run \
  --i-understand-side-effects --json
uv run python -m sellfox_shipping.cli sellfox-outbox-verify --outbox-id 123 --actor agent-name --json
```

生产真调必须同时满足：明确 `--package-sn` 或 `--outbox-id`、`--no-dry-run`、`--i-understand-side-effects`、非空 actor。第一轮真实测试 `--limit` 强制为 1；不得提供无范围的全量真调。

### 验收与同事测试交接

- 单元测试覆盖重复 candidate、未经确认不可 lease、确认范围与 actor、lease 竞争、进程崩溃后 lease 过期、退避、UNKNOWN 阻断、回读匹配与冲突。
- mock 集成测试证明 outbox 重试不会触发 carrier create。
- 同事真实测试前由用户确认一个测试包裹和赛狐账号；记录测试前 trackNo、请求 intent/outbox ID、HTTP 摘要、回读值和最终状态。
- 未获确认时只运行 dry-run 和 readback，不执行真实 `submitToPlatform`。

## 推荐顺序与 PR 所有权

| 顺序 | PR | 主要文件所有权 | 依赖 |
|---|---|---|---|
| 1 | 只读 operation CLI | `cli.py`, repository 查询, CLI tests | #136 |
| 2 | carrier error taxonomy | carrier clients, `label_service.py`, taxonomy tests | PR 1 可并行评审 |
| 3 | provider ID resume | recovery service, carrier query adapters, migration/tests | PR 2 |
| 4 | UNKNOWN 人工结案 | investigation model/CLI/migration/tests | PR 1-3 |
| 5 | Sellfox outbox | submission/outbox service, migration/CLI/tests | PR 3；真实测试可延期 |

每个 PR 从最新 `origin/main` 建独立分支和 worktree。若同事正在修改 `cli.py` 或 `package_repository.py`，优先串行合并，避免在这两个高重叠文件上并行开发。

## 总体验收

- AI Agent 能仅通过 CLI JSON 找到阻断项、判断允许动作、恢复带 provider ID 的标签并生成完整审计。
- 任意 resume、人工结案或赛狐回写路径都不能调用 carrier create。
- 无 provider ID 的不确定购标在无权威证据时永不释放。
- 赛狐回写失败只影响 outbox/submission 状态，不影响已购标签和 carrier operation。
- 所有数量报告满足 `input = success + skipped + failed + unmatched/conflict`，无静默丢弃。
- 定向及全量 `uv run pytest tests/sellfox_shipping -q` 通过，migration 覆盖干净库、正常历史库和冲突库。
- `git diff --check` 和 AGENTS.md 四组凭证扫描零输出。
