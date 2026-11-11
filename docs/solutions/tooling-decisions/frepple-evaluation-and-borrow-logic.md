---
okf: v0.1
type: Reference
title: frePPLe 评估 — 社区 MIT、企业闭源；借求解逻辑，不部署
date: 2026-10-27
category: tooling-decisions
module: supply_chain_visibility
problem_type: tooling_decision
component: tooling
severity: medium
applies_when:
  - "评估 frePPLe / APS / 供应计划器是否值得引入"
  - "想借 lead-time offset / allocation / pegging / CTP 逻辑"
  - "判断 ERPNext-FrePPLe 连接器能否直接安装"
  - "区分『跑整套系统』与『借算法逻辑』"
tags: [frepple, aps, license, erpnext, make-vs-buy, ctp, lead-time, allocation]
---

# frePPLe 评估：借逻辑，不部署

## Context

W1/W3 需要供应时间线、缺口、可售日；用户问 frePPLe 是否值得“移植逻辑 / 借用逻辑 / 直接集成”。
本仓库 EN 架构独立，不可能直接套用它的代码；重点变成：**哪些算法可借、哪些系统能力不值得引入**。

## Guidance

### 1. 版本与许可证（2026-10-27 核实）

| 项 | 事实 |
|---|---|
| 稳定版 | **9.19.0**（2026-10-09）；`docs/current` 是 10.0.0 预览（未发布，计划 2026 年底，含不兼容变更） |
| 社区版 | **MIT**（8.0 起，2023-06-03）；7.x 及更早是 **AGPLv3** |
| 企业/云 | 闭源商业许可；库存规划、交互 Gantt、承诺交期（quoting）、换型优化、保质期仅商业版 |
| 部署 | 社区版 Docker + 外部 PostgreSQL（官方 compose 用 postgres:16） |

**许可证影响**：
- 8.0+ 社区版 MIT 允许嵌入/闭源使用，保留版权声明即可；
- **不要复制 7.x 及更早代码**（AGPLv3 网络条款）；
- ERPNext 连接器是 GPL-3.0；内部可读，复制进对外分发代码会触发 GPL。

### 2. 现成 ERPNext 连接器不能直接装

- 官方只“背书不维护”（`frepple.com/docs/current/erp-integration/erpnext-connector.html`）；
- 主仓库 `msf4-0/ERPNext-Frepple-Integration`：GPL-3.0，最后 push **2022-02-21**，
  v12/v13 时代；README 明确“不做数据校验”；默认会回写 MO/PO；
- 仓库 `LICENSE` 是 GPL-3.0，但 `hooks.py` 写 `app_license = "MIT"` —— **以 LICENSE 为准**；
- **可借的是实体映射清单**：`frepple_data_export.py` 每个实体一个 `export_*()`，统一 POST
  `/api/input/<entity>/`；不要借它的回写和镜像 DocType。

### 3. 值得借的源码（MIT，社区版）

| 能力 | 源码 | 借什么 |
|---|---|---|
| 预测 | `src/forecast/forecastsolver.cpp`、`timeseries.cpp`、`measure_compute.cpp` | constant/trend/seasonal/Croston/moving average、SMAPE、离群值 |
| 预测冲减 | `freppledb/forecast/models.py`、`services.py` | SO 按 item/location/customer/时间窗冲减 |
| 提前期/分配 | `src/solver/solverdemand.cpp`、`operatorbackward.cpp`、`operatorforward.cpp` | ask/reply、admin lead time、优先级/到期日、回溯失败再前推 |
| 安全库存/短缺 | `src/solver/solverbuffer.cpp`、`src/model/buffer.cpp` | min/max、逐段缺口、按日期补货 |
| CTP 试算 | `Demand::STATUS_QUOTE/INQUIRY` | trial demand 参与排程、读回可行日 |
| 输出 | `src/model/operationplan.cpp`、`pegging.cpp` | start/end/quantity/demands pegging |

**社区版没有** `freppledb/inventoryplanning` 目录；库存规划 UI 是商业版。
预测/库存/交期/净额，本仓库已有资产（见 Related），**不要为它们部署 frePPLe**。

### 4. “订单日期必填”等阻抗只在跑系统时成立

frePPLe 的 PO/DO/MO 需要日期，不表达 `unknown ETA`；一个 item 一个 UOM；无“疑似重复批次”。
如果只借算法，这些不影响：**unknown 行不进算法，只对已证子集计算，结果回我们自己的表合并**。
不要把“跑系统”的阻抗当成“借逻辑”的否决项。

## Why This Matters

- **许可证**：抄 7.x 代码会把 AGPL 带进来；8.0+ MIT 才可安全借鉴。
- **商业边界**：W3 最需要的库存规划/承诺交期恰是商业版；社区版只有求解器。
- **工程现实**：连接器停更 4 年，默认回写，与“不自动下单”冲突。
- **真正价值**：frePPLe 是“求解层参考”，不是“证据层/数据层”的替代品。

## When to Apply

- 评估 APS/供应计划器、CP-SAT/OR 方案时，先按本表区分“跑系统/借逻辑”；
- 要移植 lead-time offset / allocation / pegging 时，按上表定位源码；
- 看到“官方有 ERPNext 连接器”时，先查维护状态和许可证，不要直接 `bench get-app`。

## Examples

- 需要“现在下单，走慢船/快船/空运分别何时可用”：用 W2 的 `leadtime_config` 正向加即可，
  不需要 frePPLe；
- 需要“客户问最快哪天能交”（CTP）：再借 `STATUS_QUOTE` trial demand；
- 需要库存规划：用本仓库 `inventory_policy.py` / `sc08_conformal.py` 的 β/α、L+R、order-up-to 框架；
- 需要预测：本仓库已装 `statsforecast 2.1.1`（AutoETS + MA3/naive guard），不要重造。

## Related

- [2026-10-27-frepple-evaluation.md](../../research/supply-chain/2026-10-20/claude/control/reviews/2026-10-27-frepple-evaluation.md) — 完整研究（版本/许可证/功能映射/源码清单）
- [2026-10-27-existing-assets-forecast-inventory.md](../../research/supply-chain/2026-10-20/claude/control/reviews/2026-10-27-existing-assets-forecast-inventory.md) — 项目已有预测/库存/交期/净额资产
- [search-first-before-implementing.md](../workflow-issues/search-first-before-implementing.md) — 先搜分支/PR，再决定重造
- https://frepple.com/docs/current/license.html
- https://raw.githubusercontent.com/frePPLe/frepple/master/COPYING
- https://raw.githubusercontent.com/frePPLe/frepple/7.0.0/COPYING
- https://frepple.com/editions/
- https://frepple.com/docs/current/erp-integration/erpnext-connector.html
- https://github.com/msf4-0/ERPNext-Frepple-Integration
