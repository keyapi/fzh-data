# Amazon 广告分析模块 — 文档索引

> 渐进式加载。Agent 接手时只需读 `advertise/AGENT_HANDOFF.md`（入口），需要细节时按下面索引深入。

## 快速导航

| 你需要... | 读这个 |
|----------|--------|
| 快速了解模块 + 开始工作 | [`advertise/AGENT_HANDOFF.md`](../../../advertise/AGENT_HANDOFF.md) |
| 了解怎么运行脚本 | [`advertise/README.md`](../../../advertise/README.md) |
| 查看调研来源和方法论 | [research/](research/) |
| 查看设计决策和架构 | [specs/](specs/) |
| 查阅列名映射、数据源、工具对比 | [reference/](reference/) |
| 查阅经验教训 | [lessons/](lessons/) |

## 目录结构

```
docs/superpowers/advertise/
├── index.md                           ← 你在这里
├── research/                          ← 调研报告
│   └── 2026-06-16-amazon-advertising-analysis-research.md
├── specs/                             ← 设计文档
│   └── 2026-06-16-amazon-advertise-analysis-design.md
├── reference/                         ← 参考资料（按需加载）
│   ├── column-mappings.md             ← 4 份报告完整列名映射
│   ├── data-sources.md               ← Amazon 数据生态全图
│   ├── tools-ecosystem.md            ← 工具对比（优麦云/卖家精灵/Perpetua等）
│   ├── source-urls.md                ← 60+ 调研来源 URL 索引
│   └── skills-mcp-catalog.md         ← 可复用 Skills/MCP 目录
├── lessons/                           ← 经验教训
│   └── lessons-learned.md            ← 12 条 Lessons Learned
└── roadmap.md                         ← 专家系统路线图 + 阶段状态
```

## 设计原则

- **渐进披露**: `AGENT_HANDOFF.md` 只放高频信息 + 导航，细节在 `reference/`
- **Diátaxis 四象限**: Tutorial (README) / How-to (AGENT_HANDOFF) / Reference (reference/) / Explanation (research/, specs/)
- **每个文件独立可读**: 不依赖上下文，有 "为什么读这个" 说明
- **交叉引用**: 每页底部有 "See also" 链接
