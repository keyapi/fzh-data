---
okf: v0.1
type: Reference
title: D/S2 冻结产物哈希索引（2026-11-03）
date: 2026-11-03
category: supply-chain
tags: [supply-chain, d-layer, s2, manifest, sha256]
---

# D/S2 冻结产物哈希索引（2026-11-03）

业务 Excel/Parquet 不入库；本表只登记文件名、SHA256 与关键行数，供独立审核时核对
脚本输出与结论数字。所有哈希均为 2026-11-03 本地冻结版本。

| 阶段 | 产物 | SHA256 | 关键计数 |
|---|---|---|---|
| D1b v2.3 | D_资格与契约_D1b_v2_3_2026-11-02.xlsx | `a92ae620db426fb2f18bb6ae5709c17a2e5c95619028713bd0237c72cdc1acd5` | 3,508 行 / 2,337 品；data_gap=0；policy 307；eligible 1,557 |
| D3b v3.5 | D_历史归一与回测_D3b_v3_5_2026-11-03.xlsx | `0a7a647be81f7563541418208ab9e29f770ae5815107e199313fce85607c3729` | as-of 1,853 序列；current-owner 1,749 键；B WAPE 0.5262 |
| D5 v6.3 | D5v6_3-full/D_概率与服务_D5_v6_3_2026-11-03.xlsx | `18964c6b87239f90b9b7d609a991d24dbb78279c3652651936d0d569d2fa42a7` | 1,749 键 / 3,498 预测；历史覆盖 95.38/94.75（97/157 天） |
| D6 v6.3 | D6v6_3-final/D_Top50沙盒_D6_v6_3_2026-11-03.xlsx | `3f2cd9b10fa488cabddaa673698290f7d019f5e4d9dc2f5b442f7cdfc4215352` | 1,749 需求键 + 307 policy；auto_order=false |
| D6 v6.4 | D6v6_4-final/D_Top50沙盒_D6_v6_4_2026-11-03.xlsx | `590552e41e5fe810785ac126b5bc10cc78186dd0da1d9ecd19a9678f40df7e4a` | 补 972 / 不补 347 / 观察 345 / 催已有 85（键数） |
| B2 范围 | business_category_scope_20261103.csv | `526614659a1c963a320ad1fab5c93a2760ca84acdf5de854cfd5ced14eae3abb` | USNJ_continue 238 / old_no_replenish 110 / owner_not_USNJ 523 |
| 老品 | old_products_scope_20261103.csv | `3426af2891ac29f8c3b2ab1c856286009a1ab25d2e0a3062037cc25d0aff1cdd` | 110 老品，50 个仍有库存 |
| S2.2 | S2_2-supply-chain-simulation/D_供应链联合模拟_S2_2_SL95_2026-11-03.xlsx | `bd488658d0b0a0635ca7ff93076492c97ffdb9ae2d074ea3f0da7a1541382b98` | 1,749 键；可模拟 478；快船 135 / 普船 1 / 空运 342 |
| S2.3 | S2_3-strategy-final/D_供应链策略_S2_3_2026-11-03.xlsx | `89187474b72bb3598ecc676b15ac6fa689941e8611c8ebdd07d22f3b226e3caf` | 可执行 332 / 复核 89 / 无路线 506 / 催后 ETA 未证 73 |
| S2.4 | S2_4-daily-inventory/D_S2_4每日库存验证_2026-11-03.xlsx | `0ddb6cd25c32fc6ead06d8f76741c712cdf0aa70bc44c8f21ab5a086291fbf23` | 332 中仅 154 达 95%；平均无断货 0.774 |
| S2.6 | S2_6-service-fix-v2/D_S2_6服务修正v2_2026-11-03.xlsx | `1b5b51a743ce320bb4f9b9e19c24661867753b6cba18e288b39c32662e58998d` | 178 失败；复核 145 / impossible 27 / 加量 4 / 升舱 2 |
| S2.8 | S2_8-decision-package/D_S2_8决策包_2026-11-03.xlsx | `1071c96bf61a71f3b23d85cd8ff3e40854a3a58b0fc37af3f604e015d9137831` | 154 冻结待人工 / 178 未决；q_zero 50 |
| 交期快照 | leadtime_snapshot_20261103.json | `30bf7be360af1bf016509b03f6481741b44c0018d8cc820b2bef9bff57e7b615` | SO→DN 2026-05..10 中位 21/p90 35.4；三运输类 50/31/13 天 p50 |

