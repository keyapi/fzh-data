---
okf: v0.1
type: Review
title: P1C 收口证明（Top50 / 紧急例外 / 交集 / 并集 / 输入快照）
date: 2026-10-22
owner: claude-worker
status: 收口完成；只新增证明文件，未改任何产物
inputs:
  - out/business_phase/ranking.json（d50310a6）
  - out/business_phase/destinations.json（44def7f5）
  - out/replenishment_v0/evidence.json（f9df4357）
  - out/replenishment_v0/model_race.json
  - D:/Work/fzh-order-store/order_store.duckdb（read_only）
artifacts:
  - out/business_phase/coverage_proof.json
---

# P1C 收口证明

> 本文件与 `coverage_proof.json` **只做重算与对账**：不修改 `build_plan.py`、
> 不修改 `plan.json / ranking.json / destinations.json`、不重排序、不引入新数据。
> 所有数字都由三份产物 + `git show` 重新算出来，不复制 P1C 的声明。

## 1. 断言总览（全部通过）

| 检查 | 期望 | 实际 | 结果 |
|---|---:|---:|---|
| Top50 数量 | 50 | 50 | ✅ |
| Top50 唯一 / rank 为 1..50 | 是 | 是 | ✅ |
| 紧急履约例外数量 | 75 | 75 | ✅ |
| 例外唯一 | 是 | 是 | ✅ |
| 交集数量 | 3 | 3 | ✅ |
| 交集名单与派单期望一致 | 3 个指定 SKU | 一致 | ✅ |
| 并集 = 50 + 75 − 3 | 122 | 122 | ✅ |
| `plan.json` 行数 | 122 | 122 | ✅ |
| 并集 == `plan.json` 的 SKU 集合 | 相等 | 相等 | ✅ |
| 每个并集 SKU 在 plan 里恰好一次 | 是 | 是 | ✅ |
| 缺失 / 多余 / 重复 | 0 | 0 / 0 / 0 | ✅ |

## 2. 交集（3 个，逐个）

| SKU | Top50 排名 | 例外待发件 | 母集内 | 在合格排序内 |
|---|---:|---:|---|---|
| `TT0000933K0011516` | 45 | 2 | 是 | 是 |
| `TT0020013K0062821` | 36 | 1 | 是 | 是 |
| `TT0031038K0062927` | 2 | 5 | 是 | 是 |

与派单给出的期望名单 **完全一致**（顺序也一致）。

## 3. 并集（122）

50 + 75 − 3 = **122**；其中**母集内 84、母集外 38**。
逐 SKU 清单见 `coverage_proof.json → union.skus`（122 项，已排序），
与 `plan.json` 的 122 行逐 SKU 相等，无缺失、无多余、无重复。

## 4. 输入快照

| 输入 | bytes | sha256（canonical LF） | 标称 commit | 内容与 commit 一致？ |
|---|---:|---|---|---|
| `out/business_phase/ranking.json` | 158,239 | `22c627ed6871dc21…` | `d50310a6` | ✅ |
| `out/business_phase/destinations.json` | 1,813,093 | `1b3032fe914ea528…` | `44def7f5` | ✅ |
| `out/replenishment_v0/evidence.json` | 297,288 | `15d52072dc5d0461…` | `f9df4357` | ✅（LF 字节；工作区 raw 为 CRLF，hash 不同但内容一致） |
| `out/replenishment_v0/model_race.json` | 1,155,587 | `81aa9f9a71bc00ec…` | `f9df4357` | ❌ **见 §5** |
| `experiments/g2g3_pilot/model_race.py` | 79,427 | `869873dfeb730951…` | `f9df4357` | ❌ **见 §5** |
| `order_store.duckdb` | 51,654,656 | `25579c5dcd802c7e…` | —（不在仓库） | 本地只读快照，运行前后 hash 不变 |

> `coverage_proof.json` 同时记录每份文件的 **raw sha256**（Windows CRLF 工作区字节）
> 与 **canonical LF sha256**（git 存储形式），并注明是否做了换行归一化。

## 5. 差异披露（如实，不调整产物）

**差异**：P1C 的输入清单把 `model_race.json` 与 `model_race.py` 标为 `f9df4357`，
但**实际内容属于 `d2eac9a3`**：

| 文件 | `f9df4357` blob | `d2eac9a3` blob | 当前内容（LF） |
|---|---|---|---|
| `model_race.json` | `9dd044b1f06c8b4e…` | `81aa9f9a71bc00ec…` | **`81aa9f9a71bc00ec…`** |
| `model_race.py` | `929f0899dc4baab8…` | `869873dfeb730951…` | **`869873dfeb730951…`** |

原因：R3 返修（`d2eac9a3`）把 `label_available_at` 写进了 `model_race` 的产物与脚本，
之后没有再回退。P1C 的计算**用的就是工作区实际内容**（`plan.json` 记录的
`model_race_json_sha256` 正是当前 raw hash `13be6ab4…`），
**错的只是输入清单里的 commit 标签**，不是计算对象。

**影响**：无计算影响（消费的文件就是被 hash 的文件，且 P1C 只复用 `model_race.py` 的函数）；
但“V1 冻结 = f9df4357”这句话对本批不成立，后续引用 P1C 时应写
**“model_race 取自 d2eac9a3（含 label_available_at 的 R3 版本）”**。
本收口**没有**修改任何产物去对齐标签——按要求只披露。

## 6. 复现方式

```python
# 重算（无脚本落库，纯读产物）：
# 1) ranking.json->top50[].sku 与 urgent_fulfilment_exceptions[].sku 取集合
# 2) 交集 / 并集逐 SKU 列出
# 3) 与 plan.json->rows[].sku 做集合相等 + 出现次数 == 1 断言
# 4) 每个输入文件 raw + LF sha256；对 FROZEN_COMMIT 做 git show 比对
```

完整结果见 `out/business_phase/coverage_proof.json`（含 50 个 Top50 行、75 个例外行、
3 个交集、122 个并集 SKU、以及每份输入的 raw/LF 双 hash 与 commit 比对）。

DONE P1C-CLOSE
