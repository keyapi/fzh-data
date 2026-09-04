---
okf: v0.1
type: Reference
title: 通途导出定时调度（Windows / macOS / Linux）
description: 让同事 clone 后按需给通途库存/销售报表导出挂定时任务，含 7 天 cookie 过期后的全自动续登
tags: [tongtu, scheduling, cron, windows-task-scheduler, unattended, ocr-login]
---

# 通途导出定时调度

目标：同事 clone `fzh-data` 后，用**系统自带调度**（Windows 任务计划 / macOS-Linux cron）让
通途库存或销售报表每隔一段时间自动导出一份，全自动、无人值守。依赖只 clone + 首次准备。

## 支持的任务与无人值守命令

| 内容 | dispatcher 任务 | 报表/产出 |
|------|-----------------|-----------|
| 通途 6 仓库存 | `tongtu.stock.export` | 6 仓清单 → `web_automation/output/` |
| 销售及库存报表 | `tongtu.sales.export` | 统计 zip → 按 6 仓分表 → `output/` |

定时命令统一为（仓库根目录执行）：

```bash
uv run python web_automation/scripts/dispatch.py tongtu.<stock|sales>.export -- --auto-login
```

- `--auto-login`：cookie 还在 → 直接跑；过期（超 7 天）→ 自动重新登录（见下）。
- 产出与日志写到 `web_automation/output/`、`web_automation/downloads/`、`web_automation/logs/`（均 gitignored）。

## 7 天后怎么继续全自动（关键）

登录 cookie 有效期默认 7 天（勾选"7 天内自动登录"）。过期后下次运行：

1. 脚本检测未登录；
2. 因为带了 `--auto-login`，先**懒惰试装 OCR**（`ddddocr`+`onnxruntime` 装进
   `web_automation/.venv`，仅首次约 50MB，自动完成，不询问）；
3. OCR 装成 → 自动识别图形验证码登录；识别失败多次自动换图重试；
4. OCR 装不上（网络 / 缺 VC++ 运行库）或多次失败 → 降级**半自动**：填好账号等你
   在浏览器输一次验证码（无人值守时这一步需要有人在场）。

> 因此：本地有桌面、装了 OCR 后，通常能一直全自动；OCR 首次装好后再也不问。

## Windows（推荐，同事最常见）

**方式 A：一键脚本注册（schtasks）**

```powershell
# 每 12 小时导一次库存
powershell -ExecutionPolicy Bypass -File web_automation\scripts\install_tongtu_schedule.ps1 -IntervalHours 12

# 每 8 小时导销售报表
powershell -ExecutionPolicy Bypass -File web_automation\scripts\install_tongtu_schedule.ps1 -Task sales -IntervalHours 8

# 每天 02:00 同时导库存和销售
powershell -ExecutionPolicy Bypass -File web_automation\scripts\install_tongtu_schedule.ps1 -Task both -AtTime "02:00"

# 取消
powershell -ExecutionPolicy Bypass -File web_automation\scripts\install_tongtu_schedule.ps1 -Remove
```

任务名 `FZH-TongtuAutoExport-stock / -sales`。查询：`schtasks /Query /TN FZH-TongtuAutoExport-stock`。

**方式 B：任务计划程序图形界面**：新建任务 → 触发器按需（每天/每周/每隔 N 小时）→
操作 = 程序 `cmd.exe`，参数填上面命令，起始于仓库根。

> 任务以当前用户运行：电脑需开机且该用户已登录才触发。

## Linux / macOS（crontab）

```bash
# 编辑 crontab
crontab -e
```

```cron
# 每 12 小时导库存（第 7 分钟整点错开，避免抢点）
7 */12 * * * cd /path/to/fzh-data && uv run python web_automation/scripts/dispatch.py tongtu.stock.export -- --auto-login >> web_automation/logs/export-stock.log 2>&1

# 每 8 小时导销售报表
13 */8 * * * cd /path/to/fzh-data && uv run python web_automation/scripts/dispatch.py tongtu.sales.export -- --auto-login >> web_automation/logs/export-sales.log 2>&1

# 每天 02:00 导库存
17 2 * * * cd /path/to/fzh-data && uv run python web_automation/scripts/dispatch.py tongtu.stock.export -- --auto-login >> web_automation/logs/export-stock.log 2>&1
```

cron 表达式（`分 时 日 月 周`）：`0 */12 * * *`=每 12h、`0 */8 * * *`=每 8h、
`0 2 * * *`=每天 2:00。错开用非 0 分钟（如 `7`/`13`/`17`）避免集体抢点。
macOS 也自带 cron，同上；若想用 launchd 亦可，但 cron 对这份工作最简单。

## 首次准备（每个 clone 只做一次）

1. `uv sync`（根环境，装 dispatcher 依赖）。
2. 手动跑一次 `dispatch.py tongtu.stock.export`，在弹出的浏览器登录一次并勾"7 天内自动登录"，
   建立 `web_automation/chrome-profile/`（之后定时任务就免登录，直至 cookie 过期自动续）。
3. 想要长期全自动：先 `uv sync --project web_automation --group ocr` 把 OCR 装好，
   或首次让 `--auto-login` 自动装。

## 排障

- 看日志：`web_automation/logs/export-<task>.log`；任务退出码非 0 = 失败。
- 电脑睡眠/关机时任务不会触发；Windows 任务计划默认错过不补跑。
- cookie 过期但 OCR 没装成 → 任务会卡在等人工输验证码直到超时（日志里看 `[错误] 登录超时`）；
  处理：手动跑一次输码，或修好 OCR（多数是缺 VC++ 运行库：安装 Microsoft Visual C++
  2015-2022 Redistributable）。
- 同名任务重复注册：脚本用 `/F` 覆盖，安全。

## 相关

- 能力与路由：`capabilities.yaml`、`scripts/dispatch.py`
- 通途登录/OCR：`legacy-compatible/tongtu_auto_export.py`、`tongtu_login_ocr.py`
- 仓库名单（改名后）见 `tongtu_auto_export.py` 顶部注释 + `--list-warehouses`
