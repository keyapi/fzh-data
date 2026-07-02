---
okf: v0.1
type: Index
title: Amazon 广告分析模块 — 文档索引
description: 渐进式加载入口
tags: [amazon, advertising, index]
---
# Amazon 广告分析模块 — 文档索引

> 渐进式加载。Agent 接手时只需读 `advertise/AGENT_HANDOFF.md`（入口），需要细节时按下面索引深入。

## 快速导航

| 你需要... | 读这个 |
|----------|--------|
| 快速了解模块 + 开始工作 | [`../AGENT_HANDOFF.md`](../AGENT_HANDOFF.md) |
| 了解怎么运行脚本 | [`../README.md`](../README.md) |
| 查看调研来源和方法论 | [research/](research/) |
| 查看设计决策和架构 | [specs/](specs/) |
| 查阅列名映射、数据源、工具对比 | [reference/](reference/) |
| 查阅 API 报告字段定义 (SP) | [reference/sp-report-column-reference.md](reference/sp-report-column-reference.md) |
| 查阅 API 报告字段定义 (SB+SD) | [reference/sb-sd-report-column-reference.md](reference/sb-sd-report-column-reference.md) |
| 查阅经验教训 | [lessons/](lessons/) |
| 查看总体规划 | [specs/2026-07-02-ad-analysis-master-plan.md](specs/2026-07-02-ad-analysis-master-plan.md) |
| 了解各报告分析价值 | [research/sp-report-analysis-value.md](research/sp-report-analysis-value.md) |
| 了解代码库现状 | [research/existing-codebase-audit.md](research/existing-codebase-audit.md) |
| 了解否定词 bulksheet 格式 | [research/amazon-bulk-negative-keyword-format.md](research/amazon-bulk-negative-keyword-format.md) |

## 目录结构

```
advertise/                               ← 广告分析模块根目录
├── AGENT_HANDOFF.md
├── README.md
├── __init__.py                          ← 数据加载 (Console + API 双格式)
├── utils.py                             ← 共享工具函数
├── thresholds.py                        ← 集中阈值管理
├── column_maps.py                       ← API 8 种报告列名映射
├── config/bjryecltd-us.json             ← 账户配置
├── analyze_campaign.py                  ← 广告活动层分析
├── analyze_targeting.py                 ← 投放层分析
├── analyze_search_term.py               ← 搜索词 5 桶分类
├── analyze_placement.py                 ← 广告位效率对比
├── analyze_ad_group.py                  ← 广告组结构诊断 (新建)
├── analyze_advertised_product.py        ← ASIN 效率排行 (新建)
├── analyze_purchased_item.py            ← 品牌光环分析 (新建, 最高 ROI)
├── analyze_cross.py                     ← 跨报告集成分析 (新建)
├── calibrate_thresholds.py              ← 阈值基线标定 (新建)
├── build_full_report.py                 ← Excel 10-sheet 报告生成器 (新建)
├── build_report.py                      ← 旧版 Excel 报告 (Console 格式)
├── generate_negatives.py                ← Amazon bulksheet 否定词生成器 (新建)
├── out/                                 ← 输出 (JSON + xlsx)
│   ├── campaign_analysis.json
│   ├── targeting_analysis.json
│   ├── search_term_analysis.json
│   ├── placement_analysis.json
│   ├── ad_group_analysis.json
│   ├── advertised_product_analysis.json
│   ├── purchased_item_analysis.json
│   ├── cross_analysis.json
│   ├── threshold_calibration.json
│   ├── BJRYECLTD-US-广告分析报告-2026-06.xlsx
│   └── BJRYECLTD-US-否定词bulksheet-2026-06.xlsx
├── data/                                ← API 下载的 xlsx 数据
└── docs/                                ← OKF v0.1 bundle
    ├── index.md                         ← 你在这里
    ├── log.md                           ← 变更历史
    ├── roadmap.md
    ├── research/                        ← 调研报告
    │   ├── sp-report-analysis-value.md
    │   ├── existing-codebase-audit.md
    │   ├── amazon-bulk-negative-keyword-format.md
    │   └── 2026-06-16-amazon-advertising-analysis-research.md
    ├── specs/                           ← 设计文档
    │   ├── 2026-07-02-ad-analysis-master-plan.md
    │   └── 2026-06-16-amazon-advertise-analysis-design.md
    ├── reference/                       ← 参考资料
    │   ├── column-mappings.md
    │   ├── data-sources.md
    │   ├── sp-report-column-reference.md
    │   ├── sb-sd-report-column-reference.md
    │   └── amazon-official-docs/
    └── lessons/
        └── lessons-learned.md
```

## 设计原则

- **渐进披露**: `AGENT_HANDOFF.md` 只放高频信息 + 导航，细节在 `reference/`
- **Diátaxis 四象限**: Tutorial (README) / How-to (AGENT_HANDOFF) / Reference (reference/) / Explanation (research/, specs/)
- **每个文件独立可读**: 不依赖上下文，有 "为什么读这个" 说明
- **交叉引用**: 每页底部有 "See also" 链接
