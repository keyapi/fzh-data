---
okf: v0.1
type: Review
title: T21 交付物一致性巡检（8 项）
date: 2026-10-22
owner: claude-worker
status: 完成；只核对，未改任何数字或既有文档
artifacts:
  - experiments/business_phase/audit_consistency.py
  - out/business_phase/consistency_audit.json
  - out/business_phase/consistency_audit.md
---

# T21 交付物一致性巡检

> 只读已有 CSV/JSON/MD，不跑数据库、不改任何数字。FAIL 只列差异与建议，
> **未静默改数**，也未改写任何既有文档（ownership 仅限本审计输出）。

## 1. 总览

| # | 检查 | 结果 | 差异数 |
|---:|---|---|---:|
| 1 | `replenishment_v2.csv` ↔ `summary_v3.md` | **PASS** | 0 |
| 2 | `model_sensitivity.csv` ↔ `model_sensitivity.md` | **PASS** | 0 |
| 3 | `wo_dn_coverage.csv` ↔ `wo_dn_coverage.md` | **PASS** | 0 |
| 4 | `explanations.csv` ↔ `decision_v2.csv`（异常计数） | **PASS** | 0 |
| 5 | `diff_v1_v2.csv` ↔ `replenishment_all.csv` / `replenishment_v2.csv` | **PASS** | 0 |
| 6 | `evidence_request.md` 责任方行数 ↔ `decision_v2.csv`（T3） | **PASS** | 0 |
| 7 | `summary_v3 §6` ↔ `nested_eval` / `short_history_eval` | **FAIL** | 1 |
| 8 | `forward_shadow_plan.md` ↔ `forward_shadow.py` | **FAIL** | 5 |

**PASS 6 / FAIL 2。** 机器可读结果与逐项差异见 `consistency_audit.json`。

## 2. 逐项结果

### 1) replenishment_v2 ↔ summary_v3 — PASS

| 字段 | 表 | 文档 |
|---|---:|---:|
| 输出行数 | 2,309 | 2,309 |
| 覆盖 SKU | 1,328 | 1,328 |
| 状态 A/B/B_pending/C | 0/2,058/160/91 | 0/2058/160/91 |
| 方法 AutoETS / MA3 | 2,106 / 112 | 2,106 / 112 |
| 6 个月净出库 B / C | —（CSV 无此列） | 48,001 / 543 → 98.9% / 1.1% |

> CSV 没有 6 个月销量列，占比按文档自身原始值验算（48,001/48,544=98.88%、
> 543/48,544=1.12%），并与 `summary.md` 的 48,001/543 一致；**不能**从主表 CSV 重算。

### 2) model_sensitivity ↔ md — PASS

- 五类计数：①308 / ③a214 / ③b1536 / 未知160 / C91（相加 2,309）。
- 近 6 月销量覆盖：37.43% / 35.49% / 81.74% / 44.45% / 1.12%（按去重 SKU 重算，逐项一致）。
- ③a 子集：② 74 / ④ 140（74+140=214）。

### 3) wo_dn_coverage ↔ md — PASS

- 三态：0 / 32（10 SKU）/ 2,277（1,318 SKU），相加 2,309。
- 关联键：WO↔SO 173/214 有键、DN↔WO 0/507、WO↔PO 0/214（total/linked/missing 与 JSON 一致）。

### 4) explanations ↔ decision_v2 — PASS

- 行数 2,309 = 2,309，状态分布一致。
- 八类异常命中行 / SKU：`short_history` 943/538、`missing_inventory` 160/160、
  `zero_sales` 875/564、`returns_unobservable` 2,309/1,328、`duplicate_mapping` 0/0、
  `promo_spike` 252/117、`operational_change` 1,046/586、`stockout_censoring` 1,472/670；
  未打标签行 0。与 T4 评审表逐项一致。

### 5) diff_v1_v2 ↔ v1/v2 — PASS

- 行数 1,328 = `replenishment_all` 行数 = v2 SKU 数。
- change_status：changed 602 / unchanged 475 / partial_unknown 154 / all_unknown 6 /
  v1_no_quantity 91；可比 1,077。与 `summary_v3 §3` 一致（475 为差额核对）。

### 6) evidence_request 责任方行数 — PASS

| 责任方 | 文档 | decision_v2 实际 |
|---|---|---|
| 采购/供应链（有未结 PO） | 169 行 / 161 SKU | 169 / 161 |
| 生产/PMC、采购/财务、业务、供应链管理 | 2,218 行 / 1,237 SKU | 2,218 / 1,237 |
| 主数据/EN（C 类） | 91 行 / 91 SKU | 91 / 91 |
| 数据/系统（去重状态非 none） | 267 行 / 259 SKU | 267 / 259 |

> 文档另写“248 条 open 行 0 条有日期”；本地 CSV/JSON 无该口径，本轮未核（不作 PASS/FAIL）。

