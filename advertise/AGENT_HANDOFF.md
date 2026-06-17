# AGENT_HANDOFF.md — Amazon 广告数据分析模块

> 本文件供接手此模块的 Agent 参考。包含完整列名映射、分析框架来源、架构决策和经验教训。
>
> **最后更新**: 2026-06-17 | **版本**: v0.3 (专家调研版) | **分支**: amazon_advertise | **PR**: [#14](https://github.com/keyapi/fzh-data/pull/14)

## 模块定位

从 Amazon 广告后台导出的 Sponsored Products 报告（4 份）→ 全维度 Excel 分析报告。分析维度对齐 2026 年业界最佳实践。

## 阶段性目标与完成情况

### Phase 1: 基础分析框架 ✅ (v0.1)

| 目标 | 状态 | 说明 |
|------|------|------|
| 数据加载 + 列名映射 | ✅ | `__init__.py`: 4 份报告中文→英文标准化, CSV $ 符号清洗 |
| 广告活动分析 | ✅ | `analyze_campaign.py`: ACOS/ROAS排行, 预算利用率, Portfolio聚合 |
| 投放分析 | ✅ | `analyze_targeting.py`: 匹配类型对比, 光环效应, 零转化投放 |
| 搜索词分析 (逐行版) | ✅ → ❌ | v0.1 逐行判断有缺陷, v0.2 重写 |
| 广告位分析 | ✅ | `analyze_placement.py`: Top of Search/Product Pages/Rest/站外 四位对比 |
| Excel 报告生成 | ✅ | `build_report.py`: 6 sheet + openpyxl 图表 |
| 知识沉淀 | ✅ | `AGENT_HANDOFF.md`: 26 个资料来源 URL |

### Phase 2: 搜索词修复 + 5 桶体系 ✅ (v0.2)

| 目标 | 状态 | 说明 |
|------|------|------|
| 搜索词聚合 | ✅ | 先 GROUP BY search_term, 再分类 (修复 Lesson 6) |
| 5 桶分类体系 | ✅ | Harvest/Negate/Monitor/Protect/Ignore (修复 Lesson 7) |
| 阈值对齐行业标准 | ✅ | Harvest≥2单, Negate≥15点击, Monitor<15点击 |
| 归因窗口检查 | ✅ | 报告期<14天自动警告 (修复 Lesson 8) |
| 错误用例验证 | ✅ | `bed wedge pillow for headboard`: 误判否定词 → 正确入 Monitor |
| Excel 报告更新 | ✅ | 搜索词 sheet 重写, 新增 Monitor 观察列表 |

### Phase 3: 后续规划 (未开始)

| 目标 | 优先级 | 依赖 |
|------|--------|------|
| 决策日志持久化 | 高 | 追加式 JSON, 不覆盖上次结果 |
| 多期对比 (环比/同比) | 中 | 需要多期数据积累 |
| Web Dashboard | 中 | FastAPI + Chart.js |
| 盈亏建模 (接入 EN BOM 成本) | 中 | 需要成本数据 |
| SB/SD 报告支持 | 低 | 需要 Sponsored Brands/Display 报告导出 |
| 自动化周报 (CronJob) | 低 | 定时导出 + 邮件发送 |

## 当前报告核心发现 (2026-05-17 ~ 2026-06-15)

| 维度 | 关键数字 |
|------|---------|
| 30 天总花费 | $3,483 |
| 30 天销售额 (7d归因) | $11,513 |
| 整体 ACOS | 30.25% |
| 整体 ROAS | 3.31x |
| 独立搜索词 | 3,696 个 |
| Harvest 收割词 | 10 个 ($168 花费 → $2,238 销售, 13.3x ROAS) |
| Negate 否定词候选 | 32 个 (节省 $498) |
| Monitor 观察 | 504 个 ($1,266 待观察) |
| Top of Search | ACOS 17.34% — 最优广告位 |
| Product Pages | ACOS 39.50% — 花费最多但效率偏低 |
| 光环效应 | 广告SKU $2,413 + 其他SKU $9,100 = 3.77x |

## 数据源

4 份报告均在 Amazon 广告后台同一路径导出（广告活动管理 → 报告 → 创建报告）：

| 文件 | 行数 | 报告类型 |
|------|------|---------|
| `商品推广_广告活动_报告.csv` | ~37 | 广告活动级 |
| `商品推广_投放_报告-30.xlsx` | ~180 | 投放/关键词级 |
| `商品推广_搜索词_报告-30.xlsx` | ~5,000 | 客户搜索词级 |
| `商品推广_广告位_报告-30.xlsx` | ~126 | 广告位级 |

> 文件名需包含关键字 `广告活动` / `投放` / `搜索词` / `广告位`，`__init__.py` 自动识别。

## 专家级分析评估 (v0.3 深度调研)

> 2026-06-17 执行了 6 维度 × 35+ 来源的深度调研。
> 完整调研报告: `docs/superpowers/research/2026-06-16-amazon-advertising-analysis-research.md`

### 当前方法的 7 个层次缺陷

对照 CRISP-DM 专家级数据分析和 Amazon 广告行业最佳实践，当前 v0.2 存在以下不足：

| # | 缺陷 | 专家标准 | 影响 |
|---|------|---------|------|
| 1 | **缺少 Business Understanding 阶段** | CRISP-DM 要求 15% 时间在此阶段：定义成功标准、利益相关者、业务目标→分析问题翻译 | 分析了数据但不知道"盈亏平衡点"在哪 |
| 2 | **无环比/同比** | 任何数据分析必须有时序对比。无历史数据 = 不知道 30% ACoS 是改善了还是恶化了 | 无法判断趋势 |
| 3 | **无行业基准** | 需要同比类目平均水平、竞品水平。Eightx 2026 数据: 家居类目平均 ACoS 32.5% | 30% ACoS 是"好"还是"一般"？无参照物 |
| 4 | **数据源严重不全** | Amazon SP 共 13 种报告，我们只有 4 种。缺少: Purchased Product (光环效应), Search Term Impression Share (份额), Budget (预算利用率), Performance Over Time (趋势) | 大量分析维度缺失 |
| 5 | **无竞争情报** | 专家必须对比竞品。工具：SellerSprite 反向 ASIN 查竞品关键词, ABA Search Query Performance | 不知道竞品在投什么词、出什么价 |
| 6 | **ACoS 单一指标** | 专家看 TACoS (广告花费/总营收), NTB% (新客占比), LTV, 增量贡献。ACoS 只是战术指标 | 可能误判盈亏（低 ACoS 但蚕食了自然流量） |
| 7 | **无归因模型** | 7天点击归因有严重局限。AMC 提供多触点归因、增量测试、路径分析 | 无法区分广告驱动 vs 自然转化 |

### 我们缺失的 9 种 SP 报告

| 报告 | 用途 | 优先级 |
|------|------|--------|
| **Purchased Product** | 光环效应：点击广告后买了哪些非广告商品 | 🔴 高 |
| **Search Term Impression Share** | 搜索词展示份额 vs 竞品 | 🔴 高 |
| **Budget** | 预算利用率 + 建议预算 | 🟡 中 |
| **Performance Over Time** | 按日/周趋势（环比/同比基础） | 🔴 高 |
| **Advertised Product** | 按 ASIN/SKU 表现 | 🟡 中 |
| **Gross and Invalid Traffic** | 无效点击/展示监控 | 🟢 低 |
| **Purchased Product (SB)** | Sponsored Brands 光环效应 | 🟢 低 |
| **Audience** | 受众定向表现 | 🟢 低 |
| **Video** | 视频广告效果 | 🟢 低 |

### 专家级分析的数据需求清单

一个完整的 Amazon 广告分析系统需要以下数据：

**第一方数据（Amazon 后台可导出）:**
- [ ] 全部 13 种 SP 报告（当前只有 4 种）
- [ ] Brand Analytics: Search Query Performance（品牌注册后可获取）
- [ ] Brand Analytics: Demographics（客户画像：年龄/收入/教育）
- [ ] Brand Analytics: Market Basket Analysis（连带购买）
- [ ] Brand Analytics: Repeat Purchase Behavior（复购率）
- [ ] Seller Central Business Reports（自然流量/转化率）
- [ ] Amazon Marketing Cloud（如果预算允许，解锁多触点归因+LTV）

**第二方数据（第三方工具获取）:**
- [ ] 竞品关键词（SellerSprite 反向 ASIN → 竞品在投什么词/出价）
- [ ] 类目基准（类目平均 CPC/ACoS/转化率）
- [ ] 价格历史（Keepa 价格 + BSR 趋势）

**外部数据:**
- [ ] 节假日日历（Prime Day, BFCM, 返校季等）
- [ ] 汇率（多站点）

### 2026 年行业巨变

1. **Rufus 已退役** (2026.5.13) → **Alexa for Shopping** 嵌入搜索栏。COSMO 知识图谱（15+ 关系类型）替换关键词匹配
2. **搜索个性化 60%+**: 搜索结果因人而异（Buyer Persona 功能）
3. **Sponsored Prompts** (全新广告形式): Alexa for Shopping 内的对话式广告，语义质量分×出价
4. **CPC 通胀不可逆**: 平台平均 CPC $1.18-1.34 (+34% vs 两年前), 80% 品牌报告 CPC 上涨
5. **关键词→人**: 投放预算从关键词 60% 降至 30%，商品/ASIN 定向升至 40%
6. **AMC 自服务化** (2025.9): 无需代理商，广告主可直接在 Ads Console 访问 AMC
7. **Conversion Path Reporting** (2025.11): 30 天多触点转化路径，跨 SP/SB/SD/DSP/STV
8. **归因窗口缩短** (2026.1.1): 展示归因从固定 14 天改为算法过滤的短窗口

### 工具选型建议

| 场景 | 推荐工具 | 月费 |
|------|---------|------|
| 关键词研究 + 竞品分析 | SellerSprite API | $19-49 |
| PPC 规则自动化 | Scale Insights (透明, 按 ASIN 收费) | $78-688 |
| AI 全自动优化 | Perpetua (中等预算) / Pacvue (企业) | $250-500+ |
| 数据分析管道 | Amazon Ads API (免费) + Coupler.io ETL | API 免费 + ETL $24+ |
| 利润分析 (TACoS, 真实 P&L) | Sellerboard / Helium 10 Profits | $19-79 |
| 数据仓库 | AMC (AWS Clean Room) | 基础版包含在广告花费中 |

### 专家系统路线图

```
Phase 1 (已完成 v0.2): 基础 4 维分析 + Excel 报告
Phase 2 (当前): 补齐数据源 + 竞争情报 + 时序对比
Phase 3: 接入 Amazon Ads API 自动化数据拉取
Phase 4: 接入 SellerSprite API 竞品数据
Phase 5: 规则引擎自动化（否定词/收割/出价建议 → API 执行）
Phase 6: ML 辅助（异常检测/出价优化/NLP 搜索词分类）
Phase 7: 闭环反馈（分析 → 建议 → 执行 → 评估 → 优化）
```

### 立即可以做的事情

1. **问用户**: 盈亏平衡 ACoS 是多少？（产品毛利率）
2. **问用户**: 有没有上个月的数据？（环比对比）
3. **问用户**: 是否有 Brand Registry？（可获取 ABA 数据）
4. **问用户**: 是否开通了 SellerSprite？（可获取竞品关键词数据）
5. **导出补充报告**: Purchased Product + Search Term Impression Share + Performance Over Time
6. **对接 SellerSprite API**: `sellersprite.ai/en/blog/SellerSprite-Data-Service`

## 列名映射

Amazon 中文后台导出 → 英文标准字段名（`__init__.py` 中定义）。

### 广告活动报告

| 中文 | 英文 | 说明 |
|------|------|------|
| 开始日期 | start_date | |
| 结束日期 | end_date | |
| 广告组合名称 | portfolio_name | Portfolio 分组 |
| 广告活动类型 | campaign_type | 商品推广 |
| 广告活动名称 | campaign_name | |
| 零售商 | retailer | Amazon |
| 国家/地区 | country | |
| 状态 | status | ENABLED/PAUSED |
| 货币 | currency | USD |
| 预算 | budget | 日预算，带 `$` 前缀 |
| 定位类型 | targeting_type | 自动投放/手动投放 |
| 竞价策略 | bidding_strategy | 固定/动态 |
| 展示量 | impressions | |
| 点击量 | clicks | |
| 点击率 (CTR) | ctr | |
| 花费 | spend | 带 `$` 前缀，需清洗 |
| 单次点击成本 (CPC) | cpc | |
| 7天总订单数(#) | orders_7d | |
| 广告投入产出比 (ACOS) 总计 | acos | |
| 总广告投资回报率 (ROAS) | roas | |
| 7天总销售额 | sales_7d | 带 `$` 前缀 |

### 投放报告 & 搜索词报告（共同字段）

| 中文 | 英文 | 专属于 |
|------|------|--------|
| 投放 | targeting | 投放关键词/商品 ASIN |
| 匹配类型 | match_type | Broad/Phrase/Exact |
| 客户搜索词 | search_term | 仅搜索词报告 |
| 广告组名称 | ad_group_name | |
| 搜索结果首页首位展示量份额 | top_search_is | 仅投放报告 |
| 7天的转化率 | conversion_rate_7d | |
| 7天内广告SKU销售量(#) | advertised_sku_units_7d | |
| 7天内其他SKU销售量(#) | other_sku_units_7d | |
| 7天内广告SKU销售额 | advertised_sku_sales_7d | |
| 7天内其他SKU销售额 | other_sku_sales_7d | |

### 广告位报告

| 中文 | 英文 | 分类 |
|------|------|------|
| 放置 | placement | |
| 亚马逊站内的搜索结果顶部 | → | Top of Search |
| 亚马逊站内的商品页面 | → | Product Pages |
| 亚马逊站内搜索结果的其余位置 | → | Rest of Search |
| 亚马逊站外 | → | 站外 |

### 注意事项

1. **CSV 金额列带 `$` 前缀** — `__init__.py` 中做了 `str.replace(r"[$,\s]", "")` 清洗
2. **百分比列可能以整数形式返回**（如 30 = 30%）— 自动除以 100
3. **去重列名** — 广告活动报告中 去年曝光量/去重点击量 等列映射为 `impressions_dedup` / `clicks_dedup` / `spend_dedup` / `cpc_dedup`

## 分析框架

以下框架来自 2026 年业界资料的综合总结。

### 关键词收割三步法

```
1. 自动/广泛匹配广告「探矿」收集搜索词数据（14-21天）
2. 搜索词报告分析「找矿」：分离高转化词（订单≥3, ACOS<目标）
3. 精准匹配「收割」：高转化词移入 Exact Match 活动 → 原数据源否定该词防止重叠
```

### 否定词 SOP

满足任一条件即添加否定关键词：
- 点击 ≥ 15-30 次，0 订单 → 精准否定
- ACOS 远超目标 3 倍以上 → 否定
- 属性/人群/用途完全不匹配 → 词组否定
- 竞品品牌词/仿品词 → 精准否定
- 垃圾意向词(cheap/free/used/wholesale) → 词组否定

**SP 广告只有词组否定和精准否定两种，没有广泛否定。**

### 300 分钟周优化流程

| 日 | 动作 | 耗时 |
|----|------|------|
| 周一 | 下载搜索词+广告位报告，识别低效投放 | 15-20min |
| 周三 | 挖掘自动广告搜索词，收割好词，加否定词 | 15-20min |
| 周五 | 基于 2 周+数据调整出价，重新平衡预算 | 15-20min |

> 不要每天优化——基于 24-48h 数据移动预算会产生鞭梢效应。每周最优。

### ACOS 基准（2026）

| 阶段 | 目标 ACOS | 策略 |
|------|----------|------|
| 新品期 (0-60天) | 30-60% | 激进冲排名 |
| 成长期 (3-12月) | 20-35% | 平衡增长与盈利 |
| 成熟期 (12月+) | 10-25% | 防守为主 |

## 完整资料来源

### 英文资料（2026）

1. [Amazon Advertising Budgets 2026 - Canopy Management](https://canopymanagement.com/amazon-advertising-budgets-how-to-allocate-spend-across-campaigns/)
2. [Sponsored Products Ad Guide - Feedvisor](https://feedvisor.com/resources/amazon-marketing-advertising-strategies/sponsored-products-ad-guide/)
3. [AMS Ads: Master Amazon Advertising in 2026 - Automateed](https://www.automateed.com/ams-ads)
4. [Amazon Bid Management Playbook 2026 - SalesDuo](https://salesduo.com/blog/amazon-bid-management/)
5. [Amazon PPC Optimization Playbook 2026 - SellerSprite](https://sellersprite.co/en/blog/Amazon-PPC-Optimization-Playbook)
6. [Placement Adjustments: Top of Search vs Product Pages - SellerSprite](https://sellersprite.co/en/blog/Placement-Adjustments-Top-of-Search-Product-Pages)
7. [Amazon Ads Strategy That Actually Scales - YourEcomTeam](https://yourecomteam.co/blog/amazon-ads-strategy-that-actually-scales)
8. [Amazon Ads Analytics: Make Your Data Actually Work - Coupler.io](https://blog.coupler.io/amazon-ads-analytics/)
9. [Amazon PPC Campaign Structure 2026: Personas Over Keywords - IMH](https://influencermarketinghub.com/amazon-influencer-marketing/amazon-ppc-campaign-structure/)
10. [Amazon PPC Guide 2026 - SellerSprite](https://www.sellersprite.ai/en/blog/amazon-ppc-guide-2026)
11. [Amazon PPC Strategy 2026 - AMZScout/EHP](https://amzscout.net/blog/amazon-ppc-strategy-ehpconsulting/)
12. [Amazon PPC Fundamentals 2026 - SellerSprite](https://www.sellersprite.com/en/blog/Amazon-PPC-Fundamentals-A-Beginner-Friendly-Course-Guide-(2026))
13. [Amazon PPC Bidding Strategies: Dynamic vs Fixed - SellerSprite](https://m.sellersprite.com/en/blog/Amazon-PPC-Bidding-Strategies-Dynamic-vs-Fixed)
14. [Amazon PPC Strategy: Complete Step-by-Step Guide 2026 - SalesDuo](https://salesduo.com/blog/create-an-amazon-ppc-strategy/)
15. [Search Term Report Optimization Guide (2026) - WisePPC EN](https://wiseppc.com/blog/search-term-report-optimization/)
16. [Amazon PPC Search Terms Guide - SellerSprite](https://www.sellersprite.com/en/blog/amazon-ppc-search-terms-guide)

### 中文资料（2026）

17. [亚马逊PPC广告诊断与ACOS优化 - CoGoLinks](https://www.cogolinks.com/news-center/b2c/26874)
18. [亚马逊广告"避坑"指南：否定广告的完整逻辑 - 跨境魔方](https://www.upkuajing.com/knowledge/zixun/25823)
19. [搜索词报告优化指南 (2026) - WisePPC CN](https://wiseppc.com/zh/blog/search-term-report-optimization/)
20. [围剿高ACoS！重塑亚马逊广告盈亏认知 - 卖家精灵](https://mjzj.com/article/fbhi4l7ex1j4)
21. [亚马逊广告分析，ACoS投入产出核算 - CoGoLinks](https://www.cogolinks.com/news-center/b2c/31389)
22. [3个报告+1个工具锁定高转化词 - 卖家精灵](https://mjzj.com/article/fm421wzlr18g)
23. [2026亚马逊广告投放完全指南 - mall520](https://mall520.com/814.html)
24. [2026最全实战：意图为王打法体系 - 卖家精灵](https://mjzj.com/article/fp6ep7gtktmo)
25. [亚马逊SP广告新品推广三阶段策略 - 跨境知道](https://www.ikjzd.com/articles/1810625995697092276)
26. [商品推广报告解读 - 星火社](https://xinghuos.com/3020.html)

## 架构决策

### 为什么是模块化而不是单脚本？

1. **独立可跑** — 每个分析脚本可单独调试和运行，不需要全跑一遍
2. **对齐项目模式** — stock_init / item_cost_sx 等模块同样是多脚本 + 数据源 + out 结构
3. **Web 扩展路径** — 中间 JSON 可直接被 Web 层消费，无需重新计算
4. **Agent 友好** — 每个文件 < 200 行，Agent 可以在上下文窗口内完全理解

### 为什么阈值是可配置常量而非命令行参数？

- 命令行参数增加调用复杂度
- 阈值通常不需要频繁改动
- 修改脚本顶部常量比传参更直观

### 为什么列名用中文精确匹配而非模糊？

- Amazon 中文后台列名可能随版本变化，精确匹配能及时发现变更
- 模糊匹配可能误命中其他列

## 经验教训

### Lesson 1: CSV 金额列格式

**问题**：广告活动 CSV 的 spend/sales/budget/cpc 列值是 `$17.78` 格式的字符串，直接 `pd.to_numeric` 全变 NaN。
**解决**：在 `__init__.py` 加载时先 `str.replace(r"[$,\s]", "", regex=True)` 清洗再转换。
**适用**：所有 Amazon 中文后台导出的 CSV 报告。

### Lesson 2: 去重列的存在

**问题**：广告活动报告中有 impressions/clicks/spend/cpc 和它们的去重版本（impressions_dedup 等）。去重版本可能比非去重版本值大（因为去除了跨活动重复）。
**决定**：当前分析用非去重版本。去重版本保留在列映射中但未参与分析。如需切换，修改分析脚本中的列名引用。

### Lesson 3: 广告位中文值精确匹配

**问题**：最初用模糊关键词匹配广告位分类（如 "顶部搜索结果"），未覆盖实际值 "亚马逊站内的搜索结果顶部"。
**解决**：从实际数据导出所有唯一值，建立精确映射字典。4 个实际值：顶部 / 商品页面 / 其余位置 / 站外。

### Lesson 4: 光环效应数据因报告而异

**问题**：广告 SKU vs 其他 SKU 的销售数据只在投放报告中完整。广告位报告中没有这个字段，搜索词报告有同样的列。
**解决**：光环效应分析放在 `analyze_targeting.py` 中。后续如需要可在搜索词报告中也做。

### Lesson 5: 数据量较大的文件是搜索词报告

**问题**：搜索词报告 4,928 行，4 个报告中最大。分类函数 classify_search_term 对每条搜索词做多次字符串匹配。
**当前方案**：纯 Python 循环处理 5,000 行，耗时可忽略（< 1 秒）。如果扩大到 10 万+行，考虑预编译正则或并行处理。

### Lesson 6: 搜索词必须聚合后再分类（严重缺陷）

**问题**：Amazon 搜索词报告中，同一个客户搜索词会在多行出现——不同的广告活动、广告组、匹配类型各自独立记录。`bed wedge pillow for headboard` 在原始数据中出现了 13 行（分散在 7 个不同广告活动中）。其中 1 行（close-match，枕头138cm 活动）显示 67 点击 / $13.40 花费 / 0 订单，但该词**全量合计**有 1 订单 + $65.99 销售额。

**根因**：`analyze_search_term.py` 逐行判断否定词，没有先按 search_term 聚合。导致一个实际有转化的词因为数据分散在某一行显示零订单，被误判为否定词候选。

**正确做法**（Trellis/WisePPC/SellerSprite 一致）：
1. 先 `GROUP BY search_term` 聚合：SUM(spend), SUM(clicks), SUM(orders), SUM(sales)
2. 再基于聚合后的统一指标做分类
3. 保留 contributing_campaigns 列表供溯源

**来源**：[Trellis Search Term Report Workflow](https://gotrellis.com/resources/blog/amazon-search-term-report-workflow/) — "Pivot by customer search term so each query has one consolidated row."

### Lesson 7: 5 桶分类体系（非 3 桶）

**问题**：当前实现只有 3 个分类（收割/否定/浪费），缺少"观察"和"保护"两个关键的中间状态。

**业界标准 5 桶体系**（Trellis/WisePPC）：

| 桶 | 标准阈值 | 操作 |
|----|---------|------|
| **Harvest 收割** | 2-3+ 订单 AND ACoS ≤ 目标(15-30%) | 加入精准匹配活动 → 在源活动否定该词 |
| **Negate 否定** | 15-20+ 点击 AND 0 订单，或完全无关意图 | 精准否定(特定词)或词组否定(整类无关主题) |
| **Monitor 观察** | < 15 点击，数据不足 | 记录在案，下周期复查 |
| **Protect 保护** | 品牌/战略/防御性词 | 保持投放，不论短期 ACoS |
| **Ignore 忽略** | 极少展示/点击，花费可忽略 | 不做任何操作 |

**关键**：Negate 阈值过低（10 点击→15-20 点击），因为 < 15 点击零订单是统计上的小样本，不是判决。"Negating under 15 clicks is usually premature."

**来源**：[WisePPC 搜索词报告优化指南](https://wiseppc.com/zh/blog/search-term-report-optimization/) / [Trellis Workflow](https://gotrellis.com/resources/blog/amazon-search-term-report-workflow/)

### Lesson 8: SP 广告 7 天点击归因窗口

**问题**：Sponsored Products 使用 **7 天点击归因**。用户导出的"近 30 天"报告，最后 3-4 天的订单数据可能不完整——客户在报告最后一天点击，但在报告窗口外下单，该订单不会被计入。

**影响**：报告末尾看起来"零订单"的词可能实际有转化。分析时应：
1. 提示用户报告期最小 14 天（确保第一周归因完整）
2. 推荐使用 30-60 天窗口
3. 对大额花费但"零订单"的词，标注归因窗口风险

**数据保留期**：Amazon 仅保留 **~60 天**搜索词数据，超过永久丢失。Treillis 建议每次下载后立即归档。

**来源**：[SalesDuo Amazon Ads Reporting](https://salesduo.com/blog/amazon-ads-reporting/) / [Trellis Workflow](https://gotrellis.com/resources/blog/amazon-search-term-report-workflow/)

### Lesson 9: 否定词操作的两个关键细节

**1. SP 只有词组否定和精准否定，没有广泛否定。** 中文后台同样。

**2. 收割后必须在源活动否定。** "Add it as a negative exact in the campaign that discovered it." 如果只收割不否定，新旧活动同时竞价同一个搜索词，造成自我竞争、CPC 抬高、归因混乱。**两步缺一不可。**

**3. 谨慎使用词组否定。** "Negative phrase blocks every query containing the phrase — it's a wider blast radius." 一个不小心的词组否定可能屏蔽几十个正在转化的长尾词。只有确认整类主题永远不相关时才用。

**来源**：[跨境魔方 否定广告完整逻辑](https://www.upkuajing.com/knowledge/zixun/25823) / [Trellis Workflow](https://gotrellis.com/resources/blog/amazon-search-term-report-workflow/)

### Lesson 10: 决策日志的重要性

**问题**：当前每次跑分析结果会覆盖前一次 JSON，没有历史记录。

**业界标准**：Treillis 明确要求每次运行记录：
- 收割了哪些词（+ 日期 + 来源活动）
- 否定了哪些词（+ 原因 + 影响花费）
- 标记为 Monitor 的词
- 处理了多少花费

> "Without a log, you re-litigate the same terms every week and can't explain account changes."

**实现方向**：`out/decision_log.json` 追加式记录，不覆盖。`build_report.py` 行动 sheet 引用上期 vs 本期的变化。

### Lesson 11: 报告字段命名差异（中文后台 vs API）

**来源**：[Amazon Ads API v3 Report Types](https://advertising.amazon.com/API/docs/en-us/guides/reporting/v3/report-types/overview)

**发现**：
- 中文后台导出的列名与 API v3 标准字段名不完全对应
- 广告活动 CSV 报告中"去重"开头的列（去重展示量/去重点击量/去重花费），中文后台显示为"去年曝光量/去年点击量/去年支出"——这是**编码错位**导致的
- 广告位报告的放置列有 4 个实际值：站内搜索结果顶部/站内商品页面/站内搜索其余位置/站外
- 搜索词报告中 `match_type` 对自动广告显示为 `-`（空），实际对应 API 的 Close-match / Loose-match / Substitutes / Complements

### Lesson 12: CSV 金额格式问题

**问题**：广告活动 CSV 报告的金额列（spend/sales/budget/cpc）是 `$17.78` 格式的文本字符串，pandas `pd.to_numeric` 直接调用全部返回 NaN。

**根因**：Amazon 中文后台导出的 CSV 在金额列加了 `$` 符号前缀。

**解决**：`__init__.py` 加载阶段统一清洗：`str.replace(r"[$,\s]", "", regex=True)` 后再 `pd.to_numeric`。

**适用范围**：所有 Amazon 中文后台导出的 CSV 报告。

## 后续可扩展方向

1. **Web Dashboard** — 用 FastAPI + Chart.js 替换 Excel，支持日期范围筛选、活动筛选、词云
2. **多期对比** — 加载多个月份的数据，生成环比/同比趋势图
3. **自动化周报** — CronJob 定期跑分析 → 邮件发送 Excel
4. **SB/SD 报告** — 扩展支持 Sponsored Brands / Sponsored Display 报告
5. **盈亏建模** — 接入 EN BOM 成本数据，计算实际盈亏平衡 ACOS
6. **Rufus/COSMO 适配** — 2026 年 Amazon 算法从关键词匹配转向意图理解，需要适配新的归因模型

## 文档归档说明

本模块遵循项目 `docs/superpowers/` 分类规范：

| 文档类型 | 位置 | 说明 |
|---------|------|------|
| 调研报告 | `docs/superpowers/research/2026-06-16-amazon-advertising-analysis-research.md` | 35 个资料来源 + 方法论摘要 |
| 设计文档 | `docs/superpowers/specs/2026-06-16-amazon-advertise-analysis-design.md` | 架构设计 + 决策记录 |
| 实现计划 | `.claude/plans/amazon-wiggly-mountain.md` | 实现步骤 + 完成状态 |
| Agent 参考 | `advertise/AGENT_HANDOFF.md` | 本文件 — 模块级完整参考 |
| 人读文档 | `advertise/README.md` | 使用方法 + 指标说明 |
| 参考文档 | `advertise/参考文档/` | **同事/朋友给的外部 MD/PDF（目前空）** |

### 参考文档目录说明

`advertise/参考文档/` 不是存放调研资料的。它的用途是：**同事或朋友从其他公司/渠道获得的 Amazon 广告投放相关 MD/PDF 文档**，可以直接放入此目录，Agent 可通过 Read 工具读取。

调研资料（网上搜索到的网页内容、URL 列表、方法论摘要）按项目规范存放于 `docs/superpowers/research/`。
