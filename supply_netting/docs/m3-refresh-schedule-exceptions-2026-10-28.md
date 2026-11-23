---
okf: v0.1
type: Design
title: M3 刷新/调度/异常清单设计（不部署）
description: 复用 run_same_day 的失败不覆盖机制，补齐每日/按需刷新链、六类异常清单与闸门、版本与审批记录字段、最小落地步骤与验收
tags: [design, refresh, scheduling, exceptions, versioning, approval, rollback]
date: 2026-10-28
status: proposed
---

# M3 刷新/调度/异常清单设计（不部署）

> **本文只是设计**：不改 cron / 计划任务 / 生产配置，不 push，不动任何现有产物。
> 落地步骤在第 5 节，按步骤实施时再单独评审。

## 0. 结论先行

**刷新链已经存在，不需要重造。** `supply_netting/scripts/run_same_day.py` 已实现
「快照校验 → 冻结 → 需求 → 净额 → 决策包 → 动作」一条命令，并且**失败不覆盖最后成功版**
（暂存目录失败改名 `.failed-*`、正式目录不出现、`latest.json` 不更新）；
`docs/runbook-same-day.md` 已记录演练与手工回滚。

M3 要补的是三件它现在**没有**的东西：

1. **调度口径**：什么算「每日」、什么算「按需」，幂等键是什么（现在全由人决定 `--label`）；
2. **异常闸门**：六类异常现在散落在六个产物里，没有任何一处汇总，也没有「阻断 vs 提示」的判定，
   于是「数据有问题」和「数据没问题」长得一样；
3. **版本 / 审批记录**：现在能追到「哪一版是最新」，但**追不到「谁批准了哪一版、批准了什么范围」**——
   而补货建议是要人签字下单的。

## 1. 刷新链

### 1.1 五段链路（全部对应真实入口）

| # | 阶段 | 入口（现有） | 输入 | 输出 | 失败时 |
|---|---|---|---|---|---|
| 0 | 快照落盘 | 外部（通途/EN 导出） | `en_stock.parquet` | 同上 | 链不启动 |
| 1 | 快照校验 + 冻结 | `run_same_day.validate_snapshot` / `freeze_snapshot` | 快照 | `_inputs/en_stock-<date>-backup.parquet` | **拒绝执行**，不动任何产物 |
| 2 | 需求 | `self_fulfilled_demand.canonical`（或复用已有 `demand_netting.parquet`） | gs/en/映射 | `demand_netting.parquet` | 整条链失败 |
| 3 | 净额 | `supply_netting.__main__` | 需求 + 冻结快照 + 预测 + sku_map + PO | `run-<date>-<label>/` | 整条链失败 |
| 4 | 决策包 | `supply_netting.decision_pack` | 净额 + 需求 | `decision-pack-<date>-<label>/` | 整条链失败 |
| 5 | 动作层 | `supply_netting.pack` + `decision_join` | 决策包 + SO/W1 | `actions-<date>-<label>/` | 可 `--allow-optional-failure` 保留前四步 |
| 6 | 指针 | `latest.json` | 以上全部 | 指针文件 | **只有全程成功才更新** |

### 1.2 两种触发

| 触发 | 条件 | 动作 |
|---|---|---|
| **每日** | 新 `en_stock.parquet` 到达，且 `snapshot_date` = 今天 | 全链跑一次，`--label` 从 `r1` 起 |
| **按需** | ① 预测重训（`forecast/CURRENT` 变了）② 审核 reject 后的返修 ③ 上游补证回填（ETA/单位/PO）④ 快照重出（同一天补数据） | 同日 `--label` 递增（`r2`/`r3`…），**绝不覆盖已发布版本** |

**不做**：不做「每 N 小时定时轮询」。轮询只会产生内容相同的版本、把 `latest.json` 刷得没有意义。
触发条件由数据到达事件决定，不由时钟决定。

### 1.3 幂等键

```
idempotency_key = (snapshot_date, label, code_commit)
```

- 同键重跑：冻结快照哈希相同 → 复用（已有行为）；正式目录已存在 → **拒绝**，除非 `--force`
  （已有行为，`_promote` 抛 `目标已存在`）；
- 换 `label` 就是新版本，旧版原样可读（已实测 r1/r2 共存）。

### 1.4 失败不覆盖（已实现，此处只做登记）

现状机制（`run_same_day.py`）：

