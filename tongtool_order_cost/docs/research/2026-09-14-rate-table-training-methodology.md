---
okf: v0.1
type: Research
title: 费率表训练口径与细层样本不足的业界做法
description: 保险精算可信度理论、分层贝叶斯部分池化、GLM 分阶段与末公里费率卡实务调研，映射到 EN 历史尾程模型的可执行改造项
tags: [rate-table, credibility, partial-pooling, shrinkage, glm, last-mile, methodology]
timestamp: 2026-09-14
---

# 费率表训练口径与细层样本不足：业界做法调研

## 为什么调研这个

EN 历史尾程模型要对「国家 × 仓库 × 渠道 × 分区 × 重量档 ×（SKU）」这样的细层发布费率。
细层样本普遍不足（ZIP3×重量档最多 47 样本，见字段剖析文档）。我们现在的做法是
**硬阈值：样本 <30 或月份 <2 就整层丢弃，并入更粗层**。这会产生肉眼可见的偏差：
2026-05 波兰仓 809 个包裹因为细层被上一级吃光，整体落到「仓库×渠道」层，
预测中位 96.00 而实际 124.31（偏差 −19.56）。

所以问题不是「阈值定多少」，而是「细层样本不足时该怎样最合理地借用粗层信息」。
这在保险精算里是一个已经解决了几十年的问题。

## 1. 可信度理论（Credibility Theory）—— 保险精算的标准答案

费率表的每一个单元（风险类）其实都在做同一件事：把小样本的自身经验和稳定的整体经验
按可信度加权：

```
C = Z·X + (1−Z)·M
```

- `X` = 该单元自身经验（我们对应：细层中位数）
- `M` = 集体/先验经验（我们对应：上一层或全国中位数）
- `Z` = 可信度因子，`0 ≤ Z ≤ 1`

Bühlmann 可信度把 `Z` 从数据里估出来：

```
k = EPV / VHM
Z = n / (n + k)
```

- `EPV` = expected process variance（组内方差）
- `VHM` = variance of hypothetical means（组间方差）

`Z` 随样本量 `n` 增大、组间差异增大、组内波动减小而上升。
注意 `n/(n+k)` 的形状：**样本少时权重不会掉到 0，样本多时也不会瞬间跳到 1**，
这正是我们硬阈值缺失的行为。此外它还支持 Bühlmann–Straub 扩展（各单元曝光量不同），
以及**用稳健估计量替换样本均值**以抗厚尾。

工程含义：我们只需额外存 `Z`（或 `样本数` + `k`），线上按 `Z` 加权即可，
不需要把「细层/粗层」做成二选一的阶梯。

## 2. 分层贝叶斯 / 部分池化（partial pooling & shrinkage）—— 同一件事的现代形式

分层模型给每组一个参数，但假设这些参数来自共同的分布（总体均值 `μ`、组间标准差 `τ`）。
于是组估计被向总体均值收缩：

```
θ̂_j = (1 − B_j)·ȳ_j + B_j·μ
B_j = σ_j² / (τ² + σ_j²)
```

- 组内样本少 → 抽样方差 `σ_j²` 大 → `B_j → 1` → 强烈拉向总体均值
- 组内样本多 → `B_j → 0` → 保留自身均值
- James–Stein 定理：同时估计 ≥3 组时，收缩估计在总平方误差上**优于**原始估计

实务可行性：**经验贝叶斯（empirical Bayes）在 5–100 个组的规模上，结果与全贝叶斯
几乎无差别**，而计算量小得多。我们正好落在这个区间（几十到几百个层）。
完全池化（把所有层当同质）与完全独立（每层各算各的）是两个极端，中间就是部分池化。

## 3. 保险 GLM 的分阶段实务（可直接照搬的流程）

`insurancerating`（R，寿险/车险定价常用包）的标准工作流：

1. **先用 GAM 看连续变量的真实形状**（是否 U 形、断点在哪），不要假设线性
2. **划分档位**（derive tariff segments）——曲线描述连续关系，档位描述实际费率表
3. **拟合 GLM**（频率 Poisson / 强度 Gamma / 纯保费 Tweedie）
4. **薄数据处加可信度/收缩/惩罚分箱**：
   - `add_shrinkage()`：减少档位级之间的差异，但保持排序，且**不改变加权平均水平**
   - 惩罚分箱设**最小暴露量**约束（如 500 暴露年），不足者不得单独成层；用 BIC 选正则强度，
     再用 lasso 把系数精确压到中性值 1.0
   - **明确结论：当曝光量连最小暴露量都不够时，Bühlmann–Straub 可信度加权优于正则化**
   - 需要单调性时用**保序回归（isotonic regression）**约束，而不是事后手工调平
