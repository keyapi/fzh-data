---
okf: v0.1
type: Report
title: 通途-EN SKU 匹配只读审计（GS 订单侧）
description: 把 GS 订单侧未命中 sku_map 的 297 个 SKU / 4,115 行拆成 base_candidate / duplicate_mapping / true_missing / insufficient_evidence 四类；不写 EN、不改 sku_map
date: 2026-10-22
owner: claude-worker
status: completed
tags: [supply-chain, sku-mapping, audit, read-only]
---

# 通途-EN SKU 匹配只读审计（C）

## 一句话结论

GS 订单侧有 **4,115 行 / 297 个唯一 SKU** 未在 `sku_map` 精确命中（占全部订单行 1.01%、占全部 SKU 11.6%）。
四类拆分为 **base_candidate 61 / duplicate_mapping 2 / true_missing 228 / insufficient_evidence 6**，计数与订单行完全对账。
最大单点是 `TT0031245K0064088` 与其 `-0` 变体（789 行，19.2%），其 EN alias 已被标记为「删除」，但订单持续到 2025-12——这不是「没登记」，而是**登记被删后仍在卖**，需业务方裁决。

## 1. 口径与分母（不可混用）

| 口径 | 行数 | 唯一 SKU | 来源 | 说明 |
|---|---:|---:|---|---|
| **本次：GS 订单侧** | **4,115** | **297** | 本地 `order_store.duckdb` → `gs_orders` LEFT JOIN `sku_map` | 本报告的唯一分母 |
| 旧：EN 订单/同步侧 | 6,549 | 6,549 行（非唯一 SKU 口径） | 旧结论，来自 EN 侧同步记录 | **分母不同，不可相加、不可替代** |

为什么不能复算旧数字：本地 `en_orders` 表只有订单头字段
（`order_id / sale_date / despatch_date / channel / account / warehouse / order_status / source / month`，2,733 行），
**没有 SKU 列**。EN 侧 6,549 必须在 EN 侧用其自身数据重新审计，不在本次范围。

匹配规则：**只认精确等值** `sku_map.tongtool_sku == gs_orders.sku_tongtool`，无后缀容错、无大小写容错、无模糊匹配。
后缀剥离只用于产生**候选**，从不构成命中或认领。

## 2. 输入与体检

| 项 | 值 |
|---|---:|
| `gs_orders` 总行数 | 407,898 |
| `gs_orders` 唯一 SKU | 2,553 |
| 已精确命中行 / 唯一 SKU | 403,783 / 2,256（88.4%） |
| 未命中行 / 唯一 SKU | 4,115 / 297 |
| 未命中数量（qty 求和） | 4,362（占总量 1.005%） |
| 订单月份范围 | 202301–202609 |
| `gs_orders.source` | 仅 `gs` 一种 |
| `sku_map.tsv` 行 / 唯一 `tongtool_sku` | 4,236 / 3,482 |
| DuckDB `sku_map` 表行数 | 3,482 |
| 表相对 TSV 丢失的 (item, tt) 对 | **10**（表按 `tongtool_sku` 去重，见 §5.2） |
| 同一 `tongtool_sku` 映射多个 `item_code` | 8 个键 |
| 同一 `item_code` 挂多个 `tongtool_sku` | 755 个（最多 11 个别名） |
| EN `ref_code` 带删除/作废前缀的键 | 169 个原始键（前缀剥离后 168 个） |

异常扫描：297 个未匹配 SKU 中**没有**空值、首尾空格、双空格、非 ASCII 或大小写仅差异的编码；因此 `insufficient_evidence` 不来自「格式坏」，而只来自「alias 被标记删除」（§3.4）。

## 3. 四分类结果

| 分类 | 唯一 SKU | 订单行 | 占比(行) | qty | 首月 | 末月 | 建议动作 |
|---|---:|---:|---:|---:|---|---|---|
| `base_candidate` | 61 | 180 | 4.4% | 186 | 202301 | 202609 | register_candidate 42 / manual_review 19 |
| `duplicate_mapping` | 2 | 177 | 4.3% | 205 | 202501 | 202511 | manual_review 2 |
| `true_missing` | 228 | 2,957 | 71.9% | 3,306 | 202301 | 202609 | register_candidate 107 / manual_review 121 |
| `insufficient_evidence` | 6 | 801 | 19.5% | 665 | 202504 | 202512 | manual_review 6 |
| **合计** | **297** | **4,115** | **100%** | **4,362** | 202301 | 202609 | — |

### 3.1 `base_candidate`（61 个 / 180 行）

剥离规则只用「可识别形状」的尾段，且**多位数字尺码一律不剥**，避免把 138 误配到 140：

