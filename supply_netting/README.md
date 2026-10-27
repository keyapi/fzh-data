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
`--backlog` 可选：未履约 SO 余额（csv/parquet，四列键 + quantity）；不传时未来桶需求为 0，
不得据此推断「没有需求」。

## 产物

| 文件 | 内容 |
|---|---|
| `supply_netting.parquet` | 逐 `sku × 仓 × 单位 × 桶 × 情景` 的期初/到货/需求/结余/缺口/状态 |
| `supply_facts.parquet` | **同一底层事实**：每条供应输入一行及其去向（计入/条件/排除+原因） |
| `replenishment_review.parquet` | 每个 SKU×仓×单位 的保护期缺口、视界累计未满足、条件供应量、状态 |
| `third_party_demand.parquet` | 3PL 需求，`replenishment_owner=unknown` |
| `replenishment_review.xlsx` | 人工审核工作簿（补货审核 / 逐桶明细 / 供应事实去向 / Manifest） |
| `supply_netting_manifest.json` | 输入哈希、口径、计数、守恒检查、partial 原因 |

## 验证

```bash
uv run pytest supply_netting/tests -q          # 26 个用例（含 8 条必测场景 + 契约 + 真实案例）
uv run pytest supply_chain_visibility/tests -q # 23 个（引入的上游组件）
```

细节：[`docs/index.md`](docs/index.md)｜Agent 入口：[`AGENT_HANDOFF.md`](AGENT_HANDOFF.md)
