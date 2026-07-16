---
okf: v0.1
type: Research
title: 赛狐尾程打单系统 — 完整调研文档
description: 2026-07-15 的完整调研过程、来源、排除方案与早期架构结论
module: sellfox_shipping
created: 2026-07-15
updated: 2026-07-16
status: complete
---

# 赛狐尾程打单系统 — 完整调研文档

> 本文档记录 2026-07-15 执行的完整调研过程，含调研方法、每条搜索的出发点、关键发现、排除方案及原因、架构借鉴来源对照、所有原始 URL。
> 可供其他 AI Agent 独立评估调研质量和规划合理性。

---

## 1. 调研动机与目标

### 1.1 业务需求

FZH 跨境电商（家居纺织品：PP棉/海绵填充靠枕、沙发）正在将 OMS 从通途迁移到赛狐。当前尾程打单流程：

```
赛狐/通途订单 → 部分尾程有 API 直接对接
              → 部分尾程需 Excel 导出 → Google Colab 脚本转格式 → 人工上传物流商后台
              → 部分平台（Wayfair）直接提供打单标签
              → 部分平台（Pottery Barn）通过 EDI
```

### 1.2 五点关键约束

1. 使用**自有尾程物流商**，不通过第三方打单平台（Easypost/ShipStation 等是参考开源架构）
2. Excel 兜底只需**按物流商表头改格式**，用户自己上传物流商后台，系统不做自动上传
3. CSV polling（DPD/DHL 扫码吐 CSV）先记录方案，暂不开发
4. 同事分布**中国 + 海外分公司**，需中英文支持
5. 需同时面向**人类用户（Web UI）和 AI Agent（MCP + CLI）**

---

## 2. 调研方法

### 2.1 四阶段递进

```
Phase 1 (1 agent)  → 公司上下文：AGENTS.md, company-context.md, CONCEPTS.md, SELLFOX_API 文档
Phase 2 (3 agents parallel) → 行业全景：ERPNext shipping, 打单平台, 承运人 API, 中国聚合, 平台打单
Phase 3 (2 agents parallel) → 深度专题：Plentymarkets, 规则引擎, 标签打印, 物流商, AI Agent 设计, 参考实现
Phase 4 (orchestrator) → 架构综合：整合所有发现, 用户反馈迭代, 最终方案
```

### 2.2 搜索工具

- **tavily-search**: AI 优化网页搜索（1000 次/月免费配额）
- **tavily-extract**: 深度提取指定 URL 内容
- **WebSearch**: Claude 自带搜索
- **WebFetch**: Claude 自带网页抓取
- **GitHub 直接访问**: 读取 Karrio、EasyPost、verbb/shippy、fastmcp、typer 等仓库源码

### 2.3 论文参考

- arxiv 2606.30317 — MCP Server Architecture Patterns
- arxiv 2602.14878 — MCP Tool Descriptions
- NSA MCP Security Guidance (May 2026)

---

## 3. 调研发现（按主题）

### 3.1 ERPNext Shipping 生态

**出发点**：用户提到 erpnext-shipping app 可能提供参考。

**调研结果**：
- 官方 erpnext-shipping 仅支持 3 个欧洲聚合商（LetMeShip, Packlink, SendCloud），无中国/美国承运人
- 社区 EasyPost fork (volkswagner/erpnext-shipping) 增加了 US 承运人支持但未合入主线
- 商业 app：Kanak FedEx Connector、ECOSIRE Logistics（付费）
- GitHub issue #89 (March 2026) 询问 v16 支持状态
- **排除原因**：不支持中国始发、不支持中国承运人、维护度低、缺少关键功能（海关申报、中国地址格式）

**来源**：
- https://github.com/frappe/erpnext-shipping
- https://docs.erpnext.com/erpnext-shipping
- https://github.com/volkswagner/erpnext-shipping
- https://discuss.frappe.io/t/are-shipping-integrations-working-in-united-states/107796

### 3.2 商业打单平台

**出发点**：调研业界领先的多承运人打单平台，研究其架构设计和 API 模式。**不是**要使用其服务，而是借鉴其开源 SDK 的代码组织方式。

