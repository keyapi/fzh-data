---
type: critique
module: sellfox_shipping
created: 2026-07-16
updated: 2026-07-16
strategy: grill-first, breadth-first
independent_path: C
---

# 赛狐尾程打单 — Grill 批判性质疑 (路径 C)

> 本对话角色：独立调研路径 C。策略是**先 grill 再调研**，避免被已有结论锚定。
> 以下 13 个问题的回答基于 briefing 文档、company-context、AGENTS.md 和已有代码骨架的阅读，
> **不基于** comprehensive-research-2026-07-15.md 的调研结论。

---

## 1. 质疑业务假设

### G1: Excel 才是主力，API 是少数场景？

**判断**: **几乎肯定是**。

理由：
- 用户自己说过"尾程物流 API 接口有时不管用"——这是来自真实运营经验的警告
- 3 个美国尾程：FedEx（API 未对接）、Vite（API 不确定有没有）、蜴国际（连名称都不确定）、七条（完全未知）——已知/确定的 API 接入比例极低
- Excel 工作流已经跑了几年（Google Colab 脚本 + 手动上传），说明它是**已验证可用的**
- "API 优先"更像是理想目标，而非当前约束

**结论**: 架构应该**以 Excel 工作流为第一优先级**。API 集成是加分项，但核心流程的用户体验应该围绕"我导出了订单 Excel，然后呢？"来设计。这意味着：
- 订单导入支持 Excel（不只是 API fetch）
- 每个物流商的 Excel 模板管理比 carrier API 抽象更重要
- 追踪号回写的 Excel 导出至少和 API 回写同等优先级

---

### G2: 手动上传 Excel 真的可行吗？有没有中间地带？

**判断**: 需要半自动化。

理由：
- 用户说"用户自己上物流商后台上传即可"——这可能低估了日单量的增长
- Google Colab 脚本的现状说明已经存在格式转换需求
- 中间地带：系统生成正确格式的 Excel → 用户审核 → 手动上传。审核环节有价值（避免错误订单发出），不应完全取消
- "一键复制粘贴"可能是更好的 UX 模型：CSV 内容复制到剪贴板 → 粘贴到物流商网页

**结论**: 不需要自动上传，但需要做到：
- 生成物流商要求的**精确格式**（列名、列序、日期格式、编码）
- 支持**分批导出**（按物流商、按仓库分组）
- 提供格式**验证**（行数、必填列、值域检查）
- 考虑"复制到剪贴板"作为比文件下载更快的中间方案

---

### G3: 赛狐有"自动物流规则"，我们还需要规则引擎吗？

**判断**: **大概率不需要独立的规则引擎**。

理由：
- 赛狐/通途自带物流规则，用户明确提到了这一点
- 如果规则已经在赛狐里维护，本系统的角色就是"执行者"而非"决策者"
- 维护两套规则 = 两个地方改同样的东西 = 一定会 drift
- 除非赛狐的规则引擎能力不够（不支持某些条件组合），否则不应重复

**结论**: 在调研 R2（赛狐物流能力边界）之前，先**假设本系统不需要独立的规则引擎**。
如果需要少量补充逻辑，用 Python 函数 + YAML 配置即可，不需要 BRE。

---

### G4: SQLite 够用吗？成本数据需要和 ERPNext 对账吗？

**判断**: SQLite 够用当前阶段，但成本对账是个沉睡需求。

理由：
- "每单成本追踪"目前只要求"知道花了多少钱"，不是财务报表级别
- 日均单量未知，但家居纺织品利润率高、单量不会到日发 10000 单
- 成本对账：如果赛狐订单后续要纳入 ERPNext，运费成本需要和采购成本合并计算利润——但这是远期需求
- SQLite 的单文件备份和迁移都比 PostgreSQL 简单

**结论**: SQLite 继续用。但 store 层应该保持抽象（Repository 模式），方便后期换数据库。
成本字段设计时预留币种、汇率、费用拆分的可能性。

---

### G5: 为什么犹豫放 ERPNext？

**判断**: 不是因为 ERPNext app 开发难，而是因为**不想被 ERPNext 的发布周期和架构约束绑住**。

