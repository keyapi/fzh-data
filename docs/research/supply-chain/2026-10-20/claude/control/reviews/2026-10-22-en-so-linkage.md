---
okf: v0.1
type: Review
title: EN SO 关联覆盖与政策时间线（只读，98 次 GET）
date: 2026-10-22
owner: claude-worker
status: 完成；只读生产 REST，无写入
artifacts:
  - experiments/auto_order/recon_linkage.py
  - out/auto_order/linkage_profile.json
  - out/auto_order/policy_timeline.md
---

# EN SO 关联覆盖与政策时间线

> 只读 GET；预算 ≤200 次、page_length ≤100、间隔 ≥200ms；超时/5xx 即停。
> **SO 级统计 = 分段全量；Delivery Plan 关联、item 级字段、配对 = 每段前 15 单样本**。
> 只记录现象；不解释字段业务含义、不给下单建议、不做全量外推。

## 1. 预算

| 项 | 值 |
|---|---|
| 请求 | **98**（上限 200） |
| 耗时 | **19.6 s** |
| 间隔 / page_length | 0.2 s / ≤100 |
| 停止 | 无（正常完成） |
| 错误 / 写入 | 0 / **无（全部 GET）** |

路径：`Custom Field` 1、`Sales Order` 列表 6、`Sales Order/<doc>` 60、
`Delivery Plan` 列表 31（含 child filter）。

## 2. 分段统计（SO 级 = 全量）

| 段 | 窗口 | SO 数 | cancelled | cancelled 比例 | submitted | 未发(<100) | 未发比例 |
|---|---|---:|---:|---:|---:|---:|---:|
| A | 2024-11..2025-05 | 108 | 9 | 8.33% | 99 | 70 | 70.71% |
| B | 2025-06..2025-12 | 116 | 2 | 1.72% | 113 | 93 | 82.30% |
| C | 2026-01..2026-06 | 83 | 8 | 9.64% | 74 | 68 | 91.89% |
| D | 2026-07..2026-10 | 50 | 0 | 0% | 49 | 46 | 93.88% |

- 全量口径：每段 SO header 列表（分页），未发 = submitted 且 `per_delivered<100`。
- 零单月份已保留（如 2025-12、2026-02，见 `policy_timeline.md §5.1b`）。

## 3. Delivery Plan 关联（样本 15/段）

| 段 | 有 DP 关联 SO | 关联率 | DP item 行 | `so_detail` 非空 | DP 单数 | `is_dn_pending` | 计划量合计 |
|---|---:|---:|---:|---:|---:|---|---:|
| A | 0 | 0% | 0 | 0 | 0 | {} | 0 |
| B | 15 | 100% | 392 | 392 | 58 | {'1': 58} | 9,486 |
| C | 10 | 66.7% | 577 | 577 | 25 | {'1': 25} | 12,530 |
| D | 10 | 66.7% | 1,914 | 1,914 | 17 | {'1': 17} | 14,047 |

**关联键实测**：

- `Delivery Plan Item.sales_order` / `.so_detail` 均存在且非空（样本内 100%）。
- 读取方式：child doctype 直读 **403**；改用 `Delivery Plan` 父列表 +
  child 过滤 `["Delivery Plan Item","sales_order","in",names]` + `items.*` 展开。
- `Delivery Plan` header 有 `sale_orders` 字段，但 `sale_orders.<child>` 查询返回
  “Field not permitted”；本轮按 items 侧字段统计。
- SO header/item 无直接 DP 链接字段；扫码关联（scan/qr）在 SO/Item/DP 均未观测到。
- `is_dn_pending` 在样本内全部为 **1**（58/25/17 个 DP）；只记录取值，不解释语义。

## 4. 配对（样本 15/段，口径同上一轮）

| 段 | both | cover_only | inner_only | neither |
|---|---:|---:|---:|---:|
| A | 15 | 0 | 0 | 0 |
| B | 10 | 0 | 0 | 5 |
| C | 8 | 1 | 1 | 5 |
| D | 0 | 7 | 0 | 8 |

口径：同一 SO 内 item_code 含 `PK#`=皮壳、`ND#`=内胆；同现=both；只看前缀，
不看数量/BOM。D 段样本内 **没有 both**，以 cover_only 为主（7/15）。

## 5. 政策字段时间线

### 5.1 `type_of_manufacturing`（SO header，全量）

| 段 | In House | Subcontract |
|---|---:|---:|
| A | 108 | 0 |
| B | 116 | 0 |
| C | 70 | 13 |
| D | 47 | 3 |

- 月份级分布见 `policy_timeline.md §5.1b`。
- **现象**：`Subcontract` 首次出现于 **2026-03**（C 段 6 单），此后 2026-04/05 各 1、
  2026-06 5、2026-07 3，2026-08 起样本月份为 0。
- 突变检测（相邻两月各 ≥5 单、top 值占比变化 ≥50pp 或 top 值变化）：**未发现**满足阈值
  的月份。只记“未见突变”，不等于“政策未变”。

### 5.2 审批/价格相关自定义字段

- 在 Sales Order / Sales Order Item 的 **11 条 Custom Field** 中，按
  label/fieldname 匹配 approve/approval/price/discount/rate/credit/limit/authoriz：
  **SO 0 条、Item 0 条**。
- 因此本节没有“审批/价格字段的实际取值分布”可报；不推断是否存在其他形式的审批。

## 6. 看到 / 看不到

- 看到：四段 SO 全量计数/cancelled/未发比例；样本内 DP 关联（B 100%、C/D 66.7%、
  A 0%）与 `is_dn_pending` 分布；`type_of_manufacturing` 全量分段/月份分布与
  `Subcontract` 首次出现月份；配对比例。
- 看不到：DP 关联的**全量**覆盖率（样本 15/段）、`sale_orders` 子表内容、
  扫码关联（无 scan/qr 字段）、审批/价格字段（未发现）、政策变化的因果。
- 不给下单建议，不做全量外推。

## 7. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/auto_order/recon_linkage.py
uv run python scripts/check_secrets.py   # 无 finding、退出码 0
```

- 凭证从 `EN_API/.env` 读取，不打印/不落盘；输出只含聚合与哈希 id。

## 8. 约束自检

| 约束 | 结果 |
|---|---|
| 只新增 `recon_linkage.py`、`linkage_profile.json`、`policy_timeline.md`、本记录 | ✅ |
| 只读 GET；无写入/下单/配置变更 | ✅ |
| 单线程、≤200 次、page_length ≤100、间隔 ≥200ms | ✅（98 次 / ≤100 / 0.2s） |
| 超时/5xx 即停 | 代码已实现；本轮 0 错误 |
| 不提交原始明细；doc id 哈希 | ✅（样本仅 `so_hash` 列表，DP 只给计数） |
| 不改主表与既有产物；未改 control 受保护文件 | ✅ |
| 未 push；只提交自己新增文件 | ✅ |
| `check_secrets.py` 无 finding | ✅ |
| 不留临时文件（含 `__pycache__`） | ✅ |
