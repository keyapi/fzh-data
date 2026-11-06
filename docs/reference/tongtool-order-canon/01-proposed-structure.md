---
okf: v0.1
type: Reference
title: 通途订单规则库 · 建议形态与迁移方案
description: 在审计基础上给出唯一事实源的存储形态（单文件 / 多文件 bundle / skill+脚本）取舍、目录结构、权威分层、与现有 cost-engine-spec/AGENTS/SKILL 的合并废弃关系、分阶段迁移步骤与验收标准
date: 2026-11-06
module: tongtool_order_cost
tags: [tongtool, order, canon, knowledge-base, structure, migration]
---

# 通途订单规则库 · 建议形态

> 配套审计：[00-audit-report.md](00-audit-report.md)。
> 本文只提方案，不改业务代码、不写 GS/EN、不提交 PR。

## 1. 结论先行

**推荐：多文件 OKF bundle + 一份机器可读 `rules.yaml` + skill 仅做指针。**

不是单文件，也不是「skill 当事实源」。

| 方案 | 结论 | 理由 |
|---|---|---|
| 单文件 `TONGTOOL-ORDER.md` | ❌ 不采用 | 规则横跨「订单身份 / 分组合并 / 计价矩阵 / 数据源 / 实现落点 / 决策史」六类，单文件会变成 3000 行、无法按需加载；且行号会漂移，单文件里混实现细节必然过期 |
| 多文件 bundle（推荐） | ✅ 采用 | 规范页稳定、实现映射页可单独重生成、证据页 append-only；可按任务只读 1–2 页 |
| skill + 脚本当事实源 | ❌ 不采用 | skill 的职责是**触发与路由**，不是规范；脚本是实现，改了代码就改了口径，无法表达「业务上应该怎样」 |

**一句话：规范与实现分离，证据与决策分离，skill 只指路。**

## 2. 为什么现有 `cost-engine-spec` 不够

它已经自称「成本口径的单一事实源」（`tongtool_order_cost/docs/reference/cost-engine-spec/01-overview-and-glossary.md:13`），但审计发现四个结构性问题：

1. **规范与证据混在一起**：38 个文件、约 6,600 行，既有「规则应该怎样」，也有「某次实测多少行」、Codex 复核更正、评审任务书。读者无法判断哪句仍然有效。
2. **行号被当成稳定键**：文档写「自采购 `bom_cost_list_v2.py:1496-1530`」，线上实际在 `:1725-1734`（本次 SSH 复核）。行号漂移后，文档看起来仍很精确，实际已误导。
3. **同一主题多页并存且口径不同**：`08-special-cases.md`、`38-en-line-identity-and-single-item-suffix.md`、`en-shaoxing-shipment-cost-logic-spec.md` 都在讲后缀/绍兴成本，读者要自己合并。
4. **没有「订单身份 / 分组合并」这一层**：`30` 是设计稿、`38` 是补丁说明，缺一页回答「什么算同一件成品、原始订单在哪、作废原单怎么处理」。

所以不是再写一篇更长的文档，而是**换一种组织方式**。

## 3. 建议目录结构

```
docs/reference/tongtool-order-canon/
├── index.md                         # 入口 + 阅读路径 + 权威声明
├── log.md                           # 变更日志（append-only）
├── 00-scope-and-conventions.md      # 范围/非目标/术语/时点/证据等级
├── 01-order-universe.md             # 原始订单、作废原单、拆分子单、FBA、退货、补发
├── 02-grouping-and-merge.md         # order_common、拆单组、合并成一件、件数、产品归属
├── 03-price-matrix.md               # 后缀 × 发货方式 × 目的地 × FBA 的计价矩阵
├── 04-cost-sources.md               # 皮壳/头程/目的地加工/绍兴侧/自采购/套件
├── 05-special-flows.md              # 尾程、有效重量、非商品配件、白名单、别名登记
├── 06-implementation-map.md         # EN / 本地引擎 / Colab / GS 的落点表（含 commit 与观测日）
├── 07-conflicts-and-decisions.md    # 活冲突登记 + 每条的状态/owner/决议
├── rules.yaml                       # 机器可读规则条目（测试与审计脚本消费）
└── adr/
    ├── 0001-shaoxing-cost-two-definitions.md
    ├── 0002-split-package-factor-scope.md
    └── ...
```

### 3.1 各页职责（只写该页该写的）

