---
okf: v0.1
type: Reference
title: 月度盈利审计（通途订单 xlsx / GSheet → 成本·运费·利润）
description: 只读冻结月源 → 离线复现「平均产品成本/平均运费/利润倒挂」→ JSON + Excel 证据簿 + 管理摘要的两阶段 CLI、口径矩阵、对账闸门与决策归属
tags: [tongtu, profitability, audit, gsheet, erpnext, report, reference]
resource: tongtool_order_cost/scripts/audit_monthly_profitability.py
---

# 月度盈利审计

> 用途：老板/财务质疑某月"平均成本低、平均运费低、回款低反而利润高"时，
> **不改任何线上数据**，把当月源冻结下来、把口径摊开、把每条差异下钻到源行。

## 一句话

**先 `snapshot` 冻结，再 `analyze` 离线**。分析只吃本地快照，不再联网；
产出 `audit.json` + `audit.xlsx`（17 张表）+ `管理摘要.md`，全部落在 gitignore 的 `out/`。

## 命令

```bash
export GSPREAD_SERVICE_ACCOUNT_FILE='<父仓库>/secrets/gsheets-service-account.json'

# 1) 冻结（只读；必需源缺失即阻断）
uv run python tongtool_order_cost/scripts/audit_monthly_profitability.py \
    snapshot --month 202607 --with-finance
#   → tongtool_order_cost/out/profitability_audit/2026年7月订单/{manifest.json,<key>/*.csv}

# 2) 离线分析（不联网）
uv run python tongtool_order_cost/scripts/audit_monthly_profitability.py \
    analyze --snapshot tongtool_order_cost/out/profitability_audit/2026年7月订单
#   → out/profitability_audit/analyze_<ts>/{audit.json,audit.xlsx,管理摘要.md}

# 只列 worksheet 与角色（不落盘）
uv run python tongtool_order_cost/scripts/audit_monthly_profitability.py list --month 202607
```

CLI **没有** apply / write / update / upload 任何标志；本文件不 import 月度上传函数。

## 7 月实证源（`通途订单202607`）

| key | worksheet | 行数 | 角色 |
|---|---|---:|---|
| `raw` | `2026年7月订单` | 9,604 | **原始订单（唯一 raw，必需）** |
| `raw_fba` | `2026年7月FBA订单` | 133 | FBA **MSKU 汇总**（无订单行/包裹） |
| `writeback` | `写回2026年7月订单` | 9,579 | 派生（成本/系数轨） |
| `writeback_fba` | `写回2026年7月FBA订单` | 1,653 | 派生 FBA |
| `writeback_combined` | `写回2026年7月FBA订单和非FBA订单` | 11,232 | = 9,579 + 1,653 |
| `check` | `检查运营人员-写回…` | 11,232 | 派生核对 |
| `archive_*` | `弃用2026年7月订单 [日期]` | 9,604 | **历史/提交版**（含 20260911 = 财务提交版） |
| `rules_170` | 和财务部共享 / `Jeck特殊规则-订单改销售额成本` | 873 | 1.7.0 规则 |
| `warehouse_cost_source` | 和财务部共享 / `订单发货仓库对应成本来源` | 47 | 仓库→成本来源 |
| `fx` | 和财务部共享 / `汇率` | 19 | 月固定汇率 |

> `写回*` / `检查*` / `透视表*` / `备份*` / `弃用*` **永不被当原始表**（`classify_worksheet`）。

## 口径矩阵（拒绝无标注的「平均值」）

每条指标都带 **分子 / 分母 / 口径 / 零值策略 / 来源列**。分母可选：
`rows`（含零行）、`nonzero_rows`、`orders`（按 `order_base` 合并）、`packages`、`pieces`、`column`（比值）。

7 月非 FBA·普通轨（n=9,579，来自 `writeback`）：

