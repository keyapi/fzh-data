# 多件套登记审计 v2（2026-11-11）

只统计明确套件后缀：`-NPCS`、`-SETN`、`xN`、以及基础码为 TT 的 `-N`。

## 按状态

| 状态 | 平台SKU数 | 行 | 件数 | 套数 |
|---|---:|---:|---:|---:|
| bundle_and_platform_registered | 2 | 331 | 881 | 331.0 |
| bundle_registered_via_tt_code | 129 | 1375 | 7250 | 1339.6 |
| no_bundle_no_registration | 113 | 1131 | 2965 | 1150.3 |
| platform_registered_but_no_bundle | 5 | 27 | 186 | 28.0 |

## 套件已登记（TT 客户码 → TJ#）Top

| 套件 | 平台SKU数 | 件数 |
|---|---:|---:|
| TJ#KS0156x3-001 | 2.0 | 930 |
| TJ#KS0211x6-006 | 11.0 | 788 |
| TJ#KS0211x12-003 | 4.0 | 762 |
| TJ#KS0211x6-003 | 7.0 | 495 |
| TJ#KS0211x6-002 | 8.0 | 486 |
| TJ#KS0211x9-003 | 8.0 | 318 |
| TJ#KS0211x9-004 | 6.0 | 307 |
| TJ#KS0211x12-006 | 7.0 | 293 |
| TJ#KS0211x12-002 | 5.0 | 289 |
| TJ#KS0156x2-001 | 4.0 | 226 |
| TJ#KS0211x4-002 | 7.0 | 224 |
| TJ#KS0211x4-006 | 5.0 | 200 |
| TJ#KS0211x12-001 | 5.0 | 197 |
| TJ#KS0211x6-001 | 6.0 | 196 |
| TJ#KS0211x4-005 | 7.0 | 185 |
| TJ#KS0211x4-001 | 7.0 | 177 |
| TJ#KS0211x9-001 | 5.0 | 144 |
| TJ#KS0211x4-004 | 5.0 | 136 |
| TJ#KS0211x6-004 | 5.0 | 130 |
| TJ#KS0211x12-004 | 3.0 | 121 |

## 缺口 Top（无套件/平台码未登记）

| 通途基础码 | 每套件数 | 状态 | 平台SKU数 | 件数 |
|---|---:|---|---:|---:|
| TT0031073K0063250 | 3 | no_bundle_no_registration | 2.0 | 517 |
| TT0031099K0063666 | 2 | no_bundle_no_registration | 2.0 | 380 |
| TT0031073K0063251 | 3 | no_bundle_no_registration | 1.0 | 219 |
| TT0031073K0063250 | 2 | no_bundle_no_registration | 1.0 | 134 |
| TT0031073K0064138 | 3 | no_bundle_no_registration | 1.0 | 121 |
| TT0031073K0064139 | 3 | no_bundle_no_registration | 1.0 | 117 |
| TT0020052K0063680 | 2 | no_bundle_no_registration | 1.0 | 114 |
| PPL-BoneStone-7PCS | 7 | platform_registered_but_no_bundle | 1.0 | 84 |
| TT0020048K0063670 | 2 | no_bundle_no_registration | 6.0 | 74 |
| TT0031073K0063251 | 2 | no_bundle_no_registration | 1.0 | 69 |
| TT0009012K0009491 | 7 | no_bundle_no_registration | 1.0 | 63 |
| PPL-RockStone-7PCS | 7 | platform_registered_but_no_bundle | 1.0 | 63 |
| TT0031038K0064292 | 3 | no_bundle_no_registration | 1.0 | 62 |
| TT0312678K0064345 | 2 | no_bundle_no_registration | 2.0 | 59 |
| TT0000931K0011512 | 3 | no_bundle_no_registration | 1.0 | 51 |
| TT0312678K0064346 | 2 | no_bundle_no_registration | 3.0 | 48 |
| TT0031073K0064139 | 2 | no_bundle_no_registration | 1.0 | 43 |
| TT0009019K0009498 | 7 | no_bundle_no_registration | 1.0 | 42 |
| TT0312630K0064258 | 3 | no_bundle_no_registration | 2.0 | 36 |
| PPL-BlackStone-7PCS | 7 | no_bundle_no_registration | 1.0 | 35 |
| TT0312585K0064169 | 4 | no_bundle_no_registration | 1.0 | 32 |
| TT0031089K0063357-1 | 2 | no_bundle_no_registration | 2.0 | 30 |
| TT0031038K0064291 | 2 | no_bundle_no_registration | 2.0 | 29 |
| TT0312632K0064260 | 2 | no_bundle_no_registration | 2.0 | 28 |
| TT0009014K0009493 | 7 | no_bundle_no_registration | 1.0 | 28 |
| PPL-GreyStone-7PCS | 7 | platform_registered_but_no_bundle | 1.0 | 28 |
| TT0312632K0064260 | 3 | no_bundle_no_registration | 2.0 | 27 |
| TT0031038K0064292 | 2 | no_bundle_no_registration | 1.0 | 24 |
| TT0312576K0064150 | 2 | no_bundle_no_registration | 1.0 | 22 |
| TT0009017K0009496 | 7 | no_bundle_no_registration | 1.0 | 21 |

## 说明

- 通途订单 `qty` 是件数；套件客户码（如 `TT0031085K0063341-6pcs`）已在 EN 套件 `TJ#KS0211x6-006` 上登记。
- 平台 SKU（如 `SUK-PUHBEIGE60-6`）通常没有直接登记；它通过通途套件码映射，**不是必须直接登记**，但订单事实需要保留套件码，否则无法回溯套型。
- 平台码未登记的问题主要在报表/回溯，不等于 EN 套件缺失。

明细：`bundle_suffix_audit_v2_20261111.csv`。
## 软包墙围结论

- EN **有套件**：`TJ#KS0211x4/x6/x9/x12-*`；套件上已登记通途套件客户码，如 `TT0031085K0063341-6pcs`、`-4pcs`、`-9pcs`、`-12pcs`。
- 通途订单 `qty` 是**件数**（6 件套行 qty=6），所以件数需求本来是对的；缺的是订单事实保留套件码/套型。
- 平台 SKU（`SUK-PUHBEIGE60-6` 等）没有直接登记客户码，但通过通途套件码映射；不是必须直接登记，报表回溯需要保留套件码。
- **判定：软包墙围不是“EN 没登记套件”，而是“我们的订单事实/销量统计没有用套件码把套型带出来”。**

## 其他多件套缺口

- 仍有 **113 个平台 SKU / 2,965 件**找不到对应 EN 套件；典型：
  - `DanNB-Vel-hui-60-new-2PCS/3PCS`（TT0031073K0063250，645 件）——无套件；
  - `PPL-BoneStone/RockStone/BlackStone-7PCS`（7 件套）——有客户码但无套件；
  - `DDE-CYVarious-7pcs` 等 7 件套——无套件。
- 另有 5 个平台 SKU / 186 件已登记客户码但无套件。
- 这些需要 EN 建套件并登记套件客户码，否则补货只能按单件算，套型/套数不可见。

## 数量单位

- 83 个平台 SKU / 557 行是**按套下单**（qty≈1），当前订单事实按件处理会低估 2–7 倍；已加 `qty_pieces = qty × pcs_per_set`。
- 2026 年影响：+220 件（全部美国；波兰 0），历史 +930 件（0.25%）；v5.5 波兰结论不变，下一版可直接用 `orders_unified_20261111_v2.parquet` + D3b v3.10。
