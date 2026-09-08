---
okf: v0.1
type: Index
title: parcel_track
description: 通途订单分流 UPS/FedEx/GLS + 共享运营异常报表
---

# parcel_track

通途非 FBA 订单表 → 按 `邮寄方式`/`渠道`（跟踪号形态兜底）分流 → `ups_track` / `fedex_track` / `gls_track` → 一张共享异常 Excel（迟发 / 承运延误 / 卡件）。日历与处理天数按承运商：US+1（UPS/FedEx）、波兰+2（GLS）。

GOFO / TikTok / USPS 停放。不安装 Karrio / AfterShip。

## 命令

```powershell
uv run python -m parcel_track.cli report --tt <通途.xlsx> --out parcel_track_output/ops.xlsx --mock
uv run python -m parcel_track.cli report --tt <通途.xlsx> --out parcel_track_output/ops.xlsx --limit 10
```

FedEx 单承运商旧入口：`python -m fedex_track.ops_report`。GLS 单承运商月报：`python -m gls_track.cli monthly`。
