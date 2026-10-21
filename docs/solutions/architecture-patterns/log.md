---
okf: v0.1
type: Log
title: architecture-patterns — 变更日志
tags: [solutions, architecture-patterns, log]
---

# architecture-patterns 变更日志

## 2026-10-21

- **核实**: `order-history-duckdb-store.md` §10 补 SO 内胆按钮的真实机制（Excel 只建 PK#；按钮按物料组+尺寸找 ND#，不是读 BOM，含 `custom_replaced_by_other_item_group`）、22 张 SO 的 13/9 分布、BOM 与按钮 84.5% 一致及两类偏差；`-Cover` 与不带后缀的通途 SKU 是独立 SKU 账（变动不镜像，cover 销量 4.4%），可售总量相加但实物同池未证。
- **修正**: `forecast_shipment_plan.py` 内胆只按 BOM，按钮误加单独列 `button_overadd_candidates` 10 行；皮壳 211 行/3,990、内胆 BOM 180/3,795、停用内胆 6 行、按钮对不上 5 行。
- **修正**: `forecast_replenishment_v3.py` 增物料级合并池（皮壳/半成品计入 `-Cover`）：296 需补货 / 4,813 件；3PL `three_pl_stock` 92 SKU/880 件。
- **根因/架构**: 61/62 个「BOM 有内胆、按钮找不到」是 BOM 仍挂停用内胆（清理 BOM，不重置物料）；82 个反例是 BOM 正确、产品无内胆、按钮误加（不进发货计划）。KS BOM 只有皮壳+内胆，PP 棉/包装在 SXBZCP/PLBZCP/USTXBZCP BOM。新增 `nd_button_gap_report.py`。
- **核实**: intransit 与 PO 高度重叠（173 个 SKU×仓同时有，146 个差 ≤1；`SUM(LEAST)=13,118`=全部 intransit），供给暂按 `available + GREATEST(intransit, PO)`；但这是**临时假设**——未证明逐笔包含，248 条未结 PO 的 `will_arrive_date` 全空，到货时点无法验证。新增 `conventions/branch-shipment-cover-rules.md`、`freeze_snapshot.py`、`replenishment_trace.py`、`input_health`/`data_flags`。
- **收紧（按 #300 复核）**: Cover 合并改为显式情景假设；“成品=皮壳+内胆+充棉”改为典型配置（部分产品无内胆）；BOM 挂停用内胆改“待清理核实”。对账包见 `D:/Work/fzh-order-store/RECONCILIATION_2026-10-21.md`。

- **修正**: `order-history-duckdb-store.md` §10 重写为「分公司发货形态」：成品 KS = PK# + ND# + 充棉；`Item Group.custom_shipment_type_to_branch` 决定发什么；补货量只有一套，`forecast_shipment_plan.py` 按 BOM 第一层换算成皮壳/内胆清单。删除面料/拉链/PP 棉与 EN Bin 供给的错误做法。3PL API 实测仅 Cranbury 有量，权威仍是 Wayfair 后台导出；E1 表述改为「E1 选择 Croston、held-out TSB 0.511 / ens5 0.520」。
- **修正**: `demand_forecast_90` 只取未来月并按实际未来月数归一，补货 v3 由 722/14,474 修正为 311/4,548；`forecast_ensemble.py` 短史 SKU 兜底后未来预测覆盖 1,156 条序列，回测 ens5 WAPE 0.690 不变。

## 2026-10-20

- **新增**: `order-history-duckdb-store.md` — 销量预测/补货的历史数据架构：GS 月表（2023-01 起）+ EN 并集进 DuckDB；实测通途 API 历史可见性有限（不带 accountCode 约 5–6 千条封顶、可见性跟最近更新时间走），**不能用来补齐历史**；含运费口径演进（运费 → 通途运费/物流商运费）、子表 REST 403 的绕法、SKU 归一 99.2%、补货快照首版。

## 2026-09-22

- **新增**: `public-private-agent-knowledge-split.md` — 公开仓、私有 Markdown 知识仓与 secret manager 三层分离；普通 clone + bootstrap 代替 submodule，保留 Agent 检索和非技术同事使用体验。