1. 所有输出先写 `.pipeline-<date>-<label>-<ts>/` 暂存；
2. 任一步抛错 → 暂存改名 `.failed-<ts>/` 留现场，**正式目录一个都不创建**；
3. `latest.json` 只在全部成功后原子写一次；
4. 冻结快照哈希与已有副本不同 → 拒绝（`--force` 时旧副本归档 `.superseded-<ts>`）。

**这条已经满足 M3 要求，不需要改。**

### 1.5 回滚（这是目前的真缺口）

现状（`runbook-same-day.md` §5）是**手工**：`mv` 目录改名 + 手改 `latest.json`。
手工改指针的危险在于——改错了没人知道，也没有记录。

设计（最小改动）：

1. `latest.json` 增加 `previous` 字段：每次成功发布时，把**上一个指针整体**存进 `previous`；
2. 新增 `--rollback` 模式：只做三件事——把当前目录归档为 `<name>.rejected-<ts>`、
   把 `previous` 提升为当前指针、往 `approvals.jsonl` 追加一条 `rollback` 记录；
3. 回滚**不改数据、不删目录**，只改「哪一版算当前」；
4. 回滚后 `status` 记为 `rolled_back`，该版本不得再被审批通过（需重新发布新版本）。

## 2. 异常清单（六类）

### 2.1 判据与数据源

全部落在**已经存在的字段/产物**上，不新造数据。

| # | 异常 | 判据（可复算） | 数据源 | 严重度 | 责任角色 |
|---|---|---|---|---|---|
| E1 | **快照陈旧** | `as_of − max(snapshot_date) > 1 天` → blocking；`> 12 小时` → warning。`snapshot_at` 与 `snapshot_date` 都记（前者是时刻，后者是日） | `pipeline-manifest-*.json` 的 `snapshot` / `as_of` | blocking | data |
| E2 | **ETA 过期** | W1 在途行有可解析 ETA 且 `ETA < as_of`，阶段仍未到仓 | `w1_supply_facts_v2/supply_facts_raw.jsonl` → `so-eta-chase-2026-10-28/eta_chase_list.csv` | warning | 物流/头程 |
| E3 | **PO 无 ETA** | 通途 PO 行 `expected_arrival` 为空或不可解析 | `tongtool_po/purchase_orders_recent.jsonl`（`--po-tongtool`） | warning | 采购 |
| E4 | **SO 不守恒** | 单张开放 SO：`Σ in_house 阶段 ≠ SO 总量`，**且逐行封顶后仍有未解释余差 > 0** | `so-conservation-fix-2026-10-28-v2/so_conservation_fix.csv` | blocking | 净额负责人 |
| E5 | **单位未证** | `canonical_uom ∈ {<unknown>, unknown, ""}` | `demand_netting.parquet` / `item_uom_cache.parquet` → `uom_audit.csv` | blocking | 主数据/运营 |
| E6 | **占位 SKU** | `warehouse_aliases.json → placeholder_skus`：`explicit` 命中 / `patterns` 命中 / `available ≥ 100000` | `self_fulfilled_demand/warehouse_aliases.json` → `placeholder_excluded` 证据行 | warning | 仓库/主数据 |

**已有真实基线的四类**（E2 / E4 / E5 / E6；E1 每版现算，E3 待 Step 1 统计）：

- E4：97 张开放 SO 重审后 **55 守恒、30 由逐行封顶解释、未解释余差 0**
  （另有 10 单 FBA 外部、2 单 FBA 混入已隔离）；
  历史四类去向「超发 3,755 / 重复 0 / 退货待核 0 / 异常占位 3,755」，超产 3,020、FBA 14,277 单列。
  → **已解释的差额不算异常**，只有未解释余差才是 blocking；
- E2：催证清单 `so-eta-chase-2026-10-28/eta_chase_summary.json` —— 共 **221 行**（P1 143），
  其中**有 Shipment 但无 ETA 44 行**、**完全无 Shipment 177 行**；在取到运单状态与 ETA 前不抵任何缺口；
- E3：通途 PO 的 `expected_arrival` 缺失行数**尚未统计**（Step 1 要先跑一遍才知道），不预设数字；
- E5：`item_uom_cache` 1,627 行；`PP10LB` 是当前已知的 `unknown` 单位实例；
- E6：`Buttonkit-pl` 曾达 **9,999,866**，是阈值 100,000 的由来。

