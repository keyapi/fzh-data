---
okf: v0.1
type: Reference
title: 通途每日库存快照 — 离线历史入库 / dry-run（v4 实现说明）
description: 读取 YYYY-MM-DD run 目录，计算 run_id/哈希/完整性/稳定 ID，写入内存或临时 DuckDB；含两日固定 SHA256 基线、27 条测试（14 验收 + 6 补充 + 7 复审回归）与残余风险
date: 2026-10-22
tags: [supply-chain, stock, ingest, dry-run, duckdb, legacy]
---

# 通途每日库存快照 — 离线历史入库（v4）

对应任务书：`../../control/reviews/2026-10-21-stock-ingest-task-v4.md`
方案来源：`../../control/reviews/2026-10-21-stock-daily-diagnosis.md`

本实现**只读本地备份目录**，不访问通途 / EN，不写 `order_store.duckdb`，
不改计划任务，不把原始 JSONL 提交进仓库。默认 `--db :memory:`；写模式必须显式给路径。

## 1. 快速开始

```bash
cd docs/research/supply-chain/2026-10-20/claude/experiments/g1_contract

# 两天 dry-run（内存库，不落盘）
uv run python stock_history_ingest.py \
  --run-dir "D:/Work/库存备份/2026-10-20" --source legacy --dry-run
uv run python stock_history_ingest.py \
  --run-dir "D:/Work/库存备份/2026-10-21" --source legacy --dry-run

# JSON 报告 / 落基线
uv run python stock_history_ingest.py \
  --run-dir "D:/Work/库存备份/2026-10-21" --source legacy --dry-run --json \
  --baseline-out /tmp/baseline-10-21.json

# 写临时库（示例；绝不要指向 order_store.duckdb）
uv run python stock_history_ingest.py \
  --run-dir "D:/Work/库存备份/2026-10-21" --source legacy \
  --db /tmp/stock_history_test.duckdb

# 回滚（按 stock_publish.previous_run_id 重放）
uv run python stock_history_ingest.py --rollback 2026-10-21 \
  --db /tmp/stock_history_test.duckdb [--dry-run]

# 测试
uv run python -m unittest -v test_stock_history_ingest.py
```

依赖：`duckdb`（**尚未写进 pyproject.toml**，执行 `uv pip install duckdb` 或 `uv add duckdb`）。
CLI 退出码：`0` 成功（含 dry-run 校验失败的报告）/ `2` 输入或日期错误 /
`3` 锁被占用 / `4` 拒绝发布或无前序 run 可回滚 / `5` 迁移失败。

## 2. CLI 参数

| 参数 | 说明 |
|---|---|
| `--run-dir PATH` | 含 `manifest.json` 与 `warehouse=*.jsonl` 的 run 目录 |
| `--source legacy\|scheduled\|manual\|unknown` | run 来源；legacy 有封存豁免 |
| `--run-id ID` | 覆盖 run_meta / 目录推导（测试用） |
| `--dry-run` | 只读校验并打印；不写任何 DB |
| `--db PATH` | DuckDB 路径，默认 `:memory:`；写模式禁止 `:memory:` |
| `--rollback DATE` | 按 `previous_run_id` 重放该日期 |
| `--lock-path PATH` | 默认 `<db 所在目录>/stock_history.lock` |
| `--lock-stale-seconds N` | **已废弃**（保留兼容）；OS 文件锁随进程释放，不再按时间抢锁 |
| `--baseline-in PATH` | 比对既有 SHA256 基线，不一致 → 拒绝发布 |
| `--baseline-out PATH` | 写出本次 manifest + 每个 JSONL 的 SHA256 |
| `--json` / `--report PATH` | JSON 输出 / 另存 |

`--dry-run` 永不创建或写入 DB 文件：给了已存在的 `--db` 会以 **read-only** 打开用于
比较已发布指针；否则使用内存库。因此 dry-run 的 `publish.action` 在同一台机器上
通常是 `publish`（内存库没有历史指针）。

## 3. run 目录契约

