---
okf: v0.1
type: Review
title: 全母集批处理返修记录（FULL-REVIEW 唯一 major：库存未知被按 0 计算）
date: 2026-10-22
owner: claude-worker
status: 已修复并重生成；计数与自检不变
reviewed: '#301 FULL-REVIEW（唯一 major）'
base_commit: c1d8f1f5
artifacts:
  - experiments/business_phase/build_replenishment_batch.py
  - out/business_phase/replenishment_all.csv
  - out/business_phase/summary.md
  - （replenishment_all.xlsx 本地重生成；仓库忽略 *.xlsx，不提交）
---

# 全母集批处理返修记录

## 0. 一句话

原脚本把「无库存行（库存未知）」在缺失说明里写成“不等于 0”，却在算建议区间时用
`(avail or 0)` 隐式归零，导致 6 行的条件数量实际按 0 库存算出。现改为：**库存缺失 →
建议数量直接留空、状态标 `B_pending_inventory`**，并在行内写明“库存未知，待核实”；
脚本内不再存在任何 `(x or 0)` 形式的隐式归零。

## 1. 根因与证据

| 项 | 内容 |
|---|---|
| 问题位置（原脚本） | 库存在 `supply_notes()` 里判为 unknown（`avail = None`），但计算块使用 `(avail or 0)` 生成区间 |
| 受影响行 | CSV 行号（含表头）**217 / 238 / 317 / 912 / 1281 / 1301**，共 **6** 行 |
| 事实核验 | 这 6 个 SKU 在 `stock_latest` 里的行数均为 **0**（库存未知），不是 0 库存 |

| CSV 行号 | SKU | 修复前建议区间（按 0 库存算） | 修复后 |
|---:|---|---|---|
| 217 | `CEN003-DPBLUE-100-old` | 1.47–2.25 | **空** |
| 238 | `CEN964NLinen-GrayLilac-153` | 0.98–78.1 | **空** |
| 317 | `CENVel1612-Black-138-Cover` | 0–5.67 | **空** |
| 912 | `TT0031004K0062860` | 0–36.61 | **空** |
| 1281 | `TT0312638K0064282` | 0–0 | **空** |
| 1301 | `TT0312687K0064377` | 0.98–1.5 | **空** |

## 2. 修复内容（脚本 `build_replenishment_batch.py`）

| 要求 | 落实 |
|---|---|
| (1) 禁止隐式归零 | 删除全部 `(avail or 0)` / `(po_qty or 0)` / `(intr or 0)`；改为先判 `None`。DB 行级 NULL 统一走 `_int()` 助手（`:70`），并在 docstring 写明“缺失 SKU 行是未知，不走这里” |
| (2) 6 行置空 + 状态 | `:364` `status = "B_pending_inventory"`；`:365` 数量留空；`:366` 缺失字段写「库存未知，待核实（无库存行，未按 0 计算）」 |
| (3) “假设库存=0”单独说明 | 本批**不产出**“库存=0 压力值”，因此不存在“既假设 0 又声明没按 0 算”的矛盾；行内 assumptions 明确写「库存未知：本行不给条件数量」 |
| (4) 库存口径入表 | 库存单元格改为 `available=N（SKU 跨仓汇总；仓列仅为标注，非分仓分配）`（`:414`）；summary 增加固定说明 |
| (5) 计数与自检不变 | 1,328 行不变；**B = 1,231 + B_pending_inventory 6 = 1,237**，A=0，C=91；8 例自检仍全部一致 |
| (6) 重生成 | CSV / summary 重生成；xlsx 本地重生成（仓库 `.gitignore` 忽略 `*.xlsx`，不提交） |

**grep 证据（脚本内已无隐式归零）**：

```
$ grep -nE "avail or 0|po_qty or 0|intr or 0" build_replenishment_batch.py
（无输出）
```

## 3. 重算后的计数（相加不变）

| 项 | 值 |
|---|---:|
| 输出行 / SKU | 1,328 / 1,328 |
| A | 0 |
| B（条件数量） | 1,231 |
| **B_pending_inventory（库存未知，数量空）** | **6** |
| **B 大类合计** | **1,237** |
| C（out_of_scope_uom 29 + unmapped 62） | 91 |
| 1,237 + 91 | 1,328 ✅ |

B 的销量仍计入 B 大类占比；`B_pending_inventory` 只作**子计数单列**，不计入可执行数量。

## 4. 自检（8 个冻结代表 SKU，仍与 N2 一致）

| SKU | 期望 | 重算 | 一致 |
|---|---:|---:|---|
| TT0031038K0062927 | 345 | 345 | ✅ |
| C/Linen-Natural-100-688-wow | 55 | 55 | ✅ |
| TT0312701K0064561 | 181 | 181 | ✅ |
| C/Cord-DKBlue-100-713-wow | 6 | 6 | ✅ |
| C/Velvet-White-100-664-wow | 0 | 0 | ✅ |
| TT0031010K0062880 | 0 | 0 | ✅ |
| C/Linen-Natural-194-688-wow | 366 | 366 | ✅ |
| CENCord995-DKGrey-97 | 1 | 1 | ✅ |

## 5. summary 新增说明

- 「**6 行待库存核实**：这些 SKU 在快照中没有库存行（库存未知，不是 0），建议数量留空，
  状态标 `B_pending_inventory`，不计入可执行数量。」
- 「**库存口径**：库存为 SKU 跨仓汇总（`stock_latest` 所有仓相加）；表里的「仓」列只是
  标注主仓，不是分仓补货分配。」

## 6. 校验

| 项 | 结果 |
|---|---|
| 两次运行 CSV 逐字节一致 | ✅（已实测） |
| DB 只读，前后 sha256 一致 | ✅ |
| 8 例自检 | ✅ 8/8 |
| 行数与 A/B/C 计数相加 | ✅ |
| 6 行建议数量为空且状态正确 | ✅ |
| `check_secrets.py` | 零输出 |
| 未改冻结名单 / plan / ranking / destinations / V1 产物 | ✅ |

## 7. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/build_replenishment_batch.py
uv run python scripts/check_secrets.py
```

产物：`replenishment_all.csv`（聚合建议表）、`summary.md`；
`replenishment_all.xlsx` 本地生成但仓库忽略，不作为提交物。
