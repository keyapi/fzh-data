---
okf: v0.1
type: Guide
title: Amazon 广告数据分析工具 — 用户指南
description: 非技术同事快速入口 + 技术同事运行指南，7 种 SP 报告分析
tags: [amazon, advertising, guide, user]
updated: 2026-07-07
---
# Amazon 广告数据分析工具

> 适用场景：Amazon 后台导出的 Sponsored Products（商品推广）报告 → 全维度分析 → Excel 报告。
>
> **版本**: v0.5 | **分支**: amazon_advertise | **PR**: [#14](https://github.com/keyapi/fzh-data/pull/14)
>
> 详细技术文档（供 Agent 接手）→ `AGENT_HANDOFF.md`

## 非技术同事 · 一句话入口

把 Amazon 广告后台的 4 份报告下载好放到 `数据源/` 后，打开 Agent 说：

> **帮我分析 Amazon 广告数据**

Agent 会自动读文档、找文件、跑脚本、出报告。你只需验证结果。

---

## 快速开始

### 1. 准备数据（推荐：赛狐 API / Proxy 自动拉取）

```bash
# 一键拉 SP 核心 7 表（优先 Proxy：ai_access_poc/open_webui/.env 的 SELLFOX_PROXY_*）
uv run python advertise/scripts/pull_sp7_verify.py --shop-id 596841 --days 30

# 旧路径：fetch_ad_reports.py 只拉 4 表；另 3 表需 fetch_extra_reports.py（且默认硬编码日期）
# uv run python SELLFOX_API/fetch_ad_reports.py --shop <店铺ID> --days 30
# uv run python SELLFOX_API/fetch_extra_reports.py
```

> 备选：手动从 Amazon 广告后台下载 7 份报告放入 数据源/，脚本自动识别中/英文文件名。  
> 独立验证产物：`advertise/docs/research/2026-07-28-report-verify/`（勿信任旧 `advertise/out/` JSON）。

### 2. 运行分析

```bash
# 7 维分析 + 跨报告集成 + 优化产出
uv run python -m advertise.analyze_campaign
uv run python -m advertise.analyze_targeting
uv run python -m advertise.analyze_search_term
uv run python -m advertise.analyze_placement
uv run python -m advertise.analyze_ad_group
uv run python -m advertise.analyze_advertised_product
uv run python -m advertise.analyze_purchased_item
uv run python -m advertise.analyze_cross
uv run python -m advertise.build_full_report
uv run python -m advertise.calibrate_thresholds
uv run python -m advertise.generate_negatives
```

### 3. 查看报告

用 Excel / WPS 打开，10 个 Sheet + 48 条行动建议：

| Sheet | 内容 |
|-------|------|
| 总览 | 关键数字、直接/混合 ACOS、健康度评分 |
| 跨报告集成 | Blended ACOS、Gateway ASIN、收割/否定清单 |
| 广告活动 | 活动 ACOS/ROAS 排行 + 散点图 |
| 投放表现 | 按匹配类型对比、光环效应、零转化投放 |
| 搜索词 | 5 桶分类、关键词收割 TOP50、否定词候选 |
| 广告位 | Top of Search vs Product Pages vs Rest 对比 |
| 广告组结构 | 组粒度预算分配、跨活动同名组检测 |
| ASIN效率 | 29 ASIN 效率排行、零销售高花费标记 |
| 品牌光环 | Gateway ASIN 判定、交叉销售矩阵 |
| 行动建议 | 48 条按优先级排列的操作清单 |

## 分析指标说明

| 指标 | 含义 | 健康区间 |
|------|------|---------|
| **ACOS** | 广告花费 ÷ 广告销售额 | 低于产品毛利率即为盈利 |
| **ROAS** | 广告销售额 ÷ 广告花费 | 若毛利率 30%，ROAS > 3.33 才保本 |
| **CTR** | 点击量 ÷ 展示量 | 0.3%-0.8% 为正常范围 |
| **CVR** | 订单数 ÷ 点击量 | 视品类而定，5-15% 常见 |
| **CPC** | 花费 ÷ 点击量 | 视品类竞争度，$0.3-$1.5 常见 |

### 关键词收割

从搜索词报告中找出**高转化、低 ACOS** 的客户搜索词，建议将其加入精准匹配（Exact Match）广告活动，进行精细化出价控制。

### 否定词

从搜索词报告中找出**有花费但零转化**的搜索词，建议在对应广告活动中添加为否定关键词，避免后续继续花费。

## 可配置阈值

各分析脚本顶部有可配置常量，按需调整：

```python
# analyze_campaign.py
HIGH_ACOS_THRESHOLD = 0.50   # ACOS > 50% 标记为高风险

# analyze_search_term.py
MIN_CLICKS_HARVEST = 5        # 关键词收割：最少点击数
MAX_ACOS_HARVEST = 0.30       # 关键词收割：最大 ACOS
MIN_SPEND_NEGATIVE = 1.0      # 否定词：最低花费 ($)
MIN_CLICKS_NEGATIVE = 10      # 否定词：最低点击数
```

## 目录结构

```
advertise/
├── config/                ← 账户配置 (品牌词/阈值/竞品)
├── data/                  ← 赛狐 API 拉取的原始报告（xlsx）
├── 数据源/                ← 手动导出的原始报告
├── 参考文档/              ← 产品策略参考
├── out/                   ← 分析输出（JSON + Excel + bulksheet）
├── analyze_campaign.py    ← 广告活动
├── analyze_targeting.py   ← 投放/关键词
├── analyze_search_term.py ← 搜索词 5 桶（核心）
├── analyze_placement.py   ← 广告位
├── analyze_ad_group.py    ← 广告组结构
├── analyze_advertised_product.py ← ASIN 效率
├── analyze_purchased_item.py     ← 品牌光环
├── analyze_cross.py       ← 跨报告集成
├── build_full_report.py   ← 10-sheet Excel
├── calibrate_thresholds.py ← 阈值标定
├── generate_negatives.py  ← 否定词 bulksheet
├── utils.py / thresholds.py / column_maps.py ← 基础设施
├── README.md              ← 本文件
└── AGENT_HANDOFF.md       ← Agent 开发参考
`docs/reference/column-mappings.md` |
| 输出报告在哪 | `out/如森US-广告分析报告.xlsx` |

## 后续计划

- [x] 7 种 SP 报告全覆盖 + 跨报告集成分析
- [x] 否定词 bulksheet 自动生成
- [x] 阈值自动标定
- [ ] 产品线聚合视图
- [ ] 搜索词战略分层（防守/主攻/长尾）
- [ ] Campaign 结构蓝图建议
- [ ] 多期数据对比（环比/同比）
- [ ] 决策日志持久化
- [ ] Web Dashboard
