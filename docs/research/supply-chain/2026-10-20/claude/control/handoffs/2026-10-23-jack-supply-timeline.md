---
okf: v0.1
type: Handoff
title: Jack 供应链任务交接：供应时间线、交期配置与决策接口
date: 2026-10-23
owner: jack
sponsor: claude-foreman
---

# Jack 供应链任务交接

## 0. 一页人话（给用户和 Jack）

**最终目的**：回答“某个 SKU 在某个仓，未来什么时候会缺货、要不要补、补多少、走慢船/快船/空运分别何时能到”。

**这条链分三段**：

1. **需求**：未来卖多少（预测，分析侧负责，不是 Jack）。
2. **供应**：现在已经有多少、已下单多少、在产多少、已出运多少、在途多少、什么时候能变成可售库存（**Jack 负责这一段**）。
3. **决策**：需求 − 供应 = 缺口；再结合交期和运输方式，判断补不补、补多少（分析/业务负责，Jack 提供事实和选项）。

**Jack 不是做预测，也不是拍板下单**；他负责把 EN 里 SO→WO/JC→DN→Shipment→入库这条链，加上通途库存/PO，整理成一张**可信的供应时间线**，并提供**交期/运输方式的配置与情景**。这样分析侧不用猜 ETA，业务也不用靠感觉选运输方式。

---

## 1. 先说清楚：哪些是 EN 开发，哪些是 EN 数据分析

| 工作包 | 主要性质 | 是否改 EN 代码 | 说明 |
|---|---|---|---|
| **W1 供应时间线** | EN 数据整合 + 只读导出；可能少量 EN 只读 API/报表 | **通常不需要**；若现有 REST/报表不够，才加只读接口 | 大部分是读取 EN 单据，整理阶段/数量/日期；不改业务逻辑 |
| **W2 交期与运输方式配置** | 历史数据分析 + 配置层 | 不需要 | 40 多个运单样本，先做“假设配置”，不是统计预测 |
| **W3 决策就绪供应接口** | 数据接口/表 | 不需要改 EN 业务 | 给分析侧/补货引擎消费的只读视图；可先做本地表/API |
| **W4 完整性巡检** | EN 数据质量报告 | 通常不需要 | DN 缺运单、运单无 DN、ETA 过期等 |

**结论**：Jack 的主要工作是**读 EN 数据、建只读供应视图**；只有现有 EN 接口不足时才做少量只读开发。不要一上来改 EN 业务代码。

---

## 2. 项目已经做了什么，Jack 不要重做

现有成果（均在供应链项目内，可直接复用）：

- **SC03 Shipment**：`59c4e5ec`，301 PASS（D01/D02）。EN Shipment 自带 **11 个状态 + ETA + 轨迹节点**，47/47 命中；按 DN-item-UOM-role 输出向量；`credited_qty` 未验证，不能当入库数量。
- **SC04 供应阶段守恒**：`228bef77`，39 张 DN 各归一个阶段，三口径闭合；但 ETA/在途逐笔关系仍未全证。
- **SC02 前向账**：`19fb2c6e`，301 PASS；逐行来源、冻结桶可复算。
- **SC09 试用包**：`04b5b630`，M1-TRIAL-v1 冻结；行表 2,309 行/23 列；不是采购批准。
- **DN 桥**：`fc0c9562`，DN 状态接入有突破。
- **SC10 目录/映射**：`0463f4fa`，1,328 母集与完整目录差集；271 个有库存无近期销售等。
- **PR310**：通途库存最新/历史落地方案；当前库存只读 DocType、每日历史本地盘；Jack 的 #309 低库存抓取已 approve。

**Jack 的 W1 不是从零开始**：以 SC03/SC04/DN 桥为骨架，补齐“PO/WO/JC→DN→Shipment→入库”的时间线和阶段数量；不要重写已有抽取器，不要复制一套平行口径。

---

## 3. 分支与工作方式

- **分析/整合代码**：在 `fzh-data` 新建分支 `feature/jack-supply-timeline`，独立 worktree；只读脚本/报告/契约，不碰工头的分支。
- **EN 只读接口/报表**：只有 W1 确实需要时，才在对应 EN 自定义 app 仓库开 `feature/supply-timeline-api`；测试系统先验，生产按现有发布链路（pull upstream + migrate + clear-cache + restart）。
- **不并发改同一文件**：与工头/Claude worker 不同 worktree；提交前确认文件所有权。
- **输出位置**：`docs/research/supply-chain/.../experiments/supply_timeline/`（脚本/契约/报告），原始数据留本地，不提交。

---

## 4. W1：供应时间线（最高优先）

### 4.1 要回答的问题

对每个 `SKU × 仓库`：

- 现在可用多少？
- 已下单多少、预计什么时候到？
- 在产多少、做到哪道工序、预计什么时候完工/入库？
- 已出运多少、走什么运输方式、运单号/承运商/当前状态/ETA？
- 已入库多少？
- 每个数量只算一次；按需要日看，未来每周可用供给是多少？

### 4.2 数据来源

- SO：EN Sales Order / SO 行（需要日、未履约量）。
- WO/JC：EN Work Order、Job Card（剩余量、当前工序、预计完工）。
- 出库计划 / DN：EN Delivery Note（数量、日期、docstatus）。
- Shipment：EN Shipment（11 态、ETA、轨迹节点、运单号、承运商）。
- 入库：Stock Entry / Purchase Receipt（实收数量、日期）。
- 通途：库存最新/历史（PR310）、未结 PO（数量、下单日、ETA 若可得）。

