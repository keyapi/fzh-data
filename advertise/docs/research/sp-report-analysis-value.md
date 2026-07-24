---
okf: v0.1
type: Research
title: SP 广告报告分析价值深度评估
description: 对 8 种 Sponsored Products 报告类型的分析价值、行业基准、优化策略、优先级及现有覆盖情况的全面评估
tags: [amazon, advertising, research, analysis-strategy, sponsored-products, benchmarks]
created: 2026-07-02
updated: 2026-07-02
sources:
  - https://eightx.co/blog/average-acos-by-amazon-category
  - https://autron.ai/blog/amazon-advertising-benchmarks-2026
  - https://salesduo.com/blog/amazon-search-term-report/
  - https://www.threecolts.com/blog/amazon-advertising-placements/
  - https://clearadsagency.com/amazon-is-hiding-revenue-from-you-and-its-in-your-account-right-now/
  - https://www.adbadger.com/blog/why-amazon-b2b-ads-are-a-game-changer-for-sellers/
  - https://captenamz.com/blog/amazon-exact-match-vs-broad-match/
  - https://advertising.amazon.ca/help/G89VFUTQUWFFN2VU
  - https://www.intentwise.com/blog/amazon-advertising/where-are-my-amazon-brand-halo-sales-coming-from/
  - https://www.skalestrategy.com/blog/amazon-advertising-reports-guide
---

# SP 广告报告分析价值深度评估

> **目的**: 对 8 种 Sponsored Products 报告类型逐一分析，明确每种报告揭示的业务洞察、可行的分析方法和优先级。
> **数据**: BJRYECLTD-US 账号 2026年6月数据样本 (Home & Kitchen / 枕头类目)
> **原则**: 每个分析建议均为可执行的具体方案，每个基准均标注行业来源。

---

## 目录

