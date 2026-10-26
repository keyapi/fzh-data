# W1 供应时间线 · 9 SKU 正式 recon（冻结基准）

> 样本：`JACK_ENTRY.md` / `JACK_QA.md`（2026-10-26）与 sample10 的 9 个冻结 SKU + 1 个缺额。
> 基准：库存 2026-10-22、WO 2026-10-20、PO 2026-10-19（`config/frozen_20261022.json`）。
> 契约：`docs/jack-w1-channel` @ `197901f7`（sha256 `45c2bb93…`），SC14 7 阶段 / 21 用例；`tests/test_sc14_sync.py` 校验副本未漂移。
> 只读：EN 生产 REST；未写、未下单、未改主数据。

## 1. 合同校验

| 项 | 结果 |
|---|---:|
| SC14 tests | **21/21 passed** |
| SC14 errors | **0** |
| SC14 warnings | 132（`W_UOM_UNPROVEN` 66 + `W_UOM_FLAG` 66） |
| supply 行 | 233 |
| demand（SO，单独文件） | 34 |
| excluded（非供给） | 0 |
| exceptions（production_conflict） | **1**（WO-26-03110） |

W3 预览：opening 832（通途 UOM 未证）；expected 1,506 个；unknown 23 行（qty_known 1,935 + 488 个；qty_null 60）。

## 2. 阶段（冻结基准）

| 阶段 | 行数 | counted 行 | counted 数量 |
|---|---:|---:|---:|
| on_hand | 54 | 22 | **832**（通途无 UOM；与 sample10 总可用一致） |
| po_open | 8 | 0 | 1,021（含 waiting 5、作废 PO 102；B_min 全排除） |
| in_production | 7 | 7 | **433 个**（全部 cover，estimated） |
| shipped_in_transit | 136 | 4 | 914（通途在途）+ 1,561 个（DN trace，不计） |
| received | 28 | 0 | qty=null（签收到达，数量未证） |
| unknown | 4 | 0 | C/Velvet DN-26-00112（状态缺失；qty known，日期 unknown） |

**B_min = 1,212（UOM 未证）**；**B_max = 2,762（UOM 未证）+ 433 个**。
- B_min 只含 `finished/component`，且排除 `same_batch_suspected` PO、`b_max_only`、未映射仓。
- B_max 含 `cover`（`conversion_assumed=true`）与全部开放 PO（含作废 PO021735 的 102）。
- 6 个 `cover` / 2 个 `finished` / 1 个 `component`（Q06）。

## 3. Q01–Q08 落地情况

| Q | 落地 |
|---|---|
| Q01 阶段 | 7 阶段已启用；`unknown` 行（DN-26-00112）进入 supply，只进 `supply_unknown`；`partially_received` 本样本 0 行 |
| Q02 库存 | 正式 recon 用 10-22 冻结值；`--snapshot live` 只输出 `provisional_live`，不计算 B_min/B_max |
| Q03 WO | 只纳入 creation ≤ 10-20；`WO-26-03110` 标 `production_conflict`、进 exceptions、不计供给；C/Linen 101、CENCord 152 与 sample10 一致；额外 `WO-26-03118` 70、`WO-26-03664` 110 按 Q03 规则计入并标 `sample10_wo_not_listed` |
| Q04 PO | `PO021735` 为 status=4（作废）：进 B_max、不进 B_min；其余 6 条开放 PO 全部保留 |
| Q05 overlap | TT0031038 201=201、C/Linen 121=121、TT0312701 480=480、C/Cord-White 112=112 均 `same_batch_suspected`；B_min 排除 PO，B_max 保留 |
| Q06 角色 | 6 cover / 2 finished / 1 component；`identity_confidence=proven`（`sku_item`）；PK# 不 1:1 转成品 |
| Q07 仓库 | 不同 `warehouse_id` 可相加；cover 行标 `conversion_assumed=true`，B_min 只放已证转换（本样本 0），B_max 放假设 |
| Q08 received | 28 行 `received_evidenced`（qty=null，只进 supply_unknown）；`received_booked=0`；9 SKU 覆盖 8/39 DN、1,516/4,279 行 |

## 4. SC04 对账

| 口径 | SC04 基线 | 本次 | 差 |
|---|---:|---:|---:|
| 有号 DN | 39 | 39 | **0** |
| 运单号 | 47 | 47 | **0** |
| 物料行 | 4,279 | 4,279 | **0** |
| received_before / unknown_date / in_transit / partially / unknown | 6/1/30/1/1 | 6/1/30/1/1 | 0 |
| FBA DN | 17 | 17 | 0 |

9 SKU 覆盖：8 DN / 8 号 / 1,516 行（6 在途、1 已收、1 状态未知）；其余 31 张 DN 不在样本内，符合 Q08。

## 5. 输出

`out/`：`supply_timeline_rows.csv`（233 行）、`demand_context.csv`（34）、`excluded_nonsupply.csv`（0）、`exceptions.csv`（1）、`unknowns.csv`、`recon.json`、`recon_by_sku_warehouse.csv`、`sc14_counts.json`、`sc14_findings.csv`、`w3_preview.json`、`sc04_recon.json`。

## 6. 复现

```bash
cd docs/research/supply-chain/2026-10-20/claude/experiments/supply_timeline
python w1_supply_timeline.py --live --snapshot frozen
python sc14/test_contract.py             # 21/21
python run_sc14.py                       # 0 error / 132 warning
python sc04_recon.py                     # 39/47/4,279 差 0
python -m unittest discover -s tests -v  # 12 条本地单测
```

实时库存只作对照：`--snapshot live`（标 `provisional_live`，不计算 B_min/B_max）。

## 7. 边界

- 不写生产、不下单、不改 EN 主数据、不合并 PR。
- 未知不写 0；`qty=null` + `qty_status=unknown`。
- 不跨 UOM 合计；通途数量 `uom_unproven`。
- 外部 FBA 两边都不算；一 DN 多号不复制数量。
- PK# 皮壳不 1:1 转成品；cover 行 `conversion_assumed=true`。
- 公开仓库不放行级 CSV/JSON。
