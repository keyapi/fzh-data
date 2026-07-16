# 赛狐尾程打单 P1 独立调研：架构决策与方法论

## Context

赛狐尾程打单系统（sellfox shipping label system）需要为 5 家跨境物流承运人（FedEx、Vite/亿龙达、GLS、蜥国际、七条）生成发货标签。前端 Agent 已经做过一轮调研（`comprehensive-research-2026-07-15.md`），但为了获取多样性视角、避免锚定效应，ONBOARDING.md 要求新 Agent 在完全屏蔽已有结论的前提下独立执行新一轮调研，最终通过 /grill-me 与用户逐项碰撞，形成经实战验证的架构决策。

这种"隔离调研 + 后期对比"的模式刻意制造了认知多样性——两个 Agent 独立从零出发，各自搜索、各自判断，最终结果既交叉验证又相互补充。

## Guidance

调研遵循 ONBOARDING.md 的六步开局流程：clone 独立分支、阅读纯事实简报（不含已有结论）、学习项目背景（company-context、AGENTS.md、CONCEPTS.md）、了解已有基础设施（SELLFOX_API、sellfox-api-proxy）、独立设计调研方案、完成后可选对比已有调研。

实际调研使用两阶段深度优先策略：

1. **Phase 0 -- 广域搜索（5 路并行 tavily）**：同时搜索"多承运人系统开源方案""中国物流 API 生态""MCP vs CLI 2026 benchmark""承运人抽象模式""后台任务队列"五个方向，快速建立领域全景认知。

2. **Area 1 -- 多承运人核心架构**：深入阅读 Karrio（30+ 承运人，Python/Django），对比 ERPNext Shipping（仅支持 3 个欧洲聚合商，对 FZH 场景无效）、Saleor shipping 模块（侧重运费计算而非标签生成）、Medusa.js Fulfillment Provider 接口（生命周期建模参考）。同时验证 5 家承运人的 API 可用性。

3. **Area 2 -- AI Agent 友好界面设计**：系统对比 MCP vs CLI vs REST API 三种 AI Agent 对接方式，收集 2026 年多个独立 benchmark 的实证数据。

4. **Grilling 验证**：通过 /grill-me 与用户逐项确认关键决策，5 个原始结论在用户反馈中被修正（范围边界、技术假设、API 可用性）。

关键技巧：
- 所有外部搜索保留原始 URL（共 36 条来源），确保可追溯
- 对开源项目用 GitHub 直接访问验证而非仅依赖二手描述
- 对商业平台（ShippyPro、PluginHive、EasyPost）提取可借鉴的架构模式而非照搬

## Why This Matters

**方法论层面**：隔离调研 + 后期对比的模式产出了实际价值——发现了已有调研未覆盖的关键证据（Karrio 的商用 license 成本 $50k/年、2026 年 MCP vs CLI 的 benchmark 数据、Vite/亿龙达 API 文档的存在性确认），同时独立验证了部分已有结论（SQLite 而非 PostgreSQL、FastAPI BackgroundTasks 而非 Redis）。两个独立调研的差异本身就是宝贵的决策参考。

**架构决策层面**：每个决策都有实证支撑而非断言：

- **CLI 优先而非 MCP** 的决策，背后是 2026 年 3 个独立 benchmark（CLI 10-35x 更便宜、100% 可靠性 vs MCP 72%）、Perplexity 宣布缩减 MCP 支持、Andrej Karpathy 的 CLI-as-first-class 论述、以及用户自己生产环境（Claude Desktop + ERPNext REST API，无 MCP）的实战经验。

- **不做"统一承运人抽象"** 的决策，建基于 API 承运人和 Excel 承运人的交互模型根本不同（API 是机器对机器，Excel 是人对机器），强行统一只会制造泄漏的抽象。2 个 API 承运人时不要建框架——等第 3 个 API 承运人真正接入时再抽象（YAGNI），这与 sellfox-api-proxy 的既有策略一致。