| 指标 | 分子 | 分母 | 值 |
|---|---|---:|---:|
| 产品成本·行均 | 1件产品成本 | rows 9,579 | **177.08** |
| 产品成本·数量加权 | 产品成本*数量 | Σ发货数量 10,196 | **170.80** |
| 产品成本·订单均 | 产品成本*数量 | orders 9,092 | **191.54** |
| 运费·行均 | 运费 | rows 9,579 | **74.10** |
| 运费·包裹均 | 运费 | packages 9,384 | **75.64** |
| 收入·行均 | 售价*汇率 | rows | **569.75** |
| 毛利率 | 订单利润 | 售价*汇率 | **0.53** |

同一批运费还有两列口径更低的来源：`通途运费` **684,590.46**（估算）、`包裹总运费` **620,416.88**（不稳）。
**"运费低"取决于看哪一列、以及按行还是按包裹。**

## 关键机制（实证）

1. **普通轨 vs `*系数`轨是两条独立的账，且 7 月系数层几乎不动**：
   `订单总成本` 2,559,594.05 vs `订单总成本*系数` 2,560,664.66 → **Δ = +1,070.62**（仅 79 行）；
   `订单利润` 2,898,063.44 vs `订单利润*系数` 2,896,992.82 → Δ = −1,070.62。
   分项：皮壳成本 −101.30（68 行）、二次加工成本 +1,137.79、绍兴二次加工/头程 **0**。
   两者差 → 标 `profit_track_confusion`，但**金额很小**（占比 ~0.04%）。
   > ⚠️ **不要**拿 `engine_170` 独立重放的结果当结论：用 873 行 `Jeck特殊规则` 直接重放
   > `检查运营人员-写回…` 会得到 −116,400 的假象，与表内 `*系数` 列**对不上**
   > （例：规则 `皮壳成本系数=0` 会把某单归零，但表内 `皮壳成本*系数`=113.95 非 0）。
   > 表的**普通列是规则前备份、`*系数` 列才是规则后**；重放必须用与产出该表相同的规则快照，
   > 否则一律标 `unreproduced`。
2. **FBA 成本口径**：FBA 汇总 `运费=0`、`订单总成本` 不含 Amazon `订单费用`（原始 FBA 表里 `订单费用` = −215,598.96），
   导致 FBA 毛利率虚高（413,511.98 / 608,941.46 ≈ **67.9%**）→ **财务口径问题**，不是技术错。
3. **成本全缺的账号**：`BBdaneeyUS`（22 行，大件云仓，`当月给分公司发货类型` 空）
   `产品成本*数量` = 0、`订单总成本` = 0、收入 41,644.62 → **毛利率 100%**。
   全表"成本 0 但收入 >0"共 **27 行 / 42,952.93 元**（BBdaneeyUS 22、WFUS 4、WOWMAXDUUS 1）→ **主数据缺口**。
4. **运费逐行重复**：同包裹同值多行（原始表 33 个包裹）逐行求和会多算 **2,213.27** 元（≈0.3%）。
5. **整列全零**：`VAT`、`PayPal fee(人民币)` 全表 0 → 标 `column_all_zero:*`，交财务判定口径。
6. **仓库口径体检**（`warehouse_cost_source_check`）：7 月有 **5 个仓库**的"二次加工成本"仍借用绍兴 `2CJG-SX`，
   合计 `二次加工成本*数量` ≈ **238,278 元**：`FZH-DANEEY-皮壳仓库`（3,903 行 / 197,480.84）、
   `FZH-DANEEY-成品仓`（334 / 23,715.60）、`FZH-DANEEY-半成品仓`（105 / 14,501.54）、
   `FZH-DANEEY-退货产品仓`（37 / 2,580.48）、`大件云仓`（22 / 0）。→ 已知历史妥协，交主数据决策。
7. **规则轨差异（已验证口径）**：只比**表内两套列**（普通列 vs `*系数`列），不用独立重放：
   `订单总成本` 2,559,594.05 → 2,560,664.66（**Δ +1,070.62**，79 行）；`订单利润` **Δ −1,070.62**；
   分项 皮壳 −101.30（68 行）、二次加工 +1,137.79（29 行）。**7 月系数层金额很小。**
