---
okf: v0.1
type: Reference
title: 国外3家分公司 工时系数(1/1/1.5)·PP棉用量·7-9月国外包装成品BOM缺口 只读调查
description: 财务 ZJ 需求的三问只读调查：①工时系数美东1/波兰1/美中1.5 的字段级落点（Manufacturing Settings.foreign_branch_time_multipliers → Foreign Branch Time Multiplier.time_multiplier）与生效逻辑（仅在 bom_batch_process.py 复制时乘算，自动 on_submit 路径不乘）②PP棉在 BOM 里的行/物料/用量与绍兴↔国外一致性③2026 年 7/8/9 月通途自发货订单的国外包装成品 BOM 缺口逐月行数、要因分布、能否用绍兴 BOM 填充
date: 2026-10-16
module: tongtool_order_cost
tags: [cost, bom, labor, ppcotton, overseas, ustx, usnj, pl, erpnext, reference, read-only]
---

# 国外 3 家分公司 工时系数 · PP棉用量 · 7-9 月国外包装成品 BOM 缺口

> 数据口径：ERPNext **生产库**（`erpnext.vilavi.cn`，SSH 别名 `阿里云-FZH-ERPNext-frappe`，bench 根 `/home/frappe/frappe-bench`），**全程只读**（只 `SELECT`；未 INSERT/UPDATE/DELETE，未 migrate / restart / build；临时 SQL 只经 stdin 传入）。订单侧：2026-07 本地冻结快照 + 2026-08/09 从 gsheet `通途订单202608`/`202609` 的「写回」表只读拉取（**未改 gsheet**）。
> 前作：[overseas-bom-labor-ppcotton-brief.md](overseas-bom-labor-ppcotton-brief.md)（本页要回答的交接书）、[en-ustx-bom-wage-rate-spec.md](en-ustx-bom-wage-rate-spec.md)、[en-ustx-no-bom-items-spec.md](en-ustx-no-bom-items-spec.md)、[en-pl-finished-processing-nonzero-spec.md](en-pl-finished-processing-nonzero-spec.md)、[en-shaoxing-ship-method-taxonomy-spec.md](en-shaoxing-ship-method-taxonomy-spec.md)。

## 结论摘要

1. **工时系数 1 / 1 / 1.5 的落点（字段级，已证实）**：存在 **Single DocType `Manufacturing Settings`** 的自定义 **Table 字段 `foreign_branch_time_multipliers`（标签「分公司工时系数」）**，指向子 DocType **`Foreign Branch Time Multiplier`**（`istable=1`）。库中三行：`PLBZCP=1.0`、`USNJBZCP=1.0`、`USTXBZCP=1.5`。生效点在 **`work_order_task/.../utils/bom_batch_process.py`**：`get_foreign_branch_time_multipliers()`（:25）读配置 → 复制时 `adjusted_time = original_time * time_multiplier`（**:242** 就地更新路径 / **:751** 新建 BOM 路径，写入 `BOM Operation.time_in_mins`）→ 入口 **:811/:883/:904**。**另一条复制路径 `work_order_task/.../utils/bom.py:copy_bom_with_new_item` 完全没有乘系数**（直接用 `time_in_mins`，见 `:261-280`）——即 `BOM.on_submit` 自动复制**不**放大工时。实证：`SXBZCP#KS0001-100` 与 USNJ/PL 的「包装」工序 `time_in_mins=10.584`，而 `USTXBZCP#KS0001-100` = **15.876 = 1.5 × 10.584**。
2. **PP棉用量（已证实）**：在 BOM 里就是唯一「`item_group='PP棉'`」的 `tabBOM Item` 行；国外成品 BOM **只有这一行**（3 家各 261 张 active+default BOM，**全部单行、全部是 PP棉**）。绍兴用 `PPM1500-7D51-SILICONIZED-NEW`（rate 10.00–11.00，254 张），三家国外统一换成 `PPM1500-15D64-SILICONIZED-NEW`（rate 10.80–15.00，783=261×3 张）。**用量 1:1 一致**：绍兴↔USTX / USNJ / PL 各 **251 对，逐对用量相同（0 例外）**。「借绍兴」= 复制时只保留绍兴 BOM 的 PP棉 行、换料、改按「分公司标准采购」价目表取价（`raw_material_cost` 即该行）。
3. **7-9 月缺口（自发货订单行）**：缺口行 PL 161/181/172、USNJ 74/117/129、USTX 396/442/289（月为 07/08/09）。**要因以「本就不需要国外加工 BOM」为主**：去重 446 条（月-分公司-包装件）里 **368 条（82%）绍兴发货方式=成品**（成品直采直发，按「成品→国外加工=0」规则**本无**国外 BOM）；**54 条=皮壳**（真需国外加工）；24 条不在 EN BOM 列表。
4. **能否用绍兴 BOM 填**：**绝大多数不能**。446 条缺口里，绍兴包装成品 BOM **含 PP棉（即可被自动复制闸门放行）的只有 25 条**（仅 `KS0018-SET7`、`KS0101-45` 两个家族）；**319 条有绍兴 BOM 但 PP棉 行=0**（现多为海绵版，闸门 `check_pp_cotton_in_bom_items` 会早退）；**102 条连绍兴包装成品 BOM 都没有**（其中 29 个 `SXBZCP#` 物料存在但**零张 BOM**、2 个物料**不存在**、1 个有 2 张但都非默认）。

