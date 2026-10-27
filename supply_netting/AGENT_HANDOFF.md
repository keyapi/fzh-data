# supply_netting — Agent Handoff

> 入口：先读 [README.md](README.md)，细节看 [docs/index.md](docs/index.md)。
> 本模块**只做**「需求净额 × 供应事实 → 按可售日期分桶净额」，不重做需求/供应管道，不写生产。

## 1. 它在哪里、谁在用

2026-10-29 要交付大范围自发货补货建议（人工下单），10-30 演示。
需求层（`self_fulfilled_demand`）产出冻结的 `demand_netting.parquet`；
供应层（`supply_chain_visibility`）产出 `SupplyRow` 与 overlap gates；
本层把两者按时间桶对账，供决策包/审核工作簿消费。

## 2. 代码地图

| 文件 | 职责 |
|---|---|
| `demand.py` | `demand_netting.parquet` 唯一入口 + 四列/资格校验 + 序列拆分 + 可选 backlog |
| `supply.py` | 通途库存快照 / 在途 / 开放 PO → `SupplyRow`；无法归属的输入留证据行 |
| `engine.py` | `build_buckets` / `net_target` / `net_all`；两种情景；调用上游 gate 与分桶 |
| `legacy_ledger.py` | `bucket_gaps` / `assert_bucket_identities` / `allocate_so`（原样引入） |
| `facts.py` | A 阶段余额 / B 里程碑 / C 可售 tranche 的结构、校验与守恒 |
| `forecast.py` | 刷新预测入口：CURRENT/manifest 校验、窗口 p50 摊桶、预测资格与去向 |
| `artifacts.py` | Parquet + manifest + Excel 工作簿 |
| `__main__.py` | CLI |

上游组件（原样 `git show` 引入，未改写）：

| 文件 | 来源 commit | 说明 |
|---|---|---|
| `supply_chain_visibility/receipt_buckets.py` | `b08acc05` | 可售日分桶纯函数 |
| `supply_chain_visibility/tests/test_receipt_buckets.py` | `b08acc05` | 11 个用例 |
| `supply_chain_visibility/supply_row.py` | `6d374085` | `SupplyRow` 与校验 |
| `supply_chain_visibility/overlap_gates.py` | `6d374085` | 重叠/单位/FBA gates |
| `supply_netting/legacy_ledger.py` | `aa93773b`（`forward_net.py`） | 逐桶账数学 |

**禁止复用**：`compute_row`（首桶塞全部供应）、`harvest_total`（按运单号粗去重）。
两条都留在原实验脚本里，没有引入。

## 3. 必须守住的不变量

1. **需求只认四列唯一净额表**：`demand_canonical` 不读；`demand_blocked` 不参与。
2. **字段不混用**：`in_default_series` 决定序列，`netting_allowed` 决定资格，互不推导。
3. **默认序列用 `quantity_default`**，不拿 `quantity` 顶替。
4. **仓 × 单位是硬边界**：同 SKU 两仓不抵消，不同单位不合计。
5. **供应只经 gate 后入桶**：FBA 排除、同批只计一次、未证资格不进已证到货。
6. **未知不写 0**：无快照基准 → `unknown`；无 ETA → `date_unproven` 条件态；
   无未来供应证据 → `conditional`。所有数量缺口在 `gap` 里保持 `null`，由调用方判断。
7. **逐桶恒等式**：`期初 + 到货 − 满足 = 期末`、`需求 − 满足 = 未满足`，每行断言。
8. **供应数量账**：`input_known = counted + excluded_known`，每 SKU×仓×单位断言。
9. **每个输入有去向**：需求逐行 disposition，供应逐行 disposition，阻断账只登记不参与。
10. **阶段互斥**：`stage_balances` 同订单×物料×仓×单位的阶段不得重复；累计完工/累计出库
    不得再加成新供应；订单差额单列，不塞进任何阶段。
11. **tranche 不是第二份供应**：可售计划由阶段余额派生，已含期初的不得补入；拆分必须
    精确等于原余额（`split_balance` 会拒绝凑数）。
12. **期初也要过 gate**：`opening_basis` 只看已证、非重放、自由库存；FBA/重放期初排除留证；
    无法判定时 `opening=null`，绝不写 0。
13. **证明随行传递**：阶段→tranche→SupplyRow 的 identity/warehouse/source_complete 原样传，
    转换层不得抬升资格。
14. **同批只计一次**：已证 `batch_key` 跨阶段保留最靠后阶段；重复 `balance_id` 抛错；
    阶段校验在写产物之前，失败不落盘。
15. **预测与需求两套资格**：`netting_eligible` ≠ `netting_allowed`；实际订单优先于预测；
    预测只覆盖通过资格的键，未覆盖部分不填 0。
16. **拆分母额度**：`split_of` + `split_total` 必须传到计数侧；同一父的 6/4 子额度各自计数，
    只有同一额度跨阶段重放才去重；拆分合计≠父余额直接报错。
17. **期初未知就是未知**：混合已知+未证期初 → `opening=null` 并给 `opening_lower_bound`，
    不能用精确小计隐含未知为零。
18. **预测哈希**：消费前按上游 manifest 的 `outputs` 校验窗口 sha256 与行数；
    缺失/重复/错配一律 `ForecastContractError`。

## 4. 两种情景

| 情景 | 含义 | 计入规则 |
|---|---|---|
| `conservative` | 已证按时可用 | 只计 `b_min_eligible` 且可售日已证 |
| `expected` | 当前预计到货 | 计入 `b_max_eligible`；日期未证仍为条件态 |

真实数据目前两种情景没有差异（通途在途/开放 PO 都没有逐行 ETA，两边都不计），
这在 manifest 里可以直接看出来，不是 bug。

## 5. 跑与验

```bash
uv run pytest supply_netting/tests -q           # 136
uv run pytest supply_chain_visibility/tests -q  # 23（上游组件）
uv run python -m supply_netting --help
```

真实案例对照在 `tests/test_real_case.py`：数据缺失时整组跳过，不误报。

## 6. 已知边界（不要假装已解决）

1. 未履约 SO 余额未接入：`--backlog` 为空时未来桶需求为 0，不能据此说「不缺」。
2. 通途在途与开放 PO 无逐行 ETA，永远条件态；PO 多为物料仓，绝大多数无法映射成品 SKU
   （`identity_unproven`），这是数据现实，不是代码缺陷。
3. 供应来源仅通途库存快照/在途 + 开放 PO，业务覆盖 unverified，manifest 恒 `partial=true`。
4. 子仓（如 `美中-FZH-DANEEY-皮壳仓库`）无库存快照 → 净额 `unknown`，需补快照源。
5. 日级需求按 `as_of` 时区当日 00:00 落桶（`date_adapter_rule`），未获业务裁定的
   「当日末可售」规则没有启用。
6. `--as-of` 与库存快照的先后关系由调用方保证；CLI 不会替你猜时区。

## 7. 常见坑

- `demand_netting.parquet` 的列是 `canonical_uom`，不是 `uom`；四列键见 `demand.NETTING_KEY`。
- 库存快照的 `sku` 是通途 SKU，必须经 `sku_map.tsv` 映射到 EN 物料；一对多不任取。
- `en_stock.parquet` 的 `snapshot_at` 没有时区：不要悄悄补，`timezone_status=unverified`。
- 库存 0 是证据（快照明确为 0），不能当作「没有基准」；没有该仓/物料行才是 unknown。
