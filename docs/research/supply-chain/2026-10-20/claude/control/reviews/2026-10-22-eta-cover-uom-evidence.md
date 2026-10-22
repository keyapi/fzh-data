---
okf: v0.1
type: Review
title: ETA / Cover / UOM / 在途证据梳理（B v2，只读）
date: 2026-10-22
owner: claude-worker
version: v2
supersedes: v1（同路径 commit b2049efe；evidence sha256 ad8cc887…）
scope_primary: 5 trace SKUs（trace_examples.json/.md）
scope_extension: 10 expand10 SKUs（g1b_en_top_1..9 + g1b_en_rr2）
verdict: primary ETA blocker 1 / cover scenario 3；extension ETA blocker 6 / cover scenario 4
---

# ETA / Cover / UOM / 在途证据梳理（B v2）

> **本版按独立复审的 5 条整改重做**：① 主口径回到 5 个 trace SKU，10 SKU 只作
> 明确标注的扩展；② JSON 缺失与 0 分开（无映射写 `null` + `cover_observed=false`）；
> ③ 补 PO 行键、Cover 仓键、逐文件 SO 行数与查询定义/源哈希；④ 软化
> `max(intransit,PO)`、UOM 换算、`open_qty=0` 等结论；⑤ 交付 v2 证据 JSON。
>
> **结论（分两套人口，不合并）**：
> - **主口径 5 个 trace SKU**：ETA **1 个 blocker**（KS0316，PO021715 未结 10，无日期）；
>   在途 5/5 可观测；Cover 2 个可观测（含 KS0316 的 43 件）、3 个无映射属 scenario；
>   UOM 5/5 为条件结论（库存单位未证）。
> - **扩展 10 个 expand10 SKU**：ETA **6 个 blocker**（13 行 / 1,465 件 / 6 个 PO）；
>   在途 10/10 可观测；Cover 6 个观测为 0、4 个无映射属 scenario；UOM 10/10 为条件结论。
>
> 本轮 0 次生产访问；`order_store.duckdb` 以 `read_only=True` 打开，运行前后
> sha256 均为 `25579c5d…`；未写入、未改表；未估算任何缺失值。

## 1. 范围：两套人口，明确不合并

任务书主口径点名 **5 个 trace SKU**（`D:/Work/fzh-order-store/trace_examples.json/.md`）。
v1 把任务书里同时提到的 10 个 EN 快照 SKU 当成了 10 SKU 人口，这是本轮返修的第一条。
v2 的处理：

| 口径 | 人口 | 来源 | 用途 |
|---|---|---|---|
| **主口径（primary）** | **5 个 trace SKU** | `trace_examples.json/.md`（5 行，SKU×仓） | 本报告主矩阵 |
| **扩展口径（extension）** | **10 个 expand10 SKU** | `g1b_en_top_1..9.json` + `g1b_en_rr2.json`，经 `sku_map` 映射 | 单独成节，**不并入主口径** |
| 重叠 | `KS0001-QDKTR-100-DEEPGREY` | 两边都有 | 不重复计数、不合并分母 |

主口径 5 个（trace 的仓即锚点仓）：

| # | SKU | trace 锚点仓 | ship_type | pool_note |
|---:|---|---|---|---|
| 1 | KS0001-QDKTR-100-DEEPGREY | 美中-FZH-DANEEY | 皮壳 | — |
| 2 | KS0230-WGMSRKQCLG-60-WHITE | 美中-FZH-DANEEY | 成品 | — |
| 3 | KS0153-KQCLG-78-WHITEKHAKI | 波兰-FZHPoland-covers | 半成品 | — |
| 4 | KS0316-HLR-55-LINEPURPLE | 美中-FZH-DANEEY | 成品 | `cover_only` |
| 5 | KS0249-QRJL-153-QIRUOJINLAN | 美东-CENTRADE | 皮壳 | — |

> trace 包本身是原型（`trace_examples.md` 首行写明「未验收，不用于下单」）。
> 主口径只回答「现有证据能支持什么」，不把 trace 当业务承诺。

扩展口径 10 个 SKU 的映射（与 v1 相同，保留以便复核）：

