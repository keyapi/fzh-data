---
okf: v0.1
type: Spec
title: 第一步：需求—实现—缺口—验收母集与双线裁决规则
date: 2026-10-29
owner: claude-worker
status: step-1-contract-confirmed-step-2-in-review
scope: read-only; no production deploy; no business data writes
---

# 第一步：契约与验收母集

> 依据：PR #312 的 `EN-CHAIN-REVIEW-2026-10-29.md`、`JACK-EN-REQUIREMENTS-2026-10-29.md`，以及 #312 最新评论。
> 复用 #314 已验收的 supply-facts、退货容量账本、单位校验、版本一致性与原子导出；本阶段**不写新的业务算法**。

## 0. 本轮已确认的业务口径

| 问题 | 确认结果 |
|---|---|
| 双线进度裁决 | **终态粘性 + 否则取更晚时间**：已签收/已完结为终态，不被后续非终态人工更新覆盖；非终态按 `latest_progress_at` 更晚者胜 |
| 时间相同、状态不同 | `conflict_flag=true`，`latest_progress_status=unknown/null`，交人工复核；不静默选 |
| 时间缺失 | 按 §0.2 唯一决策表：单缺时间选有时间者并标 `conflict_flag=true`；双缺时间 `unknown`；终态缺时间仍按终态粘性优先 |
| 异常状态 | 不参与排序，`unknown` + `conflict_flag=true`，保留两条原值 |
| “10 个代表 SKU” | 沿用 2026-10-23 冻结名单：**9 个不同 SKU + 1 个缺额**（“有 PO·ETA 可验证”无合格样本），不补第 10 个、不替换样本 |

### 0.1 双线裁决的可执行定义

输入两条标准化进度线：

```text
line = {
  status, event_time, source, source_updated_at, raw_status
}
```

裁决：

1. 任一条为终态（`已签收` / `已上传POD` / 已完结）：
   - 若只有一条终态：选该条，`is_final=true`；
   - 若两条都是终态且时间不同：选时间更晚的终态；
   - 若两条终态时间相同但状态不同：`unknown` + `conflict_flag=true`。
2. 两条都不是终态：
   - 两条都有 `event_time`：取更晚者；
   - 只有一条有时间：选该条，但 `conflict_flag=true`；
   - 两条都没有时间：`unknown` + `conflict_flag=true`；
   - 时间相同但状态不同：`unknown` + `conflict_flag=true`；
   - 任一条是异常状态：`unknown` + `conflict_flag=true`。
3. 输出必须同时保留两条原始线（状态、事件时间、来源、来源更新时间），便于追溯。

示例（用户给的歧义案例）：

```text
A: 昨天 已签收  (source=carrier_tracking)
B: 今天 在途    (source=manual)
→ latest_progress_status = 已签收
→ latest_progress_at = 昨天
→ progress_source = carrier_tracking
→ is_final = true
→ conflict_flag = true
→ 保留 B 的今天/在途原值
```

### 0.2 缺时间唯一决策表（第四步直接按此实现）

> 本表是缺时间场景的唯一口径；摘要、契约、代码注释不得再用“缺时间→unknown”这一泛化说法。

| 场景 | latest_progress_status | latest_progress_at | is_final | conflict_flag |
|---|---|---|---|---|
| 两条都非终态；仅 A 有时间 | A | A 的时间 | false | true（证据不完整） |
| 两条都非终态；两条都无时间 | `unknown` | null | false | true |
| A 终态、B 非终态；A 有时间、B 无时间 | A | A 的时间 | true | true |
| A 终态、B 非终态；A 无时间、B 有时间 | A（终态粘性） | null | true | true |
| 两条都终态；仅一条有时间 | 有时间的终态 | 该时间 | true | true（另一条缺时间） |
| 两条都终态；都无时间且状态相同 | 该终态 | null | true | false |
| 两条都终态；都无时间且状态不同 | `unknown` | null | false | true |
| 任一条是异常状态 | `unknown` | null | false | true |

补充：两条都有时间但相同、状态不同 → `unknown` + `conflict_flag=true`（见 §0.1 第 2 条）；
两条都有时间、状态相同 → 取该状态，时间取该时间，`conflict_flag=false`。

## 1. 10 个代表 SKU 与原有 9 SKU 的关系

来源：`docs/research/supply-chain/2026-10-20/claude/control/reviews/2026-10-23-jack-sample10.md`（冻结名单）。
**10 个名额 = 9 个不同 SKU + 1 个缺额；不是 10 个不同 SKU。** 不混用 G1B 的另一个 10 SKU 样本。

