---
okf: v0.1
type: Research
title: 跨仓直接发货更正 + 双仓销售分析（2026-10-29）
description: 美东/美中不互调、有库存可直接发货；v6 归属表加双仓销售（25 个双仓、11 个实质）
tags: [warehouse, direct-ship, dual-warehouse, attribution]
date: 2026-10-29
status: delivered-readonly
---

# 跨仓直接发货更正 + 双仓销售分析

## 1. 救急/近端表 v2→v3（表述更正）

- 美东 ↔ 美中**不是调拨**：没有调拨流程；另一仓有库存时**跨仓直接发货**给目的仓的订单，
  需确认**源仓可售 / 退货品质**。列名改为 `建议跨仓直发上限` / `跨仓直发后仍缺` / `同国来源仓`，
  新增 `履约方式`。
- `KS0002-CMPR-194-GINGER`：**美中 2 个可直接履约，剩余 2 仍缺**（v2 误写调后 0）。
- 波兰/跨洲规则与总量不变：48 行、参考合计 407.220、直发上限 2.000、直发后剩余 405.220。
- 产物：`analysis/46近端缺口_调拨候选_2026-10-28_v3.csv` + 报告 v3。

## 2. 归属表 v5→v6（双仓销售）

- 2026 美东>0 且美中>0：**25 个**；两边各 ≥10% 总销量 = **实质双仓 11 个**，其余 14 个少量双仓。
- v6 在 `1_美国归属与补货` 追加 `双仓销售2026` / `双仓销售近6月` / `双仓判定（实质/少量/单仓）`；
  实质双仓 11 行的「美国归属」「美国补货建议」改为「双仓销售：美东X/美中Y，按两仓分别补/核」；
  少量双仓 14 行在「运营备注」注明另一仓占比，仍按主仓。
- 新增 sheet `11_双仓销售`（25 行 + 阈值）；`0_说明` 追加 v6 变更。
- 实质双仓 11 个：DM-153/194/140 IVORY、DM-153 GREY、DM-140 GREY、DM-100 YELLOW、
  QDKTR-140 DEEPGREY、CMYH-60 FOREST、CMYH-60 BLUEBUTTERFLY、LSR 70x70 BLUEFLOWERS、SET7 ROCKSTONE。
- v5 原文件保留；产物：`analysis/美国与波兰仓库归属_2026-10-28_v6.xlsx`；脚本
  `scripts/near_gap_transfer_candidates_v3.py`、`scripts/warehouse_attr_v6_dual_sales.py`。
