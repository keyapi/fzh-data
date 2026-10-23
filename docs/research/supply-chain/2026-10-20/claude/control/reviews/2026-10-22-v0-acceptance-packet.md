---
okf: v0.1
type: Reference
title: G2+G3 V0 验收包（provisional）
date: 2026-10-22
stage: V0 provisional
---

阶段：G2+G3 窄范围 V0（2 SKU 样例 + 10 SKU 报告）
产物：
- control/reviews/2026-10-22-sample-2sku.md
- control/reviews/2026-10-22-supply-demand-replenishment-v0.md
- experiments/g2g3_pilot/build_v0.py
- experiments/g2g3_pilot/out/sample_2sku.json
- out/replenishment_v0/evidence.json

固定版本：7c1102d4
证据哈希：
- evidence.json 383a9a26…
- sample_2sku.json f3e28803…
- 数据只读；0 次生产访问；未下单/未扩样。

缺数影响：
- ETA 全空；在产无日期；死单/超发；UOM unknown；Cover 未并入；断货删失未校正。
- 用 A/B 情景与 unknown 分列，不合成精确采购量。

下一任务：Codex1 审核计算与证据 → 分级问题 → 修正或生成 10 SKU 补货行动清单。
负责人：Claude worker / Codex1 / Codex2。
截止：完成即流转；时间仅作超时告警。
