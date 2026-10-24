---
okf: v0.1
type: Research
title: DeepSeek 1017 Harness A/B 实测 — Claude Code CLI vs DeepSeek Harness（含 PTC/沙箱/稳态成本）
date: 2026-10-19
tags: [deepseek, flash-1017, claude-code, deepseek-harness, ab-test, prompt-cache, windows, ptc, sandbox]
source: Local A/B run on 2026-10-19
---

# DeepSeek 1017 Harness A/B 实测

> 同一网关、同一模型、同一任务，对比独立 Claude Code CLI 与 DeepSeek Harness。
> 调研背景与工具横向对比见
> [`2026-10-19-deepseek-1017-agent-harness-research.md`](2026-10-19-deepseek-1017-agent-harness-research.md)。

## 一、环境

| 项目 | 值 |
|---|---|
| 机器 | i3-12100，31.7 GB RAM，Windows 11 |
| Node | 24.14.0 |
| Claude Code | **2.1.303**（npm global） |
| DeepSeek Harness | **0.2.1-rc.2**（`npm install -g @deepseek-ai/dsh@next`） |
| 网关 Anthropic | `https://api.vilavi.cn/` |
| 网关 OpenAI 兼容 | `https://api.vilavi.cn/v1` |
| 模型 | `deepseek-v4-flash[1m]`（1017 权重） |
| 时间 | 2026-10-19 14:40–15:35 CST（周一，高峰时段） |
| 计价来源 | `new-api-deployment/deepseek_time_pricing.py`（与网关实际 ModelRatio 同源） |

## 二、计价模型（先看这个）

DeepSeek flash 系列，元 / 1M tokens：

| 时段 | 未命中输入 | 缓存命中输入 | 输出 |
|---|---|---|---|
| 高峰（周一至周五 9–12、14–18） | ¥2.00 | ¥0.04 | ¥8.00 |
| 空闲（其余时间） | ¥1.00 | ¥0.02 | ¥4.00 |

**缓存命中比未命中便宜 50 倍。** 所以真正的成本杠杆不是“总 token”，而是
**未命中输入（fresh input）** 和 **输出**。本文的成本都按高峰价估算：

```
cost = fresh_input * 2/1e6 + cache_read * 0.04/1e6 + output * 8/1e6   (CNY)
```

Claude Code 自报的 `total_cost_usd` 对未知模型是 `costBasis: unknown`，
按 Anthropic 价估算，**不要用它和 DSH 比**。

## 三、任务

### T1：工作流兼容（真实仓库，只读）

固定在 `D:\Work\赛狐\Cursor\.claude\worktrees\flamboyant-lumiere-ab19c9`，提示词：

> Run `uv run python scripts/check_secrets.py` in the current repository. Then read
> `docs/solutions/index.md` and identify exactly 3 entries related to cost or DeepSeek.
> Output: (1) the exit code and one-line summary; (2) the 3 titles with paths;
> (3) a 3-sentence summary. Do not modify any files.

- Claude Code：`--allowedTools "Bash,Read,Grep,Glob"`。
- DSH：`dsh headless --json`，分别测 `read-only` 与 `danger-full-access`。

### T2：小型编码（隔离目录）

在 `C:\Users\zhang\dsh-workspace\ab-test\*`，提示词：

> In the current directory, create a Python CLI `wordfreq.py` ... Add `test_wordfreq.py`
> with exactly 3 pytest tests ... Run `uv run --with pytest --no-project pytest -q`
> and make it pass. Do not modify anything outside the current directory.

- Claude Code：`--allowedTools "Bash,Read,Write,Edit,Grep,Glob" --permission-mode acceptEdits`。
- DSH native：`DSH_PERMISSION_MODE=workspace-write`，`UV_CACHE_DIR=<workspace>/.uv-cache`。
- DSH PTC：`DSH_TOOLS_MODE=ptc`，其余同上。

## 四、结果