```
<run_dir>/
  manifest.json                  # 必需；snapshot_date / snapshot_at / warehouses[]
  warehouse=<id>_<name>.jsonl    # 每个仓一个文件，可缺失/为空
  run_meta.json                  # 非 legacy 必需（run_id / started_at / ended_at / exit_code / trigger / 哈希）
  .sealed                        # 非 legacy 必需；最后写入的封存清单
```

- **manifest 里的绝对路径只是提示**。历史 10-21 的 manifest 指向
  `D:\Work\fzh-inventory\...`，实际文件在 `D:\Work\库存备份\...`；本实现按
  basename 在 `--run-dir` 内解析，manifest 路径不参与 I/O。
- 非 legacy（scheduled/manual/unknown）**必须**有 `run_meta.json` 的 `run_id`
  （或目录名 `run=<id>` / `--run-id`）与 `.sealed`；缺封存 → `integrity_ok=false`，
  不进入发布流程。legacy 允许无 `.sealed`，记 `sealed=false, sealing_exemption='legacy'`。
- `.sealed` 至少包含 `manifest_sha256` 与覆盖 **manifest + 全部已存在 JSONL** 的
  `files` 哈希；封存清单缺文件、哈希不符、或目录里多出未列文件都会拒绝发布。
- `run_meta.json` 若带 `manifest_sha256` / `files[].sha256`，同样逐项校验。

## 4. run_id 与可重复性

| 来源 | run_id |
|---|---|
| legacy | `legacy-YYYYMMDDTHHMMSS-<manifest_sha8>`，时间取 `snapshot_at` 的 **Asia/Shanghai 墙钟** |
| scheduled / manual / unknown | `run_meta.run_id`（或 `run=<id>` 目录名 / `--run-id`） |

同一 legacy 目录重复导入得到同一 run_id。**同一 run_id 的重新导入必须与首次入库
的哈希基线（snapshot_date + manifest SHA256 + 每个 JSONL 的 SHA256）完全一致**：
一致时幂等（保留首次 `ingested_at`，业务行不变，验收 1）；任何变化——哪怕
manifest 字节没变、只改了 JSONL——都写 `reimport_changed_rejected` 事件并抛
`DataIntegrityError`，**绝不先删后插**（复审修复 ①）。只读 dry-run 指向已有
`--db` 时也会返回 `action=reject, reason=reimport_changed`，与写模式一致。
哈希相同但校验结论变坏（如 `--baseline-in` 外部基线不符）的重导同样拒绝，保护
覆盖**所有已存 run**（不只当前发布 run），删除前保留旧行/元数据/指针（复审修复 ⑦，见 §8）。
legacy run_id 会随 manifest
哈希变化；只改 JSONL 不改 manifest 时 run_id 不变，但重导会被指纹挡住，
`--baseline-in` 与 `.sealed` 也会报哈希异常（验收 9）。

## 5. 三级完整性（不互相冒充）

- `batch_complete`（仓）：manifest `complete=true`、未 `truncated`、无 `error`、
  文件存在、`bad_rows=0`、manifest `rows` 与文件行一致、行内 `warehouseIdKey`
  与 manifest 一致、无重复键数值冲突。
- `scope_complete`：manifest 请求的仓集合全部 `batch_complete`。
- `run_complete`：`scope_complete` **且** `manifest.complete=true`。
  `manifest.complete` 缺失时只能判 **unknown → false**，绝不能用 `scope_complete`
  冒充"全仓完整"（复审修复 ②；“全部启用仓”以 manifest 为代理，本任务不查询通途仓库清单）。

`warehouse_scope` 原样记录 manifest 请求的仓 ID 数组；`scope_coverage` 记录完整仓数。

## 6. 空仓 vs 未知

| 情况 | `stock_run_warehouse.complete` | 行 | 说明 |
|---|---|---|---|
| 抓取成功、0 行 | `true` | 0 | 有效空仓，不写 0 观测 |
| 缺文件 / 抓取失败 | `false` | 0 | `unknown`，不写 0、不进断货统计 |
| 失败仓留下部分文件（10-20 退货仓 400 行） | `false` | 400 | 入库但 `batch_complete=false`，永不 `stockout_observed` |

`stock_run_warehouse.complete` 存的是 `batch_complete`（与 `stock_history.batch_complete` 一致）。

## 7. 稳定 ID、别名与冲突