| # | 客户码 | item_code | 来源快照 |
|---:|---|---|---|
| 1 | CENCord995-DKGrey-97 | KS0001-QDKTR-100-DEEPGREY | top_1 |
| 2 | CEN003-DPBLUE-100 | KS0001-QDKTR-100-DEEPBLUE | top_2 |
| 3 | C/Linen-Natural-100-688-wow | KS0001-XMMBS-100-HEMPNATURAL | top_3 |
| 4 | C/Cord-DKBlue-100-713-wow | KS0001-CMKTR-100-DEEPBLUE | top_4 |
| 5 | C/Linen-Natural-153-688-wow | KS0001-XMMBS-153-HEMPNATURAL | top_5 |
| 6 | C/Velvet-Grey-100-705-wow | KS0001-PR-100-GREY | top_6 |
| 7 | C/Cord-Grey-100-710-wow | KS0001-CMKTR-100-GREY | top_7 |
| 8 | C/Linen-White-100-662-WOW | KS0001-CMM-100-WHITE | top_8 |
| 9 | TT0000671K0063721 | KS0001-HLR-100-OFFWHITE | top_9 |
| 10 | C/Linen-Natural-194-688-wow | KS0001-XMMBS-194-HEMPNATURAL | rr2 |

## 2. 判定口径与「缺失 ≠ 0」

| 判定 | 含义 |
|---|---|
| `evidence_present` | 有名表/字段/行且非空，直接回答该维度；使用它不需要未证假设（或该维度不适用） |
| `scenario` | 有可引用值，但使用它需要一条写明的假设，假设可被业务接受或推翻 |
| `blocker` | 关键字段/行缺失或全空，本地数据无法给出该维度值，必须外部输入 |

**缺失 vs 0（本轮硬规则）**：

- 没有 cover 别名行、也没有 `item_cover_stock` 行 → `cover_observed=false`，
  `alias_available_sum=null`、`item_cover_stock_available_sum=null`；**不写 0**。
- 只有别名行/`item_cover_stock` 行实际存在且值为 0，才写 `observed_zero=true`。
- `replenishment_pool.cover_available` 的 0 是池输出列，单独放在
  `pool_cover_available_raw`；对无别名的 SKU 它是「缺失推导值」，不是观测。
- **无 PO 行**只说明「本地 `tongtool_po` 快照内没有该 SKU 的行」，不等于全公司没有采购；
  这类 `evidence_present` 都带 `qualifier = scope = local tongtool_po snapshot`。

**ETA 的三种类型**（本轮显式区分）：

| 类型 | 定义 | 本轮状态 |
|---|---|---|
| `planned` | `purchase_date + item_attr.lead_days` 推导 | 未获业务书面确认，**不计算、不使用**；主口径 4/5 的 `lead_days=0`，连推导路径都没有 |
| `confirmed` | `tongtool_po.will_arrive_date`（供应商/PO 承诺） | 全库 **0/524 非空**；主口径未结行 0/1 有值 |
| `usable` | 可直接进入预测/补货模型的日期 | 无 confirmed、planned 未授权 → **null** |

**供给公式 `available + max(intransit, PO)` 是条件的，不是已证安全**：

- 条件：`intransit` 必须是同一 SKU×仓 open PO 的**子集**，`max()` 才不重复计。
- 观测到的只是必要条件：同仓 `open_qty >= intransit`（主口径 KS0316 波兰 10≥10；
  扩展口径 6 个仓全部成立）。
- 必要条件 ≠ 充分条件；两表没有共同单据键，逐笔归属未证。JSON 里
  `max_basis.condition_status = "not_proven"`。

**UOM 换算也是条件的**：

- 需求侧/BOM 侧是 `个`，但 `stock_latest` 无 uom 列、`stock_history.uom_basis`
  15,820/15,820 全 `unknown`。
- 因此只能写「**若**库存单位=个，则 1:1 不需要换算」，不能写「不需要换算」。
  JSON 里 `conversion_status = "conditional"`。

**`open_qty=0` 不证明已收货**：

- 本次 21 条已结行（扩展 19 + 主口径 2）`in_quantity == quantity` 且 `status='3'`，
  这与收货一致；但 `status` 码在本库没有字典，且 `open_qty=0` 也可能来自取消/关闭/调整。
- JSON 统一写 `receipt_proven=false`，不把「已结」翻译成「已入库」。

## 3. 主口径：5 个 trace SKU × 4 判定矩阵

| # | SKU | ETA | 在途 | Cover | UOM |
|---:|---|---|---|---|---|
| 1 | KS0001-QDKTR-100-DEEPGREY | ✅ evidence_present（本地无 PO 行） | ✅ evidence_present（0） | ✅ evidence_present（别名桶 0） | ⚠️ scenario（条件换算） |
| 2 | KS0230-WGMSRKQCLG-60-WHITE | ✅ evidence_present（本地无 PO 行） | ✅ evidence_present（0） | ⚠️ scenario（**无映射，null**） | ⚠️ scenario（需求单位未知） |
| 3 | KS0153-KQCLG-78-WHITEKHAKI | ✅ evidence_present（本地无 PO 行） | ✅ evidence_present（0） | ⚠️ scenario（**无映射，null**） | ⚠️ scenario（需求单位未知） |
| 4 | KS0316-HLR-55-LINEPURPLE | ⛔ **blocker**（PO021715 / 10 件 / 无日期） | ✅ evidence_present（10） | ✅ evidence_present（43） | ⚠️ scenario（条件换算） |
| 5 | KS0249-QRJL-153-QIRUOJINLAN | ✅ evidence_present（本地无 PO 行） | ✅ evidence_present（0） | ⚠️ scenario（**无映射，null**） | ⚠️ scenario（需求单位未知） |

