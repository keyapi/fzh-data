---
okf: v0.1
type: Reference
title: 给 Codex 的评审说明（美中 USTX 成本：直连映射 + gsheet 源头修正）
description: 自足评审包：待证伪断言、证据位置、约束、已知历史、输出格式。评审对象 = PR #295 的本轮增量。
date: 2026-10-17
module: tongtool_order_cost
tags: [review, codex, ustx, cost, gsheet, direct-path]
---

# 给 Codex 的评审说明（零上下文可读）

> 目标：独立核验**本轮**（2026-10-17）在 PR [#295](https://github.com/keyapi/fzh-data/pull/295)（分支 `feature/ustx-cost-compare`）上的增量。**未做**的两项已单列（§5），不在本次评审范围。

## 0. 只读这些就够

1. `tongtool_order_cost/docs/reference/cost-engine-spec/27-gsheet-source-root-cause.md`（gsheet 源头根因 + 已执行修正）
2. `…/28-parse-vs-en-7to9.md`（解析 vs EN 真值体检 + 直连 A/B + §7 更正）
3. `…/16-customer-sku-direct-path.md`（直连的原始方案）
4. `tongtool_order_cost/tongtool_order_cost/ustx_cost_compare.py`（`build_direct_index` / `build_direct_catalog` / `direct_template_from_item` / `compare_monthly_costs(direct_catalog=)`）
5. `tongtool_order_cost/tests/test_ustx_cost_compare.py`
6. `docs/solutions/integration-issues/tongtu-en-item-mapping-and-gsheet-source-fix.md`

## 1. 待证伪断言（**逐条给证据或反例**）

1. **直连覆盖 99.9%**：7 月美中 `direct_used=4367 / b2_used=4372`。→ 复跑 `uv run python tongtool_order_cost/scripts/audit_monthly_profitability.py ustx-compare --snapshot <7月快照>`，看 `b2_direct_coverage` 闸。
2. **直连相对旧键：B2 匹配 4328→4372、未匹配 51→7、ΔB2 264,912→268,610**。→ 对比加 `--no-direct` 的 `audit.json`（`counts.b2_import/b2_unmatched`、`component_waterfall` 的 `d2_amount` 合计）。
3. **EN 物料名→重量模板 的派生规则**（去末段颜色 + 前缀 `ZLMB#`）**对所有命中都成立**、无例外（尤其多段颜色名/无颜色项）。
4. **gsheet 已执行的 43 格修正**（品类使用面料 246/247/248、皮壳表 453/634-639/838-845、糖果 625/626）**现值 = 28 页 §3/§5 所述**、且**回读过**。
5. **`importBOMCostList.客户物料号` 就是通途SKU**（与 EN `Item Customer Detail.ref_code` 同源同值）。→ 抽查若干 SKU 两源比对。
6. **`ref_code` 经 REST 查 403、经 SSH+DB 可查**；且 `tabItem Customer Detail` 的列名是 `ref_code`（不是 `customer_item_code`）。

## 2. 证据要求

- 每条断言：**给命令 + 可复现输出**（行数/哈希/键清单），不要只给结论。
- 数字类：**先抽查原始记录再下结论**（本会话吃过亏：自算的"11% 覆盖率"是脚本 `startswith("TT")` 丢 `CE*` 前缀导致的 bug，真值 99.9%；见 28 页 §7）。
- 发现冲突以 **EN 真值（`ref_code` / EN 物料名）** 为准。

## 3. 已知历史（别重复报）

- 28 页 §7 已自曝并更正「11%」；§1/§2 的 88/85 行清单只统计**命中行**，不受覆盖率 bug 影响。
- Codex 前三轮（13/17/20 页）的结论仍有效：直连**不主张"更准/零损失"**；同客户码多候选须按候选处理（我们在 `build_direct_index` 里对同 SKU 多模板做**剔除+记录**，不取首/末）。
- 26 页 §6 的「删 637」**已被 EN 反证作废**（27 页）。

## 4. 约束（评审时也请守）

- **只读**：不要写任何 gsheet / EN / 通途。
- 不打印凭证；`tongtool_api/.env`、`secrets/` 不进 git。
- Windows：`uv run python`；不要 PowerShell `Set-Content -Encoding UTF8`。

## 5. ⚠️ 本轮**未做**（不在评审范围，用户另排）

1. **拆包裹/合并订单 → 统一成一个成品再对 BOM**（避免成本重复计）。
   - **设计稿**：[30](30-design-merge-split-no-double-count.md)（落点/算法/5 条不重不漏断言/待拍板）。
   - **第 1 片已落地**：`order_common_part`（只剥 1–2 位后缀）+ `group_split_rows`（拆包裹候选分组+审计；**不合并、不改原行**）+ 2 测试。
   - **未做**：聚合（售价/运费 sum、成品行选取）、对 BOM、A/B 对拍。
2. **通途 API 改产品名**：已定位——`productType=2` 分页可见「绗缝方格/菱形扣子床头板」等；**这些商品的 `sku` 字段在 API 返回里是 `None`**（故 `skus` 过滤查不到）。**注意：通途产品主档名若本就分好类，则需先厘清"订单导出名 vs 产品主档名"再谈改。** 未改。
3. `管理摘要.md` 尚未加"直连覆盖率"行（现只在 `audit.json` 闸里）。