- 主键：`stock_history(snapshot_date, warehouse_id, goods_id)`；
  `goods_sku` / `warehouse_name` 仅展示。
- 同 run 同 `(warehouse_id, goods_id)` 重复：四个数值桶完全一致 → 去重并计
  `duplicate_rows`；任一不同 → **整 run 拒绝发布**，不选任一条候选值。
- 去重前的 `(goods_id, goods_sku)` 写入 `stock_id_observation`；发布时按**日期正序
  重建** `stock_id_history`（复审修复 ④）：某天名字缺席才把 `valid_to` 截止到当天，
  因此反向导入（先新后旧）不会产生 `valid_to < valid_from`；同日新 run 替换旧 run
  后，旧 run 的别名不再属于当前发布事实；回滚重放会把它重新建回来。
- 同一 `goods_sku` 在同一天指向多个 `goods_id` → 拒绝发布（同 run 内直接拒绝；
  跨 run 与当前已发布 run 冲突时按同一总序裁决，见 §8），
  证据保留在 `stock_run.integrity_errors` / `stock_ingest_event`。
- 跨日改名按 ID 聚合，历史查询不受影响。

## 8. 同日多 run 的选择与发布指针

偏好键（越大越优，**总序**，与导入顺序无关）：

```
run_complete > scope_complete > scope_coverage > ended_at(NULL 最后) > run_id 字典序最大
```

- 候选优于已发布 → 单事务替换该日 `stock_history` 并写
  `stock_publish(snapshot_date, run_id, published_at, previous_run_id=旧 run)`。
- 候选不优 → `skip`，只留在 `stock_run` / `stock_history_run` 作审计。
- 候选与已发布相同 → `already`。
- 完整性/同 run 别名/哈希失败 → `reject`，不写发布指针；写模式落 `publish_rejected` 事件。
- **跨 run 别名冲突按同一总序裁决**（复审修复 ③）：候选与当前已发布 run 的
  SKU→goods_id 映射冲突时，候选更优 → `publish`（整日行被原子替换，冲突自然消失，
  reason=`candidate_outranks_published_with_alias_conflict`，落
  `alias_conflict_superseded` 事件）；候选不优 → `reject`
  （reason=`alias_conflict_with_published`）。因此无论导入顺序如何，最终赢家唯一。
- **最好可用即可发布**：若某日只有不完整 run，它会被发布，但 `run_complete=false`
  且报告 `complete_day=false`；一旦出现完整 run 就原子切换。这样分析侧能显式看到
  “当前发布的是不完整日”，而不是把 400 行部分数据误当完整日。

`previous_run_id` 记录的是**实际被替换的上一个 run**，因此依赖导入顺序；发布结果
不依赖顺序。回滚：

```
--rollback DATE → 读 previous_run_id → 从 stock_history_run 重放该 run
                → 发布指针改回旧 run，previous_run_id 指向刚被回滚的 run（可再切回）
```

回滚逐行内容与 previous run 完全一致（验收 11）。previous run 为 **0 行**时按
批次有效性判断（复审修复 ⑤）：`run_complete=true`（全部仓 `batch_complete` 且
`manifest.complete=true`）的合法空仓可以回滚为 0 行；批次不完整则
`RollbackUnavailable`，发布指针不动。

**失败重导保护覆盖所有已存 run**（复审修复 ⑦）：同一 run_id 重新读入时，若内容
哈希与首次基线一致但校验失败（典型：`--baseline-in` 外部基线不符），无论该 run
是否仍是当前发布指针，都在删除前拒绝（`DataIntegrityError` + `reimport_rejected`
事件），旧 `stock_history_run` 行、`stock_run` 元数据与 `stock_publish` 指针全部
保持不变。这是回滚可用的前提：A 发布 → B 替换 → 重导 A（哈希相同、基线失败）
之后，回滚仍能按 `previous_run_id` 重放到完好的 A。

## 9. 表结构（v2 迁移）

