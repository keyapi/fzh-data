---
okf: v0.1
type: Guide
title: parcel_track — 通途混合尾程跟踪
description: 一张通途订单表分流 UPS/FedEx/GLS，输出共享运营异常 Excel
updated: 2026-09-08
---

# parcel_track

给运营：一份通途非 FBA 订单 xlsx → 自动识别 UPS / FedEx / GLS → 查询 → 一张异常表（迟发优先交接、延误优先于迟发）。

- UPS / FedEx：官方 Track（需根 `.env` 凭证）
- GLS：公开无鉴权 REST（`gls_track`，需通途 `邮编` 列做明细；免账号）
- GOFO / TikTok 派送 / USPS / 无法识别：进入「未支持/停放」，不丢弃、不查询

## 快速开始

```powershell
uv run python -m parcel_track.cli report --tt 通途非FBA订单.xlsx --out parcel_track_output/ops.xlsx --mock
```

真实查询：UPS/FedEx 需凭证；GLS 不需要。先 `--limit 10` 冒烟，全量须用户确认。

## 非目标

- 不买面单（那是 `sellfox_shipping`）
- 不写回赛狐 trackNo
- 不接入 AfterShip / 17TRACK / Karrio 作为主路径