| 尾段类型 | SKU 数 | 说明 |
|---|---:|---|
| `-Cover` | 39 | 含 1 个 `-Cover-out` 两段剥离 |
| `-Foam` | 1 | `TT0312687K0064377-Foam` |
| `-out` | 1 | `CENVel1612-Black-194-Cover-out` → `...-Cover` |
| `-Clip` | 1 | `TT0020018K0062867-Clip` |
| 单位数字 `-N`（0–9） | 11 | Shopify 变体序号，如 `-1/-2/-3/-0` |
| 长度后缀（`-60cm/-140cm`） | 2 | |
| 纯字母变体值 | 6 | `-seat-belt`×2、`-lavender/-pansy/-lilac/-pink` |

每个候选都命中**恰好 1 个** `item_code`，无歧义候选。示例：

| SKU | 行数 | 首–末月 | 候选基础码 | 候选 item_code | 行键（示例） |
|---|---:|---|---|---|---|
| `TT0031246K0064094-2` | 20 | 202507–202511 | `TT0031246K0064094` | KS0375-CTTM-120x200x84-CREAMYBEIGE | 202507:13073 |
| `TT0312687K0064377-Cover` | 12 | 202608–202609 | `TT0312687K0064377` | KS0495-FHXWXNERSZSRB-143x84x88-DARKRED | 202608:10205 |
| `TT0312687K0064377-Foam` | 11 | 202608–202609 | `TT0312687K0064377` | KS0495-FHXWXNERSZSRB-143x84x88-DARKRED | 202608:10206 |
| `TT0031247K0064095-1` | 9 | 202507–202511 | `TT0031247K0064095` | KS0395-CTTM-218x115x55-CREAMYBEIGE | 202507:13079 |
| `TT0031008K0062868-2` | 8 | 202501–202503 | `TT0031008K0062868` | KS0119-KJB-220-WHITE | 202501:5983 |
| `TT0031247K0064095-2` | 8 | 202507–202511 | `TT0031247K0064095` | KS0395-CTTM-218x115x55-CREAMYBEIGE | 202507:13081 |
| `TT0031247K0064095-3` | 8 | 202507–202511 | `TT0031247K0064095` | KS0395-CTTM-218x115x55-CREAMYBEIGE | 202507:13083 |
| `C/Cord-White-138-706-wow-Cover` | 7 | 202605–202609 | `C/Cord-White-138-706-wow` | KS0001-CMKTR-140-WHITE | 202605:2513 |
| `TT0020013K0062821-seat-belt` | 7 | 202305–202508 | `TT0020013K0062821` | KS0118-ZQTW-7652-NAVYSTRIPE | 202305:6590 |
| `C/Velvet-DKBlue-100-700-wow-Cover` | 6 | 202602–202608 | `C/Velvet-DKBlue-100-700-wow` | KS0001-PR-100-DEEPBLUE | 202602:2026 |

> **尺码口径提示（不改）**：9 个候选的 alias 尺码与 item_code 尺码不一致，且全部是 EN 既有登记：
> `138 → 140`（7 个，如 `CEN-No/B-Velvet-Grey-138-Cover → KS0248-HLR-140-GREY`）、`97 → 100`（2 个）。
> 这是现存映射口径问题，不是本次候选规则造成的；需人工确认后另行处理，本审计未做任何修改。

### 3.2 `duplicate_mapping`（2 个 / 177 行，全部列出）

| SKU | 行数 | 首–末月 | 冲突形态 | 候选 item_code |
|---|---:|---|---|---|
| `Curve-Pillow-Foam-50` | 118 | 202501–202511 | EN 仅有 `删除Curve-Pillow-Foam-50`，且指向 2 个 HM1510；同时是 `Curve-Pillow-50-Foam`（3 个 KS）的 token 换序 | HM1510-YD2-50x22x55-WHITE; HM1510-YD2-LLK50x22x55-WHITE |
| `Curve-Pillow-PPCotton-50` | 59 | 202501–202511 | `Curve-Pillow-50-PPCotton` 的 token 换序，该键映射 3 个 KS | KS0340-DM-50-DEEPBLUE; KS0340-DM-50-YELLOW; KS0340-HLR-50-GREY |

两者都属于 50 码 Curve Pillow，同一 alias 对应 2–3 个成品/皮壳物料，**不能自动认领**；需要业务方按颜色/规格定唯一对应。

### 3.3 `true_missing`（228 个 / 2,957 行）

定义：`ref_code` 里没有任何登记（基础码与后缀变体都没有），且无仅删除 alias、无 token 换序兄弟。

模式（互有重叠，仅作定位用）：

| 模式 | SKU 数 | 行数 |
|---|---:|---:|
| 以 `#qc` 结尾（质检别名） | 49 | 292 |
| `JYFBA / BNFBA / SGUSFBA / VUSFBA / YXCFBA` 前缀 | 70 | 344 |
| 以 `-Cover` 结尾（皮壳别名未登记） | 48 | 312 |
| `T2398P…` / `W…` 平台编码 | 36 | 82 |
| `XINGQIU-*` | 3 | 454 |
| 形似 ASIN（`B0…`/`X0…`） | 3 | 51 |
| 自身未登记但带后缀的子别名已登记 | 12 | — |

