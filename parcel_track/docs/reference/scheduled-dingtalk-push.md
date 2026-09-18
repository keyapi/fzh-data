---
okf: v0.1
type: Reference
title: parcel_track 定时跑 + 钉钉推送
description: 让尾程异常报表按天/周无人值守跑完并推到钉钉群：前置凭证、注册 schtasks、手动验证与排障
tags: [parcel-track, dingtalk, scheduling, windows-task-scheduler, unattended]
---

# parcel_track 定时跑 + 钉钉推送

目标：通途订单表进到 `parcel_track_input/` 后，系统**按天或按周自动**跑 `parcel_track`，
把运营异常 Excel 传到 ERPNext 并用钉钉 ActionCard 推到群里，全自动、无人值守。

## 前置（每台机器只做一次）

1. **钉钉群自定义机器人**（钉钉**官方**的「AI小钉」「智能物流助手」接不了 webhook，必须自己加）：
   进群 → 右上角 `...` → 机器人 → 添加机器人 → **自定义（通过 webhook 接入自定义服务）** →
   安全设置勾 **加签** → 记下 **Webhook 地址** 与 **secret**。
   配置细节见 [dingtalk/dingtalk_robot/钉钉自定义机器人配置指引_给同事.md](../../../dingtalk/dingtalk_robot/钉钉自定义机器人配置指引_给同事.md)。
2. 在**仓库根** `.env`（已 gitignore）写入：

   ```
   DINGTALK_WEBHOOK=...     # 上一步的 Webhook 地址
   DINGTALK_SECRET=SEC...   # 上一步的加签 secret
   ERP_API_KEY=...          # ERPNext → My Settings → API Access
   ERP_API_SECRET=...
   UPS_CLIENT_ID / UPS_CLIENT_SECRET / UPS_API_ENV
   FEDEX_API_KEY / FEDEX_SECRET_KEY / FEDEX_ENV
   ```

   真值**只放 `.env`**，任何情况下不进代码、文档、日志或 commit。
3. 首次先手动跑一次（见下）确认链路通，再挂定时。

## 输入从哪来

`--tt` 给的是**目录**，取其中最新的 `.xlsx`。有两条路：

**A. 定时任务自己取（默认，2026-09-18 起）**——`parcel_track/scripts/daily_fetch_and_report.py`
每次自动做「近 7 天、**截止昨天**」的通途导出 → 解压进 `parcel_track_input/` → 出报表 → 推钉钉。
范围固定避开今天（通途不接受截止为当天）。**取数失败不会中断**：它会先推一条失败告警，
再退回用 `parcel_track_input/` 里已有的表照常出报表——否则无人值守时会「什么都没发生」。

```bash
uv run python parcel_track/scripts/daily_fetch_and_report.py --notify            # 取数+出表+推送
uv run python parcel_track/scripts/daily_fetch_and_report.py --skip-fetch --notify  # 复用已有输入
```

**B. 手工放文件**——自己从通途导出后丢进 `parcel_track_input/`（注册定时任务时加 `-SkipFetch`）。

### 底层导出命令（排查时手跑）

```bash
# 一次性：装子环境 + Chromium + OCR
uv run python web_automation/scripts/bootstrap.py --with-ocr
# 首次要在 web_automation/.env 填 TONGTU_USER / TONGTU_PASSWORD（gitignored）

# 导一段发货时间（--auto-login = ddddocr 自动过验证码）
WEB_AUTOMATION_BROWSER_CHANNEL=chrome \
uv run python web_automation/scripts/dispatch.py tongtu.orderdetail.export \
    -- --range-start 2026-09-10 --range-end 2026-09-16 --auto-login

# 产出 web_automation/downloads/订单详情统计_*.zip，解压出 xlsx 放进 parcel_track_input/
```

**三条硬约束（都踩过）**：

1. **发货时间的「止」不能是当天**——通途不接受，会报错。所以「近 7 天」要写成
   `<今天-7> ~ <昨天>`。定时任务算范围时必须避开今天。
2. **导出的 xlsx 表头在第 30 行**（前面约 30 行是筛选条件元数据），91 列。
   元数据区自己就有一行叫 `跟踪号`（值 `全部`），**不能**拿它当表头。
   `parcel_track.ingest.read_tongtu_sheet()` 已自动定位表头行，两种导出形态通吃。
3. **本机 bundled chromium 有头模式起不来**（`spawn UNKNOWN`；chromium-1228 另报沙箱
   `拒绝访问 0x5`），但**系统 Chrome 有头正常**。`web_automation` 的脚本把
   `launch_persistent_context(headless=False)` 写死、没留 channel 开关，本机需要
   给它注入 `channel="chrome"` 才能跑（见下方「已知问题」）。

> 备注：GLS 走公开 REST、UPS 走官方 Track，**都不依赖通途那条链**；
> 「自动导出」只解决「从通途拿订单表」这一步。


## 注册定时任务（Windows）

仓库根目录执行（先 `uv sync`）：

