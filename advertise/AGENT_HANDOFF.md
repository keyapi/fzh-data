# AGENT_HANDOFF.md — Amazon 广告数据分析模块

> **入口文件** — Agent 接手时先读这个。需要细节时按链接深入。
>
> 版本: v0.3 | 分支: amazon_advertise | PR: [#14](https://github.com/keyapi/fzh-data/pull/14) | 更新: 2026-06-17

## 这是什么

从 Amazon 后台导出的 Sponsored Products 报告 → 全维度 Excel 分析报告。当前覆盖 4/13 种 SP 报告。

## 快速启动

```bash
uv run python -m advertise.analyze_campaign     # 广告活动
uv run python -m advertise.analyze_targeting    # 投放
uv run python -m advertise.analyze_search_term  # 搜索词 (聚合+5桶)
uv run python -m advertise.analyze_placement    # 广告位
uv run python -m advertise.build_report         # → Excel 报告
```

## 当前数据

`数据源/如森US-近30天广告数据/` — 4 个文件 (campaign/targeting/search_term/placement), 2026-05-17 ~ 06-15

## 文档地图 (渐进式加载)

| 你需要... | 读这个 |
|----------|--------|
| 了解运行方法 + 指标说明 | [`README.md`](README.md) |
| 查阅列名映射 | [`docs/superpowers/advertise/reference/column-mappings.md`](../docs/superpowers/advertise/reference/column-mappings.md) |
| 了解我们有什么数据 / 缺什么 | [`docs/superpowers/advertise/reference/data-sources.md`](../docs/superpowers/advertise/reference/data-sources.md) |
| 了解工具 (优麦云/卖家精灵等) | [`docs/superpowers/advertise/reference/tools-ecosystem.md`](../docs/superpowers/advertise/reference/tools-ecosystem.md) |
| 了解可复用 Skills/MCP | [`docs/superpowers/advertise/reference/skills-mcp-catalog.md`](../docs/superpowers/advertise/reference/skills-mcp-catalog.md) |
| 查看全部调研来源 URL | [`docs/superpowers/advertise/reference/source-urls.md`](../docs/superpowers/advertise/reference/source-urls.md) |
| 查看经验教训 (12 条) | [`docs/superpowers/advertise/lessons/lessons-learned.md`](../docs/superpowers/advertise/lessons/lessons-learned.md) |
| 查看设计决策 + 架构 | [`docs/superpowers/advertise/specs/2026-06-16-amazon-advertise-analysis-design.md`](../docs/superpowers/advertise/specs/2026-06-16-amazon-advertise-analysis-design.md) |
| 查看调研报告 | [`docs/superpowers/advertise/research/2026-06-16-amazon-advertising-analysis-research.md`](../docs/superpowers/advertise/research/2026-06-16-amazon-advertising-analysis-research.md) |
| 查看路线图 + 下一步 | [`docs/superpowers/advertise/roadmap.md`](../docs/superpowers/advertise/roadmap.md) |
| 文档总索引 | [`docs/superpowers/advertise/index.md`](../docs/superpowers/advertise/index.md) |

## 核心发现 (v0.2)

总花费 $3,483 → 销售额 $11,513 → ACOS 30.25% → ROAS 3.31x
收割 10 词 ($168→$2,238), 否定 32 词 (省 $498), 观察 504 词 ($1,266)
Top of Search 最优 (ACOS 17.34%), 光环效应 3.77x

## 关键架构决策

- **模块化 > 单脚本**: 独立可跑, JSON 中间产物可被 Web 消费
- **阈值常量 > 命令行参数**: 少改, 直观
- **5 桶分类** (v0.2): Harvest(≥2单) / Negate(≥15点击) / Monitor / Protect / Ignore
- **先聚合再分类** (v0.2): GROUP BY search_term 后判断 (修复 Lesson 6)

## 当前工具

**优麦云** (在用) — ERP+广告管理, 无 API 但 Excel 导出, 保存全量历史数据
**卖家精灵** MCP — 竞品关键词情报 (按需, `open.sellersprite.com/mcp/22`)

## 7 个已知不足

1. 缺 Business Understanding (盈亏平衡点未知)
2. 无环比/同比
3. 无行业基准 (家居类目平均 ACOS 32.5%)
4. 数据源不全 (4/13 种 SP 报告)
5. 无竞争情报
6. 只看 ACoS 不看 TACoS/NTB%/LTV
7. 无多触点归因

详见 [roadmap.md → 立即可执行](../docs/superpowers/advertise/roadmap.md)
