---
type: skill
name: parcel-track
description: 通途订单分流 UPS/FedEx/GLS + 共享迟发/承运延误/卡件运营表
version: 0.2.0
triggers:
  - "通途订单跟踪"
  - "混合跟踪"
  - "parcel_track"
  - "UPS FedEx 异常"
  - "迟发延误"
  - "尾程异常报表"
  - "GLS 统一报表"
---

# parcel-track Skill

通途非 FBA 订单 → 分流 UPS/FedEx 官方 Track + GLS 公开 REST → 共享运营异常 Excel。

新对话必读：`parcel_track/AGENT_HANDOFF.md`；口径：`docs/solutions/conventions/parcel-track-handling-days-sequential-workers.md`

处理时间 UPS/FedEx/GLS 统一 3 个营业日；假日历仍按承运商（美国联邦 / 波兰法定）。
`--workers N` 是**每个**承运商 N 路，三家串行（峰值 N，不是 3N）。默认 4。
GOFO/TikTok/USPS 停放，不要去爬官网或擅自接 AfterShip。GLS 不要再当成「无账号就不能查」。
禁止把 API key、买家姓名、原始跟踪号写进文档或 commit。
