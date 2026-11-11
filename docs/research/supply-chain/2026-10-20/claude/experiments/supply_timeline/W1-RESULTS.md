# W1 供应时间线 · 9 SKU 正式 recon（冻结基准）

> 样本：`JACK_ENTRY.md` / `JACK_QA.md`（2026-10-26）与 sample10 的 9 个冻结 SKU + 1 个缺额。
> 基准：库存 2026-10-22、WO 2026-10-20、PO 2026-10-19（本地 `local/frozen_20261022.json`；公开仓库只留 schema + sha256）。
> 契约：`docs/jack-w1-channel` @ `197901f7`（sha256 `45c2bb93…`），SC14 7 阶段 / 21 用例；`tests/test_sc14_sync.py` 校验副本未漂移。
> 只读：EN 生产 REST；未写、未下单、未改主数据。
> D33：公开仓库不含行级业务值；本文只放聚合计数，行级明细在本地 `out/` / `local/`。

## 1. 合同校验

| 项 | 结果 |
|---|---:|
| SC14 tests | **21/21 passed** |
| SC14 errors | **0** |
| SC14 warnings | 132（`W_UOM_UNPROVEN` 66 + `W_UOM_FLAG` 66）；66 行 × 2 code，明细见 §8.7 |
| supply 行 | 233 |
| demand（SO，单独文件） | 34 |
| excluded（非供给） | 0 |
| exceptions（production_conflict） | **1**（WO-26-03110） |

W3 预览：opening 832（通途 UOM 未证）；expected 1,506 个；unknown 23 行（qty_known 1,935 + 488 个；qty_null 60）。

## 2. 阶段（冻结基准）

| 阶段 | 行数 | counted 行 | counted 数量 |
|---|---:|---:|---:|
| on_hand | 54 | 22 | **832**（通途无 UOM；与 sample10 总可用一致） |
| po_open | 8 | 0 | 1,021（含 waiting 5、`status=4` PO 102；B_min 全排除） |
| in_production | 7 | 7 | **433 个**（全部 cover，estimated） |
| shipped_in_transit | 132 | 4 | 914（通途在途）+ 1,506 个（DN trace，不计） |
| received | 28 | 0 | qty=null（签收到达，数量未证） |
| unknown | 4 | 0 | C/Velvet DN-26-00112（状态缺失；qty known，日期 unknown） |

**B_min = 1,212（UOM 未证）**；**B_max = 2,762（UOM 未证）+ 433 个**。
- B_min 只含 `finished/component`，且排除 `same_batch_suspected` PO、`b_max_only`、未映射仓。
- B_max 含 `cover`（`conversion_assumed=true`）与全部开放 PO（含 `status=4` 的 PO021735 102，语义未证）。
- 6 个 `cover` / 2 个 `finished` / 1 个 `component`（Q06）。

## 3. Q01–Q08 落地情况

| Q | 落地 |
|---|---|
| Q01 阶段 | 7 阶段已启用；`unknown` 行（DN-26-00112）进入 supply，只进 `supply_unknown`；`partially_received` 本样本 0 行 |
| Q02 库存 | 正式 recon 用 10-22 冻结值；`--snapshot live` 只输出 `provisional_live`，不计算 B_min/B_max |
| Q03 WO | 只纳入 creation ≤ 10-20；三张额外 WO 的 creation 已回读：03110/03118=`2026-09-02`、03664=`2026-10-19`，均符合 Q03；`WO-26-03110` 标 `production_conflict`、进 exceptions、不计供给；C/Linen 101、CENCord 152 与 sample10 一致；额外 `WO-26-03118` 70、`WO-26-03664` 110 按 Q03 规则计入并标 `sample10_wo_not_listed`（见 §8.4） |
| Q04 PO | `PO021735`：`po_status=4` + `po_status_semantics=unproven`，语义未证；只进 B_max、不进 B_min，**不等同于已关闭**；其余 6 条开放 PO 全部保留 |
| Q05 overlap | TT0031038 201=201、C/Linen 121=121、TT0312701 480=480、C/Cord-White 112=112 均 `same_batch_suspected`；B_min 排除 PO，B_max 保留 |
| Q06 角色 | 6 cover / 2 finished / 1 component；`identity_confidence=proven`（`sku_item`）；PK# 不 1:1 转成品 |
| Q07 仓库 | 不同 `warehouse_id` 可相加；cover 行标 `conversion_assumed=true`，B_min 只放已证转换（本样本 0），B_max 放假设 |
| Q08 received | 28 行 `received_evidenced`（qty=null，只进 supply_unknown）；全部属于 **1 张 DN-26-00067 / 1 个 SKU**，不是 28 张单；`received_booked=0`；9 SKU 覆盖 8/39 DN、1,516/4,279 行（见 §8.5） |

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

