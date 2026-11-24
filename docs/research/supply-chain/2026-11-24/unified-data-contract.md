---
okf: v0.1
type: Spec
title: 补货与需求协同 — 统一数据契约 v1（证据链 / 人工留痕 / 评估 / Agent 工具面）
description: 把证据链、Agent 接口、可配置默认值三份研究合成一份可实现、可验收的契约：实体与键、行级证据信封、写入与审核、闭环评估、REST/MCP/CLI 映射、配置、迁移与验收
date: 2026-11-24
owner: keyapi
status: 设计稿（draft）；未改业务代码、未部署、未 push、未开 PR
contract_version: supply-contract/v1
scope: supply_copilot / demand_collaboration / supply_netting（只读口径）
tags: [contract, evidence-chain, human-in-the-loop, openapi, mcp, fva, migration, acceptance]
---

# 统一数据契约 v1

> **本轮只写契约。** 不改业务代码、不部署、不写生产数据、不调用 EN 写接口。
> 本仓库是 **PUBLIC**：本文只写口径、字段、路径与行号，**不写任何分行数量、SKU 级库存、客户名明细、凭证**。
> 数值上限（分页、批量、预算）是**建议启动配置**，须用合成负载实测后定稿。

## 0. 定位、证据等级与取舍

### 0.1 这份契约是什么

| 是 | 不是 |
|---|---|
| 页面、REST/OpenAPI、MCP、CLI、评估**共用的字段与语义定义** | 不是某个界面的实现 |
| 对现有 `supply_copilot` / `demand_collaboration` 输出的**规范化重述 + 缺口补全** | 不是第二套决策引擎，不重算 D5/D6 |
| 可验收的**检查项清单**（§8） | 不是服务目标批准书、不是采购授权 |

三份输入研究（同目录另一批次分支）：

| 输入 | 分支 / 固定内容 | 本文用它做 |
|---|---|---|
| 证据链与人工闭环 `evidence-chain-and-human-loop.md` | `keyapi/evidence-chain` | 字段清单、差距 A/B/C、判断类型、FVA/override/DM、UI 四层 |
| Agent 数据接口 `agent-data-interface.md` | `feature/agent-data-interface-research` | 五形态分层、REST/MCP/CLI 目录、权限、错误/分页/幂等、MVP 验收 |
| 默认可配置值 `decision-defaults.md` | `feature/decision-defaults-20261124` | 参数名、默认值、作用域、审批人、失效方式 |
| 项目口径 `control/DECISIONS.md` D38–D40、`PROJECT_ROADMAP.md` | 本工作树 | **冲突裁决的最高依据** |

### 0.2 证据等级

| 标记 | 含义 |
|---|---|
| **L** 本地事实 | 本工作树源码/测试确认；不代表已部署 |
| **F** 外部事实 | 官方规范/维护方文档（见 §9 来源） |
| **R** 建议 | 针对本项目的设计判断，需实施验收 |
| **U** 未核实 | 生产版本、真实配置、性能未测；不得当现状 |

### 0.3 与三份研究的取舍（本文裁决）

| # | 冲突点 | 取舍 | 依据 |
|---|---|---|---|
| X1 | 证据链建议 8 元组含 `as_of` 作行键；接口研究要求 `row_id` 绑定 snapshot、跨快照用业务键 | **7 维 `scope_key` + `snapshot_id` → `row_id`**；`as_of` 是快照属性不是维度 | 证据链自己也写"重新生成内容 hash 不替代跨快照的业务键"；D40 要求质量与身份可复现 |
| X2 | 接口研究写"SO 未加入建议量"；证据链 D8 讨论"冲减还是另加" | 引入 **`so_role`**：`supply_pipeline`（EN 分公司 SO，上游交付管线）**永不进需求**；`customer_demand`（终端客户单）才讨论 `so_in_forecast`；未知则两者都不做 | D39 §4「前向接口必须先分清源语义」；PR #375 已按此修（`tests/test_decide_supply_semantics.py`） |
| X3 | 默认值表 `po_on_time` 是三态"ETA 可售 ≤ 需要日"；现码是二分桶 | 采用**三态 + `eta_basis`**；`unknown` 不进 `supply_proven` | 证据链 B1 + 默认值表 `eta_unknown/po_on_time` |
| X4 | 评估文档 §6 用 A/B，D39 改名"试验一/二"，D40 定 `MODEL_ONLY`/`FULL_FLOW` | 只用 **`MODEL_ONLY` / `FULL_FLOW`**；旧 A/B 不再复用 | D39 §2、D40 统一命名 |
| X5 | 默认值表 `weekly_grain` "功能未完成前保持禁用"；证据链允许 `ADJUST_PERIOD` | 允许**按已有源期间**改期；**不开放周桶拆分**，直到守恒证据与 `weekly_grain` 同版本启用 | 默认值表；D38「月内分配假设必须明示」 |
| X6 | 证据链 B4 说代码注释"CG 可跨分公司调拨"，业务口径"下游缓冲不可回拨" | 契约统一 `cg_role = downstream_buffer`；无 `policy.max_share` 时 `cg_usable = null` | 11-13 UX 简报 + 默认值表 `system_manager_scope` 精神（配置不得绕过业务口径） |
| X7 | 两处研究都用"未知=null"，但现码在"源存在、该键无行"时取 0 | 新增 **`assumed_zero`** 状态：仍是 0，但**必须计数并暴露**，不得静默 | AGENTS 工作流三原则②「未匹配记录必须保留」；证据链 §5.3 第 6 项 |

---

## 1. 实体与键

### 1.1 实体清单

| 实体 | schema | 唯一键 | 可变性 | 谁写 |
|---|---|---|---|---|
| 证据快照 | `supply-snapshot/v1` | `snapshot_id`（内容 hash） | **不可变** | 取数服务 |
| 建议行 / 证据行 | `supply-row/v1` | `row_id` | 随快照生成，不改 | 计算服务 |
| 源行引用 | `supply-source-ref/v1` | `evidence_id` | 不可变 | 计算服务 |
| 人工判断（提案） | `supply-proposal/v1` | `proposal_id` + `content_hash` | 只能追加 / `REVOKE` | 运营（人） |
| 审核裁决 | `supply-review/v1` | `approval_id` | 只能追加 | 审核人（人） |
| 发布 | `supply-publication/v1` | `publication_id` | **不可变**，只能 `supersedes` | 发布人（人） |
| 实际结果 | `supply-outcome/v1` | `(scope_key, snapshot_id, actual_window)` | 追加 | 评估任务 |
| 配置版本 | `supply-config/v1` | `config_version` | 追加（回退=新版本指旧值） | 管理员 + 审批 |
| 审计事件 | `supply-audit/v1` | `event_id`（`seq` 单调） | **append-only** | 服务端同事务 |

### 1.2 键的构造（可复现，禁止"猜"）

**`scope_key`（7 维业务键）**

```
sku_canonical | customer | warehouse_pool | physical_form | uom | period_start | period_end
```

| 维度 | 规范化 | 允许为空？ | 空值表达 |
|---|---|---|---|
| `sku_canonical` | NFKC、去首尾空白、大小写按 `sku_map` 注册值 | 否 | 缺 → 行不生成，计数 `identity_unknown` |
| `customer` | 客户码 / `SO_CUSTOMER_POOL` 取值 | 是 | `""` + `ownership_pending=true`（**不并入任何分公司**） |
| `warehouse_pool` | `resolve_warehouse_role` 的 `canonical_warehouse` | 否 | 缺 → 不生成（**绝不合并到主仓**） |
| `physical_form` | 成品 / 半成品 / 皮壳（原值） | 是 | `""` 保留原值，不归并 |
| `uom` | `service_policy.csv` 的 `canonical_uom` | 否 | `uom_unknown` → 数量 `null` |
| `period_start/end` | ISO 日期，闭区间 | 否 | 缺 → 不生成建议行 |

编码：各维禁止包含 `\x1f`；以 `\x1f` 连接后按 UTF-8 编码。

**`row_id` / 快照**