### 4.3 输出表（建议字段）

```text
sku, warehouse, as_of_date,
stage,                  # on_hand / po_open / in_production / shipped_in_transit / received
doc_type, doc_name, doc_line,
qty, uom,
event_date,             # 下单/完工/出运/到港/入库
available_date,         # 预计可售日；未知写 null + date_confidence
date_confidence,        # confirmed / estimated / unknown
mode, carrier, tracking_number,
source_key,             # 可回溯到单据行
notes
```

### 4.4 规则

- 阶段互斥：同一数量不能同时算 PO、在产、在途、已入库。
- 部分完工/部分出运要拆剩余量；每部分只计一次。
- ETA 未知不得当“及时到货”；`date_confidence=unknown`。
- UOM 未证时不要跨单位合计；标 `uom_unproven`。
- 入库以实收为准；Shipment 的 `credited_qty` 未验证，不能直接当入库。
- 多仓不默认互通；调拨要有依据。

### 4.5 验收

- 10 个代表 SKU（用现有 D16 样本）先跑通；每个 SKU 的阶段数量对账、单据行可追溯。
- 未知/待核实显式列出；不填 0。
- 同一输入重复运行结果一致。
- 跑通后再扩 Top50；不先做全量。

---

## 5. W2：交期与运输方式配置（可并行，低难度）

### 5.1 现状

- 目前只有 40 多个运单号，历史统计不足；**先做“假设配置”**，不是统计估计。
- 交期可以先假设固定天数（慢船/快船/空运/3PL），后续用真实数据替换。

### 5.2 配置层（需要，且值得做）

建议新增一个版本化配置，而不是把天数硬编码在脚本里：

```json
{
  "version": "2026-10-23.1",
  "effective_from": "2026-10-23",
  "profiles": [
    {
      "route_id": "CN->US-WEST",
      "warehouse": "美东-CENTRADE",
      "mode": "slow_boat",
      "segments": {"order_to_departure": 14, "departure_to_arrival": 30, "arrival_to_stock": 7},
      "source": "assumed",
      "sample_size": 0,
      "owner": "business",
      "notes": "首批假设，待实际运单替换"
    }
  ]
}
```

- 字段：路线、仓、运输方式、分段天数、来源（measured/assumed/business）、样本数、生效日、负责人、备注。
- 变更记录：`LEAD_TIME_DECISIONS.md`，只追加；谁改、为什么、影响哪些 SKU。
- 决策时显示“用的是哪个版本/来源”；假设不得伪装成实测。

### 5.3 验收

- 配置文件 + 读取函数 + 单测；无配置时显式报错，不静默默认。
- 40 多个运单可作为“初步校验/异常检查”，不作为统计结论。
- 支持后续替换为实测 P50/P90，不改调用方。

---

## 6. W3：决策就绪的供应接口（W1/W2 之后）

### 6.1 一句话

**给补货决策一张“供应时刻表 + 如果现在下单走不同运输方式，何时能用”的查询表。** 它不是预测，也不是下单；它把 W1 的供应时间线和 W2 的交期配置，按周/按需要日汇总，供分析侧算缺口。

### 6.2 输入/输出

输入：

- SKU / 仓库；
- 需求视图（预测 P50/P90 或未履约 SO，由分析侧给）；
- 需要日/计划窗口；
- 交期配置版本。

输出（按周或按需要日）：

```text
sku, warehouse, week,
supply_confirmed,        # 已确认可用
supply_expected,         # 预计可用（含 estimated）
supply_unknown,          # 日期未知，单列
demand,                  # 分析侧给
gap,                     # demand - confirmed/expected
mode_option:             # 若现在下单
  slow_boat_available_date, fast_boat_available_date, air_available_date,
  cost_if_available
confidence, notes
```

### 6.3 边界

- 不输出最终采购量/下单建议；数量政策由分析/业务决定。
- 不把未知日期当可用；不把上界当实际供给。
- 同一供应只计一次；多仓调拨未证不合并。
- API/表只读；先本地/测试，生产读取需授权。

### 6.4 验收

- 给定 10 个代表 SKU + 需求视图，能输出每周供给、缺口、慢船/快船/空运可用日期。
- 每个数字可追溯到 W1 的单据行和 W2 的配置版本。
- 与分析侧现有 trial pack 的列能对齐；不能对齐的列显式说明。

---

## 7. W4：完整性巡检（最低优先）

只做 W1 可信所需：

- DN 无 Shipment / 无运单号；
- Shipment 无 DN；
- 重复运单号；
- ETA 过期/状态停滞；
- 入库存量与 DN 差异。

输出异常报告/计数；不逐条人工补单号作为主线。可作为 W1 的配套，不单独扩成大项目。

---

## 8. 建议的推进顺序与交付

1. **W1**：10 个代表 SKU 供应时间线（复用 SC03/SC04/DN 桥；只读）。
2. **W2**：交期配置 + 决策记录（可与 W1 并行）。
3. **W3**：供应接口/周表（W1/W2 稳定后）。
4. **W4**：最小巡检，边做边补。

每项交付：固定 commit、脚本/契约、样例、单测、计数对账、未知清单；不写生产、不下单、不改主数据、不合并 PR。

## 9. 需要工头/分析侧配合

- 提供需求视图（预测/SO）与需要日口径；
- 提供 10 个代表 SKU 名单及现有 trial pack 列定义；
- 确认 W1 输出字段与 SC09 试用包对齐；
- 业务确认运输方式/服务水平的假设；Jack 只实现配置和计算，不替业务拍板。
