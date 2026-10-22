# EN SO 关联覆盖与政策时间线

> 只读 GET；预算 ≤200 次、page_length ≤100、间隔 ≥200ms；超时/5xx 即停。
> 全量/样本在每张表注明；不解释字段业务含义、不写下单建议。

## 1. 预算

- 请求 **98** 次 / 上限 200；耗时 **19.6 s**；停止：无（正常完成）
- 按路径：{'/api/resource/Custom Field': 1, '/api/resource/Sales Order': 6, '/api/resource/Sales Order/<doc>': 60, '/api/resource/Delivery Plan': 31}

## 2. 分段统计（SO 级 = 全量）

| 段 | 窗口 | SO 数 | cancelled | cancelled 比例 | submitted | 未发(<100) | 未发比例 |
|---|---|---:|---:|---:|---:|---:|---:|
| A | 2024-11..2025-05 | 108 | 9 | 0.0833 | 99 | 70 | 0.7071 |
| B | 2025-06..2025-12 | 116 | 2 | 0.0172 | 113 | 93 | 0.823 |
| C | 2026-01..2026-06 | 83 | 8 | 0.0964 | 74 | 68 | 0.9189 |
| D | 2026-07..2026-10 | 50 | 0 | 0.0 | 49 | 46 | 0.9388 |

## 3. Delivery Plan 关联（样本：每段前 15 单）

| 段 | 样本 SO | 有 DP 关联 SO | 关联率 | DP item 行 | so_detail 非空 | DP 单数 | is_dn_pending | 计划量合计 |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| A | 15 | 0 | 0.0 | 0 | 0 | 0 | {} | 0 |
| B | 15 | 15 | 1.0 | 392 | 392 | 58 | {'1': 58} | 9486.0 |
| C | 15 | 10 | 0.6667 | 577 | 577 | 25 | {'1': 25} | 12530.0 |
| D | 15 | 10 | 0.6667 | 1914 | 1914 | 17 | {'1': 17} | 14047.0 |

关联字段实测：`Delivery Plan Item.sales_order` / `.so_detail`；`Delivery Plan` header 有 `sale_orders`（未按该字段查询）；SO 文档本身无直接 DP 链接字段。

## 4. 皮壳/内胆配对（样本：每段前 15 单）

| 段 | both | cover_only | inner_only | neither |
|---|---:|---:|---:|---:|
| A | 15 | 0 | 0 | 0 |
| B | 10 | 0 | 0 | 5 |
| C | 8 | 1 | 1 | 5 |
| D | 0 | 7 | 0 | 8 |

口径：`PK#` 为皮壳、`ND#` 为内胆；同一 SO 内同现=both；仅按 item_code 前缀判定，不看数量或 BOM。

## 5. 政策字段时间线

### 5.1 `type_of_manufacturing`（SO header，全量按段）

| 段 | `In House` | `Subcontract` |
|---|---:|---:|
| A | 108 | 0 |
| B | 116 | 0 |
| C | 70 | 13 |
| D | 47 | 3 |

### 5.1b 月份级 `type_of_manufacturing` 分布（全量）

| 段 | 月份 | 分布 |
|---|---|---|
| A | 2024-11 | {'In House': 7} |
| A | 2024-12 | {'In House': 14} |
| A | 2025-01 | {'In House': 2} |
| A | 2025-02 | {'In House': 23} |
| A | 2025-03 | {'In House': 18} |
| A | 2025-04 | {'In House': 23} |
| A | 2025-05 | {'In House': 21} |
| B | 2025-06 | {'In House': 27} |
| B | 2025-07 | {'In House': 24} |
| B | 2025-08 | {'In House': 28} |
| B | 2025-09 | {'In House': 22} |
| B | 2025-10 | {'In House': 13} |
| B | 2025-11 | {'In House': 2} |
| C | 2026-01 | {'In House': 10} |
| C | 2026-03 | {'In House': 25, 'Subcontract': 6} |
| C | 2026-04 | {'In House': 13, 'Subcontract': 1} |
| C | 2026-05 | {'In House': 10, 'Subcontract': 1} |
| C | 2026-06 | {'Subcontract': 5, 'In House': 12} |
| D | 2026-07 | {'In House': 9, 'Subcontract': 3} |
| D | 2026-08 | {'In House': 14} |
| D | 2026-09 | {'In House': 12} |
| D | 2026-10 | {'In House': 12} |

- 突变检测（仅当相邻两月各 ≥5 单且 top 值占比变化 ≥50pp 或 top 值变化）：
  - 未发现满足阈值的月份突变（这是“未见突变”，不是“政策未变”）。
  - 各取值首次出现的月份：{'In House': '2024-11', 'Subcontract': '2026-03'}（只记现象，不解释原因）。

### 5.2 审批/价格相关自定义字段

- 识别的字段（SO）：[]
- 识别的字段（SO Item）：[]
- **未发现** label/fieldname 匹配 approve/price/rate/discount/credit/limit/authoriz 的 SO 或 Item 自定义字段；本节无取值分布可报。

> 只记录存在与取值分布，不解释业务含义；如某字段在某月前后分布突变，只记现象与月份，不下结论。

## 6. 看到 / 看不到

- 看到：四段的 SO 全量计数/cancelled/未发比例；样本内的 DP 关联与 `is_dn_pending` 分布；`type_of_manufacturing` 全量分段分布；配对比例；审批/价格相关自定义字段的存在与样本取值。
- 看不到：DP 关联的全量覆盖率（样本 15/段）、字段业务含义、扫码关联（SO/Item/DP 实测未见 scan/qr 字段）、政策变化的因果。
- 不给下单建议，不做全量外推。

## 7. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/auto_order/recon_linkage.py
uv run python scripts/check_secrets.py
```

