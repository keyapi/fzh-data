---
okf: v0.1
type: Log
title: amazon_pairing 变更日志
tags: [amazon_pairing, log]
---

# 变更日志

## 2026-08-14

- **实现**: 新增 Gold/Silver/Quarantine 历史标签审计、普通/皮壳/海绵/套件路由、四家族 TF-IDF + LightGBM LambdaRank 试点、八工作表审核报告和带来源哈希的反馈导入。
- **验证**: 3,557 条在售未配对全部对账；87 条高可信证据、550 条实验候选、434 条特殊对象、2,486 条主动弃权。最终模型 `production_ready=false`，原始 Candidate Recall@20 为 32.25%，禁止自动配对。
- **纠错**: 修复 `red` 命中 `reading`、`in` 被误作 inch、纯 pillow cover 路由以及同 MSKU 多 Listing family 预测覆盖风险。

## 2026-08-11

- **知识沉淀**: 新增根级 conventions 文档，定义 Amazon 在线商品与多平台配对不可混用、快照时效、严格别名到规则/ML 的分阶段候选流程，以及运营确认前禁止写入。
- **新增**: 子项目交接文档，记录 Amazon 在线产品配对与多平台配对两套机制、4,407 在售未配对快照、分阶段方案（别名/规则/ML/运营闭环）与开放问题。
- **新增**: 复用 `missing_products` 的缓存与映射，产出 `Amazon在售未配对分析_*.xlsx` 和 `Amazon配对导入建议_*.xlsx`。