| 任务 / 轮次 | Harness / 模式 | 结果 | 墙钟 | 步/轮 | Fresh input | Output | Cache read | 命中率 | 高峰成本 |
|---|---|---|---|---|---|---|---|---|---|
| T1 | **Claude Code** | ✅ 扫描 exit 0 + 索引 3 条 | **17.4s** | 3 turns | 35,060 | 753 | 34,560 | 49.6% | ¥0.0775 |
| T1 | DSH read-only | ⚠️ 索引正确；`uv` 被沙箱挡住 | 22.3s | 4 steps | 24,103 | 853 | 72,064 | 74.9% | ¥0.0579 |
| T1 | **DSH danger-full-access** | ✅ 扫描 exit 0 + 索引 3 条 | 22.4s | 2 steps | 15,650 | 605 | 34,816 | 69.0% | **¥0.0375** |
| T2 run1 | **Claude Code** | ✅ 精确命令通过 | **31.6s** | 9 turns | 49,432 | 2,772 | 172,544 | 77.7% | ¥0.1279 |
| T2 run2 | **Claude Code** | ✅ 精确命令通过 | **32.3s** | 6 turns | 48,968 | 3,819 | 75,136 | 60.5% | ¥0.1315 |
| T2 run1 | **DSH native** | ✅ 3 tests 通过；精确命令需 workaround | 72.1s | 14 steps | 7,367 | 3,877 | 162,048 | 95.7% | **¥0.0522** |
| T2 run2 | **DSH native** | ✅ 3 tests 通过；精确命令需 workaround | 55.8s | 11 steps | 7,405 | 3,170 | 119,808 | 94.2% | **¥0.0450** |
| T2 run1 | DSH PTC | ✅ 3 tests 通过；精确命令需 workaround | 92.8s | 16 steps | 11,943 | 5,482 | 251,904 | 95.5% | ¥0.0778 |

### 稳态均值（T2）

| Harness | 墙钟 | Fresh input | Output | 命中率 | 高峰成本 | 相对 Claude |
|---|---|---|---|---|---|---|
| **Claude Code** | **32.0s** | 49,200 | 3,296 | 69.1% | ¥0.1297 | 1.00x |
| **DSH native** | 64.0s | **7,386** | 3,524 | **95.0%** | **¥0.0486** | **0.37x** |
| DSH PTC | 92.8s | 11,943 | 5,482 | 95.5% | ¥0.0778 | 0.60x |

**结论：DSH native 单任务约为 Claude Code 的 0.37 倍成本，缓存命中 95% vs 69%，
但慢约 2 倍。** PTC 在这个任务上不快也不省，反而因为代码规划和调试多花了 token。

## 五、T1 那个 ⚠️ 到底是什么，为什么能解

**现象：** `DSH_PERMISSION_MODE=read-only` 下，模型调用 shell 执行
`uv run python scripts/check_secrets.py`，`uv` 在启动阶段就失败：

```
error: Failed to initialize cache at C:\Users\zhang\AppData\Local\uv\cache
  Caused by: failed to open file ... 拒绝访问 (os error 5)
```

**原因：** 不是模型不会跑，而是 DSH 的 Windows 沙箱在 `read-only` 模式下禁止写文件；
`uv run` 即使依赖都已安装，也要初始化/写自己的缓存目录，于是命令根本没执行。
DSH 如实报告了“scan never ran”，没有编造结果。

**解法（已验证）：**

1. **可信的只读任务用 `danger-full-access`**：
   `DSH_PERMISSION_MODE=danger-full-access`。实测同一 T1：扫描 exit 0、索引正确、
   22.4s、**仓库 `git status` 无任何改动**。这是最直接的解法，但只应给可信任务/隔离目录。
