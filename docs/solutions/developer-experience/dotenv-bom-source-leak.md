---
okf: v0.1
type: Reference
title: 父仓库 .env 的 BOM + 畸形行 — 不要用 bash source 读取
date: 2026-10-19
category: developer-experience
module: tooling
problem_type: developer_experience
component: tooling
severity: medium
applies_when:
  - 要从 D:\Work\赛狐\Cursor\.env 读取 token/凭证
  - Windows 上出现 BOM/UTF-8/密钥被打印到终端
  - 写启动器/脚本需要加载 .env
tags: [dotenv, bom, windows, powershell, credentials, shell, setup]
related_components: [tooling]
---

# 父仓库 .env 的 BOM + 畸形行 — 不要用 bash source 读取

## Problem

父仓库 `D:\Work\赛狐\Cursor\.env` 有两处格式问题：

- line 1 带 UTF-8 BOM；
- line 6 的 `VITE_API_KEY` 值是从表格里粘出来的
  `API Key | \`<token>\` |`，不是标准 `KEY=VALUE`。

用 bash `source .env` 加载时，shell 把 `API` 当成赋值、把后面的 `Key:` 当成命令执行，
并把 token 打印到终端。

## Symptoms

- 终端出现 `line 6: Key: command not found`，后面跟着一段密钥；
- `source` 之后 `VITE_API_KEY` 的值是 `API`（截断），后续请求失败；
- 用 `grep`/脚本检查时看到“值含空格”，但不是所有工具都会报错。

## What Didn't Work

- 直接 `source "/d/Work/赛狐/Cursor/.env"`：会执行畸形值，泄露凭证。
- 只 `grep OPENAI_API_KEY`：能读到目标变量，但没有解决 `VITE_API_KEY` 的畸形；
- 用 PowerShell 5.1 `Set-Content -Encoding UTF8` 修：会重新写入 BOM，问题复发。

## Solution

1. **先备份**（放 repo 外）：`C:\Users\zhang\.claude\backups\.env.bak-<timestamp>`。
2. 用 Python `encoding='utf-8-sig'` 读取，按行处理：
   - 去掉 BOM；
   - line 6 用正则提取反引号里的 token，改写为 `VITE_API_KEY=<token>`；
   - 以 `utf-8`、`newline=''` 写回（保留原 CRLF）；
   - 验证：无 BOM、无值含空格、行数不变、除 line 6 外内容 hash 不变。
3. 启动器**不要整体 source**；按行匹配目标 key：
   ```powershell
   $line = Get-Content -LiteralPath $envFile -Encoding UTF8 |
       Where-Object { $_ -match '^OPENAI_API_KEY=' } |
       Select-Object -First 1
   $env:ANTHROPIC_AUTH_TOKEN = ($line -split '=', 2)[1].Trim()
   ```
4. 2026-10-19 已修复本机文件；备份在
   `C:\Users\zhang\.claude\backups\.env.bak-20261019-154524`。

## Why This Works

- 去 BOM 后，任何按 UTF-8 读取的工具都不会在第一个 key 前看到 `﻿`；
- 标准化 `KEY=VALUE` 后，`source`/dotenv/PowerShell 都能正确解析；
- 按行匹配只导出需要的变量，**不会执行值里的任何内容**。

## Prevention

- Windows 写文本优先 `pwsh` 7 的 `utf8NoBOM`；不要用 PowerShell 5.1 的
  `Set-Content -Encoding UTF8`。
- Python 读带 BOM 的文件用 `encoding='utf-8-sig'`；Node 读后去掉 `﻿`。
- 不要整体 `source .env`；用按行匹配或 dotenv 解析器。
- 定期扫描 `.env`：值含空格、带反引号/管道、行首 BOM 都是危险信号。
- 若凭证已经打印到终端/日志，按泄露处理并轮换。

## Related

- `.agents/skills/windows-agent-shell/SKILL.md` — Windows UTF-8/BOM 约定
- `docs/solutions/developer-experience/windows-codex-powershell-utf8.md` — Windows 编码
- `docs/solutions/tooling-decisions/deepseek-1017-harness-selection-cost-cache.md` — 启动器与网关
