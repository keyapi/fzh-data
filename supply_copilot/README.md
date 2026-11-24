# Supply Copilot（只读补货决策）

公共仓库放代码，客户数据放 EN 私有包（`FZH_DATA_ROOT`）。给同事 / 老板的 Agent 用：
**问补货问题 → 得到 A/B/C/D/E 证据链 + 建议**，不直接下单。
一页操作手册见 [`RUNBOOK.md`](RUNBOOK.md)。

## 3 分钟起步

```bash
git clone https://github.com/keyapi/fzh-data.git
cd fzh-data && uv sync

# 1) 准备一个空目录放私有数据包（不要在仓库里）
#    Windows PowerShell:
$env:ERP_API_KEY="<你的EN内部账号key>"
$env:ERP_API_SECRET="<你的secret>"
$env:FZH_DATA_ROOT="D:\fzh-pack"; mkdir D:\fzh-pack
#    macOS / Linux:
#    export ERP_API_KEY=... ERP_API_SECRET=... FZH_DATA_ROOT=~/fzh-pack; mkdir -p ~/fzh-pack

uv run python -m supply_copilot doctor     # pull 前显示 missing 属正常
uv run python -m supply_copilot pull       # 下载并校验私有包（约 14MB）
uv run python -m supply_copilot doctor     # 期望 status=ok, missing_files=[]
```

- 凭证只有 `ERP_API_KEY` / `ERP_API_SECRET`，用**自己的 EN 内部账号（System User）**；
  没有也不需要 `ADMIN_ERP_API_KEY`。匿名/门户账号 403。
- 目录要先存在（`doctor` 不会替你创建）；`--env-file` 对含空格路径不可靠，Windows 建议直接设环境变量。
- `doctor` / `recommend` / `batch` 只用已下载的包；`pull` / `refresh` 才需要凭证。

## 能问什么（和补货相关）

| 你可以问 Agent | 对应命令 / 依据 |
|---|---|
| 某 SKU 给某分公司要不要补、补多少、什么时候补、为什么 | `recommend --branch USNJ --sku <SKU>` |
| 这个分公司各类动作的数量/数量合计（汇总） | `batch --branch USNJ` |
| 这个建议的 q50/q90/q95、C/EN/PO/SO/CG、净需求、需要日/下单日 | `recommend` 报告与 `--json` |
| 这个分公司逐 SKU 的全部明细（不截断） | `recommend --branch USNJ --json` |
| 用的什么预测模型？回测怎么样？趋势如何？ | D5/D3b 证据（模型、holdout、趋势） |
| 现在实时库存多少？按实时库存净需求变多少？ | `refresh --branch USNJ --sku <SKU>`（仅换库存） |
| 按实时库存+开放 SO/PO 重算今天要不要补 | `supply --branch USNJ` → `decide --branch USNJ`（见下） |
| 历史订单 parquet 在哪、齐不齐 | `history` / `pull-history`（EN 私有，不打包） |
| 我要自己用最新订单分析/预测 | `pull-orders` → `<root>/orders/<version>/orders_unified.parquet` |
| 换一套决策口径（v6.24）看看 | `recommend --d6-version v6_24 ...` |
| 精确匹配还是模糊搜 SKU | 默认精确；`--like` 才模糊（防 KS100 误配 KS1000） |
| 这份数据是什么时点、是否完整可信 | `doctor` + 包版本/as_of/sha256 |

分公司编码：`USNJ`（美东）、`USTX`（美中）、`PL`（波兰）。

注意：`recommend/batch` 是**历史回放**（显示 `as_of`），不是今天的执行建议；未知一律不补 0。

## 实时决策（live）与可执行性

```bash
uv run python -m supply_copilot supply --branch USNJ   # 抓实时库存 + 开放 SO + 开放 PO → <root>/live/
uv run python -m supply_copilot decide --branch USNJ   # 用 live 供给重算，输出报告
```

