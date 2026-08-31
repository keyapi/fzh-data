---
title: "Windows Codex/Cursor：PowerShell 5.1 && 与 GBK/UTF-8 对照及 env_doctor"
date: 2026-08-13
category: developer-experience
module: tooling
problem_type: developer_experience
component: tooling
severity: high
applies_when:
  - "Codex 或 Cursor 在 Windows 思考流出现 ParserError / &&"
  - "PowerShell 读 UTF-8 中文文档乱码（代码页 936/GBK）"
  - "Set-Content -Encoding UTF8 写入 BOM 导致 Codex 配置或线程异常"
  - "同事新机器 clone 后需要按 OS 打印建议而非擅自安装"
tags:
  - windows
  - powershell
  - powershell-7
  - pwsh
  - gbk
  - utf-8
  - bom
  - codex
  - env-doctor
  - windows-agent-shell
---

# Windows Codex/Cursor：PowerShell 5.1 && 与 GBK/UTF-8 对照及 env_doctor

## Context

Windows 默认壳是 **Windows PowerShell 5.1**。Codex/Cursor Agent 常按 Linux/bash 写命令，并默认按系统 ANSI 读写文本：

1. **`&&` / `||`**：5.1 不支持（7+ 才支持）→ 思考流刷 `ParserError: The token '&&' is not a valid statement separator`
2. **GBK vs UTF-8**：控制台代码页常为 **936**；5.1 默认 `Get-Content` 按系统编码解码 UTF-8 文件 → 中文乱码
3. **BOM 反例**：5.1 `Set-Content -Encoding UTF8` 写入 `EF BB BF`；本仓库曾因此导致 Codex 线程消失（见 Related）

同事有 Windows / Mac / Linux；需要 **clone 后按本机体检只建议、不擅自 winget**。

## Guidance

1. 跑体检（默认 recommend-only）：

```text
uv run python scripts/env_doctor.py
uv run python scripts/env_doctor.py --probe
```

2. Windows 且无 `pwsh`：建议安装 **稳定版** PowerShell 7（勿装 Preview）：

```text
winget install --id Microsoft.PowerShell --accept-package-agreements
```

用户确认后再装。Agent 不要默认 `--apply-ps7`。

3. 加载项目 skill：`.agents/skills/windows-agent-shell/SKILL.md`
   - 有 `pwsh` → `pwsh -NoProfile -Command "..."`
   - 无 `pwsh` → `cmd1; if ($?) { cmd2 }`，禁止 `&&`
   - 读 UTF-8：`Get-Content -Encoding UTF8` 或 Python
   - 写 UTF-8：**禁止** 5.1 `Set-Content -Encoding UTF8`；用 Python `encoding="utf-8"` 或 .NET `UTF8Encoding($false)`

4. **不要**打开系统「Beta: 全球语言使用 UTF-8」作为修复手段。

## Why This Matters

- 不装 PS7、不约束写法时，Windows Agent 会话会被大量假失败占满上下文。
- 只装 skill 不装 PS7：可减少 bash 写法，但无法让 5.1 支持 `&&`。
- 只装 PS7 不装 skill：`&&` 常能过，仍可能写 heredoc / BOM。
- 两者叠加 + `env_doctor` 给同事可复现建议，符合用户主权。

## When to Apply

- 新机器首次 clone（AGENTS.md 步骤 2.5 / onboarding 种子指令）
- Codex 思考流出现 `&&` / 乱码 / BOM 相关故障
- 对照回归：`uv run pytest tests/env_doctor -q`

## Examples

### 本机对照（2026-08-13，代码页 936）

| 探针 | PS 5.1 | pwsh 7.6.4 |
|------|--------|------------|
| `Write-Output a && Write-Output b` | fail（ParserError） | ok |
| `a; if ($?) { b }` | ok | ok |
| 默认 `Get-Content` 读无 BOM UTF-8「赛狐SKU」 | 乱码（≠ 原文） | ok |
| `Get-Content -Encoding UTF8` | ok | ok |
| `Set-Content -Encoding UTF8` | **写入 BOM** | （skill：仍禁止用此写法写仓库文件） |

复跑：

```text
uv run python scripts/env_doctor.py --probe --json
uv run pytest tests/env_doctor -q
```

### Skill 烟雾

- doctor 检测到 `windows-agent-shell` → 建议码 `load_windows_agent_shell`
- pwsh 下 `&&` ok；Python `write_text(..., encoding="utf-8")` 无 BOM；5.1 `Set-Content -Encoding UTF8` 仍可复现 BOM 反例

## Related

- Skill：`.agents/skills/windows-agent-shell/SKILL.md`
- 脚本 / 测试：`scripts/env_doctor.py`，`tests/env_doctor/test_env_doctor.py`
- BOM 事故：`docs/codex_thread_disappear_debug.md`
- 相关：`docs/solutions/developer-experience/codex-chatgpt-windows-setup-config-recovery.md`
