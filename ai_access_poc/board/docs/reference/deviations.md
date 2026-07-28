---
okf: v0.1
type: Reference
title: 板 PoC 已知偏差清单
description: 运营审阅用；候选不可直接当自动执行依据
tags: [reference, deviations, sellfox, ivyeaops]
timestamp: 2026-07-24
---

# 已知偏差

| ID | 偏差 | 影响 | 缓解 | 实测 2026-07-24 |
|----|------|------|------|----------------|
| D1 | 订单/销量归因窗口可能与领星不同 | 阈值松紧 | 运营对照后台 | 候选已出；阈值沿用 IvyeaOps 默认（15 点击否词 / ≥3 单收割 / 目标 ACOS 30%） |
| D2 | aggregate vs 按日 | 粒度不同 | 标明模式 | 使用 7 天整窗 xlsx 一次聚合 |
| D3 | Campaign/Targeting 等曾「可拉未 ingest」 | 降加 bid/预算曾空 | Phase2 ingest | **2026-07-28 已接线**：`ingest_sellfox_phase2`；标定店候选含降/加 bid；写仍禁 |
| D4 | sid vs shopId | 映射 | 配置一店 | 独立 runner 不依赖 sid；IvyeaOps 路径用规范化 sid |
| D5 | AGPL 外部树 | 合规 | 不 vendoring | 工作树在 `IvyeaOps-sellfox` |
| D6 | 无广告写 API | 不能自动否词 | CSV 人工 | `write_blocked` 字段 + operate 硬禁 |
| D7 | Auto/商品/类目「用户搜索词」可为 ASIN | 收割候选像在加 ASIN 词 | 过滤 `B0…`（**未实施**） | 2026-07-28 TOODDLY 确认报表真值；见 solutions best-practice |

更新规则：运营签字前可改阈值并回填本表。
