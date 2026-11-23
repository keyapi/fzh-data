# supply_netting — 供给净额集成层

把**已验收的需求净额表**与**最新库存/供应事实**按可售日期分桶净额，产出：
同一底层批量结构化供应事实（Parquet + manifest）+ 人工补货审核工作簿（xlsx）。

不做需求采集、不做供应采集、不做预测、不做采购决策、不写生产。

## 它解决什么

上游（`self_fulfilled_demand`）已经把终端需求整理成四列唯一、`netting_allowed=true` 的
`demand_netting.parquet`；Jack 的供应层（`supply_chain_visibility`）已经给出
`SupplyRow` 与 overlap gates。两边都对了，但**没有人把它们按时间桶对起来**：
哪个 SKU×仓×单位、在保护期内、下周、下下周会不会缺？缺多少？哪些供应只是「可能到」？

本模块就是那一步：逐桶 `期初库存 + 本期可计到货 − 需求 = 期末结余`，
下期承接上期，缺口单列；未知数量/日期/归属一律保留条件态，不写 0。

## 入口契约（硬约束）

| 项 | 规则 |
|---|---|
| 需求入口 | 只用 `demand_netting.parquet`（849ba1b0 冻结）；四列唯一 + `netting_allowed` 全 true，否则**直接报错** |
| 明细表 | `demand_canonical.parquet` 不读、不按行连接供应 |
| 阻断表 | `demand_blocked.parquet` 只登记哈希与行数，不参与净额 |
| 默认序列 | `in_default_series=true` 的行用 `quantity_default`；与 `netting_allowed` 是两个字段，不互相推导 |
| 3PL | `in_default_series=false` 的行单独输出，`replenishment_owner=unknown`，不并入自发货净额 |
| 供应 | Jack `SupplyRow` + `apply_overlap_gates`；`bucket_receipts` 分桶 |
| FBA | 已分配/外部 FBA 供应一律 `fba_allocated` 排除，不重复分配 |
| 同批 | 跨阶段同批（PO/在途）只计一次 |
| 子仓 | 子仓按 EN `Tongtu Shipping Warehouse` 归主仓 + 角色（cover/semi/finished/return），不再整块阻断 |
| 退货仓 | `role=return` 不计可用供给，单列 `return_warehouse_excluded` 证据 |
| 占位 SKU | `placeholder_skus` 清单/正则/`available` 阈值命中即排除，单列 `placeholder_excluded` |
| 通途 PO | `purchaseOrderQuery` 落地的 JSONL，按通途 SKU（`goods_sku`）匹配；开放量 `quantity − in_quantity`；无 ETA → 条件态 |
| 未知 | 缺 ETA / 缺快照 / 缺单位 / 缺身份 → 条件态或 unknown，绝不写 0 |

## 跑一次

```bash
uv run python -m supply_netting \
  --demand      "D:/Work/fzh-order-store/en-demand-v1/canonical/demand_netting.parquet" \
  --stock       "D:/Work/fzh-order-store/en_stock.parquet" \
  --sku-map     "D:/Work/fzh-order-store/sku_map.tsv" \
  --uom-cache   "D:/Work/fzh-order-store/en-demand-v1/canonical/item_uom_cache.parquet" \
  --po          "D:/Work/fzh-order-store/po_open.tsv" \
  --demand-blocked "D:/Work/fzh-order-store/en-demand-v1/canonical/demand_blocked.parquet" \
  --as-of 2026-10-21T00:00:00+08:00 --snapshot-date 2026-10-20 \
  --protect-days 3 --weeks 2 \
  --out "D:/Work/fzh-order-store/en-demand-v1/supply-netting/run-2026-10-21"
```

`--as-of` 是库存基准时点（带时区），必须不早于所选库存快照；`--snapshot-date` 默认取最新。
**推荐 `--as-of` 取快照采集瞬间**（如 `2026-10-23T10:47:42+08:00`）：取当日 00:00 会让
00:00–采集时刻的销量既已从库存扣减、又按未来需求入桶（10.8h 错位，2026-10-27 复审 F1）。
`--backlog` 可选：未履约 SO 余额（csv/parquet，四列键 + quantity）；不传时未来桶需求为 0，
不得据此推断「没有需求」。`--po-tongtool` 可选：通途采购单 JSONL（`purchaseOrderQuery` 落地）。

未来桶需求来自刷新预测：`--forecast-root`（读 `CURRENT`）、`--forecast-run-id`
（必须与 CURRENT 一致，否则报错）、`--forecast-lead-days`（默认 60）。
历史与需求资格仍来自 `demand_netting`；`--no-forecast` 只回放历史，manifest 会标注。

## 产物

