---
type: Roadmap
title: E 节点账最小实施计划
date: 2026-11-11
---

# E 节点账实施计划

Goal: 生成源数据只读、未知不填零、不可重复消费的 SKU×客户×节点数据层。

Architecture: `e_nodes.py` 负责当前源校验/节点/对账；`e_node_history.py` 负责 DuckDB 历史读取与保留源血缘；`python -m supply_netting.e_nodes` 为 CLI。沿用现有 facts 校验，不改净额引擎。

Tech stack: pandas / pyarrow / openpyxl / duckdb / pytest，`uv run python`。

- [x] Task 1: `supply_netting/tests/test_e_nodes.py` 写契约测试，先 RED（模块不存在），再实现严格节点与 SO 对账、C 视图分离；校验 unknown 和部分额度不冒充已证。
- [x] Task 2: `supply_netting/e_node_history.py` 只读两个指定 DuckDB 表，输出历史证据、源去向/日期/重复冲突统计，断言未来记录不入当前账；新增依赖 duckdb，运行相关测试 GREEN。
- [x] Task 3: `e_node_artifacts.py` 提供 CLI 源哈希、schema、报告/manifest/Parquet，拒绝输出覆盖任何源路径；实际跑指定快照与 SO，逐 stock_key 核 C 原始量与 11,529 视图、3,674 SO；前后哈希不变。
- [x] Task 4: 全模块 153 个测试通过、9 个产物回读与自检、凭证扫描通过；更新 docs index/log 与根索引。只留本地改动，不 push、不写生产。

设计自检：原始库存与 C 视图没有两份计数；SO 汇总不是第二份供应；未证 waiting 方向和无单号 future supply 均阻断；历史不补当前空值；产品/组件/SKU 不做去前缀合并。用户授权设计自洽后直接实施，本轮顺序执行，无外部代理或消息。
