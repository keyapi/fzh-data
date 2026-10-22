---
okf: v0.1
type: Report
title: true_missing Top10 SKU 证据审计（含 TT0031245K0064088）
description: 只读核对 GS 订单侧 Top10 true_missing + 指定删除 alias 的订单行、候选基础码、冲突映射与待业务裁决项；不写 EN、不改 sku_map
date: 2026-10-22
owner: claude-worker
status: completed
tags: [supply-chain, sku-mapping, true-missing, evidence, read-only]
---

# true_missing Top10 SKU 证据审计

## 一句话结论

按订单行数取 `true_missing` 前 10 个 SKU（1,320 行 / 2,957 行，44.6%）并强制加入
`TT0031245K0064088` 及其 `-0` 变体（789 行），共 **12 个 SKU / 2,109 行 / 2,025 qty** 完成逐 SKU 对账。
**10 个 SKU 有候选证据，8 个 SKU 存在冲突**；其中 `YCSOFA001`、`FBA-duo`、`TT0031245K0064088`
是「一个通途码挂多个商品/平台码」的汇总码，不能按单条 alias 处理。全部 12 个 SKU 仍为
**pending / conflicting**，没有任何一条被认领或写回。

## 1. 范围与选择规则

| 项 | 值 |
|---|---|
| Top10 规则 | C 审计 `categories.json` 中 `category=true_missing`，按 `order_lines` 降序、`qty` 降序、`sku` 升序取前 10 |
| 强制纳入 | `TT0031245K0064088`（553 行，C 分类为 `insufficient_evidence`，删除 alias 后仍在卖） |
| 关联变体 | `TT0031245K0064088-0`（236 行，同一删除 alias 族；单列，不并入 Top10） |
| 审计对象合计 | **12 个 SKU / 2,109 行 / 2,025 qty** |
| 分母 | GS 订单侧未精确命中 `sku_map` 的 4,115 行 / 297 SKU（与 C 审计一致） |

> **路径差异（已核）**：任务书写的 C 产物目录
> `experiments/g1_contract/out/sku_match_audit/` 当前不存在；实际产物在仓库根
> `out/sku_match_audit/`（`.gitignore: out/*`）。本审计读取实际目录，JSON 写到任务书路径。

## 2. 输入与只读边界

- `D:/Work/fzh-order-store/order_store.duckdb`：`read_only=True`，只用 `gs_orders` / `sku_map`。
- `D:/Work/fzh-order-store/sku_map.tsv`：只读；用于取回 DuckDB 表按 `tongtool_sku` 去重前的别名对。
- C 产物：`unmatched_all.csv`、`categories.json`、`deep100.md`。
- **未写 EN / ERPNext、未改 sku_map、未恢复删除别名、未创建映射、未估算、未访问生产、未扩族。**

## 3. 行数对账（不丢行）

| 检查 | 结果 |
|---|---|
| `gs_orders` 总行 | 407,898 |
| 未精确命中行（DuckDB 复算） | 4,115 |
| C 审计未命中行 | 4,115 ✅ |
| `unmatched_all.csv` 数据行 | 4,115 ✅ |
| 12 个 SKU 的 CSV 行数与 C 分类逐项一致 | 12/12 ✅ |
| 选中行占未命中行 | 2,109 / 4,115 = **51.25%** |
| Top10 占 `true_missing` 行 | 1,320 / 2,957 = **44.64%** |
| 强制项 + `-0` 占 `insufficient_evidence` 行 | 789 / 801 = **98.50%** |

状态统计：`conflicting_evidence` 7、`pending_insufficient_evidence` 2、`pending_business_confirmation` 3。
冲突记录 9 条（分布在 8 个 SKU）；待业务裁决事项 28 条。

## 4. 结果总表