5. **把拟合的相对因子与观察经验对照**（`add_portfolio_experience()`）再发布

另一份材料补充：`ridge/lasso` 惩罚等价于带正态先验的贝叶斯估计，
`λ` 越大越贴近总体均值；这与可信度是同一思想的两种实现。

## 4. 末公里费率卡实务：维度与解析顺序

- **计价维度**：zone（分区）× 重量档（slab，如 0–0.5 / 0.5–1 / 1–2 kg，含续重与最低计费重）
  × 客户协议价；另有燃油、税费等附加费单列
- **分区解析顺序**：同城 → zone → 州 → 国；可被客户协议价覆盖（manual override）
- **计费重量** = max(实际重量, 体积重量)，体积重 = (L×W×H)/5000
- **数据驱动版本**：用 ML + 网络成本模型（Open Pricer / Kardinal），
  显式引入邮编、路由、星期、派送类型等——原文指出「末公里成本常被按平均值处理，
  忽略了邮编等关键因子」，这正是 HLF0001 的错误
- 也有专利用 `F(w, z)`（计费重量与分区的非线性函数）做成本敏感度排序

对照我们：zone 代理（ZIP3）、重量档、仓库、渠道都对上了；**缺的是「最低计费重/续重」
这一层语义**，以及客户协议价（VITE / M6180 / US-FEDEX 就是三条协议价——我们已经按渠道分开）。

## 5. 时间权重（近月加权）

- 支持：金融时间序列里「近期信息比久远信息更有价值」是共识，有参数化衰减
  （最近的样本权重 1，参数 `c` 控制衰减；`c<0` 时久远样本可被完全忽略）
- 但**衰减参数没有理论指导**，需从数据里网格搜索选损失最小的值
- 且有**过度打折的约束**：风控实务用「平衡点（balance point）」——加权后近半与远半
  的分界日不能太靠近当下（例如 250 天窗口下平衡点不得早于第 125 天）

对照我们：修正费用列后偏差已接近 0（202606 偏差 +0.02），**因此现阶段不做时间加权**；
若将来要做，衰减参数应从数据估计并设下限约束。

## 6. 标签溯源（label provenance）——本次踩过的坑

行业中「费率表不可信」最常见的根因不是统计方法，而是**标签口径错**。
我们刚经历的正是这一类：`包裹总运费` 口径不稳（同一包裹有时等于物流商运费、
有时等于通途运费），把它当训练目标导致波兰线整体预测偏低约 30%。
保险精算对此的对策是明确的**数据字典 + 口径验证 + 拟合值与观察经验对照**。

## 7. 折到本项目的改造清单（按性价比排序）

| 优先级 | 改动 | 理由 |
|--------|------|------|
| P0 | 训练标签只取**真实回传费用**（`物流商运费`）；建立"月初占位值"识别，避免把 EN 自己的预估当标签（循环训练） | 本次偏差的主因；业界共识：先保证口径 |
| P0 | 把「硬阈值 + 并入粗层」改为**可信度加权**：`C = Z·X + (1−Z)·M`，`Z = n/(n+k)`，`k` 由组内/组间方差估计；线上存 `Z` 与样本量 | 直接消除"细层被吃光后整体跳到粗层"的偏差；`n/(n+k)` 天然平滑 |
| P1 | **分层独立发布**（不要 exclusive 阶梯）：同一批数据允许 SKU 层与分区层并存，让解析器按 Z 选择或加权 | 现在 exclusive 会把细层吃光，导致非美国连 L2/L5 都是空的 |
| P1 | 非美国解析顺序补全并纳入目的国：`国家×SKU×仓库×渠道×重量` → `国家×仓库×渠道×重量` → `国家×仓库×渠道` → `国家×重量` → `国家` | 当前非美国只查 L2/L5/L8，而数据实际落在 L6/L7，导致 96 vs 124 |
| P2 | 重量档做**保序（单调）平滑**，缺失档位用相邻档插值而非直接跳到很粗层 | 避免档位跳变；业界用 isotonic |
| P2 | 每个发布行带 `样本数 / 覆盖月份 / Z / 置信等级`，让线上可解释 | 已做一半（样本数、置信等级已入库） |
| P3 | 时间衰减权重（参数从数据估、设平衡点下限） | 偏差已接近 0，暂不做 |
| P3 | 训练总体与打分总体对齐：月初缺失子集 ≠ 随机样本（美国偏便宜约 17%、DE/FR 偏贵约 30%），考虑按缺失总体单独校准或用重要性加权 | 业界做法是「对将要打分的总体建模」 |