| 文件 | 回答什么 | 不写什么 |
|---|---|---|
| `01-order-universe` | 哪些行进入计算；`invalid=1` 怎么用；`_1/_2` 子单怎么认；FBA/退货/补发算不算 | 具体成本公式 |
| `02-grouping-and-merge` | 什么条件下合并；件数取谁；共享皮壳/填充物谁定产品；歧义怎么阻断 | 各成本列取值 |
| `03-price-matrix` | 给定「行形态 + 发货方式 + 目的地 + 是否 FBA」，四列各取什么 | 数据源表名/行号 |
| `04-cost-sources` | 皮壳/头程/加工/绍兴/自采购/套件的**取值链**与优先级 | 订单分组 |
| `05-special-flows` | 尾程、重量、非商品、白名单、别名等旁路 | 主计价矩阵 |
| `06-implementation-map` | 每条规则在 EN/本地/Colab/GS 的**当前落点** | 规范本身 |
| `07-conflicts` | 已知不一致、未证实项、待拍板 | 已定口径（那在 01–05） |

### 3.2 `rules.yaml` 条目格式

```yaml
- id: PRICE-COVER-001
  title: 单独卖 -COVER 的计价
  scope: [non_fba, single_item]
  applies_when:
    order_has_sibling_filler: false
    sku_suffix: "-COVER"
    shipping_method_in: [皮壳, 半成品, 成品]
  then:
    shell_cost: "cost_fg"
    sx_processing: 0
    destination_processing: 0
    head_freight: "cover_freight"
  exceptions: [FBA 绕过]
  evidence:
    - "EN order_sync.py:2947-2953 (2026-11-06 观测)"
    - "EN tongtool_cost_review.py:1068-1087"
    - "本地 bom_cost.py:441-454"
  status: canon
  effective_from: 2026-11
  owner: finance
```

字段固定：`id / title / scope / applies_when / then / exceptions / evidence / status / owner / effective_from`。
`status` 只允许 `canon | decision-needed | deprecated | unverified`。

## 4. 权威分层（冲突时按这个顺序判）

| 层 | 内容 | 权威性 |
|---|---|---|
| **L0 规范** | `01`–`05` 的规则正文 | 业务口径的唯一事实源 |
| **L1 决策记录** | `adr/`、`07` 的决议行 | 解释「为什么改成这样」；可覆盖 L0 的旧版本 |
| **L2 实现映射** | `06-implementation-map.md` | 只描述现状，不定义应然；代码改了要同步 |
| **L3 证据** | `cost-engine-spec/`、`docs/solutions/`、审计报告、PR | append-only 的历史证据，**不再作为规范** |
| **L4 可执行** | `rules.yaml` + `tests/` | 规范的可执行副本；测试失败 = 规范或实现有一方错了 |

判定顺序：

1. 代码与 L0 不一致 → 先问「代码 bug 还是规范过期」，写进 `07`，**不允许两边都算对**。
2. L2 行号与代码不一致 → 只更新 L2，不动 L0。
3. 证据与规范冲突 → 规范优先；若证据足以推翻规范，开 ADR 改 L0。

## 5. 与现有资产的关系

| 现有资产 | 处置 | 说明 |
|---|---|---|
| `cost-engine-spec/01-overview-and-glossary.md` | **拆分**：系统上下文/术语 → `00`；其余 → 各页 | 「单一事实源」声明改指向本 bundle |
| `cost-engine-spec/02-keys-and-entities.md` | **保留为证据页**，实体速查并入 `00` | 键的坑属于 `05`/`07` |
| `cost-engine-spec/03-data-sources.md` | **保留为证据页** | 表清单仍有用，但不再定义口径 |
| `cost-engine-spec/04-cost-decision-tables.md` | **合并**进 `03` + `04` | 规范正文迁走，原页标「证据/历史」 |
| `cost-engine-spec/08-special-cases.md` | **合并**进 `03` + `05` | 同上 |
| `cost-engine-spec/30-design-merge-split-no-double-count.md` | **合并**进 `02`；原文保留为设计证据 | 设计稿里的「待拍板」迁 `07` |
| `cost-engine-spec/32`–`37` | **保留为实现/测试证据** | Phase 2–4 的口径细节由 `06` 引用，不复制 |
| `cost-engine-spec/38` | **合并**进 `02` + `03` | 行级身份/后缀矩阵的规范正文迁走 |
| `cost-engine-spec/07-colab-vs-en.md` | **保留**为迁移进度页（非规范） | 进度会过期，不能进 L0 |
| `cost-engine-spec/09-known-issues-register.md` | **升级**为 `07` | 从「登记册」改为「有 owner/状态的活清单」 |
| `cost-engine-spec/colab-engine-cell-by-cell.md` | **保留为证据页** | 逐 cell 逆向是取证材料，不是规范 |
| `en-shaoxing-shipment-cost-logic-spec.md` 等专项 | **保留为证据页** | `06` 引用其行号与结论 |
| `AGENT_HANDOFF.md` | **保留**为交接入口；规则段落改为**指针** | 避免第二份规范 |
| `README.md` | **保留**为使用说明 | 不写口径 |
| `.agents/skills/tongtool-order-cost/SKILL.md` | **保留触发/命令/纪律**，加一行「口径先读 canon」 | skill 不复制规则 |
| `CONCEPTS.md` | **只保留术语定义**，规则指向 canon | 避免术语页变成规范页 |
| `docs/solutions/*` | **保留 learning**，不复制到 canon | 经验库是「怎么踩过坑」，canon 是「现在该怎样」 |
| `AGENTS.md` | **只加一行路由**，不加内容 | 见 §6.5 |

