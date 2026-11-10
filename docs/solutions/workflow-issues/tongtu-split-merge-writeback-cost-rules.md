---
okf: v0.1
type: Reference
title: 通途拆单合并成本写回：五类错误与修复（组行匹配 / 件数 / 产品族 / 订单号截断 / 审计口径）
date: 2026-11-09
category: workflow-issues
module: tongtool_order_cost
problem_type: workflow_issue
component: tooling
severity: high
symptoms:
  - "合并组在 GS 写回表里成本为 0，但 Phase2 算得出整组成本"
  - "同一组两行（皮壳+填充）都写了整组成本，金额翻倍"
  - "EN 原单组件行重复时，件数被锚成 2，成本翻倍（实际只发 1 件）"
  - "同一皮壳用于 PP棉/海绵两种成品，整件成本对到错误 BOM"
  - "模板订单号少一段后缀，写回时匹配不到、成本被清空"
root_cause: "Phase36 把拆单前公共单号/单行组行当成组件清零；件数锚定用了重复的 EN 原单；产品族只按皮壳唯一性判定；模板订单号被截断；审计按单位成本直接对比组总成本"
resolution_type: fix
tags: [tongtu, split-merge, phase36, pieces, product-family, gsheet, audit]
---

# 通途拆单合并成本写回：五类错误与修复

## Problem

2026-08/09 月合并组自查（83 / 42 组）首轮有 **18 / 11 组不通过**。表面现象是 GS 里部分合并组成本为 0 或翻倍，但 Phase2 的组成本是对的。根因分布在「模板行匹配 → 件数 → 产品归属 → 写回对账」四段，共五类。

## Symptoms

- 组成本为 0：模板行是拆单前公共单号（如 `Cds-260812130757QFL`）或作废原单，被当成「被吸收组件」清零。
- 组成本翻倍：同一组的两行（`-Cover` + `-Foam`）都拿到整组成本；或件数被锚成 2。
- 产品对错：Curve Pillow 同一皮壳用于 PP 棉/海绵两种成品，皮壳 EN 行登记到海绵族，整件成本按海绵 BOM 算。
- 订单号截断：模板把 `…-6793020` 写成 `…-4922882`，写回匹配不到，成本清空（不是缺行）。
- 审计误判：把「单位成本 × 件数」与「组总成本」直接比，多件组全部报错。

## What Didn't Work

- 只按 `(订单号, 通途SKU)` 精确匹配模板行：拆单前公共单号、TikTok 归一化单号、单行组（显示组件 SKU）都匹配不到。
- 把 `invalid=1` 原单当普通组件：原单是组行，不是被吸收组件。
- 用 EN 原单的 Cover 计数锚定件数：原单组件行重复时，Cover 计数也被重复，件数翻倍。
- 只按皮壳别名唯一性定产品：同一皮壳可挂 PP 棉/海绵两个产品族，皮壳唯一不代表产品正确。
- 审计直接比较单位成本列与 Phase2 四列合计：Phase2 列是**组总成本**，模板列是**单位成本**。

## Solution

### 1. Phase36 组行匹配（`phase36_fill.py`）

- 新增 `src_group_by_common` / `src_group_by_body`：写回源只有载体一行，模板行用拆单前公共单号或 TikTok 数字主体。
- `group_row` 标记：模板行若属合并组（公共单号命中、或同组只剩一行且源是 merged 载体），按**整组成本**填入，不再按「被吸收组件」清零。
- 单行组显示组件 SKU（如 `-Foam`）时，用 `tpl_rows_by_common` 判断「同组只剩一行」；同组还有多行时仍按组件行 0 成本。
- 作废原单的公共单号行（模板里是组行）优先按组映射，不再直接走 `invalid_original` 清空。

### 2. 件数（`split_merge.py`）

- 皮壳载体：Σ 同皮壳 base 的行数量。
- EN 原单（aux）组件行重复：只说明原单 qty 合计不可用，**不代表件数翻倍**；子单皮壳件数可确定时以子单为准。
- 仅当子单件数 `pieces_ambiguous / pieces_zero` 时才用原单件数兜底。
- 实例：`KFLDE-MBU14K5` 原单 4 行（2 Cover+2 Foam），通途只发 `_1`（1 Cover+1 Foam），`_2` 顾客取消；件数应为 1 而不是 2。

### 3. 产品归属（`split_merge._cover_product_precedence`）

- 皮壳与填充产品族只差 `item_group` 的「PP棉 vs 海绵」→ **填充行**定产品（`group_filler_override`）。
- 只差款式/图案（方格 vs 菱形）→ 仍由皮壳定产品（`group_cover_override`）。
- 皮壳行 EN 物料在错误族时，按「产品族前缀替换」构造目标族同色同尺寸物料（`KS0342-HLR-50-DEEPBLUE` → `KS0340-HLR-50-DEEPBLUE`）；构造不出 → 阻断，不按错误 BOM 计价。
- `item_for_detail` 增加基号兜底：载体 SKU 在当前产品族找不到 Item 时，用去 `-Cover/-Foam` 的基号在同族再找一次，仍不唯一则阻断。

