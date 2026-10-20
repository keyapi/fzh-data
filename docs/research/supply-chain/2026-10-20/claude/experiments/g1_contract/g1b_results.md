---
okf: v0.1
type: Experiment-Results
title: G1b 首版 — family 出库消耗 vs 两仓库存覆盖
description: 2026-04..09 family 出库消耗、通途 cutoff 库存、历史 run-rate 覆盖月数与头部 SKU 缺口；含 EN 单据试点
date: 2026-10-20
tags: [supply-chain, g1b, inventory, coverage, tongtool, erpnext]
---

# G1b 首版 — family 出库消耗 vs 两仓库存覆盖

> 口径：需求 = **family 出库消耗毛量（含补发货）**，不是会计销量；退货 5% 仅未来需求情景，
> **库存净算不二次冲减**（已回库在 `available`，未回库/报废也不冲减）。
> 供给 = 通途 cutoff 的 **available + intransit**（不含 defects/waiting）。
> 覆盖月数 = 供给 / 6 个月平均出库，是**历史 run-rate**，不是预测；美中受新运营 ramp 影响，只作指示。
> 全部只读；不写 EN 生产库存账。原始库存/单据 JSON 留在本地，不入库。

## 1. 需求（2026-04..09）

| 分公司/仓 | 出库消耗（件） | 占比 |
|---|---:|---:|
| 美东 USNJ / CENTRADE | 14,720 | 43.7% |
| 美中 USTX / DANEEY（含历史皮壳仓口径） | 14,860 | 44.1% |
| 波兰 PL | 2,812 | 8.3% |
| WayfairCG（下游 3PL） | 1,162 | 3.4% |
| Daneey 退货仓（正数出库销售） | 165 | 0.5% |
| **合计** | **33,719** | **100%** |

- 行数 32,888；补发货 66 行 / 72 件（已含在毛量中）。
- 月度（件）：

| 月 | USNJ | USTX | PL | WayfairCG | 退货仓 |
|---|---:|---:|---:|---:|---:|
| 2026-04 | 1,263 | 1,406 | 431 | 254 | 18 |
| 2026-05 | 1,545 | 1,755 | 390 | 214 | 7 |
| 2026-06 | 3,050 | 2,581 | 371 | 112 | 45 |
| 2026-07 | 3,562 | 3,383 | 433 | 317 | 4 |
| 2026-08 | 3,648 | 4,213 | 629 | 144 | 36 |
| 2026-09 | 1,652 | 1,522 | 558 | 121 | 55 |

- 6–8 月明显冲高、9 月回落；这与 WX 说的新品/新运营 ramp、夏季节奏一致。
  **不能把 6 个月平均直接当稳定需求**，尤其美中。

## 2. 库存快照（通途 cutoff 2026-10-20）

| 仓 | family SKU | 可用 | 在途 | 次品 | 待发（已分配） |
|---|---:|---:|---:|---:|---:|
| 美东-CENTRADE | 478 | 9,877 | 4,504 | 80 | 49 |
| 美中-FZH-DANEEY | 337 | 8,492 | 5,071 | 4 | 54 |
| ~~美中-FZH-DANEEY-皮壳仓库~~ | 0 | — | — | — | — |

> **仓名变更**：当前通途仓库列表里没有 `FZH-DANEEY-皮壳仓库` / `美中-FZH-DANEEY-皮壳仓库`
> 这个独立仓；历史订单侧的老名字已并入 `美中-FZH-DANEEY`。因此 DANEEY 的 8,492 可用 +
> 5,071 在途就是当前美中供给池，不再单独加皮壳仓。
> CENTRADE 快照：16 次分块请求，195.7 秒，0 错误；DANEEY：30 次请求，377.8 秒，0 错误；
> 13 秒节流避开 5 次/分钟限流。`waiting` 是已分配/待发，不计入可用供给，避免与 open order 重复。

## 3. 覆盖（首版）

