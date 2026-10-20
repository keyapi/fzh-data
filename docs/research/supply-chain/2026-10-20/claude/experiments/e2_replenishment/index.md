---
okf: v0.1
type: Index
title: E2 补货分配优化
description: 8 SKU × 12 个月 CP-SAT 补货分配，对比业务 6 个月覆盖公式；B=257/180 与 ±25% 需求敏感性，含回读校验。
date: 2026-10-20
tags: [supply-chain, replenishment, ortools, cp-sat]
---

# E2 补货分配优化

> 切片：本地补货决策信息包（2026-10-16）中的 8 个楔形枕 SKU；只读，不写业务系统。

## 结论

- 求解全部 `OPTIMAL`，最长约 0.04 秒；预算与 MOQ 约束满足；目标与独立仿真 6/6 一致。
- B=180 下总缺货 394.8，与启发式完全相同；服务时点改善（前 3 月缺货 7.5 → 0），持有 −1.1%。
- 固定预算下总缺货由 `541 − Q + 期末库存` 锁死；业务公式就是 6 个月覆盖下限。
- 判定：**部分通过**；优化器暂不足以替代业务规则，但可作约束检查与诊断工具。

## 文件

| 文件 | 用途 |
|---|---|
| [README.md](README.md) | 一段式复现说明 |
| [results.md](results.md) | 方法、逐 SKU 结果、敏感性、判定、限制 |
| [solve.py](solve.py) | CP-SAT 模型 + 独立仿真 + 敏感性入口 |
| [data/input.json](data/input.json) | 8 个 SKU 的提取输入与假设 |
| [data/results.json](data/results.json) | 全部数值结果 |

## 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/e2_replenishment/solve.py
```
