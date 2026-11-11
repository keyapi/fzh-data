---
okf: v0.1
type: Review
title: 已有资产审计：需求预测 / 库存规划 / 交期 / 供应净额
date: 2026-10-27
owner: claude
status: read-only audit
scope: 先搜再造 — 项目内已有什么、在哪个分支、能不能复用、还缺什么
tags: [forecast, statsforecast, inventory-planning, lead-time, supply-netting, asset-audit, reuse]
---

# 已有资产审计：需求预测 / 库存规划 / 交期 / 供应净额

> **一句话**：预测已经落地（`statsforecast 2.1.1`），库存规划已有评估器和结论，交期配置已有契约，
> 供应净额已有引擎。**不要在 frePPLe 或新库上重造这四块**；真正缺的是**合并、接线、业务参数**。
>
> 本文只读盘点，未改任何代码、未 push、未开 PR、未写生产。路径与 commit 均在本机核对过。

---

## 0. 一页结论

| 能力 | 项目里已有什么 | 状态 | 还缺什么 | 要不要重造 |
|---|---|---|---|---|
| 需求预测 | `self_fulfilled_demand/forecast.py`：AutoETS(statsforecast 2.1.1) + MA3/naive guard；2,423 SKU；45 tests；实际 run `forecast-20261027-r2` | **本地分支，未 push/未开 PR** | 合并、接进库存规划、业务确认口径 | **不要**；复用 |
| 库存规划 | `inventory_policy.py`（order-up-to 模拟器、β/α、二分反解）+ `sc08_conformal.py`（经验/共形分位）+ SC08 服务—库存前沿 | **研究/评估器，PR #300 分支** | SKU×仓 安全库存/ROP/order-up-to 生产表；业务参数（β/L/R/lost_sales）；接预测与交期 | **不要**；扩展 |
| 交期/运输方式 | `sc13/leadtime_config.py`：版本化 JSON、四模式、分段天数、source/sample_size、严格报错；测试 | **契约就绪，仅 assumed 样例** | W2 实测数据（目前 40 多运单不够）；接入库存政策 | **不要**；接 W2 |
| 供应时间线/净额 | W1 v0（#312）、supply facts v1（#318）、`supply_netting/`（35 tests、真实 run 2026-10-23） | **#312/#318 open；supply_netting 本地分支** | backlog、PO 成品映射、ETA/里程碑、as_of 对齐、跨桶口径 | **不要**；补缺 |
| EN 原生展示 | key_test `Supply Timeline` / `SO Chain Overview`；生产已部署 | **生产可用**（库存证据层） | 预测/政策结果尚未进 EN | **不要**；按需加 |
| 旧尝试 | PR #290 `demand_forecast`：ens5（MA3/6/12+Croston+TSB 中位数）+ ROP v3（lead+safety days） | **open，旧线** | 已被新线取代 | **不要**继续加功能 |

**结论**：frePPLe 的价值只剩“lead-time offset / 分配 / pegging / CTP 试算”这类**求解逻辑**；
预测、库存政策、交期配置、供应时间线**都已经有项目内资产**，直接复用。

---

## 1. 需求预测：已经装过、跑过、有生产级脚本

### 1.1 当前实现（最新）

- 代码：`self_fulfilled_demand/forecast.py`（约 1,800 行）+ `tests/test_forecast.py`。
- 分支：`keyapi/forecast-refresh-oct27` @ `6a7d56bd`（`d6f63fd3` 的功能 + 审核返修）。
- **未 push、未开 PR**：`git for-each-ref` 无 upstream，`git ls-remote origin` 没有该分支。
- 依赖：`pyproject.toml` 已声明 `statsforecast==2.1.1`，`uv.lock` 已锁；主分支 `main` 还没有。
- 环境实测：`C:/Users/zhang/orca/workspaces/Cursor/forecast-refresh-oct27/.venv` 里
  `import statsforecast` 得到 **2.1.1**。
- 实际产物：`D:/Work/fzh-order-store/en-demand-v1/forecast/CURRENT` = `forecast-20261027-r2`。

