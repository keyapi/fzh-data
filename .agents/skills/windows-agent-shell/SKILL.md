---
name: windows-agent-shell
description: |
  Windows 上 Agent 执行 shell 的薄约定：优先 pwsh、禁止 bash 语法、UTF-8 无 BOM。
  当用户或环境在 Windows / PowerShell / pwsh / ParserError / && / GBK / cp936 /
  乱码 / 编码 / Set-Content / Codex 思考流报错时触发。
  Mac/Linux 不要加载本 skill 的执行约定。
---

# Windows Agent Shell

> 本 skill **只**约束 Windows 下的命令写法。非 Windows：忽略。

## 何时加载

- OS 为 Windows，或任务要跑 `powershell` / `pwsh`
- 思考流出现 `ParserError`、`&& is not a valid statement separator`、中文乱码、GBK/cp936
- 用户提到 Codex/Cursor 在 Windows 上命令失败、编码冲突

## 铁律

1. **优先 PowerShell 7**：有 `pwsh` 时用 `pwsh -NoProfile -Command "..."`。没有则用 `powershell`，但必须写 5.1 兼容语法。
2. **禁止 bash 习惯**：不要 `&&` / `||`（除非确认在 pwsh 7+）、不要 `cat <<EOF`、`export`、`2>/dev/null`、裸 `sed`/`grep` 管道当默认。
3. **5.1 链式命令**：用 `cmd1; if ($?) { cmd2 }`，不要 `cmd1 && cmd2`。
4. **读 UTF-8 中文文件**：`Get-Content -LiteralPath $p -Encoding UTF8`，或 `uv run python -c "print(open(r'...',encoding='utf-8').read())"`。不要依赖 5.1 默认 `Get-Content`（代码页 936 会乱码）。
5. **写 UTF-8 禁止 BOM**：
   - **禁止** Windows PowerShell 5.1：`Set-Content -Encoding UTF8`（会写 `EF BB BF`，曾导致 Codex 线程消失）。
   - 用 Python：`Path(...).write_text(s, encoding="utf-8")`
   - 或 .NET：`[IO.File]::WriteAllText($p, $s, [Text.UTF8Encoding]::new($false))`
   - pwsh 7：可用 `utf8NoBOM`；不要假设 5.1 有该枚举。
6. **不要**打开系统「Beta: 使用 Unicode UTF-8 提供全球语言支持」来“一劳永逸”——会打坏部分 GBK 软件。
7. **装软件前问用户**：`env_doctor` 默认只建议。需要 PowerShell 7 时给出：
   `winget install --id Microsoft.PowerShell --accept-package-agreements`
   （稳定版，**不要** `Microsoft.PowerShell.Preview`）。用户确认后再装。

## 快速自检

```text
uv run python scripts/env_doctor.py
uv run python scripts/env_doctor.py --probe
```

## 反例 → 正例

| 反例（易失败） | 正例 |
|----------------|------|
| `git status && git diff`（在 5.1） | `git status; if ($?) { git diff }` 或 `pwsh -NoProfile -Command "git status && git diff"` |
| `Get-Content notes.md`（UTF-8 中文，5.1+936） | `Get-Content -LiteralPath notes.md -Encoding UTF8` |
| `Set-Content out.md -Encoding UTF8`（5.1） | Python `write_text(..., encoding="utf-8")` |
| bash heredoc 写文件 | 用 ApplyPatch / Python / here-string + .NET UTF8 no BOM |

## 相关文档

- 体检脚本：`scripts/env_doctor.py`
- 已验证对照：`docs/solutions/developer-experience/windows-codex-powershell-utf8.md`（合并后）
- BOM 事故背景：`docs/codex_thread_disappear_debug.md`