```powershell
# 每天 09:07 跑（测试期用这个）
powershell -ExecutionPolicy Bypass -File parcel_track\scripts\install_parcel_track_schedule.ps1 -Task daily -AtTime "09:07"

# 每周一 09:07 跑
powershell -ExecutionPolicy Bypass -File parcel_track\scripts\install_parcel_track_schedule.ps1 -Task weekly -DayOfWeek MON -AtTime "09:07"

# 换输入目录
powershell -ExecutionPolicy Bypass -File parcel_track\scripts\install_parcel_track_schedule.ps1 -InputDir "D:\通途导出"

# 取消
powershell -ExecutionPolicy Bypass -File parcel_track\scripts\install_parcel_track_schedule.ps1 -Remove
```

任务名 `FZH-ParcelTrack-daily` / `FZH-ParcelTrack-weekly`。脚本按机器生成
`parcel_track/scripts/run_parcel_track_scheduled-<task>.cmd`（已 gitignore），里面含
`PYTHONIOENCODING=utf-8`（否则重定向到日志时中文会乱码）。

**分钟故意错开整点**（如 `09:07`），避免和其他定时任务抢同一时刻。

## 手动验证

```powershell
# 1) 离线全链路：不查官方 API、不发群，只看卡片正文
uv run python -m parcel_track.cli report --tt parcel_track_input --out parcel_track_output/ops_demo.xlsx --mock --notify --dry-run

# 2) 真查真推（先 --limit 冒烟，全量须确认）
uv run python -m parcel_track.cli report --tt parcel_track_input --limit 10 --notify

# 3) 手动触发已注册的任务
schtasks /Run /TN FZH-ParcelTrack-daily
schtasks /Query /TN FZH-ParcelTrack-daily /V /FO LIST
```

日志：`parcel_track_output/logs/parcel_track-daily.log`；产出：`parcel_track_output/ops_<YYYYMMDD>.xlsx`。

## 已知问题（2026-09-18）

- **本机 bundled chromium 有头模式起不来**：`spawn UNKNOWN`；chromium-1228 换报沙箱
  `拒绝访问 0x5`。headless 模式正常、系统 Chrome（`channel="chrome"`）有头也正常。
  已在 `web_automation` 加统一启动出口，用 `WEB_AUTOMATION_BROWSER_CHANNEL=chrome` 切系统 Chrome
  （定时包装里已设）。详见 `web_automation/docs/reference/browser-launch.md`。
  赛狐族 ~15 处尚未迁移到该出口。
- **`schtasks /TR` 不能用于带空格的仓库路径**：本仓库常在 `D:\Claude Demo\...`，
  `schtasks` 会把 `/TR "…"` 的引号剥掉，任务于是试图运行 `D:\Claude`，报
  `上次结果: -2147024894`（`ERROR_FILE_NOT_FOUND`）。注册脚本已改用
  `New-ScheduledTaskAction` / `Register-ScheduledTask`（原生 cmdlet，不走 shell 解析）。
- **`dispatch.py` 会自动补装浏览器**：它在跑任务前先 `collect_web_facts`，发现
  Chromium 缺失就执行 `playwright install chromium`（约 192 MiB + headless shell 114 MiB）。
  实测本机浏览器目录**被清空过一次**（疑与安全软件有关），于是那次定时运行多花了约 5 分钟下载。
  不影响正确性（任务最终成功），但如果每次都被清就会每天重下——体检用
  `uv run python web_automation/scripts/doctor.py`，反复出现就让安全软件把
  `%LOCALAPPDATA%\ms-playwright` 加白。
- **承运商凭证要保证是「生产」的**：`parcel_track` 把环境写死为生产
  （UPS `env="prod"` / FedEx `env="production"`），**沙箱 key 会认证失败**，报表里该承运商的
  行会**全部落进「数据异常/查无」**（看着像查不到，其实是凭证不对，极易误判）。
  FedEx 沙箱 key 的报错原文是 `Sandbox credentials not allowed in this environment`。
  换 key 后记得 `FEDEX_ENV` 同步改（`fedex_track` 读的是 `FEDEX_ENV`，不是 `FEDEX_API_ENV`）。


## 排障

- **没收到钉钉**：看日志末尾；跑挂时若带 `--notify` 应能看到一条失败告警（告警本身失败只打 stderr，不会盖住原异常）。
- **中文乱码**：`.cmd` 里漏了 `PYTHONIOENCODING=utf-8`，重新跑一次注册脚本覆盖即可。
- **电脑睡眠/关机时任务不触发**，Windows 任务计划默认**不补跑**错过的触发。
- **凭证 `KeyError`**：`.env` 不全。`cli.py` 依次加载「工作树 `.env` → 向上找到 `AGENTS.md` 那层的 `.env`」，`override=False`。
- **推送太频繁**：钉钉自定义机器人限 **20 条/分钟**。

## 相关

- 模块说明：`parcel_track/docs/index.md`、口径长文 `docs/solutions/conventions/parcel-track-handling-days-sequential-workers.md`
- 推送实现：`parcel_track/notify.py`、`dingtalk/dingtalk_robot/send_file_card.py`
- 同类调度范例：`web_automation/docs/reference/scheduling-exports.md`