2. **`workspace-write` + 用户自己的 ASCII 工作区**：
   `C:\Users\zhang\dsh-workspace`（不要用 `D:\`，见下）+ `UV_CACHE_DIR=<workspace>/.uv-cache`。
   T2 就是这样跑通的。
3. **修 D 盘 ACL**：`D:\dsh-workspace` 报
   `SetNamedSecurityInfoW failed (Win32 5): grantWrite(...)`——用户有写权限但没有
   `WRITE_DAC`。需要在管理员 shell 里给目录授 `Modify`/`Change permissions`（或 `takeown`），
   或者干脆用 C: 用户目录 / WSL2。
4. **WSL2**：DSH 官方文档明确说 Windows 无 Python SDK wheel，推荐 Node CLI/Web 或 WSL；
   如果被 ACL 反复咬，WSL2 是更干净的路线（本轮未实测）。

**pytest 的额外坑：** `workspace-write` 下 pytest 会留下
`pytest-cache-files-*`，之后因 ACL 拒绝无法读取/删除，精确命令会 collection error。
实测 workaround：
- `pytest -q -p no:cacheprovider`
- `--ignore-glob='pytest-cache-files-*'`
- `TMP`/`TEMP` 指向工作区内
- 或管理员权限删除残留目录

## 六、PTC 模式实测

- headless 下用 `DSH_TOOLS_MODE=ptc` 可启用；工具调用从 `bash` 变成 `run_code` +
  生成的 SDK。
- 本任务：PTC 16 步、92.8s、¥0.0778；native 11–14 步、55.8–72.1s、¥0.045–0.052。
- **PTC 不是自动省钱开关。** 它适合“很多工具往返、中间结果很大”的任务；小任务上
  代码规划 + 调试反而增加输出和 fresh input。要按 workload 实测。

## 七、Windows BOM / 编码问题

本机父仓库 `D:\Work\赛狐\Cursor\.env` 实测有两个格式问题：

- line 1 有 UTF-8 BOM；
- line 6 的 `VITE_API_KEY` 值含空格（形如 `Key: <token>`），bash `source` 会把后半段
  当命令执行并把内容打印到终端。

**通用约定（Claude/Codex/DSH 都适用）：**

- 写文本优先 `pwsh` 7：`Set-Content -Encoding utf8NoBOM`；
  **不要用 PowerShell 5.1 的 `Set-Content -Encoding UTF8`**（会加 BOM）。
- Python 读带 BOM 的文件用 `encoding='utf-8-sig'`；Node 读后去掉 `﻿`。
- **不要整体 `source` `.env`**；按行匹配 `^KEY=` 再导出目标变量。
- **2026-10-19 已修复**：备份到 `C:\Users\zhang\.claude\backups\.env.bak-20261019-154524`；
  去掉 BOM；line 6 改为标准 `VITE_API_KEY=<token>`；其余行内容未变；
  `claude-gw.cmd` / `dsh-gw.cmd` 冒烟仍正常。若该凭证可能已外泄，仍建议轮换。

## 八、WSL2 补充调研

### 官方定位（注意时间）

- DSH 官方 Windows 兼容页（verified 2026-08-27，测试环境 DSH 0.1.0-rc.6 / Node 24.12.0）：
  Windows 优先 **Node CLI/Web/headless**；WSL 只作为“需要 Python 编排时运行 Linux runtime”的宿主，
  **不是官方支持面**，也没有 WSL 专属说明。
- 社区 2026-10-09 实测文章明确写：“不支持。桌面版 runtime 全是 win32”；
  要用 WSL 需装 `dsh-wsl-desktop`（桌面）或 `dsh-plugin-wsl-env`（Web）等插件，
  把 `fs` / `subprocess` / `sandbox` / `directory-picker` 等 seam 换到发行版内。
- DSH 迭代很快；以上是 2026-10 的快照，升级后要重新验证。

### 本机 WSL 现状

- Ubuntu-22.04，WSL **2.2.4.0**，`.wslconfig` 已是 `networkingMode=mirrored`、`memory=8GB`、
  `processors=4`、`swap=4GB`。
- **没有干净的 Linux Node**：PATH 里是 Windows 的 `/mnt/c/Program Files/nodejs` 和
  Windows npm；DSH 要求 Node `^22.19.0 || >=24.0.0`。
- `bwrap`、`pnpm`、`uv` 未安装；DSH Web 的命令沙箱需要 **bubblewrap**，否则 fail-closed。
- `/mnt/d` 上的 worktree `.git` 指向 `D:/Work/...`，WSL 里 `git status` 直接
  `fatal: not a git repository`；要跑必须在 WSL 内重新 clone 或修 `.git`。
- 543 个文件的 `find` 约 0.2s，看起来还行；但 9P 在大量小文件/写入时会明显变慢，
  且 **没有 inotify**，file watch 会退化为 polling。

### WSL2 能解决什么

Windows ACL（`grantWrite`）、路径、PTY、原生模块编译、BOM——**前提是文件放在 WSL ext4**。

### WSL2 会引入什么

- **403 / origin**：`localhost` 与 `127.0.0.1` 被当作不同 origin；必须用启动日志里的确切 URL，
  或 `--trusted-host`。
- **目录选择器**：WSL 下原生目录选择器不弹窗/后台卡住；要换浏览器内选择器插件。
- **3080 / 转发 / 代理**：内部 `curl` 通、Windows 浏览器不通很常见；Node 24 的 fetch
  默认忽略代理，除非 `NODE_USE_ENV_PROXY=1`。
- **TTY / 后台**：`dsh web` 需要 TTY；rc.7 有 `--port` 被报 unknown option 的案例，
  后台保活要用 pty + double-fork。
- **插件/版本**：pnpm workspace-root guard（`ERR_PNPM_ADDING_TO_ROOT`，pnpm ≥10.5.0 或 `-w`）；
  Windows 与 WSL 是两个 `$DSH_HOME`；升级后插件容易断。
- **/mnt/d**：9P 慢、无 inotify、大小写/权限差异；repo 必须迁到 WSL ext4
  （`~/projects/...`），不能直接拿 `/mnt/d` 的 worktree 跑。
- **Windows 脚本/skills**：PowerShell、uv、`D:\...` 路径在 WSL 里要重写/适配；
  本仓库的 worktree `.git` 也需要修。

### D 盘 ACL 的额外发现

`D:\dsh-workspace` 的 owner 是 `FZHPC13\zhang`（当前用户），但 DSH 沙箱仍然报
`grantWrite ... Win32 5`。这说明问题不只是“文件夹属于谁”，更像是**沙箱用受限 token，
缺 `WRITE_DAC`**。所以简单的 `icacls /grant` 不一定能修好；改完要实测。
**C: 用户目录已经验证可用**，这是更稳的默认。

### 结论

- **WSL2 不是“解决所有问题”的银弹**：它把 Windows ACL 问题换成了 WSL 网络/插件/TTY/
  文件系统问题，而且官方不支持。
- 本机最稳：**C: 用户工作区 + `workspace-write`/`danger-full-access` + pytest workaround**。
- 只有在 DSH 成为日常主力、且愿意把仓库迁到 WSL ext4、安装 Linux Node 24 / bubblewrap / pnpm 时，
  才考虑 WSL2。

## 九、结论

1. **主力：Claude Code CLI 2.1.303**。仓库 skills/hooks/MCP/脚本兼容性最好，
   T1/T2 都更快、精确命令一次通过。成本约 ¥0.13/个 T2 任务（高峰）。
2. **成本敏感/批处理：DSH native**。约 Claude 的 **0.37x** 成本，缓存 95%，
   但慢约 2 倍，且必须做 Windows 沙箱调优：
   - 用户目录 ASCII 工作区（C:），`UV_CACHE_DIR` 放工作区内；
   - 可信任务用 `danger-full-access`；
   - pytest 加 `-p no:cacheprovider` / `--ignore-glob`；
   - D 盘 ACL 问题要么提权修，要么用 C:/WSL2。
3. **PTC**：不是默认省钱项；按任务类型实测选择。
4. **OpenCode** 不进入主力；**Pi 1.0** 作为后续成本对照组。

## 十、复现命令（不含任何密钥）

```bash
# Claude Code（token 由用户级启动器从父仓库 .env 读取）
claude-gw.cmd -p "<T1 prompt>" --allowedTools "Bash,Read,Grep,Glob" --output-format json
claude-gw.cmd -p "<T2 prompt>" --allowedTools "Bash,Read,Write,Edit,Grep,Glob" \
  --permission-mode acceptEdits --output-format json

# DSH headless（可信只读任务）
DSH_PERMISSION_MODE=danger-full-access dsh-gw.cmd headless --json "<T1 prompt>"

# DSH headless（可写隔离目录）
cd C:/Users/zhang/dsh-workspace/ab-test/run
UV_CACHE_DIR="$(pwd)/.uv-cache" DSH_PERMISSION_MODE=workspace-write \
  dsh-gw.cmd headless --json "<T2 prompt>"

# DSH PTC
DSH_TOOLS_MODE=ptc DSH_PERMISSION_MODE=workspace-write \
  dsh-gw.cmd headless --json "<task>"

# DSH Web UI（实测必须显式 host；PowerShell 启动器下 web 会静默挂起）
cmd /c "dsh web --no-open --host 127.0.0.1 --port 3080"
```

## 十一、局限

- 样本小：T2 每组 1–2 轮，T1 每组 1 轮；不同 cwd 会轻微影响前缀缓存。
- 未使用独立 new-api token，无法从账单精确分摊；成本按网关同源计价公式估算。
- 机器是 i3-12100，DSH 的多步调度可能更吃亏。
- DSH 仍是 developer preview；版本升级可能改变沙箱/模式行为。
- PTC 只测了一个小任务，不能外推到所有 workload。