8. **分渠道成本审计**（`channel_cost_decomposition`，对应 cell_222）：按 `发货仓按销售汇总分类` 拆
   皮壳/绍兴二次加工/二次加工/头程/尾程，并验两条恒等式（7 月全部成立，Δ ≤ 0.01）：

   | 渠道 | 行数 | 产品成本*数量 | 头程 | 运费 | 订单总成本 | 二次加工来源 |
   |---|---:|---:|---:|---:|---:|---|
   | USNJ分公司 | 4,202 | 1,070,842.07 | 32,355.52 | 353,805.10 | 1,457,002.70 | `2CJG-US` |
   | **USTX分公司** | 4,379 | **469,808.27** | 52,665.97 | 263,431.09 | 785,905.33 | **`2CJG-SX`** |
   | 波兰分公司 | 976 | 200,787.72 | 23,355.58 | 92,542.71 | 316,686.01 | `2CJG-PL` |
   | 美国海外仓 | 22 | 0 | 0 | 0 | 0 | `2CJG-SX` |

   → **美中 46.98 万的产品成本是用绍兴加工成本算的**（对比美东用 `2CJG-US`）。

   **cell_222 本身的三处不一致（已记 `CHANNEL_KNOWN_ISSUES`）**：
   ① `美国分公司_USTX` **只有 `*系数` 列、没有普通列**；
   ② `美国分公司_USTX*系数` 用「皮壳**不含包装**」，而 `美国分公司_USNJ` 用「含包装」；
   ③ `*系数` 渠道列里「头程」用的是**未乘系数**的列，而「皮壳/二次加工」用的是 `*系数` 列。

## 代码/口径的来龙去脉

见 [colab-cost-engine-spec.md](colab-cost-engine-spec.md)：Colab 成本引擎逐 cell 逆向 + EN 侧
（`BOM Cost List` 报表、`process_order_excel_for_costs`）源码规格 + **两法差异图**。

## 对账闸门（不过就**不给管理结论**）

| 闸门 | 判据 | 阈值 |
|---|---|---|
| `row_conservation` | `input = matched+unmatched+failed+excluded` | 0 行误差 |
| `profit_identity` | `售价*汇率 − 订单总成本 = 订单利润` | ≤ 0.01 元/分区 |
| `reported_profit_match` | 复算 = 表内 | ≤ 0.10 元/全月 |

任一不过 → `conclusions_blocked=True`，`管理摘要.md` 顶部标"已阻断"，诊断文件照出。

## 决策归属（三份清单分开）

| owner | 含义 | 例子 |
|---|---|---|
| `technical` | 代码/公式修正 | 运费逐行重复、成本孤悬一行 |
| `finance` | 财务口径待定 | FBA 平台费是否计入、VAT/PayPal 口径、`*系数`轨是否官方口径 |
| `master_data` | 主数据待补 | 订单成本全缺（BBdaneeyUS 等）、无采购价/无自套 BOM 的直接采购件 |

主数据候选判定（R18/AE2）：`Item Price(标准采购)` 有价 + **无自套 BOM** → `missing_self_bom_candidate`
（建法见 [en-direct-purchase-self-bom.md](../../../docs/solutions/architecture-patterns/en-direct-purchase-self-bom.md)，
**审计只报不建**）。

## 口径与件数规则

件数/后缀/TikTok/空 SKU 一律**复用** `order_side_input`（不重造）：
`<base>` 与 `<base>-2` 同单算 1 件；纯填充单保留为 `只发部件·待复核`；空 SKU 占位行保留血缘、不计件。

## 停止条件

- 必需源（`raw`）缺列或缺表 → snapshot 失败即退出，不产出分析。
- 任一闸门不过 → 管理摘要标"已阻断"，不写结论。
- 老板给的数字复现不了 → 标 `unreproduced`，**只给口径矩阵，不挑最接近的**。

## 关联

- 尾程来源口径：[monthly-tail-cost-pipeline.md](monthly-tail-cost-pipeline.md)
- 成本路径（皮壳/半成品/成品）：[bom_cost_explanation.md](../../../bom_cost_explanation.md)
- 订单后缀/合并判据：`docs/solutions/conventions/tongtu-order-suffix-and-merge-criteria.md`