**主口径计数**：ETA blocker **1** / evidence_present **4**；在途 evidence_present **5**
（其中「在途↔PO 逐笔关系」scenario **1**，即 KS0316）；Cover evidence_present **2** /
scenario **3**；UOM scenario **5**（需求侧可观测 1/5，库存侧可观测 0/5）。

### 3.1 逐 SKU 证据索引（表.字段 = 值）

| SKU | ETA（本地快照） | 在途（`stock_latest`） | Cover | UOM |
|---|---|---|---|---|
| QDKTR-100-DEEPGREY | `tongtool_po`: **0 行** → 无未结 | 5 行，`intransit=0`（美中/波兰/美东/Wayfair） | 别名 `TT0000995K0010982-Cover@波兰`：`available=0`（**观测 0**）；`item_cover_stock`: 0 行 | `bom.uom=个`；`bom_item` 2 行 `个`；EN top_1 的 19 SO 行 `uom=个`；`stock_history.uom_basis=unknown` |
| KS0230-WGMSRKQCLG-60-WHITE | `tongtool_po`: **0 行** | 4 行，`intransit=0`（美中/波兰） | 无别名、`item_cover_stock` 0 行 → **null / cover_observed=false** | `bom.uom=个`；`bom_item` 2 行 `个`；无本地 EN SO；库存 unknown |
| KS0153-KQCLG-78-WHITEKHAKI | `tongtool_po`: **0 行** | 5 行，`intransit=0`（波兰/美中/美东） | 无别名、`item_cover_stock` 0 行 → **null** | `bom.uom=个`；`bom_item` 2 行 `个`；无本地 EN SO；库存 unknown |
| KS0316-HLR-55-LINEPURPLE | 3 行；1 行未结：`PO021715@波兰 open_qty=10`，`will_arrive_date=NULL` | 3 行（全是 `-Cover`）：波兰 `10`、美中 `0`、成品仓 `0` | `item_cover_stock`: 波兰 15 / 美中 28；别名 3 行合计 **43**；`supply_in_rop=0`（`cover_only`） | `bom.uom=个`；`bom_item` 1 行（PK#）`个`；无本地 EN SO；库存 unknown |
| KS0249-QRJL-153-QIRUOJINLAN | `tongtool_po`: **0 行** | 1 行，`intransit=0`（美东） | 无别名、`item_cover_stock` 0 行 → **null** | `bom.uom=个`；`bom_item` 2 行 `个`；无本地 EN SO；库存 unknown |

> 主口径的 4 个 SKU（除 QDKTR）在本地 EN 快照里没有对应文件，所以
> `demand_uom_observed=false`；不是「需求单位=个」的观测，只是「本地没有」。

### 3.2 主口径的 PO 行键（KS0316，全部 3 行）

行键 = `(ponum, goods_sku, warehouse)`；3/3 唯一。

| PO 行键 | quantity | in_quantity | open_qty | status | purchase_date | will_arrive_date |
|---|---:|---:|---:|---|---|---|
| `PO021688\|TT0031128K00638172-Cover\|美中-FZH-DANEEY` | 15 | 15 | 0 | 3 | 2026-06-04 10:21 | NULL |
| `PO021703\|TT0031128K00638172-Cover\|波兰-FZHPoland-covers` | 10 | 10 | 0 | 3 | 2026-07-25 10:47 | NULL |
| `PO021715\|TT0031128K00638172-Cover\|波兰-FZHPoland-covers` | 10 | 0 | **10** | 0 | 2026-09-09 09:19 | **NULL** |

- 唯一 ETA blocker 是 `PO021715`；另 2 行 `open_qty=0`，**不代表已收货**（见 §2）。
- 注意：KS0316 的 trace 锚点仓是美中，未结 PO 在**波兰**；报告按 SKU 级 ETA 判 blocker，
  同时保留仓键，避免把「美中无未结」误读成「SKU 无未结」。

### 3.3 主口径的 Cover 仓键