| 分公司 | 供给状态 | 6 个月出库 | 月均 | 可用 | 在途 | on-hand 覆盖 | 含在途名义覆盖 |
|---|---|---:|---:|---:|---:|---:|---:|
| USNJ / CENTRADE | sampled | 14,720 | 2,453 | 9,877 | 4,504 | **4.03** | **5.86** |
| USTX / DANEEY | sampled | 14,860 | 2,477 | 8,492 | 5,071 | **3.43** | **5.48** |
| PL | sampled | 2,812 | 469 | 4,529 | 269 | **9.66** | **10.23** |
| WayfairCG | unknown | 1,162 | 194 | unknown | unknown | unknown | unknown |

> 在途没有 ETA，不能当作缺货前可到；`含在途` 只是名义覆盖，不是服务承诺。
> 3PL/退货仓不进入缺口统计；PL 已单独采样，WayfairCG 仍 unknown。

**完整快照重算（G1B01）**：USNJ/USTX/PL 均为 `sampled_complete`；
**131 个 branch×SKU 有需求无供给；194 个覆盖 <2 个月；127 个 supply unknown（WayfairCG/退货仓）**。
旧 450/501 撤回（它把未采样 PL/3PL/退货仓当零供给，且未按 branch×SKU 说明）。
WayfairCG `unknown`、退货仓 `demand_only` 不进入缺口；PL 已单独采样 9.66/10.24 个月。

USNJ 头部缺口：

| SKU | 6 个月出库 | 可用 | 在途 | 覆盖月数 |
|---|---:|---:|---:|---:|
| C/Linen-Natural-100-688-wow | 660 | 21 | 121 | 1.29 |
| C/Cord-DKBlue-100-713-wow | 627 | 6 | 120 | 1.21 |
| C/Velvet-Grey-100-705-wow | 581 | 38 | 0 | 0.39 |
| C/Cord-Grey-100-710-wow | 560 | 0 | 165 | 1.77 |
| C/Linen-White-100-662-WOW | 496 | 57 | 73 | 1.57 |
| C/Cord-White-100-706-wow | 449 | 2 | 112 | 1.52 |
| C/Velvet-Black-100-703-wow | 405 | 1 | 0 | 0.01 |
| C/Velvet-White-100-664-wow | 388 | 0 | 0 | 0.00 |

USTX 头部缺口：

| SKU | 6 个月出库 | 可用 | 在途 | 覆盖月数 |
|---|---:|---:|---:|---:|
| CENCord995-DKGrey-97 | 784 | 0 | 0 | 0.00 |
| CEN003-DPBLUE-100 | 703 | 1 | 0 | 0.01 |
| CENKZ1323-LTGrey-97 | 437 | 0 | 0 | 0.00 |
| CEN1607NLinen-Ivory-97 | 401 | 0 | 111 | 1.66 |
| TT0000667K0063805 | 227 | 2 | 30 | 0.85 |
| CENC/Linen-Grey-60CM | 211 | 51 | 0 | 1.45 |
| CENKZ15339426-TAN-60 | 164 | 28 | 0 | 1.02 |
| CENKZ1323-LTGrey-138 | 123 | 23 | 0 | 1.12 |
| CEN803NLinen-Black-194 | 112 | 19 | 0 | 1.02 |
| CENKZ15940285-BLACK-60 | 109 | 31 | 0 | 1.71 |

> 结论：**聚合覆盖会掩盖 SKU 级缺口**；补货决策必须下到 SKU × 仓，不能只看分公司总量。
> 其中 `C/Velvet-White-100-664-wow`、`CENCord995-DKGrey-97`、`CENKZ1323-LTGrey-97`
> 有出库但当前 0 供给，需先确认是改名/停产/漏映射还是真断货。

## 4. EN 单据试点（单个头部 SKU）

`C/Linen-Natural-194-688-wow` → BOM `KS0001-XMMBS-194-HEMPNATURAL`，
EN 订单行实际物料 `PK#KS0001-XMMBS-194-HEMPNATURAL`。

