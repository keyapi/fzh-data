# W1 供应时间线（SC14 7 阶段 / 冻结基准）

只读脚本：按 `docs/jack-w1-channel` 的 `JACK_ENTRY.md` / `JACK_QA.md`（2026-10-26，Q01–Q08）与 sample10，对 **9 个冻结 SKU + 1 个缺额**输出 `SKU × 仓库 × 阶段` 供应事实。

## 口径

- **正式 recon 用冻结值**：库存 2026-10-22、WO 2026-10-20、PO 2026-10-19，见 `config/frozen_20261022.json`；`--snapshot live` 只作 `provisional_live`，不计算 B_min/B_max。
- SC14 **7 阶段**：`on_hand / po_open / in_production / shipped_in_transit / received / partially_received / unknown`；21 条验收用例。
- 映射角色（Q06）：**6 cover / 2 finished / 1 component**；`identity_confidence=proven`（sku_item）；PK# 不 1:1 转成品。
- 仓库（Q07）：不同 `warehouse_id` 且未重复上报可相加；cover 行 `conversion_assumed=true`，B_min 只放已证转换，B_max 放假设。
- PO/在途两本账：`overlap_status`；B_min 排除 `same_batch_suspected` PO，B_max 全保留；status=4 语义未证，只进 B_max，不等同于已关闭。
- 未知不写 0；`qty=null + qty_status=unknown`；`date_confidence=unknown` 时 `available_date=null`。
- 一 DN 多号只出一行；外部 FBA `scope=external_fba`，rollup 两边都不算。
- WO `produced_qty` 只作 estimated remaining；JC 只作 `production_progress`；冲突进 exceptions。
- SO 未履约单独输出 `demand_context.csv`，不进 supply。

## 运行

```bash
cd docs/research/supply-chain/2026-10-20/claude/experiments/supply_timeline
python w1_supply_timeline.py --live --snapshot frozen   # 正式 recon
python sc14/test_contract.py                            # 21/21
python run_sc14.py                                      # E_*/W_* 计数 + W3 预览
python sc04_recon.py                                    # 39/47/4,279 对账
python -m unittest discover -s tests -v                 # 17 条本地单测（含 SC14 同步校验）
```

`--snapshot live` 用于对照实时库存（标 `provisional_live`）。重复运行走 `cache/`，`--refresh` 强制刷新。

## 输出（`out/`）

| 文件 | 内容 |
|---|---|
| `supply_timeline_rows.csv` | W1 主表（SC14 字段 + 角色/仓库/两本账/转换标记） |
| `demand_context.csv` | SO 未履约（需求上下文） |
| `excluded_nonsupply.csv` | 非供给行 |
| `exceptions.csv` | production_conflict / 部分签收分配未知 |
| `unknowns.csv` | 未知数量/日期/仓库行 |
| `recon.json` / `recon_by_sku_warehouse.csv` | 阶段计数、B_min/B_max、逐 SKU×仓汇总 |
| `b_bridge.csv` | B_min/B_max 桥接（按 ledger × role × UOM，含排除原因） |
| `sc14_counts.json` / `sc14_findings.csv` | SC14 校验 |
| `w3_preview.json` | confirmed/expected/unknown 预览 |
| `sc04_recon.json` | SC04 基线 + 9 SKU 覆盖 |

## 目录

- `config/sample_skus.json`：9 SKU + 角色/转换假设 + 缺额。
- `config/frozen_20261022.json`：10-22/10-20/10-19 冻结 stock/PO/WO。
- `config/wo_audit_20261022.json`：三张额外 WO 的 creation/modified 与 JC 首工序合计（审计元数据，不改冻结数量）。
- `config/warehouse_map.json`：6 通途仓 + FBA/FZH；`scope`/`warehouse_scope`/`warehouse_confidence`。
- `sc14/`：从 `docs/jack-w1-channel` @ `197901f7` 复制的 7 阶段契约与 21 用例（逐字节一致）；`sc14/SOURCE.json` 固定来源与 sha256，`tests/test_sc14_sync.py` 防漂移。
- `W1-RESULTS.md`：正式 recon 结果。
- `W1-QUESTIONS.md`：首轮问题存档（Q01–Q08 已由 `JACK_QA.md` 答复）。

## 已知边界

- 本样本无 `partially_received` 行；SC04 的 1 张部分签收 DN 不在 9 SKU 样本内。
- 9 SKU 覆盖 8/39 DN、1,516/4,279 行（Q08 预期）。
- `WO-26-03110` 存在 produced_qty=0 vs JC 110>100 冲突，进 exceptions。
- 额外 `WO-26-03118` 70、`WO-26-03664` 110 按 Q03（creation ≤10-20）计入；sample10 未列，标 `sample10_wo_not_listed`（结果文档说明）。
- 公开仓库不放行级 CSV/JSON。