| 文件 | 内容 |
|---|---|
| `supply_netting.parquet` | 逐 `sku × 仓 × 单位 × 桶 × 情景` 的期初/到货/需求/结余/缺口/状态 |
| `supply_facts.parquet` | **同一底层事实**：每条供应输入一行及其去向（计入/条件/排除+原因） |
| `replenishment_review.parquet` | 每个 SKU×仓×单位 的保护期缺口、视界累计未满足、条件供应量、状态 |
| `third_party_demand.parquet` | 3PL 需求，`replenishment_owner=unknown` |
| `stage_balances.parquet` | 订单执行阶段余额（互斥阶段；累计完工/出库不再相加） |
| `availability_schedule.parquet` | 分批「可售数量 × 日期」tranche 及其排除原因 |
| `supply_milestones.parquet` | 原计划 / 当前预计 / 实际 三列里程碑（结构就位，真实来源多为空） |
| `replenishment_review.xlsx` | 人工审核工作簿（补货审核 / 逐桶明细 / 供应事实去向 / Manifest） |
| `supply_netting_manifest.json` | 输入哈希、口径、计数、守恒检查、partial 原因 |

### ⚠️ `demand` / `gap` 是含跨桶结转的口径

`demand` = 本桶需求 + 上桶未满足（`carried_unserved`），`gap` = 累积未满足。
**逐桶 `sum(gap)` 或 `sum(demand)` 会重复计数**（2026-10-27 复审 F2：3 桶相加得 92，实际视界末 41）。
要逐桶统计请用 `period_demand`；要看视界末累计未满足请用最后一个桶的 `unserved`。

## 广范围补货决策包（10-29）

```bash
uv run python -m supply_netting.decision_pack   --run "D:/Work/fzh-order-store/en-demand-v1/supply-netting/run-2026-10-26-r5"   --demand "D:/Work/fzh-order-store/en-demand-v1/canonical-r2/demand_netting.parquet"   --out "D:/Work/fzh-order-store/en-demand-v1/supply-netting/decision-pack-2026-10-29"
```

每个 SKU×仓×UOM 键都有且只有一个去向（建议补货 / 无需补货 / 不可算 / 待核），
覆盖对账不符即报错；数量只在 UOM 组内合计；给 current-policy 与
higher-service 两档情景；产出 xlsx + Parquet + JSON + manifest。
见 [docs/decision-pack-2026-10-29.md](docs/decision-pack-2026-10-29.md)；
终审返修版（null 语义/严格 JSON/按 UOM）见 [r2 报告](docs/decision-pack-2026-10-29-r2.md)。

## 验证

```bash
uv run pytest supply_netting/tests -q          # 147 个用例（净额/契约/输入层/决策包/预测/F1–R3 回归/真实案例）
uv run pytest supply_chain_visibility/tests -q # 23 个（引入的上游组件）
```

## P1 条件决策包

```bash
uv run python -m supply_netting.pack \
  --run    "D:/Work/fzh-order-store/en-demand-v1/supply-netting/run-2026-10-23-r2" \
  --demand "D:/Work/fzh-order-store/en-demand-v1/canonical-r2/demand_netting.parquet" \
  --stock  "<库存快照 parquet>" \
  --blocked "D:/Work/fzh-order-store/en-demand-v1/canonical-r2/demand_blocked.parquet" \
  --out    "D:/Work/fzh-order-store/en-demand-v1/supply-netting/pack-2026-10-23-r2"
```

产物（行级数据只落本地）：

| 文件 | 内容 |
|---|---|
| `unmapped_top20_inventory.csv` / `_demand.csv` | 未映射 SKU 候选、证据、置信度、建议（map / map_after_confirm / manual / manual_or_skip） |
| `service_level_scenarios.csv` | A98/B95/C90 + flat95 情景；buffer = z×σ_daily×√14，**未含提前期** |
| `conditional_decision_pack.csv` / `.xlsx` | 每个 SKU×仓：需求、期初、已证到货、条件供给、缺口、服务档、建议（补 / 观察 / 数据不足） |
| `pack_manifest.json` | 计数、口径、引用的 run_id/as_of/partial |

匹配分级（越靠前证据越硬，低置信不硬绑）：`R1_sibling_suffix`（去后缀命中）→
`R1b_sibling_of_registered_variant`（靠已登记的 `-Foam`/`-Cover`/`-0` 兄弟继承）→
`R1c_sibling_conflict`（兄弟指向多个物料，low）→ `R2_model_unique`（型号唯一，medium）→
`R3_model_family`（型号下多物料，low）→ `none`（需运营补登）。

细节：[`docs/index.md`](docs/index.md)｜Agent 入口：[`AGENT_HANDOFF.md`](AGENT_HANDOFF.md)