**方法规则（已冻结，不要擅自换）**：

| 条件 | 方法 |
|---|---|
| `len < 3` 完整月 | naive 末值 |
| `3 <= len < 7` | MA3 |
| `len >= 7` | AutoETS（statsforecast 2.1.1）；`len>=24` 时 `season_length=12` |
| AutoETS 失败 | MA3 回退，逐 SKU 写原因 |
| 不足月（`2022-12`、`2026-10`） | 不参与拟合/同比/趋势，只单列观测 |

**当前 run 的数字**（`forecast-20261027-r2`）：

- 可预测 **2,413 / 2,423（99.6%）**；AutoETS **2,309**、MA3 **71**、末值 **33**；
  10 个只有不足月观测 → `p50=null`（不是 0）。
- 区间：需求残差 `actual−pred` 的 10/90 分位；持续低估上界扩张、持续高估下界扩张；
  **不是已标定分位，不承诺 80% 覆盖率**。
- 跨 UOM 禁止合计：`个` / `套` / `unknown` 分组；`unknown` 是原始行计数。
- 测试：`uv run pytest self_fulfilled_demand/tests -q` → **45 passed**；
  `--validate-only` → **9/9 checks**。

### 1.2 之前的调研/对照（都已经做过）

| 时间 | 工作 | 结论 |
|---|---|---|
| 2026-10-22 | **T2**：statsforecast 2.1.1 对照 9 个方法（naive/seasonal_naive/MA3/MA6/MA12/TSB/Croston/AutoETS/等权 combo） | 验证集 AutoETS 最优（WAPE 0.5565），但测试集 0.6934 与 MA3 0.6915 基本持平；combo 测试 0.5921（比 MA3 好 14.4%）；当时建议**维持 MA3** |
| 2026-10-22 | **T5**：Codex2 裁定 A，全范围改用 **AutoETS 默认 + MA3 fallback** | 1,328 SKU / 2,309 行；AutoETS 2,106 行、MA3 112 行；112 行失败原因逐行可见 |
| 2026-10-23 | **A 包**：分型路由 + 全局树（MLForecast+LightGBM）同切点对照 | 2,763 单元/774 SKU/5 起点：global_tree WAPE **0.494**、combo **0.519**、routed **0.551**、naive **0.606**；463 SKU 因历史 <18 月未评分；**无协变量，未采用** |
| 2026-10-23 | **E1**：预测回测/补货 LP/只读 Agent 最小验证 | 结论并入 `05-synthesis`；不得外推到美中新运营 |
| 2026-10-27 | **D19**：模型证据复核 | **不存在干净留出块**；现有证据不支持“选择流程/AutoETS 更好”；AutoETS 只是规则默认，不是效果改进；改默认需前向影子连续 3 个月同向且区间不含 0 |

### 1.3 不要重造

- **不要再装/对比 statsforecast**：已经装过、跑过、锁版本。
- **不要再造 ensemble/路由**：A 包的 tree/combo/routed 是挑战者，未接回主表；D19 明确不按回测切换。
- **不要在没有协变量/干净留出的情况下上 LightGBM**：A 包已说明 774 个可训练 SKU、只有月度滞后。
- **不要改预测口径不写原因**：现有实现已经做到“每个 SKU 有 method/reason/history/backtest”。

### 1.4 预测仍缺

1. **未合并/未推送**：只在本地分支；主分支没有 `self_fulfilled_demand/`，也没有 `statsforecast` 依赖。
2. **未接供应净额**：`supply_netting` 明确“不做预测”，只吃 `demand_netting.parquet`；
   预测产物目前没有进入净额/补货链。
3. **未接 EN**：预测只在本地 Parquet，不在 key_test 报表。
4. **口径限制**：区间未标定；断货删失未校正；WAPE 中位 0.89；仓库分配是最近 3 月占比假设。

---

## 2. 库存规划：研究很深，但还没有生产表

### 2.1 已有代码