| # | SKU（原始通途码） | 行 | qty | 月数 | 首–末月 | 渠道数 | C 分类 | 候选摘要 | 状态 |
|---:|---|---:|---:|---:|---|---:|---|---|---|
| 1 | `YCSOFA001` | 234 | 248 | 5 | 202510–202602 | 4 | true_missing | 无；114 个平台码均未登记 | pending_insufficient |
| 2 | `XINGQIU-Jupiter-10` | 171 | 175 | 22 | 202301–202508 | 4 | true_missing | `KS0019-PBHLR-25-JUPITER`（推断，未登记） | conflicting |
| 3 | `XINGQIU-Jupiter-16` | 149 | 152 | 27 | 202301–202504 | 6 | true_missing | `KS0019-PBHLR-41-JUPITER`（推断，未登记） | conflicting |
| 4 | `CEN003-NZAIBLUE-100` | 134 | 143 | 10 | 202301–202312 | 5 | true_missing | `KS0001-TR-100-DENIMBLUE`（推断，未登记） | pending_business |
| 5 | `XINGQIU-Earth-10` | 134 | 135 | 16 | 202301–202412 | 6 | true_missing | `KS0019-PBHLR-25-EARTH`（推断，未登记） | conflicting |
| 6 | `FBA-duo` | 120 | 122 | 9 | 202301–202409 | 2 | true_missing | 多商品桶（21 个 item_code） | conflicting |
| 7 | `CEN-No/B-Velvet-Grey-100` | 116 | 130 | 19 | 202301–202408 | 5 | true_missing | `KS0248-HLR-100-GREY`（平台码直命中） | pending_business |
| 8 | `petcushionjp-76` | 99 | 102 | 2 | 202305–202307 | 1 | true_missing | 无；`sku_map` 无 cushion 族键 | pending_insufficient |
| 9 | `CEN-No/B-Velvet-Grey-194` | 85 | 87 | 21 | 202302–202410 | 4 | true_missing | `KS0248-HLR-194-GREY`（平台码直命中） | conflicting |
| 10 | `BAI20019N0A62887SX-FBA` | 78 | 78 | 6 | 202401–202502 | 1 | true_missing | `KS0125-MM-110-NAVYSTRIPE`（跨行平台码） | pending_business |
| 11 | `TT0031245K0064088` | 553 | 483 | 9 | 202504–202512 | 9 | insufficient_evidence | `HM1510-…-WHITE`（删）/ `KS0394-…-REDDISHGRAY`（活）| conflicting |
| 12 | `TT0031245K0064088-0` | 236 | 170 | 7 | 202504–202511 | 4 | insufficient_evidence | `KS0394-…-REDDISHGRAY`（删 alias） | conflicting |

## 5. 逐 SKU 证据

### 5.1 `YCSOFA001` — 234 行 / 248 qty / 5 个月（202510–202602）

- 渠道：BESTBUY 105、tiktok 73、Shopify 34、亚马逊 22；6 个账号，仓库几乎全为「多渠道仓库」。
- 原始码 `YCSOFA001` 在 **114 个不同 platform_sku 取值**（含 8 行空值）上出现（N719Black/Grey、BJ002-*、W-*、DYBDFTJ-* 等），
  没有一条 platform_sku 直接命中 `sku_map`。
- 结论：形态是**沙发类汇总码**，不是单品编码。跨行证据中只有个别平台码能落到 item_code，
  不足以认领，标 `pending_insufficient_evidence`。
- 需裁决：该码代表哪个商品；或是否按平台码拆成多条映射。

### 5.2 `XINGQIU-Jupiter-10` — 171 行 / 175 qty / 22 个月（202301–202508）

- 渠道：亚马逊 130、Walmart 22、OSTK 13、Wayfair 6；仓库全为 CENTRADE；10 个账号。
- platform_sku：`XUE9008YAN9481PL-US` 88 行、`WMRUS-9008-Jupiter-10 in` 22、`...-MFN` 20 等。
- 候选（推断，未登记）：`XINGQIU-Jupiter-10` → `KS0019-PBHLR-25-JUPITER`。
  证据为同族已登记键：Moon-10→25-MOON、Moon-16→41-MOON、BlackMoon-10/16→25/41、Earth-16→41-EARTH。
