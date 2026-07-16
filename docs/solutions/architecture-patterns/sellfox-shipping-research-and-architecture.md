---
title: "赛狐尾程打单系统 — 完整调研与架构规划"
date: 2026-07-15
category: architecture-patterns
module: sellfox_shipping
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - "新建跨系统数据管道子项目（赛狐 ↔ 物流商）"
  - "设计多承运人打单系统架构"
  - "需要同时支持人类 UI 和 AI Agent 操作的软件"
tags:
  - "sellfox-shipping"
  - "cross-border-ecommerce"
  - "multi-carrier"
  - "label-printing"
  - "mcp"
  - "fastmcp"
  - "three-interface-architecture"
  - "karrio"
related_components:
  - sellfox-api-proxy
  - warehouse_restock
  - EN_API
---

# 赛狐尾程打单系统 — 完整调研与架构规划

## Context

FZH 跨境电商（家居纺织品：PP棉/海绵填充靠枕、沙发）正在将 OMS 从通途迁移到赛狐。当前尾程打单流程碎片化：

- 部分尾程有 API 直接对接（如 FedEx 官方），部分需 Excel 导出 → Google Colab 脚本转格式 → 手动上传到物流商后台（Vite、蜥蜴集团等）
- 涉及尾程：美国 FedEx（官方）、Vite/亿龙达（第三方）、蜥蜴集团/蜴国际（第三方）、欧洲 GLS（波兰）；平台打单：Wayfair 提供标签、Overstock 自打单、Pottery Barn EDI
- 同事分布在中国 + 海外分公司，需中英文支持
- 需要同时面向人类用户（Web UI）和 AI Agent（MCP 工具 + CLI）操作

**目标**：建设统一尾程打单系统，从赛狐获取订单 → 匹配尾程 → 生成运单标签 → 回写追踪号。API 优先，Excel 兜底。使用自有物流商，不通过第三方打单平台。

## Research Methodology

采用四阶段调研，多个 Agent 并行搜索，每步保留原始 URL：

**Phase 1 — 公司上下文**：读取 AGENTS.md、company-context.md、CONCEPTS.md、SELLFOX_API 全部文档，理解业务模型、供应链、三系统 SKU 定义、已有赛狐 API 端点。

**Phase 2 — 行业全景（并行）**：三个 Agent 同时调研：(a) ERPNext shipping 生态 + 商业打单平台对比（ShipStation/Shippo/Easyship/Pirate Ship），(b) 承运人 API（FedEx/UPS/USPS/DHL/GLS）+ 中国物流聚合（YunExpress/4PX/Yanwen/WINIT）+ 开源多承运人方案，(c) 平台打单（Wayfair/Overstock/Pottery Barn）+ 多承运人软件对比。

**Phase 3 — 深度专题（并行）**：两个 Agent 同时调研：(a) Plentymarkets/PlentyOne 物流架构 + 规则引擎（GoRules ZEN）+ 标签打印技术（ZPL/PDF/热敏打印机）+ 物流商信息（Vite/蜥蜴/七条），(b) AI Agent 友好设计模式（MCP/FastMCP/CLI）+ 参考实现架构分析（Karrio/EasyPost SDK/verbb-shippy）+ Web UI 模式 + 部署方案。

**Phase 4 — 架构综合**：基于调研结果设计三界面架构（FastAPI + FastMCP + Typer CLI），借鉴 Karrio 承运人抽象层，参考 EasyPost SDK 服务注册模式，按用户反馈迭代优化方案。

## Research Findings

### 1. ERPNext Shipping 生态

- 官方 erpnext-shipping 仅支持 3 个欧洲聚合商（LetMeShip、Packlink、SendCloud），无中国或美国承运人支持，维护度低
- 社区 EasyPost fork（volkswagner/erpnext-shipping）增加了 US 承运人但未合入主线
- 商业 Frappe apps（Kanak FedEx Connector、ECOSIRE Logistics）可用但需额外购买
- **结论**：不适合作为基础。独立开发，架构上预留后期移植到 ERPNext 的可能性

