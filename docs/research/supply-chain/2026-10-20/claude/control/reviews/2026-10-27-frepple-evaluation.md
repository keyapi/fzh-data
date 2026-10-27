---
okf: v0.1
type: Review
title: frePPLe 评估：移植逻辑 / 借用逻辑 / 直接集成
date: 2026-10-27
owner: claude
status: research-only
scope: 需求预测 / 库存规划 / 承诺交期 / W1 供应时间线 / W2 交期与运输方式 / W3 决策就绪供应接口
tags: [frepple, supply-chain, license, erpnext, frappe, make-vs-buy, aps, mrp]
---

# frePPLe 评估：移植逻辑 / 借用逻辑 / 直接集成

> **结论先行**：frePPLe 是「计划/优化器 + 一套可读的 MIT 算法实现」，不是「供应证据时间线」。
> 它不解决我们的证据/未知/血缘问题；**预测、库存政策、交期配置、供应净额项目里都已有资产**（见
> [已有资产审计](2026-10-27-existing-assets-forecast-inventory.md)）。
> **建议：复用 `self_fulfilled_demand/forecast.py`（statsforecast 2.1.1）、`inventory_policy.py`、
> `leadtime_config.py`、`supply_netting/`；frePPLe 只在“约束分配/CTP 试算”时借逻辑，不部署、不接 EN。**
>
> 依据与边界见下；所有关键事实带原始 URL。标「事实」的是官方文档/仓库原文，标「推断」的是基于事实的判断，
> 标「未核实」的是公开信息冲突或没有一手来源。

> **2026-10-27 修订（回应第二轮反馈 + 资产审计）**：本版把“使用 frePPLe 系统”与“借用/移植其逻辑”分开，
> 并在盘点后确认：**预测已装 statsforecast 并跑过；库存规划已有评估器和结论；交期已有契约；净额已有引擎。**
> 因此“订单日期必填”等硬阻抗只在“跑系统/照搬模型”时成立；借算法时不成立（见 §5.2 开头）。
> 现成 EN 连接器**有代码可读**，只是不可直接安装（见 §4）；承诺交期是什么、要不要做，见 §3.2 ②。

---

## 0. 结论摘要

| 问题 | 结论 |
|---|---|
| 当前版本 | 稳定版 **9.19.0**（2026-10-09）；`docs/current` 是 **10.0.0 预览**（未发布，计划 2026 年底，含不兼容变更）。 |
| 许可证 | 社区版 **MIT**（8.0 起，2023-06-03）；**7.x 及更早是 AGPLv3**；企业版/云版闭源商业许可。 |
| 能否嵌入 EN | 法律上社区版 MIT 允许（保留版权声明）；工程上不建议——现成 ERPNext 连接器**自 2022-02 起未更新**。**但它的实体映射代码可读可借**（§4/§6.5）。 |
| 功能匹配 | W1 证据时间线：**不适合整套**；需求预测/库存规划：**项目已有资产，不要重造**；W3 可售日/情景：**借 lead-time offset + allocation**，不必跑系统。 |
| 现成集成 | 有第三方 ERPNext 连接器代码（LICENSE **GPL-3.0**，2022-02 后未更新），**可读、可借实体映射，不可直接安装**；Frappe Marketplace 无上架。 |
| 最小接入 | **只借逻辑：0 部署**；要做对照验证才需要 Docker + PostgreSQL + 7–9 张 CSV（§8，可选）。 |
| 最终判断 | **值得深入的是“逻辑移植”，不是“集成 frePPLe”。** 预测/交期/净额复用已有；先补库存政策表；CTP 按需。 |

> **术语速查**：
> **需求预测**=未来卖多少；**库存规划**=安全库存/补货点/缺货风险；**可售日**=现在下单哪天能用；
> **承诺交期（CTP/ATP）**=客户问“最快哪天能交”，系统反推可行日（不是简单的“下单日+交期”）；
> **pegging**=把每一份供给和需求一一对应；**allocation**=缺货时按优先级/公平原则分配。

---

## 1. 版本、发行方式与可获取性

### 1.1 事实

- **稳定版 9.19.0**，发布于 **2026-10-09**；官方 Release 提供 Docker 镜像
  `ghcr.io/frepple/frepple:9.19.0` 与 Ubuntu 24.04 `.deb`。
  来源：<https://api.github.com/repos/frepple/frepple/releases/latest>、
  <https://frepple.com/docs/current/release-notes.html>
- **源码仓库活跃**：`frepple/frepple`，默认分支 `master`，最近 push **2026-10-26**，771 stars。
  来源：<https://api.github.com/repos/frepple/frepple>、<https://github.com/frePPLe/frepple>
- **`docs/current` 对应 10.0.0**（文档页标题即 “frePPLe 10.0.0 documentation”），但 10.0.0 **尚未发布**：
  官方 release notes 写 “This release is scheduled for the end of 2026”，并明确会有
  “bigger and backward incompatible changes”，且 **10.0 起只发容器镜像**。
  来源：<https://frepple.com/docs/current/index.html>、
  <https://frepple.com/docs/current/release-notes.html>
- **三种发行形态**：
  - Community：自托管、开源、社区支持；
  - Cloud：frePPLe 托管、闭源、付费；
  - Enterprise：客户自托管、闭源、付费。
  来源：<https://frepple.com/editions/>、<https://frepple.com/downloads/>
- **获取方式**：GitHub Release（源码/包）、`ghcr.io/frepple/frepple-community:latest`（社区镜像）、
  企业版私有仓库（需授权）。来源：<https://frepple.com/downloads/>
- **部署形态**：容器 + **外部 PostgreSQL**；官方 compose 示例用 `postgres:16`，容器暴露 80 端口，
  通过 `POSTGRES_HOST/PORT/USER/PASSWORD/DBNAME` 连接。
  来源：<https://frepple.com/docs/current/installation-guide/advanced/docker-compose.php>、
  <https://frepple.com/docs/current/installation-guide/index.html>

### 1.2 推断 / 提醒

- **不要把 10.0.0 预览当稳定版做原型**。文档站是 10.0 预览，字段/参数可能和 9.19 有差异；
  真要做 B，钉死 **9.19.0** 镜像与对应源码标签。
- 社区版功能不要按 `docs/current` 的“功能大全”推断。文档覆盖整个产品（含商业功能），
  版次差异要以 editions 页与功能页的 “only available in Enterprise and Cloud” 字样为准。

---

## 2. 许可证专节（单独结论）

### 2.1 事实

| 版本/形态 | 许可证 | 证据 |
|---|---|---|
| Community **≥ 8.0** | **MIT** | 仓库根 `COPYING` 为 MIT 文本，并写明双许可：<https://raw.githubusercontent.com/frePPLe/frepple/master/COPYING> |
| Community **7.0** | **AGPL v3** | 7.0.0 的 `COPYING` 为 “GNU Affero General Public License Version 3”：<https://raw.githubusercontent.com/frePPLe/frepple/7.0.0/COPYING> |
| 企业版 / 云版 | 商业闭源，源码不随附 | 官方 License 页：<https://frepple.com/docs/current/license.html> |
| OEM | 可另购商业 OEM 许可 | 同上 |
| Community 8.0 变更公告 | “The license changes from AGPL to MIT”，2023-06-03 | <https://frepple.com/v8-0/> |

官方 License 页对 MIT 的表述是 “a very permissive license that allows any use of the software
(including reuse within proprietary software)”，条件是保留版权与许可声明。
（事实：原文；解读：对“嵌入 EN/闭源分发”不构成障碍。）

### 2.2 对我们的影响（推断，非法律意见）

1. **用 8.0+ 社区版做集成/嵌入**：MIT 允许，保留 `COPYING` 与版权声明即可；不需要开源我们的 EN 自定义 app。
2. **抄 7.x 及更早的代码**：那些代码是 **AGPLv3**。AGPL 的网络使用条款会要求向通过网络交互的用户提供源码；
   即使只是“借鉴实现”，只要构成受版权保护的复制，就有传染风险。**只借概念/算法思想可以；不要复制旧版代码。**
