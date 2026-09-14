# 物料发货状态报表 — Agent Handoff

> **脚本**: `EN_API/item_shipment_status.py`
> **输出**: `EN_API/out/{客户码或物料号}_发货状态_{ts}.xlsx`
> **回答的问题**: 某个物料的销售订单，哪些已发货、哪些没发、没发卡在哪一环

## 快速操作

```bash
# 按客户物料号 (模糊匹配, 大小写不敏感)
uv run python EN_API/item_shipment_status.py --customer-code CENKZ1325-Yellow-138

# 按 EN 物料号 (逗号分隔多个)
uv run python EN_API/item_shipment_status.py --item "PK#KS0001-DM-140-YELLOW"

# 只打控制台, 不出 Excel
uv run python EN_API/item_shipment_status.py --customer-code X --no-excel

# 回归自检 (内置 fixture 断言, 失败 exit 1)
uv run python EN_API/item_shipment_status.py --customer-code CENKZ1325-Yellow-138 --assert-fixture

# 测试环境 (ensh.vilavi.cn)
uv run python EN_API/item_shipment_status.py --customer-code X --test
```

常用参数: `-o/--output`、`--lead-months`(默认 3)、`--sleep`(默认 0.15)、`--env-file`。

## 数据链

```
客户物料号 (Item Customer Detail.ref_code)
  → Sales Order  (子表过滤 Sales Order Item, 按父单去重)
    → SO Item 行 (name = Production Plan Item.sales_order_item ★连接键)
      ├─ Delivery Note Item.against_sales_order → DN  已发/草稿
      ├─ Work Order.production_item             → WO  工单
      │    └─ Job Card.work_order               → Job Card  ★真实进度
      └─ Production Plan Item.sales_order       → PP  生产计划
```

## 查询链条与五条 API 硬约束

| # | 用途 | doctype | 关键 filters |
|---|------|---------|--------------|
| Q1 | 按客户码找单 | `Sales Order` | `[["Sales Order Item","customer_item_code","like","%码%"]]` |
| Q2 | 按物料码找单 | `Sales Order` | `[["Sales Order Item","item_code","in",[...]]]` |
| Q3 | 订单行明细 | `Sales Order` | `get_single(name)` → 读 `items[]` |
| Q4 | 销售出库 | `Delivery Note` | `[["Delivery Note Item","against_sales_order","in",SOs], ["Delivery Note Item","item_code","in",[...]]]` |
| Q5 | 生产工单 | `Work Order` | `[["production_item","in",[...]]]` |
| Q6 | 生产计划 | `Production Plan` | `[["Production Plan Item","sales_order","in",SOs]]` → 再按 item_code 过滤 po_items |
| Q7 | 物料主档 | `Item` | `get_single(code)` / `[["Item Customer Detail","ref_code","like","%码%"]]` |
| Q8 | 工序卡 | `Job Card` | `[["work_order","in",[...]]]` (分块) |

**约束 1 — 子表不能直接 list**：`GET /api/resource/Sales Order Item` → **403 PermissionError**。

**约束 2 — 父单直查子字段 → 417** `Field not permitted in query`。必须用
`[子表doctype, 字段, 操作符, 值]` 四元组形式，frappe 才会展开成子查询。

**约束 3 — 子表过滤"一行一子行"**：同一父单会重复出现。必须**先按父单 `name` 去重，再**
`get_single` 扇出，否则同一张单会被拉 N 次。脚本用 `dedupe_by()` 并在每处打印
`去重: N 行 → M 个单据`（对应 AGENTS.md 规则②的入 N 出 M 对账）。

**约束 4 — `in` 列表不能太长**：把 308 个 `work_order` 塞进 `Job Card` 过滤 → nginx
`400 Request Line is too large (6737 > 4094)`。所有 `in` 查询走 `chunks(..., IN_CHUNK=40)`。
`dn_trace_report.py` 也记录过同一问题（那里是全量拉取后 Python 侧过滤）。