| 维度 | EasyPost | Shippo | Easyship | ShipStation |
|------|----------|--------|----------|-------------|
| 承运人 | 100+ | 40-90+ | 250-550+ | 100+ |
| API | 最好 | 免费层有 API | 全计划有 API | **$99+/月才有 API** |
| 定价 | 按标签 | $0.05-0.07/标签 | 免费 50 单/月 | $14.99-349.99/月 |
| 国际 | 有 | 部分 | **最强**（DDP/关税计算） | US-origin 为主 |
| Excel | 有 | 有（列映射记忆） | 有 | 有 |
| **我们借鉴什么** | Python SDK service-registry 模式 | API 文档设计 | 跨境关税处理模式 | — |

**排除原因**：用户明确表示使用自有物流商资源，不通过第三方平台打单。借鉴仅限于开源 SDK 架构设计。

**来源**：
- https://kuajingbase.com/en/tools-review/logistics
- https://www.ringly.io/blog/ecommerce-shipping-software
- https://apiscout.dev/guides/shippo-vs-easypost-vs-shipstation-shipping-api-2026
- https://www.4seller.com/blog/en/article/197-ShipStation-s-API-Price-Jumps-10x

### 3.3 承运人 API

**出发点**：调研各尾程物流商的 API 能力和接入复杂度。

| 承运人 | API 现状 | 认证方式 | 标签格式 | 复杂度 |
|--------|---------|---------|---------|--------|
| FedEx | REST only (SOAP 退役) | OAuth 2.0 + MFA | PDF/PNG/ZPL | 中等 |
| UPS | REST APIs | OAuth 2.0 | base64 JSON | 中等 |
| USPS | 新 API v3.0 (2026-01) | OAuth 2.0 | — | 仅 US 境内 |
| DHL Express | MyDHL API 统一 | — | PDF/PNG | 中等 |
| DHL eCommerce | 分区域 API | — | PDF/PNG/ZPL | 中等 |
| GLS | REST Shipping API | API Key | — | 中等 |
| YunExpress | 最好中文 API 文档 | Token | — | 低 |
| 4PX | 成熟 API | Token | — | 低 |
| Yanwen | 公开 REST API | — | — | 中（费率需联系销售） |
| WINIT | 海外仓 + 直发 | — | — | 中等 |

**来源**：
- https://developer.fedex.com
- https://developer.ups.com
- https://developers.usps.com
- https://developer.dhl.com
- https://gls-group.com
- https://open.yunexpress.cn
- http://open.4px.com
- https://opendocs.yw56.com.cn
- http://developer.winit.com.cn

### 3.4 中国物流聚合

**出发点**：研究中国市场的物流 API 聚合方案，作为 API 设计参考。

- **快递鸟 (KDNiao)**：2500+ 物流商单 API，电子面单+轨迹+取件
- **菜鸟 (Cainiao)**：淘宝/天猫生态必需，三方授权流程复杂
- **快递100**：多平台电子面单集成

**来源**：
- https://www.kdniao.com
- https://api.kuaidi100.com
- https://cloud.cainiao.com

### 3.5 开源多承运人方案

**出发点**：寻找可直接使用或借鉴的开源方案。

| 项目 | 语言 | 状态 | 借鉴价值 |
|------|------|------|---------|
| **Karrio** | Python/Django | 活跃 (v2026.1.32, 30+ carriers) | ⭐⭐⭐⭐⭐ 核心借鉴 |
| **verbb/shippy** | PHP | 早期 (16 stars) | ⭐⭐ 事件钩子模式 |
| **PurplShip** (Karrio 前身) | Python | 已演进为 Karrio | — |
| **Delivery.NET** | .NET | 小项目 | ⭐ 不适用 |

**Karrio 架构分析**（最重要参考）：
```
modules/sdk/karrio/
├── api/gateway.py       # Gateway 类 — 承运人连接包装
├── api/interface.py     # 流畅接口: Rating, Shipment, Tracking
├── api/proxy.py         # AbstractProxy — 统一承运人 API 定义
└── api/mapper.py        # 统一模型 ↔ 承运人请求/响应映射

modules/connectors/fedex/karrio/providers/fedex/
├── __init__.py           # exports: Settings, Proxy
├── rate.py               # rate_request(), parse_rate_response()
├── shipment.py           # shipment_request(), parse_shipment_response()
└── tracking.py           # tracking_request(), parse_tracking_response()
```