| 文件 | 作用 | 关键点 |
|---|---|---|
| `experiments/business_phase/inventory_policy.py`（236 行） | 最小服务/库存政策评估器 | `simulate_flow` / `simulate_policy` / `metrics` / `bisect_order_up_to`；`lost_sales` 与 `backorder` 显式二选一；逐期恒等式断言 |
| `experiments/business_phase/sc08_conformal.py`（237 行） | 经验/共形分位 vs 正态+CV | 训练侧“实际/预测”比值分位定乘数；外层只评不调；CV/EMP/EMP3x 三种 sizing 并列 |
| `sc08_frontier.csv/json` | 18 格探索前沿（L=60/90/120、R=7/30、β=90/95/99%） | 合成需求，900 天；明确**非批准值** |
| `reviews/2026-10-23-service-inventory-annex.md` | 业务可读版结论 | 服务—库存前沿、三条路径与代价 |
| `control/INVENTORY_EVALUATION.md` | 理论与验收协议 | β 主报、α 辅报；WAPE ≠ 准确率；P90 ≠ 覆盖率保证；L+R；newsvendor |

### 2.2 已有结论（重要，不要重新推一遍）

- **现行规则（正态 + CV）样本外 β 只有 0.63–0.84**；不是 0.95。
- **经验/共形分位 τ=90–95%** 可把 β 抬到 **0.83–0.91**，代价是库存 **2.4–4.6×**。
- **硬 95% 在可接受库存内做不到**：6 个真实格子里只有 1 格达到 95%；
  要稳过 95% 得抬到 τ=99%，乘数 **4.3–57×**、库存 **8.8–40×**。
- 误差尾很重：实际/预测比值 q95 **2.0–4.7**、q99 **13–47**；这是数据性质，不是模型再调参能消掉的。
- 统一政策口径（D40）：**β（Fill rate）主报、α（CSL）辅报**；周期复核按 **L+R**；
  order-up-to 只是**参照政策**，不是最优；`lost_sales`/`backorder` 不混用；零分母不填 100%。

### 2.3 不要重造

- **不要重做服务—库存前沿**：SC08 已经做了 18 格 + 6 格真实对照。
- **不要引入新的库存优化平台**：单级政策用现有 `inventory_policy.py` 就够；
  多级/多仓再考虑 `stockpyl`（MIT），但先证明单级不够。
- **不要把“硬 95%”当默认目标**：现有证据已说明代价；目标 β 必须业务拍板。

### 2.4 库存规划仍缺

1. **没有生产表**：目前没有 `SKU×仓` 的 `safety_stock / reorder_point / order_up_to / projected_inventory`
   产出；`inventory_policy.py` 只在实验目录。
2. **没接预测**：政策评估器用的是历史/实验数据，没有吃 `forecast-20261027-r2` 的 P50/P90。
3. **没接交期**：L 仍是实验参数（月/天），没有接 `leadtime_config.py` 的 route×mode 分段。
4. **没接供应净额**：`supply_netting` 只算缺口，不算安全库存/补货点。
5. **业务参数未定**：目标 β、L/R、lost_sales vs backorder、MOQ/箱规/成本预算。

---

## 3. 交期/运输方式：契约已就绪，缺实测

### 3.1 已有

- `experiments/sc13/leadtime_config.py`（355 行）：
  - 版本化 JSON：`version / effective_from / profiles[]`；
  - 每条 `(route_id, warehouse, mode)`：`segments{order_to_departure, departure_to_arrival, arrival_to_stock}`、
    `source(measured|assumed|business)`、`sample_size`、`owner`、`notes`；
  - `mode`：`slow_boat / fast_boat / air / 3pl`；
  - **缺文件/缺字段/版本不对/未知路线/歧义全部报错**，没有默认值兜底；
  - `expected_available_date(route, mode, order_date)` 返回日期 + 来源 + `is_assumed` + `explain()`；
  - 测试：`test_leadtime_config.py` + `run_contract_checks.py`。
- 样例：`examples/leadtime_config.sample.json`（全部 `source=assumed`、`sample_size=0`）。
  慢船 14+30+7=51 天、快船 33 天、空运 12 天、3PL 10 天；波兰慢船 52 天、空运 14 天。