**约束 5 — `fields` 只能是父单字段**：传未知字段 417（实测 `Item.has_bom` 被拒）。
子表值必须 `get_single` 后读 `doc["items"]` / `doc["po_items"]`。所有 list 查询都带
`fallback_fields`，遇 417 换窄字段集重试一次并打告警，不中断。

## Excel 输出

| Sheet | 内容 | 行粒度 | 列数 |
|-------|------|--------|------|
| 订单发货状态 | 订单行 + 出库/工单/工序/生产计划汇总 | 一行一 (SO × 订单行) | 27 |
| 出库明细 | 出库行明细 + 合计行 | 一行一 (SO × DN × 行) | 18 |
| 工单与工序 | 每张工单的每道工序 + 工序卡 | 一行一 (WO × 工序) | 15 |

## 关键设计

1. **两个入口模式并集语义不同**
   - `--customer-code`：先按客户码找单，再从订单行反推物料码，**在同一客户范围内**按物料码
     补一轮（抓订单行客户码为空的单）。
   - `--item`：直接按物料码找单，**不限客户**，所以结果通常是 `--customer-code` 的超集。
     实测本例：`--item` 18 张 SO（含其它客户），`--customer-code` 10 张。
   - **订单行物料码是精确匹配**（大小写不敏感）。`KS0001-…` 不能命中同单的 `PK#KS0001-…`
     或 `ND#…` 行。客户码才走子串/`like`。

2. **订单行 → 生产计划行的连接键是 `Sales Order Item.name` == `Production Plan Item.sales_order_item`**。
   不要用 `Production Plan Item.work_order`（这些行该字段为空）。

3. **出库单必须按 `item_code` 匹配，不能用 `customer_item_code`** ——
   实测 SO-25-00067 的出库行 `customer_item_code = NULL`，只按客户码会漏 20 件。

4. **客户码注册在成品 `KS` 上，订单行卖的是 `PK#` 皮壳** —— 两者不是同一个 item_code。
   实测 `CENKZ1325-Yellow-138` 挂在 `KS0001-DM-140-YELLOW`，订单行卖
   `PK#KS0001-DM-140-YELLOW`。所以「订单行物料自身的 `customer_items` 为空」是**常态**，
   不是数据缺失。脚本会单独打印客户码 → 注册物料的解析结果。

5. **docstatus 口径**：`1` 已发 / `0` 草稿（单独成列，不计入已发）/ `2` 排除并进异常区。
   `docstatus == 2` 且存在 `amended_from == 本单` 的后继单 → 判为「已改单(作废)，不计入未发」，
   与「单纯取消」区分开，否则总数对不上。

6. **预估可发 = 下单日期 + N 个月（默认 3）** —— 这是**业务约定、不是 ERP 字段**（计划同事口径）。
   列名、控制台、文档都标注了来源，别误当成系统数据。用 `--lead-months` 可调。

7. **工序卡才是真实进度** —— 见下节。

## ⚠ Work Order.status 不可信

实测：`WO-26-02609` 头部 `status = Not Started`、`produced_qty = 0`，但工序卡显示
44 件（2 批 × 22）。**截至 2026-09-14 下界**已完成 `裁剪 / 皮壳整件 / 锁扣眼 / 拷边`；
当天现场 `翻面` 从 Pending 变成 Completed，所以不要把「4 道」和「5 道」当成两份文档打架。
fixture 对在产工序只用下界（`⊇ 前 4 道` + `质检仍未完成`）。
**判断进度只看 `WO.status` 会把在产的工单误判成"未开工"。**

脚本因此：
- 报「**工单状态未回写**」：`WO.status ∈ {Not Started, Draft, Pending}` 但有已完成工序卡。
- 报「**工单未开工**」：0 张工序卡 + 工序全 Pending（如 `WO-26-03264`）。
- **完成件数取第一道工序（裁剪）的 `total_completed_qty`（空则退回 `for_quantity`），
  不是各工序求和** —— 每道工序都有自己的工序卡，求和会把同一批件数按工序数重复累加
  （WO-26-02609 会算成 4×44=176，实际 44）。