理由：
- 团队已有 ERPNext 生产环境，但所有现有子项目都是独立 Python 服务/CLI，无 ERPNext app 先例
- ERPNext app 开发意味着：Frappe 框架约束、bench 命令部署、doctype 迁移管理、版本兼容性
- 独立服务 = Docker 一行命令部署、独立迭代、不影响 ERPNext 稳定性
- 用户说"不确定部署太多服务是否可行"——这是运维担忧，不是架构担忧

**结论**: 坚持独立服务。但 Service Layer 保持框架无关（已经是 pure Python）。如果将来移植，成本可控。

---

## 2. 质疑技术选型

### G6: FastMCP 是否值得现在就绑定？

**判断**: **风险较高，建议延迟绑定**。

理由：
- MCP 协议 2026-07-28 有重大 RC —— 距离现在不到 2 周
- FastMCP v3.0 2026 年 2 月才 GA，v1→v3 不到一年，API 稳定性存疑
- CLI (`--json`) 已经能满足 Agent 的绝大多数需求：查询订单、创建标签、回写追踪号
- MCP 的真正价值在于 Agent 可以**发现**工具——但打单系统的工具数量少（<10 个），发现不是瓶颈
- 有开发者报告 CLI 比 MCP 节省约 40% token

**结论**: P1-P3 先用 CLI (`--json`) 满足 Agent 需求，MCP 延迟到 P4+。
如果用户觉得 CLI 够用，可能永远不需要 MCP。不要因为"看起来很酷"就加依赖。

---

### G7: 三界面架构是否过度设计？

**判断**: **是，建议简化为 Web + CLI**。

理由：
- 已有骨架实现了 FastAPI + FastMCP + Typer CLI 三个界面
- MCP 可以后续加（G6 已分析），不需要现在就维护
- Web UI 和 CLI 的分工明确：Web 给人看，CLI 给脚本和 Agent
- Typer CLI 已经内置了 `--json` 输出，直接可用
- 三界面 = 三份文档、三套测试、三处改动，小团队负担大

**结论**: 砍掉 MCP（暂时），聚焦 Web + CLI。如果 3 个月后 MCP 协议稳定了再加，成本很低（Service Layer 不变，只加一层 MCP tool wrapper）。

---

### G8: SQLite → PostgreSQL/MySQL 迁移成本？

**判断**: 成本可控，不需要现在换。

理由：
- 已有 store.py 用了 Repository 模式（Store 类封装所有 SQL），换数据库只需改 Store 实现
- SQLite 的 SQL 是标准 SQL，没有用 SQLite 特有语法（已检查 store.py）
- 迁移工具成熟：Alembic + SQLAlchemy 可以从 SQLite 导出再导入
- 现在换 PostgreSQL = 增加运维复杂度（多一个数据库服务要维护）

**结论**: SQLite 继续。在 Store 类里加一个 `export_to_postgres()` 方法作为保险。

---

### G9: Karrio Proxy + Provider 模式 — 会重蹈覆辙吗？

**判断**: 有风险，但当前规模可控。

理由：
- Karrio 的模式是为 30+ 承运人设计的，我们只有 4-5 个
- AbstractCarrier 接口定义的 4 个方法（validate_credentials, get_rates, create_shipment, get_tracking）看起来合理
- 但真实风险是：**每个承运人的业务逻辑差异可能远超接口能统一的范畴**
  - 有的承运人要求先创建订单再获取标签（两步）
  - 有的需要先获取报价再确认（三步）
  - 有的支持批量、有的不支持
  - Excel 兜底的承运人根本用不上 API 接口
- PurplShip → Karrio 重写的原因是"抽象不够灵活"

**结论**: 保持 AbstractCarrier 作为接口约定，但**不要强制所有承运人都实现它**。
Excel 型承运人就是一个"TemplateCarrier"（只生成 Excel，不调 API）。
先实现 2 个真实承运人，再判断抽象是否需要调整。

---

### G10: 上海测试服务器资源够吗？

**判断**: **不确定，需要验证**。

