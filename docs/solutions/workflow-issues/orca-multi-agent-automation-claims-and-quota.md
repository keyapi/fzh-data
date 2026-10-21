---
okf: v0.1
type: Reference
title: Orca 多 Agent 自动化的领取锁、超时恢复与 Codex 额度探针
date: 2026-10-21
category: workflow-issues
module: development_workflow
problem_type: workflow_issue
component: tooling
severity: high
applies_when:
  - "用 Orca automations 让 Claude Code 与 Codex CLI 周期性接力执行任务"
  - "定时任务重复开跑、已完成任务仍被锁挡住，或超时后不确定能否重派"
  - "无人值守时需要判断 Codex 5h 额度是否还够，但终端页脚不显示百分比"
  - "屏幕锁定或权限弹窗无法人工点击，Agent 会话卡在确认框"
tags: [orca, automation, multi-agent, task-claim, stale-lock, codex-quota, headless]
---

# Orca 多 Agent 自动化的领取锁、超时恢复与 Codex 额度探针

## Context

2026-10-21 用 Orca 把「Claude 实现 → Codex 独立复审 → Claude 返修」跑成周期任务。
调度层由四块组成：

- `precheck.py <task>` 原子领取：`locks/<task>.lock` 用 `O_EXCL` 创建，成功后把
  `state.json` 的任务置 `in_progress` 并写 `claimed_at`。
- `state_update.py` 带全局锁（`state.lock`）做 read-modify-write，避免两边同时写坏 JSON。
- Orca automation 定时触发 fresh session；`--precheck` 命令在派发前跑。
- `quota_check.py` 从 Codex TUI 页脚抓 `5h limit: X% left`，写入 `state.json`。

实际跑下来暴露了四个机制性问题，都会造成**重复执行、假完成或空等**。

## Guidance

### 1. 定时 run 走 precheck，手动 `automations run` 不走

`orca automations run <id>` 是强制立刻跑，**跳过 precheck**。如果直接手动触发，
任务不会被 claim，下一次定时触发可能再开一个会话。

做法：手动 run 之后**立刻补跑一次** `precheck.py <task>`（或 `precheck_cross.py`），
让状态与锁反映真实占用；或者先停用该 automation，再手动跑。

### 2. 锁必须在状态转出 `in_progress` 时释放

`precheck.py` 的锁 TTL 取任务的 `timeout_minutes`（这里是 90–180 分钟），
但 worker 完成后不会自己删锁。结果是：任务已 `completed`，下一轮把状态改回 `ready`
时，新 precheck 仍报 `task already claimed`，复审被白等一轮。

做法：在 `state_update.py status` 里，当状态不等于 `in_progress` 时删除
`locks/<task>.lock`。已完成/已阻塞 worker 的锁是残留，不是活跃占用。
清理前确认旧终端的 `status=exited`，不凭锁文件判断 worker 是否还在跑。

### 3. 超时只能标 `needs_verification`，不能自动重派

超时只证明 claim 过期，不证明旧进程退出。自动重派可能与仍在写的 worker 并发，
造成重复提交或证据互相覆盖。

`precheck.py` 的处置：把状态改成 `needs_verification`，写
`recovery_note=stale claim; verify old worker/terminal before redispatch`，返回非零。
人工或协调者先看终端，再决定重派。

### 4. 额度页脚在“健康”时消失，探针要有超时预算

Codex TUI 只在低于警告阈值时显示 `⚠ 5h limit: X% left · resets at HH:MM`。
5h 额度重置后如果用量健康，这一行会消失，`quota_check.py` 抓不到数字。
直接把它当失败会把复审永久挡住。

兜底做法（已落地）：

```text
无页脚 marker
  → 在临时目录跑一次极小 codex exec：
    codex exec --json --skip-git-repo-check \
      -c sandbox_mode="read-only" -c approval_policy="never" \
      "Reply OK only"
  → 输出含 "turn.completed" 才标记 fresh=true / pause=false
  → 探针失败才 pause=true
```

两个配套细节：

- **precheck 超时**：探针本身要几十秒，原 60 秒的 `precheck-timeout` 会直接超时
  （实测 `Precheck timed out after 60s`）。改为 180 秒。
- **19:00 后要求新鲜读数**：重置可能延迟，precheck 要求 `quota.updated` 不早于 19:00；
  探针成功会写 `updated`，所以只探一次即可，不要每 15 分钟都探。

### 5. 无人值守时不要依赖 GUI 权限弹窗

屏幕锁定后，`SetForegroundWindow` / `SendKeys` / Orca `computer press-key` 都不可用
（报 `window_not_focused`），`terminal send` 遇到权限弹窗还会报
`agent_prompt_blocked`，`--retry-request` 也解不开。

稳定的替代：新开终端跑 headless CLI，显式给权限模式：

```bash
claude -p '<task text>' --permission-mode auto --output-format json > run.json 2>&1
```

Orca 的 Claude automation 只允许 `--extra-agent-args` 传
`--model / --effort / --add-dir`；`--permission-mode` 会被拒。
所以要么用 headless 终端，要么在会话启动后立刻切 auto（需要可交互）。

### 6. fresh session 不是 fork

automation 每次是全新上下文，只靠 CONTROL/state/交接文档续接。
给它的提示词必须写**绝对路径**，并假设它不知道上一轮聊了什么。
把评审报告复制进工作区，避免读工作区外目录触发额外权限请求。

## Why This Matters

上述四点共同决定“任务到底有没有在跑”：

- 不补 precheck：两个会话写同一份证据，评审看到的是混合状态。
- 不释放锁：已完成任务把下一轮复审挡在门外，表现为“调度没反应”。
- 超时自动重派：旧会话未退出时产生重复提交，证据 hash 对不上。
- 把“页脚消失”当失败：额度明明已重置，复审却一直不跑。

这些都不是业务逻辑问题，却会直接造成**假完成、重复执行、证据丢失**。

## When to Apply

- 用 Orca / 类似调度器跑多 Agent 周期任务时。
- 添加任何“定时 + 原子领取 + 超时恢复”机制时。
- 无人值守会话（夜间、锁屏、远程）需要跑带权限的 CLI 时。

## Examples

- 手动 run 后立即补 `precheck_cross.py`：`claimed G1B-CROSS-REVIEW for codex`，
  避免 19:15 定时任务重复开跑。
- 清理 19:04 遗留锁后，19:18 的复审正常派发；随后在
  `state_update.py` 加入“非 in_progress 即释放锁”，后续轮次不再需要手工删锁。
- 页脚从 `23% left · resets at 18:51` 变成只剩 `⚠ 5 warnings`：
  探针 `turn.completed` 成功，记为 `source=probe:codex-exec`，
  19:00 后的三轮关键复审全部放行。
- 锁屏期间 headless `claude -p --permission-mode auto` 完成 86 轮返修，
  `permission_denials` 仅包含它自己尝试提交状态的那条（由协调者代为提交）。

## Related

- 返修—复审循环与状态三分：`docs/solutions/best-practices/multi-agent-rework-review-status-separation.md`
- 供应链整合控制页与证据（本轮产物）：PR #300 / PR #301；
  控制页 `docs/research/supply-chain/2026-10-20/claude/control/CONTROL.md`
- `docs/solutions/best-practices/knowledge-base-anti-rot.md`（收尾体检机制）
