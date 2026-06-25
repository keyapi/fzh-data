# AGENT_HANDOFF.md — Amazon 广告数据分析模块

> **入口文件** — Agent 接手时先读这个。需要细节时按链接深入。
>
> 版本: v0.3 | 分支: amazon_advertise | 更新: 2026-06-25

## 这是什么

从 Amazon 广告数据 → AI 驱动的分析 + 决策系统。当前 v0.3 阶段：完成 83 次行业调研 + 多账号安全评估 + 赛狐 API 接入准备。下一步：验证赛狐 API 广告读写能力，构建数据管道。

## 当前状态（2026-06-25）

### 已完成
- ✅ **行业全景调研**: 83 次搜索 × 6 维度，全部写入 OKF 文档（60+ 来源 URL）
- ✅ **多账号安全调研**: 确认 SP-API 多账号管理是官方支持的安全模式（风险 2/10）
- ✅ **赛狐 API 认证成功**: OAuth 2.0 client_credentials，获得 access_token（24h 有效）
- ✅ **赛狐 API 凭证已保存**: `.env` + `config_sellfox.json`
- ✅ **30+ OKF 文档**: 完整的研究、参考、经验教训、路线图

### 待完成（下一步）
- ⚠️ **赛狐 API 端点验证**: 需从白名单 IP (123.117.236.65) 运行 `test_sellfox_api.py`
- ⚠️ **广告读写能力确认**: 赛狐 API 是否支持 campaign 创建/修改/出价调整？
- ⚠️ **数据管道建设**: API → SQLite，替代手动 CSV 导出
- ⚠️ **决策日志实现**: 每次分析结果持久化，可追溯

## 关键凭证

| 项目 | 位置 |
|------|------|
| 赛狐 API 凭证 | `advertise/.env` (SELLFOX_APP_ID=368618) |
| 赛狐 API 配置 | `advertise/config_sellfox.json` |
| API 文档 | https://sellfoxapi.apifox.cn/ (密码: VZKGdd0Q) |
| API 生产环境 | https://openapi.sellfox.com/ |
| Token 端点 | GET `/api/oauth/v2/token.json` (client_credentials) |

## 文档地图（渐进式加载）

### 快速上手

| 你需要... | 读这个 |
|----------|--------|
| 了解怎么运行脚本 | [`README.md`](README.md) |
| **了解当前全部上下文（最重要）** | **本文档（AGENT_HANDOFF.md）** |
| 查看 API 认证流程 + 踩坑记录 | [`docs/lessons/2026-06-25-sellfox-integration-lessons.md`](docs/lessons/2026-06-25-sellfox-integration-lessons.md) |
| 测试赛狐 API 连通性 | `python test_sellfox_api.py`（需从白名单 IP） |

### 行业调研 (2026-06-24)

| 主题 | 文档 |
|------|------|
| 全景报告 (83搜索×6维度) | [`docs/research/2026-06-24-industry-landscape.md`](docs/research/2026-06-24-industry-landscape.md) |
| 策略框架 (ACoS→TACoS, COSMO, 归因) | [`docs/reference/2026-strategy-frameworks.md`](docs/reference/2026-strategy-frameworks.md) |
| AI/ML 技术栈 (MCP, LLM, RL, Agent) | [`docs/reference/2026-ai-ml-landscape.md`](docs/reference/2026-ai-ml-landscape.md) |
| 工具对比 (SaaS, 开源, MCP生态) | [`docs/reference/2026-tools-comparison.md`](docs/reference/2026-tools-comparison.md) |
| API/数据生态 (Ads API, AMC, 管道) | [`docs/reference/2026-api-data-ecosystem.md`](docs/reference/2026-api-data-ecosystem.md) |
| 系统架构 (多Agent, UX, 规则引擎) | [`docs/reference/2026-system-architecture.md`](docs/reference/2026-system-architecture.md) |
| 市场情报 (零售媒体, CPC通胀, 竞争) | [`docs/reference/2026-market-intelligence.md`](docs/reference/2026-market-intelligence.md) |
| 已验证来源 (8 个来源 WebFetch 验证) | [`docs/reference/verified-sources.md`](docs/reference/verified-sources.md) |
| 10 大关键洞察 | [`docs/lessons/2026-06-24-research-insights.md`](docs/lessons/2026-06-24-research-insights.md) |

