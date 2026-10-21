---
okf: v0.1
type: Reference
title: 供应链开源方案来源与版本许可核对
timestamp: 2026-10-20
tags: [sources, OSS, licenses, supply-chain]
---

# 来源与核对记录

访问日统一为 2026-10-20。本文记录本次实际打开的官方一手页面；版本、许可只按页面能支持的范围下结论。发布日期/版本无法从页面确定时明确标注。代码许可和模型权重许可分开处理；本轮推荐的 StatsForecast 为传统统计库，无需下载模型权重；若后续选用神经/基础模型，必须单独登记权重文件的 license card、版本与用法限制。

## 来源台账

| ID | Claim / 来源 | URL / 定位 | 页面日期或版本 | 核验结论与局限 |
|---|---|---|---|---|
| R1 | frePPLe CE 版本、许可变化与 forecasting 进入 CE | [官方 release notes](https://github.com/frePPLe/frepple/blob/master/doc/release-notes.rst)，8.0.0 段 | 8.0.0 / 2023-06-03 | 已核验：8 起 CE 由 AGPL 转 MIT，forecasting 移入 CE；只用此页确认历史变更，不推断更细的现行版本功能。 |
| R2 | frePPLe 功能概览（方向参考） | [官方 feature 文档](https://frepple.com/docs/current/features.html)，Production planning/Capacity planning 小节 | 文档版本 10.0.0，upcoming/preview | 页面已打开，但仅用作未来功能/定位参考；不能证明 9.19 CE 能力。 |
| R3 | frePPLe 通用 ERP 接口 | [Generic ERP connector](https://frepple.com/docs/current/erp-integration/generic-erp-connector.html)，L28–73 | 文档版本 10.0.0，upcoming/preview | 页面已打开；示例是需自定义提取 SQL/适配器和回写代码的骨架，不是 EN/Tongtool/Sellfox 现成连接器。 |
| R4 | Odoo 长周期 MPS | [Odoo 官方 18.0 MPS 文档](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/manufacturing/workflows/use_mps.html) | Odoo 18.0 文档 | 页面打开失败；搜索摘要不作为已核实证据，计入访问失败。 |
| R5 | Odoo CE/EE 许可差异 | [Odoo 官方许可证说明](https://www.odoo.com/documentation/17.0/legal/licenses.html)，CE/EE 小节 | Odoo 17 文档 | 页面打开超时；搜索摘要不足以核实，计入访问失败。 |
| R6 | ERPNext MRP/MPS/Forecast/Lead Time | [ERPNext 官方 MRP 文档](https://docs.frappe.io/erpnext/material-requirements-planning-mrp)，L2146–2185 | 页面 last updated 约 2026-04（页面显示 6 months ago） | 已核验：文档描述 MRP 以 SO/MR 为短期需求、较长期需求需手工输入 forecast；MPS 汇总 SO/MR/forecast/delivery schedules；MRP 依 BOM 和 item lead time。需对照现用 v15/v16 部署。 |
| R7 | 本地履约主键与头程事件模型（业务上下文） | [仓库履约蓝图](../../solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md)，第 2、6、7、10 节 | 仓库文档日期 2026-09-15 | 本地参考已读，用于避免把头程、套件和业务口径说错；它不是 OSS 候选产品证据，且本次独立判断没有继承其最终架构结论。 |
| R8 | Google OR-Tools 能力 | [Google 官方优化文档](https://developers.google.com/optimization)，About 段 | 官方站，访问时内容未显示版本 | 已核验：约束/组合优化 SDK，支持 routing、flows、integer/linear/constraint programming，内含 CP-SAT；产品本身不含供应链语义、审批 UI 或 ERP 连接。具体语言 binding 和版本须锁定。 |
| R9 | Stockpyl 代码许可和算法范围 | [Stockpyl 官方 GitHub](https://github.com/LarrySnyder/stockpyl)，README 的能力、资源及 License 段（R12 为同页算法段的第二项 claim，不重复计 source） | README 引用 2023 论文/教材；当前 tag 未在摘录中核 | 已核验 MIT、单级 EOQ/newsvendor/Wagner-Whitin、多级 SSM/GSM 与仿真；维护规模/响应支持未由本页足以证明，按研究库而不是 APS 评估。 |
| R10 | ERPNext 支持版本 | [Frappe 官方版本支持表](https://github.com/frappe/erpnext/wiki/Supported-Versions)，L130–138 | 页面由维护者于 2026-01-19 编辑 | 已核验规划性 EOL：v14 2026-01-31、v15 2027 年底、v16 2029 年底；不是服务 SLA，日期仍可能更新。 |
| R11 | StatsForecast 统计预测方法 | [Nixtla 官方源代码 README](https://github.com/Nixtla/statsforecast/blob/main/README.md)，模型表与 Quick Start | `main` 分支；访问日 2026-10-20 | 已核验 AutoARIMA/ETS/CES/Theta 与基线；另见官方 License 链接为 Apache-2.0。传统统计方法，无单独模型权重文件；分支是滚动版本，生产需 pin release。 |
| R12 | Stockpyl 算法和 MIT | [Stockpyl README](https://github.com/LarrySnyder/stockpyl)，L216–272 | README 当前页面；学术引文 2023 | 已核验其方法边界与 MIT；不是有审批、数据接入和用户权限的完整产品。 |
| R13 | DuckDB 部署模型、客户端许可与支持分层 | [DuckDB Client Overview](https://duckdb.org/docs/lts/clients/overview)，L459–484 | 文档当前 LTS 1.4.5 | 已核验 in-process 数据库、官方核心客户端 MIT、Primary/Secondary/Tertiary 支持分层；适合单机分析/试验，不能据此当并发 OLTP。 |
| R14 | dbt OSS 许可/版本变化 | [dbt 官方 release notes](https://github.com/dbt-labs/docs.getdbt.com/blob/current/website/docs/docs/dbt-versions/release-notes.md)，2026 命名/版本小节 | 页面包含 2026 年发布信息，`dbt`/`dbt OSS` 命名 | 已核验项目公布其开源 Apache-2.0 发行路径和新旧名称变化；dbt 平台/商业功能不应和 OSS Core 混算。核实际二进制/包与 adapter 兼容性。 |
| R15 | Metabase OSS/Enterprise 许可和嵌入 | [Metabase 官方许可证页](https://www.metabase.com/license)，L54–88 | 页面访问时现行条款；商业版页面日期见链接 | 已核验 OSS AGPL；嵌入可按 AGPL、保留标识的 embedding license 或商业许可处理；Enterprise 源码可见不代表免费使用 Enterprise 功能。 |
| R16 | Apache Superset 能力和本地部署边界 | [Superset 官方文档](https://superset.apache.org/docs/)，功能概览；[Quickstart](https://superset.apache.org/user-docs/quickstart/) | Quickstart 固定到 6.0.0 示例；访问 2026-10-20 | 已核验 SQL 引擎/语义层/BI 能力和 Docker Compose 不适用于生产的提示；具体 release LICENSE 需锁 tag 再核。 |
| R17 | 现有 Agent 工具基线 | [AI Access POC Open WebUI handoff](../../../ai_access_poc/open_webui/AGENT_HANDOFF.md)，目标、工具、边界章节；[Board handoff](../../../ai_access_poc/board/AGENT_HANDOFF.md) | 仓库交接快照 2026-07-24 / 2026-07-28 | 已核验仓库已有赛狐只读 Tool / Agent 界面方向；这不是供应链计划系统，也不授权扩大写权限。 |
| R18 | ERPNext Production Plan 实际流程 | [官方 Production Plan 文档](https://docs.frappe.io/erpnext/production-plan)，L2146–2193 及后续物料计划章节 | 当前官方文档，页面更新日期未显示 | 已核验可从 SO/MR 生成计划、按 BOM 获取带 BOM 的 item、展开子装配、合并相同 BOM，并规划采购/调拨；具体控产/冻结/审批须看使用版本。 |
| R19 | frePPLe 正式稳定版本 | [官方 GitHub Releases](https://github.com/frePPLe/frepple/releases)，9.19.0 条目 | 9.19.0 Community Edition，2026-10-09 发布 | 已核验版本、CE 标签与发行镜像/安装包资产；不以 stars 或单次发布时间证明成熟。 |
| R20 | frePPLe CE/EE 代码许可 | [frePPLe 官方 License 文档](https://frepple.com/docs/current/license.html)，L25–36 | current 文档页 | 已核验 CE MIT、Enterprise 专有商业许可，扩展源代码不随 EE 再分发；部署时仍须对锁定 tag 的 LICENSE 做法务复核。 |
| R21 | frePPLe 库存规划 edition 边界 | [9.19.0 固定 tag Inventory planning screen source](https://raw.githubusercontent.com/frePPLe/frepple/9.19.0/doc/user-interface/plan-analysis/inventory-planning.rst)，Important 段；[9.19.0 固定 tag Inventory planning model app source](https://raw.githubusercontent.com/frePPLe/frepple/9.19.0/doc/modeling-wizard/inventory-planning/index.rst)，Important 段 | 源码固定 `9.19.0` tag；访问日 2026-10-20 | 已直接打开并核验：screen 只在 Enterprise/Cloud；inventory policy model app 只在 Enterprise。CE 仍须按批次验证实际可用库存策略和建议解释。 |
| R22 | frePPLe 统计预测 UI 范围 | [Demand forecasting app](https://frepple.com/docs/current/apps/forecast.html) | 页面版本 10.0.0 | 页面对统计预测及预测编辑器有说明；10.0 文档不独立证明 9.19 CE，CE 许可/功能迁入证据限 R1。 |
| R23 | OpenBoxes 许可和定位 | [OpenBoxes 官方 GitHub README](https://github.com/openboxes/openboxes)，WMS 与 License 段 | `develop` 页面，EPL-1.0 | 已核验 WMS/库存和货物移动定位及 EPL-1.0；README 所称 general-purpose 不等于预测/APS 已覆盖。 |
| R24 | GreaterWMS 仓储能力与许可声明 | [GreaterWMS 官方 GitHub README](https://github.com/Briliant-wang/GreaterWMS_Software/blob/main/README.md)，L194–206 | `main` 页面，日期未显示 | README 声明 Apache-2.0 和多仓/波次/组合拣货；选用前对照锁定源仓/tag 的 LICENSE 和部署文档。 |
| R25 | Inventory Planner 商品补货流程 | [官方 101 手册](https://help.inventory-planner.com/en/articles/3456738-inventory-planner-101)，采购建议和批发零售章节 | 页面显示 9 months ago | 已核验功能范围，仅作商业对照；不是开源，费用和本公司连接器均未核。 |
| R26 | Inventory Planner 补货日期与在途库存 | [官方 Replenishment 手册](https://help.inventory-planner.com/en/articles/589017-replenishment)，L29–48 | 页面显示 8 months ago | 已核验其根据 forecast、现有库存、lead time、在途采购和 ETA 形成建议；variant 粒度不等于制造 BOM 计划。 |
| R27 | LangGraph 功能、持久化和许可 | [LangGraph 官方 GitHub](https://github.com/langchain-ai/langgraph)，README 和 License | `main`，访问 2026-10-20 | 已核验状态化 workflow、durable execution、人审/HITL、MIT；checkpoint、部署和可观测性仍有维护成本。 |
| R28 | OpenAI Agents SDK 功能与许可证 | [官方仓库](https://github.com/openai/openai-agents-python)；[SDK 文档](https://openai.github.io/openai-agents-python/) | 当前 main/docs | 已核验 MIT；提供 tools、guardrails、handoffs、sessions、人审、tracing，并支持多种模型接口。运行依赖模型 API 费用及 trace 数据策略。 |
| R29 | OpenAI Agents SDK guardrail 边界 | [官方 guardrails 文档](https://github.com/openai/openai-agents-python/blob/main/docs/guardrails.md) | 当前 main | 已核验：tool guardrails 不覆盖所有 hosted tool 和 handoff 路径；不能将其作为写入安全边界。 |
| R30 | Open WebUI 当前许可 | [Open WebUI 官方 license 文档](https://github.com/open-webui/docs/blob/main/docs/license.mdx)，v0.6.6+ | v0.6.6 起 / 2025-04-19 | 已核验许可按贡献/版本有 MIT、BSD-3 和新许可；新版本带品牌条款，≤50 用户/30 天内部部署例外；必须依部署版本核许可。 |
| R31 | MCP Python SDK 功能与许可 | [官方 Python SDK GitHub](https://github.com/modelcontextprotocol/python-sdk)，README 与 License | `main` 页面；README 要求 Python 3.11+ | 已核验官方 server/client SDK、多种 transport、MIT；大版本改动中，需固定版本与客户端兼容性；协议 SDK 不等于业务安全边界。 |
| R32 | LangGraph 持久化与人审 | [LangGraph 官方 durable execution 文档](https://docs.langchain.com/oss/python/langgraph/durable-execution) | 现行官方文档 | 已核验 checkpoint/HITL/恢复设计目标；托管观测平台为可选项，不能假设免费或自托管。 |
| R33 | frePPLe Community 计划范围 | [官方 Editions 页面](https://frepple.com/editions/)，L24–69 | 页面访问日 2026-10-20；网页不标软件发行 tag | 已核验 Community 列有限物料/产能计划、统计预测、CSV/Excel/REST API 和 what-if scenarios；页面不列完整具体 release 号，因此与 9.19.0 release label 一起解读，仍需锁 tag 试用。 |
| R34 | Odoo 18 MPS 预测与补货边界 | [Odoo 官方 18.0 文档固定分支原文](https://raw.githubusercontent.com/odoo/documentation/18.0/content/applications/inventory_and_mrp/manufacturing/workflows/use_mps.rst)，L15–34，及 replenishment quantity 公式 L196–210 | Odoo 18.0 文档分支；访问日 2026-10-20，文件未标发布日期 | 已直接打开核验：需求 forecast 手工可调，仅把产品加入MPS不会创建PO/MO；同文后部Replenishment Trigger另列Manual/Automatic/Never，不能概括成所有场景永远人工。文档警告不要给 MPS 商品同时用 reordering rules，否则预测不准并可能多余补货。MPS 所属 edition 未在所引段落确定。旧网页 URL R4 仍记录访问失败。 |
| R35 | Odoo 18 核心仓库 LICENSE | [Odoo 官方 18.0 固定分支 LICENSE](https://raw.githubusercontent.com/odoo/odoo/18.0/LICENSE)，开头 L1–9 | Odoo 18.0 源码分支；LGPLv3；访问日 2026-10-20 | 已直接打开核验该仓库声明 LGPLv3，且指出部分外部库/贡献可使用其他兼容许可，需逐项检查。此 LICENSE 不能单独证明 MPS 的 edition、CE/EE 功能边界或商业版代码许可。旧 17.0 官方法律页 R5 仍记录访问失败。 |

## 互斥计数对账

- 唯一来源 URL 数：**38**（R1–R35 去重；R9/R12 同 URL，R16/R17/R21/R28 各含两个 URL）；35 个外部 URL、3 个本地上下文 URL。
- 已打开并核实来源：**33**（外部 URL 中除两个原始 Odoo 页面外；R2/R3/R22/R32 只用于其注明的版本/范围）。
- 待核实来源：**0**。
- 排除来源：**3 个本地 URL**（R7、R17 两条记录共含 3 个仓库内上下文链接，不算外部 OSS 产品证据）。
- 访问失败来源：**2**（R4、R5 Odoo 官方页面打开失败）。
- 互斥校验：**33 个已核实外部 + 0 个待核外部 + 3 个排除本地 + 2 个访问失败外部 = 38 个唯一来源 URL**。产品/项目候选另按报告矩阵评估；来源 URL 不能直接按产品计数。本次实际打开并核对的外部官方页面 **33** 个，超过至少 12 个要求。

## 产品候选计数

按报告矩阵中的独立软件/SDK（ERPNext、frePPLe、Odoo、OR-Tools、Stockpyl、StatsForecast、DuckDB、dbt、Superset、Metabase、OpenBoxes、GreaterWMS、Inventory Planner、LangGraph、OpenAI Agents SDK、MCP Python SDK、Open WebUI）计 **17** 个；每项按它声称的用途计状态，不把仓储产品冒充 APS。

- 已核实定位及适用范围：**14**（ERPNext、frePPLe、OR-Tools、Stockpyl、StatsForecast、DuckDB、dbt、Superset、Metabase、OpenBoxes、LangGraph、OpenAI Agents SDK、MCP Python SDK、Open WebUI）；GreaterWMS 已核定位，但当前版本 LICENSE 待核。
- 待核实：**3**（Odoo MPS 所属 edition/CE-EE 功能与许可边界；GreaterWMS 锁定版本 LICENSE/部署边界；Inventory Planner 对三系统/多渠道/BOM 制造的适配与 TCO）。
- 访问失败：**0**（候选层面的 Odoo 当前证据不足归待核；仅 R4/R5 原始 URL 仍属于访问失败来源）。
- 排除：**0**（未从候选登记中静默删除项目；OpenBoxes/GreaterWMS 仅作为 WMS 比较，不作计划中枢）。
- 互斥校验：**14 + 3 + 0 + 0 = 17**。
