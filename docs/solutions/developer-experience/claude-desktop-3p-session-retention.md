---
okf: v0.1
type: Reference
title: Claude Desktop 3P 长对话保留 — 30 天清理、transcript 映射与归档
date: 2026-10-19
category: developer-experience
module: tooling
problem_type: developer_experience
component: tooling
severity: high
applies_when:
  - 用户有多段 Claude Desktop/Claude Code 长对话需要保留、继续或迁移
  - 要确认 Desktop 3P 会话与 ~/.claude/projects transcript 的对应关系
  - 准备换 DSH/Pi 前评估历史对话的可迁移性
tags: [claude-desktop, claude-code, sessions, cleanup-period, transcript, retention, handoff]
related_components: [tooling]
---

# Claude Desktop 3P 长对话保留 — 30 天清理、transcript 映射与归档

## Context

用户有大量 Claude Desktop 实际长对话，担心换 harness 后丢失或无法继续。2026-10-19 实测本机
Desktop 3P 的 Code 会话存储，发现：**173 个会话元数据中，131 个 transcript 已不存在，且全部
超过 30 天**；40 个近期会话（另加 2 个较老的）仍有完整 transcript。这与 Claude Code 默认
`cleanupPeriodDays = 30` 高度吻合。

## Guidance

### 1. 存储布局

| 类型 | 位置 | 内容 |
|---|---|---|
| Desktop 3P Code 会话元数据 | `...\Claude-3p\claude-code-sessions\<account>/<workspace>/local_*.json` | `sessionId`、`cliSessionId`、`cwd`、`model`、`title`、`lastActivityAt` |
| Claude Code transcript | `~/.claude/projects/<encoded-cwd>/<cliSessionId>.jsonl` | 完整消息/工具调用 JSONL |
| Chat（非 Code）会话 | Desktop 本地存储（IndexedDB 等） | 与 Code transcript 不同；需第三方工具导出 |

- 元数据里的 `cliSessionId` 就是 transcript 文件名的主键。
- 本机 173 个元数据里 **42 个能对上 transcript**（去重后约 191 MB，最大单会话 22.9 MB）；
  **131 个缺失，全部 >30 天**。

### 2. 保留策略

- Claude Code 默认在启动时清理超过 `cleanupPeriodDays`（默认 30 天）的 transcript；
  **0 不合法**，没有官方“永不清理”开关。
- 设大值：`~/.claude/settings.json` → `"cleanupPeriodDays": 3650`。
- `desktopSessionCleanupPeriodDays` 是 Desktop/Cowork 的另一条保留设置（默认 0），
  需要 Claude Code v2.1.248+；3P 内嵌 2.1.119 不支持，别把它当唯一保护。
- 定期把 `~/.claude/projects/` 归档到 Claude 管理目录之外（本机已归档到
  `D:\Work\赛狐\_backups\claude-transcripts-20261019`）。

### 3. 继续已有对话

- **已匹配会话**：独立 Claude Code CLI 可直接
  `claude --resume <cliSessionId>`（同一 `~/.claude/projects`）。
- **DSH / Pi**：session 格式不同，**不能直接读 Claude Code JSONL**；要迁移只能转换或
  用 handoff brief（`docs/handoff-brief-template.md`）。
- **Chat 会话**：不是 Code transcript；可用 `claude-explorer`、`unified-cowork` 等第三方工具
  导出 Markdown，但没有官方 DSH/Pi 导入。

### 4. 推荐做法

1. 先把 `cleanupPeriodDays` 调大，避免继续丢。
2. 立刻归档现存 transcript + 元数据，并生成 manifest（sessionId/title/cwd/size）。
3. 重要老对话先在 Claude 里用 `--resume` 继续；新长任务另写 handoff brief 给 DSH/Pi。
4. 已缺失的 131 条只能查 NAS/其他备份，Claude Code 本身无法恢复。

## Why This Matters

长对话是不可再生的上下文资产。换 harness、升级客户端或清理策略都可能在用户不知情时删除
transcript；等到需要 resume 时才发现只剩元数据，代价远高于提前设一个大保留期。

## When to Apply

- 换 AI 客户端/harness 前。
- 完成一个跨多天的长项目后。
- 发现 `/resume` 列表里少了旧会话时。
- 要给 DSH/Pi 做 handoff、需要找原始 transcript 时。

## Examples

```bash
# 看某个会话的 transcript 是否存在
ls ~/.claude/projects/<encoded-cwd>/<cliSessionId>.jsonl

# 继续会话（独立 Claude Code CLI）
claude --resume <cliSessionId>

# 归档（示意；目标必须放在 repo 外）
robocopy "$env:USERPROFILE\.claude\projects" "D:\Work\赛狐\_backups\claude-transcripts" /E
```

## Related

- `docs/research/2026-10-19-deepseek-1017-agent-harness-research.md` §8 — 长对话与 Pi 场景
- `docs/handoff-brief-template.md` — 跨 harness handoff 模板
- `docs/solutions/tooling-decisions/deepseek-1017-harness-selection-cost-cache.md` — 选型与成本
- Claude Code sessions 文档：https://code.claude.com/docs/zh-TW/sessions
- cleanupPeriodDays 调查：https://dev.classmethod.jp/en/articles/claude-code-conversation-history-retention/
