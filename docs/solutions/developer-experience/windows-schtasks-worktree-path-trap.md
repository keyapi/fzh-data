---
okf: v0.1
type: Reference
title: Windows 计划任务在 worktree 里注册会指向临时目录
date: 2026-11-03
category: developer-experience
module: dingtalk_group_harvest
problem_type: developer_experience
component: tooling
severity: medium
applies_when:
  - "在 git worktree 里注册 schtasks / Windows 计划任务"
  - "定时任务合并后突然找不到脚本，或 worktree 删除后任务失效"
tags: [windows, schtasks, git-worktree, scheduling, path, dingtalk]
---

# Windows 计划任务在 worktree 里注册会指向临时目录

## Problem

在 git worktree（`.claude/worktrees/<name>`）里运行定时任务安装脚本，脚本用 `(Get-Location).Path` 取仓库根，把**worktree 的绝对路径**写进了计划任务的 wrapper `.cmd`。功能当场能跑，但 worktree 是临时的：合并后一旦删除，计划任务仍指向已不存在的目录。

## Symptoms

- `schtasks /Query` 显示任务存在、状态 Ready，但下次触发时脚本找不到。
- 手动执行 wrapper 可能仍成功（worktree 还在）；删除 worktree 后才暴露。
- 任务名和日志都正常，容易误以为“已经上线”。

## What Didn't Work

- 只在 worktree 里注册、不做路径校验：任务指向 `D:\...\.claude\worktrees\<name>`。
- 用相对路径：schtasks 的起始目录不等于仓库根，`cd /d "%~dp0..\.."` 也会跟着 worktree 走。
- 把 wrapper 提交进 git：wrapper 是机器相关产物，提交后其他机器会拿到错误路径。

## Solution

1. **在 worktree 里可以注册用于当天验证，但合并后必须在主仓库根目录重跑一次安装脚本**，把任务重定向到主仓库。
2. 安装脚本用绝对路径，并在注册后校验：
   ```powershell
   $query = schtasks /Query /TN $taskName /V /FO LIST | Out-String
   if ($query -notmatch 'dingtalk_group_harvest') { throw "Task To Run 不含预期模块" }
   ```
3. wrapper 加入 `PATH=%USERPROFILE%\.local\bin`（DWS 等用户级 CLI 不在系统 PATH），并显式设置数据根目录：
   ```bat
   set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
   set "DINGTALK_HARVEST_ROOT=C:\Users\<user>\dingtalk_harvest"
   cd /d "D:\Work\<repo>"
   ```
4. wrapper 不提交 git；`.gitignore` 加 `scripts/run_harvest_*.cmd`。

## Why This Works

- 计划任务保存的是绝对路径；只有注册时所在的仓库根正确，路径才稳定。
- 注册后校验 `Task To Run` 能抓住“路径写错/指向 worktree”这类静默错误。
- 任务以当前交互用户运行，DWS 的用户 OAuth token 和用户级 PATH 才可用。

## Prevention

- 安装脚本打印并检查仓库根是否包含 `.claude\worktrees`；包含则提示“合并后需在主仓库重跑”。
- 在 README / AGENT_HANDOFF 写清这个前置条件。
- 任务触发时间避开整点（如 08:10 / 08:40），并确认电脑开机且用户已登录。
- 相关：`developer-experience/windows-worktree-claude-md-symlink.md`（同样强调 setup 脚本只在主仓库跑）。

## Related

- 模块：`dingtalk/dingtalk_group_harvest/scripts/install_harvest_schedule.ps1`
- `tooling-decisions/dingtalk-group-harvest-dws-user-identity.md`
- `developer-experience/claude-headless-long-prompt-stdin.md`