- 冲突：`XUE9008YAN9481PL-US` 同时出现在 Jupiter-10 与 Jupiter-16 行，平台码不能区分尺寸。
- 需裁决：EN 是否存在 `KS0019-PBHLR-25-JUPITER`；Jupiter 是否沿用 KS0019-PBHLR 系列。

### 5.3 `XINGQIU-Jupiter-16` — 149 行 / 152 qty / 27 个月（202301–202504）

- 渠道：亚马逊 113、Walmart 14、OSTK 11、Wayfair 9、PotteryBarn 1、tiktok 1；13 个账号。
- 候选（推断，未登记）：`KS0019-PBHLR-41-JUPITER`，证据同 5.2（16 码对应 41）。
- 冲突：与 Jupiter-10 共用平台码 `XUE9008YAN9481PL-US`；另自身平台码 `XUE9008YAN9480PL-US` 53 行。
- 需裁决：同 5.2，确认 41 码物料存在且 Jupiter 与 Moon/BlackMoon 同系列。

### 5.4 `CEN003-NZAIBLUE-100` — 134 行 / 143 qty / 10 个月（202301–202312）

- 渠道：亚马逊 85、OSTK 19、Walmart 15、Wayfair 14、HOUZZ 1；仓库全为 CENTRADE；9 个账号。
- platform_sku：`CEN3ZAIBLUE-Twin-MFN` 59、`CEN003-NZAIBLUE-100` 26、`BAI1001N0A5275SX` 19。
- 候选（推断，未登记）：`KS0001-TR-100-DENIMBLUE`。
  证据：同色 150→153、180→183、194→194 已登记；同族其它颜色 -100 均映射 `KS0001-TR-100-<COLOR>`；
  仅 DPBLUE 走 QDKTR 面料线，NZAIBLUE 应走 TR。
- 无直接平台码命中；无冲突项。标 `pending_business_confirmation`。
- 需裁决：EN 是否存在该 100 码物料；100 码不做 100→153 换算。

### 5.5 `XINGQIU-Earth-10` — 134 行 / 135 qty / 16 个月（202301–202412）

- 渠道：亚马逊 98、Wayfair 15、Walmart 12、OSTK 7、DLZ 1、PotteryBarn 1；9 个账号。
- 候选（推断，未登记）：`KS0019-PBHLR-25-EARTH`。
  证据：同族 `XINGQIU-Earth-16` 已登记 → `KS0019-PBHLR-41-EARTH`；Moon-10→25-MOON。
- 冲突：`XUE9006YAN9477PL-US` 也出现在 Earth-16 行并映射 41-EARTH，平台码不能唯一区分 10/16。
- 需裁决：确认 `KS0019-PBHLR-25-EARTH` 存在；确认 10/16 的物料/尺寸差异。

### 5.6 `FBA-duo` — 120 行 / 122 qty / 9 个月（202301–202409）

- 渠道：亚马逊 119、DLZ 1；仓库全为「多渠道仓库」；4 个账号。
- **30 个 platform_sku**（`B0BW8SWXJC-duo` 31、`BAI1538N0A9463SX` 10、`B08RN62PLM-duo` 9 等）。
- 跨行证据：这些平台码在其它 tongtool 行上已映射到**21 个不同 item_code**，例如
  `KS0001-QDKTR-100-DEEPBLUE`、`KS0001-HLR-100-GREY`、`KS0118-ZQTW-7652-NAVYSTRIPE`、
  `KS0001-HLR-100-DEEPBLUE`、`KS0001-DM-100-GREY`、`KS0001-HLR-153-TAN`、`KS0001-TR-153-COFFEE`。
- 结论：`FBA-duo` 是**多商品/多件套汇总码**，不能登记为单条 alias；`duo` 的件数/UOM 口径也未知。
- 需裁决：duo 的套件组成；若为 2 件装，订单 qty 的库存扣减口径。

### 5.7 `CEN-No/B-Velvet-Grey-100` — 116 行 / 130 qty / 19 个月（202301–202408）