3. **社区版依赖的第三方库**：本次未逐项审计（Django/PostgreSQL 等各有许可）。
   若要把 frePPLe 容器分发给我们以外的主体，需再做一次依赖许可清单。**未核实项。**
4. **ERPNext 连接器是 GPL-3.0**：内部使用不触发分发义务；若把它打包给客户/外部部署，GPL 义务适用。
   ERPNext 本身是 GPL-3.0，Frappe Framework 是 MIT（<https://api.github.com/repos/frappe/erpnext>、
   <https://api.github.com/repos/frappe/frappe>），与 frePPLe MIT 无冲突。
5. **“AGPL 会不会污染 EN”**：如果我们只是**通过 REST/CSV 调用** 8.0+ frePPLe，不复制其代码，
   不构成衍生作品；MIT 本身也已足够宽松。真正的 AGPL 风险只来自复制旧版代码。

---

## 3. 功能映射：frePPLe ↔ 我们的需求（预测 / 库存 / W1 / W2 / W3）

> 判定口径：**可直接用**＝不改模型/流程即可覆盖；**需改造**＝要补字段、补上游数据或换用法；
> **不适合**＝目标不同或会引入错误假设。

### 3.1 总表

| # | frePPLe 能力 | 官方事实（摘要） | 对应我们的需求 | 判定 |
|---:|---|---|---|---|
| 1 | 需求预测 | 统计方法（constant/trend/seasonal/intermittent/moving average），自动选优、异常值、层级预测、SO 冲减 | 我们需要预测（分析侧/补货） | **可借逻辑**；源码在社区版，或用更成熟的 `statsforecast` |
| 2 | 供应计划 / 分配 | 约束/非约束/智能非约束；按优先级与到期日回溯，失败再前推；fair-share 短缺分配 | W3 的缺口与“现在下单何时可用” | **可借逻辑**；quoting UI 是商业版，但社区 solver 有 quote/inquiry 状态 |
| 3 | 库存 / 分销 | buffer onhand/min/max、安全库存、补货量、再平衡、push replenishment | 我们需要库存规划（安全库存/补货/风险） | **算法可借**（buffer + shortage solver）；**库存规划 app 不在社区版**，政策层自建 |
| 4 | BOM / 生产 | operation/BOM 版本、替代料、联副产品、MO/WO、最小批量/倍数 | W1 的 `in_production` 阶段 | **需改造（超配）** |
| 5 | 产能 / 排程 | 资源、日历、换型矩阵、瓶颈、交互 Gantt | 非目标（不做全厂精细排程） | **不适合** |
| 6 | 提前期 / 运输方式 | `itemdistribution.leadtime/cost/priority`；`itemsupplier.leadtime`；operation `duration/duration_per/posttime` | W2 的分段交期与慢船/快船/空运 | **借字段模型**；分段/版本/来源自建 |
| 7 | what-if / 情景 | 情景=数据库副本；选情景查看；本地默认 3 个、云 6 个 | W3 的运输方式并列选项 | **借思路**；我们按方案并行算，不需要复制数据库 |
| 8 | 事件时间线 | 无事件溯源；有计划层 `operationplan.start/end`、pegging、Demand Gantt | W1 的单据级 `event_date/available_date/血缘` | **不适合** |
| 9 | REST / 数据模型 | REST（Django REST Framework）、CSV/Excel 导入、DB 访问、命令行、嵌入 | 本地 DuckDB → frePPLe；结果回 Parquet | **可直接用** |
| 10 | 完整性巡检（W4） | Problem report 针对“建好的计划模型”（缺补货方法、资源过载等） | EN 单据不一致（DN 无运单等） | **不适合** |

### 3.2 逐项说明

#### ① 需求预测

- 事实：社区版包含**完整的需求预测实现**（8.0 公告写 “The forecast module goes open source”；editions 页把
  “Demand forecasting” 列为 Community 能力）。方法包括
  `automatic / constant / trend / seasonal / intermittent / moving average / manual / aggregate`；
  源码在 `src/forecast/forecastsolver.cpp`、`src/forecast/timeseries.cpp`、`src/forecast/measure_compute.cpp`，
  Python 侧在 `freppledb/forecast/models.py`、`freppledb/forecast/services.py`（含预测冲减/重新预测）。
  链接：<https://frepple.com/docs/current/features.html>、<https://frepple.com/v8-0/>、
  <https://github.com/frePPLe/frepple/tree/master/src/forecast>
- 源码事实：C++ 实现里有 Croston（`Croston_initialAlfa` 等参数）、季节性 Holt-Winters、移动平均、
  离群值阈值（`Outlier_maxDeviation`）、SMAPE 权重（`Forecast_SmapeAlfa`）；Python 模型里有
  `method=automatic` 和 SO 冲减相关逻辑。
- 对我们：**需要预测，且已经落地**：`self_fulfilled_demand/forecast.py` 用 statsforecast 2.1.1 的
  AutoETS + MA3/naive guard，已有实际 run `forecast-20261027-r2`（2,413/2,423 可预测，45 tests）。
  前一轮 T2/T5/A 包已经做过方法对照；**不要再选型/重跑对照**。
- 判定：**已有实现，不需要 frePPLe。** frePPLe 的预测代码只作规则参考（自动选优/离群值/SO 冲减）。

#### ② 供应计划 / 分配 / 承诺交期（CTP）

- **先解释“承诺交期”是什么**：客户/业务问“我现在要 100 件，最快哪天能交？”系统在
  现有库存、已承诺订单、在途、产能和交期约束下，反算“最早可行交付日 + 卡在哪”。
  它**不等于**“下单日 + 交期”：后者是正向 lead-time offset（我们 W3 的慢船/快船/空运可售日）；
  前者是带约束的反向可行性判断（CTP/ATP）。**如果我们只算“现在下单各方式何时到”，不需要 CTP。**
- 事实：frePPLe 的 quoting screen 只在 Enterprise/Cloud；但社区版 solver 已支持
  `Demand::STATUS_QUOTE` / `STATUS_INQUIRY`，报价/询价需求会作为**低优先级 trial demand** 参与排程
  （见 `src/solver/solverdemand.cpp`、`src/solver/solverplan.cpp`、`include/frepple/model.h`）。
  也就是说：**CTP 的“试算”机制在社区源码里，缺的是报价 UI/业务流程。**
- 来源：<https://frepple.com/docs/current/user-interface/plan-analysis/quoting-screen.html>、
  <https://github.com/frePPLe/frepple/blob/master/src/solver/solverdemand.cpp>
- 对我们：正向可售日已有 `sc13/leadtime_config.py`（W2 版本化契约；当前只有 assumed 样例）；
  若销售/客服确实要“承诺日”，再把 trial demand 机制移植成一次“影子计划”，不引入 frePPLe 系统。
- 判定：**已有正向可售日；CTP 可借逻辑，但先不做，除非业务明确需要承诺日。**

#### ③ 库存 / 分销

- 事实：社区版有 buffer `onhand / minimum / maximum / minimum_calendar / maximum_calendar`，
  安全库存/短缺求解在 `src/solver/solverbuffer.cpp`（`solveSafetyStock`、短缺口检测、min/max 补货），
  库存水平计算在 `src/model/buffer.cpp`（`getOnHand(..., use_safetystock)`）。来源：
  <https://frepple.com/docs/current/model-reference/buffers.html>、
  <https://github.com/frePPLe/frepple/blob/master/src/solver/solverbuffer.cpp>
- 事实：**专门的 Inventory Planning 应用不在社区仓库**。`freppledb.inventoryplanning` 只被
  `if "freppledb.inventoryplanning" in settings.INSTALLED_APPS` 条件引用，目录不存在；
  官方页明确该模块 “only available in the Enterprise and Cloud Editions”。
  来源：<https://frepple.com/docs/current/user-interface/plan-analysis/inventory-planning.html>
