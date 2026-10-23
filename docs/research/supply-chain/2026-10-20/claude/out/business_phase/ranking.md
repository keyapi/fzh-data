---
okf: v0.1
type: Report
title: Phase 1B 销量口径与排序（1,237 合格映射 SKU）
date: 2026-10-22
owner: claude-worker
status: sales metric + ranking only; no quantity, no fill call
inputs:
  - out/business_phase/destinations.json（44def7f5，只读）
  - D:/Work/fzh-order-store/order_store.duckdb（read_only）
artifacts:
  - experiments/business_phase/build_ranking.py
  - out/business_phase/ranking.json
---

# Phase 1B：销量口径冻结与排序

> 只做口径与排序：**不出补货数量、不判补/不补**。

## 1. 口径（机器可读字段见 JSON `metric`）

- 窗口：**2026-04..2026-09**（6 个完整月），日期字段 **despatch_date**；`sale_date` 口径会得到 1,326 而非 1,328 个 SKU（差 2 个），已记录且不切换。
- 净销量 = 已发货数量 − 退货/取消；本快照窗口内 **0 条负数量行**、1 条 0 数量行，`gs_orders` 无状态字段，故净销量=已发货，已声明而非默认。
- 测试单排除：`platform_sku` 命中 `(^|[-_])test([-_]|$)` 的行 —— 剔除 **5** 行 / 6 件，涉及 2 个 SKU（这些 SKU 仍有非测试销量，不会因此掉出表）。
- 内部调拨排除：`warehouse/account/channel` 命中 `调拨|transfer|内部|internal` —— **0** 行（查过为 0，保留判据可复算）。
- 零填充：每个 SKU 都带 6 个月，无行月份 `rows=0, qty=0, zero_filled=true`。
- 套件/单位：合格的 1,237 个物料 BOM 单位均为 件/个/套；窗口内 **0 条 TJ# 套件销售行**，故不存在套件与组成件重复计入。

## 2. 分层依据与占比

用两个维度判断是否被单一维度主导（阈值 50%）：品类 top-1 占比 **63.2%**（三角靠枕），仓 top-1 占比 **31.3%**（CENTRADE）。因此按 **item_group** 分层，层内排序，Top50 名额按层占比分配。

| 层 | 占比 | 名额 | 合格 SKU 数 | 实际入选 |
|---|---:|---:|---:|---:|
| 三角靠枕 | 63.2% | 32 | 464 | 32 |
| 三角靠枕无扣 | 6.7% | 4 | 91 | 4 |
| 软包墙围 | 2.9% | 2 | 6 | 2 |
| 平条靠枕 | 2.8% | 2 | 114 | 2 |
| 身体支撑阅读枕 | 2.0% | 1 | 2 | 1 |
| 沙发支撑垫 | 1.6% | 1 | 3 | 1 |
| 车载宠物窝 | 1.6% | 1 | 5 | 1 |
| 弧形PP棉靠枕 | 1.6% | 1 | 60 | 1 |
| 主体骨架 | 1.4% | 1 | 1 | 1 |
| 床楔形枕头 | 1.1% | 1 | 16 | 1 |
| 三角带圆柱靠枕 | 0.9% | 1 | 5 | 1 |
| 平条靠枕无压条 | 0.9% | 1 | 20 | 1 |

（共 226 层，完整占比见 JSON。）

## 3. Top 50