### 2. 商业打单平台（仅作架构参考，不使用其服务）

| 平台 | 承运人数 | API 定价 | 核心借鉴点 |
|------|---------|---------|-----------|
| EasyPost | 100+ | 按标签付费 | Python SDK service-registry 模式、BaseService CRUD 模板 |
| Shippo | 40+ | 免费层含 API ($0.05/label) | 开发者友好 API 设计 |
| Easyship | 550+ | 免费 50 单/月 | 跨境关税/DDP 处理模式 |
| ShipStation | 100+ | API 需 $99+/月 | 自动化规则 UI 设计 |

来源：kuajingbase.com, ringly.io, goshippo.com, easyship.com, shipstation.com, pirateship.com

### 3. 承运人 API

- **FedEx**：SOAP 2026 年停用，仅 REST API + OAuth 2.0 + MFA。Ship API 生成标签（PDF/PNG/ZPL），Rate API 询价，Track API 追踪。developer.fedex.com
- **UPS**：REST APIs + OAuth 2.0。developer.ups.com
- **USPS**：Web Tools 2026 年 1 月退役，新 API v3.0 + OAuth 2.0。仅适用于美国境内发货
- **DHL**：分多个 API — DHL eCommerce Americas、DHL eCommerce UK、MyDHL API（统一 Rating + Shipment）。developer.dhl.com
- **GLS**：RESTful Shipping API（CreateLabel、ValidateLogin）。支持波兰/德国/欧洲 20 国。可经由 Sendcloud/ShippyPro 聚合
- **中国物流聚合**（仅作 API 设计参考，不更换物流商）：
  - YunExpress：最佳 API 文档（open.yunexpress.cn），220+ 国家，自营货机
  - 4PX：成熟 API（open.4px.com），token 认证
  - Yanwen：公开 REST API（opendocs.yw56.com.cn），费率需联系销售
  - WINIT：海外仓 + 直发（developer.winit.com.cn），eBay Fulfillment 合作

### 4. 核心参考实现

| 参考项目 | 借鉴的具体部分 | 不采用的部分 |
|----------|--------------|-------------|
| **Karrio** (github.com/karrioapi/karrio, v2026.1.32) | 整个 AbstractProxy + Provider per-carrier package 模式、统一模型→Mapper→承运人请求/响应管道、流畅接口 `.from_(gateway).parse()` | Django 框架、GraphQL API、完整 Web UI |
| **EasyPost Python SDK** (v10.7.0) | Client-as-Service-Registry 组织方式（client.shipment.create()）、BaseService CRUD 模板、Hooks 中间件系统 | API 层承运人抽象（不适用我们 per-carrier 模式） |
| **verbb/shippy** (PHP) | before/after 事件钩子模式（fetch rates、create label）、allowedServiceCodes 限制、isProduction flag | PHP 实现 |
| **Frappe/ERPNext** | `@frappe.whitelist()` "定义一次暴露到处" 思想 | Frappe Desk 前端 |
| **Plentymarkets/PlentyOne** | 三层物流模型（Service Provider → Shipping Profile → Shipping Package）、CSV polling 模式 | PlentyOne 插件 API |

### 5. AI Agent 友好设计

**MCP (Model Context Protocol)**：Anthropic 发布，2025 年 12 月捐给 Linux Foundation。97M+ 月下载，所有主流 AI 平台支持。

**FastMCP** (github.com/jlowin/fastmcp)：
- 26,100 GitHub stars，PrefectHQ 公司维护（Jeremiah Lowin, CEO），v3.0 2026 年 2 月 GA
- 生产案例：Fiverr（188 tools）、GetYourGuide、Dash0、Cloudsmith、Versa Networks、Red Hat OpenShift
- FastAPI 集成：ASGI mounting 成熟（app.mount("/mcp", mcp_app)）
- `@mcp.tool` 装饰器与 FastAPI `@app.post` 几乎一样简单
- 风险：MCP 协议仍在快速演进（2026-07-28 重大 RC），FastMCP v1→v3 不到一年

