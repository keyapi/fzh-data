---
okf: v0.1
type: Research
title: demand_forecast 实用技术路线对比（2026 电商需求/库存预测落地）
description: 从电商实际落地角度对比 3 条技术路线（统计分桶 / 全局LightGBM / 分层调和），逐条映射公司特殊环境（0库存截断、老品生命周期、新品冷启动、节假日促销、多平台）；结论 = 分段混合 + 全局ML + 调和 + Conformal
tags: [demand-forecast, forecasting, lightgbm, croston, tsb, hierarchical, conformal, ecommerce, inventory]
date: 2026-08-31
---

# demand_forecast 实用技术路线对比（2026）

> 前置：[方法现状调研](2026-08-31-ts-forecast-methods.md)（2026 前沿）、[数据可行性调研](2026-08-31-demand-forecast-data-feasibility.md)。本文给"能直接拍的方案"。

## 0. 一句话结论

**2026 年电商落地的主流不是单个模型，而是"分段（segmentation）＋全局 ML ＋分层调和 ＋ Conformal 区间"的混合架构。** 特征工程 > 模型选择。工具用开源 Nixtla 生态 + LightGBM 足够，不需要也不建议一上来上深度学习/时序基础模型。

## 1. 你的场景 → 必须处理的环境清单

| # | 特殊环境（你说/你没说的） | 是否电商常见 | 业界成熟处理 |
|---|------|------|------|
| 1 | **0 库存 = 销量截断**（断货月没销量≠没需求） | 常见，但多数人忽略 | 用库存导出给断货月打标；销量只低估需求→备货加缓冲；进阶用 Tobit/删失需求校正，避免"螺旋下降"。**别当普通 0** |
| 2 | **老品/停售/死库存**（生命周期衰退） | 常见 | TSB 方法：无销量的月份概率项会衰减→预测自动趋 0（Croston/SBA 在停售品上"卡在最后正值"是错的）；运营规则：停售品默认不自动补货 |
| 3 | **新品冷启动**（2024 后大量新品、无历史） | 常见 | 借同类：物料组内 like-item / 属性相似；全局模型天然跨 SKU 借信息；品类聚合做先验再按份额下拆 |
| 4 | **节假日/促销**（黑五、Prime Day、圣诞、CNY 等） | 常见 | 促销当结构化事件：预热/进行/余波(hangover)分相位编码；日历特征；按平台各自事件（CNY 用农历） |
| 5 | **多平台多仓**（Amazon/Wayfair/Home24/PB + 波兰/美仓） | 常见 | **先预测总需求再按渠道分**（防渠道搬单 double-count）；按 物料组(制造单元) 做库存计划 |
| 6 | **长尾间歇 SKU**（多数 SKU 月销 0-几件） | 常见 | Croston/TSB/ADIDA 分桶，或全局 Tweedie 回归；慢动销用"概率补货"而非"天数库存" |
| 7 | **销量=单位而非金额** | 常见坑 | 训练单位数，价格/促销做特征，别用销售额做目标（价格变动会污染需求信号） |
| 8 | **产品生命周期重的目录不能纯自上而下** | 常见坑 | Lokad 警告：新品不停上、目录上涨是"假的"→ 纯 top-down 会给每 SKU 超估。要按 SKU 层建 + 调和 |

## 2. 三条候选技术路线（端到端）

