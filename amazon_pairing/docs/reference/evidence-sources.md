---
okf: v0.1
type: Reference
title: Amazon 配对证据源
tags: [amazon_pairing, evidence]
timestamp: 2026-08-14
---

# 证据源

机器可读副本：[`../../knowledge/evidence-sources.yaml`](../../knowledge/evidence-sources.yaml)。

活证据优先级（冲突则降级审核，不静默丢）：

1. 同 MSKU 当前已配对（跨店跨站，含 Silver，不要求 Gold A）
2. 同 ASIN 当前已配对（默认跨站）
3. parentSku / parentAsin 家族（唯一才升高可信；多个则进智能候选）
4. 近邻 MSKU（去 `-FBA`/`-us`/`-2`）
5. EN 客户物料号（去 `NB/` 前缀、去尾缀）
6. 通途主 SKU/别名精确命中
7. 颜色/面料 + 美国床型/英寸/近寸
8. 同 `mainImage` URL
9. 图片哈希 / VL / LLM：剩余难例，默认不进高可信

Gold A 只用于训练清洗，**不是**高可信门槛。