> 口径提醒：`so_conditional_supply_v3` 记录的「在途 48,978 无 ETA 只列不抵」是**条件供给层**的
> 合计口径，与 E2 的**催证行数**（221）不是同一把尺子，两者不可互换引用。

### 2.2 六类为什么不能一视同仁

| 类型 | 为什么这个严重度 |
|---|---|
| E1 快照陈旧 | 快照是**全链路基准**；陈旧 1 天以上，后面所有数量都建立过期库存上 → 必须阻断出包 |
| E4 SO 不守恒 / E5 单位未证 | 会让「缺口」算错（要么少算供应，要么把不同单位相加）→ 阻断 |
| E2 ETA 过期 / E3 PO 无 ETA | 只让**未来到货**变得不确定；现有做法是「只列不抵」，数量本身不会因此虚高 → 提示，进催证队列 |
| E6 占位 SKU | 已被排除并留证；异常单的作用是**确认没有漏网的**（阈值/清单是否需要更新）→ 提示 |

### 2.3 闸门（本次设计的核心）

```
blocking_count > 0  →  决策包 partial=true，版本 status 不得为 approved
```

- 例外通道：某条 blocking 项经审批记为 `accepted_risk`（记 approver + 理由 + 影响范围）后，
  可放行，但该版本 manifest 必须带 `accepted_risks[]` 明细，**不得静默放行**；
- warning 不影响出包，但必须出现在交付物第一页，且计数写进版本记录。

### 2.4 异常清单产物

`exceptions-<date>-<label>.csv`（长表，一异常一行）：

| 字段 | 说明 |
|---|---|
| `exception_id` | 稳定 id，便于跨版本跟踪同一异常 |
| `exception_type` | `snapshot_stale` / `eta_expired` / `po_missing_eta` / `so_not_conserved` / `uom_unproven` / `placeholder_sku` |
| `severity` | `blocking` / `warning` |
| `entity_key` | 四列键或 SO 号 / PO 号 / 仓库，按类型而定 |
| `observed_value` / `threshold` | 实际值与阈值，便于复算 |
| `evidence_path` | 指向具体产物文件（不给「见系统」这种无法核对的指路） |
| `owner_role` | 上表责任角色 |
| `sla_hours` | 见 2.5 |
| `first_seen_at` / `status` | `open` / `ack` / `fixed` / `accepted_risk` |
| `disposition_note` | 处置说明；`accepted_risk` 必须写理由与批准人 |

`exceptions-<date>-<label>.json`：六类计数、`blocking_count`、`gate_result`（`pass` / `block`）。

### 2.5 责任与 SLA（建议值，需业务确认）

| 类型 | SLA | 闭环方式 |
|---|---|---|
| E1 快照陈旧 | 当天 | 补新快照后重跑（`label+1`） |
| E2 ETA 过期 | 2 个工作日 | `eta_chase_list.csv` 派工；回填后进下一版 |
| E3 PO 无 ETA | 2 个工作日 | 采购补 `expected_arrival` |
| E4 SO 不守恒 | 当天 | 逐行核对；确认属超发/占位的转隔离，不抵扣 |
| E5 单位未证 | 3 个工作日 | 主数据补 `stock_uom`，更新 `item_uom_cache` |
| E6 占位 SKU | 1 周 | 复核 `placeholder_skus` 清单/阈值，必要时加显式项 |

## 3. 版本 / 审批记录

### 3.1 版本记录（每版一份，落进 `pipeline-manifest-<date>-<label>.json` 的 `version` 块）

| 字段 | 例 | 现在有没有 |
|---|---|---|
| `version_id` | `2026-10-29-r2` | ❌ 新增（等价于 `<date>-<label>`） |
| `snapshot_date` / `as_of` | `2026-10-29` / `2026-10-29T…` | ✅ 已有 |
| `code_commit` / `git_dirty` | `89b1ed95` / `false` | ✅ 决策包 manifest 已有 |
| `input_hashes` | stock/demand/sku_map/uom_cache/forecast(+manifest sha256) | ✅ 分散在各步 detail |
| `output_hashes` | 每个产物的 sha256 | ✅ 已有 |
| `supersedes` / `superseded_by` | `2026-10-29-r1` / — | ⚠️ `--supersedes` 只进决策包，未回写到旧版 |
| `exceptions` | `{blocking: 2, warning: 11, path: exceptions-…csv}` | ❌ 新增 |
| `status` | `draft` → `in_review` → `approved` / `rejected` / `superseded` / `rolled_back` | ❌ 新增 |
| `approved_by` / `approved_at` / `approval_scope` | 见 3.2 | ❌ 新增 |

