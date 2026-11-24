# Supply Copilot（只读回放 + 刷新快照）

给外部 Agent/同事用：公共仓库放代码，客户数据放 EN 私有包（`FZH_DATA_ROOT`）。

```bash
uv sync
export ERP_API_KEY=... ERP_API_SECRET=... FZH_DATA_ROOT=D:/data/supply-copilot
uv run python -m supply_copilot doctor
uv run python -m supply_copilot pull
uv run python -m supply_copilot recommend --branch USNJ --sku KS0001-XMMBS-194-HEMPNATURAL

# 单 SKU 刷新（历史口径，保留兼容）
uv run python -m supply_copilot refresh --branch USNJ --sku KS0001-XMMBS-194-HEMPNATURAL

# 整分公司批量刷新 → 不可变快照 + report.json
uv run python -m supply_copilot refresh --branch USNJ --as-of 2026-11-24 --all \
  --out D:/private/supply-refresh \
  [--period-start 2026-11-13 --period-end 2027-02-17] \
  [--d6-version v6_22] [--horizon 97] [--live-snapshot EN快照.json] [--json]
```

- **凭证：只有 `ERP_API_KEY` / `ERP_API_SECRET`，没有也不需要 `ADMIN_ERP_API_KEY`。**
  用你自己的 EN 登录账号生成即可；**当前策略：任何能登录 EN 的用户（含 API Key 调用）都能拉包**，
  匿名 403；后续如需收紧，在服务端下载方法里加角色判断即可，客户端不用改。
- `doctor` / `recommend` / `batch` 只用已下载的包，不需要凭证；`pull` / `refresh` 需要。
- `recommend`：回放 pack（as_of 固定）。
- `refresh --sku`（无 `--out`）：拉 EN 实时库存、复用 pack 的 D5 预测重算；**不重训 D5**，
  报告标 `forecast reused`。这是**历史探索口径**（整期 D5 直接对当下库存、SO 仍进供给），
  不代表上面第 1–4 条的新口径；要审计口径请用 `--out`。
- `refresh --all --out`：整分公司快照，逐行写期间依据、供给分阶段、W1 SO 去重与对账。

## 刷新口径（新）

1. **期间**：D5 的 97/157 天是**整期**，不得当剩余期。未给 `--period-start/--period-end`
   时全部行 `period_basis=full_period` 且 `暂不能判断`；显式等长期间还必须满足
   **期间起点 = EN 库存观测日**——库存晚于起点时已逝需求无法桥接（D5 无日级分布），
   一律拒绝，不用整期需求减当下库存。
2. **已证供给**：`on_hand + in_transit + to_ship`（同一 EN 快照、单别名）。PO / CG / SO
   是不同阶段，单列、不进已证供给；SO 永不与生产/DN/PO 相加。
3. **W1 SO**：按 `(so, so_line)` 去重，开放量只计一次；**按 product_id 唯一汇总**
   （同产品的多形态行不可相加）；近期/历史开放/创建日未知三段保留，合计等于已知开放总量；
   数量缺失的行保持 `null` 并单列；报告拆 `so_scope`（快照内 / 范围外 / 其它分公司）。
   证据时点 ≠ 刷新时点时，SO 不参与"补"的确定判断（旧快照未观察到 ≠ 当前为 0）。
   阶段余额（`stage_balances`）单列、unknown 原样保留、不可与开放量相加。
4. **对账**：`report.json` 的 `输入行 = 接收 + 拒收 + 跳过`，每个拒收/跳过保留源行与原因；
   未知不补 0，数量缺失保持 `null`；同一输入同一字节（行级与整包 sha256）。

命令细节、字段表、样例计数见 [`docs/refresh-batch.md`](docs/refresh-batch.md)。

## 数据包管理（管理员）

1. zip 分卷放在站点 `private/files/`（文件名固定 `supply-copilot-pack-<version>.partNNN`）；
2. 由 `key_test` 的 `key_test.demand_collaboration.pack_download.get_part` 下发：
   登录即可下载、匿名 403、只允许该前缀的分卷；
3. 客户端 `pull` 通过 `FZH_PACK_METHOD`（默认上述方法）取分卷；换部署时改这个变量即可。
