# SELLFOX_API — Agent 交接说明

> **赛狐 OpenAPI 文档 + 连通性测试**
> **人读文档**: [docs/index.md](docs/index.md)

## 这是什么

赛狐 (Sellfox) 开放平台的 API 文档本地镜像 + 连通性测试脚本。从 Apifox (`sellfoxapi.apifox.cn`) 下载全部 API Markdown 文档，按原始结构组织，方便 Agent 离线查阅和搜索。

**组合商品/EN 套件**不走文档下载脚本，走 `sellfox_combo_ops.py` + Skill `sellfox-combo-create`。分层见下文 **「EN 套件 / 赛狐组合商品（热区）」**；稳定命令/硬规则 → [docs/reference/combo-ops.md](docs/reference/combo-ops.md)。

## EN 套件 / 赛狐组合商品（热区）

> **会变的内容放这里**（冻结对象、读哪、接手顺序）。稳定操作手册 → [combo-ops.md](docs/reference/combo-ops.md)（OKF Reference）。
> A 类同事不读文件；Agent 由 Skill `sellfox-combo-create` 触发后按 Read First 链阅读。

### 接手 30 秒

1. 读 [combo-ops.md](docs/reference/combo-ops.md) — 默认命令、硬规则、停手、代码地图。
2. 读本节 **冻结表**。
3. `cd SELLFOX_API` → dry-run（如 `sync-combos --like "TJ#KSxxxx%"`）→ 把 JSON 计划给用户 → 用户确认范围后 `--apply`。
4. 改脚本后：`uv run pytest tests/sellfox_api/test_combo_reconcile.py -q`。
5. dry-run 出现 `mismatch` / `blocked_*`（含 `blocked_duplicate`）必须停手，不要 `--apply`。

凭证：赛狐代理 Key → 根 `.env` 的 `SELLFOX_PROXY_API_KEY`；EN → `EN_API/.env`。EN `--env` 默认 **prod**。

### 冻结与跳过（2026-08-20）

| 对象 | 类型 | Agent 行为 |
|------|------|------------|
| KS0443 共 12 个 EN Bundle + 12 个赛狐组合（`TJ#KS0443%`） | **日期冻结**（2026-08-19 已重建并回读） | 不要重跑 `sync-combos --like "TJ#KS0443%"` 除非用户明确授权 |
| `FXLSSF3030` | **长期跳过**（历史非 `TJ#` 海绵套件；上层 Item 已 disabled） | 脚本标 `skip_historical`；**不要**按新规则改名/重建，除非用户另行授权 |
| KS0003 / KS0395 | **已关闭**（2026-08-20 用户确认无问题） | 不要纳入清理或审计待办 |

### 读哪（热 → 冷）

| 你需要 | 读这个 |
|--------|--------|
| 默认命令、硬规则、action 表、报告字段、停手、代码地图 | [docs/reference/combo-ops.md](docs/reference/combo-ops.md) |
| **当前冻结对象**（本节，随生产决策更新） | 本节 |
| 配对 API、Proxy 踩坑、KS0443 事故记录 | [sellfox-combo-sku-create-pairing-workflow.md](../docs/solutions/conventions/sellfox-combo-sku-create-pairing-workflow.md) |
| 领域词汇（TJ#、套件#） | 根 [CONCEPTS.md](../CONCEPTS.md) |
| 模块变更历史 | [docs/log.md](docs/log.md) |
| Skill 触发词与三步概要 | `.agents/skills/sellfox-combo-create/SKILL.md` |
| 改脚本、开 PR | [CONTRIBUTING.md](../CONTRIBUTING.md) |

## 快速启动

```bash
# 查看 API 文档
ls docs/api-reference/

# 下载/更新 API 文档
python download_docs.py --all

# 测试 OpenAPI 连通性（需在白名单 IP）
python test_api.py

# 拉取 SP 广告报告 (4 种: Campaign/Targeting/SearchTerm/Placement)
python fetch_ad_reports.py --days 7

# 指定店铺名称拉取
python fetch_ad_reports.py --shop-name "MyStore" --days 30
```

## 凭证

| 项目 | 位置 |
|------|------|
| App ID / Secret | `SELLFOX_API/.env`（优先），`advertise/.env`（备用） |
| API 文档密码 | `.env` 中的 `SELLFOX_API_DOC_KEY` |
| 生产环境 | `https://openapi.sellfox.com/` |
| API 文档 | `https://sellfoxapi.apifox.cn/` |

## 文档地图

| 你需要... | 读这个 |
|----------|--------|
| Agent 接手总览 | 本文件 |
| EN 套件热区（冻结/读哪） | 本文件 **「EN 套件 / 赛狐组合商品（热区）」** |
| EN 套件操作手册（命令/硬规则） | [docs/reference/combo-ops.md](docs/reference/combo-ops.md) |
| EN 套件 Skill 触发词 | `.agents/skills/sellfox-combo-create/SKILL.md` |
| 查找具体 API 端点 | `docs/api-reference/` 下按模块浏览 |
| 了解 API 接入过程 + 踩坑 | [docs/lessons/2026-06-25-sellfox-integration-lessons.md](docs/lessons/2026-06-25-sellfox-integration-lessons.md) |
| 了解探索历史 + 架构发现 | [docs/research/2026-06-25-sellfox-api-exploration.md](docs/research/2026-06-25-sellfox-api-exploration.md) |
| 查看 API 文档全文索引 | [docs/api-reference/llms.txt](docs/api-reference/llms.txt) |
| 查看变更记录 | [docs/log.md](docs/log.md) |

## API 模块速查 (419 个端点)

| 模块 | 端点数 | 目录 |
|------|--------|------|
| 商品 | 16 | `docs/api-reference/商品/` |
| 销售 | 8 | `docs/api-reference/销售/` |
| 订单 | 9 | `docs/api-reference/订单/` |
| 广告 | 37 | `docs/api-reference/广告/` |
| FBA | 44 | `docs/api-reference/FBA/` |
| 采购 | 25 | `docs/api-reference/采购/` |
| 仓库 | 46 | `docs/api-reference/仓库/` |
| 数据 | 18 | `docs/api-reference/数据/` |
| 财务 | 68 | `docs/api-reference/财务/` |
| 多平台 | 115 | `docs/api-reference/多平台/` |
| 报告中心 | 10 | `docs/api-reference/报告中心/` |
| Feed | 3 | `docs/api-reference/Feed/` |
| 客服 | 1 | `docs/api-reference/客服/` |
| 工具 | 1 | `docs/api-reference/工具/` |
| 设置 | 4 | `docs/api-reference/设置/` |
| 开发指南 | 14 | `docs/api-reference/开发指南/` |

## 关键架构决策

- **OAuth 2.0 client_credentials**: Token 端点 `/api/oauth/v2/token.json`，唯一不受 IP 白名单限制的端点
- **IP 白名单**: 所有业务端点受服务端 IP 白名单保护（北京办公室 + VPS）
- **响应格式**: `{code: 0, msg: "success", data: {...}, requestId: "..."}`
- **文档源**: Apifox 共享项目，需密码访问，通过浏览器 cookie 认证

## Agent 首次接手检查清单

1. 确认要查的 API 属于哪个模块
2. 进入 `docs/api-reference/<模块>/` 找对应 `.md` 文件
3. 文档内包含 OpenAPI YAML spec（请求参数、返回格式）
4. 如需更新文档: `python download_docs.py --all`

## Selenium 脚本

`SPS_Selenium_Local/` 下有独立的 Selenium 自动化脚本（ERP Web 端登录 + 多属性商品设置），属于不同项目，见该目录。