- 渠道：亚马逊 86、Wayfair 21、Walmart 5、OSTK 3、HOUZZ 1；仓库全为 CENTRADE；12 个账号。
- 高置信候选：`CEN-No/B-971-Velvet-Grey-100` **本身就是 sku_map 键** → `KS0248-HLR-100-GREY`；
  该平台码在本 SKU 下命中 29 行。另 `CEN-No/B-971-Velvet-Grey-Twin` 49 行（Twin 应为 100 码）。
- 无冲突；标 `pending_business_confirmation`。
- 需裁决：原始码（无 971 段）与已登记 971 写法是否同一商品；确认 Twin=100。

### 5.8 `petcushionjp-76` — 99 行 / 102 qty / 2 个月（202305–202307）

- 渠道：亚马逊 99；仓库全为「扬州仓库」；1 个账号。
- **唯一平台码 `petcushionjp-76x` 占全部 99 行**；`sku_map` 中无任何 `cushion` 相关键。
- 本地无候选、无冲突；标 `pending_insufficient_evidence`。
- 需裁决：EN 是否曾建过该宠物垫物料；如无，是否新建（本审计不创建）。

### 5.9 `CEN-No/B-Velvet-Grey-194` — 85 行 / 87 qty / 21 个月（202302–202410）

- 渠道：亚马逊 65、Wayfair 15、Walmart 3、OSTK 2；仓库全为 CENTRADE；9 个账号。
- 高置信候选：`CEN-No/B-971-Velvet-Grey-194` → `KS0248-HLR-194-GREY`（本 SKU 下命中 23 行）；
  `CEN-No/B-971-Velvet-Grey-King` 32 行（King 应为 194 码）。
- 冲突：`WM-971-Velvet-Grey-King` 在 `CEN-No/B-968-Linen-Grey-194` 行映射 `KS0248-DM-194-GREY`
  （另一面料）；平台码存在跨面料复用，不能跨行直接认领。
- 需裁决：确认 King=194；确认 WM 平台码复用不影响 971 Velvet 的 HLR 面料。

### 5.10 `BAI20019N0A62887SX-FBA` — 78 行 / 78 qty / 6 个月（202401–202502）

- 渠道：亚马逊 78（单一账号 AMZBAINAUS）；多渠道仓库 75、退货产品仓 3。
- platform_sku：`BAI20019N0A62887SX` 68、`-cui` 7、`-qinghuo` 3；均无直接 `sku_map` 命中。
- 跨行高置信候选：基础平台码 `BAI20019N0A62887SX` 在其它行对应 `TT0020019K0062887`
  → `KS0125-MM-110-NAVYSTRIPE`（跨行证据 36 行，含 `-cui`）。
- 无冲突；标 `pending_business_confirmation`。
- 需裁决：`-FBA`、`-cui`、`-qinghuo` 是渠道/运营后缀，是否统一到同一 item_code。

### 5.11 `TT0031245K0064088`（强制）— 553 行 / 483 qty / 9 个月（202504–202512）

- 渠道：TiktokUS 371、tiktok 56、XXXL 51、亚马逊 26、HOME24 22、Cdiscount 18、ETSY 4、OSTK 3、kaufland.de 2。
- 仓库：半成品仓 275、星链海外仓 161、FZHPoland-covers 116、成品仓 1；15 个账号。
- `platform_sku` 23 个：**364 行为自身**（`TT0031245K0064088`），**189 行是别的商品码**
  （`TT0031245K0064086-SOFA-Beige`、`...64087-SOFA-Gray`、`TT0020043K0063354` 等）。
- 证据 A（已删除 alias，低）：`删除TT0031245K0064088` → `HM1510-YD2-135x152x80-WHITE`；无活映射。
- 证据 B（活族别名，中）：`TT0031245K0064088-Foam` → `KS0394-CTTM-135x152x80-REDDISHGRAY`；
  同族 `TT0031245K0064086`（Beige）与 `64087`（Gray）基础码也映射 KS0394。
