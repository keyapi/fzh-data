---
name: windows-agent-shell
description: |
  Windows 上 Agent 执行 shell 的薄约定：优先 pwsh、禁止 bash 语法、UTF-8 无 BOM。
  当用户或环境在 Windows / PowerShell / pwsh / ParserError / && / GBK / cp936 /
  乱码 / 编码 / Set-Content / App Execution Alias / WindowsApps / Store 版软件 /
  装 PowerShell 7 / Codex 思考流报错时触发。
  Mac/Linux 不要加载本 skill 的执行约定。
---

# Windows Agent Shell

> 本 skill **只**约束 Windows 下的命令写法。非 Windows：忽略。

## 何时加载

- OS 为 Windows，或任务要跑 `powershell` / `pwsh`
- 思考流出现 `ParserError`、`&& is not a valid statement separator`、中文乱码、GBK/cp936
- 用户提到 Codex/Cursor 在 Windows 上命令失败、编码冲突
- 提权/非交互场景里「命令找不到」，或要装 PowerShell 7

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
6. **区分「系统 UTF-8 开关」与 `PYTHONUTF8`**：
   - **不要**打开系统「Beta: 使用 Unicode UTF-8 提供全球语言支持」来"一劳永逸"——会打坏部分 GBK 软件。
   - 但 `PYTHONUTF8=1` 是**另一回事，安全**：它只改 Python 自己的 `open()` / stdio 默认编码，**不动系统 ANSI 代码页**，对其他软件零影响。Python 层乱码优先用它（见下节）。
7. **装 PowerShell 7 前问用户，且要装对版本**：`env_doctor` 默认只建议，用户确认后再装。
   - ❌ **不要** `winget install --id Microsoft.PowerShell` —— winget 该包**只有 msix**（Store 版），装出来是 **App Execution Alias**，提权/非交互上下文解析不到，会静默回退到 5.1。这正是 Codex 配 `sandbox = "elevated"` 后**仍然用 5.1** 的原因。
   - ✅ 装 **GitHub 官方 MSI**（落 `C:\Program Files\PowerShell\7\`，真路径），并**先核对 GitHub 发布的 sha256**：
     ```powershell
     $msi = Join-Path $env:TEMP 'PS7.msi'
     $p = Start-Process msiexec.exe -Verb RunAs -Wait -PassThru -ArgumentList @(
       '/i', $msi, '/qn', '/norestart', 'ADD_PATH=1', "/L*v", (Join-Path $env:TEMP 'ps7.log'))
     $p.ExitCode        # 0 成功；3010 成功但想重启
     ```
   - `powershell.exe`(5.1) 在 System32，且与 `pwsh.exe` **文件名不同** → **改 PATH 顺序无法让 `powershell` 变成 7**，只能显式调 `pwsh`。

## 两个独立的编码层（别混为一谈）

Windows 上的「中文乱码/编码问题」有**两个互不相干的层**，修一个不会顺带修另一个：

| 层 | 症状 | 修法 |
|---|---|---|
| **Python 层** | 脚本读 UTF-8 文件抛 `UnicodeDecodeError`，或**静默读出别字** | `PYTHONUTF8=1`（机器级 `setx` + `~/.claude/settings.json` 的 `env` 块）**或**代码里显式 `encoding="utf-8"` |
| **Shell 层** | `powershell` 是 5.1：`&&` 报 `ParserError`、引号/正则/JSON 处理出错 | 显式调 `pwsh`；确保装的是 **MSI 版**（见铁律 7） |

- Python **3.15 起** `open()` 才默认 UTF-8（PEP 686）；**3.14 及以前默认走 locale**（中文 Windows = `cp936`）。
- **静默错读比崩溃更危险**：若 UTF-8 的字节恰好也是合法 GBK，`open()` **不报错、直接给出别字**。实测：「赛狐」`e8 b5 9b e7 8b 90` 被 GBK 读成 `U+74A7 U+6D9A U+5AC4`（瓧浪媄）。
- 环境变量只是**本机兜底**；**代码里写明 `encoding="utf-8"` 才对 CI 和同事成立**。两者都做，别只靠一个。

## App Execution Alias 的坑（Store 版软件）

Store/MSIX 安装的程序，在 `%LOCALAPPDATA%\Microsoft\WindowsApps\` 下只是个 **App Execution Alias**（reparse point），**不是真 exe**：

- 依赖交互式会话的解析链；**提权进程、非交互/服务上下文经常解析不到**，表现为「命令找不到」或**静默回退到同名的旧版本**。
- 与 PATH 顺序**无关** —— 真 exe 不在那里。
- 影响面：`pwsh`、Store 版 Python / node 等一切通过 alias 暴露的软件。
- **对工具链（Agent / CI / 计划任务）要装 MSI 或独立安装包，落一个真路径。**

### 排查手法

```powershell
(Get-Command pwsh).Source          # 出现 WindowsApps\ 就是 alias，不是真 exe
$PSHOME                            # 落在 WindowsApps\ 下同样是 Store 版
Test-Path 'C:\Program Files\PowerShell\7\pwsh.exe'   # MSI 版才在这个位置
```

> ⚠️ **验证必须在目标进程内做**：环境变量在进程启动时**快照**。在 Windows Terminal 里验过了，**不代表** Codex/Cursor 也拿到了 —— 要让**那个应用自己**跑上述命令，且它**必须已完全重启**（不是关窗口）。

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
| Python `open(path)` 读 UTF-8 中文 | `open(path, encoding="utf-8")`，或设 `PYTHONUTF8=1` |
| `winget install --id Microsoft.PowerShell` | 装 GitHub 官方 **MSI**，先核对 sha256 |
| 在 Windows Terminal 里验 `pwsh` 版本 | 在**目标应用内**（Codex/Cursor）验，且先**完全重启**它 |
| 在 bash heredoc 里写中文字面量 | 会被控制台 cp936 搞坏成乱码 —— 改用 `\uXXXX` 转义，或把脚本写进文件再跑 |

## 相关文档

- 体检脚本：`scripts/env_doctor.py`
- 已验证对照：`docs/solutions/developer-experience/windows-codex-powershell-utf8.md`（合并后）
- BOM 事故背景：`docs/codex_thread_disappear_debug.md`
- PowerShell 7 发布页（取 MSI + 核对 sha256）：<https://github.com/PowerShell/PowerShell/releases>

## 相关经验（docs/solutions）

踩过的坑与设计取舍，动手前先读：

- `docs/solutions/developer-experience/codex-chatgpt-windows-setup-config-recovery.md` —— Codex (ChatGPT Desktop) 更新后 Windows 安装失败与对话历史恢复
- `docs/solutions/developer-experience/windows-wsl-docker-disk-optimization.md` —— Windows WSL2 Docker VHDX disk space optimization and migration