## 6. 迁移步骤（分阶段、可回退）

### Phase 0 — 冻结与盘点（本次已完成）
- 产出 `00-audit-report.md`。
- **退出条件**：源清单、冲突清单、缺口清单齐全，所有断言有证据。

### Phase 1 — 抽取规范条目（不写散文）
- 把 `01`–`05` 要回答的问题逐条写成 `rules.yaml` 条目；每条先只填 `applies_when / then / evidence`。
- 对每条标 `status`：`canon` / `decision-needed` / `unverified`。
- **退出条件**：现有文档中每个「确定的规则」都有 id；重复条目合并。

### Phase 2 — 冲突裁决（需业务/财务）
- 按 `00` 的冲突清单逐条裁决，产出 `adr/000N-*.md`。
- 只裁决「口径归属」，不顺手改代码。
- **退出条件**：`decision-needed` 清零，或每条都有 owner + 截止日。

### Phase 3 — 写规范正文
- 由 `rules.yaml` 生成/手写 `01`–`05`；每条规则附 id，正文不重复证据行号。
- **退出条件**：五个问题能在 5 分钟内从 canon 找到答案（见 §8）。

### Phase 4 — 实现映射与测试
- `06` 用「规则 id → EN/local/Colab/GS 落点」表；落点带**观测日 + commit**，不承诺行号永久有效。
- 把 `rules.yaml` 的关键条目接进现有测试（`tests/test_tongtu_cost_engine_phase2.py` 等），失败即规范/实现不一致。
- **退出条件**：每条 `canon` 规则至少有一个可执行断言或明确的「无自动断言」理由。

### Phase 5 — 重定向与降级旧页
- 在 `cost-engine-spec/01`、`04`、`08`、`30`、`38` 顶部加一行：「规范已迁至 `docs/reference/tongtool-order-canon/`，本页保留为证据」。
- `AGENTS.md` 模块索引加一行；`SKILL.md` 加一行指针。
- **退出条件**：不再有第二处声称「我是唯一事实源」。

### Phase 6 — 防漂移
- CI/脚本检查：`rules.yaml` schema、每个 id 有 evidence、`06` 的落点文件存在（不校验行号）、断链检查。
- 每次口径变更必须：改 `rules.yaml` + 加 `adr/` + 更新 `log.md`。
- **退出条件**：`uv run python scripts/check_solutions_health.py` 同类体检可覆盖本 bundle（或新增等价脚本）。

## 7. 不建议做的事

1. **不要把 `rules.yaml` 做成第二套代码**：它只描述判定与取值，不实现计算。
2. **不要把行号写进 L0**：行号只出现在 `06` 和证据页。
3. **不要在 skill 里写规范**：skill 只保留触发词、命令、纪律、指针。
4. **不要一次性重写 38 页**：先迁规范，旧页降级为证据，避免大爆炸式改动。
5. **不要用「文档说 A、代码是 B」各打五十大板**：每条冲突必须落到「改代码」或「改规范」二选一。

## 8. 验收标准（可测）

- **Q1** 一笔订单被拆成 Cover + Foam 两行，怎么计价？→ `02` + `03` 两跳内回答。
- **Q2** 单独卖 PPCotton 且发货方式是成品，四列各是多少？→ `03` 矩阵直接查。
- **Q3** 作废原单 `invalid=1` 在写回表里保留还是删除？→ `01` 直接回答。
- **Q4** 同一 SKU 在 EN 订单同步、Cost Review、交付单三条链路成本不同，以谁为准？→ `06` + `07` 给出裁决状态。
- **Q5** 某条规则什么时候改的、谁定的？→ `adr/` + `log.md`。

另外：
- `07` 中 `decision-needed` 条目全部有 owner；
- `rules.yaml` 中 `canon` 条目 100% 有 evidence；
- 新人按 `index.md` 的阅读路径 30 分钟内能答对 Q1–Q3。