`decide` 报告开头会给出 **可执行性（是/否）** 和原因。当前默认口径下通常是「否」，因为：

- 需求仍来自 D6 历史包（95% 档，as_of 2026-11-13），不是本次刷新；
- PO 多落在物料仓/未映射 SKU，未按通途 `purchaseOrderQuery` 接入；
- CG 抵扣未按实时 WayfairCG 库存重算；
- 需要日/下单日沿用 D6 包，已过的日期会标 `past_due`。

它给的是**当天候选**（补/不补/待核 + 数量 + 证据），不是可直接下单的指令。
只有上述原因补齐、`可执行性=是` 时，才允许作为采购建议。

### SO / PO 口径（2026-11-24 P0）

- **PO 按时**：`ETA ≤ 需要日` 才算按时，逐行比较；ETA 缺失或晚于需要日均计入
  “未证按时”。`meta.po` 分开报 `quantity` / `with_eta_qty` / `on_time_qty` /
  `missing_eta_qty` / `late_qty`，以及有效开放 `accepted_rows` /
  `accepted_documents` / `outside_decision_qty`。PO/SO 是
  `(SKU, 仓, UOM)` 键级**共享事实**：D6 有重复形态键时逐行求和会重复，
  汇总只能用 `meta.po.decision_qty` / `meta.so.decision_qty`。
- **SO 身份**：EN `item_code` 是权威身份，**不拿它反查 `sku_map`**（映射表键是
  `tongtool_sku`）；别名只对明确的 `customer_item_code` 且唯一映射时执行。
  `PK#` / `ND#` 是合法 EN 物料号，不剥前缀凑成品，归
  `form_out_of_scope`；其它不在本池 D6 的归 `product_out_of_scope`。
- **SO 单位**：无 `UOM_EQUIVALENTS` 明确换算证据时，**不改标签照用数量**；
  单位不一致记 `uom_mismatch`，缺单位记 `uom_missing`。
- **SO 开放状态**：逐行正向校验，只有明确允许的开放状态
  （`To Deliver and Bill` / `To Deliver` / `To Bill`）且 `docstatus=1`
  （或无 status 列时的有效 `docstatus=1`）才计入并可附加需求；
  `Closed` 归档单列，空状态 / `Draft` / `Unknown` / 其它未知状态分别单列
  （`status_missing/draft/unknown_rows`、`docstatus_not_submitted_rows`），
  **一律不附加**。`meta.so.open_verified` 只表示来源带 status/docstatus 契约，
  不代表每行都已验开放（逐行结论看 `status_*_rows`）。没有 status/docstatus
  的来源整批 `status_missing`，不附加需求（请用 `open_nonclosed` 来源或带 status
  的 JSONL）。
- **SO 是否已在预测内**：显式开关 `--so-in-forecast true|false`（函数参数
  `so_in_forecast`）。默认 `true`（保守）：视为开放 SO 已含在预测里，
  **不叠加需求**；`false`：视为未含，把可归一的开放 SO 余额叠加到需求。
  只有真正加进某个合格建议行后才消费该键；待核行不提前占用，无法附加的量记
  `meta.so.unattached_qty`。两种语义都会写进 `meta.so.semantics/impact` 和逐行
  `warnings`。口径上 **SO 为上游交付管线，不进需求**。
- **assumed_zero**：源文件存在但解析零行时，不静默当实测 0，而是给
  `meta.so/po.assumed_zero` 信封（`applies` + `reason`），并在
  `meta.totals.assumed_zero_rows` 按来源计数（`{so, po}`）；有行但被过滤
  （如全 Closed / 零开放量）不算 assumed_zero。

## 自己重算需求/预测（不依赖我们）

```bash
uv run python -m supply_copilot pull-orders
uv run python -m supply_copilot rebuild \
  --orders <root>/orders/orders-2026-11-22.1/orders_unified.parquet \
  --out <root>/rebuild/2026-11-23
uv run python -m supply_copilot decide --branch USNJ --forecast-root <root>/rebuild/2026-11-23/forecast
```

