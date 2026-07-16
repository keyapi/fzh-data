---
okf: v0.1
type: Research
title: 赛狐尾程打单系统独立调研综合与架构判断
description: 基于已确认业务事实、赛狐与 VITE API、Karrio 及当前代码骨架形成的独立判断、目标架构和分阶段验证方案
tags: [sellfox-shipping, package-workflow, vite, karrio, spreadsheet, architecture]
timestamp: 2026-07-16
---

# 赛狐尾程打单系统独立调研综合与架构判断

> **接手实现进度（非本文职责）：** 本文是目标架构与阶段规划。  
> 2026-07-16 已完成过程、Git 提交、P1A 代码事实与下一步清单见  
> [session-progress-2026-07-16.md](session-progress-2026-07-16.md)。  
> 新对话 / 换 Agent：**先读 session-progress，再读本文。**

## 1. 执行摘要

本报告的结论不是对既有 Agent A/B/C 意见的投票或拼接，而是从实际闭环、赛狐包裹 API、当前代码和承运人接入边界重新推导。

**明确推荐：自建以 `Package(sellfox_account_id, package_sn)` 为核心的公司领域批次工作流，不采用 Karrio Server；将人工 Excel 和 API 视为同等级承运人适配方式。** 系统主干应是：

1. 从赛狐“订单处理”包裹接口拉取包裹，而不是从“全部订单”接口建立主流程。
2. 以 `Order ↔ Package` 多对多关系保存一单多包、一包多单，所有 Excel、PDF、追踪号和提交平台操作均按稳定业务标识对账，不依赖行序或页序。
3. 将蜴国际实现为 `SpreadsheetCarrierAdapter`，将 VITE、FedEx 等实现为 `ApiCarrierAdapter`；二者共享批次、制品、追踪号分配、审核、审计和回写能力。
4. Karrio 只放在防腐层之后，作为可选的 API connector 依赖。复用其统一模型、Mapper/Proxy/Settings 和已有成熟 connector，不运行 Karrio Server，不复制或 fork 已有 connector。
5. Karrio **没有现成 VITE/GOFO connector**。P1 的 VITE spike 是按 Karrio extension 规范新建最小 custom connector 的一次性技术实验，并与直接 `httpx` adapter 比较代码量、错误映射和维护收益；它不承诺复用现成 connector，也不承诺上线。[K-SDK][K-EXT]
6. 当前 1–5 人、日常少于 200 包裹、峰值少于 500 包裹的共享单服务器场景，FastAPI + Service Layer + SQLite WAL 足够。先同步执行并持久化批次状态；达到明确门槛后再引入 worker 或 PostgreSQL。
7. `submitToPlatform` 是不可盲目重放的外部副作用。一包多单按订单建立稳定 `SubmissionIntent`，每次网络调用记 `SubmissionAttempt`；调用前持久化 `CREATED/NOT_SENT`、CAS 后才发送，残留 `IN_FLIGHT` 一律转 `UNKNOWN`。阻断按 `(sellfox_account_id, package_id, order_id)` scope，而非 request hash，字段变化不能绕过。回读是否即时、是否足以作为权威确认仍待验证。[SF-SUBMIT]
8. P1 是独立服务：Jinja2 server-rendered Web + 少量 JavaScript、REST/JSON CLI、SQLAlchemy + SQLite；记录每包裹/运单成本和币种，提供中英文 UI，不依赖 ERPNext，但 Service Layer/REST 可供未来 ERPNext app 调用。

最先要解决的不是技术选型，而是输入契约。业务方已确认蜴国际模板存在客户参考号字段，且该值会出现在返回 Excel/PDF；但**三类真实样例尚未收集，具体列名、格式和可机器解析性仍须验证**，这是 P0 的硬前置和当前最大风险。

本文从本次澄清重新定义 P0–P3，并取代当前 `sellfox_shipping/AGENT_HANDOFF.md` 的旧 P1/P2 阶段描述；该文件所称“P1 骨架完成”在本文统一称为 **legacy skeleton**，不表示生产工作流已完成。

---

## 2. 证据分级与事实边界

为避免把需求、代码现状和设计意见混为一谈，全文使用四类标签：

- **[用户确认事实]**：业务方已明确确认，可直接作为范围和验收依据。
- **[代码/API 可验证事实]**：可由仓库源码、OpenAPI、官方 Swagger、官方文档或版本化源码核验。
- **[待验证假设]**：当前证据不足，必须通过样例、测试账号或运行实验确认。
- **[架构判断]**：基于约束作出的推荐，不冒充外部事实；可被后续验证门推翻。

### 2.1 用户确认事实

