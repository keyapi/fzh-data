---
okf: v0.1
type: Reference
title: 美中 USTX 成本三方案离线对比——口径不对称、「差异即结论」与歧义键 fail-closed
description: 把「美中仓库由绍兴二次加工(2CJG-SX)改走当地USTX加工」做成 A/B1/B2 三口径只读对比时，怎么先验证据再定等价闸门、怎么处理人工测算表与歧义维表键、闸门怎么分级
date: 2026-10-14
category: architecture-patterns
module: tongtool_order_cost
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - "要做跨系统/跨口径的成本对比（Colab/GSheet vs EN/Tongtool Cost Review）"
  - "某张表看起来像公式源，其实里面是人工手填的估算值"
  - "维表同一业务键对应多行、取值不同（歧义键）"
  - "想给对比结论加一条『两侧必须相等』的阻断闸门"
tags: [cost, ustx, comparison, gsheet, erpnext, audit, fail-closed]
---

# 美中 USTX 成本三方案离线对比

## Context

美中仓库（`发货仓按销售汇总分类=USTX分公司`）在 Colab 成本引擎里走 `2CJG-SX`，
「二次加工成本」这一列记的是**绍兴加工费**（如 17–50），与美东 `2CJG-US`、波兰 `2CJG-PL` 各走各的当地加工不同。
业务要评估「美中改走当地 USTX 二次加工」后，皮壳 / 头程 / 二次加工 / 绍兴二次加工**四项成本**会怎么变。

已在 `二次加工成本2022` 工作簿里建了两张**测算表**（`测算 美东USNJ二次加工成本`、`测算 美中USTX二次加工成本`），
**已建、未启用**。需求是以 7 月订单逐行对比「现状 A」与「改造后 B」并归因到 仓库 × 品类 × 绍兴发货方式。

本次落地：`tongtool_order_cost/ustx_cost_compare.py` + CLI `ustx-compare`（纯离线、不写任何表）。

## Guidance（本学习沉淀的做法）

### 1. 先验「这张表是不是公式源」，再决定要不要建等价闸门

计划里默认「测算表已有值 = 可由 import 表公式重建」，因此设了一条「measured vs reconstructed 超差即阻断」的闸门。
**实测证伪**：`测算 美中USTX二次加工成本` 的公式指向辅助表 `美中USTX成本测算`，
而那张表的 `8月…2月` 月度值和 `平均` 是**手填数字、没有任何公式**（人工报价均值）。
它与 import 表重建值在 **57 个共有键上无一相等**（差 2–3 倍很常见）。

→ 结论：**B1（人工测算）与 B2（import 重建）本质不同源，差异本身就是交付物**，
不能设「必须相等」的阻断闸门（那会让本次永远出不了金额结论）。
第一件事是**打开 A1 公式看单元格**（`colab_kit` / Drive `alt=media` 或 CLI `render_option="formulas"`），
确认是手填还是公式，再决定闸门语义。

### 2. 三口径要显式命名，且各自「改哪几项」写死

| 口径 | 定义 |
|---|---|
| A 现状 | 订单表四项现值（美中走 2CJG-SX） |
| B1 测算表 | 只把美中「二次加工成本」换成测算表最新月度列；缺行用 B2 公式补并标 `formula_filled`；再缺 `unmatched` |
| B2 EN 式 | 四项全按 import 表重建：皮壳=`importBOMCostList.皮壳成本` 按重量模板取 **max**（沿用 Colab 的 EN 聚合规则）；二次加工=`美中加工成本, USTX`；绍兴二次加工=按 `绍兴发货方式` 取 绍兴包装半成品/成品成本（半成品/成品）或 0（皮壳）；**头程 import 表无来源 → 保留 A** |

**join 链**：`品类尺寸面料编码` →（`import皮壳成本`.`EN重量模板物料号`）→（`importBOMCostList`.`重量模板, 编号`）。
`美中加工成本, USTX` 按重量模板**唯一**；`皮壳成本` 按重量模板**不唯一**（846 模板中 168 个有多个值），故取 max。

### 3. 歧义维表键 fail-closed：不进索引、排除对应行，不猜首/末行

`import皮壳成本` 里存在**同 `品类尺寸面料编码` 指向不同 `EN重量模板物料号`** 的冲突键（7 月 3 个）。
旧写法 `setdefault` 取首行 → 与其他口径不一致且**静默污染成本**。

正确做法：
- 冲突键**从索引里摘除**（`index.pop(key)`），记录到 `duplicate_keys` 证据表；
- 对应订单行按 `ambiguous_shell_key` 记入 `unmatched`，**不生成目录值**（不 fillna(0)、不取首/末行）。

### 4. 闸门分级：阻断级 vs 告警级

- **阻断级**（任一不过 → `conclusions_blocked=True`）：`writeback_row_conservation`（行数守恒）、
  `non_ustx_zero_delta`（非美中行差异必须严格为 0）、`b1_source_conservation`（来源数量闭合）、
  `b2_lineage_complete`、`component_identity`（四项 delta 之和 = 单价 delta）、`raw_coverage_conservation`。
- **告警级**（只记不阻断）：`no_ambiguous_dimension_keys`。3 个冲突键影响 3/4379 行 ≈ 0.07%，
  排除并显著标注即可，不该因这 0.07% 挡掉全月结论。
