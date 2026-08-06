---
okf: v0.1
type: Spec
title: sellfox_shipping 生产验收与 Jack Agent 交接规范
description: 定义已完成边界、生产验收矩阵、剩余任务优先级和无副作用测试规则
timestamp: 2026-08-05
---

# 生产验收与 Jack Agent 交接规范

## 结论

当前已完成的是“安全购标、恢复和人工结案核心”，不是完整 TMS，也尚未经过完整生产业务验收。下一位 Agent 应先证明已实现能力在历史数据库、CLI、Excel 和承运商测试环境中可运营，再决定下一项功能。

## Readiness Matrix

| 能力 | 状态 | 接手验收 |
|---|---|---|
| preflight、原子 claim、活动标签唯一性 | 已实现并自动化验证 | 复核并发 create-once 与阻断错误 |
| provider ID、ACCEPTED/LABEL_PENDING、resume | 已实现并自动化验证 | 复核恢复只 query/download，绝不 create |
| carrier error taxonomy | 已实现并自动化验证 | 复核 VITE/蜴国际确定性拒绝与不确定故障分类 |
| UNKNOWN_BLOCKED 人工结案 | 已实现并自动化验证 | 复核 evidence 归属、结论匹配、审计与槽位释放 |
| resume lease fencing | 已实现并自动化验证 | 复核过期 worker 不能落 label、转状态或释放新 lease |
| SQLite migration | Migration 0019 修复中 | 验证空库、0015 历史库、0018 半应用库和现有库备份副本 |
| Excel 导出/导入 | 已实现，需运营验收 | 验证文件哈希、重复导入、逐行成功/跳过/冲突/失败对账 |
| VITE/蜴国际真实链路 | 未完整验收 | 仅用户指定测试包裹和环境后进行 |
| 赛狐 trackNo 回写 | 代码完成（Outbox PR 1/2），待单包能力探针 | 按 [单包能力探针运行手册](sellfox-writeback-probe-runbook-2026-08-06.md) 执行；先 PROBE_ONLY，SAFE_TRACKNO_ONLY 后才可 SCOPED_BATCH |
| 公网安全 | 未完成 | 部署前完成 OIDC/CSRF/RBAC/secure cookie/PII 审计 |
| 每日三方对账 | 未完成 | 评估为下一项独立 PR，不静默丢失任何差异 |
| 取消与退款 | 部分完成 | 取消安全已完成；退款到账需独立状态和凭证 |
| 打印/交接 | MVP 可用，运营闭环未完成 | 评估 durable print job、重印理由、双扫与 Manifest |

## Jack Agent 第一阶段

1. 从最新 `origin/main` 创建独立 `feature/` worktree，先确认 migration head 与开放 PR。
2. 运行 `uv run pytest tests/sellfox_shipping -q`，验证空库、0015 到 head、半应用 0018 到 head。
3. 在数据库副本上运行 CLI 只读与本地写操作，检查 JSON envelope、exit code、actor 和 audit event。
4. 用合成数据复核 resume create-once、lease fencing、evidence resolution 和 Excel 重复导入。
5. 输出更新后的 readiness matrix，每项只能标为 `complete`、`implemented_not_live_validated`、`blocked_by_approval` 或 `deferred`。
6. 最多提出 3 个独立后续 PR，每个写明验收标准、非目标和是否会产生外部副作用。

## 推荐后续顺序

1. **生产验收与迁移可靠性**：当前必须完成。
2. **每日三方对账报告**：运营开始前优先，覆盖本地包裹、承运商标签/追踪号、赛狐状态；未匹配必须保留。
3. **公网安全收口**：仅在准备公网部署时升为阻塞项。
4. **取消与退款分离、打印交接、成本对账**：根据实际运营痛点分别立项。
5. **赛狐 outbox 能力探针**：代码已就绪，按 [运行手册](sellfox-writeback-probe-runbook-2026-08-06.md) 执行单包探针，记录能力结论后再开放批次。

## 禁止事项

- 不直接 push `main`，不清理主工作区未跟踪文件。
- 未经用户指定包裹和范围，不真实购标、取消、调用 `submitToPlatform` 或写回赛狐。
- 不把本地 `lizard-import-tracking` 成功解释为赛狐 UI `trackNo` 已更新。
- 未经用户指定包裹和范围，不真实调用 `submitToPlatform` 或写回赛狐；不提前引入 Karrio、PostgreSQL、消息代理或 cartonization。
- 不用自动化测试通过替代承运商沙箱证据和人工业务验收。

## 每个 PR 的门槛

- `uv run pytest tests/sellfox_shipping -q` 全量通过。
- `git diff --check` clean。
- AGENTS.md 规定的四组凭证扫描零输出。
- Markdown 遵守 OKF，并运行 `uv run python scripts/update_index.py`。
- 报告输入、成功、跳过、冲突、失败及差数去向。