| # | 名额/类别 | SKU | 备注 |
|---:|---|---|---|
| 1 | 紧急履约 | `TT0031038K0062927` | PO/在途重叠 |
| 2 | 多阶段重叠 #1 | `C/Linen-Natural-100-688-wow` | 在产 + PO/在途重叠 |
| 3 | 多阶段重叠 #2 | `TT0312701K0064561` | PO/在途重叠 |
| 4 | 有在产 | `CENCord995-DKGrey-97` | 2 张开放 WO，余量以现场查询为准 |
| 5 | 有 PO·ETA 可验证 | — **缺额** | 本地无合格样本；不替换 |
| 6 | 有 PO·ETA 不确定 | `C/Cord-White-100-706-wow` | 3 条未结 PO，ETA 全空 |
| 7 | 零库存有历史销量 #1 | `C/Velvet-White-100-664-wow` | 无未结 PO |
| 8 | 零库存有历史销量 #2 | `TT0031010K0062880` | 无未结 PO |
| 9 | 有库存·表面充足 | `CEN1607NLinen-Ivory-194` | 仅表面充足 |
| 10 | 有库存·可能不足 | `CENKZ1323-LTGrey-97` | 3PL 仓，归属未证 |

> 9 个 SKU 均来自同一 122 行候选母集；第 5 个名额的缺额是“本地无带 ETA 的未结 PO 行”，属准确阻塞，不是没有选到合适 SKU。

## 2. 验收母集（具体单据）

### 2.1 Shipment（5 张，覆盖双线/ETA/深圳入仓）

| Shipment | 状态（status11/status4） | 来源 | 关键证据/用途 |
|---|---|---|---|
| `SHIPMENT-00007` | 已离港 / 在途 | 云交天下 | `eta=2026-11-18`，事件描述又写 ETA 11/08；两套 ETA 冲突样例 |
| `SHIPMENT-00050` | 报关中 / 待发 | T6 | `eta=2026-11-16`；关联 DN-26-00114；深圳转运中心 warehouse_in，**不能当海外到达** |
| `SHIPMENT-00015` | 已上传POD / 签收 | 智美通 | `ata=2026-10-03`、`dlvr=2026-10-13`；终态样例 |
| `SHIPMENT-00016` | 已上传POD / 签收 | 智美通 | `ata=2026-10-15`、`dlvr=2026-10-23`；终态样例 |
| `SHIPMENT-00014` | 已签收 / 签收 | 智美通 | `eta=2026-08-20`；已签收样例 |

### 2.2 已签收 Shipment（5 张）

`SHIPMENT-00008`、`SHIPMENT-00009`、`SHIPMENT-00010`、`SHIPMENT-00011`、`SHIPMENT-00012`（均为 `已上传POD` / `签收`）。
用于验收 `shipment_signed_at`、`tongtool_receipt_at`、`receipt_lag_days`、`stock_state` 的字段存在与防重，不要求逐箱实收。

### 2.3 在产 SKU（5 个不同 SKU，来自生产 In Process 工单）

| WO | SKU | SO | 状态 |
|---|---|---|---|
| `WO-26-02166` | `PK#KS0328-HLR-98-RED` | SO-26-00089 | In Process |
| `WO-26-02142` | `PK#KS0001-CMKTR-100-GREY` | SO-26-00088 | In Process |
| `WO-26-02050` | `KS0181-MM-45-BLUEWHITESTRIPE` | SO-26-00087 | In Process |
| `WO-26-02040` | `PK#KS0001-CMM-140-LIGHTGREY` | SO-26-00085 | In Process |
| `WO-26-02032` | `PK#KS0001-CMM-194-LIGHTGREY` | SO-26-00085 | In Process |

> 另保留 W1 样本中的 `CENCord995-DKGrey-97`（WO-26-00684 / WO-26-03366）和 `C/Linen-Natural-100-688-wow`（WO-26-00254 / 01609 / 03171）作为“在产但完工日已知/未知”的补充追溯样例，不另凑第 6 个名额。
> 数量不在本文固化；验收时按生产当前值读取，避免行级数量进入公开仓库。

### 2.4 合成冲突案例（必测）

| 案例 | 输入 | 期望 |
|---|---|---|
| 终态 vs 后续非终态 | 昨天 已签收；今天 在途（人工） | `已签收` + `is_final=true` + `conflict_flag=true`；保留在途原值 |
| 同时间不同状态 | 10/29 10:00 已到港；10/29 10:00 清关中 | `unknown` + `conflict_flag=true` |
| 缺时间 | 一条有 10/25 开船；一条无时间 在途 | 选开船 + `conflict_flag=true` |
| 两条都缺时间 | 一条 清关；一条 派送 | `unknown` + `conflict_flag=true` |
| 异常状态 | 一条 `已签收`；一条 `异常/未知` | 终态优先 + `conflict_flag=true`，异常值原样保留 |
| ETA 两套 | SHIPMENT-00007 结构化 11/18 vs 事件描述 11/08 | 两值都保留，`conflict_flag=true`，不自动选一个当 actual |

