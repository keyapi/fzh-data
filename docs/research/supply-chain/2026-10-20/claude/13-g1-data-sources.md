---
okf: v0.1
type: Reference
title: G1 数据来源与映射清单（三角靠枕 × 两仓 × 2026-04..09）
description: 用现有 GSheet 与本地成本文件做 G1，不默认业务导出；权威映射用 ref_code/客户物料号；列出本地文件、缺口与脱敏规则
date: 2026-10-20
tags: [supply-chain, g1, data-source, mapping, tongtool, erpnext]
---

# 13 — G1 数据来源与映射清单

> 结论：**PR #304 是服务账号直读 GSheet 的 43 张月表，不是业务导出。**
> G1 默认用「现有 GSheet + 本地成本文件 + 权威映射」，业务导出只作缺口兜底。
> 本地文件含员工/买家信息，**只读使用、不提交仓库**。

## 1. 默认数据来源

| 数据 | 来源 | 说明 |
|---|---|---|
| 通途订单/发货行 | GSheet `通途订单YYYYMM` 的原始 ws `YYYY年M月订单` | PR #304 已验证 2023-01..2026-07 共 43 张；2026-08/09 也已核对存在 |
| 订单+成本处理结果 | 本地 `D:/Work/王忠于/成本核算/2026年{4..9}月订单_order_cost_*.xlsx` | 已含 `通途SKU/产品名称/品类orig/品类/品类统一名/材料编码/尺寸/有无扣/发货数量/渠道/发货仓库`；**是派生文件，不是原始凭证** |
| 历史档案 | `D:/文件存档/成本核算/` | 2022 起的历史成本文件，文件多且杂；用于 G2/G3 回补，不用于 G1 首选 |
| 通途SKU→EN物料 | `importBOMCostList.客户物料号`（GSheet）；EN `Item Customer Detail.ref_code`（SSH DB） | 权威桥；**直连优先**，旧键兜底 [dce9769a] |
| EN 产品/物料组 | EN 主数据（KS0001/KS0248） | 只读；G1 用本地导出或测试环境，不写生产 |
| 库存快照（cutoff） | **通途 `stock_alert`（PR #298 / `a4b1cf4d`）**：`stock_alert/client.py` 调 `erp2_stocks_stocksquery`；每日任务 `FZH-StockAlert-daily`（默认 09:23）；`web_automation tongtu.stock.export` 可定时导出 6 仓库存 | **只需 cutoff 当日快照**，不是 6 个月库存序列；字段：`goodsSku/availableStockQuantity/intransitStockQuantity/defectsStockQuantity/waitingShipmentStockQuantity`；按 `warehouseName` 整仓分页（pageSize≤100，5 次/分钟） |
| EN SO/PP/WO/JC/SE/DN | **EN API 只读**：`EN_API/item_shipment_status.py`（SO→PP→WO→JC→DN）、#291 `EN_API/fulfillment_query.py`、`erpnext/scripts/fetch.py` | 按单号/SKU 查询，缓存到本地 Parquet 以便复现；不写生产 |

### 1.1 库存历史限制（重要）

- **通途 API 只给当前库存，没有历史序列。**
- `stock_alert` 每日任务只写**低库存行**，不是全量归档。
- `web_automation tongtu.stock.export` 可定时导出 6 仓库存，但本机没有历史输出。
- 本地只有 `20260514`、`20260807` 等稀疏结存，不能当连续历史。
- **G1 只用 cutoff 当前快照；历史库存标 `not_available`。**
- **P0**：从今天起每日全量快照（两仓）→ 不可变 Parquet，保留 13 个月；
  不能用低库存告警结果代归档。库存策略回测等积累 3–6 个月后再做。

### 1.2 本地 2026-04..09 最新文件（示例）

| 月 | 文件 |
|---|---|
| 2026-04 | `2026年4月订单_order_cost_2026-06-01_13-52-53.xlsx` |
| 2026-05 | `2026年5月订单_order_cost_2026-07-08_15-45-40.xlsx` |
| 2026-06 | `2026年6月订单_order_cost_2026-08-06_14-55-45.xlsx` |
| 2026-07 | `2026年7月订单_order_cost_2026-10-09_11-23-27.xlsx` |
| 2026-08 | `2026年8月订单_order_cost_2026-09-03_13-37-47.xlsx` |
| 2026-09 | `2026年9月订单_order_cost_2026-10-14_16-09-47.xlsx` |

