---
okf: v0.1
type: Reference
title: gh pr edit 会因 Projects classic 弃用而失败——改 PR 标题/body 要走 gh api PATCH（且管道会掩盖退出码）
date: 2026-09-22
category: developer-experience
module: tooling
problem_type: developer_experience
component: tooling
severity: medium
symptoms:
  - "gh pr edit <n> --title ... --body-file ... 报 GraphQL: Projects (classic) is being deprecated ... (repository.pullRequest.projectCards)"
  - "命令看着'跑过了'（因为接了 | tail 之类的管道），但 PR 标题/body 其实没变"
root_cause: "gh pr edit 会先查该 PR 的 projectCards；在弃用 Projects classic 后该 GraphQL 字段报错，整个命令中止"
resolution_type: workaround
tags: [gh-cli, pull-request, graphql, exit-code, pipe-masks-status]
---

# gh pr edit 的 Projects classic 故障

## Problem

要改一个已开 PR 的标题/正文时，`gh pr edit` 直接失败：

```
$ gh pr edit 262 --title "..." --body-file pr_body.md
GraphQL: Projects (classic) is being deprecated in favor of the new Projects experience,
see: https://github.blog/changelog/2024-05-23-sunset-notice-projects-classic/.
(repository.pullRequest.projectCards)
```

**改动没有生效**（标题仍是旧的），真实退出码是 **1**。本机 `gh version 2.71.2`。

## Symptoms

- 报错里出现 `repository.pullRequest.projectCards` —— 关键字是 **`projectCards`**，不是你的参数写错。
- `gh pr view <n> --json title` 回读发现**完全没变**。
- 如果命令串里接了管道（例如 `... 2>&1 | tail -3 && echo "下一步"`），你会看到报错却依然跑到了下一步 ——
  **`$?` 是管道最后一段（`tail`）的退出码，永远 0**。

## What Didn't Work

- 反复检查 `--title` / `--body-file` 的写法 —— 参数没问题，是 `gh` 在发 GraphQL 前置查询时就挂了。
- 换 `--body` / stdin 传 body —— 同一处报错（问题不在 body 怎么传）。
- 重开 PR 绕过 —— 没必要，代价大。

## Solution

改用 **REST API** 打补丁（不动 `projectCards`）：

```bash
gh api -X PATCH repos/<owner>/<repo>/pulls/<n> \
  -f title="新的标题" \
  -F body=@/absolute/path/to/pr_body.md \
  --jq '{title,state,url}'
```

- **`-f` 传短字符串，`-F key=@file` 从文件读长 body**（body 长的时候别硬塞进命令行）。
- 改完**必须回读校验**：

```bash
gh pr view <n> --json title,body,changedFiles,commits \
  --jq '{title, body_chars:(.body|length), changedFiles, commits:(.commits|length)}'
```

`gh pr create --body-file` 不受影响，正常工作；只有 `pr edit` 会踩这个。

## Why This Works

`gh pr edit` 走 GraphQL，而它取 PR 时会连 `projectCards` 一起查 ——
GitHub 弃用 Projects classic 后该字段报错，于是整条命令在**发出任何修改之前**就中止了。
`gh api -X PATCH .../pulls/<n>` 是 REST，查的是 PR 本身，不碰 `projectCards`，所以能正常改。

## Prevention

- **别让管道掩盖退出码**。写"改了 PR 就继续下一步"的脚本时，用
  `gh pr edit ... ; rc=$?` 或先重定向到文件再判断，而不是 `| tail`。
  本次就是靠"回读 PR"才发现标题没变 —— 报错行被 `tail` 淹没在输出里。
- **凡是改远端状态（PR / issue / 文件）的命令，改完一律回读确认**，不要只看命令有没有报错。
- 同类教训与本仓库既有那条一致：**报错点离根因很远时，先确认上一步是不是静默失败了**
  （见 `colab-shell-out-filename-spaces.md`）。

## Related

- `developer-experience/colab-shell-out-filename-spaces.md` —— 同一类"报错/成功信号不可信"的坑
- `.agents/skills/ce-okf/SKILL.md` —— 已经写了「PR body 必须走 `--body-file`，否则可能静默为空」；本文补的是**改**已有 PR 时的另一条路
