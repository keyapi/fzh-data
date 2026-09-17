---
type: skill
name: parcel-track
description: 通途订单分流 UPS/FedEx/GLS + 共享迟发/承运延误/卡件运营表 + 钉钉群推送
version: 0.3.0
triggers:
  - "通途订单跟踪"
  - "混合跟踪"
  - "parcel_track"
  - "UPS FedEx 异常"
  - "迟发延误"
  - "尾程异常报表"
  - "GLS 统一报表"
  - "尾程钉钉推送"
  - "物流报表定时"
---

# parcel-track Skill

通途非 FBA 订单 → 分流 UPS/FedEx 官方 Track + GLS 公开 REST → 共享运营异常 Excel →（可选）推钉钉群。

新对话必读：`parcel_track/AGENT_HANDOFF.md`；口径：`docs/solutions/conventions/parcel-track-handling-days-sequential-workers.md`；
推送与定时：`parcel_track/docs/reference/scheduled-dingtalk-push.md`

处理时间 UPS/FedEx/GLS 统一 3 个营业日；假日历仍按承运商（美国联邦 / 波兰法定）。
`--workers N` 是**每个**承运商 N 路，三家串行（峰值 N，不是 3N）。默认 4。
GOFO/TikTok/USPS 停放，不要去爬官网或擅自接 AfterShip。GLS 不要再当成「无账号就不能查」。

推送：`--notify` 推到钉钉群（`--dry-run` 只打印正文、不发群、不需凭证）。推的是**运营异常 Excel**，
经 ERPNext 中转成 ActionCard 下载卡片；失败且带 `--notify` 会补发一条告警。
无人值守：`--tt` 给目录取最新 xlsx、`--out` 省略按日期命名、`install_parcel_track_schedule.ps1` 注册 schtasks。

禁止把 API key、买家姓名、原始跟踪号写进文档或 commit。

