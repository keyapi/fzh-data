---
okf: v0.1
type: Review
title: R290 五例独立对账（冻结包 67f73c5）
date: 2026-10-21
reviewer: codex
verdict: accept3-scenario1-blocker1
---

结论：**原型尚未完成业务对账**。5＝已接收5＋待交付0；accept 3、scenario 1、blocker 1。accept仅指冻结数值一致。

下表缩写均对应唯一完整SKU；供给＝available＋max(intransit,PO)。

| 五例 | 日均/ROP | 供给构成 | 判定与标记 |
|---|---:|---|---|
| KS0001 深灰100 | 3.276/246 | 0＋max(0,0)＝0 | accept；含Cover假设；flags="" |
| KS0230 白60 | 1.8/135 | 0＋max(0,0)＝0 | accept；不含Cover；defects=113排除 |
| KS0153 白卡其78 | 0.459/34 | 2＋max(0,0)＝2 | accept；含Cover假设；flags="" |
| KS0316 紫条55 | 0.129/10 | Cover库存28排除，供给0 | scenario；pool_note=cover_only |
| KS0249 绮若153 | 0.081/6 | 2＋max(0,0)＝2 | blocker；导出仓名错误；bom_inner_disabled |

五例均无在途/PO重叠、对应仓PO为空；日均与需求表一致，ROP＝round(日均×75)。KS0249按正确“美东-CENTRADE”只读补查后数值吻合。

有效冻结为corrected **67f73c5**；ae6a6793是旧声明。scripts仅nd_button_gap_report.py改说明、reason/action文本，未改预测算法；脚本哈希考虑换行格式后吻合。

两差异已解释：16,043＝重叠173行15,567＋另7行476；13,125＝重叠13,118＋无PO的7行各1。原文误将子集合写成全量。

全局max去重仍是scenario；248条未结PO的will_arrive_date全NULL，聚合表无ETA字段，属blocker。Cover同池未证；KS0316的PO10在波兰，不能放入美中。需求/库存无UOM，BOM有UOM，跨品类一致性未证。

最小修复及复核：统一版本、仓名和统计范围；重导五例并逐仓吻合；补逐笔重叠、ETA、Cover替代及单位换算证据后再验收。
