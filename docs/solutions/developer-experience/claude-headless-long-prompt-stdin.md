---
okf: v0.1
type: Reference
title: Windows 下 claude -p 长提示词必须走 stdin，不能塞进 argv
date: 2026-11-03
category: developer-experience
module: dingtalk_group_harvest
problem_type: developer_experience
component: tooling
severity: medium
applies_when:
  - "用 Python subprocess 调 claude -p 做批量摘要 / 周报"
  - "提示词包含长文档或 JSON，调用静默失败并回退到模板"
tags: [claude-cli, subprocess, windows, command-line-limit, stdin, headless]
---

# Windows 下 claude -p 长提示词必须走 stdin

## Problem

周报生成用 `claude -p` 做润色：把整周消息 JSON + 结构化初稿拼成提示词，再 `subprocess.run([cli, "-p", prompt])`。在 Windows 上，长提示词（约 8 万字符）会让调用失败，但程序只输出“已回退到结构化版本”，看起来像模型不配合，实际是**进程没启动成功**。

## Symptoms

- 周报文件末尾出现：`> Claude Code 调用失败，已输出结构化版本。`
- 手工用短提示词 `claude -p "只回复：OK"` 却正常。
- 代码里捕获了 `OSError`，没有把异常原因写进日志，所以现场只看到“失败”两个字。

## What Didn't Work

- 把提示词作为第三个 argv 传给 `claude -p`：Windows 命令行长度上限约 32K 字符，长 JSON 直接超限。
- 捕获 `OSError` 后静默回退：掩盖了根因，也让人误判为模型/账号问题。
- 用 `json.dumps(...)[:80000]` 截断 JSON：既没解决 argv 限制，还会把 JSON 截成非法结构。

## Solution

把提示词通过 **stdin** 传入，命令行只保留 `-p`：

```python
proc = subprocess.run(
    [cli, "-p"],
    input=prompt,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    timeout=600,
)
```

同时把回退原因写进产物（`Claude Code 返回失败（<code>）`），不要只写“失败”。

## Why This Works

- `claude -p` 在没有查询参数时会读取 stdin；stdin 不受 Windows 32K argv 限制。
- 长提示词不需要落到临时文件，也不会因为命令行转义/编码再出一次问题。
- 保留 `encoding="utf-8"` 覆盖 Windows 默认 GBK，避免中文乱码。

## Prevention

- 任何“把长文本传给外部 CLI”的场景，优先 stdin 或临时文件，不要把长文本拼进 argv。
- 子进程失败时记录 `returncode` + `stderr` 摘要；回退产物里写明原因。
- 测试时至少构造一个 >32K 的提示词跑一遍，不要只测短句。
- 相关坑：`claude -p` 可能向 stderr 打权限/模型警告，不要因此把 stdout 判为失败；以退出码和 stdout 是否有内容为准。

## Related

- 模块：`dingtalk/dingtalk_group_harvest/digest.py`
- `tooling-decisions/dingtalk-group-harvest-dws-user-identity.md`
- `developer-experience/windows-schtasks-worktree-path-trap.md`
