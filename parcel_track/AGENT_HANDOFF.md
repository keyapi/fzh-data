# parcel_track — Agent 交接

> **通途订单混合尾程跟踪 + 共享运营异常报表**
> 人读：[README.md](README.md) ｜ OKF：[docs/index.md](docs/index.md)

## 这是什么

一张通途表分流到 `ups_track` / `fedex_track` 官方客户端 + `gls_track` 公开 REST，用 `parcel_track.classify` 做迟发/承运延误/卡件。FedEx 旧 `fedex_track.ops_report` 仍可用。GLS 单承运商月报仍可用 `python -m gls_track.cli monthly`。

## 何时用

- 通途订单里 UPS / FedEx / GLS 混在一起，要一张异常表
- GOFO / TikTok / USPS 无官方自助 Track：停放，不要擅自接 AfterShip

## 命令

```powershell
uv run python -m parcel_track.cli report --tt <xlsx> --out parcel_track_output/ops.xlsx --mock
uv run python -m pytest parcel_track/tests fedex_track/tests/test_ops_report.py gls_track/tests -q
```

工作树内不要 `uv run`（会另建 `.venv`）；用父仓库 `.venv\Scripts\python.exe`。

## 口径

- UPS/FedEx：美国联邦假日，`HANDLING_DAYS=1`
- GLS：波兰 2026 法定假日（含 12/24 Wigilia），`HANDLING_DAYS=2`；建标=数据录入，收件=交接 GLS；返件（先交付后头条非 DELIVERED）归在途
- 「Amazon是否判迟」仅 Amazon/亚马逊 渠道
- 一格多号会拆开；GLS 格里的 `1Z` 改走 UPS，allegro `…U` 停放 `not_gls_number`

详见 `fedex_track/docs/ops-report-runbook.md` 与 `gls_track/AGENT_HANDOFF.md`。
