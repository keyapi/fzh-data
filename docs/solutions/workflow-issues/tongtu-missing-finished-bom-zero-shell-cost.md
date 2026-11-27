---
okf: v0.1
type: Reference
title: 皮壳商品皮壳成本=0（成品 BOM 缺失）的识别与门禁
date: 2026-11-26
last_updated: 2026-11-27
category: workflow-issues
module: tongtool_order_cost
problem_type: workflow_issue
component: tooling
severity: medium
applies_when:
  - "build-order-tabs 出来的皮壳商品皮壳成本为 0、但 1件产品成本 仍有值（只剩目的地加工）"
  - "对拍旧 Colab 表发现某 SKU 单位成本明显偏低，差的正好是皮壳那一行"
  - "怀疑 1104 BOM 里某个成品没有成品 BOM（bom_fg 空），只有绍兴成品包装 BOM（cost_sxbzcp）"
tags: [build-order-tabs, bom, cost-gap, gate, 皮壳成本, pike]
---

# 皮壳商品皮壳成本=0（成品 BOM 缺失）

## Context

`build-order-tabs` 的四列成本口径：`皮壳= BOM cost_fg`、`头程= BOM 头程`、
`二次加工= 目的地 valuation`、`绍兴二次= 皮壳0 / 半成品 cost_sxbzbcp / 成品 cost_sxbzcp / FBA cost_sxbzcp`。
对 `shipping_method=皮壳` 的成品，绍兴二次固定为 0，**皮壳成本完全依赖 `cost_fg`**。

1104 BOM（`out/bom_cost_product_with_disabled.csv`）里有一批成品
`bom_fg` 为空、`cost_fg=0`，但 `bom_sxbzcp`/`cost_sxbzcp` 有值。结果这些行的
`皮壳成本=0`，`1件产品成本` 只剩目的地 `valuation`（二次加工），皮壳那一截被静默丢掉。

## Guidance

1. **判据**（已固化为 build `warn` 门禁“皮壳成本=0但产品有成本（疑似成品BOM缺失）”）：
   `是否皮壳=皮壳` 且 非 `-COVER/-FOAM/-PPCOTTON` 组件 且 `皮壳成本=0` 且 `1件产品成本>0`。
   命中即列入清单；借用补齐后应变 `pass`。
2. **与“目的地加工=0”区分**：那是 `皮壳>0、二次加工=0`（如 KS0019 星球抱枕、KS0133 地板枕套装），
   本门禁是 `皮壳=0、二次加工>0`，两者互补。
3. **不要把 US 本地棉包 KS0050 当问题**：它 `shipping_method=成品`（`是否皮壳≠皮壳`），
   按美国本地口径 `二次加工=valuation` 是设计如此，不会被本门禁命中。
4. **借用补齐（已实现，2026-11-27）**：`build_tabs._apply_finished_bom_borrow` 对
   `皮壳 + bom_fg空 + cost_fg=0` 的物料借同「品类-面料-尺寸」其它颜色 `cost_fg`，取**众数**
   （并列取文档最先，避免个别异常色如 CMM-153-PURPLE=19.575 污染）；整族都缺 BOM 的个例走
   `config/finished_bom_borrow_overrides.csv` 跨面料指定（`MM-153-BLUE←CMM-153=64.93`、
   `KS0464-FHXYR←MSTWB=43.228`）。只改派生文件 `out/bom_cost_borrowed_<月>.csv`，**原始 BOM 不动**；
   审计 `out/finished_bom_borrow_audit_<月>.csv`，manifest `stats.finished_bom_borrow`。可 `TONGTU_NO_BOM_BORROW=1` 关闭。
5. **确认后放行**：确实应为 0 的，写进 `config/known_zero_shell_allowlist.csv`（`item_fg,note`）。
6. **根治**：让 EN/BOM 维护人补该成品的成品 BOM（`bom_fg`），或明确该类商品
   改用 `cost_sxbzcp` 作皮壳——但后者会与目的地 valuation 的覆盖范围冲突，须财务先定口径。

## Why This Matters

- 该缺口**跨月系统性存在**：202607/08/09/10 命中 50/45/32/36 行；202610 涉及 14 个物料、
  预估少计约 2,700（仅 25 行有旧值可估，另 11 行无旧值）。
- 单行差异可以很大：`TT0031112K0063740` 旧 191.30 → 新 117.95（−73.35）；
  `TT0031112K0063742` 旧 329.92 → 新 181.04（−148.89）；`C/Leaves-Grey-183-684-wow`
  旧 303.84 → 新 232.97（−70.87）。二次加工两版一致，差的正好是皮壳行。
- 静默为 0 会被当成“真实成本”，污染利润与分公司加工成本对比。

## When to Apply

- 每月 `build-order-tabs` 后看 `manifest.assertions`：本项若不是 `pass`，先看 `parity` 与清单。
- 老板/财务质疑某类成品“成本异常低”或“利润率异常高”时，优先查这条。
- 新增/迁移 EN 成品、改物料编码后，抽查 `bom_fg` 是否为空。