| # | SKU | 品类/层 | 净销量 | 层内名次 | 零库存有销量 | 部分履约 |
|---:|---|---|---:|---:|---|---|
| 1 | `CENCord995-DKGrey-97` | 三角靠枕 | 801 | 1 |  |  |
| 2 | `TT0031038K0062927` | 沙发支撑垫 | 707 | 1 |  | 是 |
| 3 | `CEN003-DPBLUE-100` | 三角靠枕 | 704 | 2 |  |  |
| 4 | `C/Linen-Natural-100-688-wow` | 三角靠枕 | 675 | 3 |  |  |
| 5 | `TT0312701K0064561` | 主体骨架 | 670 | 1 |  |  |
| 6 | `C/Linen-Natural-194-688-wow` | 三角靠枕 | 643 | 4 |  |  |
| 7 | `C/Cord-DKBlue-100-713-wow` | 三角靠枕 | 631 | 5 |  |  |
| 8 | `C/Linen-Natural-153-688-wow` | 三角靠枕 | 627 | 6 |  |  |
| 9 | `C/Cord-Grey-100-710-wow` | 三角靠枕 | 583 | 7 |  |  |
| 10 | `C/Velvet-Grey-100-705-wow` | 三角靠枕 | 581 | 8 |  |  |
| 11 | `TT0000671K0063721` | 三角靠枕 | 535 | 9 |  |  |
| 12 | `CENKZ15389463-Grey-100` | 三角靠枕 | 499 | 10 |  |  |
| 13 | `TT0312614K0064239` | 身体支撑阅读枕 | 497 | 1 |  |  |
| 14 | `C/Linen-White-100-662-WOW` | 三角靠枕 | 496 | 11 |  |  |
| 15 | `TT0000668K0063796` | 三角靠枕 | 490 | 12 |  |  |
| 16 | `CEN1607NLinen-Ivory-153` | 三角靠枕 | 467 | 13 |  |  |
| 17 | `CENKZ15389465-Grey-150` | 三角靠枕 | 463 | 14 |  |  |
| 18 | `CENKZ1323-LTGrey-97` | 三角靠枕 | 456 | 15 |  |  |
| 19 | `C/Cord-White-100-706-wow` | 三角靠枕 | 454 | 16 |  |  |
| 20 | `CENKZ159410289-BLACK-153` | 三角靠枕 | 449 | 17 |  |  |
| 21 | `CEN1607NLinen-Ivory-194` | 三角靠枕 | 423 | 18 |  |  |
| 22 | `CENKZ159410287-BLACK-97` | 三角靠枕 | 422 | 19 |  |  |
| 23 | `C/Velvet-Black-100-703-wow` | 三角靠枕 | 405 | 20 |  |  |
| 24 | `CEN1607NLinen-Ivory-97` | 三角靠枕 | 405 | 21 | 是 |  |
| 25 | `TT0031085K0063342` | 软包墙围 | 400 | 1 |  |  |
| 26 | `C/Velvet-White-100-664-wow` | 三角靠枕 | 395 | 22 | 是 |  |
| 27 | `CENKZ15349435-DBlue-100` | 三角靠枕 | 395 | 23 | 是 |  |
| 28 | `TT0031099K0063666` | 侧睡两用楔形枕 | 386 | 1 |  |  |
| 29 | `C/Velvet-DKBlue-100-700-wow` | 三角靠枕 | 380 | 24 |  |  |
| 30 | `C/Linen-DKBlue-100-660-WOW` | 三角靠枕 | 350 | 25 |  |  |
| 31 | `CEN-No/B-967-Linen-Beige-194` | 三角靠枕无扣 | 337 | 1 |  |  |
| 32 | `TT0031085K0063341` | 软包墙围 | 337 | 2 |  |  |
| 33 | `C/Cord-Black-100-707-wow` | 三角靠枕 | 336 | 26 |  |  |
| 34 | `CEN961NLinen-SageGreen-153` | 三角靠枕 | 300 | 27 |  |  |
| 35 | `CEN961NLinen-SageGreen-194` | 三角靠枕 | 284 | 28 |  |  |
| 36 | `TT0020013K0062821` | 车载宠物窝 | 277 | 1 |  | 是 |
| 37 | `TT0000671K0063724` | 三角靠枕 | 254 | 29 |  |  |
| 38 | `C/Linen-Natural-138-688-wow` | 三角靠枕 | 253 | 30 |  |  |
| 39 | `C/Linen-DKGrey-100-651-WOW` | 三角靠枕 | 240 | 31 |  |  |
| 40 | `CENC/Linen-Ivory-60` | 三角靠枕无扣 | 238 | 2 |  |  |
| 41 | `CEN1607NLinen-Ivory-138` | 三角靠枕 | 236 | 32 |  |  |
| 42 | `CENC/Linen-Grey-60CM` | 三角靠枕无扣 | 211 | 3 |  |  |
| 43 | `CEN-No/B-967-Linen-Beige-100` | 三角靠枕无扣 | 200 | 4 |  |  |
| 44 | `TT0031073K0063250` | 沙发床头靠枕 | 128 | 1 |  |  |
| 45 | `TT0000933K0011516` | 三角带圆柱靠枕 | 118 | 1 |  | 是 |
| 46 | `PTC/Linen-Natural-194-681-wow` | 平条靠枕无压条 | 105 | 1 |  |  |
| 47 | `TT0031010K0062880` | 床楔形枕头 | 104 | 1 | 是 |  |
| 48 | `TT0000752K0062993` | 平条靠枕 | 68 | 1 | 是 |  |
| 49 | `TT0000750K0063009` | 平条靠枕 | 65 | 2 |  |  |
| 50 | `TT0000914K0011634` | 弧形PP棉靠枕 | 62 | 1 |  |  |

## 4. 紧急履约例外（不按销量排序，逐条给证据）

