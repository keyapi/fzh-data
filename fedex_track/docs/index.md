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
- **同号多票**：FedEx 复用跟踪号（约 4–6 年一轮回，号码前段/SCC 常数段常绑指定发件账号），同一号可能对应多票。模块对每个号**保留全部 trackResult**；summary/timeline 用 `[n]` 后缀区分、加 `多票`/`分票` 列。判断归属：按**建标/交付时间**落在该单所属发货窗口的那一票。

## 凭证

生产：`FEDEX_API_KEY/SECRET/FEDEX_ACCOUNT_NUMBER/FEDEX_ENV=production`（项目 fzh_fedex_track / 组织 Centrade(10548976) / 账号 879197228）。sandbox 用 2023 TEST key。

## 结构

`fedex_track/{client.py, models.py, batch.py, cli.py, ops_report.py, README.md, AGENT_HANDOFF.md}`，参照 `ups_track`。输出 summary.csv / timeline.csv(完整历史) / raw.json。

- **交接**：见 `AGENT_HANDOFF.md`（Agent 入口），skill 见 `.agents/skills/fedex-track/SKILL.md`。
- **运营报表**：`ops_report.py` 生成多 Sheet 异常 Excel，runbook 见 `docs/ops-report-runbook.md`。
- **背景/教训**：`docs/solutions/workflow-issues/fedex-track-batch-query.md`、`docs/research/2026-09-04-fedex-track-account-investigation.md`。
- 已知坑：同号多票(复用号)、"已取消"仅当最终为取消且未交付、FedEx 反爬假报错需第二来源、配额按请求不按号。

## 环境/依赖

- `uv run python -m fedex_track.cli query --input <清单> --env production [--filter-carrier fedex] [--limit N]`
- 读 xlsx 需 openpyxl（已装）。
- 相关背景：`docs/research/2026-09-04-fedex-track-account-investigation.md`