| SKU | 观测源 | 仓键 | 值 |
|---|---|---|---|
| QDKTR-100-DEEPGREY | `stock_latest` 别名 | `KS0001-QDKTR-100-DEEPGREY\|波兰-FZHPoland-covers\|TT0000995K0010982-Cover` | `available=0`, `intransit=0`（**观测 0**） |
| KS0316 | `item_cover_stock` | `KS0316-HLR-55-LINEPURPLE\|波兰-FZHPoland-covers` | 15 |
| KS0316 | `item_cover_stock` | `KS0316-HLR-55-LINEPURPLE\|美中-FZH-DANEEY` | 28 |
| KS0316 | `stock_latest` 别名 | `KS0316-HLR-55-LINEPURPLE\|波兰-FZHPoland-covers\|TT0031128K00638172-Cover` | 15 |
| KS0316 | `stock_latest` 别名 | `KS0316-HLR-55-LINEPURPLE\|美中-FZH-DANEEY\|TT0031128K00638172-Cover` | 28 |
| KS0316 | `stock_latest` 别名 | `KS0316-HLR-55-LINEPURPLE\|FZH-DANEEY-成品仓\|TT0031128K00638172-Cover` | 0 |

- KS0316 的 cover 是**观测到的 43 件**，但 `replenishment_pool.supply_in_rop=0`
  且 `trace.pool_note=cover_only` → 观测行为是 **cover 未计入供给**。
  这是「观测到的池行为」，不是已文档化的分配规则。
- 另外 3 个主口径 SKU 没有别名/`item_cover_stock` 行 → `alias_available_sum=null`；
  `pool_cover_available_raw=0` 只是池输出，不是「cover=0」的证据。

## 4. 扩展口径：10 个 expand10 SKU × 4 判定矩阵

> **这是扩展，不是主口径。** 与 §3 的 5 个 trace SKU 不合并、不相加。

| # | SKU | ETA | 在途 | Cover | UOM |
|---:|---|---|---|---|---|
| 1 | KS0001-QDKTR-100-DEEPGREY | ✅ evidence_present（无未结） | ✅ evidence_present（0） | ✅ evidence_present（别名 0） | ⚠️ scenario |
| 2 | KS0001-QDKTR-100-DEEPBLUE | ✅ evidence_present（1 行已结） | ✅ evidence_present（0） | ✅ evidence_present（别名 0） | ⚠️ scenario |
| 3 | KS0001-XMMBS-100-HEMPNATURAL | ⛔ **blocker**（1 行 / 121） | ✅ evidence_present（121） | ⚠️ scenario（无映射，null） | ⚠️ scenario |
| 4 | KS0001-CMKTR-100-DEEPBLUE | ⛔ **blocker**（2 行 / 240） | ✅ evidence_present（120） | ✅ evidence_present（别名 0） | ⚠️ scenario |
| 5 | KS0001-XMMBS-153-HEMPNATURAL | ⛔ **blocker**（3 行 / 223） | ✅ evidence_present（215） | ✅ evidence_present（别名 0） | ⚠️ scenario |
| 6 | KS0001-PR-100-GREY | ✅ evidence_present（3 行已结） | ✅ evidence_present（0） | ✅ evidence_present（别名 0） | ⚠️ scenario |
| 7 | KS0001-CMKTR-100-GREY | ⛔ **blocker**（3 行 / 318） | ✅ evidence_present（165） | ✅ evidence_present（别名 0） | ⚠️ scenario |
| 8 | KS0001-CMM-100-WHITE | ⛔ **blocker**（2 行 / 73） | ✅ evidence_present（73） | ⚠️ scenario（无映射，null） | ⚠️ scenario |
| 9 | KS0001-HLR-100-OFFWHITE | ⛔ **blocker**（2 行 / 490） | ✅ evidence_present（490） | ⚠️ scenario（无映射，null） | ⚠️ scenario |
| 10 | KS0001-XMMBS-194-HEMPNATURAL | ✅ evidence_present（4 行已结） | ✅ evidence_present（0） | ⚠️ scenario（无映射，null） | ⚠️ scenario |

**扩展口径计数**：ETA blocker **6** / evidence_present **4**；在途 evidence_present **10**
（其中逐笔关系 scenario **6**）；Cover evidence_present **6** / scenario **4**；
UOM scenario **10**（需求侧 10/10 有 EN SO 观测，库存侧 0/10）。

### 4.1 扩展口径的 1,465 件未结 PO（可逐行复算）

行键 = `(ponum, goods_sku, warehouse)`；32 条 PO 记录 32/32 唯一
（13 未结 + 19 已结，无静默丢弃）。