**Typer CLI** (github.com/fastapi/typer)：
- 19,700 stars，tiangolo（FastAPI 作者）维护，v0.26.8（2026-06），MIT 协议
- 类型提示驱动，与 FastAPI 风格完全一致
- Agent 友好特性：--json flag、TTY 自动检测、Rich 集成

**关键设计原则**（来源：Anthropic "Writing effective tools for agents"、arxiv 2606.30317、dev.to 社区实践）：
1. MCP does NOT replace REST — it wraps it（MCP 工具封装 REST API 为面向结果的 Agent 友好操作）
2. Tool count matters：超过 10-15 个工具 Claude Haiku 准确率下降
3. CLI 比 MCP 节省约 40% token（简单操作用 CLI，复杂工作流用 MCP）
4. 反模式："API-primitive trap" — 把原始 REST API 直接暴露为 MCP 工具
5. Agent 友好 CLI：`--json` 一等公民、TTY 检测、无交互提示、幂等命令、`--dry-run`、结构化错误

### 6. 规则引擎

- **行业主流**：条件-动作表单构建器（ShipStation、Easyship、赛狐通途都采用）
- **推荐演进**：YAML 配置文件（MVP）→ Web UI 条件构建器 → AI Agent 辅助建议
- 决策表（Decision Table）优于决策树（物流规则本质是查表逻辑）
- GoRules ZEN Engine（MIT, Rust + Python 绑定）可用但 5-10 个承运人场景下过度设计

### 7. 标签打印

- ZPL：Zebra 热敏打印机原生格式（最高质量），TCP Port 9100 直发
- PDF 4x6"：通用打印机兜底（812x1218px @ 203dpi）
- Labelary API：ZPL → PNG/PDF 在线转换（Web UI 预览）
- Python 库：zebra_day（完整打印管理）、zebrafy（PDF→ZPL）、Pillow、ReportLab

### 8. 平台打单差异

| 平台 | 打单方式 | 集成方案 | 复杂度 |
|------|---------|---------|--------|
| Wayfair | **平台提供标签** | Partner Home API 获取标签 | 中等 |
| Overstock | **卖家自打单** | 用自建 FedEx 打单 + Supplier Oasis API 回写追踪号 | 中等 |
| Pottery Barn | **EDI 传统模式** | ANSI X12 856（850/855/810），需 EDI 能力 | 高，延期 |

### 9. 每单成本追踪

在 labels 表存储 `cost` + `currency` + `carrier` + `service_level`。数据来源：承运人 Rate API 返回的实际 totalNetCharge。ERPNext v13+ Shipment doctype 已有 carrier/awb_number/shipment_amount 字段供将来同步。

### 10. 物流商信息

| 物流商 | 状态 | 备注 |
|--------|------|------|
| FedEx | 官方 API | REST + OAuth 2.0，P2 待实现 |
| Vite/亿龙达 | 第三方，上个月在跟赛狐谈对接 | 自研 WMS，可能有 API。保留 Excel 模板兜底 |
| 蜥蜴集团/蜴国际 | 第三方，物流同事也不确定 | 洛杉矶华人物流公司，Walmart/TEMU/Target 认证 |
| 七条 | 老板找的，待确认 | 网上未搜到，可能是小物流商或昵称 |
| GLS | 官方的 | REST API，P5 实现（波兰仓） |

## Architecture Design

### 三界面一核心架构

```
                    ┌──────────────────────────────────────┐
                    │           Service Layer               │
                    │  (纯 Python，与框架无关，可移植)        │
                    │  ShippingClient (借鉴 EasyPost)       │
                    │  CarrierRegistry (借鉴 Karrio)         │
                    │  RuleEngine (YAML 决策表)               │
                    │  LabelGenerator (ZPL+PDF)              │
                    └────┬──────────┬──────────┬───────────┘
                         │          │          │
              ┌──────────▼──┐ ┌─────▼──────┐ ┌─▼───────────┐
              │  FastAPI     │ │  FastMCP   │ │  Typer CLI   │
              │  REST API    │ │  MCP Tools │ │              │
              │  → Web UI    │ │  → AI Agent│ │  → 人类+Agent │
              └──────────────┘ └────────────┘ └──────────────┘
```

