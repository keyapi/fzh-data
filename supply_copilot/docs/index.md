---
okf: v0.1
type: Index
title: Supply Copilot — 文档索引
description: 只读回放与整分公司刷新快照的渐进式加载入口
tags: [supply-copilot, supply, index]
---
# Supply Copilot — 文档索引

> Agent 接手先读 [`../README.md`](../README.md)（用法）和本页；需要口径细节再进
> [`refresh-batch.md`](refresh-batch.md)。

## 快速导航

| 你需要… | 读这个 |
|---------|--------|
| 跑命令 / 拉数据包 | [`../README.md`](../README.md) |
| 期间语义、W1 SO 去重、report 字段、验收口径 | [refresh-batch.md](refresh-batch.md) |
| 变更记录 | [log.md](log.md) |
| 单 SKU 历史回放（legacy） | [`../recommend.py`](../recommend.py) · [`../refresh.py`](../refresh.py) |
| 整分公司刷新（新） | [`../batch.py`](../batch.py) · [`../period.py`](../period.py) · [`../so_stage.py`](../so_stage.py) |

## 模块边界

- 只读：不写 EN、不写业务系统；网络只有 EN 实时库存 GET（或用 `--live-snapshot` 离线文件）。
- `refresh` 分两条路：无 `--out` 的 `--sku` 是历史单 SKU 探索口径（保留兼容）；
  给 `--out` 才走批量快照 + `report.json` 的审计口径。
- 客户数据在 EN 私有包（`FZH_DATA_ROOT`），仓库只放代码。
