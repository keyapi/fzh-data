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

`--tt` 给的是**目录**，取其中最新的 `.xlsx`：把通途「非FBA订单」导出丢进
`parcel_track_input/` 即可（该目录已 gitignore，含买家信息）。

> ⚠️ **目前没有自动导出**：通途非FBA订单仍需人工从通途下载后放进 `parcel_track_input/`。
> 真正全无人值守还差这一步（`web_automation` 现有 `tongtu.stock/sales/orderdetail` 三个能力，不含非FBA订单）。

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