### 承运人抽象层（借鉴 Karrio Proxy + Provider 模式）

```
carriers/
├── base.py              # AbstractProxy — 统一承运人接口
├── models.py            # 统一数据模型：Address, Parcel, ShipmentRequest, Label, Rate
├── registry.py          # CarrierRegistry — 服务注册与发现 (借鉴 EasyPost)
├── fedex/
│   ├── proxy.py         # get_rates(), create_shipment(), get_tracking()
│   ├── mapper.py        # 统一模型 ↔ FedEx REST JSON
│   └── settings.py      # OAuth 2.0 凭证
├── gls/, dhl/           # 同结构
├── csv_polling.py       # 无 API 物流商：生成 CSV → 用户上传 → 导入追踪号
├── excel_adapter.py     # 赛狐 Excel ↔ 物流商模板格式转换
└── platform.py          # Wayfair Partner Home 标签获取
```

### 项目结构（P1 已实现）

```
sellfox_shipping/
├── main.py, app.py, mcp_tools.py, cli.py   # 三界面入口
├── models.py, store.py, config.yaml         # 数据层
├── sellfox_client.py                        # 赛狐 API 客户端 (通过 proxy)
├── carriers/{base,registry,fedex,gls,dhl}/  # 承运人抽象层
├── templates/{index,orders}.html            # Web UI (Jinja2)
├── Dockerfile, docker-compose.yml           # 部署
├── AGENT_HANDOFF.md, README.md              # 文档
└── docs/{index,log}.md                      # OKF 文档
```

### 数据模型（SQLite，5 表）

orders → addresses, order_items, labels (含 cost/currency), tracking_log, rule_log

## Phase Plan

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | 骨架：models, store, sellfox_client, FastAPI REST, FastMCP tools, Typer CLI, Web UI, Docker, 文档 | **已完成** |
| P2 | FedEx API + 标签生成 | **暂缓**（用户决定暂不对接官方 FedEx） |
| P3 | 规则引擎 (YAML 决策表) + Excel 格式适配器 | 待开始 |
| P4 | 追踪回写 + 批量操作 + "煮湖"报告 | 待开始 |
| P5 | 其他承运人（GLS/DHL/Vite）+ 平台打单（Wayfair） | 待开始 |
| P6 | 中文 UI + 打印机 + 打磨 + Pottery Barn EDI 评估 | 待开始 |

## Unresolved Questions

1. **"七条"物流**：老板找的，准确名称待确认（网上未搜到）
2. **蜴国际**：猜测是蜥蜴集团/蜥蜴货运（洛杉矶华人物流），物流同事也不确定
3. **Vite API**：上个月在和赛狐谈对接，不论 API 是否可用都保留 Excel 模板
4. **ERPNext 集成**：需每单成本追踪（labels 表已预留），宏观统计报表之后再说
5. **部署位置**：建议上海测试服务器 Docker Compose（与 sellfox-api-proxy 等共存），后期可移植到 ERPNext app
6. **FedEx API Key / MFA**：P2 暂缓，以后需要时再处理
7. **CSV polling**（DPD/DHL 扫码吐 CSV）：先记录方案，暂不开发

## Related

- [sellfox-api-proxy-design.md](sellfox-api-proxy-design.md) — 赛狐 API 代理网关设计（同生态，不同子系统）
- `SELLFOX_API/docs/api-reference/订单/` — 赛狐订单 API 完整文档
- `warehouse_restock/AGENT_HANDOFF.md` — 仓库地址、SKU 处理参考
- 上级规划：`.claude/plans/sellfox-shipping-ethereal-quill.md`

## Source URLs (Complete)

### ERPNext Shipping
- https://github.com/frappe/erpnext-shipping
- https://docs.erpnext.com/erpnext-shipping
- https://github.com/volkswagner/erpnext-shipping (EasyPost fork)
- https://www.kanakinfosystems.com/frappe/apps/16.0/knk_frappe_fedex_connector
- https://ecosire.com/fr/apps/erpnext/shipping-multi-carrier