- `rebuild` 在本地跑：订单 → 需求表 → 预测；约几分钟（AutoETS），不写 EN、不动线上包。
- 预测只给「中位（p50）」和「保守（p90，约 90% 情形）」；**不再派生 q95**；D6 历史包仍是 95% 档，只作对照。
- 未覆盖的 SKU 退回 D6 历史 95% 档并计数，不会静默当成已刷新。
- 需要 `sku_map.tsv`（`pull` 提供）和 `item_uom_cache.parquet`（`pull-history` 提供）；
  也可用 `--sku-map/--uom-cache` 指定。
- 周计划：`uv run python -m supply_copilot weekly`（13 周；周度模型/4–8 周/等分，标 method 与回测）。

## 历史订单数据（不在公共仓库）

- **最新订单明细**：`pull-orders` → `orders_unified.parquet`，当前版本 **orders-2026-11-22.1**（数据到 2026-11-22；含历史 GS + EN 增量）。给想自己用 Excel/Pandas 分析或自建预测的人用，不强制用我们的模型。
- **需求/预测重建输入**：`pull-history` 的 parquet 快照（截止 **2026-10-26**），只在重训预测/复核明细时需要。
- 文件放在 EN 私有目录 `private/supply-history/<version>/`，登录 API 取，**不打包、不分卷**；`pull-orders`/`pull-history` 都会校验 sha256。
- 定时更新是运维任务（服务器端直接读数据库导出，不走 REST 全量翻页），不在每个 Agent 里跑。

## A/B/C/D/E 是什么

- **A SKU 宇宙**：SKU × 客户 × 仓 × 形态 × UOM（`sku_map.tsv`、`E_lifecycle.parquet`）
- **B 归属**：某 SKU 归哪个客户/池；当前 CLI 未暴露 B 确认流程（数据在本地分析侧）
- **C 库存**：当前可发 C、EN 在途/待发、PO、SO、CG（下游缓冲，不可回拨）
- **D 预估**：D5 v6.8 分位预测（p50/q90/q95…）+ D3b 分类/回测/趋势
- **E 已有供给**：E 节点/生命周期、W1 SO 事实（`E_nodes.parquet`、`W1_SO.jsonl`）
- **D6 决策**：q95 需求 − C/EN/PO/SO/CG = 净需求 → 补 / 催已有 / 不补 / 观察

## 包里有什么（15 个文件，2026-11-13.1）

D3b、D5、D6 v6.22 / v6.24、E 节点与生命周期、C14、CNY v13、traj v13、
W1 SO、SKU 映射、USNJ 建议、老板版 v5.5、需求趋势、服务水平。

其中 CNY（春节备货）、老板版、E 明细、B 归属目前**只有数据、尚无 CLI 命令**；
需要时让 Agent 直接读包内文件，或后续加命令。

## 记录在哪里

- 代码与约定：`supply_copilot/`（本目录）、`.agents/skills/supply-decision-copilot/SKILL.md`
- 测试：`tests/test_supply_copilot.py`
- 数据包清单：`supply_copilot/pack_manifest.json`（版本/as_of/分卷/哈希）
- EN 侧：`key_test` 仓库的 `pack_download`（下发）与 `usnj_static` + Page（只读页）
- 私有数据：EN `private/files/` 与本地 `FZH_DATA_ROOT`，**不进公共仓库**

## 数据包管理（管理员）

1. zip 分卷放在站点 `private/files/`（`supply-copilot-pack-<version>.partNNN`）；
2. 由 `key_test.demand_collaboration.pack_download.get_part` 下发（内部账号可下载、匿名 403）；
3. 客户端通过 `FZH_PACK_METHOD` 覆盖下载方法路径；重新打包时保持 manifest 的 sha256/分卷一致。