| 表 | 作用 |
|---|---|
| `stock_run` | run 元数据、来源、封存、三级完整性、哈希、完整性错误、`warehouse_scope`、`integrity_ok` |
| `stock_run_warehouse` | 每仓文件哈希、行数、bad/dup、`batch_complete`、错误 |
| `stock_history_run` | **每个 run 的去重行**（审计 + 回滚重放）；`stock_history` 只存已发布日期的物化行 |
| `stock_history` | 已发布行，PK `(snapshot_date, warehouse_id, goods_id)`，带 `run_id` / `stockout_observed` |
| `stock_id_observation` | 去重前别名观测（run 级） |
| `stock_id_history` | 别名/改名生效区间（不覆盖旧名） |
| `stock_publish` | 每日发布指针 + `previous_run_id` |
| `stock_ingest_event` | 拒绝/回滚/重新导入等证据事件 |
| `schema_migrations` | 版本化迁移记录 |

视图：

- `v_stock_history_analysis`：已发布行，**排除 `is_test`**。
- `v_stockout_observed`：仅 `batch_complete=true AND available=0` 的已发布行。
- `v_stock_by_sku`：唯一允许的聚合口径，按 `(snapshot_date, warehouse_id, goods_id)` 分组。
- `v_stock_run_status`：run 完整性与是否已发布。

`stock_history_run` / `stock_id_observation` 是对 v3 表结构的必要补充：
没有前者无法在“旧完整行被替换”后按 `previous_run_id` 回滚（验收 11）；
没有后者，数值一致的去重会丢掉同一 ID 的第二别名（验收 8）。

## 10. 测试商品 / UOM / 断货

- `goodsSku == "TEST-1"` → `is_test=true`；默认分析视图排除。
- 每行 `uom_basis='unknown'`（备份无 UOM 字段）。`sum_available()` 在存在 unknown
  行时抛 `UomBasisError`；只允许 `v_stock_by_sku` 的按 SKU 聚合。
- `stockout_observed=true` 仅当：该仓 `batch_complete=true`、`available=0`、且该 run
  已发布（物化时计算）。部分批次/未知仓永不标记断货。

## 11. 锁、崩溃恢复与迁移

- 锁文件：`<db 目录>/stock_history.lock`，用 **OS 文件锁**独占
  （Windows `msvcrt.locking`/LockFile，POSIX `fcntl.flock`）；内容含
  `pid/host/token/created_at`，仅作诊断（复审修复 ⑥）。
- 第二个进程：直接 `LockHeld`（CLI 退出码 3），**在打开 DB 之前**就拒绝。
- 崩溃遗留：进程退出（含崩溃/被强杀）时内核自动释放 OS 锁，下一次直接可获取；
  **活进程持锁再久也不会因为 `--lock-stale-seconds` 超时被抢**。
- 锁文件**不删除**：删除会让两个进程各自锁住不同的 inode，制造假并发；
  `release()` 解锁并关闭句柄即可。旧版本遗留的纯文本锁（无 OS 锁）可直接接管。
- 迁移：`schema_migrations` + 每版本一个事务；任一条 SQL 失败整版本 `ROLLBACK`
  （DuckDB 2.0 事务性 DDL），已成功版本保留；重复 `migrate` 幂等。

## 12. 跨日归属

- `snapshot_at` 无偏移按 `+08:00` 解释；`Z`/`±HH:MM` 换算到 Asia/Shanghai 后取日期。
- `snapshot_at` 日期必须等于 `manifest.snapshot_date`，且目录名若是 `YYYY-MM-DD`
  必须等于该日期，否则 `DateAttributionError`（退出码 2）。
- 跨日补跑应落在 `snapshot_at` 所属日期的目录；把 23:30 的 run 放进次日目录会被拒绝。

## 13. 两天固定 SHA256 基线

**2026-10-20**（manifest `186498757a79b1325edff8314d90208ca616a9955393317366b4d52e81f57828`）

