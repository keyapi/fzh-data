# AGENT_HANDOFF.md — Amazon 广告数据分析模块

> **入口文件** — Agent 接手时先读这个。需要细节时按链接深入。
>
> 版本: v0.5 | 分支: amazon_advertise | PR: [#14](https://github.com/keyapi/fzh-data/pull/14) | 更新: 2026-07-07

## 这是什么

从 Amazon 后台导出的 Sponsored Products 报告 → 全维度 Excel 分析报告。当前覆盖 7 种 SP 报告 + 跨报告集成分析 + 阈值标定 + 否定词 bulksheet 生成。SB/SD 数据极少暂未接入。

## 快速启动

```bash
uv run python -m advertise.analyze_campaign     # 广告活动
uv run python -m advertise.analyze_targeting    # 投放
uv run python -m advertise.analyze_search_term  # 搜索词 (聚合+5桶)
uv run python -m advertise.analyze_placement    # 广告位
uv run python -m advertise.build_report         # → Excel 报告
```

## 当前数据

`数据源/` — 每次分析前从 Amazon 广告后台下载最新的 4 份 SP 报告（30 天窗口）。数据文件不会被 git 跟踪。

> 赛狐 API（如需接入 API）：凭证在 `SELLFOX_API/.env`（优先），`advertise/.env`（备用）
> 实战脚本：`SELLFOX_API/fetch_ad_reports.py` — 已通过 API 端到端验证（4 种 SP 报告拉取成功）
> API 文档 https://sellfoxapi.apifox.cn/ | 生产环境 https://openapi.sellfox.com/

## Agent 首次接手检查清单

当用户说"帮我分析 Amazon 广告数据"时，按以下步骤执行：

1. 检查 `数据源/` 目录下是否存在含以下关键词的文件：`广告活动`、`投放`、`搜索词`、`广告位`
2. 如果文件不足 4 个 → 引导用户从 Amazon 广告后台下载（导航：广告活动管理 → 报告 → 创建报告 → 选择对应报告类型）
3. 如果文件齐备 → 按文件名关键词识别各报告类型
4. 依次运行 `analyze_campaign` → `analyze_targeting` → `analyze_search_term` → `analyze_placement` → `build_report`（均通过 `uv run python -m advertise.<script>` 从项目根目录运行）
5. 报告输出到 `advertise/out/如森US-广告分析报告.xlsx`，告知用户路径

## 文档地图 (渐进式加载 → 文档符合 OKF v0.1 规范)

| 你需要... | 读这个 |
|----------|--------|
| 了解运行方法 + 指标说明 | [`README.md`](README.md) |
| 查阅列名映射 | [`docs/reference/column-mappings.md`](docs/reference/column-mappings.md) |
| 了解我们有什么数据 / 缺什么 | [`docs/reference/data-sources.md`](docs/reference/data-sources.md) |
| 了解工具 (优麦云/卖家精灵等) | [`docs/reference/tools-ecosystem.md`](docs/reference/tools-ecosystem.md) |
| 了解可复用 Skills/MCP | [`docs/reference/skills-mcp-catalog.md`](docs/reference/skills-mcp-catalog.md) |
| 查看全部调研来源 URL | [`docs/reference/source-urls.md`](docs/reference/source-urls.md) |
| 查看经验教训 (12 条) | [`docs/lessons/lessons-learned.md`](docs/lessons/lessons-learned.md) |
| 查看设计决策 + 架构 | [`docs/specs/2026-06-16-amazon-advertise-analysis-design.md`](docs/specs/2026-06-16-amazon-advertise-analysis-design.md) |
| 查看调研报告 | [`docs/research/2026-06-16-amazon-advertising-analysis-research.md`](docs/research/2026-06-16-amazon-advertising-analysis-research.md) |
| 查看路线图 + 下一步 | [`docs/roadmap.md`](docs/roadmap.md) |
| 查看变更历史 | [`docs/log.md`](docs/log.md) |
| 文档总索引 | [`docs/index.md`](docs/index.md) |

## 核心发现 (v0.2)

总花费 $3,483 → 销售额 $11,513 → ACOS 30.25% → ROAS 3.31x
收割 10 词 ($168→$2,238), 否定 32 词 (省 $498), 观察 504 词 ($1,266)
Top of Search 最优 (ACOS 17.34%), 光环效应 3.77x

## 关键架构决策

- **模块化 > 单脚本**: 7 独立分析 → JSON 中间产物 → nalyze_cross 集成 → uild_full_report Excel
- **双格式自动检测**: Console CSV + API xlsx, column_maps.py 统一映射
- **5 桶分类** (v0.2): Harvest(≥2单) / Negate(≥15点击) / Monitor / Protect / Ignore
- **先聚合再分类** (v0.2): GROUP BY search_term 后判断 (修复 Lesson 6)
- **跨报告集成** (v0.5): 混合 ACOS, Gateway ASIN 判定, 账户健康度评分
- **阈值集中管理**: 	hresholds.py + config/bjryecltd-us.json, calibrate_thresholds.py 自动标定

## 当前工具

**优麦云** (在用) — ERP+广告管理, 无 API 但 Excel 导出, 保存全量历史数据
**卖家精灵** MCP — 竞品关键词情报 (按需, `open.sellersprite.com/mcp/22`)

## 当前局限 (v0.5 剩余 6 项)

1. 缺 Business Understanding (盈亏平衡点未知)
2. 无环比/同比
3. 无行业基准 (家居类目平均 ACOS 32.5%)
4. 数据源不全 (4 种 SP 报告已接入；经 2026-06-30 官方文档校验，Console 可导出 10 种，API 可获取 6-7 种，详见 data-sources.md)
5. 无竞争情报
6. 只看 ACoS 不看 TACoS/NTB%/LTV
7. 无多触点归因

详见 [roadmap.md → 立即可执行](docs/roadmap.md)
