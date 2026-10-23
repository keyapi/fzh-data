---
okf: v0.1
type: Task
title: 打工仔1｜全 SKU 预测分型 + 全局 LightGBM / 供需主线衔接
date: 2026-10-23
owner: claude-worker
status: dispatched
---

# 任务：全 SKU 预测分型 + 全局 LightGBM / 供需主线衔接（只读离线）

## 背景（复用，不重跑）

- **A 包** `2b44cdbd`：`experiments/business_phase/forecast_eval/routing_eval.py`，151 SKU / 446 窗，同切点对照 simple / 间歇 / 季节 / 固定组合 / 全局树。
- **B 包** `bf8b19c0`：`out/auto_order/linkage_audit_v2.csv`（SO 显式关联 236 / 70.4%）。
- **C 包** `b02fd083`：`out/business_phase/final_bundle.csv`（2,309 行 / 1,328 SKU）。
- 研究采用表 `control/RESEARCH_ADOPTION.md` 第 1 项把「分段 + 全局 LightGBM」标为**延后**（理由：样本量不足）。本任务就是**用分型证据更新这个判断**，不是推翻它。

## 目标

1. **全 SKU 分型**：对母集每个 SKU 判型（平滑 / 间歇 / 季节 / 新品短史 / 证据不足）。判型规则必须**训练窗内可算**，**不得**用外层评估结果反向定型。
2. **全局 LightGBM vs 基线**：在同批 `(SKU, 起点)` 单元、同一评估窗口对照。MLForecast / LightGBM 若不可用就报告降级并给替代对照，**不装包**。
3. **接回供需主线**：把分型结果映射到 C 的 2,309 行，标出「该 SKU 分型支持 / 支持不足」。**不改 C 的数字**，只加边注。

## 硬约束

- DB 只读 `read_only=True`；不访问生产；不下单；不扩样。
- 不重跑 A/B/C；引用其 commit 与数字，不覆盖其产物。
- **本轮不 commit、不 push**（工头唯一提交者）。
- 不新增依赖；不宣称单一最优模型；分型覆盖必须入 N 出 M 对账。

## 文件所有权

- **可写**：`experiments/business_phase/forecast_eval/`（新增文件）、`out/business_phase/`（新增文件）、`control/reviews/2026-10-23-full-sku-routing.md`。
- **只读引用**：A/B/C 既有产物、`control/RESEARCH_ADOPTION.md`、`order_store.duckdb`。

## 验收（Observable）

- 终端输出 `DONE FULLSKU`。
- 交付四件：
  1. 分型表（SKU → 类型 → 证据字段）；
  2. 同单元同指标对照表（全局 vs 各基线）；
  3. 覆盖对账（入 N 出 M / 未评分单元单列并给原因）；
  4. 接回 C 的映射统计 + 不可外推边界说明。
- 回报：文件路径、复现命令、耗时。