| PO | 行键（`ponum\|goods_sku\|warehouse`） | open_qty | purchase_date | will_arrive_date |
|---|---|---|---:|---|---|
| PO021716 | `PO021716\|TT0000671K0063721\|美中-FZH-DANEEY` | 309 | 2026-09-09 09:20 | NULL |
| PO021717 | `PO021717\|C/Cord-Grey-100-710-wow\|美东-CENTRADE` | 12 | 2026-09-09 09:22 | NULL |
| PO021717 | `PO021717\|C/Linen-White-100-662-WOW\|美东-CENTRADE` | 20 | 2026-09-09 09:22 | NULL |
| PO021717 | `PO021717\|C/Linen-Natural-100-688-wow\|美东-CENTRADE` | 121 | 2026-09-09 09:22 | NULL |
| PO021717 | `PO021717\|C/Linen-Natural-153-688-wow\|美东-CENTRADE` | 207 | 2026-09-09 09:22 | NULL |
| PO021726 | `PO021726\|C/Linen-White-100-662-WOW\|美东-CENTRADE` | 53 | 2026-09-29 10:54 | NULL |
| PO021727 | `PO021727\|TT0000671K0063721\|美中-FZH-DANEEY` | 181 | 2026-09-29 10:57 | NULL |
| PO021733 | `PO021733\|C/Cord-DKBlue-100-713-wow\|美东-CENTRADE` | 120 | 2026-10-12 16:15 | NULL |
| PO021733 | `PO021733\|C/Cord-Grey-100-710-wow\|美东-CENTRADE` | 153 | 2026-10-12 16:15 | NULL |
| PO021733 | `PO021733\|C/Linen-Natural-153-688-wow\|美东-CENTRADE` | 8 | 2026-10-12 16:15 | NULL |
| PO021735 | `PO021735\|C/Cord-DKBlue-100-713-wow\|美东-CENTRADE` | 120 | 2026-10-13 16:26 | NULL |
| PO021735 | `PO021735\|C/Cord-Grey-100-710-wow\|美东-CENTRADE` | 153 | 2026-10-13 16:26 | NULL |
| PO021735 | `PO021735\|C/Linen-Natural-153-688-wow\|美东-CENTRADE` | 8 | 2026-10-13 16:26 | NULL |
| **合计** | **13 行 / 6 个 PO** | **1,465** | — | **0 行有 ETA** |

按 PO 小计：PO021716=309；PO021717=360；PO021726=53；PO021727=181；
PO021733=281；PO021735=281。合计 1,465。

### 4.2 扩展口径的逐文件 SO 行数（215 行）

| 文件 | 客户码 | `so_rows` | SO 中出现的 item_code | uom |
|---|---|---:|---|---|
| `g1b_en_top_1.json` | CENCord995-DKGrey-97 | 19 | KS0001-QDKTR-100-DEEPGREY, PK#… | 个 |
| `g1b_en_top_2.json` | CEN003-DPBLUE-100 | 15 | KS0001-QDKTR-100-DEEPBLUE, PK#… | 个 |
| `g1b_en_top_3.json` | C/Linen-Natural-100-688-wow | 19 | PK#KS0001-XMMBS-100-HEMPNATURAL | 个 |
| `g1b_en_top_4.json` | C/Cord-DKBlue-100-713-wow | 16 | PK#KS0001-CMKTR-100-DEEPBLUE | 个 |
| `g1b_en_top_5.json` | C/Linen-Natural-153-688-wow | 28 | PK#KS0001-XMMBS-153-HEMPNATURAL | 个 |
| `g1b_en_top_6.json` | C/Velvet-Grey-100-705-wow | 15 | PK#KS0001-PR-100-GREY | 个 |
| `g1b_en_top_7.json` | C/Cord-Grey-100-710-wow | 18 | PK#KS0001-CMKTR-100-GREY | 个 |
| `g1b_en_top_8.json` | C/Linen-White-100-662-WOW | 17 | PK#KS0001-CMM-100-WHITE | 个 |
| `g1b_en_top_9.json` | TT0000671K0063721 | 42 | KS0001-HLR-100-OFFWHITE, PK#… | 个 |
| `g1b_en_rr2.json` | C/Linen-Natural-194-688-wow | 26 | PK#KS0001-XMMBS-194-HEMPNATURAL | 个 |
| **合计** | — | **215** | — | — |

> 215 = 逐文件 `len(json["so_rows"])` 相加；每行都只算一次，没有跨文件去重。
> 注意 top_1/top_2/top_9 的文件同时包含 KS 与 PK 行，所以 19/15/42 不是纯 KS 行数。
> 主口径的 5 个 trace SKU 中只有 QDKTR 出现在这些文件里（top_1），其余 4 个没有本地
> EN SO 证据。

### 4.3 扩展口径的 Cover 观测

- **6 个有 `-Cover` 别名且观测为 0**：QDKTR-DEEPGREY、QDKTR-DEEPBLUE、
  CMKTR-DEEPBLUE、XMMBS-153、PR-GREY、CMKTR-GREY。别名仓键见 JSON
  `cover.alias_rows[].warehouse_key`。
