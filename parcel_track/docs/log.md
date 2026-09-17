---
okf: v0.1
type: Log
title: parcel_track 变更日志
---

# 变更日志

## 2026-09-17
- **钉钉推送**：新增 `parcel_track/notify.py`（`summarize()` 渲染 markdown 正文、`notify_report()` 传 ERPNext 后发 ActionCard、`notify_failure()` 失败告警），复用 `dingtalk/dingtalk_robot` 的平铺脚本（惰性 import，`summarize` 可离线测）。
- **CLI**：`report` 新增 `--notify` / `--dry-run` / `--title`；跑挂且带 `--notify` 时补发告警。
- **无人值守**：`--tt` 支持给目录（取最新 `.xlsx`），`--out` 省略时默认 `parcel_track_output/ops_<YYYYMMDD>.xlsx` 并自动建父目录；`run_report()` 返回值新增 `counts`（按分类计数）。
- **定时注册**：新增 `parcel_track/scripts/install_parcel_track_schedule.ps1`（仿 `web_automation` 的 schtasks 包装），任务名 `FZH-ParcelTrack-<daily|weekly>`。见 [reference/scheduled-dingtalk-push.md](reference/scheduled-dingtalk-push.md)。

## 2026-09-08
- **处理时间统一 3 营业日**：UPS / FedEx / GLS `HANDLING_DAYS=3`；假日历仍分美国联邦 vs 波兰法定。
- **workers**：`--workers N` 每家 N 路、UPS→FedEx→GLS 串行（峰值 N）。8 月 live 全量分类合计见 `docs/solutions/conventions/parcel-track-handling-days-sequential-workers.md`（无单号/买家）。
- **接入 GLS**：公开 REST（免账号）、波兰历、一格多号拆分、GLS 格内 1Z→UPS。GOFO/TikTok/USPS 仍停放。

## 2026-09-07
- **新增**: 通途混合订单分流 + 共享 classify；UPS 纳入迟发/承运延误/卡件表；当时 GLS/GOFO 停放不计丢。