Top 10（按行数）：

| SKU | 行数 | 首–末月 | 证据 |
|---|---:|---|---|
| `YCSOFA001` | 234 | 202510–202602 | no_suffix_candidate |
| `XINGQIU-Jupiter-10` | 171 | 202301–202508 | no_suffix_candidate |
| `XINGQIU-Jupiter-16` | 149 | 202301–202504 | no_suffix_candidate |
| `CEN003-NZAIBLUE-100` | 134 | 202301–202312 | no_suffix_candidate |
| `XINGQIU-Earth-10` | 134 | 202301–202412 | no_suffix_candidate |
| `FBA-duo` | 120 | 202301–202409 | no_suffix_candidate |
| `CEN-No/B-Velvet-Grey-100` | 116 | 202301–202408 | no_suffix_candidate |
| `petcushionjp-76` | 99 | 202305–202307 | no_suffix_candidate |
| `CEN-No/B-Velvet-Grey-194` | 85 | 202302–202410 | no_suffix_candidate |
| `BAI20019N0A62887SX-FBA` | 78 | 202401–202502 | no_suffix_candidate |

> **命名警告**：`true_missing` 只表示「EN 客户物料明细里没有这条 ref_code alias」，**不等于 EN 没有这个物料**。
> 本次没有查询 EN Item master（任务禁止访问生产），因此不能推断商品是否存在，只能推断 alias 缺失。

### 3.4 `insufficient_evidence`（6 个 / 801 行，全部列出）

全部是「alias 存在但被标记删除」——有证据、但证据指向「已删除」，无法据此认领：

| SKU | 行数 | 首–末月 | 仅存 alias → item_code | 建议 |
|---|---:|---|---|---|
| `TT0031245K0064088` | 553 | 202504–202512 | `删除TT0031245K0064088` → HM1510-YD2-135x152x80-WHITE | manual_review |
| `TT0031245K0064088-0` | 236 | 202504–202511 | `删除TT0031245K0064088-0` → KS0394-CTTM-135x152x80-REDDISHGRAY | manual_review |
| `TT0031230K0064056` | 4 | 202504–202509 | `删除TT0031230K0064056` → HM1510-YD2-76x90x36+76x67x30-WHITE | manual_review |
| `TT0031230K0064057` | 3 | 202507–202509 | `删除TT0031230K0064057` → HM1510-YD2-76x90x36+76x67x30cm-WHITE | manual_review |
| `TT0031230K0064058` | 3 | 202507–202509 | `删除TT0031230K0064058` → HM1510-YD2-76x90x36+76x34x30-WHITE | manual_review |
| `TT0312589K0064187` | 2 | 202509–202511 | `删除TT0312589K0064187` → HM1510-YD3-55x55x40-WHITE | manual_review |

`TT0031245K0064088` + `-0` 合计 **789 行（19.2%）**，是本次最大单点；`-0` 与其基码指向**不同** item_code（KS0394 vs HM1510），不能当成同一物料的包装差异处理。

## 4. 深度审计（100 个唯一 SKU）

选法：先**全量纳入**三个小类（base_candidate 61 + duplicate_mapping 2 + insufficient_evidence 6 = 69），
再按订单行数补 31 个 `true_missing`，按行数排序输出。四类均有覆盖。

产物：`out/sku_match_audit/deep100.md`（本地，未提交）。每个 SKU 含原始码、候选基础码、候选 item_code、
命中/未命中证据、行数、首末月、建议动作。`register_candidate` **只表示建议人工登记，没有写 EN**。

## 5. 冲突与异常（单列，均未修改）

### 5.1 已删除 alias 与未匹配 SKU 的交集：8 个
除 §3.4 的 6 个 `insufficient_evidence` 外，另有：
- `Curve-Pillow-Foam-50` → 归入 `duplicate_mapping`（删除 alias 指向 2 个 item_code）；
- `TT0000995K0010979-60cm` → 归入 `base_candidate` 但动作降为 `manual_review`：
  基础码 `TT0000995K0010979` 有活映射（KS0001-QDKTR-60-DEEPGREY），但其**精确 alias 被标记 `已删除`**，
  删除意图需人工确认。

### 5.2 DuckDB `sku_map` 表丢失 10 条别名对（8 个键）
`sku_map.tsv` 有 4,236 对，表只有 3,482 行（按 `tongtool_sku` 去重），丢失的 10 对：