```
snapshot_id = sha256( canonical_json(snapshot_body_without_ids) )
row_id      = sha256( snapshot_id + "\x1f" + scope_key )
evidence_id = sha256( source_id + "\x1f" + source_row + "\x1f" + row_hash )
```

| 性质 | 要求 | 验收 |
|---|---|---|
| 同输入 → 同 hash | 规范化 JSON（`sort_keys`、无 `NaN`、decimal 转字符串） | §8 #1 |
| 跨快照可 join | `scope_key` 不随快照变；`row_id` 必变 | §8 #2 |
| 同快照唯一 | `(snapshot_id, scope_key)` 唯一 | §8 #1 |

**其余键**

| 键 | 公式 | 说明 |
|---|---|---|
| `proposal_id` | 客户端 ULID/UUID（幂等键，**不是**内容 hash） | 重试同 ID 同内容 → 原结果；异内容 → 409 |
| `content_hash` | `sha256(canonical_json({actor_sub, payload}))` | 与现有 `core.py:digest` 同构 |
| `approval_id` | `sha256({proposal_id, revision, content_hash, reviewer_sub, scope_hash, expires_at})` | **内容变动即失效**，防重放（F：MCP 审批边界） |
| `publication_id` | `sha256(publication_body)` | 与现有 `Store.publish` 一致（`core.py:376-377`） |
| `config_version` | 单调递增整数 | 每次发布一个版本；回退也发新版本 |

### 1.3 同一物理商品的多形态 / 多别名归并

**判据：能归并的只有"同一形态、同一 UOM、同一期间"的同一物料；其余一律分行。**

| 场景 | 处理 | 禁止 |
|---|---|---|
| 通途 SKU ↔ EN `item_code` ↔ 赛狐 SKU ↔ 客户物料号 | 由 `sku_map.tsv`（`mapping_status=mapped` 且**唯一**目标码）归一 | 多匹配取第一条；未映射当 0 |
| 前缀 `PK#` / `ND#` / `删除` | `so_evidence.sku_of` 现有剥离**保留**，但结果标 `identity_status=legacy_strip`，须回填 `sku_map` | 无登记的即席剥离当已归类 |
| `-Cover` / `-Foam` 等变体 | **独立行**，`physical_form` 区分；共享库存代理走 `sellfox_cover_inventory` 口径，不进本契约的数量合并 | 把皮壳量加到成品行 |
| 三角皮壳 `PK#` → `KS×1` | 只能通过已发布的组合/代理映射表达 | 在行内相加 |
| 同一 Item 的整件与 `-Cover` 同时有需求 | 两行并存，合计以 `physical_form` 分组报 | 只报一个总量 |
| 客户码缺失 | 单独行 `ownership_pending=true`，默认 HOLD，**可见** | 静默隐藏（11-13 反例） |
| 仓库别名 | `resolve_warehouse_role`；`counts_as_available=false`（退货仓/次品仓）排除并计数 | 并入主仓 |
| UOM 不同（个/箱/套） | 无版本化换算表 → `uom_unknown`、数量 `null` | 假设 1:1 或按箱规估算 |

---

## 2. 只读证据模型（行级）

### 2.1 数字信封（本契约的核心约束）

**每一个数量/金额字段都不是裸数字，而是一个信封。** 页面、JSON、Parquet 用同一结构（Parquet 展开为 `field_value/field_status/field_missing_reason/field_as_of/field_source` 列或嵌套 struct）。

```json
{
  "value": 120.0,
  "unit": "piece",
  "status": "measured",
  "missing_reason": null,
  "as_of": "2026-11-24T05:17:00+08:00",
  "basis": {"stage": "opening_C", "counts_occupancy": false},
  "source": {
    "source_id": "en_stock_run",
    "kind": "file|api|pack|manual",
    "file_sha256": "…",
    "row": 42,
    "row_hash": "…",
    "imported_at": "2026-11-24T06:02:11Z",
    "fetched_at": "2026-11-24T05:17:40Z"
  }
}
```

| 字段 | 枚举 / 规则 |
|---|---|
| `status` | `measured`（本时点实测）· `estimated`（模型/分位）· `replay`（历史包回放）· `conditional`（依赖未证前提）· `assumed_zero`（源完整但该键无行，**必须计数**）· `unknown` |
| `missing_reason` | `source_unavailable` · `not_ingested`（未接入） · `identity_unknown` · `uom_unknown` · `warehouse_ambiguous` · `period_unknown` · `not_matured` · `policy_unset` · `scope_assumed` |
| `value` | decimal 或 `null`；**`null` 只能配 `unknown`**；`0` 只能是 `measured`/`assumed_zero` |
| `unit` | 与 `scope_key.uom` 一致；金额为 `{"amount": "12.34", "currency": "USD"}` 字符串 |
| `as_of` | 该数字**所属源**的业务时点（不是下载时间） |
| `basis` | 由字段类型决定，见 §2.2–§2.5 |

**派生量规则**：任一必需分量 `unknown` → 派生量为 `null`，并带 `missing: [分量名]`。**合计不跳过 NULL**：

```json
"total": {"value": null, "known_count": 812, "unknown_count": 37,
          "completeness": 0.956, "incomplete": true, "sum_of_known_only": 4021.0}
```

`sum_of_known_only` 只作诊断，**不得**作为需求/供给总量出现在任何结论里。

### 2.2 需求段（D）

| 字段 | 结构 / 口径 | 检查什么 | 现状（L） |
|---|---|---|---|
| `demand.qty` | 信封，`basis:{period_basis, quantile, horizon_days, model_id, model_version, trained_until}` | 是整期还是剩余期；哪一档分位 | `decide.py:520-527` 只有 `demand_source` 文本 |
| `demand.period_basis` | `entire_source_period` · `remaining_period` · `explicit_start_end` | 硬规则：D5 97/157 天是**整期**，不得改名为剩余期；剩余期须新预测或有据逐桶重算 | `recommendation.py` 有 `period_basis`；`decide` 无 |
| `demand.quantile` | `p50` · `p90` · `p95` · `null` | 同报 D6 q95 与 live p90 时，汇总层须计数各档行数 | `decide.py:478-480` 有逐行标注，无汇总计数 |
| `demand.censoring` | `null` 或 `{flags:[stockout/clearance/zero_stock], observed:[date…]}` | 该 SKU×期间是否需求被截断 | **无** |
| `demand.hist` | `{series:"shipment\|orders", window:[s,e], net_of_returns:bool, channels:[…]}` | 历史是发运还是接单；是否扣退货 | **无** |
| `demand.confidence` | `{level:null\|low\|medium\|high, basis:null, text:"源值"}` | `level` 无计算依据时必须 `null`，`text` 原样保留 | `recommendation.py:192-212` 只做文本归一 |

### 2.3 SO 段（三段 + 方向）

**方向先行（D39 §4 / X2）**：

| 字段 | 枚举 | 规则 |
|---|---|---|
| `so.role` | `supply_pipeline` · `customer_demand` | EN 分公司 SO = 上游工厂交付管线 → **不进需求、不抵主建议**；只有 `customer_demand` 才讨论冲减/另加 |
| `so.in_forecast` | `true` · `false` · `null` | `null` → 既不加也不减，该行 `conditional`；禁止默认相加 |
| `so.effective_filter` | `{docstatus:"1", exclude_closed:true, exclude_amended:true, positive_balance_only:true}` | 取消/替代单排除；`Closed` 正余额**单列**"死单"，不静默丢 |

**三段守恒（`so_evidence.py` 已实现，契约要求显式布尔）**

```
so_open_qty == so_recent_open_qty + so_history_open_qty + so_unknown_date_open_qty
```

段定义：`recent` = 创建日 ≥ `as_of − 6 个月`（窗口可配、可冻结）；`history` = 更早仍开放（保留）；`unknown` = 创建日缺失或晚于 `as_of`。**三段都必须出现在响应里，包括为 0 的段。**

**行级字段（`so_lines[]`，逐行保留不丢弃）**

