---
okf: v0.1
type: Research
title: 2026 时间序列销量预估方法现状调研（为 SKU 预估计划选型）
description: 调研 2026 年销量预估方法现状：基础模型(Chronos/TimesFM/Moirai)、间歇性需求(Croston系)、概率预估(Conformal)；结论用于决定是否开公司级 SKU 预估子项目
tags: [forecast, time-series, demand, intermittent, foundation-model, conformal, research]
date: 2026-08-31
---

# 2026 时间序列销量预估方法现状调研

> 背景：PB 单 SKU 预估（sku_forecast.py，M1/M2/M3 朴素基线）已交付，但用户想扩展到"公司整体 SKU 销量预估"（数据源候选 EN tongtool order / 通途订单），需要先评估 2026 年方法现状与是否值得新开子项目。

## 结论摘要

- 2026 年前沿是**时序基础模型（TSFM）**：Chronos-2/Bolt、TimesFM-2.5、Moirai-2.0、TimeGPT，以及新 SOTA 候选 TiRex、TS-ICL、PatchFM。但**对单 SKU、月量个位数、稀疏/断货数据，它们的优势很小**（金融等低信噪比领域的独立评测显示相对朴素基线提升微弱）。它们真正的价值是大量 SKU 的"迁移/零样本"与大模型基建。
- 对用户的场景（稀疏、0 库存月、断货截断），**方法选型的关键不是"更先进"，而是按需求形态分桶**：
  1. **间歇性/零膨胀需求** → Croston 系（SBA/TSB/TSB-HB/ADIDA），把"发生概率"和"发生量"分开建模——这正是用户 2020 年"0 库存特殊处理"的学术版。
  2. **稀疏但有协变量** → LightGBM + 零膨胀特征（近窗零计数、距上次下单、间歇率）。
  3. **概率区间** → **Conformal / CQR 已是 2025-2026 默认**，分布无关、小样本可用（50-100 校准观测），业界做法 = 强点预测（LightGBM/LSTM）+ conformal 校准，输出分位数区间供补货/服务水平。
- **断货=截断需求**：0 库存导致的"无销量"不应当 0 处理；正确做法是需求校正/uncensoring，或至少文档标注低估。用户 2020 年直觉正确。
- **建议**：值得开新子项目，但先做**数据可行性调研**（通途订单 API 覆盖范围、历史深度、SKU 粒度、能否识别断货），再搭"可插拔数据源 + 需求分类 + 分桶方法 + conformal 区间"的复用管线。方法上**先跑强基线**（Croston/SBA/TSB + 简单趋势），TSFM 只在数据量大或零样本场景上。

## 方法现状（按 2026 资料来源）

### 1. 时序基础模型（TSFM）

- 成熟模型：**Chronos-2 / Chronos-Bolt**（Amazon，把预测当语言建模，Bolt=省算力）、**TimesFM-2.5**（Google，decoder-only）、**Moirai-2.0 / Moirai-MoE**（分位数、MoE）、**TimeGPT**（Nixtla）。
- 2026 新候选（自称 SOTA/并列）：**TiRex**（零样本 SOTA，GiftEval/Chronos-ZS）、**TS-ICL**（in-context learning，imputation SOTA）、**PatchFM**（无泄漏训练 + 多分位 pinball loss）、Time-MoE、Sundial、TabPFN-TS。
- 独立评测（金融收益预测，arXiv 2606.27100）：预训练 TSFM 赢多数任务（Moirai-2.0 / TimesFM-2.5 平均排名最高），但**相对随机游走/朴素基线的提升小且不显著**；局部有监督基线仍可赢特定任务。→ 低信噪比数据别指望 TSFM 带来奇迹。
- 效率评测（PMLR）：Chronos-Bolt 低能耗低延迟，TimesFM 精度好能耗低，Moirai-MoE 能耗高。→ 若要上 TSFM，选 Bolt / TimesFM 这类轻量。

### 2. 间歇性 / 零膨胀需求（用户 SKU 的典型形态）

- **Croston（1972）仍是地基**；改进：**SBA**（偏差校正，高间歇更稳）、**TSB**（控极端误差）、**TSB-HB**（2025，分层贝叶斯，稀疏/冷启动强，UCI Retail / M5 上超过 Croston/SBA/TSB/ADIDA/ARIMA/Theta）、ADIDA（聚合-分解）。
- 最佳实践（2025）：先按 **Syntetos-Boylan ADI/CV² 分类**（smooth / intermittent / erratic / lumpy），再按类选方法；FMCG 案例显示分类分桶使偏差率 53.6%→22.2%、缺货事件降 60%。
- **稀疏+协变量** → LightGBM + 零膨胀特征（零计数、距上次下单、间歇率）是 2025/2026 实用默认。