### 4. 模板订单号截断

- 现象是 `crosswalk_missing`，不是缺行；修正模板与 GS 两个表的订单号即可。
- 写回脚本按 keys 比对；本地模板和 GS 必须同步修正，否则 key mismatch 会中止。
- 本次修正 `BJRYECLTUS-113-4922882` → `BJRYECLTUS-113-4922882-6793020`（原始单与补发单 `-M7914` 分别计价）。

### 5. 审计口径（`out/_merge_audit.py`）

- 组成本对比：模板单位成本 × 该行发货数量 后再与 Phase2 四列合计比；不是直接比单位成本。
- 组行集合：子单原号 + 子单剥一层尾号 + 拆单前公共单号 + TikTok 数字主体。
- 后缀审计：合并组内行不套单品后缀矩阵（整组按产品计价）；只检查单独卖 `-Cover/-Foam/-PPCotton` 的行。

### 6. 成本列一致性 + 整成品 method 覆盖（2026-11-10）

- **症状**：同一 SKU 在 GS 里 `皮壳成本=53.939`，但 `皮壳含包装成本/不含/系数=76.961`；
  `绍兴二次加工成本` 有的行 0、有的 16.522567。
- **原因**：
  1. phase36/build 只重算 `皮壳成本`，`皮壳含/不含/系数` 仍从旧写回继承（历史 BOM），造成两套值。
  2. 0 的行是 EN 订单行 method=皮壳（多在 `退货产品仓`），而 BOM 主档=半成品；raw `发货仓库`
     却显示 `美中-FZH-DANEEY`，按 raw 过滤看不出差异。
- **修法**：
  - `皮壳含/不含/系数` 统一 = 当前 `皮壳成本`；`EN绍兴包装半成品/成品` = 当前 BOM
    `cost_sxbzbcp/cost_sxbzcp`（旧「成品」列其实是合并后二次加工×系数）。
  - **整成品 SKU**（无 `-Cover/-Foam/-PPCotton` 后缀）+ BOM=半成品/成品 + EN=皮壳 →
    按 BOM method 计价（`bom_override_full_product`）；组件后缀行仍按 EN method。
    202608 49 行 / 202609 12 行，按行重算成本差 +2,116.67 / +911.87。
  - 新增 `self_method_warehouse_audit.csv`：EN vs BOM method、raw vs EN 仓库逐行差异。
- **排查顺序**：不要只看 raw `发货仓库`；先看 `self_method_warehouse_audit.csv` 的
  `EN发货仓库/EN_method/BOM_method`，再判断 0 是后缀规则还是 method 冲突。

## Why This Works

- 合并组是「一件成品」，只有载体/整件一行有成本，组件行必须为 0；组行匹配正确后成本自然落表。
- 件数只能来自实际发货的皮壳；原单重复行不是第二件。
- 产品族由「差异化组件」决定：共享皮壳看填充类型（PP/海绵），共享填充看皮壳（图案/颜色）。
- 模板是展示层，订单号截断是数据错误；修正数据而不是在引擎里猜前缀。
- 审计必须与 Phase2 的「总成本」口径对齐，否则多件组天然报错。

## Prevention

- `tests/test_tongtu_cost_engine_phase1.py::test_aux_component_rows_do_not_sum_pieces`（原单重复不翻倍）。
- `tests/test_tongtu_cost_engine_phase2.py::test_filler_type_conflict_uses_filler_product`（PP/海绵由填充行定产品）。
- `tests/test_tongtu_cost_engine_phase2.py::test_method_diff_full_product_overrides_to_bom_method`、
  `test_cover_suffix_keeps_en_cover_method`（整成品 method 覆盖 / 组件不覆盖）。
- `out/_merge_audit.py`：组成本、后缀、守恒三类自查；202608/202609 现为 0/0 失败。
- `out/_gs_diff.py`：写回前后按备份还原对比，确认变化行与金额（202608 20 行 +23,751.83；202609 10 行 +12,543.13；FBA 表 0 变化）。
- 写回前备份：`out/gs_full_*_<时间>/backup.csv`；写后逐格回读。

## Related

- `docs/reference/tongtool-order-canon/02-grouping-and-merge.md`（§6 件数、§7 产品归属）
- `docs/reference/tongtool-order-canon/rules.yaml`（GRP-005/007/008/009）
- `docs/reference/cost-engine-spec/36-phase3.6-fill-tables.md`、`37-phase3.7-gs-ready.md`
- `docs/solutions/conventions/tongtu-split-types-and-presplit-sku.md`
- `docs/solutions/integration-issues/tongtu-en-item-mapping-and-gsheet-source-fix.md`