- 证据 C（跨行平台码，中）：23 个平台码中 7 个直接命中已映射 item_code，
  涉及 `KS0394`（红灰/米色）、`KS0228-HLR-25-GREY`、`KS0116-HLR-45-GREY`、`KS0223-NL-65XL-BLUERED`、
  `KS0390-CTTM-120x120x70-CREAMYBEIGE`、`KS0210-FBWB-74-DENIMBLUE` 等。
- **冲突 1**：活键 `-Foam` → KS0394 红灰，删除键 `删除...-Foam` → HM1510 白；同一别名族两侧指向不同物料。
- **冲突 2**：189/553 行的平台码是别的 tongtool 码并映射到多个 item_code；该码不是单品身份。
- 需裁决：该码是否为 Tiktok 沙发的汇总/占位码；HM1510（白）与 KS0394（红灰）哪个才是主体；
  删除原因与是否恢复（恢复属禁止项，只能由业务决定）。

### 5.12 `TT0031245K0064088-0`（关联变体）— 236 行 / 170 qty / 7 个月（202504–202511）

- 渠道：TiktokUS 225、tiktok 8、OSTK 2、ETSY 1；仓库全为半成品仓；4 个账号。
- 高置信候选：`删除TT0031245K0064088-0` → `KS0394-CTTM-135x152x80-REDDISHGRAY`；
  与活别名 `-Foam` 指向一致。223/236 行 platform_sku 就是自身。
- 冲突：其余 13 行指向 `KS0223`、`KS0390`、`KS0193`、`KS0394` 等其它商品码，属汇总码污染。
- 需裁决：当初删除 alias 的原因；是否按 KS0394 恢复登记（本审计只记录，不恢复）。

## 6. 冲突清单（9 条 / 8 个 SKU）

| # | SKU | 冲突类型 | 要点 |
|---:|---|---|---|
| 1 | `YCSOFA001` | `aggregate_bucket_multi_listing` | 114 个平台码、4 个渠道；无平台码直接命中，非单品 |
| 2 | `XINGQIU-Jupiter-10` | `shared_platform_sku_across_sizes` | `XUE9008YAN9481PL-US` 同时挂 10/16，平台码不能定尺寸 |
| 3 | `XINGQIU-Jupiter-16` | `shared_platform_sku_across_sizes` | 同上；另有自身平台码 53 行 |
| 4 | `XINGQIU-Earth-10` | `shared_platform_sku_across_sizes` | `XUE9006YAN9477PL-US` 也出现在 Earth-16（41-EARTH） |
| 5 | `FBA-duo` | `aggregate_bucket_multi_item` | 30 个平台码跨行对应多个 item_code；duo 套件口径未知 |
| 6 | `CEN-No/B-Velvet-Grey-194` | `platform_sku_reused_across_fabrics` | `WM-971-Velvet-Grey-King` 也映射 DM 面料物料 |
| 7 | `TT0031245K0064088` | `live_vs_deleted_alias_conflict` | 活 `-Foam`→KS0394 vs 删 `-Foam`→HM1510 |
| 8 | `TT0031245K0064088` | `aggregate_umbrella_code` | 189/553 行平台码指向其它商品码 |
| 9 | `TT0031245K0064088-0` | `platform_sku_contamination` | 13/236 行指向其它商品码 |

## 7. 需业务裁决事项（28 条，按 SKU）