- **Excel 第一优先级** 的决策，来自承运人 API 可用性的独立验证：5 家中仅 FedEx（P2）和 GLS 有可用 API，其余 3 家必须走 Excel。所有 5 家都需要 Excel 兜底——即使 API 接入后，用户仍可能需要导出 Excel 给物流商用自有系统处理。

## When to Apply

当在本项目中遇到以下情况时，这套方法论和架构决策可复用：

1. **新系统设计需要多样性视角**：当一个复杂系统（多承运人、多供应商、多平台）的初始方案已经存在但尚未开工时，用隔离调研模式让第二个 Agent 独立验证，可以既确认已有结论的正确性，又发现盲区。

2. **AI Agent 工具链选型**：当需要在 MCP、CLI、REST API 之间选择 AI Agent 对接方式时，本调研提供了完整的评估框架和 2026 年实证数据。规则是：5-10 个工具的 P1 阶段不需要 MCP；CLI（Typer --json）+ REST API（FastAPI）共享 Service Layer 是最优起步方案；当工具数量增长到需要"自动发现"时才用 fastapi-mcp 一键暴露。

3. **承运人/供应商集成**：当面对多个外部系统、其中部分有 API 部分是人工流程时，不建"大一统"抽象。让 API 适配器和 Excel 导出器各走各路，共享 Service Layer 但不需要统一接口。等第 3 个同类 provider 出现时再抽象。

4. **小团队技术选型**：3-5 人团队的技术选型不应照搬大型系统的架构。SQLite（WAL mode）而非 PostgreSQL、FastAPI BackgroundTasks 而非 Redis、Docker Compose 单机而非 K8s——这些决策都基于"够用就行、零运维成本"的原则。

## Examples

以下 5 个关键架构决策代表了本次调研的核心产出，每个决策都附有完整的"为什么"而不是"做什么"：

### 1. P1 只做 Excel，API 放 P2

**证据**：独立验证了 5 家承运人的 API 可用性。仅 FedEx（P2）和 GLS 有可用 REST API。Vite/亿龙达尽管有 API 文档（用户在微信群确认，Vite 2026 年 6 月正在与赛狐谈判），但所有 5 家都需要 Excel 兜底——物流商的后台系统天然接受 Excel 上传。

**Grilling 修正**：原始调研认为"API + Excel 双线并行"，用户纠正为"P1 只做 Excel"。API 和 Excel 不是 fallback 关系（API 失败降级 Excel 不成立），而是互斥的集成模式。每个承运人要么走 API，要么走 Excel，不存在降级路径。

**实践含义**：P1 的 Excel 模板系统必须足够通用，能覆盖 5 家承运人的不同列格式。每家的列映射、格式转换（kg 转 lb、电话号填充、文本截断）通过 YAML 配置驱动，AI 辅助生成规则，人工兜底审核。

### 2. CLI + REST API，暂不引入 MCP

**证据**：
- 2026 年 3 个独立 benchmark：CLI 比 MCP 便宜 10-35x token 消耗（Intune 合规检查实测：CLI 4,150 tokens vs MCP 145,000 tokens，35x 差距）
- MCP 可靠性 72% vs CLI 100%（75 次 benchmark runs）
- Perplexity 2026 年 3 月宣布缩减 MCP 支持，原因直接引用"token 成本低效"和"连接不稳定"
- 用户当前生产环境：Claude Desktop 直接调用 ERPNext REST API，未装 FAC MCP，完全不影响 Agent 工作——这证明 MCP 不是 Agent 的必需品
- DeepSeek API（用户团队主力模型）不原生支持 MCP，需要社区 bridge

**Grilling 验证**：用户确认现有工作流中 MCP 不是必需组件。P1 的 5-10 个工具数量不足以体现 MCP 的"自动发现"价值。

**实践含义**：三界面架构——CLI（Typer --json）给 Agent 用，REST API（FastAPI）给 Web UI 和脚本调用，共享同一个 Service Layer（核心业务逻辑只写一次）。后期如果需要 MCP，`fastapi-mcp`（11.6k stars, MIT）可一键将 FastAPI 端点暴露为 MCP tools，无需重写。