> **关键**：`superseded_by` 必须**回写旧版**。现在只有新版记 `supersedes`，
> 顺着旧版目录查不到「它被谁取代了」——回滚时这是必需信息。

### 3.2 审批记录（append-only `approvals.jsonl`）

一行一次决定，**只追加，不修改、不删除**：

```json
{"approval_id":"apr-20261029-0001","version_id":"2026-10-29-r2","decision":"approved-with-conditions",
 "approver":"<姓名>","role":"补货审核人","decided_at":"2026-10-29T09:12:00+08:00",
 "scope":{"keys":91,"warehouses":["美东-CENTRADE","美中-FZH-DANEEY"],"uom":["个"]},
 "conditions":["缺 ETA 的 19 个键不下单，只催证"],
 "accepted_risks":[],"sample_size":12,"how_verified":"逐键抽查 12 条，ERP 库存与净额一致",
 "evidence_link":"exceptions-2026-10-29-r2.csv"}
```

### 3.3 状态机与三条不变式

```
draft ──> in_review ──> approved
                 └────> rejected ──(返修)──> draft(新版本)
approved ──> superseded      （新版本发布）
approved ──> rolled_back     （发现问题回滚）
```

1. **没有 `approvals.jsonl` 记录的版本，不得进入「可下单」状态**——`approved` 只能由审批记录驱动，
   不能由脚本自己写；
2. `exceptions.blocking_count > 0` 的版本 **不得** `approved`（除非有 `accepted_risk` 且记批准人）；
3. 版本一旦 `approved` 即**冻结**（目录只读）；改数据必须出新版本、走新审批——
   **不得在已批准版本上原地改数字**。

## 4. 与现有文档的关系

| 现有 | M3 的处理 |
|---|---|
| `docs/runbook-same-day.md` §2–§4（一条命令、校验、命名） | 保留，继续作为操作手册 |
| `runbook-same-day.md` §5 手工回滚 | **被 1.5 取代**（改指针要留痕） |
| `runbook-same-day.md` §8 检查清单 | 保留，增加「异常清单 `blocking=0`」一项 |
| `decision-pack-2026-10-29-r2.md`（去向/情境/缺口） | 不动；M3 不改任何数量口径 |
| `UOM-CANONICAL` / `evidence_queue` / `eta_chase` | 作为 E2/E5 的既有数据源，不重写 |

## 5. 最小落地步骤与验收（本次不执行）

按依赖顺序，每步都可独立验收、可单独撤回。

### Step 1 — 异常清单生成器（只读，最高优先级）

- 新增 `supply_netting/scripts/exceptions.py`：读现有产物 → `exceptions-<date>-<label>.{csv,json}`；
- **不读生产、不写净额**，只做汇总与判据；
- 验收：
  - 六类各能出数（可以是 0 行，但必须有显式 `count=0`，不能缺类）；
  - E4 对账：本轮 97 单必须复现「55 守恒 / 30 逐行解释 / 未解释余差 0」；
  - E6 能把 `Buttonkit-pl` 这类命中项列出来；
  - 同一输入跑两次，输出逐字节一致（无时间戳漂移，或时间戳只在固定字段）。

### Step 2 — 版本块接进 manifest

- 改 `run_same_day.py`：成功时往 `pipeline-manifest` 写 `version` 块（3.1 字段）；
- 验收：一次 `--dry-run` + 一次完整跑；新字段齐全、**旧字段一个不少**；
  `superseded_by` 能回写到上一版 manifest。

### Step 3 — 回滚命令化

- `latest.json` 加 `previous`；新增 `--rollback` 模式；
- 验收：
  - 模拟失败（不存在的 `--forecast-run-id`）→ `latest.json` 不动、无正式目录（已有行为，回归验证）；
  - `--rollback` 后指针指向上一版、目录改名为 `.rejected-*` 而非删除、`approvals.jsonl` 多一条 `rollback`。

### Step 4 — 审批记录 + 只读校验器

- 新增 `approvals.jsonl` 与 `scripts/check_version.py`（只读：按 3.3 三条不变式判定某版本能否下单）；
- 验收：
  - 无审批记录的版本 → `not_orderable`；
  - `blocking_count>0` 且无 `accepted_risk` → `approve` 被拒；
  - 已 `approved` 版本目录被改动 → 校验器报 `tampered`。

