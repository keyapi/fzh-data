---
okf: v0.1
type: Reference
title: G1a 本地映射覆盖率 — 复现说明
description: 输入文件、命令、输出与脱敏边界
date: 2026-10-20
tags: [supply-chain, g1, mapping, readme]
---

# G1a — 复现

```bash
cd docs/research/supply-chain/2026-10-20/claude/experiments/g1_contract
uv run python g1_mapping_coverage.py
uv run python g1_missing_analysis.py
```

输入（只读，不入库）：

- `D:/Work/王忠于/成本核算/EN产品BOM成本列表20261016.xlsx`
- `D:/Work/王忠于/成本核算/2026年{4..9}月订单_order_cost_*.xlsx`（每月取最新时间戳）

输出：

- `out/mapping_coverage.json`：BOM 索引统计、两仓完成品口径、全仓对照、月度、仓库/渠道/族拆分、未匹配前缀。
- `out/missing_analysis.json`：763 vs 155 归因、尾缀/平台SKU 可救、P2 非 family 映射、仍缺失样本。
- 聚合计数，不含客户姓名/地址/电话/邮箱/原始行。

边界：不访问 EN 生产、不写业务系统；未匹配不静默丢弃。