- **4 个无映射**：XMMBS-100、CMM-WHITE、HLR-OFFWHITE、XMMBS-194 →
  `cover_observed=false`、`alias_available_sum=null`、`item_cover_stock_available_sum=null`。
  这是 scenario，不是「cover=0」。
- `replenishment_pool.cover_available=0` 在 13/13 行，但它是池输出列；
  对无映射的 4 个 SKU 不能当观测 0 用。

## 5. 业务口径与未证规则（按要求单列）

### 5.1 皮壳 ship basis

- 观测值来自 `replenishment_pool.ship_type` 与 `trace_examples.json.ship_type`：
  - 主口径：QDKTR-DEEPGREY `皮壳`、KS0249 `皮壳`、KS0230 `成品`、KS0316 `成品`、KS0153 `半成品`。
- **皮壳**：按皮壳口径计算需求；cover 是共享/独立库存的一个概念，但「cover 与不带后缀
  库存是否实物同池、可替代」**未证**（R290 遗留）。
- **成品**：KS0316 的 `pool_note=cover_only`、`supply_in_rop=0`，观测行为是 cover
  不计入供给；这只对 KS0316 有观测，不能外推到所有成品。
- **半成品**：KS0153 观测为半成品；本轮不推导其补货规则。

### 5.2 Cover 分配规则

- **没有文档化规则**：本地仓库没有生成 `item_cover_stock` 的代码，
  `replenishment_pool` 也没有说明 `cover_available` 是否并入供给。
- 观测到的两件事：
  1. 有 `-Cover` 别名的 SKU 可以观测到 cover 桶（主口径 QDKTR 为 0，KS0316 为 43）；
  2. KS0316 的 `supply_in_rop=0` 且 `pool_note=cover_only`，即 cover 被排除在供给之外。
- **不能推出**：无别名 = 无 cover 池；cover 可用 = cover 可替代非 cover 库存。
  这两条都保持 `not_proven` / `scenario`。

### 5.3 ETA 类型

见 §2 的 `planned / confirmed / usable` 表。核心一句：
**本轮没有任何一条可用 ETA**；`planned` 路径未获授权，`confirmed` 字段全空，
因此 `usable=null`，6+1 个 blocker 不是「暂时没填」，而是「本地证据不存在」。

## 6. 计数对账（两套分开）

### 6.1 主口径（5 trace SKU）

| 项 | 数量 | 说明 / 出处 |
|---|---:|---|
| SKU | 5 | `trace_examples.json` 5 个键 |
| trace 行 | 5 | 每 SKU 一个锚点仓 |
| pool 行 | 9 | 2+2+2+2+1；3 个仓 |
| PO 记录 | 3 | 全部属于 KS0316 |
| 未结 PO 行 / 数量 / PO 数 | 1 / 10 / 1 | PO021715 |
| 已结 PO 行 | 2 | `open_qty=0`；`in_quantity==quantity`；status=3 |
| BOM 头 / 子件行 | 5 / 9 | 子件全部 `qty=1`、`uom=个` |
| `stock_latest` 行 | 18 | 含 4 行 `-Cover` 别名 |
| `item_cover_stock` 行 | 2 | 均属 KS0316 |
| 本地 EN SO 覆盖 | 1 / 5 | QDKTR 有 top_1；其余 4 个无 |

### 6.2 扩展口径（10 expand10 SKU）

| 项 | 数量 | 说明 / 出处 |
|---|---:|---|
| SKU | 10 | §1 映射表 |
| pool 行 / 仓 | 13 / 3 | 美东-CENTRADE、美中-FZH-DANEEY、波兰-FZHPoland-covers |
| PO 记录 | 32 | 13 未结 + 19 已结；32/32 行键唯一 |
| 未结 PO 行 / 数量 / PO 数 | 13 / 1,465 / 6 | §4.1 逐行 |
| BOM 头 / 子件行 | 10 / 20 | 子件全部 `qty=1`、`uom=个` |
| `stock_latest` 行 | 34 | 含 6 行 `-Cover` 别名 |
| `item_cover_stock` 行 | 0 | 10 个 item_code 均无 |
| EN 快照 SO 行 | 215 | §4.2 逐文件 |

**全局字段完整性**：`tongtool_po` 524 行，`will_arrive_date` 0 非空；
`stock_history` 15,820 行，`uom_basis=unknown` 15,820；
`item_cover_stock` 全表 155 行。

**对账等式（逐仓成立）**：
`replenishment_pool.on_order = sum(tongtool_po.open_qty)`；
`available_all / intransit_all = sum(stock_latest.available / intransit)`。
主口径与扩展口径分别对平，未把两套人口相加。

## 7. 残留 blockers 与最小可验证输入

