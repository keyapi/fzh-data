# T26 交付机器核对（五项）

> 只读当前 CSV/JSON/MD；不跑数据库。数字均由脚本重算，FAIL 只列差异。

- 五项：PASS **5** / FAIL **0**

| # | 检查 | 结果 | 差异 |
|---:|---|---|---:|
| 1 | 指南口径：522 行 / 479 商品 / 约 67% 销量 | **PASS** | 0 |
| 2 | 两类条件建议分布与时窗 | **PASS** | 0 |
| 3 | 160 行库存未知：null、未被当 0、传播一致 | **PASS** | 0 |
| 4 | 库存口径：同仓快照 vs 旧“跨仓汇总”文字 | **PASS** | 0 |
| 5 | 全 1,328 SKU 去向 | **PASS** | 0 |

## 1. 指南口径：522 行 / 479 商品 / 约 67% 销量 — **PASS**

```json
{
 "rows": 522,
 "skus": 479,
 "denominator_6m": 48544.0,
 "covered_6m": 32624.0,
 "share_pct": 67.21,
 "one_only_share_pct": 37.43
}
```
- 分母 = 去重 SKU 近 6 月销量合计 48544；覆盖按同一 SKU 集合去重后计算（SKU 可跨分类，不能把百分比直接相加）。

## 2. 两类条件建议分布与时窗 — **PASS**

```json
{
 "by_class": {
  "①0/正量分歧": {
   "n": 308,
   "min": 0.0,
   "median": 0.485,
   "max": 140.47
  },
  "③a全正量一致": {
   "n": 214,
   "min": 0.4,
   "median": 9.385,
   "max": 230.82
  }
 },
 "by_caliber": {
  "MA3": {
   "n": 522,
   "min": 0.0,
   "median": 1.96,
   "max": 694.72
  },
  "naive": {
   "n": 522,
   "min": 0.0,
   "median": 1.22,
   "max": 532.78
  },
  "seasonal_naive": {
   "n": 522,
   "min": 0.0,
   "median": 5.79,
   "max": 318.05
  },
  "combo_ew": {
   "n": 522,
   "min": 0.0,
   "median": 3.385,
   "max": 298.01
  },
  "AutoETS": {
   "n": 522,
   "min": 0.0,
   "median": 1.96,
   "max": 230.82
  }
 },
 "window": "L90"
}
```
- 分布列用 `建议中位下限`（五口径下限中位数）；五口径各自分布见 by_caliber。时窗为 L90（下限=dem[90]−供给，上限=dem[90]×压力系数−可用）。

## 3. 160 行库存未知：null、未被当 0、传播一致 — **PASS**

```json
{
 "main": {
  "rows": 160,
  "null_counts": {
   "可用": 160,
   "缺口L60": 160,
   "缺口L90": 160,
   "缺口L120": 160,
   "建议下限L90": 160,
   "建议上限L90(压力情景)": 160
  },
  "demand_p50_nonnull": 160
 },
 "sensitivity": {
  "rows": 160,
  "all_lower_null": 160
 },
 "wo_dn": {
  "rows": 160,
  "status": {
   "covered_unvalidated": 6,
   "no_material_found": 154
  },
  "supply_blank": 160
 }
}
```
- 三处一致性：主表 160 行数量列全空且需求非空；敏感性表 160 行五口径下限全空；WO/DN 覆盖表同 160 行（154 无材料 + 6 有材料不可用），供给可用量全空。没有任何一处把未知写成 0。

## 4. 库存口径：同仓快照 vs 旧“跨仓汇总”文字 — **PASS**

```json
{
 "rows": 2309,
 "same_warehouse_fact": {
  "yes": 2058,
  "unknown(no_stock_row)": 160,
  "": 91
 },
 "inventory_allocation": {
  "no（逐仓库存行）": 2218,
  "n/a": 91
 },
 "demand_allocation": {
  "yes": 1415,
  "no": 894
 },
 "mismatches": 0,
 "v1_summary_old_claim_line": 40
}
```
- `summary.md`（v1，已被 `summary_v3.md` 取代）第 40 行仍写“库存为 SKU 跨仓汇总”；该文件不在本轮 ownership，未改。现行摘要与指南已加准确表述（按仓快照；需求按仓销量占比分配）。
- usability_audit：2,058 行主表可用=同仓库存事实、0 行不符、0 行库存摊派；需求摊派 1,415 行（按仓销量占比），其余 894 行占比为 0。

## 5. 全 1,328 SKU 去向 — **PASS**

```json
{
 "rows": 2309,
 "skus": 1328,
 "status_combos": {
  "B": 1077,
  "B+B_pending_inventory": 154,
  "B_pending_inventory": 6,
  "C": 91
 },
 "missing_skus": [],
 "invalid_status": {},
 "roster_skus": 1328
}
```
- 状态组合：全部 B（1,077 SKU）/ B+待核实（154）/ 全部待核实（6）/ 全部 C（91）。154 个 SKU 同时有 B 与待核实行，属同一 SKU 分仓库存缺失，可解释。

## 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/verify_delivery.py
uv run python scripts/check_secrets.py
```