### 3. 概率预估 / 区间（补货真正需要的东西）

- **Conformal Prediction / CQR 是 2025-2026 默认**：分布无关、有限样本覆盖保证，小样本（50-100 校准观测）即可用；业界 = 强点预测 + conformal 校准 + 分位数输出。
- M5 基准：LightGBM + 层级调和 + 居中 CQR 显著优于裸 LightGBM；HSML-CP（ARIMA-XGB-LSTM + 自适应 conformal）区间覆盖 97.8%。
- 生产实践（Applied ML 2026 大会）：conformal 回测数百窗口建经验误差分布，层级化重聚合保证区间一致，预计算分位数让业务直接查命中概率。
- 注意：时间序列违反可交换性 → 用时序 conformal（EnbPI / 块自助）/ 扩窗交叉验证；评估要看区间宽度（WIS/pinball），不只覆盖率。

## 对"公司级 SKU 预估子项目"的初步建议（待用户确认后深调）

1. **值得开新子项目**（新子文件夹，OKF 文档 + 可复用脚本），但分两阶段：
   - **阶段 A 数据可行性调研**（先做，别写代码）：通途订单 API（tongtool_order_cost 已接入）能拉多久历史、SKU 粒度、能否识别断货/0 库存；EN ERPNext 有无库存流水可作为"断货"信号。产出调研文档。
   - **阶段 B 搭管线**：可插拔数据源（PB invoice / 通途订单 / ERPNext）→ 需求分类（ADI/CV²）→ 分桶方法（间歇用 Croston/SBA/TSB，平滑用趋势/SES，有协变量上 LightGBM）→ conformal 分位数区间 → 给补货的表/文档。
2. **方法定位**：先强基线 + 分桶 + 概率区间；TSFM（Chronos-Bolt 等）只在 SKU 数量大（几百+）时作为零样本/迁移选项评估。
3. **断货处理**：把"0 库存期间"显式标记（用户 2020 年做法），不要当普通 0；后续可按截断需求校正。
4. **复用**：`pb_reconciliation/sku_forecast.py` 的序列读取/输出可泛化抽取为通用数据源层；`tongtool_order_cost` 已证明通途 API 可读。

## 原始来源

- 预训练时序基础模型金融评测：https://arxiv.org/pdf/2606.27100 （arXiv 2606.27100）
- TSFM 精度-能耗基准（PMLR 2026）：https://proceedings.mlr.press/v309/guibert26a.html
- TS-ICL：https://www.semanticscholar.org/paper/TS-ICL%3A-A-Flexible-Time-Indexed-Foundation-Model-Naour-Nabil/2876abbf7869f4988e78fdd0e9a48d1874390551
- PatchFM：https://github.com/vilhess/PatchFM
- Croston 白皮书（MCP Analytics）：https://mcpanalytics.ai/whitepapers/whitepaper-croston-method
- 间歇需求最佳实践（GitHub AI-Agents 技能）：https://github.com/vasilyu1983/AI-Agents-public/blob/main/frameworks/shared-skills/skills/ai-ml-timeseries/references/intermittent-demand-patterns.md
- 概率预估最佳实践（同上库）：https://github.com/vasilyu1983/AI-Agents-public/blob/main/frameworks/shared-skills/skills/ai-ml-timeseries/references/probabilistic-forecasting.md
- CQR 论文笔记（ICML 2026 SA-MSCP）：https://en.papernotes.org/ICML2026/time_series/simulation-augmented_multi-step_split_conformal_prediction_for_aggregated_foreca/
- 零售需求 conformal LLM-RF-LSTM（CoRAL-RF）：https://www.sciencedirect.com/science/article/pii/S2590123026032937
- SmallML（小样本贝叶斯迁移 + conformal）：https://ar5iv.labs.arxiv.org/html/2511.14049
- 生产级概率预测（Applied ML 2026）：https://appliedml.us/2026/sessions/will-we-hit-our-target-real-time-probabilistic-forecasting-in-production/
- 2024/2025 销售数据自动模型选择论文：https://thesis.unipd.it/handle/20.500.12608/102118