目录：`D:/Work/王忠于/成本核算/`。这些文件是 Colab/成本流程的**处理结果**，
不是通途原始导出；行级 trace 用 `发货日期/通途SKU/包裹号/订单号` 回查 GSheet。

### 1.2 2026-09 三角行画像（只读）

- 总行 6,246；含「三角」的行 3,971；发货件约 4,111。
- `品类orig` 多为 `自产-三角靠枕-<面料>`；`品类` 多为「三角」；`品类统一名` 多为「三角靠枕」。
- 仓库：美东-CENTRADE 1,631；美中-FZH-DANEEY 1,590；波兰 covers 558；WayfairCG 137；Daneey 退货仓 55。
- 有无扣：有扣 3,280；无扣 511；空 180。
- **`品类/品类统一名` 是 Colab 4.2 的派生物，可能不一致**；G1 不用它当唯一键。

### 1.3 现有记录（直接复用，不再新做）

| 记录 | 用途 |
|---|---|
| **PR #303**（`40309079`，已合并）`EN_API/query_customer_items_suffix.py` + `erpnext_bi/` | EN `customer_items.ref_code` 查询工具/BI 看板；只读；**对生产运行需授权**，G1 先用已有导出 |
| **PR #298 / `a4b1cf4d`** `stock_alert/` | 通途库存客户端 + `FZH-StockAlert-daily` 定时任务；`stock_alert/client.py` 调 `erp2_stocks_stocksquery`，按仓分页（pageSize≤100，5 次/分钟） |
| `web_automation/scripts/install_tongtu_schedule.ps1` | 通途导出定时任务（sales/both，间隔或固定时刻）；可作为库存/订单导出兜底 |
| `EN_API/item_shipment_status.py`；#291 `EN_API/fulfillment_query.py`；`erpnext/scripts/fetch.py` | EN SO/PP/WO/Job Card/SE/DN 只读查询入口 |
| `docs/solutions/integration-issues/tongtu-en-item-mapping-and-gsheet-source-fix.md`（2026-10-17） | 权威映射、99.9% 覆盖、前缀过滤/解析键坑；本页的上游依据 |
| `dce9769a` | 权威映射文档 + GSheet 源头修正 |
| `7f837046` | 直连按通途SKU 精确匹配（原来拼接串没命中）+ 双源并集 |
| `83c05e8a` | `--direct-map` 直连优先 + B2 兜底 |
| `e95cd351` | 直连优先（通途SKU→EN物料→重量模板）+ 旧键兜底 |
| `tongtool_order_cost/docs/reference/cost-engine-spec/16 / 27 / 28`（#295） | 客户物料号直连、GSheet 源头、解析 vs EN 体检 |
| `tongtool_order_cost/docs/reference/overseas-labor-multidim-method.md`（2026-10-19） | 映射 A/B、成本来源 α/β；映射/成本对照 |
| 本地 `D:/Work/赛狐/Cursor/en_tongtool_cost_review/`、`en_bom_cost_list/` | EN 成本/BOM 记录；只读复用 |
| 本地 `通途SKU缺EN客户物料号20251202/合并库存通途SKU与ENTTSKU客户物料号_20251202_095545.xlsx` | 历史映射/库存合并样例 |
| **PR #304** `docs/research/2026-08-31-demand-forecast-data-feasibility.md` | GSheet 43 个月、通途SKU↔EN 映射路径 |

> 这些记录已经存在，G1 不重复造映射；只在缺口处补数据。

## 2. 映射规则（权威优先级）

1. **从 EN 叶子物料组出发**：`KS0001 三角靠枕`、`KS0248 三角靠枕无扣`；保留 leaf group/SKU。

2. **映射优先级（用户 2026-10-20 确认）**：