**EasyPost Python SDK 架构分析**：
```
easypost/
├── easypost_client.py   # Client-as-service-registry
├── services/base_service.py  # CRUD 模板
├── services/shipment_service.py
├── hooks/               # 请求/响应中间件
└── models/              # 数据类
```

**来源**：
- https://github.com/karrioapi/karrio (详细文件路径见上)
- https://github.com/EasyPost/easypost-python
- https://github.com/verbb/shippy
- https://github.com/kevinvenclovas/ShippingProAPICollection

### 3.6 Plentymarkets/PlentyOne

**出发点**：用户之前在德国用 Plentymarkets，了解其物流模式和 CSV polling。

**关键发现**：
1. **三层物流架构**：Service Provider（承运人插件） → Shipping Profile（配送方式映射到商品） → Shipping Package（包裹尺寸/重量）
2. **CSV Polling 模式**：订单导出 CSV → 共享目录/FTP → 物流软件轮询 → 处理结果 CSV 导入
3. **"Flexible Shipping Logic"插件**：COM.Create GmbH 第三方，自动按尺寸/重量/目的国选承运人
4. **插件架构**：PHP 插件框架，`plugin.json` + `ServiceProvider` + `ShippingController`

**来源**：
- https://developers.plentymarkets.com/en-gb/developers/main/shipping-plugins
- https://knowledge.plentyone.com/en-gb/manual/main/fulfilment/preparing-the-shipment.html
- https://github.com/plentymarkets/plugin-shipping-tutorial
- https://github.com/findologic/plentymarkets-rest-exporter

### 3.7 平台打单（Wayfair/Overstock/Pottery Barn）

**出发点**：公司销售涉及这三个平台，打单方式各不相同。

| 平台 | 打单方 | 标签来源 | 集成复杂度 | 方案 |
|------|--------|---------|-----------|------|
| Wayfair | 平台 | Partner Home API 获取 Wayfair 议价标签 | 中等 | P5 实现 |
| Overstock | 卖家 | 用自建 FedEx 打完标签，追踪号通过 Supplier Oasis API 回写 | 中等 | P5 实现 |
| Pottery Barn | 卖家 | EDI ANSI X12 856（ASN）+ 850（PO）+ 810（Invoice） | **高** | **延期**，先手工 |

**来源**：
- https://sell.wayfair.com
- https://developers.overstock.com
- https://blog.jaychrisedi.com/blog/williams-sonoma-edi-vendor-guide
- https://www.spscommerce.com/community/articles/wayfair-order-management-and-shipping-policies

### 3.8 规则引擎

**出发点**：需要自动根据订单的目的国/州省/重量/体积选择最优承运人。

**调研发现**：
- **行业主流**：条件-动作表单构建器。ShipStation、Easyship、赛狐通途都采用。用户不需要写代码，下拉框选条件
- **Plentymarkets "Flexible Shipping Logic"**：自动按尺寸/重量/目的国选承运人。$299/月
- **GoRules ZEN Engine**：MIT 开源（Rust 实现，Python 绑定），决策表 + 决策图。但文档和社区偏小
- **Python business-rules**：简单的 JSON 规则引擎，维护度低（上次更新 2021）

**推荐演进路径**：
```
P3 MVP:  YAML/JSON 配置 → 技术人员用 IDE 维护
P5 增强:  Web UI 条件构建器 → 物流同事自助
远期:    AI Agent 辅助 → 基于历史数据推荐规则
```

**来源**：
- https://github.com/gorules/zen
- https://rulebricks.com/blog/rule-engines-for-fulfillment
- https://www.shipium.com/platform/rules-engine

### 3.9 标签打印

**出发点**：需要生成承运人兼容的运单标签格式。

| 格式 | 适用场景 | 说明 |
|------|---------|------|
| **ZPL** | Zebra 热敏打印机 | 原生格式，最高质量，TCP:9100 直发 |
| **PDF 4x6"** | 通用热敏打印机 | 812x1218px @ 203dpi，兜底方案 |
| **PNG** | Web UI 预览 | Labelary API ZPL→PNG 在线转换 |

