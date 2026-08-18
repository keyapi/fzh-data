---
okf: v0.1
type: Handoff
title: Amazon 在售未配对智能审核 — 子项目交接
tags: [amazon, pairing, evidence-graph, sellfox, tongtu, erpnext]
timestamp: 2026-08-14
---

# Amazon 在售未配对智能审核

> 本模块为赛狐 Amazon 在售未配对 Listing 生成只读证据图审核工作簿，不调用赛狐配对写接口。

## 当前结论

- V2 当前快照：3,557 条在售未配对。
- 强证据建议 254、Top 候选审核 779、低证据候选 2,449、冲突 2、对象专项 73、无候选 0。
- `模型可生产使用=false`；仅辅助人工审核，不自动配对。
- 严格回放 2,000 条已配对样本，排除同 ASIN/MSKU 直接命中后：候选召回 46.85%，Top-1 19.8%，Top-3 29.95%。
- 带同 ASIN/MSKU 历史命中时 Top-1 约 88%，因此高质量历史证据仍然最有价值。

## 主要入口

| 命令 | 作用 |
| --- | --- |
| `python -m amazon_pairing.cli build-labels` | 审计历史已配对，生成 Gold/Silver/Quarantine |
| `python -m amazon_pairing.cli snapshot-catalog` | 拉取 EN/赛狐候选 catalog |
| `python -m amazon_pairing.cli train-family` | 训练全家族 `family_classifier_all.joblib` |
| `python -m amazon_pairing.cli suggest-v2` | 生成证据图 V2 工作簿 |
| `python -m amazon_pairing.cli import-feedback <xlsx>` | 校验并追加人工反馈 |

默认数据在 `amazon_pairing/out/`，业务文件不提交 Git。

## V2 证据链

- 强证据：同 MSKU、同店铺 ASIN、同 ASIN、FNSKU。
- 候选证据：父 ASIN、父 SKU、主图 URL、标题规范化、MSKU 字符 TF-IDF affinity、全家族 family 检索。
- 对象本体区分成品、皮壳、海绵、套件；`with removable cover` 不当作独立皮壳。
- 属性解析同时读取标题和 MSKU 驼峰/连字符信号，用于加分，不用于无谓硬冲突。

## 安全边界

- 不调用 `matchByMsku`、`matchByAsin` 或组合商品写接口。
- 通途 ERP2 共享 5 次/分钟，批量查询必须缓存。
- 低证据候选不能自动升级为导入建议。
- 新任务先读 [Amazon 在线商品配对流程](../docs/solutions/conventions/amazon-online-product-pairing-candidate-workflow.md)。
