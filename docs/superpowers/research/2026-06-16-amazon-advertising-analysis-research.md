# Amazon 广告数据分析 — 调研报告

> 日期：2026-06-16 (更新 2026-06-17) | 分支：amazon_advertise | 版本: v0.3
>
> 关联设计文档: `specs/2026-06-16-amazon-advertise-analysis-design.md`
> 
> **2026-06-17 增量**: 补充 6 维度专家级深度调研（通用数据分析方法论 / Amazon 专家策略 / 数据生态 / 行业趋势 / 工具 / 系统架构）

## 调研目标

为 `advertise/` 模块设计提供行业标准依据。调研范围：
1. Amazon Sponsored Products 4 份报告的数据格式和字段定义
2. 搜索词报告分析的正确方法论（聚合/分类/阈值）
3. 广告位报告的结构和使用方式
4. 行业最佳实践（2026 年最新）

## 数据源文件格式调研

### 4 份报告的字段结构

通过实际数据反查 + Amazon 官方文档对照，确认了以下字段映射：

**广告活动报告** (CSV, 25 列): 开始日期, 结束日期, 广告组合名称, 广告活动类型, 广告活动名称, 状态, 货币, 预算, 定位类型, 竞价策略, 展示量, 点击量, CTR, 花费, CPC, 7天订单, ACOS, ROAS, 7天销售额

**投放报告** (XLSX, 26 列): 上述共同字段 + 投放, 匹配类型, 顶部搜索份额, 转化率, 广告SKU vs 其他SKU 销售/销量分离

**搜索词报告** (XLSX, 26 列): 上述共同字段 + 客户搜索词, 投放, 匹配类型

**广告位报告** (XLSX, 18 列): 上述共同字段 + 放置(4个值: 站内搜索结果顶部/站内商品页面/站内搜索其余位置/站外)

### 关键发现

1. **CSV 金额列带 `$` 前缀** — 广告活动 CSV 是文本格式，spend/sales/budget/cpc 均为 `"$17.78"` 格式字符串
2. **同一搜索词出现多行** — 搜索词报告按 (search_term, campaign, ad_group, targeting, match_type) 粒度拆分，同一搜索词可分散在多个活动的多行
3. **SP 7 天点击归因** — 点击后 7 天内的订单计入 `orders_7d`，报告末尾 3-4 天归因不完整
4. **数据保留 60 天** — Amazon 仅保留最近约 60 天的搜索词数据

## 搜索词分析方法论调研

### 聚合要求（Trellis/WisePPC/SellerSprite 一致）

所有权威来源一致要求：**先按 Customer Search Term 聚合，再分类**。

- Trellis: "Pivot by customer search term so each query has one consolidated row of clicks, spend, orders, and sales."
- 聚合维度: SUM(spend), SUM(clicks), SUM(orders), SUM(sales), SUM(impressions)
- 聚合后计算: 统一 ACOS = 总花费/总销售额, 统一 CPC = 总花费/总点击

### 5 桶分类体系（Trellis 标准）

| 桶 | 阈值 | 操作 |
|----|------|------|
| Harvest | 2-3+ 订单 AND ACOS ≤ 目标 | 加入精准匹配 + 源活动否定 |
| Negate | 15-20+ 点击 AND 0 订单 | 精准否定(特定词) 或 词组否定(整类) |
| Monitor | < 15 点击 | 数据不足，下周期复查 |
| Protect | 品牌/战略词 | 保持投放 |
| Ignore | 花费可忽略 | 不做操作 |

### 阈值依据

- Harvest 最小 2-3 订单: "1 order is a coincidence, not a signal" (Trellis)
- Negate 最小 15 点击: "Negating under 15 clicks is usually premature — a term with 8 clicks and no orders is a small sample, not a verdict" (Trellis/WisePPC)
- 周优化 > 月优化: "A wasted-spend term can burn its budget for four weeks before you catch it on a monthly cadence"

### 否定词类型限制（中文官方）

SP 广告**只有词组否定和精准否定两种**，没有广泛否定。这个来自跨境魔方的明确确认。

## 广告位分析调研

### 广告位 4 个值（实际数据确认）

通过读取实际中文后台导出文件，确认广告位列有 4 个精确值：
- 亚马逊站内的搜索结果顶部 → Top of Search
- 亚马逊站内的商品页面 → Product Pages
- 亚马逊站内搜索结果的其余位置 → Rest of Search
- 亚马逊站外 → 站外

### 广告位效率特征（SalesDuo/SellerSprite）

- Top of Search: 高 CVR 但高 CPC, 适合高利润产品
- Product Pages: CVR 常为 Top of Search 的 2x, 且 CPC 更低 — 许多卖家低估了这个位置
- Rest of Search: 通常表现最差

## 资料来源

### 英文权威（16 篇，全部 2026 年）