## 一、工时系数 1 / 1 / 1.5

### 落点（字段级证据）

| 层级 | 对象 | 证据 |
|------|------|------|
| Single DocType | `Manufacturing Settings` | 字段行存在于 `tabSingles`（`doctype='Manufacturing Settings'`） |
| 自定义字段 | `foreign_branch_time_multipliers`，`fieldtype=Table`，`options=Foreign Branch Time Multiplier`，`label=分公司工时系数` | `tabCustom Field` 查询；fixture `work_order_task/.../fixtures/custom_field.json:2908-2932` |
| 子 DocType | `Foreign Branch Time Multiplier`（`istable=1`） | `.../doctype/foreign_branch_time_multiplier/foreign_branch_time_multiplier.json` |
| 子表字段 | `enabled`(Check/启用)、`branch_code`(Data/分公司代码)、`branch_name`(Data/分公司名称)、`time_multiplier`(Float/工时系数) | `tabDocField WHERE parent='Foreign Branch Time Multiplier'` |

**库中实际三行**（`SELECT ... FROM \`tabForeign Branch Time Multiplier\``）：

| parent | branch_code | branch_name | time_multiplier | enabled |
|---|---|---|---|---|
| Manufacturing Settings | **PL** | 波兰分公司 | **1.000000000** | 1 |
| Manufacturing Settings | **USNJ** | 美东分公司 | **1.000000000** | 1 |
| Manufacturing Settings | **USTX** | 美中分公司 | **1.500000000** | 1 |

→ 这就是财务口述的「美东=1、波兰=1、美中=1.5」。

### 生效逻辑（代码位置）

`work_order_task/work_order_task/work_order_task/utils/bom_batch_process.py`：

| 行 | 内容 |
|---|---|
| `:25-45` | `get_foreign_branch_time_multipliers()` —— `frappe.get_single("Manufacturing Settings")`，遍历 `foreign_branch_time_multipliers`，只取 `row.enabled` 的行 → `{branch_code: time_multiplier or 1.0}`；无配置时回退内置默认（全 1.0） |
| `:242` | **就地更新已有海外 BOM** 路径：`adjusted_time = original_time * time_multiplier` |
| `:751` | **新建海外 BOM** 路径：`adjusted_time = original_time * time_multiplier; op.time_in_mins = adjusted_time`，随后按调整后工时重算 `operation_labour` / `operation_manage_cost` / `op.operating_cost` |
| `:811` | 批量主流程取 `time_multipliers = get_foreign_branch_time_multipliers()` |
| `:883` | `time_multiplier = time_multipliers.get(short_code, 1.0)`（按目标分公司前缀取） |
| `:904` / `:940` | `copy_bom_with_new_item(..., time_multiplier=time_multiplier)` 透传 |

