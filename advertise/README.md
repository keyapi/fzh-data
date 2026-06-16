# Amazon 广告数据分析工具

> 适用场景：Amazon 后台导出的 Sponsored Products（商品推广）报告 → 全维度分析 → Excel 报告。
>
> **版本**: v0.2 | **分支**: amazon_advertise | **PR**: [#14](https://github.com/keyapi/fzh-data/pull/14)
>
> 详细技术文档（供 Agent 接手）→ `AGENT_HANDOFF.md`

## 快速开始

### 1. 准备数据

把 Amazon 广告后台导出的 4 份报告放到 `数据源/` 下任意子目录：

| 报告名称 | 必需 | 导出路径 |
|---------|------|---------|
| 商品推广_广告活动_报告 | ✅ | 广告活动管理 → 报告 → 创建报告 → 广告活动 |
| 商品推广_投放_报告 | ✅ | 同上，选择 "投放" |
| 商品推广_搜索词_报告 | ✅ | 同上，选择 "搜索词" |
| 商品推广_广告位_报告 | ✅ | 同上，选择 "广告位" |

> 文件名需包含关键字：`广告活动` / `投放` / `搜索词` / `广告位`，脚本会自动识别。

### 2. 运行分析

```bash
# 依次运行 4 个分析脚本（可单独跑）
uv run python -m advertise.analyze_campaign
uv run python -m advertise.analyze_targeting
uv run python -m advertise.analyze_search_term
uv run python -m advertise.analyze_placement

# 生成最终 Excel 报告
uv run python -m advertise.build_report
```

输出在 `out/如森US-广告分析报告.xlsx`。

### 3. 查看报告

用 Excel / WPS 打开，6 个 Sheet：

| Sheet | 内容 |
|-------|------|
| 总览 | 30 天关键数字、数据一致性校验、核心发现 |
| 广告活动 | 37 个活动 ACOS/ROAS 排行 + 散点图 |
| 投放表现 | 按匹配类型对比、光环效应、零转化投放 |
| 搜索词洞察 | 关键词收割 TOP50、否定词候选、搜索词分类饼图 |
| 广告位效率 | Top of Search vs Product Pages vs Rest 对比 + 出价建议 |
| 行动建议 | 按优先级排列的操作清单 + 优化节奏 |

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
├── 数据源/                ← Amazon 后台导出的原始报告（csv/xlsx）
├── 参考文档/              ← 同事/朋友给的参考文档（MD/PDF）
├── out/                   ← 分析输出（JSON + Excel）
├── analyze_campaign.py    ← 广告活动层分析
├── analyze_targeting.py   ← 投放/关键词层分析
├── analyze_search_term.py ← 搜索词层分析（核心）
├── analyze_placement.py   ← 广告位层分析
├── build_report.py        ← 汇总 → Excel
├── README.md              ← 本文件
└── AGENT_HANDOFF.md       ← Agent 开发参考
```

## 后续计划

- [ ] Web 交互页面（筛选/下钻/趋势图）
- [ ] 多期数据对比（环比/同比）
- [ ] 自动化周报（定时导出 + 邮件发送）