| 字段 | 说明 |
|---|---|
| `so`, `so_line` | 单据号 / 行号 |
| `item_code`（原值）+ `sku_canonical` | 原值与归一值并列，禁止只留一个 |
| `qty`, `delivered`, `open_qty` | `open_qty = max(0, qty − delivered)`；**整单 `per_delivered` 不能代替行余额** |
| `status`, `docstatus`, `amended_from` | 状态与作废链 |
| `delivery_date`, `overdue_days`, `warehouse` | 交付日与逾期 |
| `stage` | 生产 / DN / 在途 / 已收（未知则 `null`） |
| `transaction_date`, `date_bucket` | 创建日与所属段 |
| `evidence_ref` | `evidence_id` → 源文件 + 行号 + `row_hash` |

### 2.4 供给段（C / E / 阶段去重 / `po_on_time`）

**阶段**（同一批供应只能计一次）：

```
opening_C → en_intransit → po_open → wo_in_process → dn_out → shipment_in_transit → receiving_and_shelving
```

| 字段 | 结构 | 规则 |
|---|---|---|
| `supply.opening` | 信封，`basis:{warehouse, counts_occupancy, includes_defects, includes_return_warehouse}` | 是否已扣占用**必须显式**；含次品/退货仓须声明 |
| `supply.intransit` | 信封，`basis:{stage:"en_intransit", saleable_eta}` | 已发运未到 |
| `supply.po_open` | 信封，`basis:{document_key, eta, eta_basis, status}` | 开放量 = `quantity − in_quantity`；`status∈{0,1,2}` 开放、`4` 作废 |
| `supply.waiting_observed` | 信封，**只观察** | 未对单的待发量：不进 `supply_proven`、不进 `new_qty`，只做解释 |
| `supply.cg` | 信封，`basis:{role:"downstream_buffer", policy_max_share}` | `role` 恒为下游缓冲；无 `policy.max_share` → `usable=null`，只给上界 |
| `supply.stage_dedup` | `proven` · `max_rule` · `unproven` | 有 `lot_key` 且账对得上 → `proven`；未知批次 → **同一批只取 `max(intransit, po_on_time)`**（现码已实现，`decide.py:581`），标 `max_rule` |
| `supply.lead_time` | 信封，`basis:{route, mode, calendar:"calendar\|business", sample_size}` | 反推的"需要日−下单日"**不是实测交期**，只能是 `estimated`（`decide.py:803-815`） |

**`po_on_time` 三态定义（X3，覆盖现码二分桶）**

```
on_time(line) =
  true    ⇔ eta_saleable 存在 且 eta_saleable ≤ need_date 且 qty/warehouse/uom 均已证
  false   ⇔ eta_saleable 存在 且 eta_saleable >  need_date
  unknown ⇔ 日期或数量任一未知，或 eta_basis ∉ {warehouse_receipt, saleable}
```

- `need_date` 是**该桶真正需要可售数量的日期**；`eta_basis=port_arrival` **不等于**可售，除非配置了已证的上架偏移。
- 逐批判断：一张 PO 的最后日期早于计划期末，**不能**抵掉全部早期缺口。
- 聚合：`po_on_time_qty`（true）+ `po_late_qty`（false）+ `po_unknown_qty`（unknown）；三者之和 = `po_open`，差数必须为 0。

**净额**

```
supply_expected = opening + max(可计入的相邻阶段) + cg_usable
supply_proven   = opening + po_on_time_qty + cg_usable
new_qty         = ceil(max(0, demand − supply_expected))
worst_case      = ceil(max(0, demand − supply_proven))
```

不变式：`new_qty ≤ worst_case`；`supply_proven ≤ supply_expected`；`cg_usable=null` 时两项均为 `null`（不给"少补"的假结论）。

### 2.5 来源段（每个数字的身份证）

| 字段 | 现状（L） | 契约要求 |
|---|---|---|
| `source.file_sha256` | 有：库存/SO/PO（`decide.py:107-111, 612-613`）；CSV 快照（`recommendation.py:240-241`） | 每个源**逐行**引用同一文件 hash |
| `source.row` / `row_hash` | 仅 CSV 快照有（`recommendation.py:383-385`） | 全部源都要（`decide` 现无） |
| `source.imported_at` | CSV 留空（`recommendation.py:537`） | 必填，UTC |
| `source.as_of` / `fetched_at` / `stale` | live 库存有 `ok`/`fallback_stale`（`live_stock.py`） | 四源各自时点 + 状态；`max_lag_hours` 检查 |
| 对账 `input = accepted + rejected + skipped` | 仅 CSV 快照（`recommendation.py:424-427`） | **所有**源都要，含 D6/D5/D3b |
| 拒收/跳过原因 | CSV 快照有 | 全部源都要 |

### 2.6 就绪度与新鲜度（与默认值表联动）

| 源 | `ok` | `warn` | `hold` | 依据 |
|---|---|---|---|---|
| 库存 | ≤24h | >24h | >48h | `inventory_age` |
| 预测 | ≤7d | >7d | >14d（或目标期间错） | `forecast_age` |
| SO 证据 | ≤7d | >7d | >14d（**仅依赖它的行/结论**） | `so_evidence_age`；证据龄按抽取覆盖时点，**不按 SO 创建日**，重新下载不能变新 |

`readiness ∈ {research, conditional, confirmed, hold}`（D40 统一命名）。试点期 `replenishment_eligible` **恒 `false`**；`hold` 行只能展示旧版/情景，不可批准。

---

## 3. 写入模型（人工判断 / 审核 / 发布）

### 3.1 判断类型（冻结枚举）

| 类型 | 语义 | 数量效果 | 必填 | 可提交 | 可裁决 | 二级批准 |
|---|---|---|---|---|---|---|
| `ACCEPT` | 认可系统建议（"我核过了"） | 不变 | 依据 | 运营 | 审核人 | 否 |
| `ADJUST_QTY` | 改量：`delta` / `total` / `percent`（三选一） | 替换/增减 | 模式、值、依据、证据、有效期间 | 运营 | 审核人 | 触发阈值时 |
| `ADJUST_PERIOD` | 改需要日/覆盖窗口 | 不改量 | 新起止、源依据 | 运营 | 计划复核 | 跨月时 |
| `EVENT_ONLY` | 报事件：促销/提价/活动/渠道/断货/交期 | 不改量 | `event{id,type,start,end,scope}` | 运营 | 审核人 | 否 |
| `REJECT` | 驳回系统值 | 不生效 | 理由 + 证据 + 被驳回值 hash | 审核人/主管 | （本身即裁决，不留待他人） | 否 |
| `NEED_EVIDENCE` | 暂不能判断 | 保持 `null` | `missing[]` | 任何角色 | 不裁决 | 否 |
| `REVOKE` | 撤销某条既有判断 | 恢复原值 | `revokes=proposal_id` + 理由 | 原作者/审核人 | 审核人 | 否 |

**`ACCEPT` 是最重要的一条**：没有它就无法区分"没人看"与"人看过并认可"，FVA 也就无法归因到人（证据链 §3.1）。

### 3.2 谁能写、谁能审（防自批）

| 规则 | 要求 | 现状（L） |
|---|---|---|
| 身份 | `actor_sub` 来自 **EN OIDC / 公司 SSO**；不从命令行/请求体传 | 现为进程参数 `--actor`/`--role`（`demand_collaboration/__main__.py:12-13`） |
| 角色 | 服务端由 EN 角色派生：Demand Contributor → 运营；Demand Reviewer / System Manager → 审核 | `frappe_bridge.py:33-36` 已有 |
| 防自批 | **不同 `sub`**（不是不同字符串标签）；同一 `sub` 不得在**同一行 + 同一基准版本**上既 `ADJUST_*` 又 `REJECT` | `core.py:329-330` 仅字符串比较 |
| 二级批准 | `\|delta\|/base > override_priority_threshold`（默认 20%）或 `base=0 且 new>0` 或"不补→补且跨月" → 第二人（计划/主管） | 无 |
| 机器身份 | Agent 只能 `proposal:write`；`decision`/`publication` scope **不授予** | 无 |
| 审批凭证 | `approval_id` 绑定 reviewer + 实体 revision + content hash + 范围 + 过期；内容变动即失效 | 无 nonce |