`out/`：`supply_timeline_rows.csv`（233 行）、`demand_context.csv`（34）、`excluded_nonsupply.csv`（0）、`exceptions.csv`（1）、`unknowns.csv`、`recon.json`、`b_bridge.csv`、`b_bridge_po.csv`（本地逐 PO）、`recon_by_sku_warehouse.csv`、`sc14_counts.json`、`sc14_findings.csv`、`w3_preview.json`、`sc04_recon.json`。审计元数据：公开 `config/wo_audit_20261022.summary.json`；本地逐 WO 明细 `local/wo_audit_20261022.json`。

## 6. 复现

```bash
cd docs/research/supply-chain/2026-10-20/claude/experiments/supply_timeline
python w1_supply_timeline.py --live --snapshot frozen --config local/frozen_20261022.json
python sc14/test_contract.py             # 21/21
python run_sc14.py                       # 0 error / 132 warning
python sc04_recon.py                     # 39/47/4,279 差 0
python -m unittest discover -s tests -v  # 离线；无 canonical 时 1 skip（预期）
python tests/run_canonical_tests.py      # fetch canonical + 19 passed / 0 skip
```

实时库存只作对照：`--snapshot live`（标 `provisional_live`，不计算 B_min/B_max）。

## 7. 边界

- 不写生产、不下单、不改 EN 主数据、不合并 PR。
- 未知不写 0；`qty=null` + `qty_status=unknown`。
- 不跨 UOM 合计；通途数量 `uom_unproven`。
- 外部 FBA 两边都不算；一 DN 多号不复制数量。
- PK# 皮壳不 1:1 转成品；cover 行 `conversion_assumed=true`。
- 公开仓库不放行级 CSV/JSON。

## 8. Q09 整改对照（2026-10-26）

| Q09 | 状态 | 落地 |
|---|---|---|
| #1 代码位置 | ✅ | 代码只在 `feature/jack-supply-timeline`；docs 分支 `140bbee6` 已 revert（`bb87549a`）；feature draft PR #312 |
| #2 SC14 不 fork | ✅ | 副本与 canonical 逐字节一致（297/245 行）；`sc14/SOURCE.json` 固定来源与 sha256；`tests/test_sc14_sync.py` 防漂移 |
| #3 PO status=4 | ✅ | `po_status=4` + `po_status_semantics=unproven`；删除“作废/cancelled”；只进 B_max |
| #4 WO 审计 | ✅ | `config/wo_audit_20261022.json` + `wo_creation/wo_modified/jc_first_op_sum/jc_source`；见 §8.4 |
| #5 received 拆分 | ✅ | `recon.json.received_audit`；28 行=1 DN/1 SKU；非样本 5 张按设计不抓取；见 §8.5 |
| #6 B 桥接 | ✅ | `recon.json.b_bridge` + `b_bridge.csv`；代码内断言桥接合计=B_min/B_max；见 §8.6 |
| #7 warning 说明 | ✅ | `sc14_counts.json` 增加 `finding_rows/warning_rows_by_stage`；见 §8.7 |

### 8.4 WO 审计

| WO | creation ≤ as_of | modified_after_as_of | 结果 |
|---|---|---|---|
| WO-26-03110 | 是 | 是 | `production_conflict`，exceptions，qty=null |
| WO-26-03118 | 是 | 否 | 计入，`sample10_wo_not_listed` |
| WO-26-03664 | 是 | 是 | 计入，`sample10_wo_not_listed` |