### Shipping Platforms (architecture reference)
- https://www.easypost.com / https://github.com/EasyPost/easypost-python
- https://goshippo.com
- https://www.easyship.com
- https://www.shipstation.com
- https://www.pirateship.com
- https://kuajingbase.com/en/tools-review/logistics
- https://apiscout.dev/guides/shippo-vs-easypost-vs-shipstation-shipping-api-2026

### Carrier APIs
- https://developer.fedex.com
- https://developer.ups.com
- https://developers.usps.com
- https://developer.dhl.com
- https://gls-group.com
- https://open.yunexpress.cn
- http://open.4px.com
- https://opendocs.yw56.com.cn
- http://developer.winit.com.cn

### Reference Implementations
- https://github.com/karrioapi/karrio (v2026.1.32)
- https://github.com/EasyPost/easypost-python (v10.7.0)
- https://github.com/verbb/shippy
- https://github.com/frappe/erpnext-shipping
- https://github.com/plentymarkets/plugin-shipping-tutorial
- https://github.com/findologic/plentymarkets-rest-exporter
- https://github.com/Ryukote/Delivery.NET

### MCP & AI Agent Design
- https://modelcontextprotocol.io/specification/2025-11-25
- https://github.com/jlowin/fastmcp (26.1k stars, PrefectHQ)
- https://gofastmcp.com/integrations/fastapi
- https://www.anthropic.com/engineering/writing-tools-for-agents
- https://www.anthropic.com/engineering/building-effective-agents
- https://dev.to/uenyioha/writing-cli-tools-that-ai-agents-actually-want-to-use-39no
- https://www.speakeasy.com/blog/engineering-agent-friendly-cli
- arxiv 2606.30317 (MCP Server Architecture Patterns)
- arxiv 2602.14878 (MCP Tool Descriptions)

### Typer CLI
- https://github.com/fastapi/typer (19.7k stars, tiangolo)
- https://typer.tiangolo.com

### Rule Engines
- https://github.com/gorules/zen
- https://gorules.io
- https://rulebricks.com/blog/rule-engines-for-fulfillment

### Label Printing
- https://labelary.com/zpl.html
- https://labelary.com/service.html
- https://pypi.org/project/zpl
- https://github.com/miikanissi/zebrafy
- https://github.com/Daylily-Informatics/zebra_day

### Plentymarkets
- https://developers.plentymarkets.com/en-gb/developers/main/shipping-plugins
- https://knowledge.plentyone.com/en-gb/manual/main/fulfilment/preparing-the-shipment.html

### Platform Shipping
- https://sell.wayfair.com
- https://developers.overstock.com
- https://blog.jaychrisedi.com/blog/williams-sonoma-edi-vendor-guide

### Logistics Companies
- https://www.viteusa.com / https://www.vitedirect.com
- https://m.amz123.com/xyjt (蜥蜴集团)

### Frappe/ERPNext
- https://docs.frappe.io/framework/user/en/basics/architecture
- https://gavv.in/blog/how-does-frappe-work

## 独立验证

2026-07-16 另一 Agent（claude/strange-jones）执行了完全独立的第二轮调研
（详见 `sellfox_shipping/docs/research/claude-strange-jones-methodology-2026-07-16.md`），在屏蔽本已有结论的前提下独立到达了大部分相似结论
（Karrio 借鉴、ERPNext Shipping 不可用、Excel 模板必要、SQLite + Docker Compose），
但在 **Agent 界面选型**上存在关键分歧：

- 本调研推荐 FastAPI + FastMCP + Typer CLI 三界面架构
- 独立调研推荐 CLI-first + REST API，MCP 推迟到 P2+
- 独立调研收集了 2026 年 CLI vs MCP 实证数据：CLI 比 MCP 便宜 10-35x token 消耗、CLI 可靠性 100% vs MCP 72%
- 独立调研额外确认：DeepSeek 不原生支持 MCP，Vite/亿龙达有 API 文档（用户微信群里）

两个调研可以作为互补视角参考。最终技术选型由团队根据具体情况决定。