### 3.3 版本与冻结

```
pack_version（数据包） → snapshot_id（证据/建议快照） → baseline_version（需求基准）
                       → publication_id（决策日冻结版） → config_version（本次配置）
```

| 规则 | 要求 |
|---|---|
| 冻结 | 发布 = 建议 + 判断 + 输入 hash + `config_version` + `algorithm_version` 打包成不可变快照 |
| 不覆盖 | 新事实（新库存/SO）**不覆盖**旧快照，只生成新版本并标 `supersedes` |
| 过期 | 判断 `end < as_of` → 标 `expired`，**不删除**，下一版重新评估 |
| 逐周滚动 | 未过期调整自动继承并显示"沿用（作者/日期）"；与本周系统方向相反时**必须提示**，不静默覆盖 |
| 只对剩余期 | `period_start = max(判断起点, as_of+1)`，避免重复调整已过去的部分 |
| 重审 | 数值/期间/归属/配置/输入源版本任一改变，或批准后 >7 天未采用 → `needs_reapproval=true` |

### 3.4 幂等与失败保留

| 项 | 规则 |
|---|---|
| 幂等键 | `Idempotency-Key` 头 = 客户端 `proposal_id`；唯一范围 = 主体 + 操作 + 键 |
| 重放 | 同键同内容 → 返回**原响应** + `Idempotent-Replay: true`（HTTP 200）；**不新增行** |
| 冲突 | 同键异内容 → `409 idempotency_conflict` |
| 批次 | 单批 ≤100 行（配置）；每行 `client_row_id` + `status` + `code`；**鉴权失败整批拒绝**，业务失败部分接收并完整报告 |
| 守恒 | `batch.input = accepted + rejected + skipped`；重复键/冲突/缺证据**不丢弃** |
| 失败保留旧版 | 写操作单事务；失败写 `last_attempt{status:failed, code, message}`；发布失败保持上一个 `publication` 指针；配置发布失败保持父版本并标失败 |

### 3.5 每条写入的审计字段

```json
{
  "event_id": "…", "seq": 1043, "prev_hash": "…", "request_id": "…",
  "actor_sub": "…", "actor_kind": "human|agent|system", "client_id": "…",
  "action": "proposal.submitted|decision.approved|publication.published|config.published|read|export|denied",
  "entity_type": "proposal|publication|config|snapshot", "entity_id": "…", "revision": 2,
  "scope": {"branch": "…", "skus": "hash", "period": ["…","…"]},
  "payload_hash": "…", "before_hash": "…", "after_hash": "…",
  "snapshot_id": "…", "config_version": 7, "algorithm_version": "…",
  "reason": "…", "decision": "approved", "at": "2026-11-24T12:00:00Z", "policy_version": "acl/v3"
}
```

**分级（不夸大）**：MVP = "状态 + 同事务追加事件"；禁止业务身份 `UPDATE/DELETE` 审计；`prev_hash` 形成哈希链，**但同一管理员仍可同时改库与链** —— 只有引入独立权限域的签名检查点/WORM 后才能提高抗篡改保证。在做到之前，文档与 UI **不得**写"不可篡改"（接口研究 §5）。读、导出、拒绝事件同样记录，且**失败审计不随业务回滚消失**。

---

## 4. 评估模型（闭环）

### 4.1 提案/审核与实际结果的关联

```json
{
  "schema": "supply-outcome/v1",
  "scope_key": "…", "snapshot_id": "…", "publication_id": "…",
  "proposal_ids": ["…"], "approval_ids": ["…"],
  "final_executed_qty": {"value": 120, "status": "measured", "basis": {"source": "approval"}},
  "actual": {"qty": {"value": 118, "status": "measured", "basis": {"series": "shipment"}},
             "window": ["…","…"], "matured_at": "…", "censored": false, "censor_reason": null},
  "evaluable": true, "not_evaluable_reason": null
}
```

| 关联规则 | 要求 |
|---|---|
| 键 | 只按**完全相同的 `scope_key`**（含期间）配对；重叠跨度**不得**当独立样本 |
| 成熟 | 只有"需求已到期且实际已结清"的桶可评 |
| 删失 | 断货/清仓导致的销量截断 → `censored=true`；不可评时标 `not_evaluable` + 原因，**不删除、不填 0** |
| 双轨保存 | 同期间同时保存"系统建议值"与"最终执行值"（FVA 的前提），另存 naive 基线 |

### 4.2 指标定义（直接引用，不新造）

| 指标 | 公式 / 口径 | 窗口 | 边界 |
|---|---|---|---|
| Fill rate β（**主报**） | 即时满足的需求**单位** / 总需求单位 | 固定评估窗口 | 潜在需求不可见时只报"已接订单满足率"或情景 β |
| CSL α（**辅报**） | 无缺货补货周期 / 有效补货周期 | 周期定义须固定 | 周期不可定义 → **不可评**；零需求周期单列 |
| Bias | `Σ(预测−实际)/Σ实际`；正=高估 | 同窗口 | 不同来源符号须转换并记录 |
| WAPE | `Σ\|预测−实际\|/Σ实际` | 同窗口 | **禁止**称 `1−WAPE` 为准确率 |
| FVA | 见 §4.3 | `fva_window`（默认 4 个完整周，累计 8 周复核） | 只评成熟桶 |
| 库存天数 | **时间加权**实物库存，不用期末余额 | L+R | 在途/在产资金另列 |
| 断货信号 | 有效观测下可售不可用的时间比例 | 快照间隔 | 快照稀疏时只报"信号"，不报"连续断货天数" |
| Tracking signal | `TS_t = Σ(F−A)/MAD`；`\|TS\|>4` **只作告警** | 滚动 | 阈值未批准，不作判据 |

### 4.3 FVA（三级相减）

```
FVA_统计模型 = 损失(naive)      − 损失(统计预测)
FVA_人工     = 损失(统计预测)   − 损失(最终执行值)
FVA_流程     = 损失(naive)      − 损失(最终执行值)
```

- 主指标 `fva_metric = FVA_WAPE = WAPE_auto − WAPE_final`；冻结定义，可加 MASE/pinball，**不可事后换冠军指标**。
- 必须同时报：样本 SKU 数、销量覆盖、**中位数**（不只均值）、"改坏占比"（FVA<0 的行占比）。
- 分层（按 `override` 是否带新信息）：

| 层 | 判据 | 期望 |
|---|---|---|
| L-A 有事件依据 | 填了 `EVENT_ONLY` 且事件日期覆盖该期间 | 应改善 |
| L-B 无事件、纯经验 | 只有 `ADJUST_QTY` | 常变差，重点监控 |
| L-C 只改期间 | `ADJUST_PERIOD` | 评"到货日误差"，不评需求量误差 |

- 降级告警（`override_degradation`）：连续 2 个成熟 4 周窗 FVA<0，或 β 比 auto 低 >2 个百分点、库存高 >20% → 提示复核该原因/分组；**不按个人小样本处罚、不自动撤权**。
- 个人 FVA 只给本人与主管，**不进公开看板**。

### 4.4 "纯自动 vs 自动+人工"（`MODEL_ONLY` / `FULL_FLOW`）

| 设计 | 做法 | 因果强度 | 记录字段 |
|---|---|---|---|
| ① 同期间成对比较 | 同一 `(SKU×周)` 同时存系统建议与最终执行 | 中（有选择偏差） | `pair_id`, `arm=MODEL_ONLY\|FULL_FLOW`, `selection_bias: observed` |
| ② 反事实模拟 | 固定初始库存/需求真值/供给路径，只换政策 | 中高 | `simulation_id`, `seed`, `demand_path_hash` |
| ③ 分群随机化（影子） | 按 SKU 簇/周块随机分组 | 高 | `experiment_id`, `assignment_unit`, `pre_registered_at`, `pre_registration_hash`；**须业务授权** |

