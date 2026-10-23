---
okf: v0.1
type: Task
title: 打工仔2｜PB 删失/断货验证核查与改进
date: 2026-10-23
owner: claude-worker-2
status: dispatched
---

# 任务：PB 删失实验核查与改进（只读离线）

## 背景（已核实事实，不要重跑）

- 现有实验：commit `e1b9b5d7`（原始销量 vs 删失感知训练对照，PB 三角，26 SKU）。
- 断货区间：T42 commit `458642cf`，产物 `out/pb_stockout/stockout_intervals.csv` + `pb_30sku_list.csv` + `cross_source_report.md`。
- 外部已实装数据（**只读、不重复入库**）：
  - `D:/Work/fzh-order-store/order_store.duckdb` —— 独立 schema `wx_inventory`；198,363 观测 / 38 个日期 / 2026-06-09..10-19。
  - `D:/Work/fzh-order-store/pb_forecast_cohort.json` —— PB 28 历史清单 + 2024/25 促销证据。
  - `D:/Work/fzh-order-store/wx_inventory_import_report.json`。
- 已定事实（不得推翻、不得绕过）：人工宽表仓名 scope 未证，不得直接并入原仓；10-19 文件 27 列仓 scope 未证。

## 四条必须核查的缺陷

### 1. 名单与促销口径

- 现有 26/27 名单 vs 外部 cohort 的 28 个历史 SKU 是否同源？**逐个给 SKU 级差异**（多出 / 缺少 / 改名 / 前缀不同）。
- `vendorSKU` 需核通途映射：能证则证（给映射来源），不能证必须标 `mapping_unproven`，**禁止按相似名猜配**。
- 促销日期（2024/25）来自 cohort.json；核对这些日期是否被用于训练/评估。若未用，说明是应作特征、还是只作外部参照。

### 2. 「14 天归并」≠「连续断货下界」

- 现状：相邻 ≤14 天的信号归并成一个区间，保守下界 = 首末信号间实际天数。
- 缺陷：归并窗口内可能包含**无信号的空档**；把"首末信号间天数"当"连续缺货天数"会**高估**。
- 要求：拆成三个量并分别落表：
  - `observed_signal_days`（有信号的实际天数）
  - `merged_window_days`（首末信号跨度）
  - `unknown_gap_days`（跨度内无观测天数，**单列不插值**）
- 任何"断货天数"表述只能用 `observed_signal_days`；`merged_window` 只能叫「信号窗口」。

### 3. 「预测/发货比」不是断货率，也不是积压指标

- 现状：`预测/发运 > 1.2 的占比` 被写作"缺货暴露"，中位数比值被当"积压代理"。
- 缺陷：该比值只说明「模型预测高于实际发运」；实际发运受需求、退货、拆单、口径影响。**推不出缺货率，也推不出库存积压**。
- 要求：字段与正文统一改名为 `forecast_above_shipment_ratio`（偏差信号）；删去"缺货率 / 积压"措辞；并写明该指标只有在**拿到库存真值**后才具备库存含义 —— 本批没有。

### 4. 未来受限标签泄漏（时点纯净性）

- 风险：`stockout_intervals.csv` 由 T42 用**全期**数据生成；若评估切点早于区间生成所用数据，评估就用了未来信息。
- 要求：逐切点检查训练/评估用到的受限标签与区间定义，是否只用**切点之前**可得的信息。做不到 point-in-time 就明确标 `not_point_in_time`，并给泄漏方向（会让删失路线看起来更好还是更差）。

## 允许的改动范围

- 新增/修改：`experiments/pb_stockout/`、`out/pb_stockout/`、`control/reviews/2026-10-23-pb-censored-audit.md`。
- **不改** `e1b9b5d7` 已提交的 4 个文件正文。如需修正口径，写进新报告并注明「取代 e1b9b5d7 报告第 X 节」。

## 硬约束

- DB 只读：`duckdb.connect(..., read_only=True)`；遇锁稍后重试，**不抢写**。
- 不访问生产、不写库、不下单、不扩样、不改回 A/B/C 产物。
- **本轮不 commit、不 push** —— 工头是唯一提交者（两个打工仔同处一个 worktree）。只改文件并回报路径。
- 不新增第三方依赖；缺库就报告降级，**不擅自安装**。
- `uv run python scripts/check_secrets.py` 必须零输出（你只跑不改）。
- 结论只用可观测量；**不得用插补需求当 ground truth**；不得宣称"删失感知更优"，除非差异明确超出噪声。

## 验收（Observable）

- 终端输出 `DONE PB-AUDIT`。
- 报告 `control/reviews/2026-10-23-pb-censored-audit.md` 含：四条缺陷逐条「成立 / 不成立 + 证据（文件:行 或 数字）」、修正后指标、边界与不可外推说明。
- 数字对账：入 N 行 → 出 M 行；未匹配 / 未评分项**单列并给原因**。
- 回报：修改 / 新增文件路径清单 + 复现命令 + 运行耗时。