> 两套人口分别列，**不相加**。重叠 SKU `KS0001-QDKTR-100-DEEPGREY` 两边都不是 blocker。

### 7.1 主口径（5 trace SKU）

| # | Blocker | 证据 | 最小可验证输入 |
|---:|---|---|---|
| 1 | **ETA：KS0316 / PO021715 / 10 件** | `will_arrive_date=NULL`；`purchase_date=2026-09-09 09:19` | 业务按 PO 行给预计到货日期；或通途采购单/采购 API 的 ETA 字段（只需 PO021715） |
| 2 | Cover 缺失（scenario，非 blocker） | KS0230 / KS0153 / KS0249 无别名、`item_cover_stock` 0 行 | 业务确认「无 cover 池」，或提供同仓 PK# 皮壳 bin 快照 |
| 3 | 在途↔PO 逐笔（scenario） | KS0316 波兰 `open_qty=10 = intransit=10`，但两表无共同键 | 发运批次 / PO 入库分录；或书面接受「intransit 是 open PO 的子集」 |
| 4 | 库存 UOM（scenario） | `stock_latest` 无 uom；`stock_history.uom_basis=unknown` | 确认 5 个通途 SKU 的库存单位，或提供带 uom 的快照 |

### 7.2 扩展口径（10 expand10 SKU）

| # | Blocker | 证据 | 最小可验证输入 |
|---:|---|---|---|
| 1 | **ETA：6 个 SKU / 13 行 / 1,465 件 / 6 个 PO** | 13/13 `will_arrive_date=NULL` | 6 个 PO 的逐行 ETA：PO021716/717/726/727/733/735 |
| 2 | Cover 缺失（scenario） | XMMBS-100 / CMM-WHITE / HLR-OFFWHITE / XMMBS-194 无映射 | 同 §7.1 #2，只需这 4 个 item_code |
| 3 | 在途↔PO 逐笔（scenario） | 6 个有未结 PO 的 SKU；每仓 `open_qty >= intransit`，但无单据键 | 同 §7.1 #3 |
| 4 | 库存 UOM（scenario） | 10/10 无 uom | 同 §7.1 #4 |

## 8. 可复现性（查询定义与源哈希）

**数据库**：`D:/Work/fzh-order-store/order_store.duckdb`
`sha256=25579c5dcd802c7e67f610432a19d08f8e6952696bd50d43bdfa47d6b9241ae9`
`bytes=51,654,656`；`read_only=True`；运行前后哈希不变。

**trace 源**：
`trace_examples.json` `sha256=963099c33d581c4b889d41c4fbfb28a0ec1b72a34109640e942cf63c89d8df98`
（5,207 bytes）；
`trace_examples.md` `sha256=3bd85258643df1a9e35c33e3f37bdd0d7e4948287a6069786cae55d00d5940d9`
（5,839 bytes）。

**PO 行查询（Q1）**：

```sql
SELECT m.item_code, p.ponum, p.goods_sku, p.warehouse, p.quantity, p.in_quantity,
       p.open_qty, p.status, p.purchase_date, p.will_arrive_date
FROM tongtool_po p
JOIN sku_map m ON m.tongtool_sku = p.goods_sku
WHERE m.item_code IN (<sku_list>)
ORDER BY m.item_code, p.ponum, p.warehouse, p.goods_sku;
```

- 行键：`(ponum, goods_sku, warehouse)`；扩展口径 32/32 唯一，主口径 3/3 唯一。
- 复算 1,465：取 Q1 结果中 `open_qty > 0` 的 13 行，`sum(open_qty)=1465.0`；
  行键与逐行值见 §4.1 / JSON `extension_scope.open_po_reproduction.lines`。

**Cover 查询（Q3）**：

```sql
SELECT item_code, warehouse, cover_available
FROM item_cover_stock
WHERE item_code IN (<sku_list>)
ORDER BY item_code, warehouse;
```

**库存查询（Q2）**：

```sql
SELECT m.item_code, s.warehouse, s.sku, s.available, s.intransit,
       s.waiting_shipment, s.defects, (s.sku LIKE '%-Cover') AS is_cover_alias
FROM stock_latest s
JOIN sku_map m ON m.tongtool_sku = s.sku
WHERE m.item_code IN (<sku_list>)
ORDER BY m.item_code, s.warehouse, s.sku;
```

**SO 行数定义**：逐个读取 10 个 EN 快照，取 `len(json["so_rows"])`，相加；
不做跨文件去重。文件哈希（完整）：