## 复现入口

- 生成脚本：`scripts/d3b_history_backtest_v3_5_2026-11-03.py`、`scripts/d5_time_validated_v6_3_2026-11-03.py`、
  `scripts/d6_top50_sandbox_v6_3_2026-11-03.py`、`scripts/d6_v6_4_scope_filter_20261103.py`、
  `scripts/supply_chain_strategy_s1_20261103.py`、`scripts/supply_chain_s2_simulation_20261103.py`、
  `scripts/supply_chain_s2_2_simulation_20261103.py`、`scripts/supply_chain_s2_3_exception_queue_20261103.py`。
- 脚本按本地分析目录的输入路径运行；仓库内不包含业务 Excel/Parquet。
- 相关方法沉淀见 `docs/solutions/architecture-patterns/us-owner-restatement-and-b2-scope.md` 与
  `docs/solutions/architecture-patterns/end-to-end-supply-chain-strategy-s1-s2.md`。

## 2026-11-05 返修（F1-F6；取代 11-03 的服务与校准结论）

| 阶段 | 产物 | SHA256 | 关键计数 |
|---|---|---|---|
| D3b v3.6 | D_历史归一与回测_D3b_v3_6_2026-11-05.xlsx | `f4bfd093eaabc709565baab2cea5243b4965a5d9417599ecf395dbf1a87b5081` | A 合计 WAPE 0.5626；B 0.5262；A 398/B 399 键 |
| D5 v6.4 | D5v6_4-full/D_概率与服务_D5_v6_4_2026-11-05.xlsx | `d716e21e6b93d5b95dd9053d6302623065ad803b61f2865965f763f02258a1cb` | 1,749 键 / 3,498 预测；US 只走 `asof_us_total_*` |
| D6 v6.5 | D6v6_5-final/D_Top50沙盒_D6_v6_5_2026-11-05.xlsx | `fd14e5e0b040ac881efd9d9c068f7b9b3671b6198f64bfc08fdefb4d479971cc` | 补 1,030 / 不补 355 / 观察 286 / 催已有 78；12 adapted / 226 unknown |
| D6 v6.6 | D6v6_6-final/D_Top50沙盒_D6_v6_6_2026-11-05.xlsx | `e20d1594f8079f179745f9b21cf039a0b8945722cfc8838eae983b8f67a272c6` | 补 987 / 不补 339 / 观察 345 / 催已有 78；观察行动标志 0 条不一致 |
| S2.9 | S2_9-daily-service-20261105/S2_9每日服务验证_2026-11-05.xlsx | `c596f239c89073846e4ce1e1f4890944cede9e4e9a5e7034903956d4a373b8c7` | A 周期95% 58 / B 满足率95% 210 / 催已有 66 / 未放行 731 |
| 交付包 | S2_9-delivery-20261106/D_补货交付包_2026-11-06.xlsx | `f7bc73e78c2031b6a8295b00f75bd1f086651d69574b4e582f370e3a4ef5f3c1` | 可批准 268 / 催已有 66 / 未放行 731 / 不补 339 / 观察 345 |

说明：S2.4 的 332/154/178 与 D5 v6.3/D6 v6.3-v6.4 的 q95 仅作为 11-03 诊断证据保留；
11-06 交付以本表 D3b v3.6 / D5 v6.4 / D6 v6.6 / S2.9 为准。