1. [Amazon Ads API v3 Report Types](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview) — 官方报告类型和字段定义
2. [Amazon SP Placement Report Help](https://advertising.amazon.ca/help/G89VFUTQUWFFN2VU) — 官方广告位报告帮助
3. [Amazon Advertising Budgets 2026 - Canopy Management](https://canopymanagement.com/amazon-advertising-budgets-how-to-allocate-spend-across-campaigns/)
4. [Sponsored Products Ad Guide - Feedvisor](https://feedvisor.com/resources/amazon-marketing-advertising-strategies/sponsored-products-ad-guide/)
5. [AMS Ads: Master Amazon Advertising in 2026 - Automateed](https://www.automateed.com/ams-ads)
6. [Amazon Bid Management Playbook 2026 - SalesDuo](https://salesduo.com/blog/amazon-bid-management/)
7. [Amazon PPC Optimization Playbook 2026 - SellerSprite](https://sellersprite.co/en/blog/Amazon-PPC-Optimization-Playbook)
8. [Placement Adjustments: Top of Search vs Product Pages - SellerSprite](https://sellersprite.co/en/blog/Placement-Adjustments-Top-of-Search-Product-Pages)
9. [Amazon Ads Strategy That Actually Scales - YourEcomTeam](https://yourecomteam.co/blog/amazon-ads-strategy-that-actually-scales)
10. [Amazon Ads Analytics - Coupler.io](https://blog.coupler.io/amazon-ads-analytics/)
11. [Amazon PPC Campaign Structure 2026 - IMH](https://influencermarketinghub.com/amazon-influencer-marketing/amazon-ppc-campaign-structure/)
12. [Amazon PPC Guide 2026 - SellerSprite](https://www.sellersprite.ai/en/blog/amazon-ppc-guide-2026)
13. [Amazon PPC Strategy 2026 - AMZScout/EHP](https://amzscout.net/blog/amazon-ppc-strategy-ehpconsulting/)
14. [Amazon PPC Fundamentals 2026 - SellerSprite](https://www.sellersprite.com/en/blog/Amazon-PPC-Fundamentals-A-Beginner-Friendly-Course-Guide-(2026))
15. [Amazon PPC Bidding Strategies - SellerSprite](https://m.sellersprite.com/en/blog/Amazon-PPC-Bidding-Strategies-Dynamic-vs-Fixed)
16. [Amazon PPC Strategy Guide 2026 - SalesDuo](https://salesduo.com/blog/create-an-amazon-ppc-strategy/)

### 英文搜索词专题

17. [Search Term Report Optimization Guide 2026 - WisePPC EN](https://wiseppc.com/blog/search-term-report-optimization/)
18. [Amazon Search Term Report Workflow - Trellis](https://gotrellis.com/resources/blog/amazon-search-term-report-workflow/)
19. [Search Terms Report: Your Best Ad Data - Vappingo](https://www.vappingo.com/word-blog/search-terms-report-amazon-ads/)
20. [Search Term Report Mastery - Seller Labs](https://www.sellerlabs.com/knowledge-base/search-term-report-mastery-find-your-best-keywords/)
21. [Amazon Ads Reporting Complete Guide - SalesDuo](https://salesduo.com/blog/amazon-ads-reporting/)
22. [Amazon PPC Search Terms Guide - SellerSprite](https://www.sellersprite.com/en/blog/amazon-ppc-search-terms-guide)
23. [Amazon Advertising Reports: Complete 2025 Guide - MyAmazonGuy](https://myamazonguy.com/advertising/amazon-advertising-reports/)
24. [Amazon SP Targeting Report - Mimbi](https://www.mimbi.io/reports/amazon-sponsored-products-targeting)
25. [Amazon SP Search Term Report - Mimbi](https://www.mimbi.io/reports/amazon-sponsored-products-search-term)

### 中文权威（10 篇，全部 2026 年）

26. [搜索词报告优化指南 2026 - WisePPC CN](https://wiseppc.com/zh/blog/search-term-report-optimization/)
27. [亚马逊PPC广告诊断与ACOS优化 - CoGoLinks](https://www.cogolinks.com/news-center/b2c/26874)
28. [否定广告的完整逻辑与实操SOP - 跨境魔方](https://www.upkuajing.com/knowledge/zixun/25823)
29. [围剿高ACoS！重塑亚马逊广告盈亏认知 - 卖家精灵](https://mjzj.com/article/fbhi4l7ex1j4)
30. [亚马逊广告分析，ACoS投入产出核算 - CoGoLinks](https://www.cogolinks.com/news-center/b2c/31389)
31. [3个报告+1个工具锁定高转化词 - 卖家精灵](https://mjzj.com/article/fm421wzlr18g)
32. [2026亚马逊广告投放完全指南 - mall520](https://mall520.com/814.html)
33. [2026最全实战：意图为王打法体系 - 卖家精灵](https://mjzj.com/article/fp6ep7gtktmo)
34. [亚马逊SP广告新品推广三阶段策略 - 跨境知道](https://www.ikjzd.com/articles/1810625995697092276)
35. [商品推广报告解读 - 星火社](https://xinghuos.com/3020.html)

## 与现有项目规范的对照

| 规范要求 | 本模块状态 |
|---------|-----------|
| `docs/superpowers/research/` 调研报告 | ✅ 本文件 |
| `docs/superpowers/specs/` 设计文档 | ✅ `2026-06-16-amazon-advertise-analysis-design.md` |
| `docs/superpowers/plans/` 实现计划 | ❌ 计划在 `.claude/plans/` (非项目共享) |
| 模块 `AGENT_HANDOFF.md` | ✅ `advertise/AGENT_HANDOFF.md` |
| 模块 `README.md` | ✅ `advertise/README.md` |
