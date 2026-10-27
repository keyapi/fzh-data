---
okf: v0.1
type: Reference
title: 版本化交期配置（A4 接线）
description: 90/75-90/7/60/35/40/春节 60 从硬编码改为读 config/leadtime_config.json，manifest 记版本与来源
tags: [leadtime, config, versioning, so-backlog, so-conditional-supply, asset-reuse]
date: 2026-10-28
status: implemented
---

# 版本化交期配置（A4 接线）

资产复用审计 A4（[asset-reuse-audit-2026-10-28.md](asset-reuse-audit-2026-10-28.md)）：

> 交期分段（90 / 7 / 60 / 35 / 40 / 春节 60）硬编码，未接 sc13 版本化合约。
> 证据：`so_backlog.py:41`、`so_conditional_supply.py:32-34`；`leadtime_config.py` 零 import。

本篇记录接线结果。**只换来源、不改数字**：所有取值与改造前逐一相等，r6/h180 净额、
决策包与已验收产物不受影响（测试 301 通过，含新增 22）。

## 1. 落点

| 角色 | 路径 |
|---|---|
| 数据（唯一事实源） | [`../config/leadtime_config.json`](../config/leadtime_config.json) |
| 加载器 / 校验 | [`../leadtime.py`](../leadtime.py) |
| 消费方 1 | `../so_backlog.py`（导入即加载，模块常量由配置派生） |
| 消费方 2 | `../scripts/so_conditional_supply.py`（按分公司仓取分段） |
| 测试 | [`../tests/test_leadtime.py`](../tests/test_leadtime.py) |

Python 消费（不要另存一份数字）：

```python
from supply_netting.leadtime import load_default_config
cfg = load_default_config()
cfg.so_pipeline.order_to_branch_days        # 90
cfg.spring_festival.buffer_days             # 60（shutdown 30 + recovery 30）
cfg.route_for("波兰-FZHPoland-covers").ocean_days   # 40
cfg.to_manifest()                           # 写进 manifest 的版本/来源留痕
```

## 2. 结构与当前值（版本 `2026-10-28.1`）

```jsonc
{
  "version": "2026-10-28.1",          // 必填；YYYY-MM-DD[.N][-SUFFIX]
  "effective_from": "2026-10-27",     // 必填；口径生效日，只记录不拦截历史 run
  "so_pipeline": {                    // so_backlog：工厂交付日 → 分公司可发货
    "order_to_branch_days": 90,
    "order_to_branch_range_days": [75, 90],
    "stage_eta_assumption_days": 14,
    "source": "assumed", "sample_size": 0, "notes": "..."
  },
  "spring_festival": {                // shutdown + recovery = 缓冲；锚点 ±window 为受影响窗口
    "anchor": "2027-02-06",
    "shutdown_days": 30, "recovery_days": 30, "window_days": 30,
    "source": "assumed", "sample_size": 0, "notes": "..."
  },
  "routes": [                         // 按分公司仓（= canonical warehouse 同名）取值
    {"route_id": "CN->US-EAST", "warehouse": "美东-CENTRADE", "mode": "slow_boat",
     "segments": {"production": 60, "shipping": 7, "ocean": 35},
     "source": "assumed", "sample_size": 0, "notes": "..."}
    // 美中-FZH-DANEEY：同 60/7/35；波兰-FZHPoland-covers：60/7/40
  ]
}
```

`source` 允许 `measured | assumed | business`；`source=measured` 时 `sample_size` 必须 > 0。

## 3. 与 sc13 合约的关系

字段与规则取自 sc13（`docs/research/supply-chain/2026-10-20/claude/experiments/sc13/
leadtime_config.py`）：版本、生效日、分段、source/sample_size/owner/notes、缺字段即报错、
未知字段只 warning、重复 profile 报歧义。

