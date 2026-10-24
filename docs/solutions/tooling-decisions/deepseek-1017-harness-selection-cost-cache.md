---
okf: v0.1
type: Reference
title: DeepSeek 1017 Harness 选型 — Claude Code vs DSH vs Pi 的成本/缓存/Windows 现实
date: 2026-10-19
category: tooling-decisions
module: new-api-deployment
problem_type: tooling_decision
component: tooling
severity: medium
applies_when:
  - 要在 Claude Code / DeepSeek Harness / Pi / OpenCode 之间选 DeepSeek 1017 的日常入口
  - 需要估算长任务/批处理的 token 成本与缓存命中
  - 在 Windows 上跑 DSH 遇到 grantWrite / pytest cache / 127.0.0.1 问题
tags: [deepseek, deepseek-v4, flash-1017, claude-code, deepseek-harness, dsh, pi, prompt-cache, windows, cost]
related_components: [tooling]
---

# DeepSeek 1017 Harness 选型 — Claude Code vs DSH vs Pi 的成本/缓存/Windows 现实

## Context

用户原先用 Claude Desktop 3P（内嵌 Claude Code 2.1.119）通过公司网关 `api.vilavi.cn` 使用
`deepseek-v4-flash`。1017（DeepSeek-V4.1-Flash-1017）上线后，需要判断是否换独立 Claude Code CLI、
DeepSeek Harness（DSH）或 Pi；成本与缓存命中是关键指标。完整调研见
`docs/research/2026-10-19-deepseek-1017-agent-harness-research.md` 与
`docs/research/2026-10-19-ab-harness-results.md`。

## Guidance

### 1. 模型名与网关

- **没有 `deepseek-v4-flash-1017` 这个模型 ID**；1017 权重在 `deepseek-flash` /
  `deepseek-v4-flash` 后面。Claude Code 侧模型名要加 `[1m]`，否则按 200k 窗口自动压缩。
- 网关 Anthropic 端点 `https://api.vilavi.cn/`；OpenAI 兼容端点 `https://api.vilavi.cn/v1`。
- 计价以 `new-api-deployment/deepseek_time_pricing.py` 为准：高峰（周一至周五 9–12、14–18
  北京时间）未命中 ¥2/M、缓存 ¥0.04/M、输出 ¥8/M；空闲减半。**缓存命中比未命中便宜 50 倍**，
  所以成本杠杆是 **fresh input（未命中输入）**，不是总 token。

### 2. 实测结论（同一网关、同一 1017）

| 场景 | Claude Code | DSH native | DSH PTC | Pi |
|---|---|---|---|---|
| T1 只读工作流 | ✅ 17.4s / ¥0.0775 | ✅（danger-full-access）22.4s / **¥0.0375** | — | — |
| T2 小型编码 | ✅ **32s** / ¥0.1297 | ✅ 64s / **¥0.0486** | ✅ 93s / ¥0.0778 | 未测 |
| T2 缓存命中 | 69% | **95%** | 95.5% | — |
| T2 fresh input | 49k | **7.4k** | 11.9k | — |

- **DSH native 约为 Claude Code 的 0.37x 成本**，缓存命中 95% vs 69%；代价是慢约 2x。
- **PTC 不是自动省钱开关**：小任务上代码规划/调试反而增加输出与 fresh input。
- Claude Code 的 `total_cost_usd` 对未知模型是 `costBasis: unknown`，不能拿来比价。
- 第三方横向评测（Composio，同一 DeepSeek V4 Flash）：Pi 20/30、$0.028/任务；
  Claude Code 16/30、$0.195/任务；OpenCode 14/30。Pi 的 99.93% 缓存命中来自
  “少工具 + 只追加会话 + 静态系统提示”。

### 3. Windows 上 DSH 的真实摩擦与解法

- **`read-only` 沙箱会挡住 `uv` 缓存写入**，看起来像“模型不会跑”，实际是命令没执行。
  可信只读任务用 `DSH_PERMISSION_MODE=danger-full-access`；实测同一 T1 扫描 exit 0、
  仓库无改动。可写任务用 `C:\Users\zhang\dsh-workspace` 这类用户目录 +
  `UV_CACHE_DIR=<workspace>/.uv-cache`。