`TT0031177K0063900-Cover`、`TT0031178K0063902-Cover`、`TT0031186K0063918-Cover`、`TT0031187K0063920-Cover`、
`TT0031188K0063922-Cover`、`Curve-Pillow-50-Foam`、`Curve-Pillow-50-PPCotton`、`删除Curve-Pillow-Foam-50`，
各丢失 1–2 个 `item_code`。

**影响**：精确命中的 SKU 集合不变，但这 8 个 alias 在**已命中**订单里会被解析成任意一个 item_code。
受影响的已命中订单行共 **231 行**（`Curve-Pillow-50-Foam` 90、`Curve-Pillow-50-PPCotton` 72、5 个 `-Cover` 键 69）。
另 `TT0031186K0063918-Cover` 的歧义还波及一个未匹配 SKU（`TT0031186K0063918`，26 行）。
建议单独开卡：要么在映射表保留全部别名并显式裁决，要么在管道里拒绝歧义而不是静默取一条。

### 5.3 EN `ref_code` 里 169 个删除/作废标记
前缀分布：`已删除` 114、`删除` 55（剥离后 168 个不同键）。这是 EN 侧的别名生命周期数据质量问题：
标记没有移除别名，而是拼进了编码本身，导致下游精确匹配同时出现「误命中」与「无法命中」。本次只读、未清理。

### 5.4 尺码口径不一致的既有映射：9 个 base_candidate
见 §3.1 提示；只列不改。`138→140` 与 `97→100` 是否为有意归一，需 EN 归属人确认。

### 5.5 大小写/空白异常：0 个
297 个未匹配 SKU 中，无一可通过大小写或去空格与 `sku_map` 键相等；本次也没有做此类容错。

## 6. 缺口（本审计无法回答的）

1. **旧 6,549 无法本地复算**：`en_orders` 无 SKU 列；EN 侧口径需另开只读审计（需 EN API 权限）。
2. **只能看 alias，看不到 EN 物料主数据**：因此 `true_missing` 不等于「EN 没有该商品」。
3. **只有 GS 订单源**（`source` 全为 `gs`）：未覆盖通途原始订单/采购/库存侧。未匹配行的渠道分布：
   Amazon 2,395 行 / 228 SKU（58% 的行、77% 的 SKU）、TiktokUS 603 行 / 7 SKU、Wayfair 228 / 31、
   tiktok 178 / 18、BESTBUY 160 / 22、Walmart 160 / 21、OSTK 106 / 27、Shopify 88 / 21，其余每渠道 ≤52 行。
4. **删除标记的语义未知**（谁、何时、为何删）：需 EN 归属人给出规则，否则 §3.4 无法收敛。
5. **qty 为原始订单行数量**，未做 UOM/套件拆分；本审计不对数量口径下结论。
6. **未验证生产**：没有调用通途/EN，没有写 EN 数据，没有改 `sku_map`。

## 7. 验收对账（全部通过）

| 检查 | 结果 |
|---|---|
| 输入行 = 已命中 + 未命中 | 403,783 + 4,115 = 407,898 ✅ |
| 唯一 SKU = 四类之和 | 61 + 2 + 228 + 6 = 297 ✅ |
| 订单行 = 四类之和 | 180 + 177 + 2,957 + 801 = 4,115 ✅ |
| qty 合计一致 | 4,362 = 4,362 ✅ |
| CSV 行数 = 4,115，`line_id` 唯一 4,115 | ✅ |
| CSV 唯一 SKU = 297，无 SKU 跨类 | ✅ |
| 深审 100 覆盖四类 | ✅（61/2/6/31） |
| 每个 base_candidate 都有基础码 + item_code 证据 | ✅ 61/61 |
| 无模糊认领（候选只记不写） | ✅ |
| 旧命中映射未修改 | ✅ `sku_map` 只读，无写入 |

## 8. 产物与复现

| 产物 | 位置 | 说明 |
|---|---|---|
| 全部未匹配行 | `out/sku_match_audit/unmatched_all.csv` | 4,115 行，含分类/候选/证据/动作；本地，未提交 |
| 计数对账 | `out/sku_match_audit/categories.json` | 四类计数、首末月、示例、逐 SKU 明细、reconciliation |
| 深度表 | `out/sku_match_audit/deep100.md` | 100 个唯一 SKU，四类覆盖 |
| 复现脚本 | `scripts/audit_sku_match.py` | `read_only=True`；重跑即重新对账，失败即非零退出 |

原始行键：`line_id`（格式 `YYYYMM:序号`，在 `gs_orders` 中唯一）。报告只放聚合与示例，
未提交原始订单明细（`out/` 已被 `.gitignore` 忽略）。

## 9. 用时

任务书落盘 08:59:44 → 本报告完稿约 09:07，**实际墙钟约 8 分钟**，远低于 90 分钟上限。
没有因超时产生缺口表；§6 的缺口是权限/数据边界，不是时间不够。