| 文件 | SHA256 |
|---|---|
| `manifest.json` | `186498757a79b1325edff8314d90208ca616a9955393317366b4d52e81f57828` |
| `warehouse=6464013595201610250000002538_美东-CENTRADE.jsonl` | `ee92d7c0958413d74c0f710566815b72febc5ca3f6e2975fac6cc94acf51b350` |
| `warehouse=6464013595202111220000516093_波兰-FZHPoland-covers.jsonl` | `de3d17b8c8066fa4f6864abd5b1b5d72ce87c3d3f8603dcc192fde7cd643590d` |
| `warehouse=6464013595202112150000528878_多渠道仓库.jsonl` | `a338228b4842d47ad48b4339e497b3dd91b3e291e4eb48c473153b928a7df86d` |
| `warehouse=6464013595202309080001023362_美中-FZH-DANEEY.jsonl` | `9414e8e2d4ce751f3e026fb5a1d331c95be77e4ed9d195bd58a5578d2fed3d8b` |
| `warehouse=6464013595202406110001248096_美中-FZH-DANEEY-退货产品仓.jsonl` | `622d92fec5e37a043514e8ed26a75f479e85a82a1780782d7dc8623213c9b105` |
| `warehouse=6464013595202504270001401335_WayfairCG-Cranbury仓.jsonl` | `eb0d0127e08292f7ee673d630d8197d9f67b73d4f0d4a1a5f9dbc49dc2b18e4e` |
| `warehouse=6464013595202504270001401336_WayfairCG-Perris仓.jsonl` | `917a4d0b68809163ecb3366f9f9783649149de2bd786c989c5c25be3b33ca5e5` |
| `warehouse=6464013595202504270001401339_WayfairCG-Romeoville仓.jsonl` | `8075a3dccf5fbfd8525f332638b841c810f32146fad02750dc84fff1e5bc333c` |
| `warehouse=6464013595202504270001401340_WayfairCG-PortWentworth仓.jsonl` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `warehouse=6464013595202504270001401341_WayfairCG-McDonough仓.jsonl` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `warehouse=6464013595202508050001504926_星链海外仓.jsonl` | `111ec1b748382351c9fd77f051427c7ad6b980bf4ae018f919b3ae0fe8916d8a` |
| `warehouse=6464013595202602050001684076_大件云仓.jsonl` | `34dc35b4a4c50c293df89abb43d79de33f5614560ccbf98d7cc2421600e5b1f4` |
| `warehouse=6464013595202608140001856736_美东-CENTRADE-退货产品仓.jsonl` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `warehouse=6464013595202608140001856741_波兰-FZHPoland-退货产品仓.jsonl` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

**2026-10-21**（manifest `4dd9bbfde0ffdcb6df64e3dc1c8761a7226a8053d931d29dad62aa77274b2ed7`）

| 文件 | SHA256 |
|---|---|
| `manifest.json` | `4dd9bbfde0ffdcb6df64e3dc1c8761a7226a8053d931d29dad62aa77274b2ed7` |
| `warehouse=6464013595201610250000002538_美东-CENTRADE.jsonl` | `d92993b290dcf670c4a3ec7ee7721a6b38745e4d773ba800ba8892d413e6991b` |
| `warehouse=6464013595202111220000516093_波兰-FZHPoland-covers.jsonl` | `ed2c00f4edf5bcbcae8d55908f553960c476fa8633c28f3f9a50fdaaebe30f0d` |
| `warehouse=6464013595202112150000528878_多渠道仓库.jsonl` | `a338228b4842d47ad48b4339e497b3dd91b3e291e4eb48c473153b928a7df86d` |
| `warehouse=6464013595202309080001023362_美中-FZH-DANEEY.jsonl` | `cfc51a12983155b932a6abfcac7ca075bae698e8ce3db5ee56ff465576c3b8c0` |
| `warehouse=6464013595202406110001248096_美中-FZH-DANEEY-退货产品仓.jsonl` | `1bb757726b1ddef15cae97da072798be9a24f9c0cf20f9fdbf5efdd2dfb773a6` |
| `warehouse=6464013595202504270001401335_WayfairCG-Cranbury仓.jsonl` | `eb0d0127e08292f7ee673d630d8197d9f67b73d4f0d4a1a5f9dbc49dc2b18e4e` |
| `warehouse=6464013595202504270001401336_WayfairCG-Perris仓.jsonl` | `917a4d0b68809163ecb3366f9f9783649149de2bd786c989c5c25be3b33ca5e5` |
| `warehouse=6464013595202504270001401339_WayfairCG-Romeoville仓.jsonl` | `8075a3dccf5fbfd8525f332638b841c810f32146fad02750dc84fff1e5bc333c` |
| `warehouse=6464013595202504270001401340_WayfairCG-PortWentworth仓.jsonl` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `warehouse=6464013595202504270001401341_WayfairCG-McDonough仓.jsonl` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `warehouse=6464013595202508050001504926_星链海外仓.jsonl` | `111ec1b748382351c9fd77f051427c7ad6b980bf4ae018f919b3ae0fe8916d8a` |
| `warehouse=6464013595202602050001684076_大件云仓.jsonl` | `34dc35b4a4c50c293df89abb43d79de33f5614560ccbf98d7cc2421600e5b1f4` |
| `warehouse=6464013595202608140001856736_美东-CENTRADE-退货产品仓.jsonl` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `warehouse=6464013595202608140001856741_波兰-FZHPoland-退货产品仓.jsonl` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