### 3.2 不要重造

- **不要再写一套交期配置**：schema、版本、错误处理、测试都在。
- **不要把 assumed 当实测**：`source` 与 `sample_size` 已经在结构上强制暴露。
- **不要改调用方**：W2 实测到了以后，换 JSON 文件即可。

### 3.3 仍缺

- **实测数据**：目前 40 多个运单，不够做分段统计；W2 尚未交付。
- **接入**：`leadtime_config` 目前只在实验/附件里用，没有进入库存政策或净额引擎。

---

## 4. 供应时间线 / 净额：引擎已有，数据缺口仍在

### 4.1 已有

| 资产 | 在哪 | 状态 |
|---|---|---|
| W1 v0 供应时间线（7 阶段、B_min/B_max、233 行） | `feature/jack-supply-timeline`，PR **#312** | open |
| supply facts v1（阶段余额/里程碑/可售 tranche/links + 批量导出） | PR **#318** `feature/supply-facts-delivery-mvp` @ `86267eda` | open；接管 #314 |
| `supply_netting/`：需求净额 × 供应事实 → 逐桶净额 | `keyapi/supply-integrate-oct27` @ `66144037` | **本地分支，未 push/未开 PR** |
| 净额上游组件（`SupplyRow`、`receipt_buckets`、`overlap_gates`） | `supply_chain_visibility`，PR #318 已带入 | open |
| EN 原生报表（Supply Timeline / SO Chain Overview） | key_test #2 已合并并生产部署 `c34fa53` | **生产可用** |

### 4.2 已有验证

- `supply_netting/tests` → **35 passed**（8 条净额场景 + 契约 + 真实案例）；
  `supply_chain_visibility/tests` → 23 passed。
- 真实 run `run-2026-10-23`：保护期需求 649、期初 22,163、到货 **0**、8 个 key 缺口合计 **10 件**、
  视界末累计未满足 **41 件**、条件供应 11,797 件；2,172 行全部 `conditional`。
- 复审（`2026-10-27-claude-review-forecast-supply.md`）：forecast / supply 均
  **accept-with-findings**。

### 4.3 仍缺（复审已列）

1. **backlog 未接入**：未来需求只有 998 件前瞻行；“保护期无缺口”不能解读为不需要补货。
2. **PO 成品映射缺失**：5,123 行 / 4,425,892 件全部 `identity_unproven`，对净额贡献 0。
3. **里程碑 0 行**：只有结构，无原计划/当前预计/实际日期。
4. **阶段余额只有在途**：未排产/在产/完工待发/到仓待上架没有本地源。
5. **同批去重未在真实数据触发**：映射补齐后必须重验。
6. **F1 as_of 与快照差 10.8 小时**；**F2 `demand/gap` 含跨桶结转**，直接求和会重计。
7. **供应来源覆盖 unverified**：manifest 恒 `partial=true`。

---

## 5. 资产状态矩阵

| 资产 | 路径/分支 | PR | 是否进 main | 测试/产物 |
|---|---|---|---|---|
| 需求预测 | `self_fulfilled_demand/` @ `keyapi/forecast-refresh-oct27` `6a7d56bd` | **无** | 否 | 45 passed；`forecast-20261027-r2` |
| 需求采集/规范化 | 同上 | 无 | 否 | 45 passed |
| 供应净额 | `supply_netting/` @ `keyapi/supply-integrate-oct27` `66144037` | **无** | 否 | 35 passed；run-2026-10-23 |
| 库存政策评估器 | `experiments/business_phase/inventory_policy.py` @ `docs/supply-chain-integration-handoff` | #300 | 否 | 合成 18 格 + 真实 6 格 |
| 共形分位 | `experiments/business_phase/sc08_conformal.py` | #300 | 否 | 790/239 两宇宙 |
| 交期配置 | `experiments/sc13/leadtime_config.py` | #300 | 否 | 契约测试 |
| W1 时间线 | `feature/jack-supply-timeline` | #312 | 否 | 21/21 + 233 行 |
| supply facts | `feature/supply-facts-delivery-mvp` | #318 | 否 | 10 + 77 tests |
| EN 原生报表 | key_test `c34fa53` | key_test #2 | **是（生产）** | 41 tests；生产冒烟 |
| 旧预测线 | `claude/affectionate-bell-93d3ec` `scripts/forecast_ensemble.py` | #290 | 否 | ens5 + ROP v3，旧 |