### Step 5 — 调度（**本步需要用户另行批准，本次不部署**）

- 用系统计划任务/cron 只调 `run_same_day`，不调任何写库脚本；
- **周节拍（何时冻结、谁批准、演示什么）见**
  `C:/Users/zhang/.agent-ops/fzh-data/weekly-cadence-2026-10-28/`（周一 betting table /
  周四冻结 / 周五演示模板）；调度只负责定时跑，节奏与审批由那份模板管；
- 验收：连续 3 天自动跑，`latest.json` 只在成功时前进；任一失败日不产生正式目录。

### 验收总表

| 验收项 | 判据 | 怎么验 |
|---|---|---|
| 失败不覆盖 | 失败后 `latest.json` 与正式目录均未变 | 用不存在的预测版本复跑，比对 `latest.json` 哈希 |
| 可回滚 | 指针回退且目录留证不删 | `--rollback` 后看 `previous`、`.rejected-*`、`approvals.jsonl` |
| 六类异常可出数 | 每类有 `count`（含 0） | `exceptions-*.json` 六个键齐全 |
| 闸门生效 | `blocking>0` → 不能 approved | 构造 1 条 blocking，跑 `check_version.py` |
| 版本可追溯 | 每版能找到输入哈希 + 代码 commit | 任意两版 `pipeline-manifest` 对读 |
| 审批留痕 | 每次决定一行，只追加 | `approvals.jsonl` 行数单调不减 |

## 6. 明确不做

- 不部署 cron / 计划任务 / 监控面板（Step 5 需另行批准）；
- 不自动下单、不自动改数量、不自动修数据（异常只登记与派工）；
- 不做告警推送渠道（钉钉等）——先让清单存在且可信，再接渠道；
- 不重写 `run_same_day` 的失败语义（已正确）；
- 不改任何数量口径、情景或政策。

## 7. 风险与已知限制

1. **快照日期是日粒度**：`snapshot_date` 只能判断「隔了几天」，判断不了「今天的快照是否比昨天新」。
   需要更细的陈旧判断，只能靠 `snapshot_at`（且其时区靠 `--tz` 解释，是已知事实）。
2. **E2/E3 的存量不小**（催证清单 221 行，其中无 Shipment 177 行）：清单上线第一天就会有大量
   warning。这不是回归，是**把一直存在的缺口第一次显式列出来**；需在交付物首页说明，避免被当成新故障。
   E3（PO 无 ETA）的行数在 Step 1 跑过才知道，这里不预设。
3. **审批人字段依赖人工填写**：设计上不校验姓名真实性，只保证「谁在什么时候批了什么范围」有记录。
4. **SLA 是建议值**：2.5 的数字需要业务确认后才能当承诺。**2026-10-28 已改为内部 SLO（见 §8），仍不是对外承诺。**

## 8. SLA：采用内部 SLO（2026-10-28 决定）

**需要，但只作为内部数据/审核节奏，不对客户或老板承诺响应时间。** 参考 DORA/AgentOps 的分层节拍：数据新鲜度用 SLO，异常处理用工作目标，审核用 WIP + 首次响应。

| 项 | 内部目标 | 超过后 | 责任 |
|---|---|---|---|
| 快照新鲜度（E1） | `as_of − snapshot_at ≤ 26 小时` | **阻断**发布；通知数据负责人 | 数据 |
| 每日发布 | 快照到达后 **4 小时内**（通常 10:00 前） | 标 `delayed`，不更新 `latest.json` | 工头 |
| ETA 过期（E2） | **2 个工作日**内问物流并登记 | 升级到周会 | 物流/头程 |
| PO 无 ETA（E3） | **3 个工作日**内采购补日期 | 升级到周会 | 采购 |
| 单位未证（E5） | **3 个工作日**内主数据补 | 阻断相关键，不阻断全包 | 主数据/运营 |
| 审核首次响应 | **1 个工作日**内 | 待审队列 >2 暂停派新实现 | 审核人 |
| 回滚 | **1 个工作日**内完成并留 `approvals.jsonl` | 标 `rolled_back`，禁止再批 | 工头 |

**不做**：不设 7×24、不设客户赔付、不设自动告警渠道（先队列，后接钉钉）；SLO 连续 2 周达不到才升级为流程问题，不因单日波动改口径。