### 3. YAML 配置 + AI 辅助生成规则

**证据**：5 家承运人的 Excel 模板各不相同——不同的列名、列序、数据格式要求。硬编码 5 套模板逻辑意味着每次新增承运人需要写新代码。配置驱动的方式让非开发人员也能维护模板映射。

参考方案：DataFlowMapper 的商业 AI-copilot 模式——用户上传示例 Excel，AI 推断列映射规则，人工确认后保存为配置。GoRules ZEN Engine（Rust+Python, MIT）的决策表模式可作为后期规则引擎参考。

**Grilling 修正**：原始调研提出"YAML 配置"，用户补充了"AI 辅助生成 + 人工兜底"的两步模式。这既利用了 AI 的模式识别能力，又保留了人类对关键业务数据的最终控制权。

**实践含义**：每个承运人的 YAML 配置包含：表头行号、数据起始行、列映射（赛狐字段名 → Excel 列名）、数据转换规则（单位换算、文本处理、默认值填充）。AI 从示例 Excel 文件推断规则，人工审核 YAML 后落地。

### 4. 做成可复用模块，不嵌入 sellfox_shipping

**证据**：Excel 转换逻辑的适用场景远不止尾程打单。通途格式转换、赛狐导入导出等场景都需要"从 A 格式化到 B"的能力。把转换逻辑嵌入 sellfox_shipping 会导致代码重复或跨模块耦合。

**Grilling 修正**：用户明确要求 Excel 转换逻辑做成独立模块，可以被其他项目 import。这是本次调研最重要的架构纠正之一——从"功能思维"（我需要一个打单功能）转向"能力思维"（我需要一个可复用的 Excel 转换能力）。

**实践含义**：独立 Python 包 `excel-mapper` 或类似命名，核心接口为 `transform(input_data, template_config) -> Excel file`。sellfox_shipping 调用它，通途工具也能调用它，未来任何需要"导出格式化 Excel"的场景都能 import。

### 5. 不建"大一统承运人抽象"

**证据**：API 承运人和 Excel 承运人的交互模型根本不同。API 模式是"订单数据 → API 调用 → 获取标签"，Excel 模式是"订单数据 → 格式化 → 导出 → 人工上传"。强行用同一个接口约束两种模式只会产生泄漏的抽象。

仅 2 个 API 承运人（FedEx P2 + GLS）时不需要 Plugin/Registry 模式。两个独立 adapter 类即可。sellfox-api-proxy 的既有实践证明：不要为 2 个 provider 建插件框架。YAGNI 原则：等第 3 个 API 承运人真正接入时再抽象。

**实践含义**：双模架构——Service Layer 之上分两个分支：API Carrier Adapter（FedEx adapter、GLS adapter，各自实现 `get_rates()`/`create_shipment()`/`get_label()`）和 Excel Exporter（模板引擎，根据 YAML 配置渲染各承运人的 Excel）。两者不共享接口，只共享 Service Layer（订单获取、追踪回写）。

### 6. SQLite + FastAPI BackgroundTasks，不引入 Redis

**证据**：3-5 个物流同事，无并发写入瓶颈。SQLite WAL mode 足以支撑读多写少的场景。标签生成是主要异步任务——调用承运人 API 可能耗时数秒——用 FastAPI 内置 BackgroundTasks 即可满足，失败任务写入 SQLite 定时轮询重试。

避免引入 Redis 增加运维复杂度，与 sellfox-api-proxy 的 aiosqlite 技术栈保持一致。后期如果确实需要完整队列（优先级、定时、监控），SAQ（Simple Async Queue）比 ARQ 快 8x，支持 Redis 或 PostgreSQL backend。

**实践含义**：Docker Compose 单机部署，2-3 个容器（app + worker + nginx），SQLite 零运维成本。与现有 sellfox-api-proxy 共享上海测试服务器。