**改的是分段词表**：sc13 的三段是 `order_to_departure / departure_to_arrival /
arrival_to_stock`，同一 `(route, warehouse, mode)` 只允许一条。我们两个消费方起点不同 ——
「完工待发运」从审计日起算 7+海运，「在产」是 60+7+海运 —— 同一路线上是两条不同前段，
硬套 sc13 三段会撞成重复 profile。因此分段用 `production / shipping / ocean`，由消费方
按阶段取舍。对应关系：`order_to_departure ≈ production + shipping`、
`departure_to_arrival ≈ ocean`、`arrival_to_stock = 0`（已并入海运，未单列）。

`effective_from` 只记录进 manifest：本层按审计日**向前**推日期，不存在 sc13 那条
「拿新口径回算历史下单日」的路径，故不实现 `ConfigNotEffective`。

## 4. 失败语义（缺文件/缺字段一律失败）

- 配置文件不存在 → `ConfigNotFound`（**没有**内置默认天数、没有环境变量回退）。
- 必填字段缺失/类型非法 → `ConfigSchemaError`，`.field` 给精确路径（如
  `routes[0].segments.ocean`）。
- `measured` 却 `sample_size=0` → 报错；版本格式非法或与 `expected_version` 不符报错。
- 同一 `(route_id, warehouse, mode)` 重复 → 报错；同一 warehouse 多条 mode 且未指定 mode →
  `ConfigAmbiguous`；查不到 warehouse → `UnknownRoute`（不猜天数）。
- `so_backlog` / `so_conditional_supply` **导入即加载**：配置坏了，引用这两个模块的代码
  立刻失败（测试 `test_consumer_import_fails_without_config` 覆盖）。

## 5. 留痕

- 配置块（`LeadTimeConfig.to_manifest()`）含 `config`（仓库相对路径）、`version`、
  **`sha256`**、`effective_from`、`sources`、每条路线的分段与 `sample_size`。
  `sha256` 按加载时读到的**同一份字节**计算：加载后文件再被改，留痕仍指被解析的那份。
- `so_backlog.summarize_backlog()` 新增 `leadtime_config`（→ `pack_manifest.json` 的
  `so_backlog` 段）。
- `so_conditional_supply` manifest：新增 `leadtime_config` 同结构；`rules` 的
  `ship_days / production_days / sea_days / spring_buffer_days` 也改为从配置派生
  （`shared_days()` 在各路线不一致时直接报错，不擅自压成单值）。
- `scripts/so_conditional_supply_v3.py` manifest：同样新增 `leadtime_config`
  （v3 的日期由 `plan_dates()` 提供，与 v2 共用同一份配置）。
- 每行 ETA 的 `eta_basis` 文本带配置版本号，例如
  `审计日+生产60天+发运7天+海运40天（assumed；交期配置 2026-10-28.1）`。
- 对账方式：产物 manifest 的 `leadtime_config.version` + `sha256` 就是这批数字用的口径；
  哈希对不上说明配置被改过（哪怕版本号没动）。

## 6. 怎么改口径

改数字 = 改配置，不是改代码：

1. 编辑 `config/leadtime_config.json`，**同时把 `version` 提升**（如 `2026-10-28.2`）。
2. 若某条假设变成实测：`source` 改 `measured` 并填 `sample_size`（否则加载失败）。
3. 跑 `uv run python -m pytest supply_netting/tests -q`；
   若默认值变化，`test_leadtime.py::FrozenValuesTests` 会失败 —— 那是**预期**的，需同步
   更新该测试的期望值并在本文件记录新版本。
4. 下游 manifest 里的 `leadtime_config.version` 就是本次产物用的口径版本，可直接对账。

## 7. 仍未接线（本次刻意不做）

- `sc13` 模块本身仍在 `docs/research/` 下（研究目录，不是包），未 import；本模块按合约
  语义自实现，未复制其代码。
- v3 的 manifest 已补 `leadtime_config`，但**既有 v3 产物目录不重跑**：其 manifest 里的
  版本/哈希要等下一次正常出包才出现（本次只改代码，未重算日期与候选量）。
- A1/A2/A3（base-stock 回放、sc08 共形校准、正态 CV）与 A5（缓冲公式两份）按审计建议
  留待后续任务，本次不动。
- 90 与「在产 60+7+35=102」两条路径口径本身不一致，本次**只做来源版本化**，不调和数字。
