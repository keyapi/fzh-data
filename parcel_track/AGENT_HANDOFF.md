# parcel_track — Agent 交接

> **通途订单混合尾程跟踪 + 共享运营异常报表**
> 人读：[README.md](README.md) ｜ OKF：[docs/index.md](docs/index.md)

## 这是什么

一张通途表分流到现有 `ups_track` / `fedex_track` 官方客户端，用 `parcel_track.classify` 做迟发/承运延误/卡件。FedEx 旧 `fedex_track.ops_report` 仍可用，分类函数已改从本模块引入。

## 何时用

- 通途订单里 UPS 和 FedEx 混在一起，要一张异常表
- 不要为 GLS/GOFO 去装聚合商；停放即可

## 命令

```powershell
uv run python -m parcel_track.cli report --tt <xlsx> --out parcel_track_output/ops.xlsx --mock
uv run python -m pytest parcel_track/tests fedex_track/tests/test_ops_report.py -q
```

## 口径

见 `fedex_track/docs/ops-report-runbook.md`。UPS 与 FedEx 共用营业日日历；UPS 在途天数阈值未单独校准，口径说明里写明。
