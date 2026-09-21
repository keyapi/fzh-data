---
okf: v0.1
type: Reference
title: git worktree 新分支的 upstream 被指成 main —— 裸 push 的隐藏方向
date: 2026-09-21
category: developer-experience
module: tooling
problem_type: developer_experience
component: tooling
severity: high
applies_when:
  - "新建 worktree / 新分支之后"
  - "`git branch -vv` 里某个分支跟着 `[origin/main]` 而不是它自己"
  - "排查「我的提交怎么跑到 main 上了」"
  - "换新机器 / 新克隆 —— 本设置是 repo-local，clone 后不存在"
tags: [git, git-worktree, upstream, push-default, main-branch, agent-safety]
---

# git worktree 新分支的 upstream 被指成 main

## Context

三个 Agent（Claude Code 的 `EnterWorktree`、Codex、Cursor）在本仓库大量创建 worktree，光 `git worktree list` 就有 **134 个**。2026-09-21 排查发现：**84 个本地分支的 upstream 被指成 `refs/heads/main`** —— 即"这些分支的上级是 main"。

这不是谁手滑，是 git 的**设计行为**：当一条新分支从**远端跟踪引用**（这里是 `origin/main`）创建时，`branch.autoSetupMerge`（默认 `true`，本仓库与全局都未设置）会让 git 把它设成跟随那个远端分支 —— 语义是"你在建 main 的本地副本"。对"新特性分支"这个语义是错的。

排查时的配置基线（git 2.35.2）：`branch.autoSetupMerge` 未设置、无 `include`、`push.default` 未设置、无 `.git/hooks`（只有 `.sample`）、107 个 `config.worktree` 里都没有 `branch`/`push` 设置。

## Guidance

### 怎么查（一条命令体检）

```bash
# 谁把 upstream 指向了 main（排除 main 自身）
git config --get-regexp '^branch\..*\.merge$' \
  | grep 'refs/heads/main$' \
  | grep -v '^branch\.main\.merge'
# 空输出 = 干净

# 现象级视角：这些分支会显示成跟 main 走
git branch -vv | grep '\[origin/main\]'
```

### 今天不会炸 —— 但 guard 是偶然的

| `push.default` | 裸 `git push` 的结果（实测） |
|---|---|
| 未设置 → git 默认 `simple` | **报错拒绝**：`fatal: The upstream branch of your current branch does not match the name of your current branch.` → main **不动** |
| `upstream` | **真的推上去**：`feat -> main` ⚠️ |
| `current` | 推 `feat -> feat`（安全） |

本仓库 `push.default` 未设置，所以现状是 **fail-safe**：裸 `git push` 只会报错停下。**但这是"没人去改过那个默认值"，不是有意设的护栏** —— 任何工具或人把 `push.default` 改成 `upstream`，裸 push 就开始往 main 推。

> ⚠️ **二级陷阱：那段报错本身会把人引到违规操作上。** 它的原文提示是
> `git push origin HEAD:main` —— 照抄就把当前分支推进了 main。
> 修好 upstream 之后，提示会变成安全的 `git push --set-upstream origin <你的分支名>`。

### 根因对照表（实测，git 2.35.2）

| 创建方式 | 自动设 upstream？ |
|---|---|
| `git worktree add -b X <path> origin/main` | ✅ 设为 `origin/main` ← **元凶**（输出会明说 `branch 'X' set up to track 'origin/main'`） |
| `git worktree add -b X <path>`（无起点） | ❌ 不设 |
| `git worktree add -b X <path> main`（本地 main） | ❌ 不设 |
| `git worktree add --no-track -b X <path> origin/main` | ❌ 不设 |

**已排除本仓库自身**：仓库内没有任何 `.ps1`/`.py`/`.sh`/`.md` 调用 `worktree add`，没有 `.claude/settings.json` 覆盖，`.git/hooks` 只有样本文件。→ 是**外部 worktree 工具**传了 `origin/main` 当起点。

旁证：排查途中又冒出 1 个同类分支（`claude/laughing-euler-8c4d54`），说明**另有会话正在并发创建**，这个模式还在持续产出。

### 修法（2026-09-21 已实施）

**① 清存量**（本次共处理 84 个分支）

```bash
# 已推到 origin 且同名 → 指回它自己
git branch --set-upstream-to=origin/<name> <name>

# 还没推过 → 直接摘掉错误标签，等 `git push -u` 时自然会设对
git branch --unset-upstream <name>
```

> 实测：`git branch --unset-upstream` 对**正被其他 worktree 占用**的分支同样有效，不需要先切过去。（本次 61 个受影响分支正被某个 worktree 占用。）