**关键：`\`utils/bom.py\` 的 `copy_bom_with_new_item`（`BOM.on_submit` 自动复制走这条）没有系数**，直接用 `time_in_mins`（`:261-280`）。因此**同一次改动，是否乘 1.5 取决于用了哪条复制路径**：

- 批量/表单按钮路径（`bom_batch_process.py`）→ 乘系数（USTX 得 1.5×）。
- `BOM.on_submit` 自动路径（`utils/bom.py`）→ 不乘。

### 实证（跨分公司同款对比）

```
SELECT b.item, bo.operation, bo.time_in_mins, bo.hour_rate_labour, bo.hour_rate
FROM `tabBOM` b JOIN `tabBOM Operation` bo ON bo.parent=b.name
WHERE b.docstatus=1 AND b.is_active=1 AND b.is_default=1
  AND b.item IN ('SXBZCP#KS0001-100','USTXBZCP#KS0001-100',
                 'USNJBZCP#KS0001-100','PLBZCP#KS0001-100');
```

| item | operation | time_in_mins | hour_rate_labour | hour_rate |
|---|---|---|---|---|
| SXBZCP#KS0001-100 | 包装 | 10.584 | 0 | 35.00 |
| USNJBZCP#KS0001-100 | 包装 | 10.584 | 618.00 | 667.62 |
| **USTXBZCP#KS0001-100** | 包装 | **15.876** | 167.80 | 202.04 |
| PLBZCP#KS0001-100 | 包装 | 10.584 | 420.04 | 605.03 |

`15.876 = 1.5 × 10.584` —— 美中工时确被放大 1.5 倍（前作 `en-ustx-bom-wage-rate-spec.md` 里 `hour_rate_labour=167.8` 即此工站；美东/波兰工资率不同，但**倍数**均为 1）。

> ⚠️ 遗留：`en-ustx-bom-wage-rate-spec.md` 已指出「2026-01-23 之后的 USTX BOM 比值为 1.00（走了不乘系数的自动路径）」，且 2025-10 那批 1.5× 无法归因于当时代码（当时 `bom_batch_process` 无系数）。本页只确认**当前代码与当前配置**的落点，不重述该时间线。

## 二、PP棉用量

### 是哪一行

`tabBOM Item` 中 `item_group='PP棉'` 的那一行。聚合（active+default BOM）：

```
SELECT CASE WHEN b.item LIKE 'SXBZCP#%' THEN 'SX'
            WHEN b.item LIKE 'USTXBZCP#%' THEN 'USTX'
            WHEN b.item LIKE 'USNJBZCP#%' THEN 'USNJ'
            WHEN b.item LIKE 'PLBZCP#%' THEN 'PL' END AS br,
       COUNT(DISTINCT b.name) n_bom,
       SUM(it.item_group='PP棉') n_pp_lines, COUNT(*) n_all_lines
FROM `tabBOM` b JOIN `tabBOM Item` bi ON bi.parent=b.name
     JOIN `tabItem` it ON it.name=bi.item_code
WHERE b.docstatus=1 AND b.is_active=1 AND b.is_default=1
  AND (b.item LIKE 'SXBZCP#%' OR b.item LIKE 'USTXBZCP#%'
       OR b.item LIKE 'USNJBZCP#%' OR b.item LIKE 'PLBZCP#%')
