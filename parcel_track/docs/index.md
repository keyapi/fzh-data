---
okf: v0.1
type: Index
title: parcel_track
description: 通途订单分流 UPS/FedEx 官方 Track + 共享运营异常报表
---

# parcel_track

通途非 FBA 订单表 → 按 `邮寄方式`/`渠道`（跟踪号形态兜底）分流 → 调用现有 `ups_track` / `fedex_track` 官方客户端 → 一张共享异常 Excel（迟发 / 承运延误 / 卡件）。

v1 不查 GLS、GOFO。不安装 Karrio / AfterShip。

## 命令

```powershell
uv run python -m parcel_track.cli report --tt <通途.xlsx> --out parcel_track_output/ops.xlsx --mock
uv run python -m parcel_track.cli report --tt <通途.xlsx> --out parcel_track_output/ops.xlsx --limit 10
```

FedEx 单承运商旧入口仍可用：`python -m fedex_track.ops_report`。
