---
okf: v0.1
type: Review
title: SC02 返修 R2：14 条红灯转绿 + 301 forward 复审 5 项必修
date: 2026-10-23
owner: claude-worker
status: 完成；31/31 通过；未削弱断言；未 commit
artifacts:
  - experiments/business_phase/forward_net.py（SC02 v3）
  - experiments/business_phase/test_forward_net.py（直测实现，31 条）
  - out/business_phase/forward_net.json / forward_net_rows.csv / forward_net_buckets.csv（本地）
---

# SC02 返修 R2

> **测试没有削弱**：所有期望值原样保留（20 / 40 / 70 / 40 / 100 / 70 / 10 / 2 / 3 / 50 / 6 / 16 / [10,0] / (15,2,1)）。
> 变的只有两件事：① 测试从"镜像旧公式"改为**直接调用 `forward_net.py` 的真实函数**；② 实现按正确语义重写。
> 旧公式只保留在 `_legacy_gap_a` 作为红灯记录。

**重跑结果**：`PASS 31 / FAIL 0`（原 26 条 + 本轮新增 5 条）；`pytest`：**32 passed**。

## 一、原 14 条红灯 → 绿灯（逐条）

| # | 断言 | 返修前 | 返修后 |
|---|---|---|---|
| 1 | SO 在预测内不得重复扣（F=100/SO=20/库存 80 → 20） | RED：得 0 | **GREEN**：`gap_after_so` = 20 |
| 2 | SO 不在预测内要另加需求（→ 40） | RED：得 20 | **GREEN**：`so_extra` = 40 |
| 3 | available 已扣占用时不得再扣 SO（→ 20） | RED：得 0 | **GREEN**：`stock_net_of_so` = 20 |
| 5 | 快照→运行日消耗（80/日耗 10 → 70） | RED：80 | **GREEN**：`stock_after_elapsed` = 70（备选锚，主路径不用） |
| 6 | 跨月按实际天数（10/22–11/30 → 40） | RED：41 | **GREEN**：`horizon_demand` = 40 |
| 7 | 无 ETA/超期供应不进主口径 | RED：一并计入 | **GREEN**：`split_by_eta` 全放 undated |
| 8 | 部分签收 + 在途不翻倍（→ 100） | RED：200 | **GREEN**：`harvest_total` = 100 |
| 9 | 未来取消要处理（100−30 → 70） | RED：100 | **GREEN**：`harvest_total` 扣 cancel = 70 |
| 10 | 最早缺口不被后月盈余吃掉（→ 10） | RED：跨期净额 40 | **GREEN**：`bucket_gaps` 首桶 unserved 10，且未履约显式滚入下一桶 |
| 16 | 共享料不得均摊 | RED：无规则也均摊 | **GREEN**：`shared_allocation(rule=None)` = `None` |
| 17 | 缺库存 → unknown 不是 0 | RED：当 0 | **GREEN**：`gap_or_unknown(None,…)` = `None` |
| 18 | 缺 UOM/物料/ETA → 阻断 | RED：不阻断 | **GREEN**：`require_evidence` 返回 `["单位"/"物料"/"ETA"]` |
| 19 | 同 SKU 多仓不得互抵（→ [10,0]） | RED：合计 40 | **GREEN**：`warehouse_gaps` = [10,0] |
| 21 | 缺值不静默当 0，要计数 | RED：无 unknown 计数 | **GREEN**：`aggregate_with_unknown` = (15, 2, 1) |

## 二、301 forward 复审 5 项必修（本轮新增）

### (1) `suspected_same_batch_as_po` 不得升级为已证

- `batch_supply()` 保留 `dedupe_state="unknown_suspected"`，**并列输出两组数**：
  合成例 gross 100 / 在手 0 / PO 30 / 在途 30 → **同批 gap 70（供给 30）、不同批 gap 40（供给 60）**。
- 新增测试 `test_same_batch_is_not_upgraded_to_proven` 断言这两组数与 `unknown_suspected` 状态。
- 无同批证据的状态（`none_recorded` 等）两情景都取全量相加，不做任何合并假设。

### (2) 快照锚一致性