1. **`YCSOFA001`（2 条）**：汇总码代表哪个商品 / 是否按平台码拆分；0 条直接命中，不能认领。
2. **`XINGQIU-Jupiter-10`（3 条）**：确认 `KS0019-PBHLR-25-JUPITER` 是否存在；Jupiter 是否沿用 KS0019 系列；平台码不能定尺寸。
3. **`XINGQIU-Jupiter-16`（3 条）**：同上，41 码。
4. **`CEN003-NZAIBLUE-100`（2 条）**：确认 `KS0001-TR-100-DENIMBLUE` 存在；确认 100 码不做 100→153 换算。
5. **`XINGQIU-Earth-10`（1 条）**：确认 `KS0019-PBHLR-25-EARTH` 存在及 10/16 差异。
6. **`FBA-duo`（2 条）**：定义 duo 套件组成/件数；确认 qty 的 UOM 与库存扣减口径。
7. **`CEN-No/B-Velvet-Grey-100`（3 条）**：原始码与 971 写法同一商品；确认 Twin=100；按流程登记。
8. **`petcushionjp-76`（2 条）**：EN 是否曾建该宠物垫物料；若无是否新建（本审计不建）。
9. **`CEN-No/B-Velvet-Grey-194`（3 条）**：同上；确认 King=194；确认平台码跨面料复用不影响 HLR。
10. **`BAI20019N0A62887SX-FBA`（2 条）**：基础平台码与 `KS0125-MM-110-NAVYSTRIPE` 的对应；`-cui/-qinghuo` 是否统一。
11. **`TT0031245K0064088`（3 条）**：是否为汇总/占位码；HM1510 白 vs KS0394 红灰谁为主体；删除原因与是否恢复。
12. **`TT0031245K0064088-0`（2 条）**：删除原因；是否按 KS0394 恢复登记。

## 8. 结论分级（证据状态，不是业务结论）

| 状态 | SKU 数 | SKU |
|---|---:|---|
| `conflicting_evidence` | 7 | Jupiter-10、Jupiter-16、Earth-10、FBA-duo、CEN-No/B-194、TT0031245K0064088、TT0031245K0064088-0 |
| `pending_insufficient_evidence` | 2 | YCSOFA001、petcushionjp-76 |
| `pending_business_confirmation` | 3 | CEN003-NZAIBLUE-100、CEN-No/B-100、BAI20019N0A62887SX-FBA |

> `YCSOFA001` 同时有「汇总码」冲突但无任何候选，因此状态取 `pending_insufficient_evidence`。
> 没有任何 SKU 达到「可直接登记」；`registered` 只表示证据来自既有映射或平台码精确命中，不代表可写回。

## 9. 未做 / 禁止项（逐条确认）

- 未写 EN / ERPNext，未创建/修改任何物料。
- 未改 `sku_map.tsv`、未改 DuckDB；全程 `read_only=True`。
- 未恢复任何删除别名（`删除TT0031245K0064088*` 保持原样）。
- 未创建映射、未做模糊认领、未估算数量或成本。
- 未访问通途 / EN 生产系统。
- 未把审计扩展到 Top10 之外的 SKU 族。

## 10. 缺口

1. **无 EN Item master 访问权**：`true_missing` 只说明 alias 未登记，不能证明 EN 无此物料；
   `KS0019-PBHLR-*-JUPITER`、`KS0001-TR-100-DENIMBLUE`、`KS0019-PBHLR-25-EARTH` 均为命名规律推断，**未验证存在**。
2. **平台码可复用**：同一 platform_sku 可能跨渠道/跨尺寸/跨面料复用（已在上表标出 3 类冲突），
   不能把平台码当作唯一业务键。
3. **删除 alias 的语义未知**：谁删、何时删、为何删，本地无记录；`TT0031245K0064088` 家族无法仅凭数据收敛。
4. **只有 GS 一个订单源**：Amazon 占多数，其他渠道样本少；未覆盖通途原始订单/库存侧。
5. **C 产物路径与任务书不一致**：实际在 `out/sku_match_audit/`；本报告已按实际目录复算并单列。

## 11. 复现

```bash
# 只读；输出 JSON 到 experiments/g1_contract/out/sku_match_audit/true_missing_top10.json
uv run python scripts/audit_true_missing_top10.py
```

产物：

- `docs/research/supply-chain/2026-10-20/claude/experiments/g1_contract/out/sku_match_audit/true_missing_top10.json`
  （聚合证据，无订单行级明细）
- 本报告：`docs/research/supply-chain/2026-10-20/claude/control/reviews/2026-10-22-true-missing-top10.md`
- 复现脚本：`scripts/audit_true_missing_top10.py`
