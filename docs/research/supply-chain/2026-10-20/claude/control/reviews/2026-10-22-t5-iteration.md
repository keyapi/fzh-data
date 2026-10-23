---
okf: v0.1
type: Review
title: T5 全范围迭代版（AutoETS 默认 + MA3 fallback）
date: 2026-10-22
owner: claude-worker
status: 完成；2,309 行、1,328 SKU 全覆盖
artifacts:
  - experiments/business_phase/build_iteration_v2.py
  - out/business_phase/replenishment_v2.csv
  - out/business_phase/diff_v1_v2.csv
  - out/business_phase/summary_v3.md
  - （replenishment_v2.xlsx 本地生成；仓库忽略 *.xlsx，不提交）
---

# T5 全范围迭代版

> 按 Codex2 裁定 A：预测默认 **AutoETS**（statsforecast 2.1.1）；AutoETS 不可用的序列
> **fallback 到 MA3 并逐行写明**；测试集反转只作迁移风险写入摘要，不据此改选。
> 决策逻辑沿用 T3；只读 T3/T4/T2/首版/1A/DB；未改任何既有产物。

## 1. 覆盖与对账

| 项 | 值 |
|---|---:|
| 输出行数 | **2,309** |
| 覆盖 SKU | **1,328** = 1,237 合格 + 29 UOM + 62 未映射 |
| SKU×仓合格行 | **2,218**（与 T3 逐行对齐） |
| 状态 A / B / B_pending_inventory / C | **0 / 2,058 / 160 / 91** |
| 与 T3 行数对账 | 2,309 / 2,309，0 丢弃、`(SKU,仓)` 唯一 |

销量占比（6 个月净出库）：**B 98.9% / C 1.1% / A 0%**（共 48,544）。

## 2. 方法（逐行可见）

| 项 | 值 |
|---|---|
| 默认方法 | **AutoETS**（statsforecast 2.1.1），SKU 级拟合 |
| 分配 | 按该仓近 3 月销量占比分配到仓（**显式假设**，写入每行 `assumptions`） |
| fallback | **112 行**（与 T4 实测一致）：`NotImplementedError: tiny datasets` 等 → 用 SKU 级 **MA3**，原因写在 `fallback理由` |
| 方法分布 | AutoETS 2,106 行 / MA3 112 行 |
| 合并解释 | 每行带 T4 的历史窗口、验证表现、缺口/建议量公式、异常标签与处理说明 |

## 3. 与首版 v1 的差异（逐 SKU 可查）

`diff_v1_v2.csv` 共 **1,328 行**（每个 SKU 一行）：

| 状态 | SKU 数 |
|---|---:|
| 数量变化 `changed` | **726** |
| 数量不变 `unchanged` | 505 |
| v1 无数量（C 类）`v1_no_quantity` | 97 |
| v2 新增行 | 0（无 SKU 消失） |

- 变化原因（逐行 `change_reason`）：① 模型由 SKU 级 MA3 切到 AutoETS（失败则 MA3）；
  ② 粒度改为 SKU×仓并按销量占比分配；③ PO/在途仍按去重批进入情景，但基数随需求变。
- 变化最大：`CENCord995-DKGrey-97` −710.37、`CEN003-DPBLUE-100` −609.58、
  `C/Velvet-Grey-100-705-wow` −283.14（下限合计净变化 −3,125.55）。

## 4. 决策逻辑（沿用 T3，未改）

- SKU×仓粒度；共享池**默认不跨仓调拨**；需求冲减前后两列（SO 不冲减）；
- PO / 在途 / 在产**分别去重**；L60/L90/L120 三情景；**PR#297 基线并排**（含差异列）；
- MOQ / 包装 / 成本单列待定；A/B/C 三态；B 行 `assumptions` 必填；未知 null 不填 0。

## 5. 校验

| 项 | 结果 |
|---|---|
| 1,328 SKU 全覆盖（1,237+29+62） | ✅ |
| SKU×仓行数与 T3 对账（2,218） | ✅ |
| B 行数量与 assumptions 均非空 | ✅（2,058/2,058） |
| pending 行数量为空 | ✅（160 行） |
| fallback 逐行可见 | ✅（112 行，含原因） |
| 无隐式归零 `grep` | ✅ 零命中 |
| 两次运行 CSV 逐字节一致 | ✅ |
| DB 只读前后 sha256 | ✅ 一致 |
| `check_secrets.py` | 零输出 |
| 未改 T2/T3/T4/首版/V1 产物 | ✅ |

## 6. 摘要要点（`summary_v3.md` 已含）

- 覆盖 1,328 SKU；A/B/C 分布与销量占比；
- 方法对照与选择依据，含**验证/测试反转**（验证 AutoETS 0.5232 最优、测试 combo 0.6100 最低）
  作为**迁移风险**记录，不据此改选；
- v1→v2 差异汇总（726 个 SKU 数量变化）；
- 使用限制：A=0（G8 与在产缺失）、B 为条件区间、MOQ/成本未定、退货不可观测、
  促销/运营/断货异常检出未校正、共享池不默认调拨。

## 7. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/build_iteration_v2.py
uv run python scripts/check_secrets.py
```

运行约 21 秒（含 1,328 个 SKU 的 AutoETS 拟合）；xlsx 仅本地生成。