- `D:\dsh-workspace` 报 `SetNamedSecurityInfoW ... Win32 5`；即使 owner 是当前用户，
  沙箱仍可能因受限 token 缺 `WRITE_DAC` 失败。**优先 C: 用户工作区**，不要先改 D: ACL。
- pytest 在 `workspace-write` 下会留下 `pytest-cache-files-*` 并触发 ACL 拒绝：
  用 `-p no:cacheprovider` / `--ignore-glob='pytest-cache-files-*'` / `TMP` 放工作区内。
- `dsh web` 默认 host 实测不监听，必须 `--host 127.0.0.1 --port 3080`；PowerShell 启动器下
  `web` 会静默挂起，用 `cmd /c dsh web ...` 或 bash 直接启动。
- 网关兼容：DSH 默认发 `developer` role，需要 provider `compat: supportsDeveloperRole: false`；
  同时 `thinkingFormat: deepseek`。
- **WSL2 不是银弹**：官方 Windows 兼容页未把 WSL 列为支持面；社区 2026-10-09 实测明确
  “官方不支持 WSL”，需 `dsh-wsl-desktop` / `dsh-plugin-wsl-env` 等插件，并引入
  403/trustedHosts、目录选择器、TTY、代理、bubblewrap、pnpm 版本、`/mnt/d` 9P 慢等问题。
  本机 WSL 还缺 Linux Node 24（PATH 指向 Windows Node），`/mnt/d` worktree 的 `.git`
  指向 `D:/...`，`git status` 直接失败。

### 4. 选型建议

- **主力：独立 Claude Code CLI 2.1.303**（skills/hooks/MCP/worktrees 兼容最好、最快）。
- **成本敏感/批处理：DSH native**（0.37x 成本，95% 缓存；接受慢 2x 与 Windows 沙箱调优）。
- **长任务/成本实验：Pi**（99.93% 缓存、`pi-long-task`、8.6 万 Star；但默认无护栏、MCP 生态新）。
- **不推荐 OpenCode 作 Windows 主力**（内存泄漏/2.0 beta/成功率最低）。
- **WSL2** 只在 DSH 成为日常主力且愿意把 repo 迁到 WSL ext4 时考虑。

## Why This Matters

同一模型换 harness，实测成本差 2–2.7 倍、缓存命中差 26 个百分点；把 Windows 沙箱错误当成
模型能力问题会得出完全相反的结论。选型要同时看 **成功率、墙钟、fresh input、缓存命中**，
不能只看单价或跑分。

## When to Apply

- 给团队/个人选 DeepSeek 1017 的日常入口或批处理 harness。
- 估算长任务/月度 token 账单（先看 fresh input 与缓存命中）。
- 在 Windows 上首次配置 DSH、遇到 `grantWrite`/pytest cache/3080/403。
- 准备从 Claude Desktop 切到 DSH/Pi 前，评估会话迁移与 handoff。

## Examples

```bash
# Claude Code（token 由用户级启动器从父仓库 .env 读取）
claude-gw.cmd -p "<task>" --allowedTools "Bash,Read,Write,Edit,Grep,Glob" --output-format json

# DSH 可信只读任务（已验证扫描通过、仓库无改动）
DSH_PERMISSION_MODE=danger-full-access dsh headless --json "<task>"

# DSH 可写隔离目录
cd C:/Users/zhang/dsh-workspace
UV_CACHE_DIR="$PWD/.uv-cache" DSH_PERMISSION_MODE=workspace-write dsh headless --json "<task>"
```

## Related

- `docs/research/2026-10-19-deepseek-1017-agent-harness-research.md` — 完整调研与来源
- `docs/research/2026-10-19-ab-harness-results.md` — A/B 数据、PTC、WSL2、沙箱
- `new-api-deployment/deepseek_time_pricing.py` — 网关实际计价
- `docs/handoff-brief-template.md` — 从老对话切到 DSH/Pi 的 brief 模板
- `docs/solutions/developer-experience/claude-desktop-3p-session-retention.md` — 长对话保留
- `docs/solutions/developer-experience/dotenv-bom-source-leak.md` — `.env` BOM/source 坑
