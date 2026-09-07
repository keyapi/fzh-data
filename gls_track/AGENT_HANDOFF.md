# gls_track AGENT_HANDOFF

Agent 参考（人读见 [README.md](README.md)；OKF 文档见 [docs/index.md](docs/index.md)）。

## 这是什么 / 为什么

波兰分公司经 **GLS 波兰**自发货的 GLS 单号批量跟踪。**不需要开发者账号 / 不需要波兰 GLS 登录**：
GLS 的消费级网页跟踪底层是**公开无鉴权 REST**（`rstt029` 摘要 / `rstt028` 明细需目的邮编），本模块直接走它。
调研/口径见 `docs/research/2026-09-07-gls-poland-track-feasibility.md`；已解决坑见
`docs/solutions/integration-issues/gls-track-public-rest-calendar.md`。

## 模块文件

| 文件 | 作用 |
|---|---|
| `client.py` | httpx 客户端：`summary(no)` / `detail(no, postal)` / `track(no, postal?)`。免账号；有邮编只调 `rstt028` 一次即可拿全量 history。共享连接池线程安全。 |
| `models.py` | 解析 → `GlsParcel`：当前状态、delivered、关键时点 数据录入(≈建标)/交接GLS(≈收件)/交付 + 全量 events + cust_ref。 |
| `cli.py` | `query`（批量查）；`monthly`（批量查 + 直接出 FedEx 风格 8-Sheet 异常表 `{out}_ops.xlsx`）；`--workers`(默认4) / `--resume`(仅中断续跑，**不刷新**)；loader 自动**一格多号拆分**+去重。 |
| `ops_report.py` | FedEx 风格运营异常表；**GLS 独立口径**（见下）。 |
| `tests/` | 离线单测（httpx MockTransport；11 passed）。 |

## 端点（实测 2026-09-07；宿主 gls-group.com，实例 /PL/en/）

- 摘要：`GET /app/service/open/rest/PL/en/rstt029?match={号}&type=&caller=witt002&millis={ms}`
- 明细：`GET /app/service/open/rest/PL/en/rstt028/{号}?caller=witt002&millis={ms}&postalCode={目的邮编}`

**明细是唯一能拿全量 history 的**；钥匙 = 目的邮编（页面收货人侧校验用），通途订单 `邮编` 列有。
无邮编退化为摘要（只有状态/交付时间）。

## 常用命令

```bash
python -m gls_track.cli query   --input <通途xlsx|txt> --out result [--workers 4] [--limit N]
python -m gls_track.cli monthly --input <当月通途xlsx> --out gls_202608 --workers 4
#   → gls_202608.summary.csv / .timeline.csv / gls_202608_ops.xlsx
python -m gls_track.ops_report --summary result.summary.csv --tt <通途xlsx> --out out.xlsx
```

## summary 列 → ops 判定映射

- 数据录入时间 ≈ **建标**（history 首条 "data was entered into the GLS IT system..."）
- 交接GLS时间 ≈ **收件首扫**（"was handed over to GLS"，排除文案里的 "not yet handed over"）
- 交付时间 = delivered 事件 / arrivalTime
- 错误非空 → 「数据异常/查无」（非 GLS 号 / GLS 查无）

## GLS 口径（区别于 FedEx 表，见 ops_report.py 顶部可调）

- `HANDLING_DAYS = 2`（FedEx 表为 1；GLS 周四录入→周一交接不再误判迟发）
- 营业日 = 排除周末（`np.busday_count` 天然）+ **波兰 2026 法定假日** `PL_HOLIDAYS_2026`（起运/交接在 GLS 波兰；**勿沿用 FedEx 美国联邦假日**；12/24 Wigilia 自 2025 起法定）
- 「Amazon是否判迟」**仅 Amazon/亚马逊 渠道**标（非 Amazon 渠道不判）

## 已知边界 / 坑

- **一格多号**：通途 `跟踪号` 单元格可能塞多个号/混入 UPS `1Z`、allegro `…U`、截断碎片 → loader 自动拆分；非 GLS 号照查会 404 → 报表「数据异常/查无」待清源，属源数据问题不是工具问题。
- **返件**：先 DELIVERED 后又回退（如 29626350320 派送→回 Strykow）头条 INTRANSIT → 报表按“先交付后回退+头条非DELIVERED”归在途，不误标正常交付。
- **GLS 公开查询窗口**：部分已交付很久的单号可能随机 404（“no results”）；两批相隔几小时结果可能略有出入。
- **限流**：公开接口无速率头/无公开限流文档；共享连接池 ≤8 并发实测安全（默认 4）；每请求新建 TLS 会零星 transport 失败 → 用共享 client + 重试。欧盟无统一假日；本表波兰单历近似。
- **隐私红线**：不提交客户行数据 / 凭证；凭证类走父仓库 `.env`（本模块无凭证）。样本仅测试单号。

## 与 parcel_track(PR #215, Cursor 统一多承运商)的关系

- 统一的多承运商 runner 由 **Cursor 在 parcel_track** 做；届时把 `gls_track` 当 GLS adapter 接入。
- 接 parcel_track 需对齐的归一字段（UPS/FedEx 同款）：`跟踪号 / 承运商=gls / 交付时间 / 站点收件时间(=交接GLS时间) / 建标时间(=数据录入时间) / 最近节点时间 / 当前状态 / 已取消`。
- GLS 给统一侧的**可选改进点**：① 日历要能按 承运商/区域 配置（US 联邦 vs 波兰，FedEx 表硬编码 US 假日；GLS 用波兰）；② GOFO 无官方自服务 Track，仍停放待 VITE/聚合；③ 单号形态过滤（`…U`/`1Z`/`1303…`/`1049…` 不是 GLS 号段）；④ 区域(欧洲/美国)分类若做，建议以收货国为主、货主仓兜底。
