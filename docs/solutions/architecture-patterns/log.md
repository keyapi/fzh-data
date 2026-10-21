---
okf: v0.1
type: Log
title: architecture-patterns — 变更日志
tags: [solutions, architecture-patterns, log]
---

# architecture-patterns 变更日志

## 2026-10-21

- **修正**: `order-history-duckdb-store.md` §10 重写为「分公司发货形态」：成品 KS = PK# + ND# + 充棉；`Item Group.custom_shipment_type_to_branch` 决定发什么；补货量只有一套，`forecast_shipment_plan.py` 按 BOM 第一层换算成皮壳/内胆清单。删除面料/拉链/PP 棉与 EN Bin 供给的错误做法。3PL API 实测仅 Cranbury 有量，权威仍是 Wayfair 后台导出；E1 表述改为「E1 选择 Croston、held-out TSB 0.511 / ens5 0.520」。
- **更新**: `order-history-duckdb-store.md` — 补 §10 组件级补货：EN 默认 BOM 5,582 条/明细 13,157 行，成品 → PK#/ND# → 面料/拉链两层展开，981/1,004 有预测成品可匹配；组件供给取 EN Bin（中国仓）+ 未结 PO，负库存夹紧；MOQ/装箱取整后 1,334 个组件需补货、34,283 件。§11 记 `bench mariadb` 1000 行截断，批量导出须直连 mysql。§12 列剩余缺口（3PL、BOM 缺口、组件仓口径）。【已被上条修正】
- **修正**: `demand_forecast_90` 只取未来月并按实际未来月数归一，补货 v3 由 722/14,474 修正为 311/4,548；`forecast_ensemble.py` 短史 SKU 兜底后未来预测覆盖 1,156 条序列，回测 ens5 WAPE 0.690 不变。

## 2026-10-20

- **新增**: `order-history-duckdb-store.md` — 销量预测/补货的历史数据架构：GS 月表（2023-01 起）+ EN 并集进 DuckDB；实测通途 API 历史可见性有限（不带 accountCode 约 5–6 千条封顶、可见性跟最近更新时间走），**不能用来补齐历史**；含运费口径演进（运费 → 通途运费/物流商运费）、子表 REST 403 的绕法、SKU 归一 99.2%、补货快照首版。

## 2026-09-22

- **新增**: `public-private-agent-knowledge-split.md` — 公开仓、私有 Markdown 知识仓与 secret manager 三层分离；普通 clone + bootstrap 代替 submodule，保留 Agent 检索和非技术同事使用体验。