三张 WO 的 creation 均 ≤ 2026-10-20，Q03 纳入成立，B_max 不变。`jc_first_op_sum` 只作证据字段，不参与 remaining 计算、不改变 conflict 判定；`wo_state_as_of=2026-10-20`、`jc_as_of=2026-10-26`，03110/03664 的 modified 晚于 as_of，标 `modified_after_as_of=true`。逐 WO 日期/JC 明细在本地 `local/wo_audit_20261022.json`，公开侧只有聚合 summary。

### 8.5 received 拆分

| DN | SKU | rows | doc_lines | posting_date |
|---|---|---:|---:|---|
| DN-26-00067 | CEN1607NLinen-Ivory-194 | 28 | 28 | 2026-08-21 |

主 supply 行带 `doc_qty / received_qty / posting_date / received_source`（`received_source=shipment_signed`，`received_qty=null`）。`doc_qty` 合计 231 在本地 `out/recon.json` 的 `received_audit`，公开文档不展开行级数量。W1 只抓 9 SKU，`received_audit.out_of_sample=0`（`not_fetched_by_design`）。SC04 的 6 张 received DN 中 1 张在样本内，其余 5 张不在样本内，W1 不抓取。

### 8.6 B_min/B_max 桥接

| 来源（ledger） | 行数 | qty | → B_min | → B_max | 排除原因 |
|---|---:|---:|---:|---:|---|
| stock（on_hand） | 22 | 832 | 531 | 832 | cover 301 `cover_conversion_unproven` |
| po | 6 | 914 | 0 | 914 | `po_not_counted` 914 |
| po_bmax | 1 | 102 | 0 | 102 | `b_max_only` 102 |
| wo | 7 | 433 个 | 0 | 433 个 | cover 433 |
| stock_intransit | 4 | 914 | 681 | 914 | cover 233 |
| dn_trace | 128 | 1,506 个 | 0 | 0 | `not_in_ledger`（trace_only） |
| received_evidenced | 28 | qty null | 0 | 0 | `qty_unknown` |
| waiting | 1 | 5 | 0 | 0 | `not_in_ledger` |
| unknown | 36 | 55 个（4 行有量） | 0 | 0 | `not_in_ledger` |
| **合计** | | | **1,212** | **2,762 + 433 个** | |

桥接由 `build_bridge()` 按与 `ledger_sum()` 完全相同的排除顺序生成；`build_recon()` 内断言各 UOM 合计与 B_min/B_max 一致。其中 `po` 6 行 / 914 全部是 `same_batch_suspected` 且无 ETA（`date_confidence=unknown`），因此不进 B_min；逐 PO 明细（含 open_qty）在本地 `out/b_bridge_po.csv`。

### 8.7 SC14 warning 132 vs 136

- 132 = **66 行 × 2 code**（`W_UOM_UNPROVEN` + `W_UOM_FLAG`）。
- 行级分类：`on_hand` 54 + `po_open` 8 + `shipped_in_transit` 4（全部通途来源、无 UOM）；行级清单见本地 `out/sc14_findings.csv`（不进公开仓库）。
- exceptions 1 行与 unknown 4 行都带 `uom=个`，不产生 UOM warning。
- 136（68×2）来自旧的 **provisional-live** 轮次（as_of 10-23、live 库存 10-26、232 行），行级 CSV 未保留，不能逐行回溯；正式基准以 10-22 冻结轮为准。

## 9. Q10 整改对照（2026-10-26）

