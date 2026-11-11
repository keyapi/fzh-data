# 2026-11-11 波兰 / E 供给线阶段性产物

本目录是 2026-11-11 会话的阶段记录，源数据与中间 parquet/xlsx 在 `D:/Work/fzh-order-store/analysis/`，这里只放可读报告与判定 CSV。

| 文件 | 内容 |
|---|---|
| `FINAL_REPORT_20261111.md` | 总报告：通途库存、手工扣减、E、波兰请求、3 张 SO、v5.5 |
| `POLAND_SO_20261110_audit.md` | SO 数量、禁用物料、波兰 Excel、A/B/C、Poland Order |
| `POLAND_COVERS_NONORDER_DEDUCTION_20261111.md` | 9–10 月波兰皮壳仓非订单扣减审计（9 月覆盖 51.5%） |
| `PJ_EXCEL_LOGIC_20261111.md` | 波兰给老板的下单逻辑、2026 实际动销、软包墙围套件证据 |
| `PJ_EXCEL_FACTS_20261111.csv` | 56 行请求的 2025/2026 销量、请求倍数、覆盖月数 |
| `POLAND_REQUEST_SO_JUDGEMENT_20261111.md` | 2,991 件请求与 3 张 SO 的判定 |
| `poland_request_judgement_20261111.csv` | 逐 SKU 请求判定 |
| `poland_so_judgement_20261111.csv` | 逐 SO×产品判定 |
| `wall_panel_set_mix_20261111.csv` | 软包墙围 1/2/3/4/6/9/12 件套销量结构 |
| `E_ARCHITECTURE_PRINCIPLES_20261111.md` | E 的修正架构：SKU×客户×节点、单据可选、lifecycle 按客户、UOM/套件 |
| `E_REVIEW_RESULT_20261111.md` | 第一轮 E 复核（后续已被 E v2 取代） |
| `E_CODEX_BRIEF_20261111.md` | 给 Codex 的 E 任务简报 |
| `POLAND_ORDER_INTEGRATION_PLAN_20261111.md` | Poland Order 并入 orders_unified 与 v5.5 计划 |
| `orders_unified_20261111_report.json` | 订单事实构建报告（1,142 行 / 1,216 件） |

E v2 代码与设计在分支 `feature/e-nodes-20261111`（`supply_netting/e_nodes.py`、`e_node_views.py`、`e_node_timing.py`、`docs/E_DESIGN.md`）。

**口径提醒**：报告里的“产品×仓池”就是“SKU×客户”；仓池=客户（波兰/USNJ/USTX），SKU=产品=EN 物料，日常混用。
