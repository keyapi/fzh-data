# SELLFOX_API — Agent 交接说明

> **赛狐 OpenAPI 文档 + 连通性测试**
> **人读文档**: [docs/index.md](docs/index.md)

## 这是什么

赛狐 (Sellfox) 开放平台的 API 文档本地镜像 + 连通性测试脚本。从 Apifox (`sellfoxapi.apifox.cn`) 下载全部 API Markdown 文档，按原始结构组织，方便 Agent 离线查阅和搜索。

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