GROUP BY br;
```

| 分公司 | active+default BOM 张数 | 其中含 PP棉 行 | 总物料行 |
|---|---:|---:|---:|
| SX | 391 | 254 | 1515 |
| USTX | 261 | **261** | **261** |
| USNJ | 261 | **261** | **261** |
| PL | 261 | **261** | **261** |

→ **国外成品 BOM 是「单行 BOM」，那一行就是 PP棉**，`raw_material_cost` = 该行金额（无其它物料）。绍兴则是一张多行 BOM（含 PP棉 + 皮壳/纸箱等），254 张含 PP棉。

### 物料与价

| 侧 | PP棉物料 | rate 区间 |
|---|---|---|
| 绍兴 | `PPM1500-7D51-SILICONIZED-NEW` | 10.00 – 11.00（254 张） |
| 国外 3 家 | `PPM1500-15D64-SILICONIZED-NEW` | 10.80 – 15.00（783 张） |

换料规则写死在前作已述的 `utils/bom.py:197-198`（`-7D51-` → `-15D64-`），并按各分公司「标准采购」价目表取价（USTX=15.00 / USNJ=14.80 / PL=10.80）。

### 用量是否一致（借绍兴的核心）

按「同款」把绍兴 BOM 的 PP棉 用量与三家国外 BOM 的 PP棉 用量配对比较（BOM 名去前缀对齐）：

```
-- 见 out/_q_q2b.sql（USTX/USNJ/PL 三段 UNION ALL，按 PPM1500-15D64-SILICONIZED-NEW 配对）
```

| 配对 | 对数 | 用量相同 | 不同 |
|---|---:|---:|---:|
| 绍兴 ↔ USTX | 251 | **251** | 0 |
| 绍兴 ↔ USNJ | 251 | **251** | 0 |
| 绍兴 ↔ PL | 251 | **251** | 0 |

→ **用量 1:1 继承绍兴，0 例外**。这就是「PP棉 用量借绍兴」的落地形态：复制时只搬 PP棉 行、数量原样、只换料号与单价。

## 三、7-9 月国外包装成品 BOM 缺口

### 口径

对 7/8/9 月**自发货**订单写回表，逐行按 `发货仓按销售汇总分类`（值 `USNJ分公司`/`USTX分公司`/`波兰分公司`）判分公司，经 EN BOM 成本列表（`客户物料号` = 通途SKU）桥接到该分公司的**包装成品编号**（`美东包装成品, USNJ 编号` / `美中包装成品, USTX 编号` / `波兰包装成品, PL 编号`），再查该编号是否有 **`docstatus=1 且 is_active=1 且 is_default=1`** 的 BOM（快照 `out/bom_presence.tsv`）。

状态定义：
- `BOM_OK`：分公司成品编号有 active+default BOM。
- `无分公司成品编号`：列表行在，但该分公司编号列为空。
- `BOM_非启用默认`：编号有 BOM，但无「提交+启用+默认」的一张。
- `BOM缺失`：编号有，但 `tabBOM` 里查无（任何状态）。
- `不在EN_BOM列表`：该通途SKU 不在 EN BOM 成本列表里。
- 缺口 = 后四类。

### 逐月 × 分公司（订单行）

| 月 | 分公司 | 订单行 | 有BOM行 | **缺口行** | 有BOM占比 |
|---|---|---:|---:|---:|---:|
| 2026-07 | PL | 976 | 815 | **161** | 83.5% |
| 2026-07 | USNJ | 4202 | 4128 | **74** | 98.2% |
| 2026-07 | USTX | 4379 | 3983 | **396** | 91.0% |
| 2026-08 | PL | 1253 | 1072 | **181** | 85.6% |
| 2026-08 | USNJ | 4138 | 4021 | **117** | 97.2% |
| 2026-08 | USTX | 5479 | 5037 | **442** | 91.9% |
| 2026-09 | PL | 1149 | 977 | **172** | 85.0% |
| 2026-09 | USNJ | 2138 | 2009 | **129** | 94.0% |
| 2026-09 | USTX | 2959 | 2670 | **289** | 90.2% |

### 要因分布（缺口状态）

缺口行共 **1961**（= 161+74+396+181+117+442+172+129+289）；去重（月-分公司-通途SKU）**446**。

| 状态 | 行级 | 去重 |
|---|---:|---:|
| 无分公司成品编号 | 1296 | 235 |
| BOM缺失 | 588 | 186 |
| 不在EN_BOM列表 | 71 | 21 |
| BOM_非启用默认 | 6 | 4 |
| **合计** | **1961** | **446** |

### 要因分布（按绍兴发货方式，去重 446）

| 绍兴发货方式 | 去重条数 | 占比 | 业务含义 |
|---|---:|---:|---|
| **成品** | **368** | 82.5% | 成品直采直发，按规则**本无**国外加工 BOM → **非缺陷** |
| 皮壳 | 54 | 12.1% | 皮壳需国外二次加工 → **真缺口** |
| 空（不在 EN 列表 / 无发货方式） | 24 | 5.4% | 通途SKU 未挂到 EN 产品，另案 |

→ **「缺口」的主体是口径/字段问题，不是「该有 BOM 却没有」**：82% 是 `绍兴发货方式=成品`，与 `en-pl-finished-processing-nonzero-spec.md` 的「成品→0」规则自洽。真需追的是那 **54 条皮壳**（及 24 条未挂靠 SKU）。

### 能否用绍兴 BOM 填充

对 446 条缺口逐条取「绍兴包装成品, BOM」，查该绍兴 BOM 的 **PP棉 行数**（自动复制闸门 `check_pp_cotton_in_bom_items` 要求 ≥1）：

| 类别 | 去重条数 | 说明 |
|---|---:|---|
| **SX_BOM 含 PP棉（可被自动复制放行）** | **25** | 仅 `KS0018-SET7`、`KS0101-45` 两个家族（皮壳 21 + 成品 4） |
| SX_BOM 无 PP棉（闸门会早退） | 319 | 成品 318 + 皮壳 1 |
| 无绍兴包装成品 BOM | 102 | 成品 46 + 皮壳 32 + 空 24 |

**「无绍兴 BOM」的 32 个绍兴成品编号查证**（`tabItem` + `tabBOM`）：29 个 `SXBZCP#` 物料**存在但零张 BOM**（`valuation_rate=0`）；2 个物料**根本不存在**（`SXBZCP#KS0010-38`、`SXBZCP#KS0019-41`）；1 个（`SXBZCP#KS0212-54`）有 2 张 BOM 但**都非默认**（`is_default=0`，故自动扫描不认）。