## 8. 明确**不**建议的做法

- 不要用整体偏差校正系数把偏差压到 0：分月看 5 月两边都低估、6 月已 +0.02，
  整体校正会在 5 月制造新偏差（业界对应：不要用全局缩放替代分组估计）
- 不要为了「样本量足够」而合并本质不同的价目（VITE / M6180 / US-FEDEX），
  那正是 HLF0001「全国均价」的错误
- 不要在细层样本不足时直接删除该层而不发布样本量与可信度（不可审计）

## 来源

- [Fundamentals and Models of Credibility Theory](https://www.remnote.com/learn/math/applied-mathematics/fundamentals-and-models-of-credibility-theory-study-deck)
- [A general optimal approach to Bühlmann credibility theory (Insurance: Mathematics and Economics)](https://www.sciencedirect.com/science/article/abs/pii/S0167668722000245)
- [Credibility Parameters: Estimation and a Classical vs. Bühlmann Comparison](https://economics.town/actuarial-economics/credibility-estimation-classical-buhlmann-comparison/)
- [Credibility Theory (SOA/CAS handout)](http://www.actuary.com/seac/handouts/200906_03c_Credibility_Theory.pdf)
- [Credibility Distribution Estimation with Weighted or Grouped (Risks, 2024)](https://ideas.repec.org/a/gam/jrisks/v12y2024i1p10-d1312633.html)
- [Hierarchical Bayesian Models — partial pooling and shrinkage (MetricGate)](https://metricgate.com/blogs/bayesian-hierarchical-models-explained/)
- [Hierarchical Modeling for Small Samples and Many Groups](https://cursa.app/en/page/hierarchical-modeling-for-small-samples-and-many-groups)
- [Should we trust inferences from multilevel models? (Gelman, Columbia)](https://statmodeling.stat.columbia.edu/2007/10/24/should_we_trust/)
- [insurancerating — refinement workflow（分阶段：GAM → 档位 → GLM → smoothing/shrinkage/惩罚分箱）](http://ftp.naist.jp/pub/CRAN/web/packages/insurancerating/vignettes/refinement-workflow.html)
- [insurancerating 参考手册](https://cran.r-project.org/web/packages/insurancerating/refman/insurancerating.html)
- [Regressione Penalizzata e Credibilità nei GLM（惩罚回归与可信度）](http://www.sia-attuari.it/materiale/20250626_ISOA_PenalizedRegressionAndCredibilityInGlms.pdf)
- [Optimal Binning for GLM Rating Factors](https://burning-cost.github.io/2026/03/14/your-factor-banding-is-made-up/)
- [专利 US20160092831A1 — 单位运输成本敏感度 F(w, z)（计费重量 × 分区）](https://patents.google.com/patent/US20160092831A1/en)
- [专利 US20170206500A1 — 由邮政分区与承运商费率卡生成运输成本矩阵](https://patentimages.storage.googleapis.com/99/b0/f8/fcb38f9d3b0fa4/US20170206500A1.pdf)
- [iCargos 快递费率/资费管理（zone × 重量档 × 客户价 + 燃油税费）](https://www.icargos.com/customized-tariff)
- [Open Pricer × Kardinal 末公里定价优化（原文指出按平均成本处理会忽略邮编等关键因子）](https://www.spb.gov.cn/gjyzj/c200007/202307/a60b74e782ad42669dcfc852159ba5a2.shtml)
- [Mizar — Sample Weights（时间衰减权重与参数 c）](https://docs.mizar.com/mizar/mizarlabs/model/sample-weights)
- [Exponential weighting 与 balance point 约束](https://www.econstor.eu/bitstream/10419/224735/1/1733298630.pdf)
