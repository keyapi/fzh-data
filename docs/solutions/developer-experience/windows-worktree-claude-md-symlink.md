---
okf: v0.1
type: Reference
title: Windows 上 worktree 的 CLAUDE.md：symlink 还是 stub，取决于开发者模式
date: 2026-09-21
category: developer-experience
module: tooling
problem_type: developer_experience
component: tooling
severity: medium
applies_when:
  - "在 Windows 上创建 git worktree（Claude / Codex / Cursor 都可能用）"
  - "worktree 里 Claude 好像没读到 AGENTS.md 正文 / 项目守则"
  - "要跑 setup.ps1，纠结在哪儿跑、跑完为什么 CLAUDE.md 变脏"
  - "发现 CLAUDE.md 是 git 跟踪的 symlink（mode 120000）"
tags: [windows, git-worktree, symlink, claude-md, agents-md, developer-mode, setup]
---

# Windows 上 worktree 的 CLAUDE.md：symlink 还是 stub

## Context

三个 Agent（Claude Code / Codex / Cursor）共用一套事实源：**`AGENTS.md` 是唯一源头**，`CLAUDE.md` 在 git 里是 symlink（mode 120000）指向它，让 Claude 也有个入口。`~/.claude/skills/*` 同样是链接，把 `.agents/skills/*` 暴露给 Claude。

Windows 上普通权限**建不了文件符号链接**（目录可以，走 junction）。2026-09-21 实测发现 `CONTRIBUTING.md` 里那条老结论 —— "开启开发者模式会让 worktree 创建因权限不足失败" —— **已经反向失效**：开发者模式正是提供这个权限的东西。开着它，`core.symlinks=true` 建 worktree 完全成功。

## Guidance

### 两种状态

| 开发者模式 | `core.symlinks` | 得到的 `CLAUDE.md` | git | 该 worktree 里 Claude 能读到 AGENTS.md |
|---|---|---|---|---|
| **开（推荐）** | `true` | 真 symlink → `AGENTS.md` | 干净 | ✅ |
| 关 | `false` | 1 行 stub（内容就是字符串 `AGENTS.md`） | 干净 | ❌ 读不到正文 |

**关键坑：本仓库 `.git/config` 把 `core.symlinks` 显式设成了 `false`，worktree 共享这份配置** —— 所以即使开发者模式已开，**不传 `-c` 覆盖，建出来的仍是 stub**。实测确认。

### 推荐的创建方式

```bash
# 从主 repo 目录（如 D:\Work\赛狐\Cursor）执行，一次性设好
git config core.symlinks true
git worktree add <path> -b <branch-name>

# 不想改配置就每次显式带
git -c core.symlinks=true worktree add <path> -b <branch-name>
```

设 `core.symlinks=true` 后实测：worktree 建成功，`CLAUDE.md -> AGENTS.md` 是真 symlink，且 `git status` 干净。

### `setup.ps1` 只在主仓库根目录跑

`~/.claude/skills/*` 是**全机一份**的链接，必须指向**主仓库**，这样每个 worktree 里 Claude 读到的都是同一份（已合并的）skill。

**在 worktree 里跑会把链接指到那个临时 worktree**：链接随 worktree 删除而失效，而且 `New-SafeJunction` 对已存在路径直接 `[SKIP]`，**事后在主仓库再跑也修不回来**，只能手工删链接重建。

```powershell
# 删错指的链接（只删链接，不动目标）
(Get-Item "$env:USERPROFILE\.claude\skills\<name>" -Force).Delete()
```

开发者模式关着时，`setup.ps1` 对 `CLAUDE.md` 会退化成 `Copy-Item`（把 AGENTS.md 整份写进去）—— git 变脏，但 Claude 至少读得到内容。这个兜底是 commit `5582464` 特意加的（原先没有 `-ErrorAction Stop`，权限失败时 catch 不触发 → 文件直接丢失）。

## Why This Matters

**stub 状态特别隐蔽**：git 干净、不报任何错、`setup.ps1` 也显示成功，但那个 worktree 里的 Claude 系统提示里项目指令**只有 `AGENTS.md` 这 9 个字符**，AGENTS.md 正文（项目总纲、模块索引、第 8~11 条硬规则）完全没进来。今天就是先按老文档用 `core.symlinks=false` 建了 worktree，才踩到的。

反过来，`Copy-Item` 兜底让 git 变脏，容易被误当成"脚本有 bug"而去 `git restore` —— 那会把本机 Claude 打回什么都读不到的状态。

## When to Apply

- 在 Windows 上新建 worktree 前（三种 Agent 都可能建）。
- 发现某个 worktree 里 Claude 表现得"不知道项目规矩"时。
- 纠结 `setup.ps1` 在哪儿跑、跑完 `CLAUDE.md` 为什么变脏时。

## Examples

```bash
# 一次性（开发者模式已开）
git config core.symlinks true

# 验证某个 worktree 的状态
git worktree list
ls -la <path>/CLAUDE.md          # lrwxrwxrwx = 真 symlink；-rw-r--r-- 9 bytes = stub
```

### 批量修存量 worktree

设 `core.symlinks=true` 之后，仍是 stub 的 worktree 会立刻在 `git status` 里显示 **`T CLAUDE.md` + `T .claude/skills`**（typechange：git 期望 symlink，实际是普通文件）。原地重新检出这两个条目即可，**只碰它们、不动任何其他文件**，改完 `git status` 干净：

```bash
git -C <worktree-path> checkout -- CLAUDE.md .claude/skills
```

批量扫时**务必先按工作区内容筛选**，只处理"除这两行 typechange 外别无改动"的 worktree；带在制品的（有些上千个文件）一律跳过 —— 那些是别的 Agent 正在干的活。2026-09-21 实测：134 个 worktree 里 88 个属"纯 typechange"，全量扫完 0 失败、`status` 归零，44 个带在制品的一个未动。

## Related

- [`CONTRIBUTING.md` 的「Git Worktree 创建（Windows 特别说明）」](../../../CONTRIBUTING.md) — 本节结论已回写
- [`ce-okf` skill](../../../.agents/skills/ce-okf/SKILL.md) — 「多 Agent 并存」一节同样记了这条
- [Windows Codex/Cursor：PowerShell `&&` 与 GBK/UTF-8](windows-codex-powershell-utf8.md) — 同目录的 Windows 环境坑