**「没有绍兴 BOM」的可能原因（判断 + 证据）**：

1. **本就是成品（主因）**：这些款绍兴 `发货方式=成品`，绍兴侧就**不做填充工序、也不维护包装成品 BOM**——与「成品→0」一致。名单里的 `KS0302`（good靠枕）、`KS0307`（绑带款膝盖腿枕）、`KS0143`（多功能阅读枕）、`KS0103`（护颈枕）、`KS0010`（圆形坐垫）等，正是 `en-pl-finished-processing-nonzero-spec.md` 认定「像绍兴直采成品」的边缘品线。**证据**：29/32 的 `SXBZCP#` 物料存在却 0 BOM、`valuation_rate=0`；无任何加工痕迹。
2. **皮壳款在绍兴也没有（次因）**：9 个皮壳-lane 无 SX BOM 的款（`KS0004-100`、`KS0011-40`、`KS0019-41`、`KS0115-45`、`KS0145-45`、`KS0146-60`、`KS0244-66x50`、`KS0529-45x45`、`KS0530-90x60x36`）——查其半成品对应件 `SXBZBCP#`，**只有 2 个存在且都是 0 BOM**，其余 7 个连半成品物料都没有。→ 绍兴侧两级（成品/半成品）都不具备「可复制源」。**注意**：`KS0004-100`、`KS0019-41`、`KS0115-45`、`KS0529-45x45` 等也正是 PL 前作点名的「2025-02 建料批次人工残值」家族，属同一类历史遗留。