| Q10 | 状态 | 落地 |
|---|---|---|
| 阻塞：行级 JSON | ✅ | `frozen_20261022.json` / `wo_audit_20261022.json` 已移出 git，值在本地 `local/`（gitignore）；公开侧只留 `frozen_20261022.schema.json`、`frozen_20261022.sha256`、`wo_audit_20261022.summary.json`；新增 `--config` / `--wo-audit` |
| #2 SC14 skip | ✅ | `tests/test_sc14_sync.py` 优先读 `SC14_CANONICAL_DIR`，否则从 `origin/docs/jack-w1-channel` 读取 canonical（缺失时 `git fetch --depth=1`）；CI/`SC14_SYNC_REQUIRE=1` 下缺失即失败；19 passed / 0 skip |
| #3 WO 时点 | ✅ | `wo_state_as_of` / `jc_as_of` / `modified_after_as_of` 落到 WO 行与 exception；03110、03664 标 true；conflict 仍保守不计 |
| #4 per-PO 桥接 | ✅ | `out/b_bridge_po.csv`（本地逐 PO）；`recon.json.b_bridge_po_summary` 聚合：6 行 / 914 / 全部 `same_batch_suspected` + 无 ETA → `po_not_counted` |
| #5 received 字段 | ✅ | 主 supply 行带 `doc_qty / received_qty / posting_date / received_source` |
| #6 contract pin | ✅ | `run_sc14.py` 从 `sc14/SOURCE.json` 读取 `contract_source_commit` 与 sha256 |

### 9.4 逐 PO 桥接（公开视图，不含 open_qty）

| PO | po_status | overlap_status | date_confidence | B_min 排除原因 |
|---|---|---|---|---|
| PO021716 | 0 | same_batch_suspected | unknown | po_not_counted |
| PO021727 | 0 | same_batch_suspected | unknown | po_not_counted |
| PO021717（C/Linen） | 0 | same_batch_suspected | unknown | po_not_counted |
| PO021705 | 0 | same_batch_suspected | unknown | po_not_counted |
| PO021717（C/Cord-White） | 0 | same_batch_suspected | unknown | po_not_counted |
| PO021733 | 0 | same_batch_suspected | unknown | po_not_counted |

6 行合计 914，全部因 `same_batch_suspected` 且无 ETA（`date_confidence=unknown`）不进 B_min，不是数量为 0；`open_qty` 逐行在本地 `out/b_bridge_po.csv`。

## 10. Q11 整改对照（2026-10-26）

| Q11 | 状态 | 落地 |
|---|---|---|
| #1 仓库 confidence/scope | ✅ | `warehouse_map.json` 增加 `warehouse_scope_basis=operator`：`warehouse_scope` 表示运营方（own/3pl/fba），**不是库存所有权**；in_house 库存所有权均为我方。波兰仓 `warehouse_confidence` 由 confirmed 降为 assumed（EN 映射无独立证据）；CENTRADE/DANEEY 保留 confirmed 并写 `warehouse_confidence_basis`（DN customer + en_finished 交叉印证）。数量口径不变（assumed 仍计入，只有 unmapped 排除）。 |
| #2 SC14 默认 skip | ✅ | `tests/test_sc14_sync.py` 改为纯离线：读 `SC14_CANONICAL_DIR` → `local/sc14_canonical` → `../sc14`；都没有时 skip（离线预期）。网络 fetch 移到 `tests/run_canonical_tests.py`，该入口 fetch 后以 `SC14_SYNC_REQUIRE=1` 运行，19 passed / 0 skip。 |
| #3 PR body | ✅ | 改为“无行级数量 JSON；sample_skus/warehouse_map 仍含标识/映射，已由用户确认保留”；SC14 说明离线 skip 为预期。 |
| #4 minor | ✅ | §8.6 补 `po` 行说明；`sample_skus.json` 增加 `as_of_note`（样本冻结日；快照 10-22/10-20/10-19）。 |

**用户决定（已关闭）**：保留 `sample_skus.json` / `warehouse_map.json`（只有标识/映射，无数量/金额）。

### 10.1 仓库 scope 语义

- `scope`：`in_house` / `external_fba`（SC14 口径）。
- `warehouse_scope`：仓库**运营方**，`own`=自营、`3pl`=第三方运营、`fba`=FBA；**不是库存所有权**。
- in_house 库存所有权均为我方；`supply_own_*` 不应按 `warehouse_scope=own` 过滤，应按 `scope`/所有权口径。