- 对我们：**需要库存规划，且已有研究/评估器**：`inventory_policy.py`（order-up-to 参照、β/α、L+R）+
  `sc08_conformal.py`（经验/共形分位）+ SC08 服务—库存前沿。已有结论：现行规则 β **0.63–0.84**；
  经验分位 τ90–95 可到 **0.83–0.91**，代价库存 **2.4–4.6×**；**硬 95% 在可接受库存内不可行**
  （要稳过 95% 需 τ99、库存 8.8–40×）。缺的是**生产政策表**，不是算法。
- 判定：**复用已有；不要重造。** frePPLe 的 buffer min/max/短缺语义只作参考，不值得为它部署。

#### ④ BOM / 生产

- 事实：operation 支持固定时长、按量时长、routing、替代、拆分；BOM 版本、替代料、联副产品、
  MO/WO、最小批量/倍数、`posttime`。来源：
  <https://frepple.com/docs/current/features.html>、
  <https://frepple.com/docs/current/model-reference/operations.html>
- 对我们：W1 的 `in_production` 只需要“单据级剩余量 + 预计完工”；frePPLe 要把它变成
  operationplan，需要先建 operation/routing 模型，粒度明显超配。
- 判定：**需改造（超配）**。W1 v0 不建议为此建 BOM 产能模型。

#### ⑤ 产能 / 排程

- 事实：资源、班次日历、技能、替代资源、换型矩阵、瓶颈、交互 Gantt。
  来源：<https://frepple.com/docs/current/features.html>、<https://frepple.com/editions/>
- 对我们：明确非目标（不做全厂精细排程）。
- 判定：**不适合**。

#### ⑥ 提前期 / 运输方式

- 事实：`itemdistribution` 字段只有**单段 `leadtime`**，外加 `cost / priority / size_* / resource / resource_qty`；
  **没有 transport mode 字段**。来源：
  <https://frepple.com/docs/current/model-reference/item-distributions.html>
- 事实：`distributionorder` 有 `shipping date / receipt date`、`origin / destination`；
  **origin 留空表示“已离源、在途”**，destination 收货即增加库存。来源：
  <https://frepple.com/docs/current/model-reference/distribution-orders.html>
- 事实：生产提前期 = operation `duration + quantity × duration_per`，可加 `posttime` 软缓冲。
  来源：<https://frepple.com/docs/current/model-reference/operations.html>
- 推断：慢船/快船/空运应建模为**同一起讫点的多条 itemdistribution**（不同 leadtime/cost/priority），
  solver 按 priority/成本选一条；它不是“同时给出三个日期”。
- 对我们：W2 要的是**分段**（order→departure→arrival→stock）+ **来源/版本/样本数**（measured/assumed/business）。
  frePPLe 既没有分段字段，也没有 provenance/version。可以用两条腿（工厂→港、港→仓）模拟分段，
  但“假设 vs 实测、配置版本、负责人”必须在我们自己的 W2 配置层维护。
- 判定：**只借模型（lane + leadtime + cost + priority），W2 配置层自建**。

#### ⑦ what-if / 情景

- 事实：情景是**独立数据库副本**；`Copy / Restore / Release / Promote`；本地默认 3 个、云 6 个；
  页面没有专门的并排比较工具，靠切换情景查看。来源：
  <https://frepple.com/docs/current/user-interface/what-if-scenarios.html>
- 对我们：W3 的“慢船/快船/空运三选项”可以用 3 个情景各跑一次；但每日批量跑、并排对比、
  把结果对齐到 `supply_confirmed/expected/unknown` 都要自己做。
- 判定：**需改造**。适合人工探索，不适合作为每日决策接口。

#### ⑧ 事件时间线

- 事实：frePPLe 的核心是**计划**（operationplan 有 `start/end`、`quantity`、`demands` pegging），
  Demand Gantt 按需求展示上游活动；没有“单据事件表/事件溯源”这一层。
  来源：<https://frepple.com/docs/current/features.html>、
  <https://frepple.com/docs/current/user-interface/plan-analysis/supply-path-where-used.html>、
  Demand Gantt：<https://frepple.com/docs/current/user-interface/plan-analysis/demand-gantt-report.html>
- 对我们：W1 的每个数量要能回溯到 `doc_type/doc_name/doc_line/source_key`，并区分
  `confirmed/estimated/unknown`；frePPLe 只存“订单状态 + 日期”，不保存原始事件与血缘，
  更不表达“未知日期”。
- 判定：**不适合**。这正是我们自建 W1 的原因，不要指望 frePPLe 替我们做证据层。

#### ⑨ REST / 数据模型

- 事实：REST API 基于 Django REST Framework，浏览器内 `API Help` 列出全部 URL/方法；
  支持 Basic/JWT/API Key；`GET/POST/PUT/PATCH/DELETE`；示例数据端点为 `/api/input/demand/` 一类；
  另有 CSV/Excel 导入、数据库访问、命令行、嵌入。
  来源：<https://frepple.com/docs/current/integration-guide/rest-api/index.html>、
  <https://frepple.com/docs/current/integration-guide/index.html>、
  <https://demo.frepple.com/operation-autofence/api/>
- 对我们：作为“模型与接口参考”很干净；但它是**全量模型导入**，不是增量事件同步。
- 判定：**可直接用**（作为接口/模型参考或未来集成面）。

#### ⑩ 完整性巡检

- 事实：Problem report 覆盖 demand invalid data、resource overload、buffer material shortage、
  operation precedence、forecast outlier；不覆盖 EN 单据之间的一致性（DN↔Shipment、运单重复等）。
  来源：<https://frepple.com/docs/current/user-interface/plan-analysis/problem-report.html>
- 判定：**不适合** W4。

---

## 4. 现成集成：ERPNext / Frappe / frePPLe

### 4.1 事实

- 官方 ERP integration 页把 **ERPNext** 列为可用连接器之一；另有 Odoo、Openbravo/Etendo、uzERP 和
  “generic ERP connector（需要自己改）”。来源：
  <https://frepple.com/docs/current/erp-integration/index.html>
- 官方 ERPNext 连接器页明确：它是**第三方应用**，frePPLe 团队“contributes to and endorses”，
  但 **“we are not owning or actively maintaining this connector”**。来源：
  <https://frepple.com/docs/current/erp-integration/erpnext-connector.html>、
  <https://raw.githubusercontent.com/frePPLe/frepple/master/doc/erp-integration/erpnext-connector.rst>
- 主仓库：`msf4-0/ERPNext-Frepple-Integration`
  - 许可 **GPL-3.0**；30 stars；2 open issues；**最后 push 2022-02-21**；
  - 最新 10 个 commit 全是 2022-02 的 README/LICENSE/一次上游合并，**没有功能现代化**；
  - 数据同步方式：**REST**（bearer token + frePPLe URL + 超级用户账号），可 iframe 嵌入；
    导出 ERPNext 数据、回写 MO/PO、同步 SO/WO/PO 状态与库存；
  - README 明确 **“does not perform any data validation”**，且需要用户自己保证 supply path 正确。
  - **代码结构（可借的部分）**：`frepple/frepple/doctype/frepple_data_export/frepple_data_export.py`
    每个实体一个 `export_*()`（item / customer / location / buffer / itemdistribution / resource / supplier /
    itemSupplier / operation / operationMaterial / salesOrder），统一 POST 到 frePPLe `/api/input/<entity>/`；
    `frepple_run_plan.py` 负责 `runplan` 与 MO/PO 回读。**这是现成的“ERPNext → frePPLe 实体映射清单”**。
    但它读的是自定义镜像 DocType（`tabFrepple Item`、`tabFrepple Buffer` 等），不是 ERPNext 原生 DocType；
    实现里有 `print`、`http://` 硬编码、用户名密码拼进 URL、部分字段被注释掉（如 MO 的 operation/quantity）。
  - **许可证不一致（坑）**：仓库 `LICENSE` 是 **GPL-3.0**，README 写 GPLv3，但 `frepple/hooks.py` 里
    `app_license = "MIT"`。**以 LICENSE 文件为准 = GPL-3.0**；不能按 hooks 的 MIT 当依据。
  来源：<https://github.com/msf4-0/ERPNext-Frepple-Integration>、
  <https://api.github.com/repos/msf4-0/ERPNext-Frepple-Integration>、
  <https://api.github.com/repos/msf4-0/ERPNext-Frepple-Integration/commits?per_page=10>、
  <https://github.com/msf4-0/ERPNext-Frepple-Integration/blob/master/LICENSE>
