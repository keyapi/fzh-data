---
okf: v0.1
type: Reference
title: 通途特殊规则换表：参考值优先、FBA 列对齐与旧/新 BOM 口径差
date: 2026-11-11
category: workflow-issues
module: tongtool_order_cost
problem_type: workflow_issue
component: tooling
severity: high
applies_when:
  - "特殊规则表换维护人/换 ws（旧 Jeck ws → 新 黄-特殊规则 ws）"
  - "同一行同时有系数和参考值，需要决定谁优先"
  - "FBA 成本列口径从旧二次加工改为二次=0、绍兴二次承接"
  - "旧 BOM 制定的参考值遇到最新 BOM，扣减可能翻成增加"
  - "跑 1.7.0 前需要判断参考值是否与当前成本匹配"
tags: [tongtool, special-rule, reference-value, bom-caliber, fba, google-sheet]
related_components: [tongtool_api, EN_API]
---

# 通途特殊规则换表：参考值优先、FBA 列对齐与旧/新 BOM 口径差

## Context

2026-11 前任维护人离职，老板给了新特殊规则表 `黄已填 google表 和财务部共享 Jeck特殊规则-订单改销售额成本 20261109.xlsx`。新 ws `黄-特殊规则-订单改销售额成本` 成为 1.7.0 输入；旧 ws `Jeck特殊规则-订单改销售额成本` 只读留存。

新表 873 行、678 个 SKU；其中 13 行同时有系数和参考值。老板 2026-11-10 明确：**参考值和系数同时出现，优先参考值**。同一时期成本口径也变了：

- 皮壳 = BOM `cost_fg`；
- 绍兴二次 = 皮壳 0 / 半成品 `cost_sxbzbcp` / 成品 `cost_sxbzcp` / FBA `cost_sxbzcp`；
- 二次加工 = 目的地 valuation；FBA=0；
- 头程按 BOM method 取皮壳/半成品/成品。

旧 9/3 BOM 与最新 BOM 差异明显：阅读枕旧皮壳 76.96、二次 206.48，现皮壳 53.94、绍兴 16.52、二次 90.31、头程 33.15。参考值是按旧 BOM 定的，遇到新 BOM 会把扣减翻成增加。

## Guidance

1. **新 ws 是唯一输入，旧 ws 只读。** 不要修改旧 Jeck ws，也不要把新 ws 的 13 行系数重新填回。
2. **参考值优先。** 引擎 `get_rule_mode` 先判 ref；同时有系数/参考值时打印 `⚠️ ... 按参考值优先，忽略系数`，并在 `meta["n_mixed_ref_priority"]` 计数；Colab cell 22 同步。不要整行跳过。
3. **FBA 列对齐。** 28 条 FBA 规则的参考值原本写在 `二次加工`；新口径 FBA 二次=0，绍兴包装进 `绍兴二次`。已把 `二次` 与 `绍兴` 参考值对调，数值不变、总净额不变，只修正科目归属。
4. **旧/新 BOM 口径差要先对拍，再决定是否重填。** 参考值可能是按旧 BOM 定的；用最新 GS 订单表逐条算 `(参考值×汇率 − 当前成本) × 数量`，把结果分成“抬高 / 扣减 / 未命中”。202609 扫描：14 条抬高 +13,206.75，47 条扣减 −33,278.88，净 −20,072.13。
5. **老板决定按现有参考值执行时，不要自行重填。** 2026-11-10 老板确认“全部按照现在表格里的参考值计算”。阅读枕第 776–777 行 +10,055.94、FBA 153/138/194 +3,150.81 都是在这个决定下接受的；要改必须再确认。
6. **报告时写 Excel 行号。** 规则表第 1 行是表头，数据从第 2 行起；说“第 776–777 行”而不是只写 SKU，避免和订单行号混淆。
7. **钉钉单聊读回复用 DWS。** `dws chat +chat-messages --open-dingtalk-id <id> --start ... --end ... --order asc --page-all`；只用结论，不在文档里写 openDingTalkId/手机号/个人聊天标识。

## Why This Matters

特殊规则直接改订单成本/利润。旧 BOM 参考值遇到新 BOM 时，同一组数可能从“扣减”静默翻成“增加”：阅读枕 −77.8 → +20.2 元/件，9 月 +1.0 万；FBA 153/138 也从扣减翻成小额增加。FBA 的 `二次/绍兴` 放反则会把成本记到错误科目，虽然总额可能接近，但按科目分析会失真。参考值优先是老板的明确口径，不能再按旧的“混合即跳过”处理。

## When to Apply

- 特殊规则表换维护人/换 ws；
- 同一行同时有系数和参考值；
- FBA 成本口径调整（二次=0、绍兴承接）；
- BOM 成本更新后，参考值可能过时；
- 跑 1.7.0 月度核算前，或某条参考值规则从扣减变增加时。

## Examples

阅读枕（第 776–777 行，USTX，2026-09）：

| 科目 | 9/3 旧 BOM | 最新成本 | 参考值 |
|---|---:|---:|---:|
| 皮壳 | 76.96 | 53.94 | 71.34 |
| 绍兴二次 | 0 | 16.52 | 0 |
| 二次加工 | 206.48 | 90.31 | 116.22 |
| 头程 | 8.5 | 33.15 | 26.58 |
| 净/件 | −77.80 | +20.22 | — |

FBA 153（第 677/680/685/688/691 行）：旧 BOM 净 −15.56/件，最新成本 +3.94/件；FBA 138（第 664/666/668/671/674 行）：旧 −19.93 → 现 +1.42。FoamFBA 194（第 717/718 行）在 9/3 旧 BOM 下已是 +30.60/件，最新 +47.58，属于规则本身的问题，不是换 BOM 翻出来的。

对拍方式：读最新 GS 月度写回表 → `build_order_filter` 匹配规则 → 对每个参考值列算 `(ref_usd × fx − 当前 unit_cost) × 发货数量` → 汇总每行规则的净 Δ；结果落 `tongtool_order_cost/out/ref_scan_202609_latest.csv`（gitignore）。

## Related

- [tongtool_order_cost/AGENT_HANDOFF.md](../../../tongtool_order_cost/AGENT_HANDOFF.md)
- [.agents/skills/tongtool-order-cost/SKILL.md](../../../.agents/skills/tongtool-order-cost/SKILL.md)
- [通途主档 SKU 改名后用本地 gspread 对齐订单 Google Sheet](tongtool-sku-rename-gsheet-remap.md)
- [CONCEPTS.md](../../../CONCEPTS.md) — 特殊规则 / 参考值优先定义