**Python 库**：
- `zebra_day`：完整 Zebra 打印机管理（FastAPI GUI + 标签模板 + 打印队列）
- `zebrafy`：PDF/图片 → ZPL 转换
- `zplgrf`：ZPL/GRF/PDF/图片互转
- `Pillow` + `ReportLab`：PDF 标签生成

**来源**：
- https://labelary.com/zpl.html + https://labelary.com/service.html
- https://github.com/Daylily-Informatics/zebra_day
- https://github.com/miikanissi/zebrafy
- https://github.com/kylemacfarlane/zplgrf

### 3.10 AI Agent 友好设计

**出发点**：用户明确要求新系统需要"面向 AI Agent 的便利操作性"。

**MCP 协议**：
- 2024 年 11 月 Anthropic 发布，2025 年 12 月捐给 Linux Foundation
- 与 OpenAI、Block 共同创立 Agentic AI Foundation
- 97M+ 月下载，10,000+ 活跃 MCP server
- JSON-RPC 2.0 协议：Tools（Agent 调用）+ Resources（上下文）+ Prompts（模板）
- 传输：stdio（本地首选，安全）+ Streamable HTTP（远程）+ WebSocket

**FastMCP**：
- 26,100 GitHub stars，PrefectHQ（全职工程团队，非个人项目）
- v3.0 2026 年 2 月 GA，当前 v3.x 稳定
- 生产案例：Fiverr（188 tools）、GetYourGuide、Dash0、Cloudsmith
- 约 70% 的 MCP server 使用 FastMCP
- FastAPI ASGI mounting：`app.mount("/mcp", mcp.asgi_app())`
- 风险：MCP 协议快速演进（2026-07-28 重大 RC）、v1→v3 不到一年

**Typer CLI**：
- 19,700 stars，tiangolo（FastAPI 作者），v0.26.8（2026-06），MIT
- 风格与 FastAPI 完全一致（类型提示驱动）
- Agent 友好：`--json` flag、`sys.stdout.isatty()` 自动切换输出模式、Rich 集成

**CLI vs MCP 权衡**：
- 有开发者报告 CLI 比 MCP 节省约 40% token（简单操作用 CLI，复杂工作流用 MCP）
- 最佳策略：**两者都提供**

**来源**：
- https://modelcontextprotocol.io/specification/2025-11-25
- https://github.com/jlowin/fastmcp
- https://github.com/fastapi/typer
- https://gofastmcp.com/integrations/fastapi
- https://www.anthropic.com/engineering/writing-tools-for-agents
- https://dev.to/uenyioha/writing-cli-tools-that-ai-agents-actually-want-to-use-39no
- arxiv 2606.30317, arxiv 2602.14878
- https://www.nsa.gov/Portals/75/documents/Cybersecurity/CSI_MCP_SECURITY.pdf

### 3.11 物流商信息

| 物流商 | 类型 | 区域 | 集成方式 | 确认状态 |
|--------|------|------|---------|---------|
| FedEx | 官方 | US | REST API + OAuth 2.0 + MFA | ✅ 确认 |
| Vite/亿龙达 | 第三方 | US | 自研 WMS，可能有 API（上月和赛狐谈对接）。保留 Excel 模板 | ✅ 确认 |
| 蜥蜴集团/蜴国际 | 第三方 | US | Walmart/TEMU/Target 认证，洛杉矶 | ⚠️ 物流同事也不确定 |
| GLS | 官方 | EU/PL | REST Shipping API | ✅ 确认 |
| 七条 | 未知 | 未知 | 老板找的 | ❌ 网上未搜到 |

**来源**：
- https://www.viteusa.com (VITE USA，2008 年成立于 Boston)
- https://www.vitedirect.com (亿龙达，深圳子公司 2018 年)
- https://m.amz123.com/xyjt (蜥蜴集团，2020 年成立，洛杉矶)
- https://www.chineseinla.com/company/task_view/id_93251/蜥蜴货运集团公司.html

---

## 4. 架构决策记录

### 4.1 决策 1：独立 Python 服务（先独立，后期可移植 ERPNext）

