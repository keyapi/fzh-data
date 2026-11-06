---
type: Reference
title: 交期四段与 pre-haul 变量（默认 0）
date: 2026-11-06
---

# 交期四段与 pre-haul 变量

当前模型把交期拆为：

1. 生产 SO→DN（按池，已有）
2. **DN→头程物流商仓/开船（pre-haul）**
3. 头程仓→目的仓（按区域×方式，已有 ZMT 样本）
4. 目的仓入仓/上架（如未包含，另加 1–2 天）

## pre-haul 变量

暂不纳入当前计算，先默认 0 天；后续可直接改：

| 变量 | 默认 | 含义 |
|---|---:|---|
| `prehaul_days` | 0 | DN 出库 → 头程物流商仓/开船的固定天数 |
| `prehaul_pool_adj` | {} | 按池/分公司调整，如 USNJ/USTX/PL |
| `prehaul_port_adj` | {} | 按发货港口调整（宁波/上海/义乌等） |
| `prehaul_distance_days` | 0 | 与绍兴距离相关的附加天数 |
| `prehaul_scenario` | "default_zero" | 0 天情景标签；实测后改 measured |

规则：在没有逐票 DN↔Shipment 实测前，**默认 0，不偷偷塞进 55/30/14**；一旦填入变量，总交期 = 生产 + prehaul + 头程仓→目的仓 + 入仓上架。

## 已有实测（仅记录，不进入当前计算）

用 Jack 的 `shipment_segments_fixed.csv`（`dn` 关联）计算 DN→开船：

| 池/客户 | 样本 | p50 | p90 |
|---|---:|---:|---:|
| 美东 CENTRADE | 3 | 9 | 23.4 |
| 美中 DANEEY | 6 | 9 | 19.5 |
| 波兰 | 2 | 13 | 13.8 |
| 美国 FBA 仓 | 15 | 13 | 22.8 |

样本仍少；后续用全量 DN↔Shipment 统计后再替换默认 0。