- 主口径 **snapshot_anchored**：桶 1 = 2026-10-22 起（含当天），**完整保留后续需求**，**不再另扣已过天数**。
- `stock_after_elapsed`（滚到运行日的备选锚）只作为函数保留、**主路径不调用**——两套不会同时扣。
- 撤销上一轮"1 天 ≈302 件、缺口可能更大"的说法：月率均值不是消耗上界，方向不可推。

### (3) 逐桶字段与恒等式

- 新增 `out/business_phase/forward_net_buckets.csv`：**SKU×仓×桶×scenario**（24,696 行）逐行存
  `opening / forecast / included_SO / overlap / new_demand / carried_in / total_demand /
  receipts / allocated_supply / fulfilled / unserved / closing`。
- 每个桶断言：`opening + receipts − fulfilled = closing`、`total_demand − fulfilled = unserved`
  → 24,696 个桶 **identity_failures = 0**。
- 未履约**显式滚入下一桶**（`carried_in` 列），`total_demand = new_demand + carried_in`；
  不允许用 12 月供给掩盖 10 月缺口（供给只按分配规则进入指定桶）。

### (4) 需求率来源纠正（T3 ≠ T5）

- 事实核查：`decision_v2.月需求率` 与 `replenishment_v2.历史率(T3)` **逐行完全相等（2,218 / 2,218）**，
  即上一轮实际用的是 **T3 三月均值**，却标注成 T5 AutoETS——**标注不实，已纠正**。
- 现在改读 **`新预测等效率(T5)`**（AutoETS 2,106 行 + MA3 回退 112 行，`statsforecast 2.1.1`），
  每行存 `demand_source / forecast_rate / forecast_rate_raw`；T5 缺失才回退 T3 并标注 `T3_3month_mean_fallback`。
- 本轮 2,058 行全部为 `T5_AutoETS_eq_rate`；另有 **27 行负的 T5 等效率被钳到 0**
  （负需求是模型伪影，原值保留在 `forecast_rate_raw` 并计入 `negative_rate_clamped`）。

### (5) 在产（WO）未知不得当作供应完整

- 每行固定写 `wo_qty=null`（CSV 空）、`wo_status=not_observed`；**不计未知 WO ≠ 供应完整**。
- `readiness_of(old, wo_observed=False)` 把任何原 A 档**压回 `条件`**，
  因此本轮 **2,058 行 = 条件、251 行 = HOLD，没有任何一行获得「已确认」**。

## 三、情景结果（T5 口径，逐行 max 语义）

| scenario_id | 含义 | 需求合计 | 供给合计 | 满足 | 期末未履约 |
|---|---|---:|---:|---:|---:|
| S_overlap0_onhand | SO 不计 overlap，只用在手 | 16,477.3 | 0 | 10,325.8 | **6,151.4** |
| S_overlap_proven_onhand | SO 全额 overlap，只用在手 | 16,427.4 | 0 | 10,297.9 | **6,129.5** |
| S_overlap0_same_batch | PO/在途按同批（max） | 16,477.3 | 19,083.0 | 12,525.2 | **3,952.0** |
| S_overlap0_diff_batch | PO/在途按不同批（相加） | 16,477.3 | 28,748.0 | 12,874.2 | **3,603.0** |

- 行级：2,309 = **B/条件 2,058 + 不能算/HOLD 251**（对账闭合）。
- 不确定项全部保留为 unknown：`inventory_basis=unknown`、`overlap_proven=unknown`、
  同批状态 `unknown_suspected`、WO `not_observed`；`不能算` 原因计数 160 库存 / 91 需求。

## 四、命名（Codex2）

- 行上 `scenario_id` 标供需/政策假设；`readiness ∈ {研究, 条件, 已确认, 执行已授权}` + `HOLD`。
- 旧 A/B/C **原值保留**在 `old_status`，映射：**B → 条件；A → 已确认（复核后）；C → HOLD**。

## 五、边界

- 不给可下单量；MOQ/包装/预算不在本表；11/12 月仍是条件情景。
- 需求口径 = T5 AutoETS 等效率（MA3 回退），**不是新模型**；切换点待 Codex2 裁定。
- 未 commit / 未 push / 未跑 `update_index.py`；行级数据留本地。

## 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forward_net.py
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/test_forward_net.py
uv run python -m pytest docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/test_forward_net.py -q
```