- `conclusions_blocked` 只能由 **blocking 闸门**的 fail 触发（首版误把告警也算进去，导致永远 blocked）。

### 5. 只读快照支持「值 / 公式」双冻结

同一 worksheet 要分别冻结**显示值**（算钱）与**公式文本**（验口径）。
`audit_sources.SourceSpec.render_option ∈ {values, formulas}`，gspread 侧走
`ws.get_all_values(value_render_option=ValueRenderOption.formula)`，manifest 逐源记 `render_option` + sha256。
默认 `values`，旧调用不受影响。

## Why This Matters

- **硬套「等价校验」= 结论永远出不来**：把两个不同来源的东西设成「必须相等」，闸门必然失败，
  你会误判成『数据有问题』而不是『它们本来就不该相等』。
- **猜歧义键 = 静默污染**：取首/末行不会报错，但会让成本账在几十行上悄悄错掉，事后极难发现。
- **口径不对称是代码证据，不是口误**：`FZH-DANEEY`/`大件云仓` 等映射到 `2CJG-SX`，
  是「美中之前没有加工成本数据、用绍兴拟合」的历史妥协（见 `colab-cost-engine-spec.md` §7）。

## When to Apply

- 做跨系统成本/口径对比（Colab/GSheet ↔ EN/Tongtool Cost Review）之前。
- 要把一张「看起来像公式源」的表（测算表、平均值表、人工维护表）当基准之前 —— **先看 A1 有没有公式**。
- 维表同一业务键出现多行时。

## Examples

7 月实证（美中 4,379 行，按 `发货数量` 加权，￥）：

| 分项 | A | B1 | B2 | B3 | ΔB2 | ΔB3 |
|---|---:|---:|---:|---:|---:|---:|
| 皮壳成本 | 231,530 | 231,530 | 231,530 | 231,530 | 0 | 0 |
| 头程运费 | 52,666 | 52,666 | 52,666 | 52,666 | 0 | 0 |
| 二次加工成本 | 242,029 | 468,658 | 468,011 | 394,552 | +225,982 | +152,522 |
| 绍兴二次加工成本 | 0 | 0 | 38,930 | 38,930 | +38,930 | +38,930 |
| **合计** | **526,225** | **752,854** | **791,137** | **717,678** | **+264,912** | **+191,453** |

分歧来源：① Colab 用绍兴二次加工，EN 用 `USTXBZCP#` 成品 BOM `total_cost`（大得多）；
② EN 按绍兴发货方式补了 绍兴包装半成品/成品成本，Colab 该列整列记 0；③ 皮壳/头程与现状一致（Δ=0）；
④ **B3**（工资率 167.8→105）只动 `operating_cost` → 二次加工降 73,459，合计收窄到 +191,453。

**第五条（新增）· 情景复算必须锚定「快照当时的对象」**：
给一个成本列做「只改一个变量」的假设测算时，绝不能拿**当前默认对象**去套快照值。
本例：sheet 是 2026-09-03 导出，该物料可有多张 BOM，此后部分物料新增 BOM 并改了默认
（`USTXBZCP#KS0455-92x56x75` sheet=206.479 对应 -001，现默认 -006=90.306）。
正确做法是**按值匹配**出 9/3 当时那张 BOM 再改变量；否则会把「其它变量」一起带进来。
另有 96 个物料**完全没有 BOM**，其值来自 `Item.valuation_rate` 回退 —— **不随工资率变**，Δ 必须记 0 而不是猜。

**未纳入 / 待变量**（写进结论时必带）：
- **头程口径（已核，Δ=0）**：B2 头程 = **EN BOM 成本列表**（`EN产品BOM成本列表20260202`，是
  `importBOMCostList` 的**超集**，前 25 列值完全一致）按 `绍兴发货方式` 取
  （半成品→`头程半成品运费, 美中USTX`、成品→`头程成品运费, 美中USTX`、皮壳→`头程皮壳运费, 美中USTX`，
  缺则皮壳兜底，键=重量模板）。
  **订单表 A 的头程本就等于这个值**（Colab 的 EN 覆盖层）→ **Δ=0**：用户设想的
  「半成品用半成品重量」**已经在 A 里生效**，不是缺口。
  唯一的头程口径分歧点是「按皮壳重量」勾选项（`测算 按皮壳重量 美国分公司USTX头程运费核算`），
  启用后头程再变 **−16,517**（7 月，￥加权）——已作为敏感度写入产出。
- **工资待调**：EN 美中USTX包装工站工资拟从 167.8 降到 105（会话时**尚未调整**），B2 二次加工成本可能偏高。
- **B1 覆盖有限**：美中用到 178 个键，测算表仅 59 键（measured），其余 1510 行靠 B2 公式补、49 行 unmatched。

## Related

- 月度盈利审计 CLI / 闸门 / 输出：[monthly-profitability-audit.md](../../../tongtool_order_cost/docs/reference/monthly-profitability-audit.md)
- Colab 成本引擎逆向规格（仓库→成本来源编码、美中口径不对称的代码证据）：[colab-cost-engine-spec.md](../../../tongtool_order_cost/docs/reference/colab-cost-engine-spec.md)
- EN 直接采购件自套 BOM（成本码为空时的缺口）：[en-direct-purchase-self-bom.md](en-direct-purchase-self-bom.md)
