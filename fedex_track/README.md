# fedex_track — FedEx 官方 Track API 批量查询（仿 ups_track）

给一批 FedEx 跟踪码 → 返回**完整状态历史**（每个扫描节点）+ 关键时点（建标/站点收件/交付），用于销售核查**迟发/漏发**（尤其"站点收件时间"）。

## 特点

- 官方 `POST /track/v1/trackingnumbers`，**每请求 ≤30 号**，超出自动分块；OAuth2 client_credentials。
- **保留完整 `scanEvents` 历史** → 输出 timeline 是每个节点一行。
- 关键时点：`建标时间 / 站点收件时间 / 交付时间`（站点收件= Picked up / Arrived at FedEx location）。
- 支持 txt / csv / **xlsx** 清单；`--filter-carrier fedex` 可从混合单号（带 UPS/USPS）中只留 FedEx。
- 只查号、不关心号是否属于自己账号（跨渠道/VITE/蜴国际 出的 FedEx 单都可查）。

## 凭证（env）

```bash
FEDEX_API_KEY=...          # 生产（项目 fzh_fedex_track / 组织 Centrade 10548976 / 账号 879197228）
FEDEX_SECRET_KEY=...
FEDEX_ACCOUNT_NUMBER=879197228
FEDEX_ENV=production        # production | sandbox（sandbox 用 2023 TEST key）
```

## 用法

```bash
# 离线演示（无凭证）
uv run python -m fedex_track.cli query --input tracking.txt --out result --mock

# 生产：读 xlsx，只留 FedEx，查前 10 个
uv run python -m fedex_track.cli query \
  --input "D:\Work\王忠于\成本核算\通途非FBA订单202608 202609030947 无需填0售价 加预估尾程.xlsx" \
  --env production --filter-carrier fedex --limit 10 --out result
```

输出三件套（同前缀）：
- `result.summary.csv` — 每号一行：当前状态/已交付/已取消/建标/站点收件/交付时间
- `result.timeline.csv` — 每号每个节点一行（**完整历史**）
- `result.raw.json` — 每号原始响应（断点续跑依据）

## 结构

`fedex_track/{client.py, models.py, batch.py, cli.py}`，参照 `ups_track`。
