# Amazon 广告数据分析 — 设计文档

> 日期：2026-06-16 | 分支：amazon_advertise | 状态：已实现

## 背景

Amazon 广告数据首次接入 fzh-data 项目。用户从 Amazon 后台导出了 4 份 Sponsored Products 报告，需要全面分析广告效果。数据规模：30 天，$3,472 花费，$11,403 销售额。

## 数据源

4 份 Amazon Sponsored Products 中文后台报告：
- 广告活动报告 (37 行 × 25 列)
- 投放报告 (180 行 × 26 列)
- 搜索词报告 (4,928 行 × 26 列)
- 广告位报告 (126 行 × 18 列)

## 实现架构

```
模块化 Pipeline: 4 分析脚本 + 1 汇总脚本
中间数据: JSON (可单独查看/消费)
最终输出: 多 sheet Excel + 图表 (openpyxl)
```

## 分析维度

1. **广告活动** — ACOS/ROAS 排行、预算利用率、优胜/问题标记
2. **投放** — 匹配类型对比、关键词vs商品投放、光环效应
3. **搜索词** — 关键词收割、否定词识别、搜索词分类
4. **广告位** — Top of Search/Product Pages/Rest/站外四位对比

## 设计决策

- 模块化 > 单脚本：独立性、可扩展性、Agent 友好
- 阈值常量 > 命令行参数：少改动、直观
- 中文精确匹配 > 模糊匹配：Amazon 列名版本变化可检测
- openpyxl > xlsxwriter：更好的图表支持

## 资料来源

英文 16 篇 + 中文 10 篇（详见 AGENT_HANDOFF.md），覆盖 Canopy、Feedvisor、SalesDuo、SellerSprite、WisePPC、AMZScout 等。
