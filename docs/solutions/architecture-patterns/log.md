---
okf: v0.1
type: Log
title: architecture-patterns — 变更日志
tags: [solutions, architecture-patterns, log]
---

# architecture-patterns 变更日志

## 2026-11-03

- **新增**: `us-owner-restatement-and-b2-scope.md` —— 美国需求按当前 owner 重述（1,853→1,749）、A/B/C 三方案与 B2 品类范围；84,343 件/181 产品迁移、53 特例、31,033 件 US_unassigned 不猜。
- **新增**: `end-to-end-supply-chain-strategy-s1-s2.md` —— S1 节点时间线与 S2 联合蒙特卡洛；普船/快船/空运三分类、例外队列优先、Q95 分位≠全程 95% 服务（332 候选仅 154 达标）、S2.8 分层决策包。

## 2026-11-02

- **新增**: `demand-forecast-layer-d.md` —— D 的四状态（decision/demand/forecast/netting）、政策与数据缺口分离、CG 销量入分公司、统一 4 年订单历史、删失/短史/模型选择边界。

## 2026-10-30

- **新增**: `supply-chain-a-b-c-data-pipeline.md` —— A 活跃宇宙 / B 市场归属 / C 库存归并 / join 的边界与不变量；记录库存仓作投放证据、DN 看时间段、套件拆 Product Bundle、拆包成品 min(Cover,Foam)、CG 只取汇总行、`join_full/partial/no_join` 三态。

## 2026-09-22

- **新增**: `public-private-agent-knowledge-split.md` — 公开仓、私有 Markdown 知识仓与 secret manager 三层分离；普通 clone + bootstrap 代替 submodule，保留 Agent 检索和非技术同事使用体验。