触发条件：`stock_latest.waiting_shipment>0`（有待发订单=可观测的未履约需求），`v_stockout_observed` 只作辅助证据（零库存观测本身不等于未履约）。共 **75** 条（母集内 37、母集外 38；其中 37 条在合格集内）。

| SKU | 去向 | 待发件 | 断货观测行 | 证据 |
|---|---|---:|---:|---|
| `TT0031038K0062927` | mapped_eligible | 5 | 1 | stock_latest[sku='TT0031038K0062927'] waiting=5 warehouses=[{'warehouse': '波兰-FZHPoland-co |
| `TT0000931K0011512` | mapped_eligible | 3 | 2 | stock_latest[sku='TT0000931K0011512'] waiting=3 warehouses=[{'warehouse': '波兰-FZHPoland-co |
| `CENC/Linen-Yellow-60` | mapped_eligible | 2 | 3 | stock_latest[sku='CENC/Linen-Yellow-60'] waiting=2 warehouses=[{'warehouse': '美中-FZH-DANEE |
| `TT0000933K0011516` | mapped_eligible | 2 | 3 | stock_latest[sku='TT0000933K0011516'] waiting=2 warehouses=[{'warehouse': '波兰-FZHPoland-co |
| `TT0001325K0010667` | mapped_eligible | 2 | 1 | stock_latest[sku='TT0001325K0010667'] waiting=2 warehouses=[{'warehouse': '波兰-FZHPoland-co |
| `TT0031087K0063345` | mapped_eligible | 2 | 1 | stock_latest[sku='TT0031087K0063345'] waiting=2 warehouses=[{'warehouse': '波兰-FZHPoland-co |
| `C/Linen-DKGrey-60-651-WOW` | mapped_eligible | 2 | 0 | stock_latest[sku='C/Linen-DKGrey-60-651-WOW'] waiting=2 warehouses=[{'warehouse': '美东-CENT |
| `TT0000758K0062945` | mapped_eligible | 2 | 0 | stock_latest[sku='TT0000758K0062945'] waiting=2 warehouses=[{'warehouse': '波兰-FZHPoland-co |
| `TT0000995K0010982` | mapped_eligible | 2 | 0 | stock_latest[sku='TT0000995K0010982'] waiting=2 warehouses=[{'warehouse': '波兰-FZHPoland-co |
| `TT0020013K0062821` | mapped_eligible | 1 | 3 | stock_latest[sku='TT0020013K0062821'] waiting=1 warehouses=[{'warehouse': '波兰-FZHPoland-co |
| `CENKZ15349436-DBlue-138-DN` | mapped_eligible | 1 | 2 | stock_latest[sku='CENKZ15349436-DBlue-138-DN'] waiting=1 warehouses=[{'warehouse': '美中-FZH |
| `KDHY-020-MAHUI-45CM` | mapped_eligible | 1 | 2 | stock_latest[sku='KDHY-020-MAHUI-45CM'] waiting=1 warehouses=[{'warehouse': '波兰-FZHPoland- |
| `TT0000668K0063798` | mapped_eligible | 1 | 2 | stock_latest[sku='TT0000668K0063798'] waiting=1 warehouses=[{'warehouse': '波兰-FZHPoland-co |
| `TT0020013K0062820` | mapped_eligible | 1 | 2 | stock_latest[sku='TT0020013K0062820'] waiting=1 warehouses=[{'warehouse': '波兰-FZHPoland-co |
| `C/Linen-White-153-662-WOW` | mapped_eligible | 1 | 1 | stock_latest[sku='C/Linen-White-153-662-WOW'] waiting=1 warehouses=[{'warehouse': '美东-CENT |
| `KZ0001325K0005896` | mapped_eligible | 1 | 1 | stock_latest[sku='KZ0001325K0005896'] waiting=1 warehouses=[{'warehouse': '波兰-FZHPoland-co |
| `TT0020019K0062887` | mapped_eligible | 1 | 1 | stock_latest[sku='TT0020019K0062887'] waiting=1 warehouses=[{'warehouse': '波兰-FZHPoland-co |
| `TT0020029K0063031` | mapped_eligible | 1 | 1 | stock_latest[sku='TT0020029K0063031'] waiting=1 warehouses=[{'warehouse': '波兰-FZHPoland-co |
| `TT0031010K0062877` | mapped_eligible | 1 | 1 | stock_latest[sku='TT0031010K0062877'] waiting=1 warehouses=[{'warehouse': '波兰-FZHPoland-co |
| `TT0031244K0064084-Cover` | mapped_eligible | 1 | 1 | stock_latest[sku='TT0031244K0064084-Cover'] waiting=1 warehouses=[{'warehouse': '波兰-FZHPol |
| … | 母集内其余 17 条见 JSON | | | |

母集外（同样有待发订单，说明紧急例外不能只看业务母集）：

| SKU | 待发件 | 断货观测行 | 证据 |
|---|---:|---:|---|
| `STPPW-04-2` | 16 | 1 | stock_latest[sku='STPPW-04-2'] waiting=16 warehouses=[{'warehouse': '美东-CENTRADE', 'waitin |
| `STPPW-08-2` | 7 | 1 | stock_latest[sku='STPPW-08-2'] waiting=7 warehouses=[{'warehouse': '美东-CENTRADE', 'waiting |
| `STPPW-02-2` | 6 | 1 | stock_latest[sku='STPPW-02-2'] waiting=6 warehouses=[{'warehouse': '美东-CENTRADE', 'waiting |
| `STPPW-01-1` | 5 | 1 | stock_latest[sku='STPPW-01-1'] waiting=5 warehouses=[{'warehouse': '美东-CENTRADE', 'waiting |
| `STPPW-01-2` | 5 | 1 | stock_latest[sku='STPPW-01-2'] waiting=5 warehouses=[{'warehouse': '美东-CENTRADE', 'waiting |
| `STPPW-04-1` | 5 | 1 | stock_latest[sku='STPPW-04-1'] waiting=5 warehouses=[{'warehouse': '美东-CENTRADE', 'waiting |
| `STPPW-06-2` | 5 | 1 | stock_latest[sku='STPPW-06-2'] waiting=5 warehouses=[{'warehouse': '美东-CENTRADE', 'waiting |
| `STPPW-08-1` | 5 | 1 | stock_latest[sku='STPPW-08-1'] waiting=5 warehouses=[{'warehouse': '美东-CENTRADE', 'waiting |
| `STPPW-13-2` | 5 | 1 | stock_latest[sku='STPPW-13-2'] waiting=5 warehouses=[{'warehouse': '美东-CENTRADE', 'waiting |
| `STPPW-12-1` | 4 | 1 | stock_latest[sku='STPPW-12-1'] waiting=4 warehouses=[{'warehouse': '美东-CENTRADE', 'waiting |
| … | 其余 28 条见 JSON | | |

## 5. 合格集外的高销量候选（单列，绝不并入）

| SKU | 去向 | 原因码 | 净销量 |
|---|---|---|---:|
| `C/Linen-Natural-60-688-wow` | mapped_ineligible | uom_unknown | 60 |
| `TT0031112K0063740` | mapped_ineligible | uom_unknown | 50 |
| `TT0031112K0063739` | mapped_ineligible | uom_unknown | 42 |
| `C/Leaves-Grey-153-684-wow` | mapped_ineligible | uom_unknown | 20 |
| `CEN963Velvet-DKGreen-138` | mapped_ineligible | uom_unknown | 18 |
| `C/Leaves-Grey-183-684-wow` | mapped_ineligible | uom_unknown | 17 |
| `TT0031112K0063738` | mapped_ineligible | uom_unknown | 17 |
| `Buttonkit` | unmapped | unmapped | 16 |
| `C/Leaves-Grey-138-684-wow` | mapped_ineligible | uom_unknown | 14 |
| `PP10LB` | unmapped | unmapped | 13 |
| `TT0031102-zuhe-all` | mapped_ineligible | uom_unknown | 13 |
| `T2398P154418` | unmapped | unmapped | 12 |
| `TT0312639K0064284` | mapped_ineligible | uom_unknown | 12 |
| `TT0312687K0064377-Cover` | unmapped | unmapped | 12 |
| `TT0312687K0064377-Foam` | unmapped | unmapped | 11 |
| `C/Leaves-Grey-100-684-wow` | mapped_ineligible | uom_unknown | 9 |
| `PP5LB` | unmapped | unmapped | 9 |
| `SXQC-CEN003-ROBLUE-150` | mapped_ineligible | uom_unknown | 9 |
| `TT0031112K0063742` | mapped_ineligible | uom_unknown | 9 |
| `C/Cord-White-138-706-wow-Cover` | unmapped | unmapped | 8 |

## 6. 对账

| 项 | 值 |
|---|---|
| 入 / 出 | 1,237 / 1237，0 丢弃 |
| 每月单元 | 1,237 × 6 = 7,422，全部带零填充标记 |
| Top50 | 50（名额按层占比，已断言无重复） |
| 紧急例外 | 75 |
| 合格集总净销量 | 48,001 |
| 两次运行 | 除 `generated_at` 外逐字节一致 |

## 7. 本阶段不做

- 不出补货数量、不判补/不补、不做提前期/供给/需求匹配。
- 不把销量排序当补货优先级；紧急履约例外只是证据清单。

