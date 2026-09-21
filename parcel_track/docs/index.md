---
okf: v0.1
type: Index
title: parcel_track
description: 通途订单分流 UPS/FedEx/GLS + 共享运营异常报表 + 钉钉推送
updated: 2026-09-17
---

# parcel_track

通途非 FBA 订单表 → 按 `邮寄方式`/`渠道`（跟踪号形态兜底）分流 → `ups_track` / `fedex_track` / `gls_track` → 一张共享异常 Excel（迟发 / 承运延误 / 卡件）。处理时间 UPS/FedEx/GLS **统一 3 个营业日**；假日历仍按承运商：美国联邦（UPS/FedEx）、波兰法定（GLS）。`--workers N` 是每个承运商 N 路、三家串行。

GOFO / TikTok / USPS 停放。不安装 Karrio / AfterShip。口径长文：[parcel-track-handling-days-sequential-workers](../../docs/solutions/conventions/parcel-track-handling-days-sequential-workers.md)。

## 命令

```powershell
python -m parcel_track.cli report --tt <通途.xlsx> --out parcel_track_output/ops.xlsx --mock
python -m parcel_track.cli report --tt <通途.xlsx> --out parcel_track_output/ops.xlsx --workers 4
```

跑完推到钉钉群（`--dry-run` 只打印卡片正文、不发群）：

```powershell
python -m parcel_track.cli report --tt <通途.xlsx> --notify
```

FedEx 单承运商旧入口：`python -m fedex_track.ops_report`。GLS 单承运商月报：`python -m gls_track.cli monthly`。

## 无人值守

- `--tt` 可以给**目录**：取其中最新的 `.xlsx`（导出落盘后直接跑，不用改命令行）。
- `--out` 省略时写 `parcel_track_output/ops_<YYYYMMDD>.xlsx`（父目录自动创建）。
- 跑挂时若带 `--notify`，会额外发一条钉钉纯文本告警，避免静默失败。

定时注册：[reference/scheduled-dingtalk-push.md](reference/scheduled-dingtalk-push.md)。