统计口径：
- 损失差分 + **Diebold–Mariano** 检验 `E[d_t]=0`（允许非二次、非对称损失与误差自相关）。
- **不得**按 SKU 独立检验再数 p 值；必须**按 SKU 簇/时间块 block bootstrap**（D40 §4）。
- 样本量先算后跑：`n ≈ (z_{1−α/2}+z_{1−β})²·σ²/δ²`；比例指标 `σ²=p(1−p)`。**周级、单分公司、数百 SKU 的样本对断货率通常不足以显著**，只能评连续指标（如"同 β 下库存占用"）。
- 预注册：指标、最小可检测效应、退化容忍、切点、检验方法，**先写后跑**；不允许事后挑显著项宣布成功。

---

## 5. 契约到工具面的映射

### 5.1 分层（F：官方规范；R：本项目）

**REST/OpenAPI 是业务契约，MCP 是任务适配，CLI 是批处理入口，语义层是共同语言。** UI、CLI、MCP 全部调用同一服务与同一授权检查；MCP 不另建一套规则（接口研究 §1–3）。

### 5.2 REST / OpenAPI（`/api/v1`，全部为设计，不是现存端点）

| 端点 | 方法 | 请求 DTO | 响应 DTO | scope | 幂等 |
|---|---|---|---|---|---|
| `/catalog` | GET | `{branch?}` | `{datasets[], fields[], freshness{}, config_version}` | `supply:read` | 天然 |
| `/queries/recommendations` | POST | `{branch, period_start, period_end, snapshot_id?, filters{}, group_by[], page{limit,cursor}}` | `{rows[], page, applied_filters, metric_version, query_hash}` | `supply:read` | 天然（可缓存键） |
| `/queries/evidence` | POST | `{row_ids[] \| scope_keys[], snapshot_id}` | `{rows[], page}` 每行含信封 + `source_refs[]` | `evidence:read` | 天然 |
| `/refresh-jobs` | POST | `{branch, skus?="授权全集", reason}` | `{job_id, scope_frozen, snapshot_id_expected}` | `refresh:run` | `Idempotency-Key` |
| `/jobs/{id}` | GET | — | `{status, counts{in,succeeded,failed,skipped}, reasons[]}` | `refresh:run` | 天然 |
| `/proposal-batches` | POST | `{batch_id, items[{client_row_id, proposal}]}` | `{items[{client_row_id,status,code,proposal_id}], counts}` | `proposal:write` | `Idempotency-Key` |
| `/proposals/{id}/decision` | POST | `{status: approved\|rejected\|cancelled, revision, reason, approval_id}` | `supply-review/v1` | `decision:write` | `If-Match` revision |
| `/publications` | POST | `{baseline_version, snapshot_id, as_of, approved_only:true}` | `supply-publication/v1` | `publication:write` | `Idempotency-Key` |
| `/publications/{id}` | GET | — | 同 | `supply:read` | 天然 |
| `/publications/{id}/download?format=json\|parquet` | GET | — | 文件流（`Content-Disposition`、`Digest` 头） | `supply:read` | 天然 |
| `/configs` | GET | `{scope?}` | `{versions[]}` | `supply:read` | 天然 |
| `/configs` | POST | `{key, value, unit, scope, reason, evidence, effective_at, expires_at, parent_version}` | `{config_version}` | `config:write`（人工，非 Agent） | `Idempotency-Key` |
| `/outcomes` | POST | `supply-outcome/v1` | `{outcome_id}` | `eval:write`（服务账号） | `Idempotency-Key` |
| `/evaluations` | GET | `{metric, window, strata[], snapshot_ids[]}` | `{metrics[], samples, power}` | `supply:read` | 天然 |

**查询/过滤/聚合白名单**：允许的 `group_by` 与 `metrics` 由服务端枚举；SKU 默认精确匹配，模糊必须显式且先消歧；`branch`/期间/`snapshot_id` 必填或由已授权保存视图确定；**不提供任意 SQL、任意路径、任意 RPC 方法名**。

**分页**：建议默认 100、最多 500 行/页；冻结快照上按稳定 `row_id` keyset 排序；cursor 不透明，绑定主体 + 策略版本 + `snapshot_id` + filters + 过期时间；越权/过期 cursor 拒绝；`matched_count` 只统计授权范围。

**大结果**：内联预算 256 KiB，超限返回 `has_more`/`next_cursor` 或 `export_id`；`returned_count/matched_count/has_more/truncated/reason` 必报；聚合覆盖**全授权集合**而不是第一页。

**错误结构**（F：RFC 9457 + 扩展）：

```json
{"type": "https://contract/supply/errors/idempotency-conflict",
 "title": "Idempotency key reused with different content",
 "status": 409, "code": "idempotency_conflict",
 "detail": "同一 proposal_id 的内容与已存记录不一致",
 "instance": "/api/v1/proposal-batches",
 "request_id": "req_…", "retryable": false,
 "field_errors": [{"field": "items[3].value", "code": "negative_result"}]}
```

不泄漏 SQL、凭证、私有路径。MCP 业务失败用 `isError` + 同一错误对象；CLI 用同一 `code` + 非零退出码。

**并发**：`expected_revision` / `ETag`+`If-Match`；基准/修订陈旧 → 409/412；裁决与发布在事务内再次读版本/重叠/权限。

### 5.3 MCP 工具（v1 精选，手选，不从 OpenAPI 全量生成）

| 工具名 | 入参 | 出参 | 读/写 | scope |
|---|---|---|---|---|
| `describe_supply_data` | `{branch?}` | 目录 + 语义 + 新鲜度 + `config_version` | 只读 | `supply:read` |
| `query_recommendations` | 同 `/queries/recommendations`（分页参数必填或显式默认） | 行 + `page` | 只读 | `supply:read` |
| `get_supply_evidence` | `{row_ids[]}` 或 `{scope_keys[], snapshot_id}` | 证据行（含 `source_refs[]`） | 只读 | `evidence:read` |
| `start_branch_refresh` | `{branch, reason}` | `{job_id}` | 写（只写本地分析产物） | `refresh:run` |
| `get_job` | `{job_id}` | 状态与计数 | 只读 | `refresh:run` |
| `submit_proposals` | 同 `/proposal-batches` | 行级状态 | 写（仅提案） | `proposal:write` |
| `get_publication` | `{publication_id}` | 发布快照（按范围裁剪） | 只读 | `supply:read` |
| `get_supply_config` | `{scope?}` | 配置版本（只读） | 只读 | `supply:read` |

**v1 不向机器暴露**：`decision`、`publication` 写、`config` 写、`outcomes` 写。工具注解（readOnly/destructive）**不是**授权边界（F：MCP 安全最佳实践）；仅隐藏 `tools/list` 或提示"请勿写入"不能阻止直接调用。MCP 的工具发现分页**不等于**业务结果分页，两者独立设计。

### 5.4 CLI（薄封装；离线计算保留为显式 `mode=offline`）

| 命令 | 对应 | 输出 | 退出码 |
|---|---|---|---|
| `supply-copilot catalog --branch X` | `/catalog` | JSON | 0 / 2 参数 / 3 鉴权 / 4 后端 |
| `supply-copilot recommend --branch X --json` | 离线回放 | `supply-row/v1` 行 | 同上 |
| `supply-copilot decide --branch X --json` | 本地 live 决策 | 行 + `manifest` | 同上 |
| `supply-copilot evidence --row-id R` | `/queries/evidence` | 行级证据 | 同上 |
| `supply-copilot supply --branch X` | `start_branch_refresh` | `manifest.json` | 同上 |
| `supply-copilot job --id J` | `/jobs/{id}` | 状态 | 同上 |
| `demand-collab submit --file f.json` | `/proposal-batches` | 行级结果 | 同上 |
| `demand-collab decide --id P --status approved` | 人工裁决（拒绝机器凭证） | 裁决记录 | 同上 |
| `supply-copilot evaluate --window …` | `/evaluations` | 指标 + 样本量 | 同上 |

