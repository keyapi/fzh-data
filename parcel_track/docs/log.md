---
okf: v0.1
type: Log
title: parcel_track 变更日志
---

# 变更日志

## 2026-11-17
- **按区域分块推送**：钉钉卡片改为按 **美东 / 美中 / 波兰** 分节（其余仓归「其他」），每区显示「总单数（已查 X · 停放 Y）」+ 待办分类，末尾附合计。此前只统计「已分类」票数，导致「美东 72」被误读成一周只有 72 单——实际该区一周 324 单、其中 **247 单是停放**。全停放的仓（如 `WayfairCG-Cranbury仓`）也会列出，不再从卡片消失。`orchestrate.run_report()` 新增 `by_region`（`orders` / `queried` / `parked` / `counts`）；`notify.summarize()` 按区域渲染。
- **数据新鲜度闸门**：取数失败会退回旧输入，原先会「旧数据冒充当天」。现在出表前比对输入表实际区间与期望区间：不符则输出名加 `_stale`、卡片标题写明**真实数据区间**并标「今日取数失败」。见 `daily_fetch_and_report.input_range()`。
- **告警不再静默**：`daily_fetch_and_report.main()` 在取数/告警**之前**加载 `.env`。此前 `.env` 只在 `parcel_track.cli` 里加载，取数失败时告警拿不到 `DINGTALK_SECRET`，只留下 `[告警] 发送不成功：'DINGTALK_SECRET'`。
- **取数瞬时故障自动重试**：取数失败后等 60 秒重试一次，两次都失败才告警/退回（2026-11-05 09:07 一次登录页 15 秒未渲染即导致当天退回旧数据）。
- **通途登录密码框改版修复**：登录页可见密码框已变为 `id="password"`（无 `name`），`name="password"` 是隐藏的 `passwordMd5`。选择器 `input[name="password"]` → `input[type="password"]`（`tongtu_login_ocr.py` + `tongtu_export_ocr.py`）。这是 **2026-10-20 起每日取数连续失败**的根因。另：登录前先判「会话仍有效」（passport 已跳回 erp102 则跳过），登录页等待 15s→30s 且超时优雅返回。见 web_automation 变更日志。
- 测试：`parcel_track/tests` **49 passed**；真实链路实测（`10-29~11-04`、`11-10~11-16`）推送成功。

## 2026-09-18
- **每日无人值守编排**：新增 `scripts/daily_fetch_and_report.py`——自动做「近 7 天、**截止昨天**」的通途取数 → 解压 → 出表 → 推钉钉。范围固定避开今天（通途不接受截止为当天）。**取数失败不中断**：先推失败告警，再退回用已有输入出表，否则无人值守时会「什么都没发生」。
- **定时注册改用原生 cmdlet**：`install_parcel_track_schedule.ps1` 原先用 `schtasks /TR`，在带空格的仓库路径（`D:\Claude Demo\…`）下引号被剥掉，任务于是试图运行 `D:\Claude` → `上次结果 -2147024894`（ERROR_FILE_NOT_FOUND）。改用 `New-ScheduledTaskAction` / `Register-ScheduledTask`，并加注册后校验（可执行路径必须等于包装脚本）。新增 `-SkipFetch` 保留「人工放文件」模式。
- **实测**：任务 `FZH-ParcelTrack-daily`（每天 09:07）手动触发一次，完整跑通取数 → 1366 单 → UPS 48/48、FedEx 241/241、GLS 226/228 → 推钉钉群。
- 新增 `tests/test_daily_run.py`（7 用例，含「截止必须是昨天」这条硬约束）。

## 2026-09-17
- **钉钉推送**：新增 `parcel_track/notify.py`（`summarize()` 渲染 markdown 正文、`notify_report()` 传 ERPNext 后发 ActionCard、`notify_failure()` 失败告警），复用 `dingtalk/dingtalk_robot` 的平铺脚本（惰性 import，`summarize` 可离线测）。
- **CLI**：`report` 新增 `--notify` / `--dry-run` / `--title`；跑挂且带 `--notify` 时补发告警。`--dry-run` 打印卡片正文走 `_safe_print`——正文含 emoji，Windows GBK 控制台直接 `print` 会 `UnicodeEncodeError` 崩掉（推给钉钉的那份始终是完整 UTF-8）。
- **无人值守**：`--tt` 支持给目录（取最新 `.xlsx`），`--out` 省略时默认 `parcel_track_output/ops_<YYYYMMDD>.xlsx` 并自动建父目录；`run_report()` 返回值新增 `counts`（按分类计数）。
- **`.env` 真的会加载了**：`_load_env()` 原先吞掉 `dotenv` 的 ImportError，而 `python-dotenv` 从没进过依赖——该函数**从未生效**过。补依赖 + 去掉吞异常；`--mock` 也不再连带跳过凭证（`--mock` 只表示不打承运商 API）。
- **自动定位表头行**：新增 `ingest.read_tongtu_sheet()`。`tongtu.orderdetail.export` 导出的 xlsx 表头在**第 30 行**、91 列，前 30 行是筛选条件元数据——**元数据里自己就有一行叫 `跟踪号`（值 `全部`）**，取「第一处出现跟踪号的行」会误判。改为「含跟踪号的各行中取非空格子最多的那行」。
- **定时注册**：新增 `parcel_track/scripts/install_parcel_track_schedule.ps1`（仿 `web_automation` 的 schtasks 包装），任务名 `FZH-ParcelTrack-<daily|weekly>`。见 [reference/scheduled-dingtalk-push.md](reference/scheduled-dingtalk-push.md)。
- **真数据端到端实测通过**：通途 orderdetail 导出（09-10~09-16，1415 行）→ UPS 53/53、GLS 234/236 拿到真实轨迹 → 出表 → 推钉钉群。FedEx 251 行全落「查无」——**沙箱凭证打生产端点**，需换生产 key。

## 2026-09-08
- **处理时间统一 3 营业日**：UPS / FedEx / GLS `HANDLING_DAYS=3`；假日历仍分美国联邦 vs 波兰法定。
- **workers**：`--workers N` 每家 N 路、UPS→FedEx→GLS 串行（峰值 N）。8 月 live 全量分类合计见 `docs/solutions/conventions/parcel-track-handling-days-sequential-workers.md`（无单号/买家）。
- **接入 GLS**：公开 REST（免账号）、波兰历、一格多号拆分、GLS 格内 1Z→UPS。GOFO/TikTok/USPS 仍停放。

## 2026-09-07
- **新增**: 通途混合订单分流 + 共享 classify；UPS 纳入迟发/承运延误/卡件表；当时 GLS/GOFO 停放不计丢。
