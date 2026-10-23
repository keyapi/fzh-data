---
okf: v0.1
type: Task
title: 打工仔1｜全 SKU 主线自审：不确定性量化 + 时点纯净性 + 计数对账
date: 2026-10-23
owner: claude-worker
status: dispatched
---

# 任务：全 SKU 主线自审（并行于 PB 返修，不阻塞）

## 背景

你上一轮交付的 `full_sku_routing`（`experiments/business_phase/forecast_eval/full_sku_routing.py`，
产物 `out/business_phase/{full_sku_classification.csv,full_sku_eval.json,final_bundle_routing.csv,full_sku_routing.md}`，
报告 `control/reviews/2026-10-23-full-sku-routing.md`）已收。**不要重做**，本轮只做同类审查口径的自审与加固。

参照：Codex #301 对 PB 包给出 FAIL 的五条（损失方向、跨度冒充下界、比值冒充积压、全期选样前视、集合差异未闭合）。
其中与全 SKU 主线同类的风险是**时点纯净性**与**不确定性未量化**——先自查，不要等复审再返工。

## 必须做

### 1. 不确定性量化（最重要）

- 对 `global_tree`（WAPE 0.494）与 `combo`（0.524）做 **SKU 整簇 bootstrap**（≥2000 次），给 WAPE Δ 的 95% CI。
- 其余方法同样给 CI。
- **若 CI 跨 0，必须明写「无显著差异」，不得按点估计排序宣称全局树更好。**
- 说明重采样单位（SKU 整簇，不是单元）与为什么这样选。

### 2. 时点纯净性自检

逐项给证据（文件:行）：
- 分型规则用到的每个特征，是否**只用该 SKU 在该切点之前**的数据；
- 切点、评估窗口、标签可用时间是否一致；是否存在用目标期数据反推分组；
- 若有任何一处做不到，明确标 `not_point_in_time` 并给泄漏方向。

### 3. 计数对账复核

逐项写清分母口径并可复算：`1,328 SKU` / `6,640 候选单元` / `2,820 已评分` / `3,820 未评分` /
`1,366 支持充足` / `943 支持不足`。给出等式与差额去向（**不得静默丢弃**）。

### 4. 与 A 包一致性

A 包（`2b44cdbd`）的 `routing.csv` 与你这次的共同单元是否同源、数字是否一致；不一致就列差异，**不覆盖 A 的产物**。

## 硬约束

- DB `read_only=True`；不访问生产、不扩样、不下单。
- **不 commit、不 push** —— 工头是唯一提交者。
- 不新增依赖；不改 A/B/C 既有产物与数字；不改 C 的 `final_bundle.csv`。
- 只写：`experiments/business_phase/forecast_eval/`（新增文件）、`out/business_phase/`（新增文件）、`control/reviews/2026-10-23-full-sku-selfaudit.md`。
- `uv run python scripts/check_secrets.py` 零输出（**不要**跑 `update_index.py`）。

## 验收

- 终端输出 `DONE FULLSKU-AUDIT`。
- 报告含：bootstrap 表（方法 / WAPE / Δ vs global_tree / 95% CI / 是否显著）、时点纯净性逐项结论、
  计数等式与差额去向、与 A 包的差异表（无差异也要写"无差异 + 复算方式"）。
- 回报文件路径与复现命令。