空文件哈希 `e3b0c442...b855` 是 SHA256 of empty input。
直接比对：`--baseline-in <(该日 --baseline-out 的文件)>`；不一致会写
`baseline_*_mismatch` / `baseline_file_unlisted` 并拒绝发布。

## 14. 两天 dry-run 对账结果（2026-10-21 实测）

| 项 | 2026-10-20 | 2026-10-21 |
|---|---:|---:|
| run_id | `legacy-20261020T181947-18649875` | `legacy-20261021T094623-4dd9bbfd` |
| snapshot_at (+08) | 18:19:47 | 09:46:23 |
| 仓数 / 完整仓 | 14 / **13** | 14 / **14** |
| 文件行 / 去重后 | 5,192 / 5,192 | 5,314 / 5,314 |
| manifest 行合计 | 4,792（失败仓无 rows） | 5,314 |
| 重复 / 坏行 | 0 / 0 | 0 / 0 |
| `scope_complete` | **false** | true |
| `run_complete` / `complete_day` | **false / false** | true / true |
| `integrity_ok` | true | true |
| TEST-1 行 | 2（分析视图后 5,190） | 2（分析视图后 5,312） |
| 发布动作 | `publish`（当日唯一，标不完整） | `publish` |

失败仓：`美中-FZH-DANEEY-退货产品仓`，manifest `complete=false`、`rows=null`、
`URLError 10060`；磁盘上 400 行 → `batch_complete=false`，`rows_read=400`，
不进断货统计。其余 13 仓 `manifest.rows == 文件行`。

## 15. 14 条验收对应测试

| # | 验收 | 测试方法 |
|---|---|---|
| 1 | 同 run 重复导入不变 | `test_a01_reimport_same_run_is_idempotent` |
| 2 | 10-20 不完整、13/14 完整、不发布为完整日 | `test_a02_real_2026_10_20_incomplete_day` |
| 3 | 10-21 5,314 行 / 14 仓 / run_complete | `test_a03_real_2026_10_21_complete_day` |
| 4 | 完整↔不完整、反序导入 | `test_a04_complete_then_incomplete_keeps_complete` |
| 5 | 不完整→完整原子切换、无旧行残留 | `test_a05_incomplete_then_complete_atomic_switch` |
| 6 | 空仓 complete vs 缺文件 unknown | `test_a06_empty_vs_unknown` |
| 7 | 平局按 run_id、反序一致 | `test_a07_multirun_tie_break_is_order_independent` |
| 8 | 别名/ID 冲突拒绝并留证据 | `test_a08_alias_and_duplicate_conflicts_rejected_with_evidence` |
| 9 | 哈希异常拒绝 | `test_a09_hash_anomaly_rejected` |
| 10 | 跨日/目录冲突 | `test_a10_cross_day_attribution` |
| 11 | 回滚逐行一致 | `test_a11_rollback_replays_previous_run_row_by_row` |
| 12 | 并发锁 + 崩溃恢复 + 活进程超时不被抢 | `test_a12_lock_concurrency_and_crash_recovery` |
| 13 | 迁移失败回滚 | `test_a13_migration_failure_rolls_back` |
| 14 | TEST-1 排除 + 禁止跨 SKU 求和 | `test_a14_test_sku_excluded_and_no_cross_sku_sum` |

另有 6 条补充用例：非 legacy 缺封存拒绝、manifest 行数不符拒绝、legacy run_id
确定性、CLI 基线往返（正常 → 篡改）、manifest 绝对路径忽略、跨 run 已发布别名冲突
（按总序裁决）。

