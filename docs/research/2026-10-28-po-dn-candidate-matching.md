---
okf: v0.1
type: Research
title: PO ↔ DN 候选匹配（2026-08–10，给人工确认）
description: 28 张 DN 中 20 张无正式 PO 链接；用 SKU 交集+逐 SKU 数量+日期窗口给候选，8 张回归全中
tags: [erpnext, delivery-note, purchase-order, tongtool, matching]
date: 2026-10-28
status: delivered-pending-human-confirmation
---

# PO ↔ DN 候选匹配（2026-10-28）

> 只读分析：不改 EN、不改通途数据、不 push。
> 交付：`D:/Work/fzh-order-store/analysis/po_dn_candidate_links_2026-10-28.csv`
> / `po_dn_sku_recon_2026-10-28.csv` / `PO_DN候选匹配报告_2026-10-28.md`；
> 脚本 `scripts/po_dn_candidate_match.py`。

## 1. 结果

| 指标 | 值 |
|---|---:|
| 2026-08-01 起 DN | 28（2,589 行 / 122,327 件，其中材料/组件 99,515 件） |
| 已有 EN 正式链接 | 8 |
| 无正式链接 | 20 |
| └ 给出候选 | 19 |
| └ 明确无候选 | 1（DN-26-00068，`ND#KS0001-60-CYF-WHITE` ×800，无客户码、PO 侧无对应 SKU） |
| 8 张回归样例 | 8/8 命中且 rank 1 |
| 采纳对逐 SKU 对账 | 27 对 / 337 SKU 行；数量全等 302，不等 35（全部 PO > DN） |

## 2. 关键口径（新增/校正）

1. **PO 日期用 `createdDate`**，`po_no` 是 LH 旧编号，不参与匹配。
2. **年份窗口双向 ±90 天**：实测同日 12 张、PO 晚于 DN 15 张（隔日 8 / 回溯 7）、PO 早于 DN 0 张。
   8/26 集中建了 9 张 PO（PO021704–021712），是 8/4–8/21 六张 DN 的**回溯建单**。
3. **DN 客户码为空的行**：先按 `item_code` 去 `PK#`/`ND#` 前缀反查 `sku_item` → 通途 SKU
   （2,310/2,589 行可解析；279 行主要是材料/组件，如 `KZKP1010-5#-IRONBOTTOMSURFACE`）。
4. **同 SKU 数量逐行对账**：DN 按 SKU 聚合 ↔ PO 按 SKU 聚合，`-Foam`/`-Cover` 后缀归一后才命中
   （5 行靠归一）。
5. 评分 = 0.45×SKU 召回 + 0.30×数量拟合 + 0.10×完全相等 + 0.15×日期接近；≥0.60 采纳。

## 3. 数据缺口

| 缺口 | 事实 | 影响 |
|---|---|---|
| 7/26–8/25 无 PO | 只读 API `purchaseOrderQuery` 该窗口返回 0 行 | 8 月初 DN 只能靠 8/26 回溯批匹配 |
| PO021743 不在本地快照 | 本地快照截到 10/26；已用只读 API 补拉（10/27 建单） | 回归样例 8/8 才能复现 |
| 任务书给的入库明细路径不存在 | 实际在 `tongtool_po/po_receipts_20260801_20261028.csv` | 已按实际路径读取 |
| 组件行无物料映射 | `ND#`/`PK#` 在 `sku_item` 覆盖不全 | 1 张 DN 完全无法匹配；多张 DN 数量口径要拆「材料」 |
| 重复 PO | PO021733=PO021735；PO021719=PO021720（同仓同 SKU 同数量） | 未纳入候选，需业务确认作废 |

## 4. 边界

- 候选是**规则推断**，不是凭证；回填 EN `custom_tongtool_purchase_order` 需单独授权。
- 不把 `po_no` 当通途 PO；不按总数判等（只按 SKU）。
- 行级数据留本地，本文只写聚合。

---

## 附录：v2（2026-10-28 复审 reject 后重做）