约定：`--json/--jsonl/--cursor/--output`；**stdout 只放机器结果，stderr 放进度**；token 走环境/文件，**不放命令行参数**；离线模式 `mode=offline` **不得**产生批准或发布。

### 5.5 权限（身份 × 操作 × 行列范围）

| 主体 | 身份 | 可做 | 不可做 |
|---|---|---|---|
| 人（运营） | EN OIDC（授权码 + PKCE），`sub` 来自验证结果 | 读授权范围、提交判断 | 裁决、发布、扩权 |
| 人（审核） | 同 | 裁决、发布（限授权范围，`sub≠author`） | 自批、跨范围 |
| 人（主管/财务） | 同 | 二级批准；财务参数加签 | 绕过值范围 |
| 服务账号（取数/评估） | 独立机器身份、短期凭证 | `supply:read`/`evidence:read`/`refresh:run`/`eval:write` | `decision:write`/`publication:write`；不复用 System Manager |
| Agent（MCP） | 继承发起人主体或独立机器主体 | 查询、重算、提交提案 | 裁决、发布、生成"人工已批准"字段 |

- scope 只表达**动作**；行/列范围由服务端人员/商品/分公司关系与字段许可表决定（成本、毛利、客户明细另控）。
- **默认拒绝**：范围缺失即拒；`branch` 参数只是筛选，不扩权；鉴权先于查询、聚合、缓存命中、导出与错误细节。
- 缓存键含主体/授权版本/字段许可；权限撤回后旧 cursor 与下载**不可继续用**。
- 私有导出按范围生成，链接短效且重新鉴权；**已下载的文件无法用 token 追回**，只能靠生命周期与终端访问限制。
- 当前隔离边界 = SQLite 服务层授权 + 文件 ACL；不同授权主体**不得**直接读同一个全量 DB/pack。

---

## 6. 配置项

### 6.1 存储与优先级

- 全部参数进**版本化配置表**（`supply-config/v1`），每次运行固定 `config_hash`，发布记录带上它。
- 优先级：**SKU×分公司例外 > 分公司×商品分型 > 分公司 > 全局**；未匹配回到上层；**未知事实不通过继承变成 0**。
- SKU 例外必须同时带仓/库存池、形态、UOM、期间，避免跨形态串用。
- 字段：`config_version/parent_version/key/scope/old/new/unit/reason/evidence/author/approver/effective_at/expires_at`；默认下一周版本生效；紧急修改也产生新版本并撤销受影响审批；回退=发新版本指向旧值，不删日志、不覆盖历史快照。
- 例外默认 7 天到期（允许 1–28 天，审核人可改）；到期回上层政策，相关未执行判断重新审核。

### 6.2 不可突破的硬约束（受保护配置，允许集合恒 `{false}`）

`auto_order=false`、`write_en_business=false`、`allow_self_approval=false`、`unknown_as_zero=false`。管理员**不能**通过配置解除；回退同样受检查。

### 6.3 本契约直接消费的参数（默认值以 `decision-defaults.md` 为准，此处不复制数值）

| 组 | 键 | 契约在哪用 |
|---|---|---|
| 身份/范围 | `operator_scope`、`reviewer_scope`、`system_manager_scope`、`pilot_scope` | §5.5 行级范围；空范围=拒绝 |
| 新鲜度/就绪 | `inventory_age`、`forecast_age`、`so_evidence_age`、`critical_unknown`/`readiness` | §2.6 三态门槛 |
| 期间/粒度 | `weekly_grain`（试点期禁用）、`weekly_freeze`、`review_period_R`/`protection_period` | §2.2 期间口径、§3.3 冻结 |
| 分位/服务 | `segmentation_basis`、`abc_breaks`/`xyz_basis`、`service_beta_target`、`service_alpha_target`、`quantile_preset`、`q95_downgrade_gate`、`hard_service_infeasible`、`inventory_policy`、`safety_stock_method`、`history_fallback` | 需求信封 `basis.quantile`；评估目标 |
| 交期/ETA | `lead_time_quantile`、`lead_time_evidence`、`eta_unknown`/`po_on_time` | §2.4 三态与 `eta_basis` |
| 约束 | `moq`/`order_multiple`、`hard_budget`、`soft_budget_warning` | 取整与告警；**不得**当采购授权 |
| 写入/审批 | `accept_auto`、`override_quantity`、`override_priority_threshold`、`event_only`/`period_override`、`reapproval` | §3 判断必填与二级批准 |
| 评估 | `fva_window`、`fva_metric`、`override_degradation`、`pilot_window` | §4 窗口与降级告警 |
| 特殊状态 | `special_cny_owner_hold` | 逐行 HOLD，不得一键放行 |

**变更即重审**：`reapproval` 规定任一数值/期间/归属/配置/输入源版本改变 → 相关判断 `needs_reapproval`；与依赖无关的行**不全表撤销**。

---

## 7. 迁移与兼容

### 7.1 `supply_copilot.decide` 行 → `supply-row/v1`

| 现字段（`COLUMNS`，`decide.py:67-79`） | 契约字段 | 转换 |
|---|---|---|
| `branch` | `scope.branch` | 枚举 `美东USNJ/美中USTX/波兰` |
| `sku` | `scope.sku_canonical` | 已是 `product_id` |
| `warehouse` | `scope.warehouse_pool` | 固定主仓 |
| `uom`, `pool`, `physical_form` | `scope.*` | 原值 |
| （无） | `scope.period_start/end` | **新增**：来自 D6 窗口（须显式，不从 as_of 推） |
| `action` | `action.code` | `补/不补/待核` → `replenish/no_replenish/needs_review`；**新增** `expedite`/`observe`（现缺，`decide.py:593` 抄 D6） |
| `new_qty` | `qty.new`（信封） | 现为 `ceil`；契约要求 `qty.new.raw`（未取整）+ `qty.new.display`（取整） |
| `new_qty_if_conditional_late` | `qty.worst_case` | 同 |
| `expedite_qty` | `qty.expedite` | 现直接抄 D6，须标 `status=replay` 直到按 live 重算 |
| `need_date` / `order_date` / `date_source` | `dates.need` / `dates.order` / `dates.source` | 枚举 `d6_pack\|computed_lead` |
| `need_date_status` / `order_date_status` | `dates.need_status` / `dates.order_status` | `future/past_due/null` |
| `demand_qty` / `d6_q95` / `demand_source` / `demand_evidence` | `demand.qty` / `demand.reference.p95` / `demand.source` / `demand.evidence_text` | 包进信封 |
| `supply_opening/intransit/po/cg/so/expected/proven` | `supply.*` | 各自信封 + `basis.stage` |
| `qty_status`（`measured/replay/unknown_*` 拼接串） | `status{code, missing[]}` | **结构化**；禁止拼接字符串 |
| `reason` / `warnings` | `explain.reason[]` / `explain.warnings[]` | 数组化 |
| `stock_snapshot_at/sha256/date` | `sources.stock.*` | + `row` / `row_hash`（**新增**） |
| `forecast_run_id` / `forecast_as_of` | `sources.forecast.*` | + `config_hash` |
| `so_sha256` / `po_sha256` | `sources.so.sha256` / `sources.po.sha256` | 逐行引用 |
| `cg_source` | `supply.cg.basis.source` | `live_capped_by_d6` → `policy_pending` |
| `source` / `mode` | `snapshot.mode` | `live` / `replay_fallback` |

`meta`（`decide.py:880-904`）→ `supply-snapshot/v1.manifest`：`mode/branch/as_of/pack/stock/forecast/so/po/cg/supply_evidence/executable/executable_reasons/stock_age_hours/totals/warnings/limits`，新增 `snapshot_id`、`config_version`、`algorithm_version`、`sources[].coverage`。

**迁移期必须先修的 3 处**（另外三处口径问题 —— `po_on_time` 二分桶、SO 计入需求、同批 `intransit`+`po` 重复叠加 —— 已在 PR #373–#375 修好，对应验收见 §8.2 #8–#10）：