> **文档漂移提醒**：`RESEARCH_ADOPTION.md` 仍写“statsforecast 未安装 / AutoETS skip”，
> `01-asset-inventory.md`（2026-10-20）仍写“C5 预测无资产”。这两处已被 10-21～10-27 的工作推翻，
> 应由各自文档 owner 更新；不要据此判断“没有”。

---

## 6. 与 frePPLe / 其他开源库的关系

| 选项 | 结论 |
|---|---|
| frePPLe 做预测 | **不需要**；已有 statsforecast 2.1.1，且 frePPLe 预测代码与它的时间序列模型耦合 |
| frePPLe 做库存规划 | **不需要**；社区版没有 inventory planning 模块，研究/评估器我们已有 |
| frePPLe 做交期配置 | **不需要**；`leadtime_config.py` 已覆盖且更严格（版本/source/报错） |
| frePPLe 做供应时间线 | **不需要**；W1/supply_facts/supply_netting 已有证据层，frePPLe 不解决证据问题 |
| frePPLe 做分配/lead-time offset/CTP | **可选借逻辑**；只有要做“约束分配/承诺交期”且现有净额不够时 |
| `statsforecast` | **已采用**；2.1.1 是 PyPI 最新，Apache-2.0，Python >=3.10 |
| `stockpyl` | **可选**；单级政策用现有模拟器即可，多级再引入 |
| Odoo / ERPNext | **只作参考**；不复制代码 |

**一句话**：frePPLe 只值得作为“求解逻辑参考”，不值得作为“预测/库存/交期/时间线”的替代品。

---

## 7. 更新后的计划（reuse-first）

### P0：合并与接线（先做，不新造）

1. **把两条本地分支合成一条可评审分支**：`keyapi/forecast-refresh-oct27` + `keyapi/supply-integrate-oct27`
   共享 base `da4fa1e6`；先 rebase/merge，跑 45 + 35 测试。
2. **预测 → 库存政策 → 净额**：用 `forecast_sku_windows` 的 P50/P90 替换/补充
   `demand_netting` 的前瞻需求；明确“实际未履约 SO”与“预测”不重复。
3. **交期接入**：用 `leadtime_config.expected_available_date()` 生成 L；assumed 必须显式标记。
4. **产出第一张库存政策表**：`SKU×仓×UOM` 的 `safety_stock / reorder_point / projected_inventory / gap`；
   参数先给 90/95% 情景，不擅自定唯一目标。
5. **按分型设政策**：正常/慢销/长尾/清仓/停售分开；近 6 月无销量的 192 个有库存 SKU 先走清仓复核。
   分型与名单见 [2026-10-27-sku-segmentation-stockout-promotion](2026-10-27-sku-segmentation-stockout-promotion.md)。

**工作量粗估**：合并/接线 **2–3 人日**；政策表 **5–8 人日**；交期接入 **2–3 人日**。

### P1：补净额数据缺口（按阻塞排序）

1. backlog（未履约 SO 余额）；
2. PO 成品映射（当前 4.43M 件贡献 0）；
3. ETA/里程碑（当前到货 0、milestones 0）；
4. 阶段余额补齐（未排产/在产/完工待发/到仓待上架）；
5. F1 `as_of` 对齐、F2 跨桶 `demand/gap` 口径。

**工作量粗估**：**5–10 人日**，其中 PO 映射/ETA 取决于 EN/通途数据，可能被外部阻塞。

### P2：只有在业务明确需要时才做