| 项 | 数值 |
|---|---:|
| SO | 26 张 |
| 订单量 / 有效 / 已发 / 未发 | 3,220 / 3,120 / 2,084 / 1,036 件 |
| 未发构成 | **死单 421 + 在产 622 + 无计划 9 + 超发 -16 = 1,036** |
| DN | 17 张 / 100 行；每行保留 `dn_line_id`（Delivery Note Item.name） |
| WO / Job Card | 22 张 / 555 张，覆盖 20 张 WO；按工序聚合，不跨工序求和 |
| Manufacture SE | 63 张（已提交）；按 WO 汇总成品入库量 |
| PP | 28 张（按物料过滤后 24 行） |

关键发现：

1. **`PK#` 码**：BOM 是 `KS...`，SO 行卖 `PK#KS...`；用 `--item KS...` 查不到，必须用客户码或 `KS → PK#` 映射。
2. **ERP `Closed` ≠ 已发完**：3 张 Closed 未发共 421 件，必须单列死单，不能当 open demand。
   未发 1,036 的互斥分解为死单 421 + 在产 622 + 无计划 9 + 超发 -16；
   旧报告 421+622=1,043 的差 7 已解释为 `+9`（无计划）与 `-16`（超发）的净额。
3. **未开工**：`WO-26-02663` 320 件、`WO-26-03128` 300 件工序卡为 0；`SO-26-00036` 9 件无生产计划。
4. **疑似重复单**：同物料同量同交货日两组，需业务确认改单/重下，不能直接相加。
5. **Job Card 是主要进度证据，但不能免验证**：按工序聚合、首道/末道分开；无 JC=unknown；
   WO 头部状态/`produced_qty` 不可当产出；产出用已提交 Manufacture SE 单独核对。

详见 [g1b_pilot.md](g1b_pilot.md)。

## 5. 结论与风险

1. **G1b 链路已跑通**：通途库存快照 + EN SO/DN/WO/JC/PP 结构化提取 + 出库消耗对账均可复现。
2. **两仓总量覆盖 5.86 / 5.48 个月（名义、含在途），on-hand 4.03 / 3.43**；
   完整快照重算：**131 个 branch×SKU 有需求无供给、194 个 <2 个月、127 个 supply unknown**
   （WayfairCG/退货仓不计入缺口）；补货必须按 SKU × 仓。
3. **Codex `852d7791` 三条硬约束已纳入**：
   ① **退货已计入库存时不得再次冲减**；当前库存净算不扣退货，5% 仅未来需求情景；
   ② **调拨完成 ≠ Wayfair 实收；历史供货占比 ≠ 当前库存归属**；当前库存用后台实盘，归属用近期调拨/unknown；
   ③ **美中 new cohort run-rate 要考虑 Listing 上架、有货曝光、断货**；5.48 个月只作指示，不是决策级预测。
4. **WayfairCG 库存仍是 unknown**；3PL 需求 1,162 件单独列，不能拿通途调拨当在手。
5. **退货 5% 只是未来需求情景**；已回库在 inventory，未回库不冲减；未来可从 Amazon 结算 V2/退货报表配置化。
6. **`PK#` 映射、死单、未开工、重复单**是 G1b 的四个硬异常类别，必须进异常清单。

## 6. 输入 manifest、逐行去向与守恒

### 6.1 输入 manifest

| 输入 | 来源 | 规模 | fetched_at / 版本 |
|---|---|---|---:|
| BOM | `EN产品BOM成本列表20261016.xlsx` | 3,700 行；family 1,739；有效客户码 1,486（排除含「已删除」）；0 歧义 | 2026-10-16 |
| 订单 | `2026年{4..9}月订单_order_cost_*.xlsx` | 6 文件；45,129 行 / 48,346 件 | 每月最新时间戳 |
| 库存 | 通途 `erp2_stocks_stocksquery`（每日 API 备份） | CENTRADE 2,072 行/21 页；DANEEY 1,024/11；PL 1,369/14；family 去重 1,140 | 2026-10-20 18:19 |
| EN 单据 | EN 生产只读 API | 1 SKU：26 SO / 100 DN 行 / 22 WO / 555 JC / 28 PP | 2026-10-20 |

