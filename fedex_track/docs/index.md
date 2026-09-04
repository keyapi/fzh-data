---
type: Module
title: fedex_track
description: FedEx 官方 Track API 批量查询，输出完整状态历史 + 建标/站点收件/交付关键时点
---

# fedex_track

给一批 FedEx 跟踪码 → 返回**完整状态历史**（每个扫描节点）+ 关键时点，用于销售核查仓库**迟发/漏发**。

## 关键决策

- 官方 `POST /track/v1/trackingnumbers`，每请求 ≤30 号，自动分块；OAuth2 client_credentials。
- **保留完整 `scanEvents`**（FedEx 响应为倒序，模块按升序全量保留）。
- 关键时点关键字提取：建标(Label created / Shipment information sent)、站点收件(Picked up / Arrived at FedEx location)、交付(Delivered / eventType DL)、取消(CA)。
- 只查号、不关心号是否属自有账号 → 跨渠道(VITE/蜴国际)出的 FedEx 单可查。

## 凭证

生产：`FEDEX_API_KEY/SECRET/FEDEX_ACCOUNT_NUMBER/FEDEX_ENV=production`（项目 fzh_fedex_track / 组织 Centrade(10548976) / 账号 879197228）。sandbox 用 2023 TEST key。

## 结构

`fedex_track/{client.py, models.py, batch.py, cli.py}`，参照 `ups_track`。输出 summary.csv / timeline.csv(完整历史) / raw.json。

## 环境/依赖

- `uv run python -m fedex_track.cli query --input <清单> --env production [--filter-carrier fedex] [--limit N]`
- 读 xlsx 需 openpyxl（已装）。
- 相关背景：`docs/research/2026-09-04-fedex-track-account-investigation.md`