- **分配/lead-time offset/CTP**：借 frePPLe `solverdemand` / `STATUS_QUOTE` 逻辑，**不部署**；
  **5–10 人日**。
- **多级/多仓库存优化**：先证明单级政策不够，再考虑 `stockpyl`；
  **5–10 人日**。

### 不建议

- 部署 frePPLe（B）——除非 P2 的分配结果有争议，需要对照。
- EN 集成 frePPLe（C）——没有业务必要，且连接器 2022 年后未维护。

---

## 8. 复现命令与证据

```bash
# 预测（需在 forecast 工作区，venv 内有 statsforecast 2.1.1）
uv run pytest self_fulfilled_demand/tests -q                       # 45 passed
uv run python -m self_fulfilled_demand.forecast --validate-only <run_dir>  # 9/9

# 供应净额
uv run pytest supply_netting/tests -q                             # 35 passed
uv run pytest supply_chain_visibility/tests -q                    # 23 passed

# 库存政策 / 共形分位（实验）
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/inventory_policy.py
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/sc08_conformal.py

# 交期契约
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/sc13/test_leadtime_config.py
```

关键路径：

- 预测产物：`D:/Work/fzh-order-store/en-demand-v1/forecast/forecast-20261027-r2/`
- 净额产物：`D:/Work/fzh-order-store/en-demand-v1/supply-netting/run-2026-10-23/`
- 预测接口：`self_fulfilled_demand/docs/reference/forecast-interface.md`
- 净额接口：`supply_netting/docs/reference/output-schema.md`
- 交期契约：`experiments/sc13/leadtime_config.py`（文件头 schema）
- 库存结论：`reviews/2026-10-23-service-inventory-annex.md`、`control/INVENTORY_EVALUATION.md`

---

## 9. 事实 / 推断 / 未核实

**事实（本机核对）**

- `statsforecast==2.1.1` 在 `keyapi/forecast-refresh-oct27` 的 `pyproject.toml` / `uv.lock`；
  forecast 工作区 venv 可导入 2.1.1；PyPI 最新也是 2.1.1（Apache-2.0，Python >=3.10）。
- 预测 run `forecast-20261027-r2` 存在；45 tests；9/9 checks。
- 供应净额 branch `66144037`；35 tests；run-2026-10-23 存在。
- 两条分支都**没有** origin upstream；PR 列表里没有它们。
- 库存政策/共形分位/交期配置在 `docs/supply-chain-integration-handoff`（PR #300）。
- W1 #312、supply facts #318 均 open；key_test 报表已生产。

**推断**

- 预测与净额未接线：`supply_netting` 明确“不做预测”，且代码里没有 forecast 输入。
- 库存政策表尚未生产化：当前只有模拟器/评估器，没有 SKU×仓政策产物。
- frePPLe 对这些已有资产没有增量价值，除非要做分配/CTP。

**未核实 / 文档漂移**

- `RESEARCH_ADOPTION.md` 的“statsforecast 未安装”已过时；`01-asset-inventory.md` 的“C5 无资产”已过时。
- 旧 PR #290 的 ens5/ROP v3 是否还有业务在用，未核实；建议不继续加功能。
- 预测区间覆盖率未标定；断货删失未校正；这些是已知限制，不是本次审计能解决的。

---

## 10. 外部来源（网上核对）

- statsforecast PyPI（最新 2.1.1、Apache-2.0、Python >=3.10）：
  <https://pypi.org/pypi/statsforecast/json>
- statsforecast GitHub（Apache-2.0，活跃）：
  <https://github.com/Nixtla/statsforecast>
- MLForecast（Apache-2.0，A 包挑战者用过）：
  <https://github.com/Nixtla/mlforecast>
- LightGBM（MIT，A 包挑战者用过；主仓已有依赖）：
  <https://github.com/microsoft/LightGBM>
- stockpyl（MIT，多级库存优化备选）：
  <https://github.com/LarrySnyder/stockpyl>
- frePPLe 评估与许可证：见同目录
  [`2026-10-27-frepple-evaluation.md`](2026-10-27-frepple-evaluation.md)