| # | 位置 | 问题 | 迁移动作 |
|---|---|---|---|
| M1 | `decide.py:374-389` | 原始 EN SO 导出分支用 `item_code` 原值作键，未过 `lookup`；主循环用 `product_id` → 皮壳/通途码/带后缀的 SO **静默落 0**（B2 残留） | 该分支先 `lookup` 归一；归不上标 `identity_unknown` 计数，**不取 0** |
| M2 | `decide.py:532-533` | 源存在即"无行=0"，无 `assumed_zero` 计数 | 改为 `assumed_zero` 信封 + `totals.assumed_zero_rows` |
| M3 | `decide.py:900` | `limits` 仍写"未履约 SO 按未完成量计入需求"，与 §2.3 及现有代码相反 | 删除该句，改为"SO 为上游交付管线，不进需求" |

### 7.2 `usnj-recommendation/v1` 行 → `supply-row/v1`

| 现字段 | 契约字段 | 备注 |
|---|---|---|
| `row_id`（`digest(7 元组)`） | `row_id`（`snapshot_id + scope_key`） | 旧值保留为 `legacy_row_id` |
| `sku/customer/warehouse/physical_form/uom/period_start/period_end` | `scope.*` | 一致 |
| `period_basis` | `demand.period_basis` | 现有 `explicit_start_end/period_range/week…` → 映射到三值枚举，其余转 `explicit_start_end` 并记 `legacy_basis` |
| `action` + `action_recognized` | `action.code` + `action.recognized` | 未知动作不得映射成 `hold`，须 `needs_review` |
| `qty/expedite_qty/new_order_qty` | `qty.expected/expedite/new` | 信封 + `unit` |
| `coverage` + `coverage_text` + `coverage_unit` | `coverage{value,text,unit,basis}` | **`basis` 现未知**（"45 天量"还是"到某天"）→ 迁移期必须 `basis=null, status=unknown`，UI 标"待核" |
| `confidence` + `confidence_text` + `confidence_level` | `confidence{level,basis:null,text}` | `level` 无依据时 `null` |
| `c_qty` / `e_qty` / `forecast` / `q50/q90/q95` / `model` | `supply.opening` / `supply.intransit` / `demand.qty` / `demand.quantiles` / `demand.model` | 同值换结构 |
| `source_row` / `source_hash` | `sources.rows[].row` / `.row_hash` | 已有，保留 |
| `extra`（未映射列） | `sources.raw.unmapped` | 保留原列名与值 |
| `needs_decision/low_confidence/missing_supply/special/ownership_pending` | `flags.*` | 布尔集合 |
| `so_*`（14 个汇总字段）+ `so_lines[]` | `so.*` | **加 `role`/`in_forecast`** |
| `so_included_in_recommendation`（现恒 false） | `so.in_instead_of_demand=false` | 语义改名，禁止再出现"在建议内"表述 |
| `service_certified` / `replenishment_eligible` | 同名字段，**恒 false** | 服务端强制，忽略入参（`core.py:150-151`） |

快照头（`recommendation.py:506-534`）→ `supply-snapshot/v1`：`source_sha256/as_of/columns/unmapped_columns/input_count/accepted_count/rejected_count/skipped_count/reconciled/status/unknown_policy/unknown_counts/flag_counts/assumptions/so_evidence_source/so_window_*`。

### 7.3 提案/基准/发布 → 契约

| 现结构（`core.py`） | 契约 | 转换 |
|---|---|---|
| `proposals.data.id` | `proposal_id` | 同值（幂等键） |
| `row_id`（指向基准行） | `subject.row_id` + `subject.scope_key` | 基准行需先能算出 `scope_key`（`product_id+branch+unit+physical_form+period`） |
| `kind`：`delta/total/percent/event_only` | `judgment_type=ADJUST_QTY` + `mode`；`event_only` → `EVENT_ONLY` | 映射表冻结；新增 `ACCEPT/REJECT/NEED_EVIDENCE/REVOKE` |
| `value` / `start` / `end` | `quantity{value,mode}` / `period{start,end}` | 负值结果禁；`percent` 语义保留 |
| `reason` / `evidence`（文本） | `reason` / `evidence[]`（结构化引用） | 文本仍收，但至少 1 个结构化引用 |
| `baseline_version` | `binding.baseline_version` + `snapshot_id` | 新增快照绑定 |
| `status/revision/reviewer/decision_reason/author` | 同 + `approval_id` / `actor_sub` | 角色改由 OIDC 派生 |
| `baseline.rows[].id/week/baseline_qty/period_end` | 判断主体 + `period` + `demand.baseline` | 周期间仍只接受与源期间完全对齐（`core.py:298-299`），不开放拆周 |
| `publications.data` | `supply-publication/v1` | `id/sha256/published_by/published_at/rows/proposal_decisions/assumptions` 保留 |
| `audit`（`seq/actor/action/entity/at/detail`） | `supply-audit/v1` | 加 `actor_sub/request_id/payload_hash/before_hash/after_hash/policy_version/prev_hash` |

### 7.4 版本号规则

| 规则 | 要求 |
|---|---|
| 每个 DTO 带 `schema_version`（如 `supply-row/v1`） | 客户端必须校验 **major**；major 不符拒绝渲染 |
| 加字段 | minor 升级；**响应**允许新增字段，客户端忽略未知；**请求**严格拒绝未知字段（`fields()` 已如此，`core.py:61-64`） |
| 改枚举/改语义 | major；需迁移脚本 + 双读窗口 |
| 兼容窗口 | 过渡期服务端同时提供 `legacy` 视图（旧字段名），至少一个发布周期；旧 `row_id` 与新 `row_id` 同时输出 |
| 语义变更必须留痕 | 变更写 `log.md` + 配置 `algorithm_version`；历史报告不重写 |

### 7.5 分阶段落地（先加 / 后加）

| 阶段 | 内容 | 理由 |
|---|---|---|
| **A 先加（不新接数据源）** | `scope_key`/`row_id`/`snapshot_id`；数量信封 + `status`/`missing_reason`；`assumed_zero`；SO 三段 + `role` + `in_forecast`；`po_on_time` 三态 + `eta_basis`；`sources.row/row_hash/imported_at`；`config_hash`；M1–M3 修复 | 证据链 §6 结论：**B 类（接错了）优先于 A 类（没接）** —— 先让已有数字可信 |
| **B 后加** | WO / DN / Shipment 阶段（先 `null` + `not_ingested`）；`censoring`；`lead_time` 证据；`lot_key` 与 `stage_dedup=proven`；`coverage.basis` 基准核定；`confidence_basis` | 需要新数据源或业务裁定 |
| **C 工具面** | REST `/api/v1` 全部端点；MCP 精选工具；CLI 薄封装；OIDC 身份；`approval_id`；评估端点 | 依赖 A/B 的 schema 稳定 |

**不在本契约范围**（避免煮海）：CI/CD、监控面板、BI 平台、Marquez/dbt 上线、PostgreSQL 迁移、预测模型替换。D6/D5 的计算口径不由本契约改变。

---

## 8. 验收清单

每条给**验证方法**与**通过判据**；全部用合成/授权私有夹具，不读生产明细。

### 8.1 结构测试

| # | 契约项 | 验证方法 | 通过判据 |
|---|---|---|---|
| 1 | 键与规范化 | 同输入两次构建；改一维重建 | `snapshot_id`/`row_id` 完全一致；改任一维度 → 全变；`(snapshot_id, scope_key)` 唯一 |
| 2 | 跨快照 join | 两个快照各建一行 | `scope_key` 相同、`row_id` 不同，可连接 |
| 3 | 信封完整 | JSON Schema / Pydantic 校验全量行 | 每个数量字段都有 `value/unit/status/source`；`value=null` 的行 `status=unknown`；无字段缺失 |
| 4 | 枚举冻结 | 快照 diff 枚举值 | `judgment_type`、`action.code`、`stage`、`eta_basis` 与本文一致 |
| 5 | 别名歧义 | 构造一个 SKU 两条映射 | 返回 `ambiguous`，**不选第一条**；未映射行计数可见 |

### 8.2 守恒与口径

