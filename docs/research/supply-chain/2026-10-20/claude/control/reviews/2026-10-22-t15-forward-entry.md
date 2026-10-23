---
okf: v0.1
type: Review
title: T15 前向评分入口修正（缺最后目标月不再 SystemExit）
date: 2026-10-22
owner: claude-worker
status: 完成；只改脚本与新增本记录，未重算 M01/M02
artifacts:
  - experiments/business_phase/forecast_eval/forward_shadow.py
---

# T15 前向评分入口修正

> 只修 `forward_shadow.py` 的评分入口；未重跑数据库、未改 T9/T10 产物、未改主表与
> control 下任何文件。参数化、预存清单、防覆盖逻辑与零需求口径保持不变。

## 1. 问题（T14-REVIEW M03 剩余项）

旧入口 `score()` 在数据库未覆盖最后一个目标月时直接退出：

```python
_, db_hi = db_months(args.db)
if ym_i(db_hi) < ym_i(targets[-1]):
    raise SystemExit(f"labels missing: need through {targets[-1]}, DB has {db_hi}; ...")
```

后果：`build_score()` 根本不执行，月度任务既没有 `labels_incomplete` 结构化输出，
也没有逐 SKU 排除原因与重试日期——与 T14 修复记录声明的“标签不全则标 unknown 并列出
排除原因”不符。

## 2. 修复

| 改动 | 位置 |
|---|---|
| **移除提前退出**；缺月交给 `build_score()` 统一处理 | `forward_shadow.py:406`（入口不再检查 `db_hi`） |
| 入口可注入只读读取器（回归测试用，不改真实路径） | `forward_shadow.py:381`（`load_score_inputs`）、`:406`（`fetch=None` 参数） |
| 输出结构化 `labels_incomplete`：缺哪些月、影响哪些 SKU、每 SKU 原因、重试日期 | `forward_shadow.py:360`（`labels_complete`）、`:361`（`scoring_due`）、`:362`（`labels_needed_through`）、既有 `coverage`/`excluded` |
| 真实路径的 db sha256 仍记录；注入路径记为 `null` | `forward_shadow.py:423-424` |

`build_score()` 的行为未变：标签完整时照常评分；任一目标月缺标签时
`status=labels_incomplete`、`n_scored=0`、`wape` 全为 null、`excluded` 逐 SKU 带
`missing_labels:<月份>`，并给出 `scoring_due`。零需求口径（无订单按 0 计入分子）不变。

## 3. 入口回归用例（新增 `--mode entrytest`）

与 `--mode selftest` 的区别：selftest 只测 `build_score()`；entrytest **驱动真实入口
`score()`**（注入只读读取器、临时目录），覆盖“缺最后目标月”的整条路径。

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forecast_eval/forward_shadow.py --mode entrytest
```

运行输出（断言失败即中止）：

```json
{
 "entry_missing_last_month": "labels_incomplete",
 "missing_months": ["2026-12"],
 "excluded": 2,
 "per_sku_reasons": ["missing_labels:2026-12"],
 "retry_after": "2027-01-04",
 "entry_complete_labels": "scored",
 "wape_when_complete": 0.15
}
```

覆盖的断言：

1. 缺最后一个月（`2026-12`）时**不再 `SystemExit`**，返回 `labels_incomplete`；
2. `coverage.missing_months` 精确为该月，`labels_complete=False`；
3. 预存样本 2 个 SKU 全部进入 `excluded`（`n_excluded=2`），原因为
   `missing_labels:2026-12`；`n_scored=0`、三种方法 WAPE 均为 null；
4. `scoring_due=2027-01-04`（预存文件给出，用于提示重试时点）；
5. 同一入口在标签完整时仍正常评分：`status=scored`、WAPE 0.15（与 selftest 一致）。

临时预存/输出文件都在 `TemporaryDirectory` 内，退出即删除。

## 4. 保持不变的项

| 项 | 状态 |
|---|---|
| `--data-cutoff` / `--origin` 参数化（无写死截止期） | 不变 |
| 预存清单（样本、选模、预测、生成时间、`--force` 防覆盖） | 不变 |
| 母集 = 预存样本；零需求计入分子；聚合总实际量为 0 才无定义 | 不变 |
| `--mode selftest` 合成反例（0.15 vs 0.0） | 不变（本次重跑通过） |
| 真实 `--mode score` 的数据库读取与 sha256 记录 | 不变（仅去掉缺月提前退出） |

## 5. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forecast_eval/forward_shadow.py --mode entrytest
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/forecast_eval/forward_shadow.py --mode selftest
uv run python scripts/check_secrets.py   # 无 finding、退出码 0
```

## 6. 约束自检

| 约束 | 结果 |
|---|---|
| 只改 `forward_shadow.py` + 新增本记录 | ✅ |
| 不跑数据库重算、不访问生产、不下单、不删数据、未合并 PR | ✅（回归用例用注入读取器，不连 DB） |
| 未改其他产物与 control 下任何文件 | ✅ |
| 未 push | ✅ |
| `check_secrets.py` 无 finding | ✅ |
| 不留临时文件（含 `__pycache__`） | ✅ 临时目录自动删除；`__pycache__` 提交前清理 |