本节来源为文内的 [2026-07-16 需求澄清决策记录](#user-2026-07-16) `[USER-2026-07-16]`，不是 `briefing-for-independent-agent.md`；briefing 仅提供较早背景。

- **[用户确认事实]** P1 试点物流商为**蜴国际**。美国使用较多，目前只有 Excel 流程。
- **[用户确认事实]** P1 完整闭环是：

  `赛狐拉包裹 → 人工审核 → 导出蜴国际 Excel → 人工上传物流商 → 物流商返回追踪号 Excel → 按 packageSn/客户参考号对账 → 人工复核 → 赛狐 submitToPlatform → 回读核验`

- **[用户确认事实]** 一单多包和一包多单都可能存在，不能依赖 Excel 行顺序或 PDF 页顺序。后续 PDF 以包裹号匹配；packlist 后置。
- **[用户确认事实]** 初期物流商选择直接读取赛狐 `channelName`；本地规则引擎只保留扩展点，不在 P1 再建设第二套路由规则。
- **[用户确认事实]** 用户分布在中国和美国，为 1–5 人小团队，共享一台服务器；日常少于 200 包裹，峰值少于 500；认证采用钉钉 OIDC。
- **[用户确认事实]** VITE 当前主要通过通途 API；大件使用 VITE。未来美国可能有两家分公司、多个账户分别结算。
- **[用户确认事实]** P1 只做 VITE 测试环境技术验证，不替换通途现有生产接入。
- **[用户确认事实]** 欧洲主要使用 GLS；波兰 GLS 当前走 Excel。是否已有可用 API 和账户仍待确认。
- **[用户确认事实]** 蜴国际模板有客户参考号字段，且会出现在返回 Excel/PDF；真实上传文件、返回文件和 PDF 样例尚未收集，具体列名与格式必须作为 P0 前置验证。
- **[用户确认事实]** 需要记录每个包裹/运单的发货成本和币种；Web UI 需要支持中英文。
- **[用户确认事实]** 系统作为独立服务运行，不依赖 ERPNext；同时 Service Layer/REST 应允许未来 ERPNext app 调用。

### 2.2 代码/API 可验证事实

- **[代码/API 可验证事实]** 赛狐包裹列表接口为 `POST /api/packageShip/v1/getPackagePage.json`，支持按 `packageSn`、`orderId`、`trackNo` 搜索；每个包裹响应 schema 含 `orders[]`、`items[]`、`address`、`logistics`。[SF-PKG-LIST]
- **[代码/API 可验证事实]** 赛狐包裹详情接口为 `POST /api/packageShip/v1/packageDetail.json`，请求键是 `packageSn`；物流字段含 `channelName`、`trackNo`、重量和长宽高。[SF-PKG-DETAIL]
- **[代码/API 可验证事实]** 提交平台接口为 `POST /api/packageShip/submitToPlatform.json`，请求字段是 `shopId`、`orderId`、`carrierName`、`trackNo`、`shipService`、`items[]`，其中产品数量要求为正整数。[SF-SUBMIT]
- **[代码/API 可验证事实]** 订单详情的 `orderPackageList[]` 与包裹接口的 `orders[]` 在 API schema 层面支持数组多值；结合用户确认生产中确有少量一单多包和一包多单场景，数据模型必须按多对多实现。不能仅凭 schema 宣称生产数据一定出现多值。[SF-ORDER-DETAIL][SF-PKG-LIST]
- **[代码/API 可验证事实]** 当前项目 `uv run python --version` 输出 `Python 3.12.13`；根 `pyproject.toml` 声明 `requires-python = ">=3.10"`。
- **[代码/API 可验证事实]** Karrio v2026.1.32 的 PyPI 元数据要求 Python >=3.11，SDK 可脱离 Server 独立使用。[K-PYPI][K-SDK]
- **[代码/API 可验证事实]** 当前根 `pyproject.toml` 与 `uv.lock` 均无 FastMCP 依赖，但 `mcp_tools.py` 直接导入 `fastmcp`；`Dockerfile` 又单独执行 `pip install fastmcp`，形成本地 uv 环境与镜像依赖漂移。[CODE-PYPROJECT][CODE-DOCKER]
- **[代码/API 可验证事实]** Karrio v2026.1.32 的 connector 列表中没有 VITE 或 GOFO，因此不存在可直接复用的现成 connector。[K-SDK][K-REPO]

### 2.3 待验证假设

- **[待验证假设]** 已确认的蜴国际客户参考号在真实上传/返回文件中的具体列名、格式、长度约束和解析规则，以及 PDF 中的文本/条码呈现方式。
- **[待验证假设]** 蜴国际真实文件的日期格式、必填项、编码、工作表结构和追踪号唯一性符合目前口头理解。
- **[待验证假设]** 赛狐 `channelName` 在目标店铺、目标仓库和拆/合包场景中稳定且足以决定物流商。
- **[待验证假设]** `submitToPlatform` 对重复的 `orderId + trackNo + items` 是否幂等；官方文档没有给出幂等承诺。
- **[待验证假设]** `submitToPlatform` 后包裹列表/详情的更新延迟，以及回读字段能否作为权威提交结果；在验证前，一次未观察到变化不能证明提交未生效。
- **[待验证假设]** VITE 业务方给出的 `serviceType=GOFO_PARCEL`、`channel=GFUS/YT` 在测试账户可用。公开 Swagger 示例使用 `GOFO_PX/PARCEL`，两者不可视为同义。
- **[待验证假设]** VITE 的 `requestId` 在超时重试、单票、批量和取消场景下具有业务方期望的唯一性/幂等语义。
- **[待验证假设]** 波兰 GLS 账户可调用 GLS Group API；Karrio 的 GLS Group connector 能否支持该账户和波兰合同不能从“存在 GLS connector”推导。

### 2.4 核心架构判断

- **[架构判断]** 包裹而非订单是打单工作流聚合根；订单是包裹的关联业务对象。
- **[架构判断]** 人工 Excel 不是临时补丁，而是长期存在的正式承运人通道；其适配器必须与 API 适配器拥有同样的幂等、审计和对账质量。
- **[架构判断]** 当前规模不值得部署 Karrio Server、Celery、Redis 或独立规则服务；复杂度会大于收益。
- **[架构判断]** Karrio SDK 只有在具体 connector 经测试环境通过后才引入生产；不能为了“统一”提前把全部流程绑到 Karrio。

### 2.5 Python 与外部 API 命名边界

本文同时讨论 Python 领域模型和第三方 API，因此会有两套合法命名；实现时必须在 adapter/gateway 边界显式转换，不能把外部驼峰字段扩散到 Service Layer 或数据库：

- **Python 类与枚举：** `PascalCase`，例如 `SubmissionIntent`、`PackageStatus`。
- **Python 属性、函数、内部 DTO、REST/CLI JSON 和数据库列：** `snake_case`，例如 `package_sn`、`channel_name`、`tracking_number`、`request_id`、`service_type`。
- **常量与枚举值：** Python 常量使用 `UPPER_SNAKE_CASE`；持久化状态值保持版本化的 `UPPER_SNAKE_CASE`。
- **外部 wire payload：** 严格保留官方字段名，例如赛狐 `packageSn`、`channelName`、`orderId`、`trackNo`，VITE `requestId`、`serviceType`。文中出现这些驼峰名时，表示外部契约，不表示 Python 属性。
- **Pydantic 映射：** gateway 模型用显式 alias（例如 `package_sn = Field(alias="packageSn")`）或等价映射；只在向外部系统序列化时使用 alias，领域层始终读取 snake_case。
- **规范化 request hash：** 基于内部 canonical DTO 的 snake_case 字段计算；外部 payload 由 adapter 映射生成，避免第三方字段命名变化污染幂等键。

核心对应关系固定为：`package_sn ↔ packageSn`、`channel_name ↔ channelName`、`order_id ↔ orderId`、`tracking_number ↔ trackNo`、`request_id ↔ requestId`、`service_type ↔ serviceType`。

---

## 3. 业务闭环与不变量

### 3.1 P1 蜴国际闭环

```text
赛狐 package workflow
  │
  ├─ 拉取包裹列表/详情
  │    └─ 保存 Order、Package、PackageOrder、PackageItem 原始快照
  │
  ├─ 人工审核
  │    ├─ channelName 是否为蜴国际
  │    ├─ 地址、重量、尺寸、商品数量是否完整
  │    └─ 一单多包/一包多单关系是否完整
  │
  ├─ 创建 ShippingBatch
  │    └─ 导出蜴国际 Excel Artifact（写入 packageSn/客户参考号）
  │
  ├─ 人工上传蜴国际
  │
  ├─ 导入追踪号 Excel Artifact
  │    ├─ 按 packageSn/客户参考号匹配
  │    ├─ 输出成功/跳过/失败/未匹配
  │    └─ 建立 TrackingAssignment
  │
  ├─ 人工逐包复核
  │
  ├─ 逐条 submitToPlatform（1 rps）
  │    ├─ 一包 N 单生成 N 个 SubmissionIntent
  │    └─ 每个 intent 建立 SubmissionAttempt，不批量掩盖单条结果
  │
  └─ 回读包裹详情/列表
       └─ 逐 intent 核验后聚合 package 状态；回读权威性待验证
```

### 3.2 必须维持的不变量

1. `(sellfox_account_id, package_sn)` 是内部包裹唯一业务键；外部 `packageSn` 只在对应赛狐账户范围内参与对账，不假设跨账户全局唯一，数据库代理主键也不能替代该组合键。
2. 一个 `Order` 可连接多个 `Package`，一个 `Package` 也可连接多个 `Order`。
3. 所有外部行、PDF 页和返回记录必须通过显式业务键匹配，禁止位置匹配。
4. 同一输入文件按内容 hash 重复上传时，不得重复创建追踪号分配或重复回写。
5. 每个批次的四个顶层结果必须互斥，并满足：

   `输入 N = 成功 S + 跳过 K + 失败 F + 未匹配 U`

   `duplicate`、`conflict` 等只作为某一个顶层结果的子原因，并进入 `reason_counts`；不得再作为顶层计数重复参与求和。每个差数都可追溯到逐行结果和原因。
6. 每个 Artifact 保存原始文件 hash、文件类型、模板版本、上传用户、时间和解析结果；原始文件不可被后续处理覆盖。
7. 每个关键操作记录操作者身份。钉钉 OIDC 的用户标识必须进入 `AuditEvent`，而不只存在访问日志。
8. `submitToPlatform` 成功不能只以 HTTP 200 或 `code=0` 推断；应结合回读和人工核验，但回读的即时性与权威性须先验证，不能把一次回读当作自动重试依据。
9. 每个已生成运单的包裹必须保存发货成本、币种、来源和是否预估/最终值。
10. 一包多单时，**回写执行单元是 package-order，而不是整个 package**。每个订单生成一个稳定 `SubmissionIntent`；其 `items` 只能来自该 `PackageOrder` 对应的 `PackageItem`，不得混入同包其他订单商品。
11. 已有 `SUCCESS` 或 `VERIFIED` 的 intent 永不重发；`UNKNOWN` 一律阻断重发并转人工调查；`FAILED` 只允许人工针对该订单重试，并在同一 intent 下新增 attempt。不能假定赛狐外部接口幂等。
12. `UNKNOWN` 的阻断键是提交作用域 `(sellfox_account_id, package_id, order_id)`，不是 `request_hash`。该作用域存在未结案 UNKNOWN 时，修改 `tracking_number`、`carrier_name`、`shipping_service` 或 `items` 产生新 hash 也不得创建或执行新 intent。

### 3.3 建议的状态模型

状态应反映本地工作流事实，不要照抄某一家承运人的枚举。提交前仍按包裹推进：

```text
FETCHED
  → REVIEW_REQUIRED
  → READY_FOR_EXPORT
  → EXPORTED
  → UPLOADED_EXTERNALLY
  → TRACKING_IMPORTED
  → TRACKING_REVIEWED
```

进入回写后分为**订单级 intent 状态**和**包裹级聚合状态**：

```text
SubmissionIntent:
READY → IN_FLIGHT → SUCCESS → VERIFIED
                  ├→ FAILED
                  └→ UNKNOWN
FAILED --仅人工按该订单重试并新增 attempt--> IN_FLIGHT
UNKNOWN --权威确认已应用--> VERIFIED
UNKNOWN --证据化调查结案--> CLOSED
                              resolution=CONFIRMED_NOT_APPLIED
UNKNOWN --升级但尚未确认副作用--> UNKNOWN + escalation metadata
```

`SUCCESS` 只表示该订单的外部调用明确成功，尚未完成权威回读；`VERIFIED` 才表示该订单已核验。`CONFIRMED_NOT_APPLIED` 必须有权威回读或人工调查证据。升级处理只增加批准人、原因和处置记录，不改变 `UNKNOWN`，也不释放 scope lock。`CLOSED` intent 不进入当前 intent 聚合集合；若仍需提交，必须重新人工确认并创建后继 `READY` intent。

包裹状态必须由 Service Layer 以以下**穷尽且固定优先级**的纯函数从当前订单级 intent 派生；输入不能为空，且只允许 `READY/VERIFIED/SUCCESS/FAILED/UNKNOWN/IN_FLIGHT`：

```python
def aggregate_package(intent_states):
    if not intent_states or any(state not in ALLOWED_STATES for state in intent_states):
        return "BLOCKED"  # 空集合或非法状态
    if any(state == "UNKNOWN" for state in intent_states):
        return "PARTIAL_UNKNOWN"
    if any(state == "IN_FLIGHT" for state in intent_states):
        return "SUBMITTING"
    if any(state == "READY" for state in intent_states):
        return "TRACKING_REVIEWED" if all(state == "READY" for state in intent_states) else "PARTIAL_READY"
    if any(state == "FAILED" for state in intent_states):
        return "SUBMIT_FAILED" if all(state == "FAILED" for state in intent_states) else "PARTIAL_FAILED"
    if all(state == "VERIFIED" for state in intent_states):
        return "VERIFIED"
    if all(state in {"SUCCESS", "VERIFIED"} for state in intent_states):
        return "SUBMITTED_PENDING_VERIFY"
    return "BLOCKED"  # 理论不可达；作为非法组合保护
```

优先级因此严格为 `UNKNOWN > IN_FLIGHT > READY > FAILED > VERIFIED > SUCCESS/VERIFIED > BLOCKED`，覆盖六种 intent 状态的所有混合组合。单 intent UNKNOWN 和任意含 UNKNOWN 的混合组合都返回 `PARTIAL_UNKNOWN`；`READY + FAILED` 为 `PARTIAL_READY`，`IN_FLIGHT + FAILED` 为 `SUBMITTING`。package 完成状态不设人工写入口，不允许 UI、管理员或最后一次 attempt 提前把 package 标记为 `VERIFIED`。成功订单永不因同包失败订单的人工重试而重发。

其他异常分支：

- `BLOCKED`：缺字段、关系异常、模板不兼容，需人工处理。
- `UNMATCHED`：返回记录找不到唯一包裹。
- `CONFLICT`：同一包裹出现多个不同追踪号，或追踪号映射多个不允许的包裹。
- `TRACKING_REVIEWED/PARTIAL_READY`：分别表示全部 intent 待提交，或 READY 与其他非 UNKNOWN/IN_FLIGHT 状态混合；都不是提交完成。
- `SUBMITTING`：至少一个 intent 为 IN_FLIGHT 且没有 UNKNOWN。
- `SUBMIT_FAILED`：单订单包裹失败或全部订单 intent 均失败；只允许人工按失败订单重试。
- `PARTIAL_UNKNOWN`：至少一个 intent 结果未知（包括单 intent 包裹）；整个包裹阻断自动重试，等待人工调查。

状态跃迁与聚合由 Service Layer 校验并写 `AuditEvent`。Web、REST 和 CLI 只能调用同一个用例，不能各自修改数据库状态。

---

## 4. 方案对比与明确推荐

### 4.1 方案 A：采用 Karrio Server 作为主系统

**优势**

- 已有多承运人 API、Dashboard、carrier account、shipment、tracking 等基础能力。
- Django、PostgreSQL、Redis、worker 适合更大规模、多租户平台。

**不适合当前项目的原因**

- 蜴国际主流程是人工 Excel 往返，不是标准 JSON/XML carrier API。
- 本项目需要赛狐包裹多对多关系、人工审核、文件制品、逐行对账、不可盲重放回写等公司领域流程；这些不是 Karrio Server 的核心模型。
- Server 引入 Django API、Next.js Dashboard、PostgreSQL、Redis 和 worker，明显超过 1–5 人、峰值 500 包裹的需求。
- SSO/SAML、审计、复杂权限、多租户等高级能力属于 Enterprise；批处理/CSV 工作流在官方资料中长期处于 Insiders、Preview 或企业边界，不能作为免费自建版确定能力。

**结论：不采用。**

### 4.2 方案 B：完全自行实现全部承运人 connector

**优势**

- 领域模型和控制权最直接。
- 不受第三方 SDK 发布节奏和 Python 版本约束。

**问题**

- FedEx 等成熟 API 的认证、错误映射、地址/包裹/标签/追踪抽象重复建设成本高。
- 容易把公司工作流与某家承运人协议耦合。
- 后续每个 API connector 都要独立维护协议变化。

**结论：只适合 Karrio 不支持或验证失败的承运人，不作为默认路线。**

### 4.3 方案 C：自建领域工作流 + 可选 Karrio SDK connector

**组成**

- 自建：赛狐包裹同步、数据模型、批次、Excel、Artifact、对账、审批、审计、回写和 UI。
- 自建防腐层：`CarrierAdapter` 接口及公司领域 DTO。
- `SpreadsheetCarrierAdapter`：蜴国际、GLS Excel 等人工文件流程。
- `ApiCarrierAdapter`：VITE、FedEx、未来其他 API。
- 可选 Karrio：在 `ApiCarrierAdapter` 内部复用经验证的现成 connector；对于没有现成 connector 的 VITE，只在 spike 中按 extension 规范实现最小 custom connector，并与直接 `httpx` adapter 对比。

**结论：明确推荐。** 它保留 Karrio 最有价值的协议抽象，同时不把公司业务流程交给不匹配的 Server 模型。

---

## 5. 目标架构

### 5.1 分层

```text
┌───────────────────────────────────────────────────────────────┐
│ Web UI / REST API / JSON CLI                                  │
│ 钉钉 OIDC；输入校验；展示；不直接编排数据库和外部副作用        │
└──────────────────────────────┬────────────────────────────────┘
                               │
┌──────────────────────────────▼────────────────────────────────┐
│ Service Layer                                                 │
│ SyncPackages / ReviewPackage / ExportBatch / ImportTracking   │
│ ConfirmTracking / SubmitTracking / VerifySubmission           │
└──────────────┬──────────────────────────────┬─────────────────┘
               │                              │
┌──────────────▼──────────────┐  ┌────────────▼─────────────────┐
│ Repository + Unit of Work  │  │ 外部系统防腐层                │
│ SQLAlchemy + migrations    │  │ SellfoxGateway               │
│ SQLite WAL + busy_timeout  │  │ CarrierAdapter               │
└─────────────────────────────┘  │ ├─ SpreadsheetCarrierAdapter │
                                 │ └─ ApiCarrierAdapter         │
                                 │    └─ optional Karrio SDK    │
                                 └──────────────────────────────┘
```

FastAPI 只负责 HTTP、OIDC 会话和请求/响应。CLI 输出稳定 JSON，调用相同 Service Layer。MCP 延后，避免在核心用例未稳定时增加一套权限和工具协议。系统独立部署，不依赖 ERPNext；未来 ERPNext app 如需接入，只调用稳定的 Service Layer/REST，不直接共享数据库。

### 5.2 核心数据模型

#### `Order`

- 平台订单标识、店铺、平台、站点、状态、时间等订单级字段。
- 唯一约束应基于真实作用域，例如 `(shop_id, platform_order_id)`，不能假设全局只有 Amazon。

#### `Package`

- `(sellfox_account_id, package_sn)` 唯一，不假设 `package_sn` 跨赛狐账户全局唯一。
- 赛狐状态、`channel_name`、仓库、地址快照、重量、尺寸、原始响应、最近同步时间。
- 作为审核、打单、追踪号和平台提交的聚合根。

#### `PackageOrder`

- `package_id + order_id` 关联表。
- 保存该包裹内此订单的关系信息；支持一单多包、一包多单。

#### `PackageItem`

- 按包裹保存 `order_item_id`、所属订单、SKU 和数量；gateway 映射到赛狐外部字段 `orderItemId`。
- 明确关联到一个 `PackageOrder`；为该订单级 `SubmissionIntent.items[]` 提供唯一可审核的数量来源。
- 构造 intent 时只选择当前 package-order 的 `PackageItem`，并按 `order_item_id`（再按 `quantity`）稳定排序；禁止把同包其他订单商品混入请求。

#### `CarrierAccount`

- 承运人、账户别名、法人/分公司、环境、启用状态、密钥引用、结算归属。
- 为未来美国两分公司、多账户分别结算预留；不把凭证值写入数据库明文字段或文档。

#### `ShippingBatch` 与 `BatchPackage`

- `ShippingBatch` 保存 adapter、账户、模板版本、创建人、状态和汇总数量。
- `BatchPackage` 保存包裹在批次中的状态、导出/导入结果、跳过或失败原因。

#### `Artifact`

- 原始上传、导出 Excel、返回 Excel、PDF、解析报告等文件制品。
- 保存 SHA-256、模板版本、MIME、大小、存储路径、上传人和时间。

#### `TrackingAssignment`

- `package_id`、tracking number、carrier、service、发货成本、币种、成本状态（预估/最终）、来源 artifact/行号、匹配键、复核人和复核时间。
- 应能表达冲突和替换历史，不直接覆盖旧记录。

#### `SubmissionIntent`

- 表示一次稳定的**逻辑订单级提交**，关联 `sellfox_account_id`、`package_id`、`package_order_id`、外部 `order_id`、`tracking_assignment_id`，保存规范化请求快照、`request_hash`、intent 状态、确认人和版本号。
- 规范化请求至少包含：`sellfox_account_id`、`package_id`、`order_id`、`tracking_number`、`carrier_name`、`shipping_service`，以及仅属于该 package-order 且排序后的 `items[{order_item_id, quantity}]`。使用固定 snake_case 字段名、明确空值规则、UTF-8 canonical JSON（键排序、无无意义空白）后计算 SHA-256；adapter 再映射为外部 `trackNo/carrierName/shipService/orderItemId`。
- 数据库对 `request_hash` 建唯一约束。若追踪号、承运人、服务或 items 改变，通常需要新 hash、新 intent 并重新人工确认；但必须先通过提交作用域锁检查，不能用改字段绕过旧 UNKNOWN。
- 提交作用域固定为 `(sellfox_account_id, package_id, order_id)`。intent 保存 `scope_key`；另设以该三元组为唯一键的 scope guard 记录。Service Layer 在创建/执行 intent 的同一事务中锁定 guard；其状态为 `UNKNOWN_BLOCKED` 时拒绝任何后继 intent，避免只靠 `request_hash` 或普通查询产生竞态。
- UNKNOWN 只能通过权威回读/人工调查结案：确认已应用则将原 intent 置为 `VERIFIED`；确认未应用则记录 `CONFIRMED_NOT_APPLIED`、证据、调查人和时间。需要升级处理时只记录 escalation metadata；在尚未确认副作用结果前仍保持 `UNKNOWN_BLOCKED`。只有 `CONFIRMED_NOT_APPLIED` 才允许按业务需要重新确认并创建后继 intent。
- Service Layer 在短事务中先创建 `CREATED/NOT_SENT` attempt，再以 compare-and-swap（例如 `version` + 当前状态）把 `READY/FAILED` intent 与该 attempt 切换为 `IN_FLIGHT`；唯一约束、scope lock 与 CAS 共同防止重复点击或并发调用。
- `SUCCESS/VERIFIED` intent 拒绝再次发送；`UNKNOWN` intent 锁定并拒绝重发；`FAILED` intent 只允许人工针对该订单创建下一次 attempt。

#### `SubmissionAttempt`

- 表示某个 `SubmissionIntent` 的一次网络尝试，保存 `intent_id`、递增 attempt number、操作者、开始/结束时间、HTTP/API 请求响应、异常和 correlation id。
- attempt 状态为 `CREATED/IN_FLIGHT/SUCCESS/FAILED/UNKNOWN`。`CREATED` 明确带 `send_state=NOT_SENT`：此时尚未通过发送 CAS，进程重启后也可安全取消或重新进入 CAS；`VERIFIED` 是 intent 的核验状态，不是网络 attempt。
- CAS 成功将 attempt 持久化为 `IN_FLIGHT` 后才允许发出 HTTP 请求。进入 `IN_FLIGHT` 后，本地无法证明请求尚未发送；进程启动恢复或超时扫描发现残留 `IN_FLIGHT` 时，一律把 attempt 和 intent 转为 `UNKNOWN` 并锁定提交作用域，禁止自动重发。
- 每次失败后的人工重试只新增 attempt，不修改 `request_hash`，也不触碰同包已 `SUCCESS/VERIFIED` 的其他 intent。

#### `AuditEvent`

- actor、action、entity type/id、before/after 摘要、request correlation id、时间。
- 所有审核、导出、导入、复核、提交和人工改动都必须记录用户。

### 5.3 数据库与执行模型

**[架构判断]** P1 使用 SQLite：

- 启用 WAL。
- 设置合理 `busy_timeout`。
- 通过 SQLAlchemy repository 和 migrations 管理 schema。
- 数据库与 Artifact 放在单服务器持久化本地卷，并纳入备份。
- 一个写事务只做本地短操作；外部 HTTP 和文件解析不应长时间占有写锁。

迁移 PostgreSQL 的触发条件：

- 部署多个 API/worker 实例；
- 持续出现真实锁冲突且优化短事务后仍影响业务；
- 并发写入或查询量明显超出单机 SQLite；
- 需要数据库级高可用或集中运维能力。

关键业务不能放进 FastAPI `BackgroundTasks`：它没有可靠队列语义，进程重启会丢任务。当前规模可由请求同步执行，但每一步先持久化状态。满足任一条件再引入 worker：

- 单个操作稳定超过 30 秒；
- 需要自动可靠重试或计划任务；
- 需要多实例消费；
- 实测同步请求影响操作体验。

### 5.4 P1 明确技术栈

- **Web：** FastAPI + Jinja2 server-rendered 页面 + 少量原生 JavaScript；不引入 React/Vue 等 SPA。
- **Excel：** `openpyxl` 读写工作簿，保留工作表、单元格类型和格式控制；每个模板由 Pydantic 模型或明确的 Python adapter 完成列级、行级校验，不用模糊列名猜测。
- **认证授权：** 钉钉 OIDC 通过标准 OIDC client 接入；可优先评估 Authlib，但具体库、session/callback 行为和 OIDC bridge 兼容性在实施前验证。OIDC 只解决身份认证，角色/操作授权仍由应用实现。
- **测试：** `pytest`；Excel 与后续 PDF 使用脱敏 golden files；赛狐/VITE HTTP 使用 `respx` 或等价的 `httpx` mock；repository 与 migration 使用临时 SQLite。关键副作用测试必须覆盖 timeout/重启残留 `IN_FLIGHT` → `UNKNOWN` 且按 scope 阻断、字段变化不能绕过，以及聚合函数的全部状态组合。
- **部署：** 单应用 Docker 容器 + 本地持久卷，复用外部 Sellfox proxy 和钉钉 OIDC bridge；反向代理负责 HTTPS。数据库与 Artifact 均持久化和备份。
- **PDF（P2）：** 先做文本提取并按包裹号/客户参考号匹配；文本不可用时再用条码识别或 OCR 兜底。具体 PDF、条码和 OCR 库必须基于真实样例的命中率、版式和性能验证后确定，不提前锁死。

---

## 6. 赛狐 API 判断与安全回写

### 6.1 为什么主入口必须换成 package workflow

“全部订单”接口以 `amazonOrderId` 为中心，订单详情虽然返回 `orderPackageList[]`，但打单需要的地址、包裹物流、`channelName`、包裹维度和 `orders[]` 在“订单处理”包裹接口中表达更直接。

**[架构判断]** 主同步流程：

1. 用 `getPackagePage` 分页拉取候选包裹。
2. 对需要完整字段或回读核验的包裹调用 `packageDetail(packageSn)`。
3. 原样保存响应快照，同时映射规范化字段。
4. 将外部 `packageSn` 映射为内部 `package_sn`，以 `(sellfox_account_id, package_sn)` 做增量 upsert，以关系表保存所有 `orders[]` 和 `items[]`。[SF-PKG-LIST][SF-PKG-DETAIL]

### 6.2 `submitToPlatform` 的副作用控制

官方契约要求 `orderId`，不是 `amazonOrderId` 字段名。对于一包多单，必须基于包裹内每个订单分别生成一个 `SubmissionIntent`，不能用“第一个订单”代替整个包裹。每个 intent 的 `items[]` 必须只来自当前 `PackageOrder` 对应的 `PackageItem`，不能包含同包其他订单商品。

建议提交协议：

1. 只允许已完成追踪号人工复核的包裹进入提交。
2. 对一包 N 单生成 N 个 intent。人工确认 UI 展示 N 个订单级摘要，同时区分内部 snake_case DTO 与即将发送的外部 wire payload；后者明确展示 `shopId/orderId/carrierName/trackNo/shipService/items` 和 `request_hash`，让操作者看清每个订单将提交哪些商品数量。
3. 根据 `sellfox_account_id/package_id/order_id/tracking_number/carrier_name/shipping_service` 和排序后的 `items` 生成 canonical request 与唯一 `request_hash`。数据库唯一约束先拦截相同逻辑提交。
4. 在创建或执行 intent 前，按 `(sellfox_account_id, package_id, order_id)` 锁定并检查 scope。只要该 scope 有未结案 UNKNOWN，即使新字段产生不同 hash，也立即拒绝；不得用修改 `tracking_number/carrier_name/shipping_service/items` 绕过。
5. 在数据库短事务中先创建 `SubmissionAttempt(CREATED, send_state=NOT_SENT)`。`CREATED` 可安全取消，或继续 CAS；不能在 CAS 前发请求。
6. 以 CAS 将 intent `READY/FAILED → IN_FLIGHT`、attempt `CREATED → IN_FLIGHT` 一并持久化。只有 CAS 成功后才调用 HTTP；CAS 失败即停止。进入 `IN_FLIGHT` 后，不得依据本地日志声称请求“肯定未发送”。
7. 后端按**订单 intent 单条**调用，限速 1 rps。调用完成后只更新当前 attempt 和 intent，不改写同包其他 intent。
8. 明确外部成功将 attempt/intent 标记 `SUCCESS`，且立即禁止重发；随后调用包裹详情/列表回读。只有在测试确认回读延迟和字段语义后，才可把 intent 标记 `VERIFIED`。
9. 明确失败将 attempt/intent 标记 `FAILED`。只有人工针对该订单重新确认后，才允许在同一 intent 下新增 `CREATED` attempt；同包已 `SUCCESS/VERIFIED` 的订单不得重发。
10. 超时、断连或响应无法解析将 attempt/intent 标记 `UNKNOWN` 并锁定 scope。进程启动恢复或超时扫描发现任何残留 `IN_FLIGHT`，也一律转 `UNKNOWN`；禁止自动重发。
11. UNKNOWN 结案必须有证据：权威确认已应用 → 原 intent `VERIFIED`；权威确认未应用 → `CONFIRMED_NOT_APPLIED`。只有这两种有副作用结论的结果才能释放 scope lock；前者禁止后继 intent，后者仍需业务重新确认才可创建。人工升级只记录 escalation metadata，并继续保持 `UNKNOWN_BLOCKED`，不能作为重新提交的依据。
12. 每次 intent 状态变化后，调用 §3.3 的唯一聚合函数派生 package 状态，不提供手工设置完成状态的接口。

`request_hash` 唯一约束用于识别相同请求；scope lock 防止未知副作用被“换字段”绕过；CAS 防止并发发送。三者都只保证**本系统内部**的控制，不证明赛狐外部接口幂等。官方文档没有提供可依赖的幂等保证，也没有说明回读的即时性和权威性，因此必须以副作用最保守策略处理。[SF-SUBMIT][SF-PKG-DETAIL]

---

## 7. Karrio 深入评估

### 7.1 可复用的部分

**[代码/API 可验证事实]** Karrio v2026.1.32 是 Python 多承运人 SDK，核心可脱离 Server 使用。[K-PYPI][K-SDK] 其价值在于：

- 统一 `Address`、`Parcel`、`Shipment`、`Rate`、标签和 `Tracking` 等模型。
- 用 `Mapper` 在统一模型与承运人模型间转换。
- 用 `Proxy` 负责实际 HTTP 调用。
- 用 `Settings` 隔离承运人连接参数和环境。
- 统一返回详情与错误 `Message`，减少每个 connector 自定义异常形状。

**[架构判断]** 公司领域模型不能直接使用 Karrio 模型持久化。应由防腐层完成：

```text
Company Package/Address
  → ApiCarrierAdapter
  → Karrio Address/Parcel/Shipment
  → Mapper/Proxy/Settings
  → Carrier API
  → Karrio result/messages
  → Company TrackingAssignment/Artifact/Error
```

这样更换 Karrio 版本或单个 connector 不会侵入批次、审批和赛狐回写。

### 7.2 版本与运行环境

- **[代码/API 可验证事实]** 当前版本是 v2026.1.32，版本化 PyPI 元数据要求 Python >=3.11。[K-PYPI]
- **[代码/API 可验证事实]** 本仓库实际 uv 运行时为 Python 3.12.13，能够满足要求。
- **[代码/API 可验证事实]** 根项目仍声明 Python >=3.10，意味着生产或同事环境可能合法地安装 Python 3.10。
- **[架构判断]** Karrio core 与 connector 应固定到同一发行版本，避免同步发布的内部模型/Mapper 接口漂移；不能使用 connector 对 core 的无上限依赖作为生产锁定策略。
- **[架构判断]** P1 VITE spike 使用隔离的 Python >=3.11 环境和独立 lock。只有验证通过并决定生产采用后，才讨论是否把根项目最低 Python 提升到 3.11 或建立独立子环境。

### 7.3 FedEx connector

- **[代码/API 可验证事实]** v2026.1.32 插件元数据标记 `status="production-ready"`。[K-FEDEX-META]
- **[代码/API 可验证事实]** 版本化 FedEx `Mapper` 明确实现 rate、shipment、return shipment、cancel shipment、tracking、document upload、pickup/update/cancel 的请求与响应映射，`Proxy` 实现对应 HTTP 操作；因此这些能力有源码支撑，而不只来自产品页标签。[K-FEDEX-MAPPER][K-FEDEX-PROXY][K-FEDEX-SETTINGS]
- **[架构判断]** 将来接 FedEx 时优先评估官方 Karrio connector，而不是复制其实现。仍需用公司 FedEx 测试账户做契约测试，`production-ready` 不等于适配本公司合同和特殊服务。

### 7.4 GLS connector

- **[代码/API 可验证事实]** v2026.1.32 GLS 插件元数据为 `status="development"`。[K-GLS-META]
- **[代码/API 可验证事实]** `Settings.account_country_code` 默认 `"DE"`，不能据此假设支持波兰账户。[K-GLS-SETTINGS]
- **[代码/API 可验证事实]** 实际 PyPI 项目为 `karrio-gls`，而版本化 README 的安装命令写 `karrio-gls-group`；两者不一致。`karrio_gls` 与 `karrio-gls` 只是 Python 包名规范化等价，不作为问题。[K-GLS-PYPI][K-GLS-README]
- **[架构判断]** GLS 不进入 P1 API 接入。P2 先实现波兰现有 Excel；只有拿到 API 账号、合同区域和沙箱后，才验证 Karrio GLS connector。不能把 GLS Group 的 OAuth2 connector 与“波兰 GLS 账户可用”画等号。

### 7.5 Custom carrier 与蜴国际

Karrio Custom Carrier 官方流程要求基于承运人 API 文档实现 JSON 或 XML/SOAP schema、`Proxy`、`Mapper` 和契约测试。它原生面向在线 API。

**[架构判断]** 蜴国际是人工上传 Excel、人工取得返回文件/PDF的异步人机流程。硬套 Custom Carrier 会把文件批次、人工确认和未匹配记录伪装成一次 API 请求，丢失真正的业务状态。因此应实现公司自己的 `SpreadsheetCarrierAdapter`，不为蜴国际开发 Karrio connector。

VITE/GOFO 不同：它有在线 JSON API，但 Karrio 没有现成 connector。[K-SDK][K-REPO] 因此 P1 只做以下技术实验：

1. 按 Karrio extension 规范建立仅覆盖 spike 用例的最小 custom connector（`Settings/Proxy/Mapper` + contract tests），不复制或 fork 其他 connector。[K-EXT]
2. 同时实现功能等价的直接 `httpx` adapter。
3. 对比两者的业务代码量、映射代码量、错误保真、单位转换、异步标签处理、测试难度、依赖体积和升级维护成本。
4. 产出“采用 Karrio custom connector / 采用直接 adapter / 暂不接入”的决策记录；实验代码本身不构成生产承诺。

### 7.6 为什么不采用 Karrio Server

**[代码/API 可验证事实]** Karrio Server 包含：

- Django REST Framework API；
- Next.js Dashboard；
- PostgreSQL；
- Redis 缓存/消息代理；
- Huey worker。[K-SERVER]

**[代码/API 可验证事实]** 多租户、高级团队权限、工作流和 CSV 批处理列在 Insiders；批处理页面/工作流处于 Insiders/Preview 边界。官方后续说明多租户、审计、SSO/SAML、Shipping Rules 等属于 Enterprise。公开 OpenAPI 即使出现 batch endpoint，也不能证明开源 Dashboard 的完整批处理页面已稳定可用。[K-INSIDERS][K-ENTERPRISE]

**[架构判断]** 当前需求只需要单公司、少量用户、钉钉 OIDC 和明确的内部审计。引入 Server 不会消除公司领域开发，反而增加两套用户、权限、状态和部署栈。因此不采用。

### 7.7 最终定位

Karrio 的定位必须严格限定为：

> 位于公司 `ApiCarrierAdapter` 防腐层后的可选 connector SDK；不作为领域数据库、不作为批次编排器、不作为 UI/认证系统。

不复制、不 fork connector。确需修复时，优先升级、提交上游补丁或在适配器边界做小范围补偿，并保留版本化契约测试。

---

## 8. VITE 官方 API 与 Karrio spike

### 8.1 官方 API 证据

2026-07-16 访问最初给出的 `Uniuni Ground` query 时，页面实际默认加载的是 **USPS** 定义，不能把该 query 当作 GOFO 的直接证据；随后从同一官方页面的定义选择器选择 **GOFO Express**，其直达链接为 <http://docs.vitedirect.com/?urls.primaryName=GOFO%20Express>。[VITE-GOFO] GOFO 定义可核验：

- 认证：请求头 `x-api-key`。
- 测试服务：`https://test-api.vitedirect.com`。
- 费率：`POST /rate2/gofo`。
- 单票：`POST /shipment2/gofo`。
- 批量：`POST /shipment2/gofo/batch`。
- 标签轮询：`GET /shipment2/label/{orderId}`。
- 取消：文档路径显示 `DELETE /shipment2/label/{requestId}`，但该操作的参数命名又出现 `orderId`；这是官方契约内部不一致，必须在测试环境验证，不能自行猜测。
- 账户：`GET /user/account`。
- 支持 webhook，在标签处理后返回订单状态、标签 URL 和 tracking number。
- `requestId` 是唯一请求标识，应贯穿重试和对账。
- `reference` 会原样返回；规划使用 `reference=packageSn`。
- GOFO 请求只接收 lbs/in，内部 kg/cm 必须显式换算并测试舍入。

测试渠道存在必须正面处理的差异：

- 业务方给出：`serviceType=GOFO_PARCEL`，`channel=GFUS/YT`。
- 公开 Swagger 示例：`GOFO_PX/PARCEL`。

**[待验证假设]** 不能通过名称相似推断映射。必须使用测试账户分别验证服务、渠道、计费和标签结果，并由业务方确认期望值。

### 8.2 spike 形态与范围

VITE spike 仅在测试环境执行：用 Karrio extension 规范新建最小 custom connector，同时实现直接 `httpx` adapter，并记录两种方案的实现代码量、依赖量、统一模型/错误规范收益和维护成本。Karrio 没有现成 VITE/GOFO connector，本实验不承诺上线。[K-EXT][K-REPO]

两种实现至少覆盖：

1. `x-api-key` 是否由 `Settings/Proxy` 正确发送且不会进入日志。
2. kg/cm → lbs/in 的换算、精度、边界值和超限错误。
3. `requestId` 唯一生成、相同请求重试及超时后的幂等行为。
4. `reference=packageSn` 是否在单票、批量、轮询和 webhook 中原样返回。
5. `GFUS/YT` 与 `GOFO_PARCEL` 是否被测试账户接受；与公开示例差异如何解释。
6. `/rate2/gofo` 的价格、服务和错误映射。
7. `/shipment2/gofo` 单票标签流程。
8. `/shipment2/gofo/batch` 的逐票结果、部分失败和批次上限。
9. pending 状态下轮询间隔、最终态和超时；若用 webhook，验证签名/来源、重复通知和乱序。
10. 标签 URL/文件下载、格式、过期时间和 Artifact hash。
11. `DELETE /shipment2/label/{requestId}` 的取消结果、路径 `{requestId}` 与参数名 `orderId` 的差异、重复取消和退款/状态回读。
12. 账户接口与错误响应是否能被 Karrio `Message` 无损表达。

### 8.3 通过标准与决策门

只有同时满足以下条件，才讨论生产接入：

- 测试账户真实成功完成 rate、单票、标签获取、取消；
- `reference=packageSn` 可稳定对账；
- `requestId` 超时重试语义已用实验确认；
- 单位转换和渠道差异有固定契约测试；
- 单票和批量的部分失败可逐包落账；
- 日志、数据库和 Artifact 不泄露密钥；
- Karrio 最小 custom connector 与直接 `httpx` adapter 已完成量化对比，且选定方案无需 fork Karrio 已有 connector；
- 业务方明确决定从通途迁移某个受控范围。

未通过时，继续通途生产流程；即使任一 spike 实现通过，也只形成候选方案，不能因已写代码就自动上线。

---

## 9. 当前骨架的可验证问题

当前 `AGENT_HANDOFF.md` 所称“P1 骨架完成”在本文改称 **legacy skeleton**。以下不是未来优化建议，而是当前源码可直接核验的缺口；本文第 10 节阶段定义取代旧 P1/P2 描述：

1. **数据模型不支持多对多。** `orders.amazon_order_id` 为 `UNIQUE`，`Order` 只有一个 `package_sn`；订单详情解析只读取 `orderPackageList[0]`，包裹解析只读取 `orders[0]`。一单多包和一包多单都会丢关系。[CODE-MODELS][CODE-CLIENT]
2. **当前入口仍走 order API。** Web、CLI、MCP 的 fetch 均调用 `fetch_orders()` 和 `/api/order/pageList.json`，不是包裹工作流；虽然客户端存在 `fetch_packages()`，主入口没有使用。[CODE-APP][CODE-CLI][CODE-CLIENT]
3. **没有独立 Service Layer。** Web、CLI、MCP 三个入口分别复制分页、fetch、upsert 逻辑；文档声称共享 Service Layer，但代码实际是直接调用 client/store。[CODE-APP][CODE-CLI]
4. **代理 Bearer key 未发送。** `SellfoxClient` 接收并保存 `proxy_api_key`，但 `_post()` 没有构造 `Authorization: Bearer ...` 或其他认证头；`proxy_account` 也未参与请求，而 proxy auth 明确要求 Bearer token。[CODE-CLIENT][CODE-PROXY-AUTH]
5. **提交字段错误。** `write_tracking()` 请求体使用 `amazonOrderId`，官方 `submitToPlatform` 契约要求 `orderId`。[CODE-CLIENT][SF-SUBMIT]
6. **提交模型不足。** 当前函数以单个 Amazon 订单为中心，没有按 `PackageOrder/PackageItem` 表达一包多单及逐订单商品数量，也没有 `SubmissionIntent`、逐 intent `SubmissionAttempt`、唯一 request hash、CAS 防并发、包裹聚合状态、人工确认、1 rps、UNKNOWN 阻断和安全回读策略。[CODE-CLIENT][CODE-MODELS]
7. **FastMCP 依赖漂移。** `mcp_tools.py` 导入 `fastmcp`，根 `pyproject.toml` 和 `uv.lock` 没有 FastMCP，但 `Dockerfile` 单独 `pip install fastmcp`；本地 uv 与镜像不能保证同一依赖集。[CODE-PYPROJECT][CODE-DOCKER]
8. **无测试。** `sellfox_shipping` 下没有测试套件；关键 parser、多对多、Excel 幂等、数量对账和副作用回写都无自动验证。[CODE-APP][CODE-CLIENT]
9. **SQLite 生产设置不足。** 当前直接使用 `sqlite3`，没有 WAL、`busy_timeout`、migration、repository/transaction 边界。[CODE-MODELS]
10. **规则方向与已确认业务不符。** `config.yaml` 已写大量本地承运人规则且默认 FedEx，但 P1 应读取赛狐 `channelName`，规则引擎仅留扩展点。[CODE-CARRIER][USER-2026-07-16](#user-2026-07-16)
11. **无应用认证授权，存在 PII 暴露风险。** 当前 FastAPI 没有 auth middleware；CLI `serve` 和 Docker/uvicorn 均绑定 `0.0.0.0`。Web、REST、MCP 可读取订单地址、电话、邮箱等字段。部署前必须完成钉钉 OIDC、应用授权与反向代理 HTTPS；不能把网络位置视为授权。[CODE-APP][CODE-CLI][CODE-DOCKER]

因此当前代码应视为概念骨架，不应在其 schema 上增量堆叠蜴国际流程；P1A 先修正领域模型和用例边界。

---

## 10. 分阶段计划

以下 P0–P3 是 2026-07-16 澄清后的权威阶段定义，**取代** `AGENT_HANDOFF.md` 中旧的“P1 骨架完成 / P2 FedEx”等描述；旧代码仅作为 legacy skeleton 参考。

### P0：样例与 API 合约

**目标：消除阻止正确实现的未知项。**

- 收集蜴国际真实上传 Excel、追踪号返回 Excel、PDF 样例；样例需脱敏但保留结构。
- 基于已确认存在且会回传的客户参考号字段，验证真实文件中的具体列名、格式、长度和 PDF 呈现。
- 记录模板版本、必填字段、编码、工作表、日期和数字格式。
- 用赛狐测试范围验证包裹列表、详情和 `channelName`。
- 明确 `submitToPlatform.orderId` 在各销售平台中的含义、拆/合包请求数量与回读判断。
- 获取 VITE 测试环境必要参数，但不记录任何凭证到文档。

**退出门：** 三类蜴国际样例齐全；字段映射和匹配键经业务方签字确认；赛狐测试包裹覆盖一单多包与一包多单，或已明确构造测试办法。

### P1A：数据模型、认证与只读拉取

- 建立本文数据模型和 migration，包括包裹/运单发货成本、币种及预估/最终状态。
- FastAPI + Service Layer + SQLAlchemy repository。
- SQLite WAL、`busy_timeout`、本地持久卷和备份说明。
- Jinja2 server-rendered 中英文 Web + 少量 JavaScript，不引入 SPA。
- 用标准 OIDC client 接入钉钉 OIDC bridge；实施前验证具体库，优先评估 Authlib；所有用例接收 actor 并执行授权。
- 以 package workflow 分页拉取、详情补全、原始快照和数量报告。
- Web/REST/JSON CLI 共用同一 Service Layer。
- 建立 `pytest` + 临时 SQLite + `respx/httpx` mock 测试基线。
- 本阶段只读赛狐，不调用 `submitToPlatform`。

**退出门：** 多对多关系无损；重复拉取幂等；输入总数与保存/跳过/失败完全对账；权限和审计可追踪到用户。

### P1B：蜴国际 Excel 闭环前半段

- 实现版本化 `SpreadsheetCarrierAdapter`。
- 用 `openpyxl` 读写 Excel，以 Pydantic/明确 Python adapter 做模板和逐行校验。
- 包裹审核、批次创建和上传 Excel 导出。
- 保存导出 Artifact hash 和模板版本。
- 导入返回追踪号 Excel，按 `packageSn/客户参考号` 匹配。
- 返回文件如含成本和币种则一并校验、保存；缺失时保留待人工补录状态，不伪造默认币种。
- 文件重复上传幂等；逐行错误、未匹配和冲突完整保留。
- 提供人工复核界面。

**退出门：** 真实样例往返通过；乱序行、重复文件、缺字段、多余行、重复追踪号和未知包裹均有确定结果；N 行完全对账。

### P1C：人工确认、赛狐回写与 VITE spike

- 按本文安全协议实现单条 `submitToPlatform`。
- 一包多单按订单生成 `SubmissionIntent`，每个 intent 的 items 只取对应 `PackageItem`；唯一 request hash + 提交 scope lock + 数据库约束 + 事务/CAS 防重复点击、并发和换字段绕过 UNKNOWN。
- 1 rps 限流、调用前持久化 `CREATED/NOT_SENT` attempt、CAS 后发送；重启或超时遗留 `IN_FLIGHT` 一律转 UNKNOWN。实现 `SUCCESS/VERIFIED` 不重发、`UNKNOWN` 按 scope 阻断、`FAILED` 仅人工按订单重试，以及 §3.3 的穷尽 package 聚合函数。
- 验证回读延迟/权威性；UNKNOWN 不因一次回读自动重试，无法确认时保持 UNKNOWN 并人工介入或使用赛狐官方导入流程。
- 使用测试商品/包裹完成受控端到端闭环，扩大范围前再次由用户确认。
- 在隔离环境按 Karrio extension 规范实现最小 VITE custom connector，并实现等价直接 `httpx` adapter，量化比较代码量与收益；只产出技术决策证据，不切换通途生产、不承诺上线。

**退出门：** 蜴国际受控测试批次端到端核验；无盲重放；VITE 形成通过/不通过结论和生产决策材料。

### P2：PDF、packlist 与 GLS Excel

- 按 PDF 内包裹号匹配，不依赖页序。
- PDF 先文本提取，再以条码/OCR 兜底；最终库依据真实样例验证后确定。
- 保存原始 PDF 与拆分后 Artifact 的 hash、页码和匹配结果。
- packlist 在包裹/标签匹配稳定后实现。
- 用相同 `SpreadsheetCarrierAdapter` 框架支持波兰 GLS Excel。

**退出门：** PDF 页数完全对账；未匹配页不丢失；GLS 真实 Excel 样例通过。

### P3：经决策门启用 API connector / 多账号

- 仅对通过测试门且另获业务批准的 VITE 或其他 connector 启用受控生产范围；P1 spike 通过不等于自动进入 P3。
- CarrierAccount 支持美国两分公司、多账户和结算归属。
- 按真实业务需求评估 GLS API。
- 仅当现有 `channelName` 不足时再评估规则 UI。

**退出门：** 每个生产 connector 都有测试账户契约测试、回滚方案、账户隔离和小范围用户确认。

---

## 11. 明确暂不做

- 不建设第二套完整物流规则引擎；P1 读取赛狐 `channelName`。
- 不建设完整 MCP；先稳定 REST 和 JSON CLI 的领域用例。
- 不引入 Celery/Redis worker。
- 不采用 Karrio Server。
- 不把 VITE 从通途切换到本系统生产。
- 不做静默打印或未经人工确认的自动打印。
- 不在 P1 提前实现 packlist。
- 不因未来可能多实例而提前迁移 PostgreSQL。

---

## 12. 风险与验证门

### 风险 1：蜴国际匹配字段的真实格式不可稳定解析

- **影响：** 虽已确认客户参考号字段会出现在返回 Excel/PDF，但若真实列名、格式或 PDF 呈现不可稳定解析，追踪号仍无法可靠关联包裹，顺序匹配会产生错发。
- **控制：** P0 用真实样例验证具体格式和唯一性；不满足则不得开始自动回写。

### 风险 2：一包多单的 items 边界或聚合错误

- **影响：** 将同包其他订单的 items 混入当前请求会提交错误商品数量；用最后一次 attempt 覆盖 package 状态会把部分失败误报为全部成功。
- **控制：** 每个 intent 只取对应 package-order 的 `PackageItem`；人工 UI 展示 N 个订单级摘要；统一调用 §3.3 的穷尽聚合函数，覆盖 READY、IN_FLIGHT、FAILED、SUCCESS、VERIFIED 和 UNKNOWN 的全部组合。

### 风险 3：重复操作、换字段或崩溃恢复造成重复副作用

- **影响：** 重复追踪号分配或重复提交平台；若只按 request hash 防重，用户改字段即可绕过 UNKNOWN；若进程在发送边界崩溃，盲目恢复会重复副作用。
- **控制：** Artifact hash 幂等；intent canonical request hash 唯一约束；UNKNOWN 按 `(sellfox_account_id, package_id, order_id)` scope 锁定；attempt 先持久化 `CREATED/NOT_SENT`，CAS 成 IN_FLIGHT 后才发送；重启/超时遗留 IN_FLIGHT 一律转 UNKNOWN，不根据本地状态推断未发送。`SUCCESS/VERIFIED` 不重发，`FAILED` 只允许人工按订单新增 attempt。以上不依赖外部接口幂等。

### 风险 4：VITE 文档与测试账户渠道不一致

- **影响：** rate/label 请求失败或走错结算渠道。
- **控制：** 明确测试 `GOFO_PARCEL + GFUS/YT` 与 `GOFO_PX/PARCEL`，禁止猜测映射。

### 风险 5：Karrio connector 版本/成熟度误判

- **影响：** 升级破坏接口，或 GLS 在波兰账户不可用。
- **控制：** core/connector 同版本锁定、隔离 spike、契约测试、不 fork；GLS development 状态不进入 P1。

### 风险 6：SQLite 锁或同步请求耗时

- **影响：** 小团队操作阻塞。
- **控制：** WAL、busy timeout、短事务、持久化阶段状态；用实际指标达到门槛后再升级 worker/PostgreSQL。

### 风险 7：PII、凭证和标签泄露

- **影响：** 地址、电话、API 密钥或面单暴露。
- **控制：** 最小字段、日志脱敏、密钥只用秘密管理/环境注入、Artifact 权限控制、审计和保留期限；报告不输出原始 PII。

### 风险 8：未授权接口直接暴露 PII

- **影响：** 当前应用没有 auth middleware 且绑定 `0.0.0.0`，订单地址、电话、邮箱可能被未授权读取。
- **控制：** 部署前必须完成 OIDC、角色/操作授权和反代 HTTPS；在此之前不得作为共享生产服务开放。

---

## 13. 验收与对账检查表

每个导入/导出/同步操作必须生成机器可读和人可读报告：

```text
operation_id
actor
source_artifact_sha256
template_version
input_count
success_count
skipped_count
failed_count
unmatched_count
reason_counts
row_results[]
started_at / finished_at
```

必须自动校验：

- `input_count == success + skipped + failed + unmatched`；
- success/skipped/failed/unmatched 是互斥顶层分类，每一输入行只进入其中一个；
- 每个失败和未匹配有行号、业务键和原因；
- `duplicate`、`conflict` 等属于某一顶层结果的明确子原因，在 `reason_counts` 中统计，不额外加入顶层求和；例如重复文件行通常是 `skipped: duplicate`，一键多值冲突通常是 `failed: conflict`；
- 必填列全量校验，缺列直接拒绝整个模板，不猜相似列；
- 同一 hash 重传返回既有操作结果；
- 原始 Artifact 只读保留，派生文件创建新 Artifact；
- 每个 package-order 恰有一个当前逻辑 `SubmissionIntent`；其 `request_hash` 可由 `sellfox_account_id/package_id/order_id/tracking_number/carrier_name/shipping_service` 和排序后 `items` 的 canonical request 重算并命中唯一约束；
- unresolved UNKNOWN 的阻断键精确为 `(sellfox_account_id, package_id, order_id)`；同一 scope 修改 `tracking_number/carrier_name/shipping_service/items` 得到新 hash 时，创建和执行新 intent 均必须失败；
- UNKNOWN 只有在记录权威回读/人工调查证据、操作者和时间，并结案为 `VERIFIED` 或 `CONFIRMED_NOT_APPLIED` 后才释放 scope lock；`VERIFIED` 不得产生相同逻辑提交的后继 intent，人工升级仍必须保持阻断；
- 每个 attempt 只属于一个 intent；外部调用前数据库必须已存在 `CREATED/NOT_SENT` 记录，且重复点击/并发只能有一个 CAS 成功把 intent 和 attempt 切为 `IN_FLIGHT`；
- `CREATED/NOT_SENT` 可安全取消或重新进入 CAS；mock 必须证明 CAS 前无 HTTP 调用。启动恢复和超时扫描必须把所有残留 `IN_FLIGHT` 转为 `UNKNOWN` 并按 scope 阻断，且不触发自动重发；
- intent 的 `SUCCESS/VERIFIED` 永不重发；未结案 `UNKNOWN` 阻断该 scope 的所有新建和发送；`FAILED` 只有人工按该订单确认后才能新增 attempt；
- 一包 N 单时，UI 必须展示 N 个订单级提交摘要，且每个摘要的 items 与对应 `PackageItem` 集合完全相等、与其他订单不交叉；
- package 聚合函数必须按 `UNKNOWN > IN_FLIGHT > READY > FAILED > all VERIFIED > all SUCCESS/VERIFIED > BLOCKED` 固定优先级通过单元测试；覆盖六种 intent 状态的每个非空状态子集、代表性重复状态及空集合/非法状态。断言任意含 UNKNOWN（包括单 intent）→ `PARTIAL_UNKNOWN`、IN_FLIGHT → `SUBMITTING`、全 READY → `TRACKING_REVIEWED`、含 READY → `PARTIAL_READY`、全 FAILED → `SUBMIT_FAILED`、含 FAILED → `PARTIAL_FAILED`、全 VERIFIED → `VERIFIED`、全 SUCCESS 或 SUCCESS/VERIFIED 混合 → `SUBMITTED_PENDING_VERIFY`；
- package 状态只能从当前订单级 intent 派生；Web、REST、CLI 和管理员入口均不能手工写入 `VERIFIED` 或其他 package 完成状态；
- 同包失败订单重试不得创建或触发已成功订单的新 attempt；
- 批次结束时仍为 `UNKNOWN/PARTIAL_UNKNOWN/SUBMITTING/PARTIAL_READY/PARTIAL_FAILED/SUBMITTED_PENDING_VERIFY` 或未匹配的记录必须醒目标示，不能把批次显示为全成功。

---

## 14. 来源与可复核证据

### 14.1 仓库内证据

- [`USER-2026-07-16`](#user-2026-07-16)：本文附录中的“2026-07-16 需求澄清决策记录”（本文“用户确认事实”的可访问来源）。
- `[PROJECT-RULES]`：`AGENTS.md`。
- `[LEGACY-HANDOFF]`：`sellfox_shipping/AGENT_HANDOFF.md`（旧阶段描述，仅作为 legacy skeleton 背景）。
- `[EARLY-BRIEFING]`：`sellfox_shipping/docs/research/briefing-for-independent-agent.md`（较早背景，不是后续业务决定来源）。
- `[SF-PKG-LIST]`：`SELLFOX_API/docs/api-reference/订单/订单处理/查询订单处理列表.md`。
- `[SF-PKG-DETAIL]`：`SELLFOX_API/docs/api-reference/订单/订单处理/查询订单处理详情.md`。
- `[SF-SUBMIT]`：`SELLFOX_API/docs/api-reference/订单/订单处理/提交平台.md`。
- `[SF-ORDER-LIST]`：`SELLFOX_API/docs/api-reference/订单/全部订单/订单列表.md`。
- `[SF-ORDER-DETAIL]`：`SELLFOX_API/docs/api-reference/订单/全部订单/订单详情.md`。
- `[CODE-MODELS]`：`sellfox_shipping/models.py`、`sellfox_shipping/store.py`。
- `[CODE-CLIENT]`：`sellfox_shipping/sellfox_client.py`。
- `[CODE-PROXY-AUTH]`：`sellfox-api-proxy/auth.py`。
- `[CODE-APP]`：`sellfox_shipping/app.py`、`sellfox_shipping/mcp_tools.py`、`sellfox_shipping/main.py`。
- `[CODE-CLI]`：`sellfox_shipping/cli.py`。
- `[CODE-CARRIER]`：`sellfox_shipping/carriers/base.py`、`sellfox_shipping/config.yaml`。
- `[CODE-PYPROJECT]`：`pyproject.toml`、`uv.lock`。
- `[CODE-DOCKER]`：`sellfox_shipping/Dockerfile`、`sellfox_shipping/docker-compose.yml`。

### 14.2 VITE

- `[VITE-INITIAL]` 官方 Swagger 最初链接（2026-07-16 访问时默认加载 USPS，不能作为 GOFO 直接证据）：<http://docs.vitedirect.com/?urls.primaryName=Uniuni%20Ground>
- `[VITE-GOFO]` 从官方定义选择器进入的 GOFO Express 配置（访问日期：2026-07-16）：<http://docs.vitedirect.com/?urls.primaryName=GOFO%20Express>

### 14.3 Karrio 版本、SDK 与架构

- `[K-PYPI]` Karrio v2026.1.32 PyPI：<https://pypi.org/project/karrio/2026.1.32/>
- `[K-SDK]` SDK 可独立使用、统一模型及公开 connector 列表：<https://docs.karrio.io/carriers/sdk>
- `[K-EXT]` Custom Carrier / Mapper / Proxy / Settings：<https://docs.karrio.io/carriers/sdk/extension>
- `[K-REPO]` Karrio v2026.1.32 仓库树：<https://github.com/karrioapi/karrio/tree/v2026.1.32/modules/connectors>
- `[K-SERVER]` Server 开发架构（Django、Next.js、PostgreSQL、Redis、worker）：<https://www.karrio.io/docs/developing/local-development>
- Self-hosting 架构：<https://www.karrio.io/docs/self-hosting>
- `[K-INSIDERS]` Insiders 能力边界：<https://docs.karrio.io/insiders>
- `[K-ENTERPRISE]` Enterprise/SSO/审计边界：<https://www.karrio.io/blog/2025-11-30-karrio-2025-5-sustainability>

### 14.4 FedEx connector

- 官方集成能力页：<https://docs.karrio.io/carriers/integrations/fedex>
- `[K-FEDEX-META]` v2026.1.32 插件元数据（production-ready）：<https://github.com/karrioapi/karrio/blob/v2026.1.32/modules/connectors/fedex/karrio/plugins/fedex/__init__.py>
- `[K-FEDEX-MAPPER]` v2026.1.32 Mapper（rate/shipment/return/cancel/tracking/document/pickup）：<https://github.com/karrioapi/karrio/blob/v2026.1.32/modules/connectors/fedex/karrio/mappers/fedex/mapper.py>
- `[K-FEDEX-PROXY]` v2026.1.32 Proxy（对应 HTTP 操作）：<https://github.com/karrioapi/karrio/blob/v2026.1.32/modules/connectors/fedex/karrio/mappers/fedex/proxy.py>
- `[K-FEDEX-SETTINGS]` v2026.1.32 Settings：<https://github.com/karrioapi/karrio/blob/v2026.1.32/modules/connectors/fedex/karrio/mappers/fedex/settings.py>

### 14.5 GLS connector

- `[K-GLS-PYPI]` v2026.1.32 PyPI：<https://pypi.org/project/karrio-gls/2026.1.32/>
- `[K-GLS-META]` 插件元数据（development）：<https://github.com/karrioapi/karrio/blob/v2026.1.32/modules/connectors/gls/karrio/plugins/gls/__init__.py>
- `[K-GLS-SETTINGS]` 默认 `account_country_code="DE"`：<https://github.com/karrioapi/karrio/blob/v2026.1.32/modules/connectors/gls/karrio/mappers/gls/settings.py>
- `[K-GLS-README]` README 安装说明：<https://github.com/karrioapi/karrio/blob/v2026.1.32/modules/connectors/gls/README.md>

---

## 15. 最终判断

本项目的难点不是“接多少家承运人”，而是把**包裹、文件、人工作业和不可逆外部副作用**组织成可追溯闭环。蜴国际 Excel 不是 API 上线前的临时阶段，而是目标架构必须长期支持的一等通道。

因此应先用真实样例建立以内部 `(sellfox_account_id, package_sn)` 为核心、外部 `packageSn` 为对账值的可靠批次工作流，再用同一领域边界接入 API。Karrio 有价值，但价值集中在 connector SDK，不在 Server；它没有现成 VITE/GOFO connector。VITE 测试 spike 的正确含义是比较“最小 Karrio custom connector”与“直接 `httpx` adapter”，而不是假装复用现成能力。实验通过之前不改变通途生产流程；实验通过本身也不构成上线决定。

---

<a id="user-2026-07-16"></a>

## 附录 A：2026-07-16 需求澄清决策记录

> 对话决策摘要，非逐字稿。以下只记录本次对话中已确认、可作为本文范围与验收依据的决定，不把研究判断改写成用户原话。

1. **P1 闭环：** 从赛狐拉取包裹并审核，导出蜴国际 Excel，由人工上传；导入蜴国际返回的追踪号 Excel，按 `packageSn`/客户参考号对账并人工复核，再逐条调用赛狐 `submitToPlatform`，最后回读核验。
2. **试点顺序：** 蜴国际是 P1 首个业务试点；美国使用较多，当前只有 Excel 流程。真实上传 Excel、返回 Excel 和 PDF 样例尚未收集，必须先完成 P0 样例验证。
3. **参考号：** 蜴国际模板有客户参考号字段，且会出现在返回 Excel/PDF；具体列名、格式和可机器解析性仍以真实样例为准。
4. **包裹关系：** 生产中确有少量一单多包和一包多单场景；Excel 行序和 PDF 页序均不可作为匹配依据。后续 PDF 按包裹号匹配，packlist 后置。
5. **物流商选择：** P1 读取赛狐 `channelName`；本地规则引擎只留扩展点，不建设第二套完整规则。
6. **提交安全：** `submitToPlatform` 必须人工确认、单条提交并逐条记录结果；结果未知时不得自动重复提交。
7. **团队与规模：** 使用者位于中国和美国，共享单服务器，约 1–5 人；日常少于 200 包裹，峰值少于 500 包裹；认证采用钉钉 OIDC。
8. **业务记录与界面：** 记录每个包裹/运单的发货成本和币种；Web UI 支持中英文。
9. **系统边界：** 系统作为独立服务，不依赖 ERPNext；Service Layer/REST 为未来 ERPNext app 调用保留接口。
10. **VITE 范围：** VITE 当前主要通过通途 API，大件使用 VITE；P1 只做测试环境 proof/spike，不替换通途、不承诺上线。未来可能按美国两家分公司、多账户分别结算。
11. **Karrio 定位：** 不采用 Karrio Server；Karrio 仅可位于公司防腐层之后，作为可选 API connector SDK。VITE 没有现成 Karrio connector，spike 仅比较最小 custom connector 与直接 `httpx` adapter。
12. **欧洲 GLS：** 欧洲主要使用 GLS，波兰当前走 Excel；可用 API/账户尚待验证，不能预设 Karrio GLS 支持波兰合同。