- 增强版：`szufisher/ERPNext-Frepple-Enhanced-Integration`，GPL-3.0，1 star，最后 push **2022-10-04**。
  来源：<https://github.com/szufisher/ERPNext-Frepple-Enhanced-Integration>、
  <https://api.github.com/repos/szufisher/ERPNext-Frepple-Enhanced-Integration>
- GitHub 搜索 `frepple erpnext` 共 14 个仓库，绝大多数是 2022–2023 的 fork；最新 push 的
  `yamposskype/ERPNext-Frepple-Integration`（2026-04-22）经 commit 核对仍是 **2022-02 的代码**，
  只是 fork 时间晚。来源：<https://api.github.com/search/repositories?q=frepple+erpnext&sort=updated&order=desc&per_page=10>
- Frappe 论坛：
  - 2022-01 起的帖子 <https://discuss.frappe.io/t/erpnext-integration-with-frepple-production-plan-tool/84678>
    使用 ERPNext v12；社区项目“v13 可用但很笨重”；v14 只有私人 fork；**没有公开的端到端成功记录**。
  - 2024-10 的帖子 <https://discuss.frappe.io/t/implementing-erpnext-and-frepple-for-production-planning/136483>
    未得到有效答复，回复者反而建议用 ERPNext 自带制造模块。
- **Frappe Cloud Marketplace 未检索到 frePPLe app**（检索日期 2026-10-27；只出现 ProcurementNext 等无关应用）。

### 4.2 推断

- **“不可用”不等于“没有代码”**：前面说的“不可用”指**不能直接装到 v15/v16 生产**、没人维护；
  代码本身可读，**实体映射（哪个 EN 单据 → 哪个 frePPLe 实体、哪些字段）可以借**。
- 这个连接器是 **v12/v13 时代**的产物，**没有证据支持 ERPNext v15/v16**；直接装到我们生产版大概率要改。
- 它默认包含**回写**（在 EN 里创建 PO/WO），与我们的非目标（不自动下单、不改主数据）冲突；
  即便要用，也只能裁剪成“只读导出”。
- 数据同步是**全量/模型级**，不是我们 W1 需要的“单据增量 + 事件血缘”。
- 许可证：LICENSE 为 GPL-3.0。**内部使用/阅读不受分发约束**；若把它的代码复制进我们对外分发的 app，
  GPL 义务会触发。EN 是内部系统，实践中可读可参考；但更稳妥的是**照着映射清单自己写**。

---

## 5. 数据模型与接入代价

### 5.1 最小输入表（仅 B 本地对照需要）

> **A（借逻辑/移植）不需要这些 CSV**：算法直接吃我们自己的 DuckDB 行。
> 下面只用于 B：真的起一个 frePPLe 跑对照。

> 只做“供应时间线 + 缺口 + 运输方式假设”，**不需要**建产能/工序模型。
> 下列字段来自官方 model reference；CSV 文件名按官方导入约定（`item.csv`、`demand.csv` 等）。
> 来源：<https://frepple.com/docs/current/model-reference/index.html> 及各实体页。

| 目的 | 实体 / 文件 | 最小字段 | 我们的来源 | 注意 |
|---|---|---|---|---|
| SKU | `item.csv` | `name, type, unit of measure, cost` | `sku_item` / item master | `type=make-to-stock`；一个 item 一个 UOM |
| 仓/地点 | `location.csv` | `name, available(calendar), owner` | `warehouse_map` | 地点层级可表达“工厂→海外仓”，但没有“运营方/所有权”语义 |
| 现有库存 | `buffer.csv` | `item, location, onhand` | `stock_latest`（as-of 冻结快照） | `onhand` 是期初库存；必须钉死 as-of |
| 需求 | `demand.csv`（sales order） | `name, item, location, customer, due, quantity, priority, status` | 未履约 SO / 分析侧需求视图 | 预测用 `forecast.csv`，不与 SO 混用 |
| 采购在途 | `purchaseorder.csv` | `reference, item, location, supplier, quantity, ordering date, receipt date, status` | `tongtool_po` 未结 PO | **receipt date 必填**；未知 ETA 无法表达 |
| 已出运在途 | `distributionorder.csv` | `reference, item, origin(可空), destination, quantity, shipping date, receipt date, status` | EN Shipment / DN | origin 留空 = 已离源在途；destination 收货即增库存 |
| 生产在制 | `manufacturingorder.csv` | `reference, operation, location, quantity, quantity_completed, start date, end date, status` | EN WO / JC | 需要先有 operation 定义，否则不能直接建 MO |
| 交期/运输方式 | `itemdistribution.csv` | `item, origin, destination, leadtime, cost, priority, size_*` | W2 假设配置 | 一种运输方式 = 一条记录；无分段、无 provenance |
| 工作日历 | `calendar.csv` + `calendarbucket.csv` | 工作时段/节假日 | 可先用默认 7×24 | 影响 lead-time offset 的精度 |
| 预测（可选） | `forecast.csv` | `name, item, location, customer, method, planned` | 分析侧 P50/P90 | 与 SO 冲减规则要单独定 |

**最小可跑集合**：`item + location + buffer + demand + purchaseorder + distributionorder + itemdistribution`
（7 个文件）。加上 `manufacturingorder` 才覆盖 `in_production`；但需要 operation 模型，代价陡增。

### 5.2 硬阻抗：我们的规则 vs frePPLe 的假设

> **适用范围**：这一节只在 **B（实际跑 frePPLe）/ C（照搬其数据模型）** 时成立。
> 如果只借算法（A），这些阻抗**不影响我们**：unknown 行可以不进算法、只对“已证日期/已证 UOM”的子集计算，
> 结果再回到我们自己的 W1/W3 表里合并。**不要因为这一节就否掉“借逻辑”。**

| 我们的硬规则 | frePPLe 的现实 | 后果 |
|---|---|---|
| 未知日期不得当到货，`date_confidence=unknown` 单列 | PO/DO/MO 的 `receipt date` 是必填的计划输入；没有 “unknown date” 语义 | 只能**剔除**未知行并单独报告；若硬塞远期日期，等于伪造供给 |
| 同一数量只计一次；`same_batch_suspected` 去重 | 无“重复/疑似同批”概念；导入即视为独立订单 | 去重必须在上游（我们的 W1/SC14）完成 |
| UOM 未证不跨单位合计 | 一个 item 一个 `unit of measure`；BOM 用 operation 做转换 | `uom_unproven` 行只能剔除或先证明换算 |
| 部分入库/部分出运要拆剩余量 | MO 有 `quantity_completed`；PO 以状态/数量表达，部分收货需拆行 | 拆分逻辑仍在我们这边 |
| 多仓不默认互通 | location 层级 + itemdistribution 显式建 lane | 可以表达“不互通”（不建 lane 即可），这点反而更清晰 |
| 可追溯到单据行 | 只存 `reference`；无 doc_line / source_key | 血缘要我们在导出时塞进 `reference/remark`，或另存映射表 |

### 5.3 如果做 EN app

