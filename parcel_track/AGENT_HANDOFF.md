# parcel_track — Agent 交接

> **通途订单混合尾程跟踪 + 共享运营异常报表 + 钉钉推送**
> 人读：[README.md](README.md) ｜ OKF：[docs/index.md](docs/index.md)

## 这是什么

一张通途表分流到 `ups_track` / `fedex_track` 官方客户端 + `gls_track` 公开 REST，用 `parcel_track.classify` 做迟发/承运延误/卡件。FedEx 旧 `fedex_track.ops_report` 仍可用。GLS 单承运商月报仍可用 `python -m gls_track.cli monthly`。

`notify.py` 把出好的 Excel 传到 ERPNext、用钉钉 ActionCard 推到群（复用 `dingtalk/dingtalk_robot`）。

## 何时用

- 通途订单里 UPS / FedEx / GLS 混在一起，要一张异常表
- 要按天/周无人值守跑完并推钉钉群 → [docs/reference/scheduled-dingtalk-push.md](docs/reference/scheduled-dingtalk-push.md)
- GOFO / TikTok / USPS 无官方自助 Track：停放，不要擅自接 AfterShip

## 命令

```powershell
# 离线形状检查
python -m parcel_track.cli report --tt <xlsx> --out parcel_track_output/ops.xlsx --mock

# live：每家 --workers 默认 4，三家串行（先 UPS 再 FedEx 再 GLS，峰值 4 不是 12）
python -m parcel_track.cli report --tt <xlsx> --out parcel_track_output/ops.xlsx --workers 4

# 推钉钉（--dry-run 只打印卡片正文不发群；失败会补发一条告警）
python -m parcel_track.cli report --tt <xlsx> --notify
python -m parcel_track.cli report --tt <xlsx> --notify --dry-run

# 无人值守：--tt 给目录=取最新 xlsx；--out 省略=parcel_track_output/ops_<日期>.xlsx
python -m parcel_track.cli report --tt parcel_track_input --notify

# 定时注册（任务名 FZH-ParcelTrack-<daily|weekly>）
powershell -ExecutionPolicy Bypass -File parcel_track\scripts\install_parcel_track_schedule.ps1 -Task daily -AtTime "09:07"

python -m pytest parcel_track/tests fedex_track/tests/test_ops_report.py gls_track/tests -q
```

> ⚠️ `ups_track/tests` 和 `fedex_track/tests` 的测试模块重名，**这两个不能同时给**（collection error）。
> `gls_track/tests/test_ops_report.py::test_build_workbook` 目前是**既有失败**（fixture 写死日期的时间炸弹，与 parcel_track 无关），已单独挂任务修。

工作树内不要 `uv run`（会另建 `.venv`）；用父仓库 `.venv\Scripts\python.exe`，并设 `PYTHONPATH` 为工作树根。凭证：CLI 依次加载工作树/仓库/sibling worktree 的 `.env`（`override=False`，只补未 export 的变量）。禁止把 key 写入文档或 commit。

## 推送口径

- 推文正文由 `notify.summarize()` 渲染，**钉钉 markdown 不渲染表格**，所以用列表
- 分类按待办优先级排：漏发/未交接 → 卡件 → 迟发 → 承运延误（`carrier_slow`/`fedex_slow` 合并一行）→ 数据异常/查无；计数取自 `run_report()` 返回的 `counts`
- `--dry-run` 不发网络、不需凭证，可离线看正文
- 钉钉自定义机器人限 **20 条/分钟**

## 口径

- UPS/FedEx：美国联邦假日；GLS：波兰 2026 法定假日（含 12/24 Wigilia）
- **处理时间统一 3 个营业日**（`HANDLING_DAYS=3`）；假日历仍分叉
- `--workers N`：**每个**承运商 N 路并发，承运商之间顺序执行
- GLS 建标=数据录入，收件=交接 GLS；返件（先交付后头条非 DELIVERED）归在途
- 「Amazon是否判迟」仅 Amazon/亚马逊 渠道
- 一格多号会拆开；GLS 格里的 `1Z` 改走 UPS，allegro `…U` 停放 `not_gls_number`
- GOFO / TikTok / USPS：停放，不查、不丢

口径长文：`docs/solutions/conventions/parcel-track-handling-days-sequential-workers.md`。
FedEx 单承运商 runbook：`fedex_track/docs/ops-report-runbook.md`。GLS 先行：`gls_track/AGENT_HANDOFF.md`。
