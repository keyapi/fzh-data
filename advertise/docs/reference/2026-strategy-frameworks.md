---
okf: v0.1
type: Reference
title: Amazon 广告策略框架 — 2026年6月
description: ACoS→TACoS演进、COSMO算法、Alexa for Shopping、归因模型、campaign架构、竞价策略、全漏斗方法
tags: [amazon, advertising, strategy, TACoS, COSMO, attribution, 2026]
timestamp: 2026-06-24
---

# Amazon 广告策略框架 (2026年6月)

## 1. ACoS → TACoS 转型

### TACoS 作为北极星指标

行业共识已从单一 ACoS 指标转向 TACoS (Total Advertising Cost of Sale) 作为衡量广告健康度的北极星指标。四大权威来源一致确认：[Adverio](https://www.adverio.io/amazon-agency-benchmark-report/)、[Mr. Prime](https://mrprime.com/blog/good-tacos-amazon-brand-benchmarks/)、[SalesDuo](https://salesduo.com/blog/amazon-advertising-benchmarks/)、[Helium 10](https://www.helium10.com/blog/how-to-allocate-advertising-budget-across-channels-in-2026/)。

核心逻辑：ACoS 只看广告花费与广告销售额的比例，而 TACoS 将广告花费与总销售额（自然+广告）挂钩，反映广告对自然排名的拉动效应。

### TACoS 基准对照表

| 年营收规模 | 目标 TACoS 区间 |
|---|---|
| $1-3M | 10-18% |
| $3-10M | 8-15% |
| $10-30M | 6-12% |
| $30M+ | 5-10% |

数据来源：[Mr. Prime TACoS Benchmarks](https://mrprime.com/blog/good-tacos-amazon-brand-benchmarks/)、[Adverio Agency Benchmark Report](https://www.adverio.io/amazon-agency-benchmark-report/)。

### 盈亏平衡 ACoS 公式（含 LTV）

传统公式：`Break-even ACoS = 毛利率`

引入 LTV 修正后：`Break-even ACoS = 毛利率 + (LTV增量 / 首单收入)`，来源：[Adverio](https://www.adverio.io/amazon-agency-benchmark-report/)。

这意味着对于高复购品类（如宠物食品、美妆），可承受的 ACoS 应显著高于毛利率。

### ACoS vs TACoS 诊断规则

| ACoS 变化 | TACoS 变化 | 诊断 | 行动 |
|---|---|---|---|
| ↑ 上升 | ↓ 下降 | 自然销售强势增长，广告被挤出 | 降低竞价，减少低效投放 |
| ↑ 上升 | ↑ 上升 | 广告过度依赖，自然排名未提升 | 审视关键词策略，检查 listing 质量 |
| ↓ 下降 | ↓ 下降 | 理想状态 | 扩大规模 |
| ↓ 下降 | ↑ 上升 | 广告收缩过度，自然销售下滑 | 重新加大广告投入 |

来源：[Mr. Prime](https://mrprime.com/blog/good-tacos-amazon-brand-benchmarks/)。

---

## 2. COSMO 算法与意图匹配

### 规模与架构

Amazon COSMO (Common Sense Knowledge Enhanced) 知识图谱已扩展至：
- **630 万个节点** — 产品、属性、使用场景等实体
- **2900 万条边** — 实体间关系
- **15 种关系类型** — 包括 "used for"、"compatible with"、"alternative to" 等
- **18 个品类** — 全品类覆盖

来源：[SellerApp COSMO Guide](https://www.sellerapp.com/blog/amazon-cosmo/)、[ZonGuru COSMO Guide](https://www.zonguru.com/blog/amazon-cosmo-guide/)。

### 个性化影响

超过 **60% 的搜索结果**已受 COSMO 个性化影响。同一搜索词，不同用户看到不同的结果排序。这意味着：
- 关键词排名不再有统一基准
- 基于"场景"和"意图簇"的优化取代关键词精确匹配
- Listing 内容需要使用 COSMO 可理解的语义语言

来源：[SellerApp](https://www.sellerapp.com/blog/amazon-cosmo/)。

### 实践建议

- 在标题和五点描述中使用 **场景驱动语言**（"for outdoor camping" 而非仅 "waterproof"）
- 在产品描述中注入 **关系信号**（兼容什么、替代什么、与什么搭配使用）
- 利用 A+ 内容构建 **意图簇**，而非孤立卖点

---

## 3. Alexa for Shopping（2026年5月上线，取代 Rufus）

### 关键数据

- **3 亿+ 用户基数**，覆盖 Echo 设备、Fire TV、Alexa 移动应用
- 预计 **$120 亿增量销售额**
- 预测到 **2026 年底 40% 的购买**通过 Alexa 语音/对话完成
- 对话式查询 **CPC 低 45%**（早期红利期）

来源：[Tinuiti Alexa for Shopping](https://tinuiti.com/blog/amazon/alexa-for-shopping/)、[Canopy Management Seller's Guide](https://canopymanagement.com/amazon-alexa-for-shopping-sellers-guide/)、[Autron PPC Implications](https://autron.ai/blog/amazon-replaces-rufus-with-alexa-for-shopping-what-the-ppc-implications-actually-are)。

### 对 PPC 的影响

- 传统关键词竞价的边际效用下降
- 对话式意图匹配成为新战场
- 需要在 listing 中注入"问题-回答"语义结构
- SB/SD 格式在语音场景中占据优势（品牌推荐优先）

---

## 4. 三桶 Campaign 架构

2026 年最佳实践已从传统 SKAG (Single Keyword Ad Group) 转向意图驱动的三桶架构。来源：[Autron Campaign Structure 2026](https://autron.ai/blog/amazon-ppc-campaign-structure-in-2026-why-fewer-campaigns-now-beat-more)、[ClearAds Agency Structure Fix](https://clearadsagency.com/your-amazon-ad-structure-is-starving-the-algorithm-heres-the-fix/)。

### 三桶模型

| 桶 | 预算占比 | 功能 | 关键指标 |
|---|---|---|---|
| **Discovery（发现）** | 15-25% | 自动投放 / 广泛匹配，探索新搜索词 | 新搜索词发现率 |
| **Harvest / Validation（收割/验证）** | 25-35% | 词组匹配，验证搜索意图相关性 | 点击率、转化率 |
| **Performance（绩效）** | 40-50% | 精确匹配 + ASIN 定向，高转化词 | ACoS、ROAS |

### 与传统架构的对比

- SKAG 依赖精确关键词分桶，与 COSMO 的语义匹配层不兼容
- 三桶架构与 COSMO 的意图簇对齐
- 每个 ASIN **至少需要 30 点击/周**才能积累足够算法信号（阈值）— [Autron](https://autron.ai/blog/amazon-ppc-campaign-structure-in-2026-why-fewer-campaigns-now-beat-more)
- 意图驱动重组可实现 **20-35% ACOS 降低** — [Autron](https://autron.ai/blog/amazon-ppc-campaign-structure-in-2026-why-fewer-campaigns-now-beat-more)

---

## 5. 基于 Persona 的产品组合策略

Wedbush / Amazon Growth Lab 推出 **Persona-Driven PPC Framework**，将消费者画像与广告策略直接挂钩。来源：[Wedbush Investor Article](https://investor.wedbush.com/wedbush/article/accwirecq-2025-11-5-how-top-amazon-brands-will-advertise-in-2026-amazon-growth-lab-launches-persona-driven-ppc-framework)。

### 五大消费者画像

- **Value Hunter（价值猎手）**：价格敏感，响应 coupon/折扣
- **Brand Loyalist（品牌忠诚者）**：复购驱动，响应 SB + 品牌旗舰店
- **Researcher（研究者）**：长决策周期，响应 A+ 内容 + 视频广告
- **Impulse Buyer（冲动买家）**：响应 SD + 强视觉创意
- **Need-Based Shopper（需求驱动者）**：响应精确匹配 + 场景化 listing

### 应用

每个 ASIN 根据其目标画像分配差异化的广告预算和创意策略，而非统配。

---

## 6. 2026 预算分配指南

### 广告类型分配

| 广告类型 | 预算占比 | 说明 |
|---|---|---|
| Sponsored Products (SP) | 60-70% | 仍为主体，但占比在下降 |
| Sponsored Brands (SB) | 15-25% | 品牌建设 + 视频格式增长 |
| Sponsored Display (SD) | 10-20% | 再营销 + 受众定位 |
| DSP | 0-10% | 程序化，大品牌专用 |

来源：[Canopy Management Budget Allocation](https://canopymanagement.com/amazon-advertising-budgets-how-to-allocate-spend-across-campaigns/)。

### 定向方式转变（2024 vs 2026）

| 定向方式 | 2024 占比 | 2026 占比 | 趋势 |
|---|---|---|---|
| Keyword 关键词 | 60% | 30% | ↓ 大幅下降 |
| ASIN 商品定向 | 15% | 40% | ↑ 成为主力 |
| SD 受众定向 | 10% | 30% | ↑ 增长最快 |

来源：[Canopy Management](https://canopymanagement.com/amazon-advertising-budgets-how-to-allocate-spend-across-campaigns/)。

---

## 7. 竞价策略

### 自动化 vs 手动对照表

| 任务 | 自动化 | 手动 | 建议 |
|---|---|---|---|
| 竞价调整 | ✅ AI bidding | ✅ 战略判断 | 80% AI + 20% 手动 [Eva.guru](https://eva.guru/blog/amazon-ai-bidding-strategies/) |
| 关键词发现 | ✅ 自动投放 | ❌ | 完全自动化 |
| 否定关键词 | ⚠️ 辅助 | ✅ 主导 | 手动审查 AI 建议 |
| 预算分配 | ⚠️ 辅助 | ✅ 主导 | 基于 TACoS 数据手动决策 |
| 创意测试 | ✅ AI 生成 | ✅ 策略方向 | 人机协作 |

来源：[SellerSprite PPC Guide 2026](https://m.sellersprite.com/en/blog/amazon-ppc-guide-2026-AI-automation)、[Eva.guru AI Bidding](https://eva.guru/blog/amazon-ai-bidding-strategies/)。

### AI 竞价护栏

- 硬性 ACoS 上限：每个 campaign 类型设置不可逾越的 ACoS 天花板
- 20% 手动基线：保留部分手动投放以发现 AI 盲区
- 重要发现：动态竞价在强化学习下可能**激励平台涨价**— 来源：[Marketing Science Journal (2026)](https://econpapers.repec.org/article/inmormksc/v_3a45_3ay_3a2026_3ai_3a3_3ap_3a576-595.htm)

---

## 8. 归因模型变更（2026年1月生效）

### 关键变化

- **View-through 归因窗口收窄**：DSP 展示归因更加保守
- **MTA (Multi-Touch Attribution) Beta 上线**：告别最后点击归因
- 影响：DSP 报告效果可能"看起来"下降 15-25%，实际价值未变

来源：[CODE3 Attribution Changes](https://code3.com/resources/amazon-quietly-tightened-attribution-and-its-changing-how-dsp-performance-is-measured/)、[SellerMetrics MTA](https://sellermetrics.app/amazon-multi-touch-attribution/)。

### 应对

- 不要因归因变更而削减 DSP 预算（DSP 的实际增量价值可能被低估）
- 关注 MTA Beta 中"辅助转化"指标
- 交叉验证：广告报告 vs 业务报告中的自然销售趋势

---

## 9. 全漏斗方法 (Full-Funnel)

### 四层漏斗与广告格式

| 漏斗层级 | 目标 | 推荐格式 | 优化指标 |
|---|---|---|---|
| **认知 (Awareness)** | 触达新受众 | SB Video, DSP OTT, STV | Impressions, Reach |
| **考虑 (Consideration)** | 引导浏览 | SB, SD 内容定向 | CTR, Detail Page Views |
| **转化 (Conversion)** | 促成购买 | SP 精准, SD 再营销 | CVR, ACoS |
| **忠诚 (Loyalty)** | 复购/交叉销售 | SB 品牌旗舰店, SD 受众 | 复购率, LTV |

来源：[Feedvisor Full-Funnel Guide](https://feedvisor.com/resources/amazon-marketing-advertising-strategies/sponsored-brands-guide/)。

---

## 10. Dayparting（分时投放）

### 效果评估

[Velocity Sellers Dayparting 2026](https://www.velocitysellers.com/2026/05/13/amazon-dayparting-ad-scheduling-2026/) 调查报告：

- **25% 的卖家**使用分时投放并获得正收益（通常为高客单价/长决策周期品类）
- **75% 的卖家**使用分时投放但效果不显著（"剧场效应"——在固定时段竞争加剧抵消了分时优势）
- 有效场景：B2B 商品（工作日白天）、高客单价（晚间研究型流量）
- 无效场景：日用品/低客单价（全天均匀需求）

---

## 11. 各品类 ACoS 基准

| 品类 | 目标 ACoS 区间 | 平均 CPC |
|---|---|---|
| Electronics 电子 | 30-45% | $1.20-2.50 |
| Health & Household 健康家居 | 25-40% | $0.80-1.80 |
| Home & Kitchen 家居厨房 | 20-35% | $0.60-1.50 |
| Beauty & Personal Care 美妆 | 20-30% | $0.70-1.60 |
| Grocery 食品 | 15-25% | $0.40-1.00 |
| Clothing & Accessories 服饰 | 25-40% | $0.50-1.40 |
| Toys & Games 玩具 | 15-25% | $0.50-1.30 |
| Pet Supplies 宠物用品 | 20-30% | $0.70-1.50 |

来源：[SalesDuo Advertising Benchmarks](https://salesduo.com/blog/amazon-advertising-benchmarks/)。

---

## 12. 反方观点：当前赛狐系统的实践解剖

当前赛狐广告管理系统的架构局限：

### ACoS-Only 模式
系统以 ACoS 作为唯一优化指标，未纳入 TACoS 视角。短期优化可能导致自然排名受损，但无法从现有报表中识别。

### SKAG 与 COSMO 不兼容
当前 Keyword → 精准匹配 → 单一 ASIN 的架构与 COSMO 语义匹配层存在根本性冲突。COSMO 按意图簇（产品+场景+画像）组织结果，而非按孤立关键词。

### 缺失 NTB% (New-to-Brand)
无法区分新客获取与老客复购的广告效率，导致预算不成比例地流向老客——这在表现上与 MTA 的"辅助转化"视角一致。

### ASIN 定向未被充分利用
当前 2026 年行业 ASIN 定向占比应达 40%，但赛狐系统中该能力尚未启用，限制了竞争性防御和收割能力。

---

## See also

- [2026 Market Intelligence](./2026-market-intelligence.md) — 市场规模、竞争格局、隐私合规
- [Verified Sources](./verified-sources.md) — 所有引用源的 WebFetch 验证记录