| # | 项 | 验证 | 判据 |
|---|---|---|---|
| 6 | 导入对账 | 三个源各跑一次 | `input = accepted + rejected + skipped`；差数为 0 或每条有原因 |
| 7 | SO 三段 | 构造 recent/history/unknown 各若干 | 三段之和 = 开放总量；**死单**（Closed 正余额）单独出现不丢 |
| 8 | SO 方向 | 复跑 `test_open_branch_so_is_supply_not_demand` | `demand_qty` 不含 SO；`supply_so` 有值；主建议不被无到货日 SO 抵扣 |
| 9 | `po_on_time` | 三个反例：ETA 早于/晚于/缺失需要日；`eta_basis=port_arrival` | 分别为 true/false/unknown；三态之和 = `po_open`；unknown 不进 `supply_proven` |
| 10 | 阶段去重 | 同批在 `intransit` 与 `po_open` 各出现 | 只计一次（`max_rule`）；有 `lot_key` 时 `stage_dedup=proven` 且加总一致 |
| 11 | 未知传播 | 缺 UOM / 缺 ETA / 缺库存 | 派生量 `null` + `missing[]`；`qty_status ≠ measured` 的行数被报出；**任何合计不跳过 NULL** |
| 12 | `assumed_zero` | 源完整、键不存在 | 值为 0 且 `status=assumed_zero`；`totals.assumed_zero_rows` 计数 |
| 13 | 期间语义 | 97/157 天整期输入 | `period_basis=entire_source_period`；改名"剩余期"被拒；剩余期需新预测或有据逐桶重算 |
| 14 | `new_qty ≤ worst_case` | 随机 1000 组合成行 | 不变式恒成立；`supply_proven ≤ supply_expected` |
| 15 | 新鲜度门槛 | 25h/49h 库存；8d/15d 预测与 SO | 分别 ok/warn/hold；`hold` 不可批准；**重新下载不解除 SO 证据陈旧** |

### 8.3 权限

| # | 项 | 验证 | 判据 |
|---|---|---|---|
| 16 | 双人双分公司矩阵 | 两个真实账号 × 两个分公司 | 越权读/聚合/state/证据/job/audit/download/直接工具调用**全部拒绝**或只返回授权集合 |
| 17 | 防自批 | 同一 `sub` 用两个标签 | 拒绝（`self_approval`），不是靠字符串不同就放行 |
| 18 | 机器身份 | 服务账号调 `decision`/`publication` | 403；Agent 无法写入"人工已批准" |
| 19 | 审批绑定 | 批准后改取值再裁决 | `approval_id` 失效；陈旧 `revision` 409 |
| 20 | cursor 撤回 | 授权撤销后用旧 cursor | 拒绝；下载链接同样不可用 |
| 21 | 范围空集 | 空范围配置 | 默认拒绝，**失败时不得回落到"看全部"**（评审发现：现 `filter_snapshot` 空名单调 `allows()` 返回 False 属正确，勿改） |

### 8.4 幂等与审计

| # | 项 | 验证 | 判据 |
|---|---|---|---|
| 22 | 幂等重放 | 同键同内容并发 5 次 | 1 条提案 + 1 条成功事件；响应一致 |
| 23 | 幂等冲突 | 同键改一个值 | 409，无新行 |
| 24 | 批次部分接收 | 100 行混合合法/重复/错期间/缺证据 | 每行有 `status/code`；`input=accepted+rejected+skipped` |
| 25 | 事务原子 | 中途注入失败 | 不出现"提案有记录、审计无记录" |
| 26 | 审计回放 | 从 audit + 冻结输入重算发布 hash | 一致；篡改测试被识别（有外部锚点）或**明确报告保证不足** |
| 27 | 失败保留旧版 | 发布/配置发布失败 | 旧版仍是当前；`last_attempt` 记录原因；不恢复旧采购资格 |

### 8.5 评估

| # | 项 | 验证 | 判据 |
|---|---|---|---|
| 28 | 双轨保存 | 取一个成熟桶 | 系统值/执行值/naive 三者同键可取；样本数与销量覆盖被报出 |
| 29 | FVA 分层 | 构造 L-A/L-B/L-C | 三层分别出 FVA、中位数、改坏占比；不只看均值 |
| 30 | 不可评标记 | 缺实际、删失、窗口不匹配 | `evaluable=false` + 原因，**不被静默丢弃**，不进分母 |
| 31 | 显著性 | 同 SKU 簇重复观测 | 用 block bootstrap + DM；**不按 SKU 独立检验数 p 值**；预注册字段非空 |
| 32 | 样本量 | 断货率指标 | 事前算出的 n 与功效被记录；样本不足时只报描述性，不宣布改善 |

### 8.6 迁移

| # | 项 | 验证 | 判据 |
|---|---|---|---|
| 33 | 旧包可读 | 用现有 D6/D5 夹具跑新 schema | 全部旧字段有映射；未知保持 `null`；差异逐行可解释 |
| 34 | 旧快照不被改写 | 载入旧 `usnj-recommendation/v1` 后发布 | 旧 `snapshot_id`/`publication_id` 不变；新版本带 `supersedes` |
| 35 | 版本 gate | `schema_version` major 不符 | 客户端拒绝渲染，报 `unsupported_schema` |

---

## 9. 未决与业务主权

| 项 | 状态 | 归属 |
|---|---|---|
| `po_on_time` 的 `eta_basis` 是否允许 `port_arrival`（到港≈可售的偏移量） | **U** 未证 | 物流负责人举证，审核人批 |
| 服务目标（β 90/95/99、按分型分层） | 探索网格，**非批准值** | 业务拍板（D40 §2） |
| 二级批准阈值（默认 20%，允许 10–100%） | 建议 | 业务拍板 |
| `coverage` 基准（"45 天量"还是"到某天"） | **U** 源表未证 | 业务/源表负责人 |
| 试点范围与周周期冻结时点 | 建议 6 周 / 周三 12:00 | 业务拍板 |
| 审计抗篡改等级（是否需要外部锚点/WORM） | 威胁模型未定 | 项目主 |
| 性能上限（分页/批量/refresh 并发） | **U** 未实测 | 实施时用合成负载定稿 |
| MCP 宿主对 scope/OAuth 扩展的支持 | **U** 未做互操作测试 | 实施前验证，不支持则不扩权兜底 |

**一句话**：契约把"每个数字能回源、每次人改能留痕、每次对比能复现"变成可检查的字段；服务目标、阈值、范围这些**业务主权**仍由人拍板，契约只保证拍板结果被忠实记录与执行。

## 10. 来源

- 本地（**L**）：`supply_copilot/{decide,recommend,refresh,cli,live_rules}.py`、`demand_collaboration/{core,recommendation,so_evidence,web,live_stock,recommendation_scope,frappe_bridge}.py`、`tests/{test_decide,test_decide_supply_semantics,test_demand_collaboration_recommendation,test_live_rules,test_rebuild}.py`、`docs/research/supply-chain/2026-10-20/claude/control/{DECISIONS,INVENTORY_EVALUATION,PROJECT_ROADMAP}.md`。
- 同批次研究（跨分支，只读）：`evidence-chain-and-human-loop.md`（`keyapi/evidence-chain`）、`agent-data-interface.md`（`feature/agent-data-interface-research`）、`decision-defaults.md`（`feature/decision-defaults-20261124`）。
- 外部（**F**）：[MCP 授权](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)、[MCP 工具](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)、[MCP 安全最佳实践](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices)、[RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457.html)、[Pydantic JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/)、[FastAPI](https://fastapi.tiangolo.com/features/)、[PostgreSQL RLS](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)、[Diebold & Mariano 1995](https://doi.org/10.1080/07350015.1995.10524599)、[SAS FVA](https://www.sas.com/content/dam/SAS/en_us/doc/whitepaper1/forecast-value-added-analysis-106186.pdf)、[Forecast value added in demand planning (IJF 2024)](https://www.sciencedirect.com/science/article/pii/S0169207024000736)、[Sobel 2004](https://pubsonline.informs.org/doi/pdf/10.1287/msom.1030.0027)。