**选项**：
- A. 纯 CLI 工具
- B. 独立 Web 服务（FastAPI）
- C. ERPNext Custom App

**选择 B（独立 Web 服务），架构预留 ERPNext 移植可能性。**

**理由**：
- 项目所有子模块都是独立服务/CLI，无 ERPNext app 先例
- 订单源为赛狐，不依赖 ERPNext doctype
- 复用已有 sellfox-api-proxy（所有赛狐 API 通过 proxy）
- 核心 Service Layer 纯 Python 与框架无关 → 后期移植只需换 FastAPI 层为 Frappe doctype

### 4.2 决策 2：三界面架构（FastAPI + FastMCP + Typer CLI）

**选项**：
- A. 仅 Web UI
- B. 仅 CLI
- C. Web UI + CLI
- D. Web UI + CLI + MCP

**选择 D（三界面）**

**理由**：
- Web UI：人类物流同事日常操作
- MCP Tools：AI Agent 调用（如 Claude/Codex 直接查询订单、创建标签）
- CLI：技术人员脚本调用 + Agent 批量操作
- 三个界面共享同一个 Service Layer，不重复实现业务逻辑
- FastMCP 和 Typer 都是成熟生产级框架

### 4.3 决策 3：承运人抽象层 — Karrio Proxy + Provider 模式

**选项**：
- A. 每个承运人独立函数（无抽象）
- B. 简单 ABC 接口
- C. Karrio 风格 Proxy + Provider

**选择 C（Karrio 风格）**

**理由**：
- Karrio 已通过 30+ 承运人验证此模式可行
- 统一模型 → Mapper → 承运人请求管道确保新承运人可插拔
- 每个承运人是独立 Python 包，互不影响
- 代码组织清晰：Settings → Proxy → Mapper 三层

### 4.4 决策 4：Service Registry — EasyPost 模式

**选项**：
- A. 直接 import 承运人类
- B. 简单 dict 注册
- C. Client-as-Service-Registry

**选择 C（EasyPost 模式）**

**理由**：
- `client.carriers["fedex"]` 比 `import fedex; fedex.create()` 更可发现
- BaseService CRUD 模板减少样板代码
- 延迟加载（只在首次访问时初始化承运人）

### 4.5 决策 5：规则引擎 — 从 YAML 开始

**选择 YAML 决策表 → Web UI 构建器 → AI 辅助（三阶段演进）**

**理由**：
- 5-10 个承运人规模不需要完整 BRE
- YAML 配置技术人员即可维护，不需要 UI 开发
- 后期可加 Web UI 供物流同事自助维护
- 不需要额外依赖（GoRules 等）

### 4.6 决策 6：SQLite 持久化

**选择 SQLite**，理由：轻量、零配置、单文件、足够当前规模。后期可迁移到 PostgreSQL（如移植到 ERPNext）。

---

## 5. 借鉴来源完整对照表

| 架构组件 | 借鉴来源 | 借鉴的具体内容 | 不采用的部分 |
|----------|---------|--------------|-------------|
| **Client-as-Service-Registry** | EasyPost Python SDK (v10.7.0, MIT) | client.orders.fetch(), client.shipments.create() 组织方式、BaseService CRUD 模板、Hooks 中间件 | API 层承运人抽象（EasyPost 在 API 层统一，不适合 per-carrier 模式） |
| **承运人 AbstractProxy + Provider** | Karrio (v2026.1.32, Apache 2.0) | 整个 per-carrier package 模式: Settings → Proxy → Mapper、统一模型管道、流畅接口 `.from_(gateway).parse()` | Django、GraphQL API、完整 Web UI |
| **事件钩子** | verbb/shippy (MIT, PHP) | before/after_fetch_rates、before/after_create_label 钩子模式、allowedServiceCodes 限制、isProduction flag | PHP 实现 |
| **三界面架构** | Frappe/ERPNext | `@frappe.whitelist()` "定义一次暴露到处" 思想 | Frappe Desk 前端 |
| **Shipping Profile 概念** | Plentymarkets/PlentyOne | 三层模型: Service Provider → Shipping Profile → Shipping Package | PlentyOne 插件 API、PHP 实现 |
| **CSV Polling 模式** | Plentymarkets 德国市场实践 | 订单 CSV 导出 → 共享目录/FTP → 物流软件轮询 → 结果导入 | 暂不开发 |
| **MCP 工具设计** | Anthropic + FastMCP 社区 | outcome-oriented tools（不暴露 API 原语）、tool count < 20、@mcp.tool 装饰器 | — |
| **Agent 友好 CLI** | dev.to + speakeasy.com 社区 | --json flag、TTY 检测、无交互提示、幂等命令、--dry-run | — |