复审：`C:/Users/zhang/.agent-ops/fzh-data/reviews/po-dn-match-review-2026-10-28.md`（F1–F5）。

**结果变化**：28 张 DN = 正式链接 **9**（EN 字段导出，比任务书多 DN-26-00114→PO021742）/ 有候选 18 /
纯内胆 1（DN-26-00068，业务规则：ND# 纯内胆不建 PO）/ FBA 0（规则已实现）/ 无候选 0。
9 张正式链接全部 rank 1；8 张已知样例仍全中。

**修复**：
- F1 `official_owner` 来自 EN `custom_tongtool_purchase_order` 只读导出（带 manifest）；
  评分前排除他人正式占用的 PO；`official_owner` / `proposed_owner` 分列，非正式不再写「本DN」；
  采纳对做逐 SKU 显式分配 `alloc_qty`（full/po_excess/shortfall）。
- F2 `qty_fit = 1 - Σ|DN_sku-PO_sku| / ΣDN_sku`（未命中全差计入）+ `coverage`；
  测试含 DN(10,90) vs PO(90,10) 反例 → 0。
- F3 多别名 63 行/518 件/9 DN：显式渠道别名规则解析 28 行/271 件，隔离 35 行/247 件；不挑选别名抬分。
- F4 反查别名与 PO 别名都清 `删除`；DN-26-00086 恢复 10/10 SKU、141=141。
- F5 通途 PO 补拉带分页 manifest（7/25–8/26 = 2 页 113 行，修正 v1 只取 100 行漏 PO021712）；
  「7/26–8/25」改述为「该查询窗口返回 0 行（状态 200、未触发分页上限）」。

**新增业务分类**：纯内胆 DN、FBA DN → 「不建PO/无需匹配」，属预期正常，不是缺口；
EN 侧 8/1 起共 63 张 DN（32 张 FBA + 3 张已取消），明细导出只含 28 张非 FBA 未取消单。

产物：`D:/Work/fzh-order-store/analysis/*_v2.csv/json`、`PO_DN候选匹配报告_2026-10-28_v2.md`；
脚本 `scripts/po_dn_candidate_match_v2.py`、`scripts/en_dn_po_field_export.py`、
`scripts/tongtool_po_pull.py`；测试 `tests/po_dn_match/test_po_dn_v2.py`（8 passed）。

## 附录：v3（2026-10-28 v2 复审 accept-with-findings 后小修）

复审：`C:/Users/zhang/.agent-ops/fzh-data/reviews/po-dn-match-v2-review-2026-10-28.md`。
只改 5 项，匹配结果不变：27 个首选与 v2 完全一致，9/9 正式链接仍 rank 1。

- **P2#1**：非正式推荐改标 `候选建议→DN-…（未正式登记）`；「本 DN」只留正式链接
  （v3 links：正式 9、候选建议 53、空 20，**无「本 DN（建议）」**）；v2 报告 19 已更正为 18。
- **P2#2**：FBA 判定补「全部明细客户码都是 FBA 码」分支；mixed/unknown 不算 FBA，新增 3 条测试。
- **P2#3**：exception 每条带 `uom` / `qty_by_uom` / `role` / `aliases_raw_all`；
  JSON 删掉跨单位 `dn_qty_total`，改 `dn_qty_by_uom`（个 38,422 / 套 83,805 / 件 100），
  recon 只含个 22,565；不做套/件→个换算。
- **P3#4**：边界更正为 **32 FBA（含 5 取消）+ 3 非 FBA 取消 + 28 分析 = 63**；
  敏感性改为「27 个首选不变，部分分值与低位排序变化」（DN-00089 第 3 位由 PO021728→PO021711）。
- **P3#5**：新增 `aliases_raw_all` 保留 DB 原始 `删除` 前缀别名，清洗后别名仍在 `aliases_all`。

产物：`D:/Work/fzh-order-store/analysis/*_v3.csv/json`、`PO_DN候选匹配报告_2026-10-28_v3.md`；
脚本 `scripts/po_dn_candidate_match_v3.py`；测试 `tests/po_dn_match/`（17 passed）。
