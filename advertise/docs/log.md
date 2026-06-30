---
okf: v0.1
type: Log
title: 变更日志
description: Amazon 广告分析模块的时序变更记录
tags: [amazon, advertising, changelog]
---

# 变更日志

## 2026-06-30

- **v0.3 修正**: 9 种 SP 报告类型官方文档逐项校验（3 并行 agent），修正 5 处错误声明
- **v0.3 修正**: `data-sources.md` 重写缺失报告表 — 增加校验状态(✅/⚠️/❌)、实际获取方式、官方文档 URL
- **v0.3 修正**: 6 种可获取报告的完整列结构详表（中英对照 + 含义 + API 配置参数）
- **v0.3 修正**: 新增 Lesson 13（外部数据源声明必须先验证官方文档）+ `docs/solutions/documentation-gaps/`
- **v0.3 修正**: AGENT_HANDOFF.md 修复 merge conflict + 清理过时引用 + 添加 Agent 首次接手检查清单
- **v0.3 修正**: README.md 添加非技术同事入口 + troubleshooting section
- **v0.3 修正**: 创建 `advertise/数据源/.gitkeep` + `README.txt` 确保目录在仓库中可见
- **v0.3 修正**: 优麦云 + 卖家精灵工具能力核验 — 修正"优麦云无 API"和卖家精灵 MCP 端点 2 处错误
- **v0.3 修正**: 新增 Lesson 14（第三方工具声明同样需要官方核验）
- **v0.3 新增**: `colleague-data-requests.md` — 向运营同事要数据的话术模板
- **v0.3 新增**: `report-download-checklist.md` — 给 YX 的 10 种报告手动下载清单

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