### 安全调研 (2026-06-24)

| 主题 | 文档 |
|------|------|
| 多账号防关联 (137+检测信号, 浏览器vs API) | [`docs/reference/2026-security-multi-account.md`](docs/reference/2026-security-multi-account.md) |
| SP-API 开发者模型 (私人vs公共, SPN认证) | [`docs/reference/2026-sp-api-developer-model.md`](docs/reference/2026-sp-api-developer-model.md) |
| 赛狐 API 实践指南 (接入+MCP评估) | [`docs/reference/2026-sellfox-api-guide.md`](docs/reference/2026-sellfox-api-guide.md) |

### 经验教训

| 主题 | 文档 |
|------|------|
| v0.1-v0.3 12条开发教训 | [`docs/lessons/lessons-learned.md`](docs/lessons/lessons-learned.md) |
| **赛狐 API 接入踩坑记录** | [`docs/lessons/2026-06-25-sellfox-integration-lessons.md`](docs/lessons/2026-06-25-sellfox-integration-lessons.md) |

### 规划与路线

| 主题 | 文档 |
|------|------|
| 路线图 + Phase 4 优先级 | [`docs/roadmap.md`](docs/roadmap.md) |
| 最终可执行方向 (含安全修正) | [`C:\Users\zhang\.claude\plans\amazon-parsed-finch.md`](../../../plans/amazon-parsed-finch.md) |

## 核心架构决策

1. **赛狐 OpenAPI 作为数据源**（非直接 Amazon Ads API）— 多账号安全 + SPN 认证
2. **MCP Server 作为 AI 集成层** — Claude 可通过 Sellfox MCP 自然语言查询
3. **分析先行，自动化后续** — 先确认赛狐 API 写能力再决定自动化执行
4. **OKF v0.1 渐进式文档** — 入口(本文件) → reference/ → research/ → lessons/
5. **SQLite → FastAPI + React + ECharts** — 2-5 人小团队 Web Dashboard

## 关键风险

1. **赛狐 API 写能力未知** — 广告创建/修改/出价调整是否支持？需验证
2. **赛狐 API 端点数有限** — 60-70 vs 领星 373+ vs 直接 SP-API 完整
3. **IP 白名单限制** — 当前代理 IP 无法调用 API，需从白名单 IP 操作
4. **Apifox 文档不完整** — 公开共享项目只含开发指南，API 参考文档需展开侧栏
5. **Sellfox MCP 是第三方项目** — shuolol/sellfox-mcp（2星7提交），不建议作核心依赖

## 项目文件结构

```
advertise/
├── AGENT_HANDOFF.md           ← 你在这里
├── .env                        ← 赛狐 API 凭证 (gitignored)
├── config_sellfox.json         ← 赛狐 API 配置
├── test_sellfox_api.py         ← API 连通性测试脚本
├── sellfox_openapi.json        ← OpenAPI 文档 (运行测试脚本后生成)
├── README.md
├── __init__.py                 ← v0.3 数据加载 (CSV 清洗 + 列映射)
├── analyze_campaign.py         ← v0.3 campaign 分析
├── analyze_targeting.py        ← v0.3 targeting 分析
├── analyze_search_term.py      ← v0.3 搜索词分析 (聚合+5桶)
├── analyze_placement.py        ← v0.3 placement 分析
├── build_report.py             ← v0.3 Excel 报告生成
├── 数据源/                     ← CSV/XLSX 数据文件 (gitignored)
└── docs/                       ← OKF v0.1 bundle (30+ 文档)
    ├── index.md
    ├── log.md
    ├── roadmap.md
    ├── reference/ (17 文件)
    ├── research/ (3 文件)
    ├── lessons/ (4 文件)
    └── specs/ (2 文件)
```
