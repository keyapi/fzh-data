---
okf: v0.1
type: Log
title: architecture-patterns — 变更日志
tags: [solutions, architecture-patterns, log]
---

# architecture-patterns 变更日志

## 2026-11-02

- **新增**: `demand-forecast-layer-d.md` —— D 的四状态（decision/demand/forecast/netting）、政策与数据缺口分离、CG 销量入分公司、统一 4 年订单历史、删失/短史/模型选择边界。

## 2026-10-30

- **新增**: `supply-chain-a-b-c-data-pipeline.md` —— A 活跃宇宙 / B 市场归属 / C 库存归并 / join 的边界与不变量；记录库存仓作投放证据、DN 看时间段、套件拆 Product Bundle、拆包成品 min(Cover,Foam)、CG 只取汇总行、`join_full/partial/no_join` 三态。

## 2026-09-22

- **新增**: `public-private-agent-knowledge-split.md` — 公开仓、私有 Markdown 知识仓与 secret manager 三层分离；普通 clone + bootstrap 代替 submodule，保留 Agent 检索和非技术同事使用体验。
