---
okf: v0.1
type: Review
title: P1C 溯源标签更正（model_race → d2eac9a3）
date: 2026-10-22
owner: claude-worker
status: 已完成；纯元数据更正，数值零变化
scope:
  - out/business_phase/plan.json（仅 inputs 段）
  - out/business_phase/plan.md（仅溯源行）
  - out/business_phase/coverage_proof.json（仅差异/快照记录）
---

# P1C 溯源标签更正

> 只改元数据，**不重算任何销量、供给或判定数值**；不触碰 ranking / destinations / evidence /
> V1 冻结产物；不重排序、不引入新数据。
> 更正对象：`plan.json → inputs` 里把 `model_race.json` 与 `model_race.py` 标成 `f9df4357`，
> 而实际消费的是 **`d2eac9a3`**（R2/R3 返修后版本）。

## 1. 更正内容（保留历史）

| 字段 | 更正前 | 更正后 |
|---|---|---|
| `model_race_commit` | `f9df4357` | **`d2eac9a3`** |
| `model_race_json_sha256`（raw，原字段保留） | `13be6ab4d6a118f3…` | 不变 |
| `model_race_py_sha256`（raw，原字段保留） | `0db651a533bcf387…` | 不变 |
| `model_race_json_sha256_canonical_lf` | — | **`81aa9f9a71bc00ec330eb3b131573bc48ebff1c0cebc8c15860ef519f2712f84`** |
| `model_race_py_sha256_canonical_lf` | — | **`869873dfeb730951d4eaf36022a15eec225951c50c317d96370d13ca356ab7ba`** |
| `model_race_json_blob_d2eac9a3` | — | **`c05fd6b8965cd31e79c85fa45dadb1c0f2bdff96`** |
| `model_race_py_blob_d2eac9a3` | — | **`574b0c127d87d9f5f22da79da68a042f1480b608`** |
| `declared_baseline_commit`（新增，保留原声明） | — | **`f9df4357`** |
| `correction_note`（新增） | — | 说明为何更正、原 raw hash 保留 |

`plan.md` 的溯源行同步改为两行：evidence 仍标 `f9df4357`，
model_race.json / model_race.py 标 **`d2eac9a3`** 并给出 canonical-LF 前缀与
`原 declared_baseline_commit=f9df4357`。

## 2. 明确结论（复审要的那句话）

**P1C 的需求侧消费的是 `d2eac9a3` 的 `model_race`（含 `label_available_at` 过滤与
conformal-style 标定），不是 `f9df4357` 的字节内容。**
`f9df4357` 只是本批最初声明的基线；R3 返修把该产物与脚本一起重写了。

## 3. 数值零变化证明

| 对比对象 | 更正前 sha256 | 更正后 sha256 | 结论 |
|---|---|---|---|
| `plan.json` 除 `inputs`/`generated_at` 外的全部内容 | `2e1634ba711f8432…` | `2e1634ba711f8432…` | **逐字节不变** |
| `plan.json → rows`（122 行明细） | `f84c346f3c1534e4…` | `f84c346f3c1534e4…` | **逐字节不变** |

即：只有 `inputs` 段的标签与哈希字段变了；`counts`、`coverage`、`decisions`、
每行的需求/供给/判定数值全部原样。没有重算、没有重新生成。

## 4. 断言重跑（14/14 仍为真）

| # | 断言 | 结果 |
|---:|---|---|
| 1 | Top50 数量 = 50 | ✅ |
| 2 | Top50 唯一 | ✅ |
| 3 | Top50 rank 为 1..50 | ✅ |
| 4 | 紧急例外数量 = 75 | ✅ |
| 5 | 例外唯一 | ✅ |
| 6 | 交集数量 = 3 | ✅ |
| 7 | 交集名单与期望一致 | ✅ |
| 8 | 并集 = 50+75−3 | ✅ |
| 9 | 并集数量 = 122 | ✅ |
| 10 | `plan.json` 行数 = 122 | ✅ |
| 11 | plan 内 SKU 唯一 | ✅ |
| 12 | 并集 == plan SKU 集合 | ✅ |
| 13 | 无缺失 / 无多余 | ✅ |
| 14 | 每个并集 SKU 恰好一次 | ✅ |

`coverage_proof.json → checks` 里存的 14 个布尔值与本次独立重算**逐项相同**，`all_checks_pass` 仍为 `true`。
`plan.json` 的 122 行与并集逐 SKU 相等（集合相等 + 出现次数 = 1）。

## 5. `coverage_proof.json` 的处理

- 两条 `differences` 记录**保留全部原始证据字段**（declared commit、declared blob、actual LF hash、
  解释文本），新增 `status="resolved"`、`resolved_in`、`resolution`。
- `inputs_snapshot.model_race_json / model_race_py` 保留 `frozen_commit=f9df4357`
  （作为“当初声明”的证据）与 `content_matches_commit=false`，另加
  `actual_content_commit="d2eac9a3"`、`blob_sha256_d2eac9a3`、`matches_actual_commit=true`。
- 新增 `label_correction` 块：更正前后 commit、canonical-LF sha256、两个 blob id、
  以及“P1C 消费 d2eac9a3”的明确表述。
- **该 proof 并未记录 `plan.json` 的 sha256**，因此没有需要重算的 plan 哈希——
  这一点也写在 `label_correction.plan_json_note` 里，避免读者误以为漏了。

## 6. 没有做的事

- 没有修改 `ranking.json` / `destinations.json` / `evidence.json` / `model_race.*` / V1 产物。
- 没有重算销量、供给、决策或任何数量。
- 没有把 `f9df4357` 的历史声明删掉（`declared_baseline_commit` 永久保留）。
- `check_secrets.py` 零输出；无临时文件。

DONE P1C-LABEL