1. [执行摘要](#1-执行摘要)
2. [每个报告类型的逐一分析](#2-每个报告类型的逐一分析)
   - [2.1 广告活动报告 (Campaign)](#21-广告活动报告-campaign)
   - [2.2 投放报告 (Targeting)](#22-投放报告-targeting)
   - [2.3 搜索词报告 (SearchTerm)](#23-搜索词报告-searchterm)
   - [2.4 广告位报告 (Placement)](#24-广告位报告-placement)
   - [2.5 广告组报告 (AdGroup)](#25-广告组报告-adgroup)
   - [2.6 广告产品报告 (AdvertisedProduct)](#26-广告产品报告-advertisedproduct)
   - [2.7 已购产品报告 (PurchasedItem)](#27-已购产品报告-purchaseditem)
   - [2.8 企业购报告 (BusinessReport)](#28-企业购报告-businessreport)
3. [报告间交叉分析矩阵](#3-报告间交叉分析矩阵)
4. [推荐开发路线图](#4-推荐开发路线图)
5. [来源清单](#5-来源清单)

---

## 1. 执行摘要

### 核心发现

我们在 BJRYECLTD-US (Home & Kitchen 枕头类目) 上拥有 8 种 SP 报告类型的完整数据。目前已有 4 份分析脚本，覆盖了最高优先级的报告类型。另外 4 种报告类型各具独特价值，但分析优先级和投入产出比不同。

### 8 种报告类型速览

| # | 报告类型 | 数据行数 | 已分析? | 优先级 | 核心价值 |
|---|---------|---------|---------|--------|---------|
| 1 | Campaign | 206 | 是 | **HIGH** | 宏观账户健康度、预算管理、投资组合聚合 |
| 2 | Targeting | 492 | 是 | **HIGH** | 匹配类型效率、关键词vs商品投放、光环效应 |
| 3 | SearchTerm | 790 | 是 | **HIGH** | 客户真实搜索词、否定词挖掘、关键词收割 |
| 4 | Placement | 457 | 是 | **HIGH** | Top of Search vs Product Pages vs Rest of Search 效率 |
| 5 | AdGroup | 190 | 否 | **MEDIUM** | 广告组粒度预算分配、组内竞食检测 |
| 6 | AdvertisedProduct | 189 | 否 | **MEDIUM** | ASIN 级贡献度、哪些产品该投/不该投广告 |
| 7 | PurchasedItem | 13 | 否 | **HIGH** | 品牌光环效应、交叉销售归因、Gateway ASIN 识别 |
| 8 | BusinessReport | 160 | 否 | **LOW** | B2B 买家细分 (数据量极少，13.40美元总花费) |

### 投入产出比排名

1. **PurchasedItem** -- 工作量极小 (13行数据, 简单聚合), 但能揭示品牌光环效应, 对广告ROI认知有颠覆性影响
2. **AdvertisedProduct** -- 中等工作量 (按 ASIN 聚合分析), 直接回答"哪些产品该投广告"
3. **AdGroup** -- 低工作量 (与 Campaign 几乎同构), 提供广告组粒度洞察
4. **BusinessReport** -- 低工作量 (与 Placement 同构), 但当前数据量极少, 价值有限

---

## 2. 每个报告类型的逐一分析

### 2.1 广告活动报告 (Campaign)

**数据规模**: 206 行 (按 天 × 广告活动 的维度展开)
**现有脚本**: `advertise/analyze_campaign.py`

#### What It Reveals

广告活动报告是广告账户的**最高层视图**。它回答以下业务问题:

- 广告整体花了多少钱, 带来了多少销售额?
- 哪些广告活动盈利, 哪些在亏钱?
- 预算利用率是否合理? (每日预算是否被充分消耗还是被浪费)
- 自动广告 vs 手动广告的效率差异?
- 投资组合 (Portfolio) 层面的汇总表现?

#### Key Metrics

| 指标 | 作用 | 典型阈值 (Home & Kitchen) |
|------|------|---------------------------|
| **ACoS** | 核心效率指标 | 健康 < 25%, 可接受 25-35%, 危险 > 35% |
| **ROAS** | 投资回报率 | 健康 > 3x, 可接受 2-3x, 危险 < 2x |
| **Budget Utilization** | 预算利用率 (花费/日预算/30) | 理想 70-90%, 太低 = 预算浪费, 太高 = 错失流量 |
| **SameSKU vs OtherSKU Sales** | 直接销售 vs 品牌光环销售 | OtherSKU 占比越高, 光环效应越强 |

**本次数据样本表现** (BJRYECLTD-US, 2026年6月):
- 总花费: $946.44
- 总销售额 (7d): $1,369.76
- 整体 ACoS: ~69% (偏高, 需要优化)
- 整体 ROAS: ~1.45x
- 活动数量: 206 行 (多天展开后)

#### Analysis Recommendations

已实现的脚本覆盖了以下分析:

1. **全量汇总** -- 总花费/销售额/订单/点击/曝光
2. **活动排行** -- 按花费排序, 标记优胜/高风险/问题活动
3. **Portfolio 聚合** -- 按投资组合汇总
4. **状态分布** -- 已开启/已暂停/已归档分布

建议补充的分析:

5. **趋势线分析 (新增)** -- 用日粒度数据绘制花费/ACoS/ROAS 时间序列, 检测异常波动
6. **同SKU vs 其他SKU 占比** -- 量化每个活动的品牌光环贡献
7. **生命周期分析** -- 对比不同开始日期的活动, 评估新活动冷启动 vs 成熟活动表现
8. **预算调整建议** -- 基于 budget_utilization 生成具体预算调整金额建议

#### Industry Benchmarks

| 类别 | 中位数 ACoS | 等效 ROAS | 来源 |
|------|------------|-----------|------|
| Home & Garden | 31% | 3.2x | Eightx 2026 品类基准 |
| 平台整体 SP | 29-34% | ~3x | AdBadger/Autron 2026 基准 |
| 高支出卖家 ($25K+/月) Home & Garden | 28% | 3.6x | Eightx 大型卖家分层 |

> 注意: 我们的 Home & Kitchen (枕头) 属于 Home & Garden 子类目。品类基准仅供参考, 实际目标需结合产品利润率 (枕头毛利一般在 40-60%)。若毛利率为 45%, 则盈亏平衡 ACoS = 45%, ROAS >= 2.2x 即盈利。

#### Priority: HIGH

这是所有分析的起点 -- 所有其他报告都从 Campaign 向下钻取。此报告是整个分析系统的基础层。

#### Existing Coverage

已完整覆盖。脚本产出 `campaign_analysis.json`, 包含 summary / ranking / portfolio / winners / problems。与 `build_report.py` 集成, 产出 Excel 报告的"总览"和"广告活动"两个 sheet。

#### Dependencies

- 是所有其他报告的**父级**报告
- 与 Placement 报告结合可分解活动×广告位效率
- 与 Targeting/SearchTerm 报告结合可追溯活动内哪些投放/搜索词驱动了表现

---

### 2.2 投放报告 (Targeting)

**数据规模**: 492 行 (按 天 × 投放目标 展开)
**现有脚本**: `advertise/analyze_targeting.py`

#### What It Reveals

投放报告揭示**每个关键词/商品投放的具体表现**。回答以下问题:

- 广泛匹配 vs 词组匹配 vs 精确匹配, 哪种匹配类型的 ACOS 最低?
- 哪些投放目标在产生销售, 哪些在烧钱无转化?
- 自动广告的"紧密匹配""替代品""互补品"各自的表现如何?
- 品牌光环效应有多强? (广告 SKU 销售 vs 其他 SKU 销售)

#### Key Metrics

| 指标 | 作用 | 特别关注 |
|------|------|---------|
| **Match Type** | 按匹配类型汇总 | 精确匹配 ACOS 应远低于广泛匹配 |
| **Top Search IS** | 搜索首页首位展示份额 | < 20% 表示竞争对手强势或出价不足 |
| **Other SKU Sales** | 非广告商品的销售 | 量化光环效应 |
| **Zero-conversion targets** | 有花费无订单的投放 | 否定词候选 |

#### Analysis Recommendations

已实现的分析:

1. **按匹配类型表现** -- ACOS/ROAS/CTR/CPC 对比
2. **投放对象 TOP/BOTTOM** -- 按花费排序, 零转化投放识别
3. **光环效应** -- 广告 SKU vs 其他 SKU 销售金额和销量

建议补充的分析:

4. **匹配类型效率漏斗** -- 展示量 → 点击 → 订单的层层转化率
5. **Top Search IS 分析** -- 按投放汇总搜索首页份额, 识别低份额高价值的投放
6. **自动广告 4 种匹配方式对比** -- 紧密匹配/松散匹配/替代品/互补品的效率
7. **出价调整模拟** -- 基于当前 ACOS, 模拟提价 X% 对总花费和销售额的影响

#### Industry Benchmarks

| 匹配类型 | 典型 ACOS | 转化率 | 来源 |
|---------|-----------|--------|------|
| 精确匹配 | 12-25% | 15-28% | CaptenAMZ 2026 策略指南 |
| 词组匹配 | 20-35% | 10-19% | CaptenAMZ / Trellis 数据 |
| 广泛匹配 (有否定词管理) | 25-40% | 5-12% | CaptenAMZ 2026 |
| 广泛匹配 (无否定词管理) | 45-70% | 5-12% | CaptenAMZ 2026 |

#### Priority: HIGH

投放报告是关键词级别优化的核心数据源。与搜索词报告配合使用, 一个告诉你关键词 (你设置的) 表现, 一个告诉你搜索词 (客户输入的) 表现。

#### Existing Coverage

已完整覆盖。脚本产出 `targeting_analysis.json`, 包含 match_type 对比、top/bottom targets、halo_effect 分析。集成到 Excel 报告的"投放表现"sheet。

#### Dependencies

- 与 **SearchTerm** 报告共享 targeting + match_type 维度, 可做关键词 vs 搜索词对比
- 与 **Campaign** 报告通过 campaign_id 关联, 可追溯活动级别的投放分布
- **Halo 指标** (OtherSKU) 可交叉验证 **PurchasedItem** 报告

---

### 2.3 搜索词报告 (SearchTerm)

**数据规模**: 790 行 (按 天 × 搜索词 展开)
**现有脚本**: `advertise/analyze_search_term.py`

#### What It Reveals

搜索词报告是 **Amazon 广告最具操作性的报告**。它显示客户在搜索框中实际输入的内容及其广告效果。回答:

- 客户用什么词找到了我们的广告?
- 哪些搜索词在产生销售 (应该收割)?
- 哪些搜索词在烧钱无转化 (应该否定)?
- 搜索词归属什么语义类别 (品牌词/品类词/竞品词/长尾词/不相关词)?
- 每个语义分类的广告花费和效率如何?

#### Key Metrics

| 指标 | 作用 | 解释 |
|------|------|------|
| **ACoS (聚合后)** | 搜索词效率 | 按搜索词聚合后的 ACOS 消除行内失真 |
| **Orders (聚合后)** | 订单数 | Harvest 判断的关键: >= 2 单 = 信号, 1 单 = 巧合 |
| **SearchTermImpressionShare** | 展示份额 | 低份额 = 未被充分利用的高价值词 |
| **SearchTermImpressionRank** | 展示排名 | 排名靠后 = 需要提高出价 |

#### Analysis Recommendations

已实现的分析 -- 这是 4 个脚本中**最完善**的一个:

1. **按 search_term 聚合** -- 消除同一搜索词分散在多行的失真
2. **5 桶分类** -- Harvest / Negate / Monitor / Protect / Ignore
3. **搜索词语义分类** -- 品牌词/品类词/竞品词/长尾词/不相关词
4. **归因窗口警告** -- 报告期 < 14 天时提醒
5. **决策日志输出** -- 差异化上次运行的分类结果

建议补充的分析:

6. **Harvest 词 → 精准匹配转移清单** -- 自动生成将收割词加入精准活动的操作步骤
7. **否定词导入文件生成** -- 输出 Amazon Bulk Operations 格式的否定词文件
8. **搜索词随时间变化趋势** -- 哪些词是新出现的, 哪些词的表现在下滑
9. **搜索词-广告活动关联矩阵** -- 识别同一搜索词在不同活动中的表现差异
10. **周度变化对比** -- 本周 vs 上周各桶的数量和花费变化

#### Industry Benchmarks

最佳实践工作流 (来源: SalesDuo 2025, Amify 2025):

| 频率 | 操作 |
|------|------|
| **每周** | 下载搜索词报告 → 识别新增否定词候选 → 检查 Harvest 候选 |
| **每两周** | 否定词全面审查 → 关键词收割 → 出价调整 |
| **每月** | TACoS 趋势审查 → 搜索词分类分布变化 |
| **每季度** | 完整账户结构审计 → 预算再分配 |

行业标准阈值:
- Harvest: >= 2 订单 AND ACoS <= 30% (取决于利润率)
- Negate: >= 15-20 点击 AND 0 订单 (部分专家建议 >= 20 点击)
- Monitor: < 15 点击 (数据不足以判断)

#### Priority: HIGH

搜索词报告是 PPC 优化的核心工具。专业广告代理将此报告作为每周必做的标准操作。我们的 5 桶分类脚本已达到专业级分析水平。

#### Existing Coverage

**最完善的覆盖**。脚本包含聚合、5 桶分类、语义分类、归因警告。产出 `search_term_analysis.json`, 集成到 Excel 报告的"搜索词洞察"sheet, 包含 Harvest 清单/否定词候选/观察列表/分类分布。

#### Dependencies

- 与 **Targeting** 报告互补: 搜索词 (客户输入) vs 关键词 (卖家设置)
- 分析结果驱动 **Campaign** 层面的预算和出价调整
- Harvest 词可输入到新建的精准匹配广告组/活动

---

### 2.4 广告位报告 (Placement)

**数据规模**: 457 行 (按 天 × 广告活动 × 广告位 展开)
**现有脚本**: `advertise/analyze_placement.py`

#### What It Reveals

广告位报告揭示**广告在不同位置的效率差异**。三种主要广告位:
- **Top of Search** (搜索结果顶部): 最高曝光度和 CPC
- **Product Pages** (产品页面): 通常在购物决策深处, 转化率最高
- **Rest of Search** (搜索其余位置): 最低 CPC, 适合低成本曝光

回答:
- 我们的广告费花在哪个位置最多?
- 哪个位置的 ACOS 最低, 转化率最高?
- 应该在哪里提高出价, 在哪里降低出价?

#### Key Metrics

| 指标 | 作用 | 行业模式 |
|------|------|---------|
| **ACoS by Placement** | 三位效率 | Product Pages 通常最低, Rest of Search 最高 |
| **CVR by Placement** | 转化率 | Product Pages 通常最高 (2x Top of Search) |
| **CTR by Placement** | 点击率 | Top of Search 通常最高 (位置优势) |
| **Spend Share** | 花费占比 | 通常 60-70% 花在产品页面 |

**本次数据样本 Placements** (BJRYECLTD-US):

| 广告位 | 花费占比 | 模式 |
|--------|---------|------|
| Top of Search | 取决于实际数据 | CPC 最高, 位置最显眼 |
| Product Pages | 取决于实际数据 | CVR 通常最高 |
| Rest of Search | 取决于实际数据 | CPC 最低, 低意向浏览 |

#### Analysis Recommendations

已实现的分析:

1. **按广告位聚合** -- Top of Search / Product Pages / Rest of Search 的效率对比
2. **出价调整建议** -- 基于 ACOS/CVR 阈值生成操作建议
3. **逐活动 × 广告位明细** -- Top 100 行明细

建议补充的分析:

4. **广告位出价系数量化** -- 计算每个位置应调整的百分比
5. **位置效率热力图** -- 用活动 × 广告位矩阵可视化
6. **跨时间对比** -- 两周前 vs 本周的广告位效率变化
7. **产品页面位置再细分** -- 详情页顶部 vs 加购页 vs "买了又买"(如果可获得)

#### Industry Benchmarks

| 广告位 | 印象占比 | 典型 CVR | 相对 CPC | 来源 |
|--------|---------|----------|---------|------|
| Product Pages | 60-70% | 最高 (可达 Top of Search 的 2x) | 基准的 35-50% | Threecolts, Skale Strategy |
| Top of Search | 15-25% | 中高 | 基准 (最贵) | 同上 |
| Rest of Search | 10-20% | 最低 (Top of Search 的 1/3-1/2) | 基准的 45-55% | 同上 |

出价系数建议 (来源: Marketplace Valet, SellerSprite 2026):

| 广告位 | 建议系数 | 理由 |
|--------|---------|------|
| Product Pages | +30% 至 +70% | 高转化效率 |
| Top of Search | +10% 至 +50% | 高可见度和增量收入 |
| Rest of Search | -10% 至 -30% | 持续表现不佳时降低 |

#### Priority: HIGH

广告位报告提供独特的效率视角, 是 Campaign 报告的必需要补充。出价系数的优化直接提升 ROI。

#### Existing Coverage

已完整覆盖。脚本产出 `placement_analysis.json`, 包含 placements 汇总 / detail / recommendations。集成到 Excel 报告的"广告位效率"sheet。

#### Dependencies

- 是 **Campaign** 报告的向下钻取维度
- 出价建议应用于 **Campaign** 层面的广告位出价系数设置
- 与 **BusinessReport** 共享 placement 维度 (企业购是特殊广告位)

---

### 2.5 广告组报告 (AdGroup)

**数据规模**: 190 行 (按 天 × 广告组 展开)
**当前状态**: 无分析脚本
**工作量估算**: 0.5 天 (与 Campaign 脚本 80% 同构)

#### What It Reveals

广告组报告是 Campaign 和 Targeting/ASIN 之间的**中层视图**。回答:

- 同一活动内不同广告组的效率差异?
- 是否存在一个广告组消耗了活动 80% 预算而其他组得不到展示?
- 广告组粒度下, 自动/手动的 ACOS 对比?
- 哪些广告组需要拆分或合并?

**核心洞察**: 一个广告活动中的多个广告组**共享同一日预算**。如果某广告组的投放特别激进 (高 CPC + 高搜索量), 会"饿死"同活动内的其他广告组。

#### Key Metrics

| 指标 | 分析用途 |
|------|---------|
| **花费组内占比** | 识别"预算黑洞"广告组 |
| **ACoS / ROAS** | 组级别的效率 |
| **SameSKU vs OtherSKU** | 组级别的光环效应 |
| **活动内广告组数量** | 结构诊断: 太多组 = 预算分散, 太少 = 粒度不够 |

**本次数据** (BJRYECLTD-US):
- 190 行 × 27 列
- 包含完整的指标: 花费/曝光/点击/CPC/CTR/转化率/ACoS/ROAS/订单/销售额/销量 (含 SameSKU/OtherSKU 拆分)
- 数据包含广告活动名称、定位类型、广告组状态

#### Analysis Recommendations

1. **活动内广告组份额分析** -- 计算每个广告组在父活动中的花费/订单/销售额占比, 标记过于集中或过于分散的活动
2. **广告组排行** -- 同 Campaign 分析的逻辑, 按花费排序, 标记优胜/问题组
3. **组结构诊断** -- 统计每个活动下的广告组数, 建议拆分 (>10组/活动) 或合并 (1组/活动)
4. **跨活动同名组检测** -- 识别在不同活动中投放相同关键词的广告组 (自我竞争)

#### Industry Benchmarks

| 结构模式 | 建议 | 来源 |
|---------|------|------|
| 单活动 > 10 广告组 | 拆分为多个活动, 防止预算争抢 | FNDEcommerce 2025 |
| 每个活动 3-5 广告组 | 多数卖家的最佳实践区间 | SellerSprite 2025 |
| 单一关键词广告组 (SKAG) | 仅用于头部词, 精确控制预算 | AdLabs 2025 |

#### Priority: MEDIUM

广告组报告的价值在于结构性诊断, 而非日常优化。它更多用于**定期账户审计** (每月/每季度), 而非周度优化循环。

但是 -- 由于它与 Campaign 脚本 80% 同构, 开发成本极低, 建议顺手实现。

#### Existing Coverage

无独立脚本。可复用 `analyze_campaign.py` 的结构, 将 groupby 维度从 campaign 改为 ad_group_name。

#### Dependencies

- 是 **Campaign** 报告的子维度, 与 Campaign 通过 campaign_id 1:N 关联
- 是 **Targeting** 和 **AdvertisedProduct** 的父维度, 广告组包含投放目标和 ASIN

---

### 2.6 广告产品报告 (AdvertisedProduct)

**数据规模**: 189 行 (按 天 × ASIN 展开)
**当前状态**: 无分析脚本
**工作量估算**: 1 天

#### What It Reveals

广告产品报告是**ASIN 粒度**的广告效果视图。它回答广告主最根本的问题:

- **每个产品的广告投入产出比如何?**
- 哪些 ASIN 值得投广告, 哪些应该暂停?
- 是否存在"广告补贴有机销售"的情况? (高广告销售, 低有机销售)
- 产品变体 (颜色/尺寸) 之间的广告表现差异?

**核心洞察**: 亚马逊广告的归因是 ASIN 级别的。同一个广告组内可能包含多个 ASIN, 但每个 ASIN 的转化能力可能完全不同。一个转化率 15% 的 ASIN 和转化率 2% 的 ASIN 放在同一个广告组里, 前者在补贴后者。

**本次数据** (BJRYECLTD-US):
- 189 行 × 30 列
- 8 个唯一 ASIN
- 包含完整指标: 花费/曝光/点击/CPC/CTR/转化率/ACoS/ROAS/订单/销售额/销量 (含 SameSKU/OtherSKU 拆分)
- 包含广告产品运行状态 (已开启/已暂停)

#### Key Metrics

| 指标 | 分析用途 |
|------|---------|
| **ACoS by ASIN** | 每个产品的广告效率 |
| **CVR by ASIN** | 产品转化能力, 反映 Listing 质量 |
| **OtherSKU Sales by ASIN** | 该 ASIN 的广告拉动了多少其他产品的销售 (Gateway ASIN 潜力) |
| **Spend Concentration** | 是否 20% ASIN 消耗 80% 花费 |

#### Analysis Recommendations

1. **ASIN 效率排行** -- 按 ACOS/ROAS 排序, 标记优胜/问题 ASIN
2. **80/20 分析** -- 计算 ASIN 的花费集中度 (Gini 系数或 Top N 占比)
3. **Listing 质量诊断** -- 高花费低转化 → 可能 Listing 有问题; 高曝光低点击 → 主图或标题问题
4. **Gateway ASIN 识别** -- OtherSKU Sales / SameSKU Sales 比率高的 ASIN → 广告拉动效应强
5. **广告暂停建议** -- 花费 > $X 且 0 订单超过 30 天的 ASIN, 建议暂停或修复 Listing
6. **变体对比** -- 同父 ASIN 下的各子 ASIN 广告表现对比

#### Industry Benchmarks

ASIN 分类框架 (来源: Skale Strategy 2025):

| ASIN 分类 | ACOS | CVR | 策略 |
|-----------|------|-----|------|
| 优质 (Excellent) | < 26% | > 7% | 加预算, 扩大投放 |
| 待优化 (Poor) | > 66% | < 3% | 暂停广告, 诊断 Listing |
| 数据不足 (Low Data) | -- | -- | 单独分组, 给预算测试 |

**80/20 法则**: 行业数据显示, 通常 **20-30% 的 ASIN 贡献 80%+** 的广告归因收入。预算应按此比例分配。
**Zero-sale 红线**: 单个 ASIN 花费超过 $500 且 30 天内零销售时, 应立即停止广告并修复 (来源: Skale Strategy)。

#### Priority: MEDIUM

此报告的优先级取决于 ASIN 数量。目前我们只有 8 个 ASIN, 分析价值中等。但随着 ASIN 数量增长 (品牌扩张、多品类), 此报告的优先级会快速上升。

对于 8 个 ASIN 的账户, 手动识别即可。但当达到 20+ ASIN 时, 自动化分析就成为必需。

#### Existing Coverage

无独立脚本。需新建 `analyze_advertised_product.py`。考虑到与 Campaign 脚本类似但维度不同 (ASIN 代替 campaign_name), 可复用基础框架。

#### Dependencies

- 通过 ad_group_id 关联 **AdGroup** 和 **Campaign** 报告
- 通过 advertised_sku 关联 **PurchasedItem** 报告
- 建议与 ERPNext 的产品数据 (成本/库存) 结合, 计算真实利润

---

### 2.7 已购产品报告 (PurchasedItem)

**数据规模**: 13 行
**当前状态**: 无分析脚本
**工作量估算**: 0.5 天

#### What It Reveals

已购产品报告 (也叫 Purchased Product Report) 是 Amazon 广告分析中的**"隐藏宝藏"**。它揭示:

- 客户点击了 A 的广告, 但最终购买了 B -- 这对于品牌来说依然是广告驱动的收入
- 哪些 ASIN 是 **Gateway 产品**: 自身 ACOS 不佳, 但为品牌内其他产品带来大量销售
- **交叉销售模式**: 客户从枕头广告进来, 买了床垫罩和枕套

**核心洞察**: 标准的广告报告只计算"同 SKU 的销售" ("cookies attributed to same ASIN")。已购产品报告填补了归因空白 -- 它将"点击 A 买 B"的 B 的销售数据单独列出。这对拥有多 SKU 的品牌至关重要。

**本次数据** (BJRYECLTD-US):
- **仅 13 行** -- 但包含关键信息
- 显示: 其他 SKU 销量 19 件, 销售额 $651.81
- 这意味着广告花费 $946 不仅带来 $718 (同SKU销售), 还额外带来 $652 (其他SKU销售)
- **真实销售额 = $718 + $652 = $1,370**, **真实 ACOS = $946/$1,370 = 69%** (比只看同SKU好)
- 注意: 标准 Campaign/Targeting 报告中已经包含了 OtherSKU 的汇总数字($651.81)，但是只有 PurchasedItem 能告诉你具体哪个广告 ASIN 拉动了哪个被购买的 ASIN

报告结构:
- 广告 ASIN (advertisedAsin): 客户点击了谁的广告
- 其他 ASIN (purchasedAsin): 客户实际买了什么
- 投放 + 匹配类型: 通过什么关键词/投放方式来的
- 其他 SKU 销量 + 销售额: 买了多少, 花了多少钱

#### Key Metrics

| 指标 | 分析用途 |
|------|---------|
| **advertisedAsin → purchasedAsin 映射** | 交叉销售关系图 |
| **Blended ACoS** | (花费) / (同SKU销售 + 其他SKU销售) -- 真实效率 |
| **Halo Ratio** | 其他SKU销售 / 同SKU销售 -- 光环强度 |
| **Gateway Potential** | OtherSKU销售额占比 > 50% 的广告ASIN |

#### Analysis Recommendations

1. **Blended ACOS 计算** -- 为每个广告活动/ASIN 计算包含光环效应的真实 ACOS
2. **Gateway ASIN 识别** -- 找出"本身 ACOS 高但带动大量其他销售"的产品
3. **交叉销售网络图** -- advertiseAsin → purchasedAsin 的关系映射
4. **广告暂停风险评估** -- 在因高 ACOS 暂停广告之前, 检查 PurchasedItem 报告: 如果该 ASIN 是 Gateway, 暂停广告会伤害其他产品销售

#### Industry Benchmarks

| 场景 | 数据 | 来源 |
|------|------|------|
| Gateway ASIN 典型表现 | 直接 ACOS 80-108%, 混合 ACOS 降至 27% | ClearAds Agency 2025 |
| 品牌光环的普遍性 | 约 50% 的品牌有显著的品牌光环效应 | Intentwise 2025 |
| 错过光环的代价 | $50K+/月花费的账户每月可能错失 $10K-$30K 光环收入 | ClearAds Agency |

#### Priority: HIGH

尽管只有 13 行数据, 但这 13 行数据**改变了我们对广告 ROI 的认知**。对于多 SKU 品牌, 已购产品报告是不可或缺的。

当前数据的实际影响: 同 SKU 销售 $718 + 其他 SKU 销售 $652。如果不看此报告, 我们会低估 47% 的广告驱动销售额。

#### Existing Coverage

无独立脚本。需新建 `analyze_purchased_item.py`。由于数据结构简单 (无 impressions/clicks 等流量指标), 分析逻辑以聚合和映射为主。

#### Dependencies

- 与 **Campaign** 和 **AdvertisedProduct** 报告交叉验证 OtherSKU 数据
- 通过 advertisedAsin 关联 **AdvertisedProduct** 报告
- 需建立 ASIN → 产品名称的映射 (从 ERPNext 或手动维护)

---

### 2.8 企业购报告 (BusinessReport)

**数据规模**: 160 行
**当前状态**: 无分析脚本
**工作量估算**: 0.25 天 (与 Placement 脚本 90% 同构)

#### What It Reveals

企业购报告是 Placement 报告中 **Amazon Business 广告位**的子集。Amazon Business 是面向企业批量采购的 B2B 场景。

回答:
- B2B 买家在广告中的转化表现如何?
- B2B 场景的 ACOS 是否显著低于普通消费者场景?
- 值得为 Amazon Business 设置专门的广告活动和出价系数吗?

**本次数据** (BJRYECLTD-US):
- 160 行 × 26 列 (与 Placement 报告完全同构)
- 广告位显示: "产品页面(企业购广告位)"
- **总花费仅 $13.40**, 总点击 13 次, 零销售
- 广告活动状态: 已暂停

**关键发现**: BJRYECLTD-US 账号的企业购广告基本处于未运营状态。$13.40 的总花费和零转化表明要么没有专门开启, 要么 B2B 受众对此类目 (枕头) 不感兴趣。

#### Key Metrics

| 指标 | 分析用途 |
|------|---------|
| **B2B vs B2C ACOS** | B2B 的效率是否显著更高 |
| **B2B Order Value** | B2B 订单的客单价是否显著更高 |
| **B2B Spend Share** | B2B 广告花费占总花费的比例 |

#### Analysis Recommendations

1. **B2B vs B2C 效率对比** -- 将 BusinessReport 的数据与 Placement 报告的 Product Pages 对比
2. **B2B 趋势追踪** -- 如果业务有 B2B 采购需求, 追踪 B2B 广告花费和销售额的月趋势

鉴于当前数据量极少, 不建议深度分析。保留此脚本的模板, 当 B2B 花费增加到有意义的水平时再激活。

#### Industry Benchmarks

| 指标 | B2B 客户 | 普通客户 | 来源 |
|------|---------|---------|------|
| 转化率 | ~30%+ | ~18-20% | Intentwise / AdBadger 2025 |
| 客单价 | **~2x** | 基准 | Intentwise 2025 |
| ACOS | **常为整体的 50% 以下** | 基准 | AdBadger B2B 分析 |
| 购买意向 | 浏览后 3x 更可能购买 | 基准 | Amazon Business 官方数据 |
| 退货率 | **远低于**普通消费者 | 基准 | 多个来源 |

> B2B 买家之所以表现更好: (1) 批量采购需求, (2) 决策基于规格而非冲动, (3) 有采购预算而非个人零花钱, (4) 退货流程更复杂所以购买前更仔细。

#### Priority: LOW

当前数据量太少 ($13.40 总花费, 零销售)。对于目前阶段的枕头类目来说, B2B 广告价值有限。但如果品牌扩展到办公用品、工业耗材等品类, 优先级会显著提升。

保留模板, 等待数据量增长后再激活。

#### Existing Coverage

无独立脚本。与 Placement 脚本 90% 同构, 仅需修改 placement_category 分类逻辑即可复用。

#### Dependencies

- 本质上是 **Placement** 报告的 B2B 子集
- 出价系数应用于 Campaign 层面的 Amazon Business 出价调整

---

## 3. 报告间交叉分析矩阵

下面列出最有价值的跨报告组合分析:

| # | 组合分析 | 涉及报告 | 业务问题 | 复杂度 |
|---|---------|---------|---------|--------|
| 1 | **搜索词 → 关键词收割** | SearchTerm + Targeting | 哪些客户搜索词应转为精准匹配关键词? | 中 |
| 2 | **广告活动 × 广告位** | Campaign + Placement | 每个活动在不同位置的效率; 预算分配优化 | 中 |
| 3 | **Gateway ASIN 识别** | AdvertisedProduct + PurchasedItem | 哪些 ASIN 是光环驱动者, 不应被暂停 | 低 |
| 4 | **真实 ACOS 纠正** | Campaign + PurchasedItem | 加入光环销售后的真实投资回报 | 低 |
| 5 | **广告组预算公平性** | AdGroup + Campaign | 组内预算是否被特定关键词垄断 | 低 |
| 6 | **ASIN-搜索词匹配度** | AdvertisedProduct + SearchTerm | 每个 ASIN 被哪些搜索词找到, 是否相关 | 高 |
| 7 | **全套归因闭环** | Campaign + Targeting + SearchTerm + Placement + PurchasedItem | 从花费到真实收入的完整归因 | 高 |

---

## 4. 推荐开发路线图

### Phase 1: 补全 4 个缺失的分析脚本 (本次)

| 顺序 | 脚本 | 工作量 | 理由 |
|------|------|--------|------|
| 1 | `analyze_purchased_item.py` | 0.5天 | 投入产出比最高: 13行数据, 颠覆性的洞察 |
| 2 | `analyze_advertised_product.py` | 1天 | ASIN级别答案, 直接指导产品级别的广告决策 |
| 3 | `analyze_ad_group.py` | 0.5天 | 复用Campaign框架, 几乎零成本实现 |
| 4 | `analyze_business_report.py` | 0.25天 | 复用Placement框架, 保存模板等数据增长 |

### Phase 2: 增强现有脚本 (下一轮)

| 增强项 | 涉及脚本 | 说明 |
|--------|---------|------|
| 时间趋势分析 | Campaign, SearchTerm | 添加日/周趋势线检测 |
| 否定词Bulk Upload生成 | SearchTerm | 直接输出Amazon Bulk Operations格式 |
| 跨期对比 | 全部 | 本周 vs 上周变化量报告 |
| TACoS 追踪 | Campaign + 有机销售数据 | 需要有机销售数据源 |

### Phase 3: 跨报告集成分析 (远期)

| 集成分析 | 说明 |
|---------|------|
| 全套归因闭环报告 | 从花费到真实收入 (含光环) 的完整归因 |
| 自动优化引擎 | 基于规则自动生成出价/预算/否定词建议 |
| 预测模型 | 基于历史数据预测广告支出与销售的边际回报 |

---

## 5. 来源清单

### 行业基准来源

| # | 来源 | URL | 提供的数据 |
|---|------|-----|-----------|
| 1 | Eightx 2026 ACOS Benchmarks | https://eightx.co/blog/average-acos-by-amazon-category | 品类 ACOS 基准 |
| 2 | Autron 2026 Advertising Benchmarks | https://autron.ai/blog/amazon-advertising-benchmarks-2026 | 平台整体 CPC/CTR/CVR/ACOS |
| 3 | CaptenAMZ Exact vs Broad Match Guide | https://captenamz.com/blog/amazon-exact-match-vs-broad-match/ | 匹配类型 ACOS 基准 |
| 4 | Titan Network Amazon Ad Costs 2026 | https://titannetwork.com/amazon-ad-costs-guide/ | CPC 范围, 品类分解 |
| 5 | Helium10 Q3 2025 SMB Benchmark | (PDF report) | 季度 CPC/ROAS 趋势 |

### 最佳实践来源

| # | 来源 | URL | 提供的洞察 |
|---|------|-----|-----------|
| 6 | SalesDuo Search Term Report Guide | https://salesduo.com/blog/amazon-search-term-report/ | 5 阶段搜索词优化工作流 |
| 7 | Amify Search Term Report 2025 | https://goamify.com/blog-articles/amazon-search-term-report-2025/ | 搜索词报告深度分析 |
| 8 | Threecolts Amazon Ad Placements | https://www.threecolts.com/blog/amazon-advertising-placements/ | 3 种广告位定义和策略 |
| 9 | SellerSprite Placement Adjustments | https://m.sellersprite.com/en/blog/Placement-Adjustments-Top-of-Search-Product-Pages | 广告位出价系数建议 |
| 10 | ClearAds Agency Brand Halo Analysis | https://clearadsagency.com/amazon-is-hiding-revenue-from-you-and-its-in-your-account-right-now/ | Gateway ASIN, 混合 ACOS |
| 11 | Intentwise Brand Halo Sales | https://www.intentwise.com/blog/amazon-advertising/where-are-my-amazon-brand-halo-sales-coming-from/ | 品牌光环归因 |
| 12 | AdBadger B2B Ads Game Changer | https://www.adbadger.com/blog/why-amazon-b2b-ads-are-a-game-changer-for-sellers/ | B2B 广告位和指标 |
| 13 | Skale Strategy Amazon Ad Reports | https://www.skalestrategy.com/blog/amazon-advertising-reports-guide | 如何解读各类型广告报告 |
| 14 | FNDEcommerce Campaign Structure | https://fndecommerce.com/amazon-ppc-campaign-structure/ | 广告活动和广告组结构最佳实践 |
| 15 | Amazon Placement Report Help | https://advertising.amazon.ca/help/G89VFUTQUWFFN2VU | 官方广告位报告文档 |

### 项目内部来源

| # | 来源 | 内容 |
|---|------|------|
| 16 | `advertise/docs/reference/sp-report-column-reference.md` | 所有 8 种报告的完整字段定义 (66 列 × 8 类型) |
| 17 | `advertise/analyze_campaign.py` | 广告活动分析脚本 (206 行输入) |
| 18 | `advertise/analyze_targeting.py` | 投放分析脚本 (492 行输入) |
| 19 | `advertise/analyze_search_term.py` | 搜索词 5 桶分类脚本 (790 行输入) |
| 20 | `advertise/analyze_placement.py` | 广告位分析脚本 (457 行输入) |
| 21 | `advertise/build_report.py` | Excel 汇总报告生成器 |
| 22 | `advertise/__init__.py` | 数据加载和列名映射 |

---

## See also

- [SP 广告报告字段权威参考](../reference/sp-report-column-reference.md) -- 全部 8 种报告的列定义
- [列名映射参考](../reference/column-mappings.md) -- 中文到英文列名的完整映射
- [2026年6月广告分析研究报告](2026-06-16-amazon-advertising-analysis-research.md) -- 前一轮调研文档