```text
e72c0e8a30c81f4105104b6f0ecff377c4eb88fd6570d0f53ba7035ee03515ee  g1b_en_top_1.json  (19)
e3855cc03ca00d13e548cbe515a5efb9a6a1b965f89174478fae2c9c38a60b17  g1b_en_top_2.json  (15)
71d0150d67dede9e70c1b3b217c7cec73b8edd4e6414846d7680a5c63f10a343  g1b_en_top_3.json  (19)
c03399ec398fa2f334f28ffae6f2125be9a5a948a4c02dc59ae14012e265bd52  g1b_en_top_4.json  (16)
67a3e00213e04eefcbfc2b2b4911ea089edde39e20ca99ddc022fecb6508e311  g1b_en_top_5.json  (28)
09b0791aac8314c968f6cb5974cc9f3d09efaecfe86cacb837d44bf8f96dae53  g1b_en_top_6.json  (15)
afaa289dd9d3add0cf341316926d6ac58b6903fc340641c30da88717beb12201  g1b_en_top_7.json  (18)
c7608ef50ba7ae23cbc3d8055d327180f008857c4ef03e0759b19399c7cd22b0  g1b_en_top_8.json  (17)
8605c067c888b17e40e02a779ceab5aa9bea9e7d19c48c2a8bf78be92feab32e  g1b_en_top_9.json  (42)
e01e79520077d3fdcec893ed8e7961b17a5e80b8c633bd46a09d9e2d887818c7  g1b_en_rr2.json    (26)
```

**证据 JSON**：
- 规范位置：`experiments/g1_contract/out/eta_cover_uom/evidence.json`
- 重复副本：`out/eta_cover_uom/evidence.json`（**同一份字节**）
- 两处 `sha256=5b6bca32ed6da635bd55bd4a31aab34592c4e632a8de034728ed5d4d85f73678`
  `bytes=133,136`
- 内容为聚合值/键/哈希，**不含原始订单明细**。

完整的 8 条查询定义（含占位符说明）在 JSON `query_definitions`；
逐文件 SO 计数与哈希在 `source_hashes.en_snapshots.files`。

## 9. 已知限制

1. **主口径只有 1/5 有本地 EN SO 证据**：QDKTR 有 top_1（19 行，含 KS+PK）；
   KS0230 / KS0153 / KS0316 / KS0249 没有本地 EN 快照，需求单位与需求量为 unknown。
2. **trace 没有客户码**：4 个 SKU 的 `customer_code=null`（QDKTR 的客户码取自 top_1）。
3. **库存时点**：`replenishment_pool`/`stock_latest` 是 2026-10-21 13:48 抓取；
   `stock_history` 已有 10-22 快照，4 个扩展 SKU 的 available 有 1–6 件差异，
   intransit 无差异；本轮引用 pool 口径，故与 pool 对平。
4. **pool 只覆盖 3 个仓**；`stock_latest` / `three_pl_stock` 里的 WayfairCG-Cranbury
   等 3PL 库存不在 pool 口径内，本轮不并入供给，也不代表不存在。
5. **`item_cover_stock` 来源不可考**：本地没有生成该表的代码；无行只能当假设。
6. **`status` 码无字典**：`open_qty=0` + `in_quantity==quantity` 与收货一致，
   但本轮不写「已收货」。
7. **EN 快照是 2026-10-20/21 离线抓取**，不是本轮实时；本轮 0 次生产访问。
8. **未估算**：没有用 `purchase_date + lead_days` 生成任何日期，没有补 0，没有外推。

## 10. v1 → v2 差异摘要

| # | v1 问题 | v2 处理 |
|---:|---|---|
| 1 | 把 10 个 expand10 SKU 当主口径，5 个 trace SKU 只放附录 | 主口径改为 5 trace SKU；10 SKU 单列扩展；不合并、不相加 |
| 2 | 无 cover 映射时写 `cover_alias_available=0` | 改为 `alias_available_sum=null` + `cover_observed=false`；观测 0 单独用 `observed_zero` |
| 3 | 缺 PO 行键、cover 仓键、逐文件 SO 计数、查询定义/哈希 | 全部补入 JSON 与报告 §3.2/§3.3/§4.1/§4.2/§8 |
| 4 | 「`max()` 安全」「不需要换算」「19 条已入库」等过强 | 全部改为条件结论；`condition_status=not_proven`、`receipt_proven=false`；补 ETA 三类型与皮壳/cover 规则说明 |
| 5 | 证据复制到两处但未说明 | 明确规范位置 + 重复副本 + 相同 sha256 |

## 运行信息

- 用时：约 12 分钟（只读查询、重建 JSON、写报告），在 90 分钟时间盒内。
- `order_store.duckdb`：`read_only=True`，运行前后 `sha256=25579c5d…`，未修改。
- 0 次通途/EN 网络调用；未访问生产；未提交原始订单明细。
- 交付 v2 后仍待 lead 与 fresh reviewer 对照；本报告不自行宣布 PASS。