---

## 6. P1 实施摘要

P1 创建了以下 22 个文件：

```
sellfox_shipping/
├── __init__.py, main.py, app.py              # 入口
├── models.py                                  # 7 个 Pydantic 模型
├── store.py                                   # SQLite 5 表 + 完整 CRUD
├── config.yaml                                # 仓库/承运人/规则模板
├── sellfox_client.py                          # 赛狐 API 客户端 (通过 proxy)
├── mcp_tools.py                               # 6 个 FastMCP Agent 工具
├── cli.py                                     # 7 个 Typer CLI 命令
├── carriers/{__init__,base}.py                # AbstractCarrier + CarrierRegistry
├── carriers/{fedex,gls,dhl}/__init__.py       # 占位 (P2/P5)
├── templates/{index,orders}.html              # Web UI (Jinja2)
├── Dockerfile, docker-compose.yml             # 部署
├── {README,AGENT_HANDOFF}.md                  # 文档
└── docs/{index,log}.md                        # OKF
```

外部更新：
- pyproject.toml：添加 httpx, pyyaml, jinja2, typer 依赖
- AGENTS.md：模块索引新增 sellfox-shipping
- .agents/skills/sellfox-shipping/SKILL.md：Skill 注册
- index.md：自动重新生成

---

## 7. 全量来源 URL（按主题）

### ERPNext Shipping
- https://github.com/frappe/erpnext-shipping
- https://docs.erpnext.com/erpnext-shipping
- https://github.com/volkswagner/erpnext-shipping
- https://www.kanakinfosystems.com/frappe/apps/16.0/knk_frappe_fedex_connector
- https://ecosire.com/fr/apps/erpnext/shipping-multi-carrier
- https://discuss.frappe.io/t/are-shipping-integrations-working-in-united-states/107796
- https://discuss.frappe.io/t/shipstation-integration/34759

### Shipping Platforms
- https://www.easypost.com / https://github.com/EasyPost/easypost-python
- https://goshippo.com / https://goshippo.com/pricing
- https://www.easyship.com / https://www.easyship.com/developers
- https://www.shipstation.com / https://www.shipstation.com/pricing
- https://www.pirateship.com
- https://kuajingbase.com/en/tools-review/logistics
- https://apiscout.dev/guides/shippo-vs-easypost-vs-shipstation-shipping-api-2026
- https://www.4seller.com/blog/en/article/197-ShipStation-s-API-Price-Jumps-10x
- https://www.teapplix.com
- https://www.aftership.com

### Carrier APIs
- https://developer.fedex.com
- https://developer.ups.com
- https://developers.usps.com
- https://developer.dhl.com (DHL eCommerce + MyDHL API)
- https://docs.api.dhlecs.com
- https://gls-group.com
- https://www.sendcloud.com/carrier-apis/gls-api
- https://synkka.ai/integrations/carriers/gls-germany
- https://www.shippypro.com/en/gls-tracking
- https://open.yunexpress.cn
- http://open.4px.com
- https://opendocs.yw56.com.cn
- http://developer.winit.com.cn

### Chinese Logistics Aggregators
- https://www.kdniao.com
- https://api.kuaidi100.com
- https://cloud.cainiao.com
- https://open.taobao.com

### Reference Implementations
- https://github.com/karrioapi/karrio (all sub-paths analyzed)
- https://github.com/EasyPost/easypost-python (easypost_client.py, services/base_service.py, services/shipment_service.py)
- https://github.com/verbb/shippy (Shippy.php, carriers/AbstractCarrier.php, carriers/CarrierInterface.php)
- https://github.com/plentymarkets/plugin-shipping-tutorial
- https://github.com/findologic/plentymarkets-rest-exporter
- https://github.com/Ryukote/Delivery.NET
- https://github.com/kevinvenclovas/ShippingProAPICollection

