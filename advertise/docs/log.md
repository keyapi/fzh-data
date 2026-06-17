---
okf: v0.1
type: Log
title: 变更日志
description: Amazon 广告分析模块的时序变更记录
tags: [amazon, advertising, changelog]
---

# 变更日志

## 2026-06-17

- **v0.3**: 文档架构重构 — 按 OKF v0.1 标准加 frontmatter, 文档从 `docs/superpowers/` 移至 `advertise/docs/`（co-location）
- **v0.3**: 6 维度专家级深度调研完成（通用数据分析 + Amazon 广告策略 + 数据生态 + 行业趋势 + 工具 + 系统架构）
- **v0.3**: 工具修正 — 优麦云替换卖家精灵作为主要工具, 卖家精灵保留用于竞品情报 MCP
- **v0.3**: Skills/MCP 调研 — 7 个可复用资源目录
- **v0.3**: TACoS 方法论 + AMC 自服务化 + COSMO/Alexa for Shopping 深度研究

## 2026-06-16

- **v0.2**: 搜索词聚合修复 — 先 GROUP BY search_term 再分类 (修复 `bed wedge pillow for headboard` 误判)
- **v0.2**: 5 桶分类体系 — Harvest/Negate/Monitor/Protect/Ignore
- **v0.2**: 阈值对齐行业标准 — Harvest≥2单, Negate≥15点击, Monitor<15点击
- **v0.2**: 归因窗口检查 — 报告期<14天自动警告
- **v0.1**: 基础框架 — 数据加载 + 4 分析脚本 + Excel 6 sheet 报告
- **v0.1**: AGENT_HANDOFF.md 初始版 + 26 个资料来源 URL