**② 防复发**（一行，仓库级）

```bash
git config branch.autoSetupMerge false
```

实测效果：
- 从 `origin/main` 建分支**不再**自动设 upstream；
- `git push -u origin <name>` **仍然**能正确建立 upstream（`-u` 是显式请求，不受此项影响）；
- 代价：`git checkout -b foo origin/bar` 这类"本地副本"用法不再自动跟随，需要显式 `--track` 或之后 `push -u`。本仓库 AGENTS.md 第 8 条本来就要求显式 `git push -u origin <branch>`，所以此代价实际为零。

> 坑：`git config branch.autoSetupMerge simple` 会报 `fatal: bad boolean config value 'simple'` —— git 2.35.2 只接受 `true` / `false` / `always`。

> ⚠️ **`branch.autoSetupMerge` 是 repo-local（`.git/config`），不会随 clone 走。** 换新机器 / 新克隆后默认值又变回 `true`，隐患复活。要真正跨机器持久，得加进 `setup.ps1`（clone 后必跑的那一步）—— 本次**未做**，待确认（见「遗留」）。

**③ 没上 pre-push hook**：本次没加。hook 不进版本库，要对同事生效还得配 `core.hooksPath` 或写进 `setup.ps1`，成本和 ② 重复。

### 同一根因的另一个形态

`merge` 指向**别的分支**（不一定是 main）也是这个机制。本仓库有 4 个：

```
review-141 → claude/gifted-lamarr-7ffe1d
review-142 → codex/sellfox-shipping-label-operation-cli
review-180 → feature/platform-account-reconciliation
nas-visuals-review → dev/jack-wq-ops-nas-visuals
```

`review-*` 看起来是**有意**跟随"被审查的那个分支"（`-b review-141 <path> origin/<被审查分支>` 的自然结果），所以本次**一个未动**。若要一并收敛，判据是"这个分支是否真的该跟随目标分支"。

## Why This Matters

AGENTS.md 第 8 条是硬规则：**永远不直接 push main**，唯一例外是紧急 revert。而这个配置把"feature 分支内容推进 main"变成一条**只差一个默认值**的路径。

它同时**极其隐蔽**：`git branch -vv` 里显示 `[origin/main]`，读起来像"我这个分支是基于 main 起的"，完全不像错误配置；git 不报任何错；本次也是靠"两个分支裸 push 行为异常"才被抓到的。

## When to Apply

- 新建 worktree / 新分支之后（尤其是通过 Agent 工具建的）。
- 看到 `git branch -vv` 里某分支跟着 `[origin/main]`。
- 排查"提交跑到 main 上了"。
- **换新机器 / 新克隆后**必须重设 ②（repo-local，不随 clone 走）。

## Examples

```bash
# ── 体检 ──────────────────────────────────────────────
git config --get-regexp '^branch\..*\.merge$' | grep 'refs/heads/main$' | grep -v '^branch\.main\.merge'
git worktree list --porcelain | grep -c '^worktree '   # 本仓库 134 个

# ── 已确认要修时：先备份配置，再分组处理 ────────────────
cp .git/config .git/config.bak-$(date +%Y%m%d-%H%M%S)

# 分两类：origin 上有同名分支的 / 没有的
git config --get-regexp '^branch\..*\.merge$' | grep 'refs/heads/main$' \
  | sed 's/^branch\.//; s/\.merge .*//' | grep -vx main | sort > /tmp/aff.txt
git for-each-ref --format='%(refname:short)' refs/remotes/origin/ \
  | sed 's|^origin/||' | sort > /tmp/orig.txt

comm -12 /tmp/aff.txt /tmp/orig.txt   # → set-upstream-to=origin/<n>
comm -23 /tmp/aff.txt /tmp/orig.txt   # → unset-upstream

# ── 防复发 ────────────────────────────────────────────
git config branch.autoSetupMerge false

# ── 验证（--dry-run，不会真的推）───────────────────────
git push --dry-run
# 期望：fatal: The current branch <name> has no upstream branch.
#       To push ... use  git push --set-upstream origin <name>
# 而不是：... git push origin HEAD:main        ← 说明 upstream 还指错
```

## Related

- [`AGENTS.md`](../../../AGENTS.md) 第 8 条 —— 本隐患直接抵触的硬规则
- [`CONTRIBUTING.md`](../../../CONTRIBUTING.md)「Git Worktree 创建（Windows 特别说明）」 —— 已补本条的 pitfall
- [Windows 上 worktree 的 CLAUDE.md：symlink 还是 stub](windows-worktree-claude-md-symlink.md) —— 同一批 worktree 相邻的坑（`core.symlinks`）