### 路线 A — 统计模型分桶（最省事、可解释）
- 做法：每个 SKU 独立跑模型。平滑快动销 → AutoETS/AutoTheta；间歇 → Croston/SBA/**TSB**；统一 Nixtla `statsforecast` 跑。
- 优点：简单、透明、几乎零工程；TSB 天然处理停售/老品；单机可跑几千序列。
- 缺点：**不吃协变量**（促销/价格/节假日得靠先加工）；不跨 SKU 借力→新品冷启动差；无分层一致性；区间只是假设分布。
- 适合：先当**基线**，或只补"长尾/间歇"段。

### 路线 B — 全局 LightGBM（2026 电商"现代默认"）
- 做法：把全部 SKU×月 揉成一个面板，训练**一个** LightGBM（`objective=tweedie` 天然扛零膨胀）。特征 = 滞后/滚动统计（主导）+ 日历节假日 + 促销相位 + 价格 + 渠道 + 物料组/生命周期/上市月龄 + 断货标记。按 M5/生产案例，滚动统计和滞后特征最关键。
- 优点：**处理新品**（同类 SKU 借信息）、**吃促销/价格/节假日协变量**、几千 SKU 一个模型、M5 与多家零售实证（Walmart 多层集成、IEEE LightGBM-SHAP 框架等）；LightGBM 在 <1 万序列常比深度学习好。
- 缺点：要特征工程 + 数据质量（业界项目失败第一原因）；需 walk-forward 回测，忌随机切分；极端零销量 SKU 可能高估 → 需分桶兜底。
- 适合：**主线引擎**。

### 路线 C — 分层调和（保证库存计划一致）
- 做法：物料组(410) 与 SKU 两(或三)层都出预测，再做调和使"组总=各 SKU 和"。工具 Nixtla `hierarchicalforecast`（BottomUp / MinT）。
- 关键结论（2025-2026 研究）：**SKU/操作层 → BottomUp；组/战术层 → MinT**；不要只在一个层级预测。
- 优点：物料组总量稳定（他们按组做皮壳/内胆/备货），新品进组由组总量兜底；防渠道/层级数字打架。
- 缺点：不能纯 top-down（见上 8）；实现比 A/B 多一点。
- 适合：**生产/补货层的输出格式**。

## 3. 对比表

| 维度 | A 统计分桶 | B 全局 LightGBM | C 分层调和 | 备注 |
|------|-----------|----------------|-----------|------|
| 平滑快动销 | ✅ AutoETS | ✅ Tweedie | ✅ | B 通常更准 |
| 间歇/长尾 | ✅ Croston/TSB | 🟡 需 Tweedie+零膨胀特征 | — | 长尾建议 A 兜底 |
| 老品停售 | ✅ TSB（衰减到0） | 🟡 靠 recency/月龄特征 | — | TSB 是专门答案 |
| 新品冷启动 | ❌ | ✅ 借同类SKU | ✅ 组兜底+份额 | 缺一不可 |
| 节假日/促销 | ❌ | ✅ 事件/日历特征 | — | B 的主场 |
| 0库存截断 | 🟡 打标 | 🟡 打标+特征 | — | 都要做断货标记 |
| 多平台 | 分渠道跑 | ✅ 渠道特征/总-分 | ✅ 渠道层调和 | |
| 工程成本 | 低 | 中（特征+回测） | 中 | B 是大头 |
| 可解释 | 高 | 中（SHAP） | 高 | 补货同事要能质疑 |
| 生态/库 | statsforecast | LightGBM | hierarchicalforecast | 全开源 |

## 4. 推荐路线：B 主引擎 + A 兜底长尾 + C 输出（分段混合）

1. **数据层**（先行，见可行性调研）：通途订单月表 2023+ → EN 映射 → SKU×月 单位数面板；打标签：**生命周期**（disabled/新品月龄/停售）、**断货月**（通途库存导出 可用库存≤0）、渠道/仓库、促销/价格（有则加）。
2. **预测引擎**：全局 LightGBM `tweedie` 出 SKU 层点预测 + **Conformal/分位数**（P50/P80/P95）做区间 → 喂安全库存。
   - 长尾/停售段：AutoETS→不成则 Croston/**TSB**（TSB 专门让停售品衰减）。
3. **调和输出**：SKU 预测 → 物料组 BottomUp/MinT 调和，保证"组总=SKU和"，按 物料组 出补货计划。
4. **新品**：组内属性相似 like-item 先验 + 全局模型共享；前 3-6 月按组份额估算。
5. **回测与运营**：walk-forward（不随机切分）；指标 WMAPE/偏差，按 SKU×渠道×仓 盯漂移；**补货同事可覆盖预测并填原因码**，原因回灌成下一轮特征（信任=落地关键）。
6. **不上**（现阶段）：深度学习/TSFM（Chronos 等）——数据量（几千 SKU、多数稀疏、2-3 年）不支持，等 SKU 覆盖够大再评估。

## 5. 落地工作量（粗略）

- 数据层（读月表+映射+标签+面板）：1-2 周。
- B 主引擎 + 回测框架：2-4 周。
- A 兜底 + C 调和 + 输出表/文档：1-2 周。
- 合计约 **1-2 个月**出可用的第一版（到"能给补货同事一张表+区间"）。

## 原始来源

- 电商落地实践框架：https://www.mds.co/blog/demand-forecasting-ecommerce ；https://branch8.com/posts/ai-powered-demand-forecasting-apac-e-commerce-guide
- LightGBM-SHAP 可解释零售框架（IEEE/DOAJ）：https://doaj.org/article/1d4295aaa5934ed2880be50492cef3df ；https://www.mdpi.com/search … 滚动统计特征主导
- Walmart 多层 HiFoReAd（LightGBM+MSTL+ETS+调和）：来源见搜索结果（Walmart Global Tech）
- Damm UK 全局池化+稀疏：见搜索结果（Asda R² 0.04→0.40 案例）
- 删失/丢失销量需求校正（Tobit KF、Bayesian、MLE、online learning）：https://www.sciencedirect.com/science/article/abs/pii/S0169207023000961 ；https://www.euro-online.org/conf/euro34/treat_abstract?frompage=edit_session&sessid=70&paperid=870 ；NSF 删失定价：https://par.nsf.gov/biblio/10581612
- 新品冷启动（聚合层正则/transfer）：https://scite.ai/reports/pooling-and-boosting-for-demand-A34glzPE ；视觉相似聚合：https://link.springer.com/article/10.1007/s41060-025-00888-8 ；Lokad top-down 生命周期警告：https://www.lokad.com/blog/2011/4/1/business-is-up-but-forecasts-are-down
- 生命周期/慢动销/停售 TSB、Blue Yonder 概率补货：https://metricgate.com/docs/teunter-syntetos-babai-method/ ；https://info.blueyonder.com/retail-planning-category-management/what-is-blue-yonder-slow-mover-forecasting-and-replenishment
- 节假日/促销/因果特征：https://cartesiankinetics.com/how-retailers-are-using-ai-to-navigate-holiday-shopping-volatility-in-2025/ ；https://github.com/Mohdshy1999/Causal-Retail-Demand-Forecasting
- Nixtla 生态（statsforecast/neuralforecast/hierarchicalforecast）：https://nixtlaverse.nixtla.io/hierarchicalforecast/examples/reconciliationdiagnostics.html ；https://github.com/databricks-industry-solutions/intermittent-forecasting
- 分层调和（BottomUp vs MinT、M5）：https://arxiv-org.ezproxy.obspm.fr/html/2606.26774v1 ；bayesRecon M5：https://rdrr.io/cran/bayesRecon/f/inst/doc/mixed_reconciliation.Rmd
- 销量预测实践者指南（2026，walk-forward/WMAPE 等）：https://prospeo.io/s/time-series-sales-forecasting
