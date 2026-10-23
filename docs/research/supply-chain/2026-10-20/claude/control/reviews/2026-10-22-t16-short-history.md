---
okf: v0.1
type: Review
title: T16 短历史方法正式对照（开发期验证）
date: 2026-10-22
owner: claude-worker
status: 完成；新增评估脚本与产物，未改主表与既有产物
artifacts:
  - experiments/business_phase/forecast_eval/short_history_eval.py
  - experiments/business_phase/forecast_eval/short_history_eval.json
  - experiments/business_phase/forecast_eval/short_history_eval.csv
  - experiments/business_phase/forecast_eval/short_history_report.md
---

# T16 短历史方法正式对照

> **开发期验证**：全部数据均已见过，**不是独立留出（hold-out）**；任何数值差都不构成
> “改进已证实”。本记录只陈述“在已见数据上的差异”。
> 只新增脚本与产物；未改主表、T2–T6/T9/T10/T11–T15 产物与 control 受保护文件。

## 1. 范围与预先注册方案

| 项 | 内容 |
|---|---|
| 范围 | 标签覆盖（首单月..2026-09）内历史 <24 月的 eligible 序列：**463 条**（n<3：15；3≤n<13：203；13≤n<24：245） |
| 目标 | 月度累计 h=3（origin+1..origin+3） |
| 切点 | 从“≥3 个月训练”的第一个 origin 起，**每 3 个月**一个；目标窗必须完全落在 ≤2026-09 |
| 训练 | 每个窗口重拟合，只用该切点当时可得的标签 |
| 类目借力 | peer 必须**在该切点**已有 ≥24 个月历史，形状只取截至该切点的 12 个月（`short_history_eval.py:119`） |
| 组合 | naive/SES/TSB 固定等权 |
| 对齐 | 先取五方法 **(SKU, origin)** 共同交集，再聚合（`:189`） |
| 指标 | MAE / WAPE=Σ\|F−A\|/ΣA / Bias=Σ(F−A)/ΣA；零需求保留在分子（`:173`） |
| 低置信 | 历史 <12 月或共同窗口 <3 个（`:317`） |

可评分 SKU **403**；五方法共同交集 **151 SKU / 685 个 (SKU, origin) 单元格**（全部候选
单元格 1,457）。

## 2. 各方法指标（共同交集，685 格）

| 方法 | MAE | WAPE | Bias |
|---|---:|---:|---:|
| naive | 10.778 | 0.6422 | −0.1279 |
| SES | 10.095 | 0.6015 | −0.1272 |
| TSB | 10.104 | 0.6020 | −0.1319 |
| 类目借力 | 11.687 | 0.6963 | −0.0022 |
| 固定等权组合 | **9.928** | **0.5915** | −0.1290 |

按历史长度：3≤n<13（53 格）TSB **6.33** < SES 6.625 < 组合 6.726 < 类目借力 7.649 <
naive 7.868；13≤n<24（632 格）组合 **10.196** < SES 10.386 < TSB 10.421 < naive 11.022 <
类目借力 12.026。

## 3. fallback 可靠性（现规则 AutoETS 失败 → MA3）

- 对齐子集内 AutoETS 失败 **289 格 / 147 SKU**（`NotImplementedError` 286、`KeyError` 3）；
  全部候选单元格失败计数：`NotImplementedError` 751、`KeyError` 12。
- 失败格上四种规则（同 289 格）：

| 规则 | MAE | WAPE | Bias |
|---|---:|---:|---:|
| 现规则（AutoETS→MA3） | **10.567** | 0.7329 | −0.1704 |
| TSB | 11.014 | 0.7639 | −0.1789 |
| SES | 10.529 | 0.7302 | −0.1840 |
| naive | 10.606 | 0.7355 | −0.2268 |