- **EN schema**：只读导出**不需要**改 EN schema；若要存 frePPLe 的计划结果（快照/行），
  需要新增自定义 DocType（如 `Supply Plan Snapshot` / `Supply Plan Line`），即新增表与权限。
- **权限**：读导出需要只读 API 账号；回写需要 PO/WO 的 create 权限——**与“不自动下单”冲突，建议禁止**。
- **部署**：EN 之外要有 frePPLe 容器 + PostgreSQL（官方 compose 用 `postgres:16`）；
  EN app 通过 REST 连接；iframe 嵌入还要配允许域与 secret。
  来源：<https://frepple.com/docs/current/installation-guide/advanced/docker-compose.php>
- **EN 生产约束**（来自本项目 P0 文档）：生产只读闸门 300 请求 / 32 MiB / 900 秒每批；
  生产不跑 `bench setup requirements`，新增 pip 依赖要手动装。
  因此**不能让 frePPLe 直接高频拉 EN**；更合理的是本地 ETL 导出 → frePPLe → 结果回写快照。
- **与现有 Parquet/DuckDB 的衔接**：
  - 出：`duckdb` 查询 → CSV（每实体一个文件）→ `importfromfolder` 或 REST POST；
  - 回：frePPLe 报表/API 导出 → Parquet/JSON → 入库 DuckDB；
  - 没有原生 DuckDB 连接器，也没有“增量事件”接口；每次是全量模型刷新（或按 batch 覆盖）。
  - 来源：<https://frepple.com/docs/current/integration-guide/index.html>、
    <https://frepple.com/docs/current/user-interface/getting-around/importing-data.html>
- **部署代价（粗估）**：一个容器 + 一个 PostgreSQL + 备份/监控/升级；对我们是**新增一套有状态服务**，
  不是“加个 cron”。

### 5.4 版本与稳定性风险

- 10.0 预览有 breaking changes，且 10.0 只发容器；如果现在按 10.0 文档建模，等正式版可能返工。
- 社区版功能边界（库存规划/报价/Gantt）会直接影响 W3 的可用性；这是**产品策略**，不是配置能解决的。

---

## 6. 我们真正缺的能力

把 W1/W2/W3 拆开看：

| 需求 | 我们已经有的 | frePPLe 能补的 | 真正缺的 |
|---|---|---|---|
| 需求预测 | 分析侧已有预测实验；未统一到补货主链 | 完整统计预测源码（Croston/Holt-Winters/异常值/自动选优）+ SO 冲减规则 | **统一引擎与回测口径**；frePPLe 可借，但 `statsforecast` 更成熟 |
| 库存规划 | 有库存快照/历史；无安全库存/ROP/缺货风险表 | buffer min/max/短缺求解；**库存规划 UI 不在社区版** | **政策层**（服务水平/ABC/补货建议/例外）；计算可借 |
| W1 供应时间线 | 7 阶段、数量守恒、单据行、B_min/B_max、unknown 单列（#312） | 一个更规范的 item/location/buffer/order 词汇；pegging 思路 | **证据与血缘**、未知日期语义、UOM/去重、EN 单据一致性；frePPLe 不解决 |
| W2 交期与运输方式 | 版本化假设配置草案、分段字段设计 | lane + leadtime + cost + priority 的建模词汇 | **分段、来源/样本数/版本**；frePPLe 只有单段 leadtime |
| W3 决策接口 | 周表草案：confirmed/expected/unknown/gap/mode 选项 | 约束计划、分配、what-if、承诺交期（UI 商业版，试算逻辑社区有） | **并列运输方式选项 + 置信度 + 可追溯**；frePPLe 输出的是“选中方案”，不是“并列选项” |

**判断**：

- frePPLe 覆盖的是**求解层**（allocation、lead-time offset、约束、what-if）以及**预测/安全库存的算法实现**。
- 我们当前卡住的是**证据层**（数据可信、日期可信、未知可表达）。这两层不是一回事。
- 预测与库存规划：**算法可借**；但预测建议直接用 `statsforecast`，库存政策层自建。
- 因此：**“供应时间线/缺口/可售日/运输方式情景”不是 frePPLe 已覆盖的现成产品能力**；
  它只覆盖其中“给定干净输入后如何排”的那一段。真正该借的是：
  1. **数据模型词汇**（item/location/buffer/itemdistribution/purchaseorder/distributionorder/demand）；
  2. **算法概念**（backward/forward scheduling、lead-time offset、pegging、fair-share allocation）；
  3. **输出结构**（operationplan 的 start/end/quantity/demands pegging）。
- 不建议整套引入，除非我们确定要做“多级网络 + 产能约束 + 每日重排”的优化，而不是现在的证据时间线。

---

### 6.5 可借用的代码/逻辑清单（按能力）

> 原则：**EN 架构独立，只移植逻辑，不复制整套代码。** frePPLe 社区版 8.0+ 是 MIT（保留版权声明即可）；
> ERPNext 连接器是 GPL-3.0（内部可读；复制进对外分发代码会触发 GPL）；Odoo 是 LGPL-3（参考为主）。
> 下面路径均已在本机 clone 的 `frepple_src` / `erpnext_frepple_src` 中核对。

| 能力 | frePPLe 源码（可读） | 借什么 | 移植难度 | 替代/补充 |
|---|---|---|---|---|
| 预测方法 | `src/forecast/forecastsolver.cpp`、`timeseries.cpp`、`measure_compute.cpp` | constant/trend/seasonal(Holt-Winters)/Croston/moving average、SMAPE、离群值、自动选优 | 中（C++→Python） | **`statsforecast`（Apache-2.0）已实现同族方法，优先直接用** |
| 预测冲减 | `freppledb/forecast/models.py`、`services.py`；`ForecastSolver::matchDemandToForecast` / `netDemandFromForecast` | SO 按 item/location/customer/时间窗冲减预测；层级 | 中 | 无成熟独立库；**值得移植规则** |
| 提前期 offset / 排程 | `src/solver/solverdemand.cpp`、`operatorbackward.cpp`、`operatorforward.cpp` | ask/reply 循环、administrative lead time、优先级/到期日排序、回溯失败再前推 | 中高 | Odoo/ERPNext MRP 更简单；优化可用 OR-Tools |
| 安全库存 / 短缺 | `src/solver/solverbuffer.cpp`（`solveSafetyStock`）、`src/model/buffer.cpp`（`getOnHand`） | min/max、逐段缺口检测、按日期补货 | 中 | **`stockpyl`（MIT）做 newsvendor/多级安全库存** |
| 库存政策/补货 | **社区版无**（`freppledb.inventoryplanning` 目录不存在） | 只能借 min/max/短缺语义；政策层自建 | 低 | Odoo reordering rules（LGPL-3）、ERPNext reorder level（GPL-3）作交互参考 |
| 承诺交期（CTP） | `src/solver/solverdemand.cpp`、`solverplan.cpp` 的 `STATUS_QUOTE/INQUIRY` | trial demand 参与排程、读回计划日期与 constraints | 中 | 先做正向 lead-time offset；业务需要再做 |
| 数据导出映射 | `freppledb/erpconnection/management/commands/erp2frepple.py`（MIT）；连接器 `frepple_data_export.py`（GPL-3.0） | 实体顺序、字段映射、REST 调用方式 | 低 | 按 EN 原生 DocType 自己写 |
| 计划输出/pegging | `src/model/operationplan.cpp`、`pegging.cpp`、`flowplan.cpp` | `start/end/quantity/demands` 的 pegging 结构 | 中 | 我们 W3 行模型已接近 |

**不要借的**：

- 连接器的**回写逻辑**（自动建 PO/WO）——与非目标冲突。
- 连接器的**镜像 DocType 设计**（`tabFrepple Item` 等）——多一层同步，且已过时。
- frePPLe 的**完整 schema/PostgreSQL 模型**——借算法不需要引入它的数据库。

