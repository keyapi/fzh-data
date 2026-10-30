---
okf: v0.1
type: Reference
title: 供应链补货 A/B/C 数据管线：活跃宇宙→市场归属→库存归并→决策基座
date: 2026-10-30
category: architecture-patterns
module: supply_chain
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "要做 SKU×仓库×发货形态×单位的补货/供给分析"
  - "需要把 EN 活跃物料、市场归属、通途库存拼成可审计的决策输入"
  - "遇到共享码、套件、拆包成品、CG 仓、波兰/美国双市场"
tags: [supply-chain, sku, warehouse, inventory, attribution, join, audit]
---

# 供应链补货 A/B/C 数据管线

## Context

补货问题不是「一个 SKU 一个仓库」的加减法。实际链路被拆成四个 artifact：

- **A 活跃宇宙**：回答「哪些 EN 物料还值得看」；
- **B 市场归属**：回答「这个产品属于波兰/美东USNJ/美中USTX 哪个市场，美国谁负责」；
- **C 库存归并**：回答「截至某快照，哪些物理库存、在什么仓/形态/单位下，可以作为哪个产品的供给证据」；
- **join 决策基座**：把 C 的供给、B 的市场、D 的需求合成一行一决策。

四者必须分别验收，不能用一张大表混过去。任何一层把「缺失」写成「0」、把「共享」写成「单一归属」、把「历史」写成「当前」，下游都会放大成错误采购。

## Guidance

### A：活跃宇宙只做「是否值得看」

- 母集是 EN 物料 + 通途 SKU + 库存的并集；活跃判定用 2025/2026 销售、2026 通途订单、库存，不要求有美国销量。
- 角色与实物形态分列：`KS/PK#/ND#/HM/TJ#/ZT` 是角色，`actual_form` 另判；不能把角色当供货形态。
- 只有 **60cm 三角靠枕** 的 KS0248/KS0001 与 PK# 视为同物；153/194 等尺寸不合并。`-2PCS/-3PCS` 等后缀先做大小写/后缀归一，再判断。
- ND# 内胆只做配套，不建独立终端需求；共享 Foam/Cover 保留全部候选，不取第一个。
- 不允许用父件市场拼出多市场行；父件只可作为「已证同物/套件/60cm」的血缘证据。

### B：市场归属只做「市场与责任」

- 键是 `EN 产品 × 地区 × 供货形态 × 时间`；波兰与美东/美中可并存，美国同一时间只能有一个 owner。
- 证据级联固定：`own90 → own180 → own2026 → DN → own2025 → 库存仓`；每地区独立，不能拿另一地区的最近记录覆盖。
- 库存仓是**投放证据**（低置信），不是当前需求；波兰仓有货→波兰，美东USNJ 或美中USTX 单侧有货→该侧，两侧都有且无订单/DN 决胜→冲突卡。
- DN 双美国客户必须看**时间段/迁移日**，不能只数笔数；历史量保留，不冒充当前。
- 仓名只用 `美东USNJ` / `美中USTX`，禁止 `East/Central`（美东公司名是 CENTRADE，容易混）。
- CG 仓是履约渠道，不是第三个市场；`warehouse_id='CG'` 是 10 个分仓的汇总行，不得再加分仓；CG 只服务 Wayfair，按 B 的 owner 归 `CG-USNJ/CG-USTX`，无 owner 停留 `CG-unknown`。

### C：库存归并只做「供给事实」

- 六桶互斥穷尽：计入A、共享码、A未激活、规则排除、未映射、皮壳无活跃EN；源行数/数值和必须逐桶闭合。
- 仓池固定为 `美东USNJ/美中USTX/波兰/CG/其他`；不合成「美国」。
- 可发供给必须有适用事实、唯一身份、真实仓池、可解释单位、覆盖完整性；空集是 `null`，不是 0；缺行是 `uncovered`，不是 0。
- `join_class` 三态：`join_full`（可进净额）、`join_partial`（只观察/白名单）、`no_join`（隔离）；`null/未覆盖/共享/套件/CG·其他` 不进净额。
- 发货方式决定供给：皮壳=成品+皮壳；成品/半成品=成品；单一形态正常；成品可替代皮壳（用户 2026-10-30 确认）。
- 套件 TJ# 必须拆 EN Product Bundle：套件需求按套、组件供给按个，`set_qty × component_qty`；套件本身不作为库存。
- 拆包成品：成品可能以 Cover/Foam/基础码存储；成品可组装数 = 各必需组件按仓取 min；只有 Cover 且缺 Foam 时，Cover 仍可单独补，标 `component_partial_nonblocking`，不阻塞。
- 共享/身份按**库存源 SKU**判：源 SKU 唯一映射一个活跃 EN → 身份唯一；零库存的共享码不阻塞；只有共享池有正库存且实际进入该行才标共享。

### join：只消费已证子集

- 只消费 C 的 `join_full`；B 只提供市场/责任证据，`可进净额=否` 的行不得生成采购。
- 每个键带 `as_of`：B/C 物理库存、CG 快照、D 预测日期各不相同，不能当同一天。
- 同一需求只计一次；套件、拆包、共享池、CG 都要有 `demand_scope_id/shared_pool_id`，禁止重复相加。

## Why This Matters

- 一次「缺行=0」会把 191 行皮壳库存误判为缺货；一次「共享取首个」会把 333 行共享订单塞进单一产品；一次「美国合仓」会把美东 10 + 美中 40 算成 50 给任一仓。
- A/B/C 的经验是互相反哺的：A 的大小写/后缀规则救了 B 的旧 151；B 的市场证据救了 C 的 stock_placement；C 的 `join_full` 又限制 B 的数量消费。
- 分层验收让每个数字都能回到源行，出错时能定位到是 A 的角色、B 的市场还是 C 的仓池。

## When to Apply

- 新建任何「补货/供给/库存归属」分析；
- 修改 A/B/C 任一脚本或规则；
- 给业务/老板解释「为什么这个 SKU 补/不补」；
- 把本地结果落到 EN（`SKU Market Attribution` 版本表）之前。

## Examples

- **KS0248 153/194**：库存源 SKU 是 `CEN-No/B-...-153/194`（无扣），唯一对应 KS0248；共享的 `...-cover` 码库存为 0，因此分开处理、`join_full`，不与 KS0001 合并。
- **TJ#KS0156x2-001/x3-001**：EN Product Bundle 为 2×/3× `KS0156-NYBDSFH-52x52x5-BLACK`；CG 8 套/2 套 → 16/6 件，不能标 unknown。
- **KS0342-HLR-50-DEEPBLUE**：美中 Cover 41 + Foam 29 → 可组装 29 个成品；波兰 Cover 46、Foam 0 → 0。
- **CG 仓**：`Wayfair CG Stock Latest` 的 `warehouse_id='CG'` 行合计 417 个，10 个分仓明细只做对账，不再累加。

## Related

- `docs/solutions/best-practices/sku-normalization-uom-sets-split-package.md` — SKU 归一、套件、拆包、单位层级的具体规则
- `docs/solutions/workflow-issues/supply-chain-review-and-human-escalation.md` — 多 Agent 复审与人工升级边界
- `docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md` — EN 履约链路
- `docs/solutions/conventions/sellfox-cover-shared-inventory-transition.md` — 皮壳共享库存代理
