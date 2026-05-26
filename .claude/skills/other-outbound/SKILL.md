---
name: other-outbound
description: >
  赛狐其他出库导入。从赛狐库存明细导出生成其他出库单，清零库存。
  当用户提到"其他出库"、"other_outbound"、"清零库存"、"出库单"、
  "库存清零"、"库存导出"、"出库导入"等时触发。
  不要用于海外仓备货单(warehouse-restock)或期初库存(stock-init)。
compatibility: >
  需要 pandas, openpyxl。从 other_outbound/ 目录运行。
  依赖 数据源/ 下的赛狐库存明细导出 xlsx。
metadata:
  module: other_outbound
  script: build_saihu_other_outbound.py
  updated: 2026-05-26
---

# 赛狐其他出库导入

赛狐库存明细 → 其他出库单（清零现有库存）。

## 快速启动

```bash
cd other_outbound
uv run python build_saihu_other_outbound.py
```

## 管道概要

赛狐库存明细导出 → 过滤非零库存 → 过滤组合商品(-ALL) → 填入出库模板 → 输出。

## 硬约束

- 每次操作前重新导出赛狐库存明细（库存会变化）
- 组合商品(-ALL后缀)不支持其他出库，自动跳过
- 库存明细中的店铺/FNSKU逐行保留，不聚合
- 模板仅 1 行表头（不同于海外仓备货单 2 行）
- 出库后需手动确认出库才能生效

## 输出

3 个文件（CENTRADE/DANEEY/POLAND），每个文件同仓共享一个临时单号。

## 参考

- [给人看的 README](../../other_outbound/README.md)
- [Agent 详细参考](../../other_outbound/AGENT_HANDOFF.md)