### 6.6 其他开源选项（预测 / 库存 / 优化）

| 领域 | 项目 | 许可 | 状态（2026-10-27） | 适合我们什么 |
|---|---|---|---|---|
| 统计预测 | [statsforecast](https://github.com/Nixtla/statsforecast) | Apache-2.0 | 活跃，4.9k stars | AutoARIMA/AutoETS/AutoCES、Croston/TSB/ADIDA/IMAPA、交叉验证；**首选** |
| 统计/ML 预测 | [sktime](https://github.com/sktime/sktime) | BSD-3-Clause | 活跃，10k stars | 统一 API、预测/分类/回归；备选 |
| 预测/异常 | [Darts](https://github.com/unit8co/darts) | Apache-2.0 | 活跃，9.5k stars | 深度学习/概率预测；有 GPU 再考虑 |
| 概率预测 | [GluonTS](https://github.com/awslabs/gluonts) | Apache-2.0 | 活跃，5.2k stars | 大规模概率预测；偏重 |
| 库存优化 | [stockpyl](https://github.com/LarrySnyder/stockpyl) | MIT | 活跃（2026-06），183 stars | newsvendor、单级/多级安全库存、base-stock、GSM；适合做政策实验 |
| 库存/补货参考 | [Odoo Inventory](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/inventory/warehouses_storage/replenishment/reordering_rules.html) | LGPL-3 | 活跃 | min/max、visibility days、lead-time-aware replenishment；参考交互 |
| MRP/库存参考 | [ERPNext](https://github.com/frappe/erpnext) | GPL-3.0 | 活跃 | reorder level、auto reorder、生产计划；参考，不复制 |
| 约束优化 | [OR-Tools](https://github.com/google/or-tools) | Apache-2.0 | 活跃，14k stars | 以后要做约束分配/排程优化 |
| MRP/履约参考 | [Apache OFBiz](https://github.com/apache/ofbiz-framework) | Apache-2.0 | 活跃 | 仓储/制造 MRP/履约；首页未确认 ATP |

**结论**：**预测已经有 `self_fulfilled_demand/forecast.py`（statsforecast 2.1.1），不要重造**；
**库存规划已有 `inventory_policy.py` / `sc08_conformal.py` 和结论**，缺的是生产政策表；
**交期已有 `leadtime_config.py`**；**供应时间线/净额已有 W1 / #318 / `supply_netting`**。
frePPLe 的独特价值只剩 **lead-time offset / 分配 / pegging / CTP 求解逻辑**。
详见 [已有资产审计](2026-10-27-existing-assets-forecast-inventory.md)。

---

## 7. 推荐：复用已有，按需借逻辑

> 大白话：**预测、库存、交期、时间线都已有项目内资产，先复用、接线；
> frePPLe 只在“约束分配/CTP 试算”时借逻辑，不部署。**

### A. 复用已有 + 按需借 frePPLe 逻辑（推荐，默认）

**A1 预测**：复用 `self_fulfilled_demand/forecast.py`（AutoETS + MA3/naive guard，statsforecast 2.1.1）；
**不要重新选模/重跑对照**；只做合并、接线、业务确认。**0 新建**；合并约 **1–2 人日**。

**A2 库存规划**：复用 `inventory_policy.py` + `sc08_conformal.py` 的 β/α、L+R、order-up-to 框架；
补一张 `SKU×仓×UOM` 的 `safety_stock / reorder_point / projected_inventory` 生产表；
参数先给 90/95% 情景，业务拍板。**5–8 人日**；不引入 `stockpyl`，除非证明单级不够。

**A3 可售日/运输方式**：复用 `sc13/leadtime_config.py`；W2 实测未到前用 assumed 并显式标注；
若要做约束分配，再移植 `solverdemand.cpp` 的 ask/reply + backward/forward。
**2–3 人日接入；5–10 人日按需分配**。

**A4 CTP（按需）**：只有业务明确要“承诺日”才做；借 `STATUS_QUOTE` trial demand。**3–5 人日**。

**A5 EN 映射**：照连接器 `export_*()` 清单，从 EN 原生 DocType 生成我们自己的行表。**2–3 人日**。

- 条件：A1/A2/A5 可立即做；A3 需要 W2 配置；A4 需要业务明确需求。
- 风险：两条本地分支合并冲突；预测与净额口径不一致；库存参数未批准；assumed 交期被误用。
- 工作量：**先做 A1+A2+A3 接入 ≈ 8–13 人日**（不含净额数据缺口修复）；不新增服务。
- 交付物：库存政策表 + 接线后的净额/补货视图；不部署 frePPLe。

### B. 本地 frePPLe 对照验证（可选，不是必需）

**做什么**：只在需要**验证/对标** A3 的求解结果时，Docker 起 9.19.0 + PostgreSQL，
用 **9 个冻结 SKU** 的 7 张 CSV 跑一次计划，跟我们自己的 lead-time offset/分配结果对账。
不接 EN、不写回、不生产；**不作为主链**。

- 启动条件：A3 已实现，且出现“我们的分配/可售日结果对不对”的争议；否则不做。
- 风险：未知日期/UOM/重复行要剔除；社区版没有 inventory planning/quoting；新增一套有状态服务。
- 工作量：**3–5 人日**（窄验证；只跑 3–9 SKU）。
- 退出条件：若 >20% 的供给行无法表达，或结果跟我们的差异无法解释 → 停止，以 A 为准。

### C. EN app 集成（暂不做）

**做什么**：把 frePPLe 结果接进 EN（自定义 DocType/报表/iframe），或改造第三方连接器。

- 条件（全部满足才考虑）：B 已证明有业务价值；业务明确要“在 EN 里看计划/报价”；有人负责 frePPLe 运维；
  能接受只读、不回写。
- 风险：
  - 现成连接器 2022 年后未维护，v12/v13 时代，v15/v16 无证据；
  - 默认含回写（自动建 PO/WO），与“不自动下单”冲突；
  - EN 生产发布链路、权限、备份、网络、安全面都要扩；
  - frePPLe 是新有状态服务，故障域独立但运维归属要定。
- 工作量：**25–40 人日**（连接器现代化/自研 + 部署 + 权限 + 测试→生产），另加持续运维。
- 结论：**现在不做。** 如果只是要在 EN 里看预测/库存，直接在 `key_test` 出只读报表即可，不需要 frePPLe。

### D. 不引入 frePPLe 系统（本方案的默认终点）

- 含义：复用项目已有预测（`self_fulfilled_demand/forecast.py`）、交期（`leadtime_config.py`）、
  净额（`supply_netting/`），补一张库存政策表；frePPLe 只当“算法参考手册”，
  **不部署 frePPLe、不建 PostgreSQL、不接 EN**。
- 触发条件：A1+A2+A3 完成；业务不需要“约束分配/承诺交期”。
- 成本：0（除了 A 的人日）；把 frePPLe 当“算法参考手册”。

### 推荐组合

**A1（复用预测）+ A2（补库存政策表）+ A3（接交期）先做 → A4 按业务需要 → B 只在结果有争议时做对照 → C 不做 → D 是默认终点。**

如果只允许一个动作：**把已有的 `self_fulfilled_demand/forecast.py`、`inventory_policy.py`、
`leadtime_config.py` 合到一条可评审分支并接线；不要为了预测/库存去部署 frePPLe。**

---

## 8. 下一步最小验证

### 8.1 复用已有预测 + 补库存政策表（推荐，先做）

> 目的：不新建模型，验证“已有预测 + 已有政策评估器 + 已有交期配置”能否产出可用的库存政策表。

1. **预测复用**：直接用 `forecast-20261027-r2` 的 `forecast_sku_windows`（L60/90/120，P50/P10/P90）；
   不再跑 statsforecast 对照，不再选模。
2. **库存政策**：用 `inventory_policy.py` 的 order-up-to 参照 + `sc08_conformal` 的经验分位，
   对 9 个冻结 SKU 生成 `safety_stock / reorder_point / projected_inventory`；目标先给 90/95% 两档。
3. **交期接入**：用 `leadtime_config.expected_available_date()` 生成 L；assumed 必须标 `is_assumed`。
4. **对账**：与 `supply_netting/run-2026-10-23` 的保护期缺口对齐；不得把预测与未履约 SO 重复计。
5. **决策门**：
   - 预测是否覆盖业务要的 SKU/仓？不可预测的 10 个 SKU 是否可接受？
   - 库存政策表的缺口是否与净额引擎一致？差异能否解释？
   - 业务是否确认目标 β（90/95%）与 L/R？未确认就只出情景，不批准采购。

### 8.2 B 的对照验证（可选，只在 A3 有争议时做）

> 目的不是“把 frePPLe 跑起来”，而是**验证我们的 lead-time offset/分配结果对不对**。

1. **起环境**：`ghcr.io/frepple/frepple:9.19.0` + `postgres:16`（官方 compose），只用本机 Docker。
2. **选 3 个 SKU**：1 个成品、1 个皮壳、1 个组件（覆盖不同角色）。
3. **导 7 张 CSV**：`item / location / buffer / demand / purchaseorder / distributionorder / itemdistribution`，
   从 DuckDB 冻结快照导出；**未知 ETA 行单独放一份 excluded 清单**，不塞日期。
4. **跑计划**：`importfromfolder` → 生成 plan → 导出 problem report / operationplan。
5. **对账**：
   - `on_hand` 是否等于 W1 的 832 口径子集；
   - PO/在途的“可售日”是否与 W1 的 `available_date` 一致；
   - 未知行剔除后，缺口是否仍可解释；
   - 一个运输方式并列问题：用 3 条 itemdistribution 跑 3 个情景，看是否能得到 3 个日期。
6. **决策门**：
   - 若 7 张表能覆盖 ≥80% 的供给行，且缺口可解释 → 说明 frePPLe 的分配逻辑可借鉴；
   - 若大量行因未知/UOM/重复被剔除，或结果差异无法解释 → 以我们自己的 A3 为准。

**验证产出**：一页 `experiments/frepple/2026-10-27-spike.md`（环境、输入行数、剔除原因、对账表、结论）。
行级业务数据留本地，不进公开仓库（D33）。

---

## 9. 非目标

- 不做全厂精细排程（产能/换型/班次/Gantt 优化）。
- 不替换 EN（ERPNext 仍是单据与主数据系统）。
- 不自动下单、不回写 PO/WO、不改主数据。
- 不把 frePPLe 的营销页/功能大全当事实；所有版次能力以官方 editions/license/release notes 为准。
- 不在公开仓库放行级业务 CSV/JSON、凭证、连接串。

---

## 10. 事实 / 推断 / 未核实清单

**事实（有官方一手来源）**

- 9.19.0 于 2026-10-09 发布；10.0.0 未发布、计划 2026 年底、容器-only、含不兼容变更。
- Community 8.0+ 为 MIT；7.0 为 AGPLv3；Enterprise/Cloud 闭源商业。
- Community 含生产计划/排程、需求预测、浏览器 UI、Excel/CSV/REST、what-if（本地 3 情景）。
- Cloud/Enterprise 额外含库存规划、交互 Gantt、承诺交期、换型优化、保质期。
- 库存规划与报价页明确 “Enterprise and Cloud Editions only”。
- 数据模型字段（item/location/buffer/itemdistribution/purchaseorder/distributionorder/salesorder/operation/forecast）如正文。
- 第三方 ERPNext 连接器：GPL-3.0，2022-02-21 后再无代码更新；官方“背书但不维护”；无 Marketplace 上架。
- 连接器**有可读代码**：`frepple_data_export.py` 里每个实体一个 `export_*()`，统一 POST `/api/input/<entity>/`；
  但读的是自定义镜像 DocType，不是 ERPNext 原生 DocType。
- 连接器**许可证元数据不一致**：`LICENSE` 为 GPL-3.0、README 写 GPLv3，`hooks.py` 却写 `app_license = "MIT"`。
- 社区源码包含：预测方法（constant/trend/seasonal/Croston/moving average、SMAPE、离群值）在 `src/forecast/`；
  buffer min/max 与短缺求解在 `src/solver/solverbuffer.cpp`、`src/model/buffer.cpp`；
  `Demand::STATUS_QUOTE/INQUIRY` 在 `include/frepple/model.h` 与 `src/solver/`。
- 社区仓库**没有** `freppledb/inventoryplanning` 目录；该模块只被 `if "freppledb.inventoryplanning" in INSTALLED_APPS` 条件引用。
- Docker 需外部 PostgreSQL；官方 compose 用 postgres:16。

**事实（项目内资产，本机核对）**

- `statsforecast==2.1.1` 已在 `keyapi/forecast-refresh-oct27` 的 `pyproject.toml`/`uv.lock`；forecast 工作区 venv 可导入；
  实际 run `forecast-20261027-r2` 存在，45 tests，2,413/2,423 可预测。
- `inventory_policy.py`（order-up-to 模拟器）与 `sc08_conformal.py`（经验分位）在 `docs/supply-chain-integration-handoff`（PR #300）。
- `sc13/leadtime_config.py` 已有版本化契约与测试，样例全部 `source=assumed`。
- `supply_netting/` 在 `keyapi/supply-integrate-oct27` @ `66144037`，35 tests，run-2026-10-23 存在；**未 push、无 PR**。
- W1 #312、supply facts #318 open；key_test 报表已生产部署。

**推断（基于事实的判断，不是官方声明）**

- 慢船/快船/空运 = 多条 itemdistribution；不是并列输出。
- frePPLe 是计划中心、非事件溯源；无法表达 unknown date / doc_line 血缘。
- 社区版没有库存规划 UI/报价 UI，但**求解逻辑可读可移植**；“跑系统”与“借逻辑”要分开判断。
- 预测已有实现，**不需要 frePPLe 的预测模块**；库存规划已有评估器，缺的是生产政策表与业务参数。
- CTP 的“trial demand”机制在社区 solver 里，缺的是报价 UI；业务不需要承诺日就不做。
- 现成连接器不能直接用于 ERPNext v15/v16；但**实体映射清单可以借**。
- 工作量估算（A1 合并 1–2、A2 政策表 5–8、A3 接入 2–3、A5 2–3、A4 3–5、B 3–5、C 25–40 人日）。

**未核实 / 公开信息冲突**

- Community 是否支持“前向排程”：官方 features 写支持；俄语经销商页称社区仅回溯。未找到官方版次说明。
- Problem report / Demand Gantt 是否属社区版：文档未标版次。未核实。
- Community 实际 UI 缺失范围（有用户评论称看不到 forecast/inventory/plan），与维护者“同核心求解器”的说法不完全一致；以官方 editions 页为准，其余按未核实处理。
- frePPLe 容器内第三方依赖的许可证清单：未审计。
- “AI MCP app”仅 Enterprise/Cloud（9.19 release notes），是否对我们有价值未评估。

---

## 11. 来源清单（原始 URL）

**官方文档 / 版本**

- <https://frepple.com/docs/current/features.html>
- <https://frepple.com/docs/current/release-notes.html>
- <https://frepple.com/docs/current/index.html>
- <https://frepple.com/docs/current/license.html>
- <https://frepple.com/editions/>
- <https://frepple.com/downloads/>
- <https://frepple.com/pricing/>
- <https://frepple.com/v8-0/>
- <https://frepple.com/docs/current/installation-guide/index.html>
- <https://frepple.com/docs/current/installation-guide/advanced/docker-compose.php>
- <https://frepple.com/docs/9.15/installation-guide/docker-container.php>

**数据模型**

- <https://frepple.com/docs/current/model-reference/index.html>
- <https://frepple.com/docs/current/model-reference/items.html>
- <https://frepple.com/docs/current/model-reference/locations.html>
- <https://frepple.com/docs/current/model-reference/buffers.html>
- <https://frepple.com/docs/current/model-reference/item-distributions.html>
- <https://frepple.com/docs/current/model-reference/purchase-orders.html>
- <https://frepple.com/docs/current/model-reference/distribution-orders.html>
- <https://frepple.com/docs/current/model-reference/sales-orders.html>
- <https://frepple.com/docs/current/model-reference/forecast.html>
- <https://frepple.com/docs/current/model-reference/operations.html>

**功能 / UI**

- <https://frepple.com/docs/current/user-interface/index.html>
- <https://frepple.com/docs/current/user-interface/plan-analysis/inventory-planning.html>
- <https://frepple.com/docs/current/user-interface/plan-analysis/quoting-screen.html>
- <https://frepple.com/docs/current/user-interface/plan-analysis/supply-path-where-used.html>
- <https://frepple.com/docs/current/user-interface/plan-analysis/problem-report.html>
- <https://frepple.com/docs/current/user-interface/plan-analysis/inventory-status.html>
- <https://frepple.com/docs/current/user-interface/what-if-scenarios.html>

**集成 / API**

- <https://frepple.com/docs/current/integration-guide/index.html>
- <https://frepple.com/docs/current/integration-guide/rest-api/index.html>
- <https://demo.frepple.com/operation-autofence/api/>
- <https://frepple.com/docs/current/erp-integration/index.html>
- <https://frepple.com/docs/current/erp-integration/erpnext-connector.html>
- <https://raw.githubusercontent.com/frePPLe/frepple/master/doc/erp-integration/erpnext-connector.rst>
- <https://frepple.com/docs/current/user-interface/getting-around/importing-data.html>

**许可证原文**

- <https://raw.githubusercontent.com/frePPLe/frepple/master/COPYING>
- <https://raw.githubusercontent.com/frePPLe/frepple/7.0.0/COPYING>

**GitHub / 社区**

- <https://github.com/frePPLe/frepple>
- <https://api.github.com/repos/frepple/frepple>
- <https://api.github.com/repos/frepple/frepple/releases/latest>
- <https://api.github.com/repos/frepple/frepple/tags?per_page=15>
- <https://github.com/frePPLe/frepple/discussions/444>
- <https://github.com/msf4-0/ERPNext-Frepple-Integration>
- <https://api.github.com/repos/msf4-0/ERPNext-Frepple-Integration>
- <https://api.github.com/repos/msf4-0/ERPNext-Frepple-Integration/contents/frepple/frepple/doctype>
- <https://github.com/szufisher/ERPNext-Frepple-Enhanced-Integration>
- <https://api.github.com/repos/szufisher/ERPNext-Frepple-Enhanced-Integration>
- <https://api.github.com/search/repositories?q=frepple+erpnext&sort=updated&order=desc&per_page=10>
- <https://discuss.frappe.io/t/erpnext-integration-with-frepple-production-plan-tool/84678>
- <https://discuss.frappe.io/t/implementing-erpnext-and-frepple-for-production-planning/136483>

**源码（本机 clone 核对，2026-10-27；用于确认“有什么逻辑可借”）**

- <https://github.com/frePPLe/frepple/tree/master/src/forecast>
- <https://github.com/frePPLe/frepple/blob/master/src/forecast/forecastsolver.cpp>
- <https://github.com/frePPLe/frepple/blob/master/src/solver/solverdemand.cpp>
- <https://github.com/frePPLe/frepple/blob/master/src/solver/solverplan.cpp>
- <https://github.com/frePPLe/frepple/blob/master/src/solver/solverbuffer.cpp>
- <https://github.com/frePPLe/frepple/blob/master/src/solver/operatorbackward.cpp>
- <https://github.com/frePPLe/frepple/blob/master/src/solver/operatorforward.cpp>
- <https://github.com/frePPLe/frepple/blob/master/src/model/buffer.cpp>
- <https://github.com/frePPLe/frepple/blob/master/freppledb/forecast/models.py>
- <https://github.com/frePPLe/frepple/blob/master/freppledb/erpconnection/management/commands/erp2frepple.py>
- <https://github.com/msf4-0/ERPNext-Frepple-Integration/blob/master/frepple/frepple/doctype/frepple_data_export/frepple_data_export.py>
- <https://github.com/msf4-0/ERPNext-Frepple-Integration/blob/master/LICENSE>

**其他开源项目（预测 / 库存 / 优化）**

- <https://github.com/Nixtla/statsforecast>（Apache-2.0）
- <https://github.com/sktime/sktime>（BSD-3-Clause）
- <https://github.com/unit8co/darts>（Apache-2.0）
- <https://github.com/awslabs/gluonts>（Apache-2.0）
- <https://github.com/facebook/prophet>（MIT）
- <https://github.com/LarrySnyder/stockpyl>（MIT）
- <https://github.com/google/or-tools>（Apache-2.0）
- <https://github.com/odoo/odoo>（LGPL-3）
- <https://github.com/apache/ofbiz-framework>（Apache-2.0）
- Odoo reordering rules：<https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/inventory/warehouses_storage/replenishment/reordering_rules.html>

**项目内资产（本地/分支，非外网）**

- 资产审计：[2026-10-27-existing-assets-forecast-inventory.md](2026-10-27-existing-assets-forecast-inventory.md)
- 预测：`self_fulfilled_demand/forecast.py` @ `keyapi/forecast-refresh-oct27`
- 净额：`supply_netting/` @ `keyapi/supply-integrate-oct27`
- 库存政策：`experiments/business_phase/inventory_policy.py`、`sc08_conformal.py`
- 交期：`experiments/sc13/leadtime_config.py`

**许可对照（本项目相关系统）**

- <https://api.github.com/repos/frappe/erpnext>
- <https://api.github.com/repos/frappe/frappe>

---

## 12. 附：与现有 W1/W2/W3 的接口建议（不改变现有结论）

1. **W1 字段**：保留现有 7 阶段与 `date_confidence`；把 frePPLe 的 `item/location/buffer/order`
   作为**命名对照**，不引入其“必填日期”假设。未知行继续单列。
2. **W2 配置**：采用 `lane + mode + segments` 自建模型；frePPLe 的 `leadtime/cost/priority`
   只作为字段灵感，不用它的单段模型替换分段。
3. **W3 输出**：保持 `supply_confirmed / expected / unknown / gap / mode_option`；
   不要为了对齐 frePPLe 而把 unknown 折成 0 或远期日期。
4. **A 的产物**：复用已有预测/交期/净额，补一张库存政策表，接入主链；frePPLe 只作为算法参考。
5. **B 的产物**：只作为“对照计划器”，不进入每日主链；主链仍是 W1/W2/W3 的可追溯表。

---

**最终判断**：**值得继续深入的是“逻辑移植”，不是“集成 frePPLe”。**

- **预测**：复用 `self_fulfilled_demand/forecast.py`（statsforecast 2.1.1）；不要再选型/重跑对照；
- **库存规划**：复用 `inventory_policy.py` + `sc08_conformal.py` 的结论，补生产政策表；
- **可售日/分配**：复用 `leadtime_config.py` 的正向可售日；需要约束分配再移植 `solverdemand.cpp`；
- **CTP（承诺交期）**：业务不需要就不做；需要就借 `STATUS_QUOTE` 的 trial demand 机制；
- **EN 映射**：照连接器的 `export_*()` 清单从原生 DocType 自己写，不装它的镜像 DocType。

**不建议部署 frePPLe 系统（B 只在对照有争议时做）、不建议接 EN（C）。**
它最有价值的部分是**可读的 MIT 求解/预测源码**，不是它的产品或集成。
项目内已有资产的完整清单见 [2026-10-27-existing-assets-forecast-inventory.md](2026-10-27-existing-assets-forecast-inventory.md)。