| 优先级 | 来源 | 用法 | 标记 |
|---|---|---|---|
| **P1** | **通途SKU → EN 客户物料号**：EN `Tongtool Order` 父单 `order_items` 明细；EN BOM 成本表 `importBOMCostList.客户物料号`；EN `Item Customer Detail.ref_code` | 三者都是精确匹配桥；按通途SKU 查，命中即用；冲突进异常 | `mapping_source=tongtool_order` / `bom_cost_list` / `ref_code` |
| **P2（仅参考）** | GSheet「写回」结果里的 `品类/品类统一名`（如「三角」「三角靠枕」） | 只作候选/对照，**不能当映射主键** | `reference_only=true` |
| **P3（兜底）** | Colab 4.2 及后续派生物：`品类orig/材料编码/尺寸/有无扣/品类尺寸面料编码` | **仅当 P1 缺失时使用**；可能不一致 | `mapping_source=colab_4_2`，输出 `fallback=true` |

- **不要**用拼接串或按前缀过滤（`TT` 前缀会漏 `CE/SX/PP`）；完整通途SKU 精确匹配。
- `Tongtool Order Item` 不能直接查列表（403）；item 级数据从父单 `GET /api/resource/Tongtool Order/{name}` 的 `order_items` 读取。
- 旧键 `品类尺寸面料编码` 只作最后兜底；解析键可能指错（实测 KS0423/KS0396 撞车）。
- 直连覆盖实测 99.9%（2026-07 美中 4372 行，未匹配 7）[dce9769a/7f837046]。
- 任何 P3 行必须单列报告，不能与 P1/P2 混在一起当“已映射”。

3. **GSheet/本地文件里的「三角」只作候选**：
   - `品类orig` 含「自产-三角靠枕-*」可作候选；
   - `品类统一名` 的「三角靠枕」「三角带圆柱」等不能直接等同 KS0001/KS0248；
   - 一行只归一个 leaf group；同时命中 KS0001/KS0248 → `ambiguous`，不取 max/平均。

4. **family 只用于规划聚合**；成本、BOM、库存仍按 leaf group/SKU。

## 3. 缺口与兜底

| 缺口 | 兜底 | 不能做什么 |
|---|---|---|
| 库存时间线 | **G1 只需 cutoff 当日快照**；用 `stock_alert`/`FZH-StockAlert-daily` 或通途 API 拉最新快照；如需历史，逐日快照留档 | **不要造“6 个月库存序列”**；不能拿 EN Bin 当可用库存；不能补 0 |
| EN 生产/出库单据 | 用 EN API 只读（`item_shipment_status.py` / `fulfillment_query.py` / `erpnext/scripts/fetch.py`）；按单号/SKU 查询并缓存 | `Tongtool Order Item` 列表 403，从父单 `order_items` 读；不写生产 |
| 头程事件 | 钉钉表/现有文件；没有标 unknown | 不能用“订单日期+3个月”冒充 ETA |
| 历史 2023-01..2026-09 | `D:/文件存档/成本核算` + GSheet 月表 | 不能把处理后的品类当原始事实 |

**业务导出只在上述缺口无法用现有文件补齐时使用**，不是 G1 的默认前提。

## 4. 脱敏与存储

- 本地成本文件含员工名（如执行发货人）与可能的买家字段；G1 只取
  `发货日期/通途SKU/产品名称/品类orig/材料编码/尺寸/有无扣/发货数量/渠道/发货仓库/包裹号/订单号`，
  其余 PII 列丢弃或哈希。
- 不导出/不提交客户姓名、地址、电话、邮箱、买家 ID；订单号/包裹号如需关联用稳定哈希。
- 中间 Parquet/DuckDB 只放本地或 NAS 指定目录，**不入 git**。

## 5. 验收（收到/读取数据后）

- [ ] 每月行数与 GSheet 原始 ws 对账，差异可解释。
- [ ] 两仓都覆盖 2026-04..09；三角 family 映射覆盖率与未匹配清单。
- [ ] `品类统一名` 与 `品类orig` 的差异单列，不用前者当唯一键。
- [ ] 缺失/坏数量/歧义单列，不静默丢弃。
- [ ] 无 PII、无凭证。