## Examples

202610 命中的物料族（均为 `bom_fg` 空、`cost_fg=0`、`cost_sxbzcp>0`）：

| 物料族 | 例子 | 旧 Colab 皮壳 |
|--------|------|---------------|
| KS0301-XER | KS0301-XER-100/140/194/200-GREYBEIGE | 93.73 / 114.51 / 147.28 / 148.88 |
| KS0001-TR | KS0001-TR-153-GREEN/YELLOW/ROYALBLUE、194-DENIMBLUE | 57.05 / 160.01 |
| KS0001-CMM | KS0001-CMM-140/153-YELLOW | 72.89 |
| KS0001-CMGDTH | KS0001-CMGDTH-183-GREY | 70.87 |
| KS0001-MM / HLR | KS0001-MM-153-BLUE、HLR-140-DARKGREEN | 134.32 / 42.64 |
| KS0464 | KS0464-FHXYR-60x45x42-RED | 45.38 |

### 已落地结果（2026-11-27，202610）

借用后 202610：命中 36 行全部补齐（140 条同面料众数 + 2 条跨面料 override），
门禁 `皮壳成本=0但产品有成本` → `pass`；self `皮壳成本` +3,268.23（345,173.13）、
`订单总成本` 1,856,044.80→**1,859,313.03**、`订单利润` −3,268.23；FBA Δ0；
merged 同步 +3,268.23。三张写回表 **readback 0**。

跨面料个例（整族无成品 BOM）：`KS0001-MM-153-BLUE←KS0001-CMM-153-COFFEE=64.93`、
`KS0464-FHXYR-60x45x42-RED←KS0464-MSTWB-60x45x42-RED=43.228`。

### 精修：以成品 BOM 明细行引用的 PK# `bom_no` 为准（2026-11-27）

**不要去启用/使用「某个恰好有成本的」或「被停用的」PK# BOM；成品 BOM 明细行的 `bom_no` 才是权威。**
override CSV 用 `cost_fg` 绝对列写入「引用的 PK# 子BOM total_cost + 内胆(ND#) 子BOM total_cost」：

- `KS0301-XER-{100,140,194,200,153}-GREYBEIGE = 68.5792 / 83.026 / 106.6008 / 107.9182 / 89.6724`（均引用 **PK#-002**）。
- `KS0464-FHXYR=45.86704`（引用 PK#-002 36.41784 + ND#-001 9.4492）。
- `CMGDTH-183-GREY=59.882`、`CMM-153-YELLOW=64.93`：目标面料单价与同款相同（17.64 / 23.5），借用=重建，精确。
- 面料物料本身不存在时（如 `CMM2020-BLUE-142-260` 404）无从重建，只能借。

**踩过的坑**：XER 的 `PK#-001`（雪儿绒 XERML1010）**自 2025-03-27 就被 002 取代停用**，不是 9/10 误停；
我一度按「001 有成本」重建（95.20/148.61）→ 错误。成品行引用的是 **002**。
教训：**看成品行 `bom_no`，不要看「哪个 BOM 有成本」**。已把 001 恢复停用、引用到的 002/KS0464-002 置 `is_active/default=1`。

**改用荷兰绒（业务决定）**：雪儿绒难采购，三角靠枕改用荷兰绒 HLR1020 降本。已把 `PK#-002`：
140/200 两道面料 XERML→HLR、153 补 2.1m CREAM（原漏一道），`update_cost`；
PK# 物料 `valuation_rate` 同步为新 BOM 成本、成品 `update_cost` 后成品=68.579/83.026/106.601/107.918/89.672。
本版 `rm_cost_as_per` 不支持 "BOM Rate"（仅 Valuation/Last Purchase/Price List），故走「皮壳物料估值=BOM成本」。

精修后 202610：self 总成本 **1,858,743.04**、利润 1,650,383.95、皮壳 344,603.13；
相对「第一次借用版(已提交财务)」皮壳 **−570.00**、绍兴二次不变。

7/8/9 月不重算（已提交财务，老板定 2026-11-27）。

## Related

- `tongtool_order_cost/tongtool_order_cost/tongtu_cost_engine/domain/build_tabs.py` —— 门禁 + `_apply_finished_bom_borrow`
- `tongtool_order_cost/config/known_zero_shell_allowlist.csv` —— 确认放行清单
- `tongtool_order_cost/config/finished_bom_borrow_overrides.csv` —— 跨面料借用个例
- `tongtool_order_cost/docs/reference/build-order-tabs.md` —— 四列口径与门禁
- [tongtu-cost-engine-local-migration.md](../architecture-patterns/tongtu-cost-engine-local-migration.md) —— 四列语义
- [tongtu-e2e-gates-silent-failures.md](../best-practices/tongtu-e2e-gates-silent-failures.md) —— 静默 fallback 转可解释失败
