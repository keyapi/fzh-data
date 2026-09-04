# fedex_track — Agent 交接说明

> **FedEx 官方 Track API 批量查询 + 运营异常报表**
> **人读文档**: [README.md](README.md) ｜ **模块 OKF**: [docs/index.md](docs/index.md)

## 这是什么

给一批 FedEx 跟踪码 → **完整状态历史**（全部 `scanEvents`）+ 关键时点（建标/站点收件/交付）+ **运营异常报表**（多 Sheet、配色、Amazon 营业日/假日口径）。仿 `ups_track`。用于销售核查**迟发/漏发**（尤其站点收件时间 vs 发货时间），以及后续做"FedEx 延误 / 卡件 / 取消 / 数据异常"的运营排待办。

## 新对话必读

1. `fedex_track/docs/index.md`（模块说明）
2. `docs/solutions/workflow-issues/fedex-track-batch-query.md`（背景 / 账号组织恢复路径 / 三条教训）
3. `docs/research/2026-09-04-fedex-track-account-investigation.md`（完整勘查、凭证实测、腾讯邮箱接收链路、原始 URL）

## 凭证（只写来源，不写明文）

- **生产**：根 `.env` 的 `FEDEX_API_KEY / FEDEX_SECRET_KEY / FEDEX_ACCOUNT_NUMBER / FEDEX_ENV=production`（项目 `fzh_fedex_track` / 组织 **Centrade(10548976)** / 账号 **879197228**）。⚠️ **secret 只在门户显示一次**，勿随意重新生成。
- **sandbox**：`FEDEX_ENV=sandbox`（用 2023 TEST key）。测试环境与生产 token 不通用。

## 快速开始

```bash
set -a && . ./.env && set +a   # 凭证从根 .env 读

# 批量查询（txt/csv/xlsx 清单，自动识别跟踪号列；--filter-carrier fedex 只留 FedEx）
uv run python -m fedex_track.cli query --input <清单> --env production [--filter-carrier fedex] [--limit N] --out <前缀>

# 生成运营异常报表（多 Sheet + 配色 + 汇总）
uv run python -m fedex_track.ops_report --out fedex_track_output/fedex_ops_report_<date>.xlsx
```

输出三件套（query）：`<前缀>.summary.csv`（每票一行：当前状态/已交付/已取消/建标/站点收件/交付）、`<前缀>.timeline.csv`（每节点一行，完整历史）、`<前缀>.raw.json`（每号完整原始响应，可归档）。

## 硬规则 / 易错点（务必先读）

- **同号多票**：FedEx **复用跟踪号**（约 4–6 年一轮，号码前段/SCC 常绑指定发件账号），同一号可能对应多票。模块对每号**保留全部 trackResult**，用 `[n]` 后缀 + `多票`/`分票` 列区分；判归属按**建标/交付时间**落在该单所属发货窗口的那一票。无建标、直接从 Picked up 开始的一票标为"复用旧票(缺建标)"。
- **"已取消"**：**仅当**最终状态(`latestStatusDetail.code in CA/CAF`)**且未交付**才算取消。FedEx 事件流可能**残留一条 `CA cancel` 节点但包裹实际已交付**（曾误标 4 单，已修）。`fedex_slow`、`reused_no_label` 等分类勿与取消混淆。
- **反爬假报错**：FedEx(Akamai) 对 headless/自动化返回**假的** `system-error` + "can't find that tracking number"。下"查无/不行"结论前**至少第二来源**（真实 Chrome / 官方 API / 用户实测 / 文档）；对反爬站，**同会话先暖机（访问几页、接受 cookie）再重试**往往就过。**不要**把自动化一次的 `can't find` 当铁证。
- **配额按请求次数**：Track 能力 **10 万次/日**、限速 **1400 次/10 秒**，且**每请求 ≤30 号**。几万号也就几百次请求，远低于配额，**不会触发超额收费**（超额的"overage 费用"条款在 10 万次/日之上，量级碰不到；收费的 AIV 是另一付费产品）。
- **迟发口径（ops_report）**：起点=**建标时间**，确认发货=**站点收件时间**；延迟 = 建标→收件的**营业日**数 − 处理时间(默认 1 天)。营业日**排除周末 + 美国联邦节假日**，贴近 Amazon LSR（ship-by = 下单日 + 处理时间，只算工作日）。
- **`发货日期`列含义要核实**：通途表"发货日期"(第 0 列) 是"标记发货日"，未必是真实出库/交接时间；报表已改用**建标时间**为基准，`发货日期`仅作参考。
- **运营报表阈值在 `ops_report.py` 顶部**（`HANDLING_DAYS`/`TRANSIT_SLOW_DAYS`/`STUCK_DAYS`/`MISSING_AFTER_DAYS`/`US_HOLIDAYS`），可按实际调整。

## 结构

```
fedex_track/
  client.py      # OAuth2 token 缓存 + track_many(≤30/请求, 保留多票)
  models.py      # 归一化: 完整 scanEvents + 三时点 + 多票/取消判定; 词表可调
  batch.py       # 分块并发/重试/断点续跑; txt/csv/xlsx 清单, 自动识别跟踪号列
  cli.py         # query: 输出 summary/timeline/raw 三件套
  ops_report.py  # 运营异常报表生成器(多Sheet/配色/Amazon口径)
  README.md      # 人读
  docs/{index,log}.md + AGENT_HANDOFF.md
```
