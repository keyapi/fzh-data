# 外部 SO 的 DN 关联核对

> 只读；判断“外部逾期是否已出库未回写/确实无出库记录”。
> **无 DN ≠ 真缺货**：可能线下发货，单据只能证明“系统内有无记录”。

## 0. 预算

- 请求 **74** / 80；停止：无（正常完成）；外部 SO 22、外部行 212

## 1. SO 级三类计数

| 类别 | SO 数 | 行数 | 含义 |
|---|---:|---:|---|
| `dn_submitted` | 13 | 164 | 有已提交 DN（docstatus=1） |
| `dn_unsubmitted` | 0 | 0 | 有 DN 但仅 draft/cancelled |
| `none` | 8 | 42 | 无任何 DN 与 DP |
| `dp_only`（补充） | 1 | 6 | 有 DP、无 DN（待出库） |

## 2. per_delivered 与 DN 的对照

- 有已提交 DN 的 SO：**13**；全部 `per_delivered<100`：**13** 个。
- 其中 `per_delivered≥99` 的 **4** 个（残余 <1%），`<99` 的 **9** 个；已提交 DN 对应的 164 行中，仍有未履约量的 **54** 行。
- 单据显示“DN 已提交”，但 SO 的 `per_delivered` 未达 100；差额可能是**未交付剩余**，也可能是**未回写**——DN 本身不能区分。
- `dn_unsubmitted` / `dp_only` / `none` 的 SO：per_delivered 见 CSV 逐行。

## 3. 逐行清单（摘要）

| SO 哈希 | 状态 | per_delivered | DP | DN 状态 | class | 行数 |
|---|---|---:|---|---|---|---:|
| `1d7ccd6df339` | To Deliver and Bill | 0.0 | 无 /  | 无 | none | 1 |
| `2d0cd5ee134f` | To Deliver and Bill | 99.565217 | 有 / 1 | DN-26-00043:1 | dn_submitted | 10 |
| `2e264550d679` | To Deliver and Bill | 99.508197 | 有 / 1 | DN-26-00048:1 | dn_submitted | 28 |
| `35a7807ef6f7` | To Deliver and Bill | 45.679012 | 有 / 1 | DN-26-00010:1|DN-26-00018:1 | dn_submitted | 6 |
| `4113055c490a` | To Deliver and Bill | 82.285714 | 有 / 1 | DN-26-00015:1|DN-26-00022:2 | dn_submitted | 5 |
| `4ff1269e40b4` | To Deliver and Bill | 85.849057 | 有 / 1 | DN-26-00009:1|DN-26-00011:1 | dn_submitted | 8 |
| `54d2298caf51` | To Deliver and Bill | 0.0 | 有 / 1 | 无 | dp_only | 6 |
| `6821e18c1cc7` | To Deliver and Bill | 99.322034 | 有 / 1 | DN-26-00069:1 | dn_submitted | 13 |
| `7076bd695ac9` | To Deliver and Bill | 0.0 | 无 /  | 无 | none | 18 |
| `72fcea0d87cc` | To Deliver and Bill | 19.047619 | 有 / 1 | DN-26-00011:1 | dn_submitted | 7 |
| `76a22b9df2d3` | To Deliver and Bill | 99.067599 | 有 / 1 | DN-26-00027:1 | dn_submitted | 9 |
| `7cbaa45ade44` | To Deliver and Bill | 87.105263 | 有 / 1 | DN-26-00040:1 | dn_submitted | 10 |
| `88e257a6c173` | To Deliver and Bill | 0.0 | 无 /  | 无 | none | 1 |
| `9816b8d0333b` | To Deliver and Bill | 0.0 | 无 /  | 无 | none | 2 |
| `a4ae8fc264b0` | To Deliver and Bill | 94.583333 | 有 / 1 | DN-26-00058:1|DN-26-00069:1 | dn_submitted | 15 |
| `b18c5afeb777` | To Deliver and Bill | 0.0 | 无 /  | 无 | none | 1 |
| `bc6699d13119` | To Deliver and Bill | 83.492749 | 有 / 1 | DN-26-00078:1|DN-26-00079:1|DN-26-00080:1|DN-26-00082:1|DN-26-00083:1|DN-26-00091:2|DN-26-00092:2|DN-26-00093:2|DN-26-00094:2|DN-26-00095:1|DN-26-00096:1|DN-26-00097:1|DN-26-00098:1|DN-26-00099:1 | dn_submitted | 29 |
| `d839e91ef8e1` | To Deliver and Bill | 47.309417 | 有 / 1 | DN-26-00105:1|DN-26-00106:1|DN-26-00107:1|DN-26-00108:1|DN-26-00109:1 | dn_submitted | 20 |
| `e0e7f835764e` | To Deliver and Bill | 0.0 | 无 /  | 无 | none | 2 |
| `f35e79122d51` | To Deliver and Bill | 60.0 | 无 /  | DN-26-00022-1:1 | dn_submitted | 4 |
| `f6ea885265de` | To Deliver and Bill | 0.0 | 无 /  | 无 | none | 15 |
| `f89f9add4601` | To Deliver and Bill | 0.0 | 无 /  | 无 | none | 2 |

逐行明细（212 行）见 `dn_linkage_check.csv`。

## 4. 能证明什么 / 不能证明什么

- 能证明：系统内是否存在 Delivery Plan 与 Delivery Note，以及 DN 的 docstatus；对已提交 DN 的 SO，可对照 per_delivered 是否同步。
- 不能证明：无 DN 的 SO 是否线下发货、DN 未提交是否已实物出库、DP `is_dn_pending` 之外的仓内状态；这些需仓储/财务确认。
- **不得**把“无 DN”直接等同于“真缺货”。

## 5. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/auto_order/check_dn_linkage.py
uv run python scripts/check_secrets.py
```