### 7) summary_v3 §6 ↔ 模型产物 — **FAIL（1 处措辞过时）**

数字全部一致：最后块 0.5255/0.4978/0.5016、bootstrap
[−0.1052,+0.1672] / [−0.1114,+0.1654]、选模分布 136/103/99/92/89/79、
28/11 旧规则未首单、392/403、各自子集 9.591/9.593/9.692/10.272/13.118、
正式共同子集 12.063/12.694/12.786/13.118/14.299、低置信 139/392、窗口 446、
fallback 71 SKU/0.10%。

| 文件 | 字段 | 产物实际 | 文档 |
|---|---|---|---|
| `summary_v3.md` | guard 阈值建议 | `len<7`（T20，`short_history_eval.py:69`） | `guard len(y) < 3` |

- 建议：把 §6 末句改为“guard `len(y) < 7`（len<3→naive，3≤len<7→MA3）”，
  与 T20 及 `short_history_eval.py` 一致。**本轮未改**（ownership 不含 summary）。
- 另注：T16 的 `combo_ew` MAE 9.928 未写入 §6；§6 的短历史数字来自 T9/T14
  （`attribute_errors`），口径（对齐方式/窗口集）不同，不构成数字矛盾。

### 8) forward_shadow_plan ↔ forward_shadow.py — **FAIL（5 处）**

| 文档要求 | 脚本实际 |
|---|---|
| §1 使用代码 `nested_eval.py` | 实际实现是 `forward_shadow.py` |
| §2 各候选 WAPE（每个候选 1 个值） | 只算 `selected` / `naive` / `ma3` |
| §2 各候选 Bias | 未实现 |
| §2 各候选覆盖率（上限列实测覆盖） | 未实现 |
| §2 零分母单元格数量**与占比** | 仅记录 `n_zero_demand_retained`，无占比 |

- 已一致项：零需求误差保留在分子；聚合总实际量为 0 才 `undefined_denominator`；
  缺标签输出 `labels_incomplete` + 逐 SKU 原因 + 重试日期；评分阶段不重新选模；
  `--data-cutoff/--origin` 参数化、预存清单、`--force` 防覆盖均保留。
- §3 的“连续 3 个月 / 区间不含 0”是**人工判定流程**，脚本只产出单次评分，
  文档未声称脚本自动判定，故不计失败。
- 建议：①文档 §1 改指 `forward_shadow.py`；②脚本补全五候选 WAPE/Bias/覆盖率与
  零分母占比（或把文档 §2 的“各候选”改为“selected/naive/MA3 三个对照”）。

## 3. superseded（不逐字比对）

| 文档 | 替代 | 原因 |
|---|---|---|
| `control/reviews/2026-10-22-t17-sensitivity.md` | `…t18-sensitivity-fix.md` | T17 正文“无全正量行”与数据矛盾，T18 已重分五类并更正。 |
| `control/reviews/2026-10-22-t16-short-history.md` | `…t20-guard.md` | T16 称 len 3–6 仍抛错；T20 已把 guard 扩到 len<7。 |
| `control/reviews/2026-10-22-t12-audit-fixes.md` | `…t14-recheck-fixes.md` | T12 的 M01 对齐 MAE / M02 早期块指标已被 T14 取代。 |

## 4. 处置建议（不改数）

1. check 7：只改 `summary_v3.md §6` 的 guard 措辞为 `len<7`（纯措辞，不动数字）。
2. check 8：改文档路径，或补脚本的五候选 WAPE/Bias/覆盖率与零分母占比；
   二者择一即可消除文档—脚本口径差。
3. 数字项全部 PASS；本审计**未改动任何 CSV/JSON/MD 数值**。

## 5. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/audit_consistency.py
uv run python scripts/check_secrets.py   # 无 finding、退出码 0
```

- 输入 sha256 全部写入 `consistency_audit.json`；脚本无 DB 访问、确定性。
- 8 项结果与差异表由脚本生成，可逐条复算。

## 6. 约束自检

| 约束 | 结果 |
|---|---|
| 只新增 `audit_consistency.py`、`consistency_audit.*` 与本记录 | ✅ |
| 未跑数据库重算（只读已有 CSV/JSON/MD） | ✅ |
| 未改任何数字产物；FAIL 只列差异与建议 | ✅ |
| 未改既有文档（含 summary/plan） | ✅ |
| 未改 control 下 HANDOFF/state/DECISIONS/NIGHT_PLAN/CONTROL/RESEARCH_ADOPTION | ✅ |
| 未访问生产、未扩样、未下单、未删数据、未合并 PR | ✅ |
| 未 push；只提交新增文件 | ✅ |
| 未提交原始明细与凭证；`check_secrets.py` 无 finding | ✅ |
| 不留临时文件（含 `__pycache__`） | ✅ |