**结论（c）**：这批缺口**基本不能用现有绍兴 BOM 自动填**——只有 25 条（2 个家族）的绍兴源含 PP棉、可走既有复制链路；其余要么绍兴源是海绵版（无 PP棉）、要么绍兴根本没 BOM。真正需要业务决策的是**那 54 条皮壳缺口**：先补绍兴侧的 PP棉 版 BOM（或确认该款已改海绵、不再借绍兴），再谈复制。

## 四、可复现命令

> 全部在 worktree `.../hardcore-cerf-de2df7/tongtool_order_cost` 下执行；一律 `uv run python`。`out/` 已 gitignore。EN 侧只读 SSH：`ssh 阿里云-FZH-ERPNext-frappe`。

```bash
cd "D:/Work/赛狐/Cursor/.claude/worktrees/hardcore-cerf-de2df7/tongtool_order_cost"

# ① 订单侧写回（8/9 月；7 月用本地冻结快照）
uv run python out/_fetch_wb.py            # → out/writeback_202608.csv, out/writeback_202609.csv

# ② EN BOM 成本列表（桥接表：通途SKU = 客户物料号 → 3 家分公司编号 + 绍兴包装BOM名）
uv run python out/_fetch_bomlist.py       # → out/importBOMCostList_now.csv

# ③ EN 各分公司包装成品 BOM 存在性快照（按前缀分批，规避 1000 行截断）
uv run python out/_fetch_bom_presence.py  # → out/bom_presence.tsv (1451 行)

# ④ 缺口分析（读 ①②③ + 7月快照）
uv run python out/_gap_analysis.py        # → out/overseas_bom_gap_jul_sep.csv, out/gap_detail.json
uv run python out/_gap_summary.py         # → out/overseas_bom_gap_summary.csv, out/overseas_bom_gap_no_sx.csv
```

EN 只读查询（Q1 落点与 Q2 聚合）用 stdin 传 SQL，避免命令行过长：

```bash
# Q1: 工时系数三行
ssh 阿里云-FZH-ERPNext-frappe "cd /home/frappe/frappe-bench && bench --site erpnext.vilavi.cn mariadb --skip-column-names" <<'SQL'
SELECT parent, name, branch_code, branch_name, time_multiplier, enabled
FROM `tabForeign Branch Time Multiplier`;
SQL

# Q1 代码落点
ssh 阿里云-FZH-ERPNext-frappe "cd /home/frappe/frappe-bench/apps && grep -rn 'time_multiplier' --include='*.py' work_order_task | head"

# 本仓库已落盘的 SQL：out/_q_q1.sql / _q_q1b.sql / _q_q1c.sql / _q_q2.sql / _q_q2b.sql / _q_q2c.sql
# 缺口集绍兴 BOM PP棉：out/_q_gap_sxbom.sql   → out/gap_sxbom_pp.tsv
# 无绍兴 BOM 的绍兴件：   out/_q_nosx_items.sql → out/gap_nosx_items.tsv
#                        out/_q_nosx_semi.sql  → out/gap_nosx_semi.tsv
```

### 产出清单（`out/`，gitignore）

| 文件 | 内容 |
|---|---|
| `overseas_bom_gap_jul_sep.csv` | 缺口明细（446 行，月×分公司×SKU），列含绍兴发货方式/绍兴包装BOM |
| `overseas_bom_gap_summary.csv` | 逐月×分公司汇总（订单行/有BOM行/缺口行/去重/绍兴发货方式分解） |
| `overseas_bom_gap_no_sx.csv` | 「无绍兴包装成品 BOM」的 102 条明细 |
| `gap_detail.json` | 全部订单行级判定（含非缺口行） |
| `bom_presence.tsv` | 四前缀 BOM 存在性快照（1451 行） |
| `gap_sxbom_pp.tsv` | 缺口集 73 张绍兴 BOM 的 PP棉 行数/状态 |
| `gap_nosx_items.tsv` / `gap_nosx_semi.tsv` | 无绍兴 BOM 的绍兴成品/半成品件是否存在的查证 |

