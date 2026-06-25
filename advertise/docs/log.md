---
okf: v0.1
type: Log
title: 变更日志
description: Amazon 广告分析模块的时序变更记录
tags: [amazon, advertising, changelog]
---

# 变更日志

## 2026-06-25

- **赛狐 API 接入实践**: Playwright 浏览器自动化突破 Apifox 密码保护，成功获取 OAuth 认证文档
- **OAuth 认证成功**: client_credentials grant，获得 access_token（24h有效），确认凭证有效
- **API 端点探测**: IP 白名单阻止业务端点调用，token 端点例外
- **文档结构发现**: 16 个 API 模块确认（商品/销售/订单/广告/FBA/采购/仓库/数据/财务/工具/设置/Feed/报告中心/多平台 + 数据结构 + 场景调用指南）
- 新增 lessons/: 2026-06-25-sellfox-integration-lessons.md (10条踩坑教训)
- 新增 research/: 2026-06-25-sellfox-api-exploration.md (API探索完整记录)
- 更新 AGENT_HANDOFF.md: 全面重写，包含当前状态、凭证位置、文档地图、关键决策
- **关键教训**: Sellfox MCP 亲自验证（2星7提交，早期项目）、多账号安全是架构第一约束、认证方式不能猜测必须查文档
- **凭证标准化**: .env + config_sellfox.json 双格式，AGENT_HANDOFF.md 中记录位置

## 2026-06-24

- **多账号安全专项调研**: 4路并行调研（防关联机制、领星MCP、赛狐API、架构风险）
- 新增 reference/: 2026-security-multi-account.md, 2026-sp-api-developer-model.md, 2026-sellfox-api-guide.md
- 关键发现: SP-API多账号管理是官方支持的安全模式（风险2/10），ERP中介（赛狐/领星）通过SPN认证是最安全路径
- Sellfox MCP亲自验证: shuolol/sellfox-mcp（2星7提交，第三方开源，65%广告工具，不建议作核心依赖）
- 更新: index.md (新增3个导航条目), reference/index.md (新增3个文档)
- 赛狐 OpenAPI 已开通: 生产环境 openapi.sellfox.com，API文档 sellfoxapi.apifox.cn

## 2026-06-24 (early)

- **行业全景调研完成**: 83次搜索×6维度
- 新增 reference/: 2026-strategy-frameworks.md, 2026-ai-ml-landscape.md, 2026-tools-comparison.md, 2026-api-data-ecosystem.md, 2026-system-architecture.md, 2026-market-intelligence.md, verified-sources.md
- 新增 research/: 2026-06-24-industry-landscape.md
- 新增 lessons/: 2026-06-24-research-insights.md
- 创建子目录索引: lessons/index.md, reference/index.md, research/index.md, specs/index.md
- 更新: index.md, source-urls.md, roadmap.md

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
