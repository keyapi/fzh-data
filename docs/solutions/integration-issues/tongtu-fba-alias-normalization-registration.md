---
okf: v0.1
type: Reference
title: FBA SKU 别名归一化、KS0001 优先与 EN 客户物料号登记
date: 2026-11-05
category: integration-issues
module: tongtool_order_cost
problem_type: integration_issue
component: tooling
severity: medium
symptoms:
  - "FBA 销量报表 SKU 在 EN 找不到客户物料号，成本覆盖率卡在 90%"
  - "别名大小写/空格/连字符不同，或同一款分 KS0001 与无扣 KS0248"
  - "BOM 报表排除 disabled 物料，历史订单缺行"
root_cause: "customer_code 是逗号分隔别名文本，未做归一化；同款有无扣两个系列；BOM 报表默认排除停用物料"
resolution_type: fix
tags: [fba, alias, customer-code, ks0001, disabled-bom, product-bundle]
---

# FBA SKU 别名归一化、KS0001 优先与 EN 客户物料号登记

## Problem

通途 FBA 销量报表（按 MSKU/SKU 汇总）里有一批 SKU 在 EN `Item.customer_code` 未登记，导致成本无法定价；部分 SKU 与已登记别名只差大小写、空格或连字符（如 `SUK-SJWKDM-GREY45CM` vs `SUK-SJWKDM-grey 45cm`）。

## Symptoms

- FBA priced 覆盖率停在 91.3%/91.8%，缺口 33 SKU / 287 件。
- 同款"有扣/无扣"两个系列（KS0001 vs KS0248）候选同时命中，自动映射会错。
- BOM Cost List 最新表默认过滤 disabled，33 个历史物料缺行；实际这些物料有 BOM，只是停用。

## Solution

1. **别名归一化**：去掉空格、连字符、下划线并大写后比较；先匹配已登记别名，再做候选启发式（尺寸+面料+颜色）。
2. **同款只差有无扣优先 KS0001**：若 KS0001 对应存在，目标改 KS0001（更全）；不要泛化到其它差异。
3. **单候选强依据才自动**：`candidate_count==1` 且依据同时命中尺寸+面料+颜色才自动（`auto_pref=single_candidate`）；弱依据仍待审。
4. **BOM 快照 include disabled**：历史订单可能引用停用物料；用 `show_disabled=1` 冻结 2,358 行，33/33 缺行补齐，并标记 `disabled_source`。
5. **套件**：Product Bundle 子件 method 全一致才派生 `kit_method`；混合/空 → 待审；订单只有 TJ# 时子件不另计。
6. **登记流程（权威源是子表，不是文本字段）**：先 dry-run → 在 `tabItem Customer Detail`（页面「客户物料」子表）追加 `ref_code` + `customer_group`，旧值/行数/hash 备份 → 写入 → 回读子表 → `clear-cache`。**不要只改 `Item.customer_code` 文本字段**：页面不显示、引擎若读文本会误判"未登记"（本次踩过：33 条先写错字段，后补子表）。
7. **特殊借成本**：无白色物料时，先将别名挂到象牙白（同组/同面料/同尺寸），标 `cost_borrow_white→ivory`，成本借用、语义可回滚。

## Why This Works

- 子表 `Item Customer Detail.ref_code` 才是页面与 EN 映射的权威源；`Item.customer_code` 只是汇总文本，不能单独作为登记依据。
- 归一化把"同一 SKU 的多种写法"合并，避免无谓登记；KS0001 优先符合业务"更全"的口径。
- 只在强依据/已登记别名时自动，其余待审，防误映射。
- disabled 快照保证历史可复现；BOM 仍是成本主源，不用存储行字段。

## Prevention

- 每次 FBA 登记保留 proposals/旧值/hash/回读结果；别名重复检测（归一化）后再写。
- 自动映射必须记录候选集、命中字段/层级、版本；假唯一（候选集不完整）要降级待审。
- 套件 method、BOM 版本、白名单 hash 写入 manifest，canary/写回前校验。

## Related

- `docs/solutions/workflow-issues/tongtu-order-universe-invalid-split-fba.md`
- `docs/reference/cost-engine-spec/35-phase4-fba-shadow.md`
- `tongtool_order_cost/tongtu_cost_engine/domain/fba_shadow.py`
