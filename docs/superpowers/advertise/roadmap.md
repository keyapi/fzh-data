# 专家系统路线图 — Amazon 广告分析

> 何时读: 规划下一阶段工作时、需要了解整体进度和优先级。

## 版本历程

| 版本 | 日期 | 关键变更 |
|------|------|---------|
| v0.1 | 2026-06-16 | 基础 4 维分析 + Excel 报告, 逐行搜索词分析 |
| v0.2 | 2026-06-16 | 搜索词聚合→5桶分类, 阈值对齐行业标准, 归因窗口检查 |
| v0.3 | 2026-06-17 | 6 维度专家调研, 工具修正(优麦云), Skills/MCP 调研, TACoS/AMC/COSMO 深度挖掘 |

## 核心发现 (v0.2 分析)

| 维度 | 关键数字 |
|------|---------|
| 30 天总花费 | $3,483 |
| 30 天销售额 (7d) | $11,513 |
| 整体 ACOS | 30.25% |
| 整体 ROAS | 3.31x |
| Harvest 收割词 | 10 个 |
| Negate 否定词 | 32 个 ($498) |
| Monitor 观察 | 504 个 ($1,266) |
| Top of Search | ACOS 17.34% — 最优 |
| 光环效应 | 3.77x |

## Phase 路线图

### ✅ Phase 1: 基础分析框架
- 数据加载 + 列名映射 + CSV 清洗
- 4 分析脚本 + Excel 6 sheet 报告
- 知识沉淀 (AGENT_HANDOFF + 26 URL)

### ✅ Phase 2: 搜索词修复 + 5 桶体系
- 搜索词聚合 (GROUP BY)
- Harvest/Negate/Monitor/Protect/Ignore
- 阈值对齐 Trellis/WisePPC 标准
- 归因窗口检查

### ✅ Phase 3: 专家调研 (v0.3)
- 6 维度 × 60+ 来源深度调研
- 通用数据分析方法论 (CRISP-DM)
- Amazon 数据生态全图 (13 种 SP 报告)
- 2026 行业趋势 (COSMO/Alexa for Shopping)
- 工具生态 + Skills/MCP 调研

### 下一步 (Phase 4+)

| 优先级 | 目标 | 依赖 |
|--------|------|------|
| 🔴 高 | 从优麦云导出历史广告数据 → 对接分析 | 用户操作 |
| 🔴 高 | TACoS 计算（需 Seller Central Business Reports） | 获取自然销售数据 |
| 🔴 高 | 决策日志持久化 (`out/decision_log.json`) | 无 |
| 🟡 中 | 多期对比 (环比/同比) | 多期数据 |
| 🟡 中 | 补充报告 (Purchased Product + Impression Share + Perf Over Time) | 用户导出 |
| 🟡 中 | 接入 Amazon Ads API 自动化拉取 | 开发者审批 |
| 🟢 低 | Web Dashboard (FastAPI + Chart.js) | Phase 4-6 稳定后 |
| 🟢 低 | AMC 接入 (多触点归因/LTV) | $20K+/月广告花费 |
| 🟢 低 | COSMO 覆盖审计 (15 种关系类型扫描) | COSMO 知识图谱数据 |
| 🟢 低 | 规则引擎自动化 (API 写回) | Ads API 接入 |

## 立即可执行

1. **问用户**: 盈亏平衡 ACoS？（产品毛利率）→ 才能算 TACoS 基准
2. **问用户**: 上期数据？（环比对比）
3. **问用户**: Brand Registry 状态？（可获取 ABA 数据）
4. **从优麦云导出**: 广告/搜索词/销售/库存 Excel → 放入 `数据源/`
5. **导出补充报告**: Purchased Product + Search Term Impression Share + Performance Over Time
6. **试用 Two Minute Reports MCP**: 自然语言查 Amazon Ads 数据

## See also
- [调研报告](research/2026-06-16-amazon-advertising-analysis-research.md)
- [设计文档](specs/2026-06-16-amazon-advertise-analysis-design.md)
- [经验教训](lessons/lessons-learned.md)
- [Skills/MCP 目录](reference/skills-mcp-catalog.md)
