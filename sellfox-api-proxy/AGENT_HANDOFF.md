# sellfox-api-proxy — Agent Handoff

> **给接手 Agent 的第一句话**：赛狐 API 代理网关已部署到上海 VPS (`api.vilavi.cn/sellfox/`)，v0.4.3 生产可用。支持钉钉 OIDC 登录、自动配给 Key、多 Account、全局限速、Key 加密存储、离职自动封号、冒烟测试全覆盖。代码 ~1,500 行 (Python + JS + HTML)。

## 快速理解

**问题**：赛狐 API (openapi.sellfox.com) 要求 IP 白名单 + 只支持 5 个 API 账号。团队的 IP 不固定（家里/办公室/联通动态 IP），App ID/Secret 不能直接分发给同事。

**方案**：在 VPS（固定 IP 82.156.238.248）上部署一个 API 代理网关，持有赛狐真实凭证，对外给每个同事发放独立 API Key。借鉴 Kong 插件阶段模型，用声明式 YAML 配置 Provider。

**进度**：v0.4.3 已完成 — 核心功能全部实现并测试通过，包括离职封号集成和冒烟测试。

## 文档导航

| 你需要… | 读这个 |
|----------|--------|
| 了解为什么要做这个项目 | [docs/research/2026-07-07-problem-background.md](docs/research/2026-07-07-problem-background.md) |
| 看所有现成方案的调研（NyaProxy/Kong/等） | [docs/research/2026-07-07-existing-solutions-survey.md](docs/research/2026-07-07-existing-solutions-survey.md) |
| 理解通用 API 网关分析（Gateon/Bifrost/ShenYu/等） | [docs/research/2026-07-08-api-gateway-deep-dive.md](docs/research/2026-07-08-api-gateway-deep-dive.md) |
| 深入理解 Kong 架构分析 | [docs/research/2026-07-08-kong-architecture-analysis.md](docs/research/2026-07-08-kong-architecture-analysis.md) |
| 看对话过程完整摘要 | [docs/research/2026-07-07-conversation-evolution.md](docs/research/2026-07-07-conversation-evolution.md) |
| 看完整经验教训（17 条） | [docs/lessons/2026-07-09-full-architecture-evolution.md](docs/lessons/2026-07-09-full-architecture-evolution.md) |
| 运行冒烟测试 | `ADMIN_API_KEY=xxx python smoke_test.py [--local]` |
| 了解离职封号机制 | `new-api-deployment/offboarding-check.py` + `new-api-dingtalk-oidc/stream_listener.py` |
| 看所有文档索引 | [docs/index.md](docs/index.md) |

## 关键架构决策

1. **自研替代 Fork**：NyaProxy 有 query 参数丢失 Bug 且无插件系统，Fork 需要理解 3,350 行再改 ~90 行。自研 ~500 行，架构更清晰。

2. **借鉴 Kong 不照搬 Kong**：Kong 太重（15 万行 Lua、需 PostgreSQL 或受限的 DB-less 模式）。取其插件阶段模型 + 声明式配置思想，用 Python 实现。

3. **声明式配置 + SQLite 双层存储**：静态配置（providers/plugins）放 YAML，动态数据（API Keys）放 SQLite。避免 Kong DB-less"改 Key 要 reload"的痛点。

4. **策略模式支持多 Provider**：认证策略（static_key / oauth2_cc / custom）+ 签名策略（noop / sellfox_hmac / md5_sign / custom）。加新 API = 加 YAML + 可选加 ~40 行插件。

5. **复用钉钉 OIDC 身份体系**：不重建登录系统，通过已有的 `new-api-dingtalk-oidc` 桥实现 OIDC 登录。API Key 绑定 `dingtalk_union_id`，离职时 `offboarding-check.py`（每日 cron）+ `stream_listener.py`（实时 Stream）双通道自动封号。

6. **冒烟测试覆盖**：`smoke_test.py`（290 行，纯 stdlib，9 条用例）覆盖 health/auth/CRUD/proxy/rate-limit，支持 `--local`（VPS 本地）和远程（公网 nginx）双模式。

## 关键代码参考

| 来源 | 复用内容 |
|------|----------|
| `SELLFOX_API/fetch_ad_reports.py:55-69` | HMAC-SHA256 签名（生产验证） |
| `SELLFOX_API/fetch_ad_reports.py:97-108` | OAuth2 token 获取 |
| `SELLFOX_API/docs/lessons/2026-06-25-sellfox-integration-lessons.md` | 16 条踩坑教训 |
| `new-api-dingtalk-oidc/Dockerfile` | Dockerfile 参考模式 |

## 约束

- 部署在已有 VPS (82.156.238.248)，Docker 方式
- Python 技术栈（团队技能匹配）
- 赛狐限流 ~1 rps（全局限流需要处理）
- 赛狐 API 账号仅剩 3 个配额（已有 5 个中用了 2 个）