理由：
- 已经在跑：new-api、钉钉 OIDC、赛狐 API 转发——至少 3 个常驻服务
- 再加一个 FastAPI + SQLite = 内存 ~100MB（uvicorn + Python），CPU 可忽略
- 但如果是 Docker Compose = FastAPI + SQLite + 可能的前端静态服务
- 不知道服务器配置（CPU/内存/磁盘），不知道当前负载
- "测试服务器"意味着稳定性不如生产，但打单系统是生产级的

**结论**: P1 可以先部署验证。如果资源紧张，考虑：
- 用 `uv run` 而非 Docker（更轻量）
- SQLite 文件放在 SSD 上
- 加健康检查和简单监控（至少知道服务挂了）

---

## 3. 质疑流程设计

### G11: P1 骨架在无真实承运人对接的情况下是"空壳"吗？

**判断**: **部分是，但不完全是**。

理由：
- models, store, sellfox_client 是有实际价值的——即使没有承运人 API
- 赛狐订单拉取 + 存储 + Web UI 展示 = 已经可以替代"赛狐后台看订单"的部分功能
- 需要先对接一个真实承运人来验证 carrier 抽象的可行性
- Excel 模板生成不需要等 API 对接

**结论**: P1 骨架的价值在于**数据层和赛狐 API 对接**。P2 应该优先实现 Excel 模板生成（不需要 API），然后才是 FedEx API。

---

### G12: 为什么要等 FedEx API？

**判断**: **不应该等**。

理由：
- FedEx 是最确定的承运人（官方 API、文档齐全、OAuth 认证）
- 对接一个真实 API = 验证整个 carrier 抽象
- FedEx 美国的单量可能占大头（USNJ + USTX 两个仓）
- API Key 获取可能需要几周，但不妨碍**先写代码**（用 sandbox/mock 测试）

**结论**: P2 应该同时做 FedEx API 对接（mock 模式）+ Excel 模板生成。等 API Key 拿到后切到真实环境。

---

### G13: 订单数据到底需要存多少字段？

**判断**: **精简存储，保留原始 JSON 兜底**。

理由：
- 已有 Order 模型包含了 20+ 字段 + items + address + raw_json
- `raw_json` 字段的设计很好——不需要预测未来需要什么字段
- 打单必需的最小字段集：order_id, platform, package_sn, shipping_address, items(SKU+qty), order_status
- 成本追踪需要：shipping_cost, carrier, service_level, tracking_number
- 其余字段（shop_name, marketplace, currency, order_total, purchase_date 等）可能只在 audit 时用到

**结论**: 当前模型已经合理。不要继续膨胀，也不要急于删减。`raw_json` 策略是正确的。

---

## Grill 总结

| 问题 | 判断 | 对架构的影响 |
|------|------|------------|
| G1: Excel 主力 vs API 少数 | Excel 是主力 | 优先 Excel 模板管理 → 再 API |
| G2: 手动上传可行吗 | 需要半自动 | 加剪贴板复制、模板验证 |
| G3: 需要规则引擎吗 | 大概率不需要 | 先调研赛狐规则能力边界 |
| G4: SQLite 够吗 | 够 | 保持，预留 Repository 抽象 |
| G5: 为什么犹豫 ERPNext | 不想被框架绑住 | 坚持独立服务 |
| G6: FastMCP 现在绑定？ | 风险高 | 延迟到 P4+，先用 CLI |
| G7: 三界面过度设计？ | 是 | 简化为 Web + CLI |
| G8: SQLite 迁移成本 | 可控 | 加 export_to_postgres() 保险 |
| G9: Karrio 模式风险 | 中等 | 不强求所有承运人实现同一接口 |
| G10: 服务器资源 | 不确定 | P1 验证，准备降级方案 |
| G11: P1 是空壳吗 | 不完全是 | 先做 Excel 模板生成 |
| G12: 为什么等 FedEx | 不应等 | P2 同时 mock FedEx + Excel |
| G13: 存多少字段 | 精简 + raw_json | 当前模型已合理 |

**核心立场**: 这个系统的真实使用场景可能是 **"90% Excel + 10% API"**，而非已有调研假设的 "API 优先，Excel 兜底"。
如果这个判断正确，架构的重心应该从 carrier API 抽象转向 **物流商模板管理 + 格式转换**。