## 五、未查实 / 存疑

1. **1.5× 的「历史成因」未重查**：本页只证实**当前**配置与代码落点（USTX=1.5 生效于批量复制路径）。为何 2025-10 那批 USTX BOM 也呈 1.5×、而 2026-01-23 后部分又退回 1.00（自动路径不乘系数）——前作已记，本次未再逐张回溯。
2. **「同一 SKU 该走哪条复制路径」无机器判据**：`bom_batch_process.py` 与 `utils/bom.py` 两条路径并存且系数有无不同，**何时用哪条**取决于触发方（批量任务/表单按钮 vs `on_submit`），本页未枚举全量触发点。
3. **缺口口径依赖 EN BOM 成本列表的「分公司编号」列**：若该列本身漏填（`无分公司成品编号` 1296 行/235 去重），缺口会被高估。本次**未**独立于该列表去反推「该 SKU 应属于哪家分公司编号」，故 235 条里有多少是「列表列漏填」vs「确实无对应物料」未拆分。
4. **「绍兴发货方式=空」的 24 条（去重）未逐条定位**：部分是通途SKU 不在 EN BOM 列表（`不在EN_BOM列表` 21 条），部分可能是列表行缺发货方式。其业务归属未查。
5. **皮壳 54 条里 32 条无绍兴源**——只给出「绍兴两级都无 BOM」的事实与「像直采成品」的旁证，**未取得业务确认**「这些款到底该在绍兴做填充、还是本就直采」。
6. **未按发货数量加权**：本页缺口统计是**订单行/去重产品**口径，未乘 `发货数量`，故不等于「金额影响」；`overseas_bom_gap_summary.csv` 有 `发货数量` 列可用。
7. **工作表外的核对未做**：财务给的 `D:\Work\王忠于\成本核算-9境外二次加工成本.xls`（3 家×3 月工钱+PP棉）在**工作目录之外**，需目录授权才能读；本次**未读**，故「工站工资率 167.8 / 拟 105、管理费率 34.24 是否与财务口径吻合」**未核对**。

## 补充（2026-10-17，用户问「绍兴侧都没有 → 直接采购？还是借用逻辑？」）—— 已用 `default_material_request_type` 验证

对 `out/overseas_bom_gap_no_sx.csv` 的 **59 个物料编号**（32 绍兴 `SXBZCP#` + 27 分公司 `…BZCP#`）查 EN `tabItem`：

| 类别 | 条数 | 含义 | 处置 |
|---|---:|---|---|
| **`default_material_request_type = Purchase`** | **30** | **直接采购** ⇒ **本就不该有 BOM** | ✅ **不用补**（用户假设成立） |
| **`= Manufacture`** 但**零张 BOM** | **24** | **应制造却没 BOM** ⇒ **真缺口** | ⚠️ **必须补**（且**无从"借"**：借用=从绍兴复制，绍兴也没有） |
| **EN 里查无此物料** | **5**（`PLBZCP#/SXBZCP#KS0010-38`、`KS0019-41`、`USNJBZCP#KS0019-41`） | 物料不存在（疑改名/淘汰） | 需核 SKU 映射 |

> **结论**：A 原文"102 条不能填"应细化为 —— **约 30 条（直接采购）本来就不需要 BOM**（**不是缺陷**）；**24 条是 `Manufacture` 却无 BOM，才是真缺口**；5 条物料不存在。
> **"借用逻辑"对真缺口的 24 条不适用**（借用 = 复制绍兴 → 绍兴也没有可复制源）；只能**人工补 BOM** 或**改 `default_material_request_type`**（若业务上其实是采购）。