## 3. “关闭”的含义（本轮）

- 关闭是**事实层状态切换与对账记录**：`in_transit` → `signed_pending_tongtool_receipt` → `tongtool_received`。
- **不写回 EN、不写回通途、不自动关闭源系统在途**；只生成本地只读事实与异常清单。
- 未签收：在途；已签收未入库：已到未入库，不再计在途；已入库且已纳入库存：只计库存。部分入库按已证数量拆分。
- 无通途关联或身份不明：保持 `unknown`，不得用数量相等强行关联。

## 4. 仓库语义

| 类型 | 例子 | 语义 | 不能做什么 |
|---|---|---|---|
| 工厂仓 | `FZH-DANEEY-成品仓/半成品仓`、绍兴工厂 | 生产/所有权侧仓 | 不能直接当海外目的仓可售 |
| 集货仓 | 深圳转运中心 | 国内集货/中转；`warehouse_in` 只证明到深圳 | **不能当海外到达**；不能据此关闭在途 |
| 海外目的仓 | CENTRADE、DANEEY、波兰仓、FBA 仓、WayfairCG-Cranbury (3PL) | 目标仓/可售侧 | 需有客户→分公司→目的仓映射证据 |
| `warehouse_scope` | `operator` | 当前表示**仓库运营方**（own/3pl/fba），不是库存所有权 | 不据此推断自由供给 |
| `scope` | `in_house` / `external_fba` | 用途/分配维度 | FBA 用途不等于仓库运营方；FBA 预留不能与自发货自由供给混算 |

## 5. 需求—现有实现—缺口—验收案例

| # | 需求（#312 审核） | 现有实现（#314） | 缺口 | 本阶段/后续验收 |
|---:|---|---|---|---|
| 1 | SO→WO/JC→DN→Shipment→目的仓统一只读视图 | `get_supply_facts` 的 lines/stage_balances/milestones/availability/links；版本/manifest | 通途 PO/入库未接入；目标仓映射未证；部分阶段 unknown | 单 SO、9 SKU 母集；仓库/阶段过滤语义（第二步）；第四步补双线 |
| 2 | 头程运单/ETA 结构化 | Shipment 自定义字段、events、custom_zmt_status11/eta/ata/dlvr | 事件类型/来源优先级/原始值/修订历史；两套 ETA | 5 张 Shipment（含 00007/00050）；合成冲突 |
| 3 | 签收→通途入库对账/在途关闭 | `receipt`/`tongtool_po`/`warehouse_receipt` 均 `not_integrated`；`available_date=null` | `shipment_signed_at`、`tongtool_receipt_at`、`receipt_lag_days`、`stock_state`、关闭记录 | 5 张已签收 Shipment；第五步 |
| 4 | 下单/开工/完工/出库/开船/到港/清关/入仓事件 | milestones 8 节点；WO/JC/DN/Shipment 时间 | 清关/目的仓入库节点；首工序≠完工；时区/来源 | 5 个在产 SKU；第三步 |
| 5 | DN/Shipment/ETA/阶段巡检 | 零散异常字段 | 未合并为一次可复算巡检；母集/成功/跳过/异常数 | 第六步 |
| 6 | 稳定只读导出/API、分页 | `supply_facts_export.py` JSON/Excel/manifest；版本一致性 | filters 静默扩大、顶层参数忽略、无分页元数据/partial | **第二步已实现**；见 `STEP2-INTERFACE-SCOPING.md` |

## 6. 阻塞项（本阶段不擅自决策）

1. 通途 PO/入库事件的权威来源、状态码字典与关联键（当前 `not_integrated`）。
2. 目的仓映射（客户→分公司→目的仓）及 3PL 仓归属。
3. FBA 预留量/自由供给的权威口径。
4. 30 分钟刷新频率与陈旧阈值（候选，未部署）。
5. 9 SKU 生产只读验收需要生产授权；测试站无该样本。
6. “关闭”不写回 EN/通途；是否需要在未来写回，需业务另行确认。

## 7. 下一步

- 第二步：严格 filters/顶层参数/分页契约（已实现，待 Codex 审核与测试站部署）。
- 第三步：拆 `first_process_done / all_process_done / qc_passed / stock_in_posted`。
- 第四步：按本文件 0.1 规则输出 Shipment 双线裁决。
- 第五步：签收→通途入库只读对账与防重（需先解决第 6 节阻塞 1–3）。
- 第六步：同批巡检与最终验收。