### 6.2 逐行去向

| 输入 | used | pending / unmatched | out_of_scope / anomaly | 合计 |
|---|---:|---:|---:|---:|
| 订单行 | 32,888 family | 759 text-tri pending | 11,482（11,334 其余非 family + 148 非 family 退货仓） | 45,129 |
| 订单坏行 | 0 | bad_qty=0 / negative=0 / 非整数=0 / 缺 SKU=0 / 缺仓=0 | — | 45,129 |
| 库存行 | 1,140 family（CENTRADE 478 + DANEEY 337 + PL 565，去重后） | bad_values=0 / duplicate_conflicts=0 | 非 family 未进入 family 快照 | — |
| EN SO | 26 | 3 dead / 2 未开工 / 2 疑似重复（待业务确认） | — | 26 |

### 6.3 数量守恒

```text
45,129 = 32,888 + 759 + 11,334 + 148
48,346 = 33,719 + 925 + 13,550 + 152
33,719 = 33,452 (base) + 267 (Cover)
USNJ supply 14,381 = 9,877 available + 4,504 intransit
USTX supply 13,563 = 8,492 available + 5,071 intransit
```

### 6.4 假设 / unknown

| 项 | 状态 | 处理 |
|---|---|---|
| 三角退货率 5% | assumption, low | 仅未来需求情景；库存净算不二次冲减；未来从 Amazon 结算 V2/退货报表配置化 |
| WayfairCG 库存 | unknown | YTQ 后台手工导出；不拿调拨当在手 |
| WayfairCG 供货归属 | unknown/partial | 近期调拨单按 SKU/区间；历史占比不作当前归属 |
| 美中 run-rate | biased | 新运营/Listing ramp、有货曝光、断货；只作指示 |
| 平台库存 <=2 视为无货 | manual rule | 标 `censored/manual_low`；不补 0；记录调整事件（待建） |
| 皮壳仓 | **unverified** | 当前列表无该仓，但无 ID/改名/迁移/余额证据；见 [g1b_warehouse_evidence.md](g1b_warehouse_evidence.md) |
| 快照完整性 | legacy | 旧快照 0 错误但缺 `complete/page` 元信息；完整 API 备份重跑后更新缺口 |
| 浏览器 `stock.export` | cost template | 只产 `通途导入_头程运费_其他费用.xlsx`，不是库存数量；API 库存任务另立 |
| `PK#`/`ND#` | fact | SO 行用包装码；G1b 用客户码或 `KS → PK#` 映射 |
| 死单/未开工/重复单 | fact/anomaly | 单列；不计入 open demand/供给，不直接相加 |

## 7. 下一步

- 旧快照已拉；完整 API 快照重跑后更新缺口；皮壳仓合并 `unverified`。
- 选 top 10–20 个 SKU 跑 `g1b_en_extract.py`，把 SO/DN/WO/JC/PP 与库存覆盖按 SKU 对齐。
- 取 WayfairCG 后台库存 + 赛狐/通途调拨单，补 `3pl_supply_allocation`；
  调拨完成只当发出，不当实收；历史供货占比不当当前库存归属。
- 退货：5% 仅未来需求情景；未来从 Amazon 结算 V2/退货报表配置化，库存净算不二次冲减。
- **每日库存备份**：API 任务 `FZH-TongtuStockApiDaily` 每日 **05:17** →
  `D:/Work/库存备份/YYYY-MM-DD/`（JSONL + manifest）；浏览器 `FZH-TongtuAutoExport-stock` 02:17
  只产成本/头程模板，不是库存数量。
- 同时记录销售平台库存 <=2 的人工规则/调整事件，供 G2/G3 断货删失。
- 所有输出带 `source/fetched_at/confidence`；未匹配/死单/未开工/重复单单列，不静默修正。
