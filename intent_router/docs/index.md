---
okf: v0.1
type: Index
title: intent_router — 文档索引
description: 中文意图 → 本仓库模块路由模块的文档入口
tags: [intent-router, typesafe, jev, routing, index]
---
# intent_router — 文档索引

> 渐进式加载。接手时先读 [`../AGENT_HANDOFF.md`](../AGENT_HANDOFF.md)（Agent 入口），
> 需要细节再按下面索引深入。

## 快速导航

| 你需要... | 读这个 |
|----------|--------|
| 快速了解模块 + 开始工作 | [`../AGENT_HANDOFF.md`](../AGENT_HANDOFF.md) |
| 了解怎么跑、三态输出、退出码 | [`../README.md`](../README.md) |
| 查 System One 请求/响应契约与本仓库用法 | [reference/typesafe-contract.md](reference/typesafe-contract.md) |
| 查变更历史 | [log.md](log.md) |
| 改 catalog（新增/删除模块） | [reference/typesafe-contract.md](reference/typesafe-contract.md#目录真源与防漂移) |
| 看运行时目录真源 | [`../catalog.yaml`](../catalog.yaml) |

## 目录结构

```
intent_router/                          ← 中文意图 → 模块路由
├── AGENT_HANDOFF.md                    ← Agent 入口
├── README.md                           ← 人读
├── __init__.py
├── cli.py                              ← argparse 入口；三态渲染；退出码
├── router.py                           ← 编排：build → POST → parse → gate
├── typesafe.py                         ← 纯函数：payload / parse / normalize / gate
├── catalog.py                          ← 读 catalog.yaml + 解析 AGENTS.md 防漂移
├── catalog.yaml                        ← ★运行时目录真源
├── env.py                              ← .env 有界上溯加载
├── docs/                               ← OKF v0.1 bundle
│   ├── index.md                        ← 你在这里
│   ├── log.md                          ← 变更历史
│   └── reference/
│       ├── index.md
│       └── typesafe-contract.md        ← System One 契约
└── tests/
    ├── test_typesafe.py                ← 纯函数
    ├── test_router.py                  ← HTTP 边界打桩
    ├── test_catalog.py                 ← 与 AGENTS.md 防漂移
    ├── test_env.py                     ← .env 上溯
    ├── test_cli.py                     ← 三态 + 退出码
    └── test_live_typesafe.py           ← opt-in 真实调用
```

## 设计原则

- **只分类，不执行**：本模块给出模块名，业务动作交回对应模块自己的流程。
- **code 拥有 dispatch**：模型只给概率分布，阈值判断与三态闸门在代码里。
- **不冒充 dispatch.py**：通用退出码复用，但状态词表独立（见 README「退出码」一节）。
- **单一真源 + 防漂移测试**：`catalog.yaml` 是运行时真源，集合相等由测试守住。
