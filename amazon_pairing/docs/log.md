---
okf: v0.1
type: Log
title: amazon_pairing 变更日志
tags: [amazon_pairing, log]
---

# 变更日志

## 2026-08-11

- **知识沉淀**: 新增根级 conventions 文档，定义 Amazon 在线商品与多平台配对不可混用、快照时效、严格别名到规则/ML 的分阶段候选流程，以及运营确认前禁止写入。
- **新增**: 子项目交接文档，记录 Amazon 在线产品配对与多平台配对两套机制、4,407 在售未配对快照、分阶段方案（别名/规则/ML/运营闭环）与开放问题。
- **新增**: 复用 `missing_products` 的缓存与映射，产出 `Amazon在售未配对分析_*.xlsx` 和 `Amazon配对导入建议_*.xlsx`。
