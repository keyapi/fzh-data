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
uv run python g1_cover_matching.py
```

> **口径更正**：`mapping_process.md` 是待确认的正确匹配过程；`g1_cover_matching.py`
> 只用 BOM 客户码精确匹配，不用品类文本。G1a v1 的品类筛选口径已作废。

输入（只读，不入库）：

- `D:/Work/王忠于/成本核算/EN产品BOM成本列表20261016.xlsx`
- `D:/Work/王忠于/成本核算/2026年{4..9}月订单_order_cost_*.xlsx`（每月取最新时间戳）

输出：

- `out/mapping_coverage.json`：BOM 索引统计、两仓完成品口径、全仓对照、月度、仓库/渠道/族拆分、未匹配前缀。
- `out/missing_analysis.json`：763 vs 155 归因、尾缀/平台SKU 可救、P2 非 family 映射、仍缺失样本。
- 聚合计数，不含客户姓名/地址/电话/邮箱/原始行。

边界：不访问 EN 生产、不写业务系统；未匹配不静默丢弃。

## G1b — 库存快照 / EN 单据 / 覆盖

```bash
# 1) 两仓 + 皮壳仓 family 库存快照（通途只读；5 次/分钟限流，脚本 13s 节流）
uv run python g1b_stock_snapshot.py \
  --warehouses "美东-CENTRADE,美中-FZH-DANEEY,美中-FZH-DANEEY-皮壳仓库" \
  --chunk-size 100 --min-interval 13 \
  --out out/stock_snapshot_YYYYMMDD.json

# 2) 单个客户码 / 物料的 EN 单据结构化导出（生产只读）
uv run python g1b_en_extract.py --customer-code "C/Linen-Natural-194-688-wow" \
  --out out/g1b_en_<code>.json

# 3) 出库消耗 vs 库存覆盖
uv run python g1b_coverage.py --stock out/stock_snapshot_YYYYMMDD.json \
  --out out/g1b_coverage_YYYYMMDD.json
```

输入与凭证：

- 通途凭证默认读 `D:/Work/赛狐/Cursor/tongtool_api/.env`（worktree 里没有 `.env`）；
  可用 `TONGTOOL_ENV_FILE` 或 `--env-file` 覆盖。
- EN 生产凭证走 `EN_API/item_shipment_status.py` 的候选 `.env`（worktree → 主仓库）。
- 全部只读；不写 EN 生产库存账。

注意：

- 通途库存查询按仓库 + `skus` 分块；`pageSize` 上限 100，5 次/分钟。
- EN SO 行可能用 `PK#`/`ND#` 包装码；用 `--customer-code` 或先做 `KS → PK#` 映射。
- `g1b_en_extract.py` 输出不含客户名/地址等 PII；原始控制台输出仅本地。
- `g1b_coverage.py` 的覆盖月数是历史 run-rate，不是预测；美中受新运营 ramp 影响。