### 15.1 2026-10-22 代码复审六项回归

| # | 复审问题 | 回归测试 |
|---|---|---|
| ① | 重导未比旧哈希、先删后插 | `test_r1_reimport_with_changed_file_hash_is_rejected` |
| ② | 缺 `manifest.complete` 仍判全仓完整 | `test_r2_missing_manifest_complete_flag_is_unknown` |
| ③ | 别名冲突先到先占、反序赢家不同 | `test_r3_alias_conflict_is_deterministic_regardless_of_order` |
| ④ | 反序导入 `valid_to < valid_from`；回滚不恢复区间 | `test_r4_alias_intervals_are_date_rebuilt_and_rollback_restores` |
| ⑤ | 合法零行空仓不能回滚 | `test_r5_zero_row_empty_previous_run_is_rollbackable` |
| ⑥ | 活进程仅超时便被抢锁 | `test_r6_live_process_lock_is_not_stolen_after_timeout`（+ `test_a12`） |
| ⑦ | 被替换的 run 重导失败会毁掉回滚目标 | `test_r7_failed_reimport_after_supersede_keeps_rollback_target` |

共 **27 条**；其中 2 条真实数据用例在 `D:/Work/库存备份` 不存在时 `skip`。

## 16. 已知限制 / 残余风险

1. **DuckDB 未在 pyproject 声明**：需手动 `uv pip install duckdb`；换机器会缺依赖。
2. **“全部启用仓”用 manifest 代理**：不以通途实时仓库清单校验；若备份脚本漏抓
   某个启用仓且 manifest 也漏记，`run_complete` 仍可能为 true。
3. **legacy 文件可变**：没有 `.sealed`；同一库内重导已被哈希指纹挡住，但**首次**
   导入仍靠 `--baseline-in` 外部基线发现漂移。本次基线已记录在 §13，需要人/任务在
   导入时传入。
4. **10-20 的 400 行部分数据会被物化**（若该日只有它）：`batch_complete=false`
   且永不标记断货，但按仓求和的消费者必须自己过滤 `batch_complete`；
   `v_stock_by_sku` 未强制过滤（保留原始事实）。
5. **`previous_run_id` 与导入顺序相关**：发布结果顺序无关，但回滚目标取决于实际
   替换链；多次回滚/切换后只保留一条前序指针，不构成完整历史（事件表可审计）。
6. **goodsSku → EN 物料 / 仓库映射未验证**：本任务只处理通途 ID 与展示名，
   `sku_map`/`warehouse_map` 仍是未决项。
7. **无 UOM**：`uom_basis='unknown'`，任何跨 SKU/品类求和都被 `sum_available` 拒绝；
   目前没有“已知 UOM”的写入路径。
8. **断货语义受限**：每日快照无法定位日内断货；`available=0` 只是观测，
   `stockout_observed` 不含“本应有多少需求”。
9. **05:17 是否运行仍待证**：两天数据只证明 10-20 18:19 与 10-21 09:46 的 run；
   历史目录可能被同日覆盖，封存改造尚未落地到计划任务。
10. **legacy run_id 冲突**：同一秒 + 同一 manifest 哈希的两次不同运行会得到同一
    run_id（概率极低）。同 run_id 但内容不同的重导会被指纹拒绝（复审修复 ①），
    不会静默覆盖；legacy 仍不支持同日多份同内容 run 的区分。
11. **dry-run 的内存发布决策**不包含“与线上已发布 run 的比较”，除非 `--db` 指向
    已有文件（只读）；跨进程并发由锁保护，但 dry-run 不取锁。
12. **跨 run 别名冲突只与“当前已发布”run 比对**：未被发布的历史/拒绝 run 不会
    永久阻断后续导入。冲突由总序裁决，最终赢家与导入顺序无关，但事件流里可能是
    “后来者发布”或“后来者被拒”，取决于候选与已发布 run 的优劣（复审修复 ③）。
13. **OS 文件锁依赖本地文件系统语义**：SMB/NFS 上 `flock`/LockFile 的行为可能不同；
    锁文件默认放在 DB 同目录，建议 DB 与锁都在本地盘。
