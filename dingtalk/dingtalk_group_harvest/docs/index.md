---
okf: v0.1
type: Index
title: dingtalk_group_harvest — 文档索引
timestamp: 2026-11-03
---

# dingtalk_group_harvest 文档索引

| 你需要... | 读这个 |
|---|---|
| 人读入口 | [README.md](../README.md) |
| Agent 交接 | [AGENT_HANDOFF.md](../AGENT_HANDOFF.md) |
| 周报提示词 | [prompts/digest.md](prompts/digest.md) |
| DWS 选型与完整性账本 | [../../../docs/solutions/tooling-decisions/dingtalk-group-harvest-dws-user-identity.md](../../../docs/solutions/tooling-decisions/dingtalk-group-harvest-dws-user-identity.md) |
| `claude -p` 长提示词坑 | [../../../docs/solutions/developer-experience/claude-headless-long-prompt-stdin.md](../../../docs/solutions/developer-experience/claude-headless-long-prompt-stdin.md) |
| 计划任务 worktree 路径坑 | [../../../docs/solutions/developer-experience/windows-schtasks-worktree-path-trap.md](../../../docs/solutions/developer-experience/windows-schtasks-worktree-path-trap.md) |
| 变更 | [log.md](log.md) |

## 核心事实

- 数据源：DWS（钉钉官方 CLI，个人 OAuth 身份）。
- 群：运营2部/3部/4部 AI项目沟通群。
- 归档根：`%USERPROFILE%\dingtalk_harvest`（仓库外）。
- 采集：每日 08:10；周报：每周一 08:40。
- 不依赖群机器人；不回推群。