- 工单挂到「本 SO × 本物料」这一行；取消件（`docstatus>=2` / `Cancelled`）不计入进度。
- 超产跟工序卡完成量比 `WO.qty`，不看会停在 0 的头部 `produced_qty`。

`Job Card.time_logs` 只在**单文档**查询返回，列表查询没有；本脚本不需要。

## 技术要点

- **API**: ERPNext REST，`requests` 直连（无 session，避免 nginx 417）
- **分页**: `paginated_get` 相对 `dn_trace_report.py` 有两处修正（**只在新脚本，未回灌旧脚本**）：
  - 默认 `order_by="name asc"` —— 无稳定排序时跨页 `LIMIT/OFFSET` 会漏行或重复
  - 按**实收行数**前移（`start += len(data)`），不再 `page * page_size`（服务端返回不足一页时会跳行）
- **重试**: 实测 `erpnext.vilavi.cn` 偶发 `ConnectTimeoutError`，`api_get_status` 带 3 次重试
- **URL 编码**: 物料码含 `#`/`+`，`urllib.parse` 全量编码
- **凭证**: `.env` 里只有通用 `ERP_API_KEY`/`ERP_API_SECRET`（`.env.example` 文档的是
  `PROD_*`/`TEST_*`，实际不存在）。通用 key **在 prod 和 test 都能认证通过**，
  所以 `--test` 是真能跑的，不是摆设。

## 已知限制

- **只看本物料**：订单里若还有配套件（内胆 `ND#`、成品 `KS`），其进度不在本脚本范围。
  实测 SO-26-00101 名下 308 张工单（98 订单行 × 皮壳/内胆），全量查既超 Request Line
  限制又是噪音。「整单齐套能不能发」是另一个功能。
- **退货未抵扣**：退货型 DN / `Sales Invoice` 退货未从已发量净掉。
- **疑似重复下单是启发式**：同物料 + 同量 + 交货日相差 ≤ 3 天，仅 `warn`，绝不自动处置。
- **`--customer-code` 里的 `%`/`_` 会被当 LIKE 通配符**（ERPNext `like` 无转义钩子）。
- **`--assert-fixture` 只认 `--customer-code CENKZ1325-Yellow-138`**：`--item` 是不限客户的超集
  （本例 18 张 vs 10 张），对不上 fixture 的 `so_count`。数字取自 2026-09-14；若断言失败，
  **先确认是不是生产真的推进了**，不要直接改 fixture。list 查询 HTTP ≠ 200 会 `QueryError` 退出，
  不当空结果继续算。

## 实测结论 (2026-09-14)

`--customer-code CENKZ1325-Yellow-138` / `--item PK#KS0001-DM-140-YELLOW`
客户：美中公司 DANEEY，公司 FZH，仓库 半成品仓 - FZH

- 10 张 SO / 330 件 = 有效 310 + 已改单(作废) 20
- 已发 **126** / 未发 **184**
  - 死单(Closed未发) **64** — SO-26-00099 40 + SO-26-00003 20 + SO-25-00198 4
  - 在产/待发 **120** — SO-26-00101 40 + SO-26-00110 80
- 出库单 4 张：DN-25-00043(20) / DN-25-00138(60) / DN-26-00003(26) / DN-26-00039(20)
- 工单 18 张；工序卡 94 张覆盖 17 张工单
- 生产计划 6 张（其余为历史计划），本轮待产：PP-26-00033(40 待产) / PP-26-00036(80 待产)

**两条核心洞察**
1. **ERPNext 的 `Closed` ≠ 已发完** —— 10 张 SO 里 3 张 `Closed` 却仍有未发量。
2. **`Work Order.status` 不可信** —— `WO-26-02609` 写 `Not Started`，实际 44 件已过裁剪等前道工序
   （2026-09-14 下界 4 道；当天 `翻面` 后来也 Completed）。