### MCP & Agent Design
- https://modelcontextprotocol.io/specification/2025-11-25
- https://github.com/jlowin/fastmcp
- https://gofastmcp.com/integrations/fastapi
- https://www.anthropic.com/engineering/writing-tools-for-agents
- https://www.anthropic.com/engineering/building-effective-agents
- https://www.anthropic.com/engineering/code-execution-with-mcp
- https://dev.to/uenyioha/writing-cli-tools-that-ai-agents-actually-want-to-use-39no
- https://www.speakeasy.com/blog/engineering-agent-friendly-cli
- https://www.openstatus.dev/blog/building-cli-for-human-and-agents
- https://www.infoq.com/articles/ai-agent-cli
- https://digitalgarden.bhekani.com/agent-native-interfaces
- https://workos.com/blog/mcp-vs-rest
- https://atlan.com/know/when-to-use-mcp-vs-api
- https://tallyfy.com/mcp-agents-rest-apis
- https://developer.ibm.com/articles/mcp-architecture-patterns-ai-systems
- arxiv 2606.30317 — MCP Server Architecture Patterns
- arxiv 2602.14878 — MCP Tool Descriptions
- https://www.nsa.gov/Portals/75/documents/Cybersecurity/CSI_MCP_SECURITY.pdf
- https://labs.cloudsecurityalliance.org/agentic/agentic-mcp-security-best-practices-v1

### Typer CLI
- https://github.com/fastapi/typer
- https://typer.tiangolo.com
- https://oneuptime.com/blog/post/2025-07-02-python-cli-click-typer/view

### Rule Engines
- https://github.com/gorules/zen
- https://gorules.io
- https://rulebricks.com/blog/rule-engines-for-fulfillment
- https://www.shipium.com/platform/rules-engine
- https://sellercloud.com/blog/how-an-order-rule-engine-can-save-your-e-commerce-business-time-money

### Label Printing
- https://labelary.com/zpl.html
- https://labelary.com/service.html
- https://pypi.org/project/zpl
- https://github.com/miikanissi/zebrafy
- https://github.com/kylemacfarlane/zplgrf
- https://github.com/Daylily-Informatics/zebra_day
- https://developer.zebra.com/products/printers/zpl
- https://www.servopack.de/support/zebra/ZPLII-Prog.pdf
- https://github.com/EliteScouter/PrintToBTLabel

### Plentymarkets
- https://developers.plentymarkets.com/en-gb/developers/main/shipping-plugins
- https://knowledge.plentyone.com/en-gb/manual/main/fulfilment/preparing-the-shipment.html
- https://marketplace.plentyone.com/en/plugins/fulfillment-stock/shipping
- https://github.com/plentymarkets/plugin-shipping-tutorial
- https://github.com/findologic/plentymarkets-rest-exporter

### Platform Shipping
- https://sell.wayfair.com
- https://www.edi2xml.com/blog/wayfair-edi-api-integration-guide-for-suppliers
- https://www.synctify.net/2024/09/13/wayfair-api-integration
- https://www.spscommerce.com/community/articles/wayfair-order-management-and-shipping-policies
- https://developers.overstock.com
- https://sellersuccess.com/sell-on-overstock
- https://help.shipstation.com/hc/en-us/articles/360027910412-Overstock-com
- https://blog.jaychrisedi.com/blog/williams-sonoma-edi-vendor-guide
- https://www.celigo.com/integrations/williams-sonoma-edi-integrations

### Logistics Companies
- https://www.viteusa.com (VITE USA 亿龙达)
- https://www.vitedirect.com (亿龙达中文站)
- https://m.amz123.com/xyjt (蜥蜴集团/蜴国际)
- https://www.chineseinla.com/company/task_view/id_93251/蜥蜴货运集团公司.html

### Frappe/ERPNext Architecture
- https://docs.frappe.io/framework/user/en/basics/architecture
- https://gavv.in/blog/how-does-frappe-work
- https://www.red-gate.com/simple-talk/development/other-development/frappe-and-erpnext-leveraging-erp-capabilities-for-business-solutions-part-i