- SKU 重抽 300 次的 MAE 差（替代 − 现规则）：TSB **+0.459** [−0.697, +1.980]；
  SES **−0.026** [−0.710, +0.613]；naive **+0.064** [−1.680, +1.510]。**全部跨 0**。
- **结论：不建议**改用 TSB/SES。TSB 点估计更差、SES 与现规则几乎相同，两者区间都跨 0，
  在已见数据上不可区分；现规则（AutoETS 失败→MA3）保留。

## 4. KeyError guard 前后对照

| len | 条数 | 修复前（raw AutoETS） | 修复后（len<3→naive） |
|---:|---:|---|---|
| 1 | 4 | KeyError × 4 | 4 条均可产出预测 |
| 2 | 11 | NotImplementedError × 10、KeyError × 1 | 11 条均可产出预测 |
| 3 | 16 | NotImplementedError × 16 | **仍抛错**（guard 未覆盖） |
| 4 | 16 | NotImplementedError × 16 | **仍抛错** |
| 5 | 13 | NotImplementedError × 13 | **仍抛错** |
| 6 | 11 | NotImplementedError × 11 | **仍抛错** |
| 7 | 11 | ok × 11 | ok × 11 |

- len<3 的 guard 解决的是 **KeyError**（len=1 为主，len=2 有 1 例）；len=3..6 的
  `tiny_datasets` 仍会抛错。完整修复应把 guard 扩到 **len<7**，或捕获后回退 MA3
  （生产规则已这么做）。
- len=1–2 的 15 条序列首单在 2026-08/09，当前没有完整 3 个月目标窗，**不进入计分**；
  guard 只保证不再抛错，不用默认值伪造评分。

## 5. 同类异常（计数与处理，均不静默）

| 异常 | 数量 | 处理 |
|---|---:|---|
| 单点序列（len=1） | 4 | naive 常数预测；无完整目标窗，本轮不计分 |
| 两点序列（len=2） | 11 | naive 末值；无完整目标窗，本轮不计分 |
| 全零序列 | **0** | 若出现则保留（预测 0、分子 0）；本轮无 |
| 常数序列 | 1 | 正常评分，不做特殊剔除 |
| 零需求单元格 | 102 | 保留在 WAPE 分子，对分母贡献 0 |
| AutoETS 非 ok 单元格 | 289 | 按原因保留并回退 MA3 |

## 6. 低置信标记

- 判定：历史 <12 个月，或共同可评分子集内窗口数 <3。
- 计数：**337 / 463**；其中进入共同交集子集的 **25** 条。

## 7. 建议（一句话）

短历史默认仍保留 **AutoETS 失败→MA3**；已见数据上 TSB/SES 与现规则不可区分
（区间跨 0），不构成切换依据；固定等权组合 MAE 最低（9.928）只作前向影子候选。

## 8. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forecast_eval/short_history_eval.py
uv run python scripts/check_secrets.py   # 无 finding、退出码 0
```

- 输出：`short_history_eval.csv`（1,457 行，逐 SKU×切点）、`.json`（全部汇总）、
  `short_history_report.md`。
- DB 只读（前后 sha256 一致）；固定切点/步长/模型参数，脚本确定性；运行约 5 s。

## 9. 约束自检

| 约束 | 结果 |
|---|---|
| 只新增脚本、产物/报告与本记录 | ✅ |
| 未改主表、T2–T6/T9/T10/T11–T15 产物 | ✅ |
| 未改 control 下 HANDOFF/state/DECISIONS/NIGHT_PLAN/CONTROL/RESEARCH_ADOPTION | ✅ |
| DB 只读、未访问生产、未扩样、未下单、未删数据、未合并 PR | ✅ |
| 未 push；只提交新增文件 | ✅ |
| 未提交原始明细与凭证；`check_secrets.py` 无 finding | ✅ |
| 不留临时文件（含 `__pycache__`） | ✅ |
| 措辞：明确“非独立留出”，未称改进已证实 | ✅（报告首段与 JSON `status`/`wording`） |
