---
okf: v0.1
type: Task
title: 打工仔1｜全 SKU R3 返修：A 包归因 + 措辞边界 + 冻结 hash
date: 2026-10-23
owner: claude-worker
status: dispatched
base_commit: b9c9b4ed
review: 2026-10-23-fullsku-review.md（Codex #301，FAIL：1 major + 3 minor）
---

# 任务：全 SKU 主线 R3 窄返修

## 301 复审结论（已复核原文，照此修）

五项中 **1（bootstrap）/ 3（计数）/ 5（不宣称最优）PASS**；**2 措辞 PARTIAL**；**4 归因 FAIL**。
**数值、CI、计数全部可复现，不需要重跑 2000 次 bootstrap，不要改任何已通过的数字。**

### M01（唯一 major）· A 包树模型差异的归因错了

你写成「global_tree 差 −0.0002（取整）」——**不成立**。301 做了训练池消融：

| 实验（同算法/超参/切点/评分单元） | 树 WAPE |
|---|---|
| A 固定产物（`2b44cdbd`） | `0.49354508379541745` |
| 1328 全母集训练，仅在 A 的 2,763 单元评分 | `0.49333642687199925` |
| 精确差 | `−0.00020865692341820452` |
| 训练母集限定回 A 的 **1,237 mapped_eligible**，其余不变 | `0.49354508379541745`（**精确恢复 A 值**） |

→ 差异来自**训练母集 1,237 → 1,328 的全局重训**，不是评分交集，也不是取整。**同评分单元 ≠ 同预测模型**。

**要求**：
1. 把 `full_sku_selfaudit.py:363`、`out/business_phase/full_sku_selfaudit.md:79`、
   `control/reviews/2026-10-23-full-sku-selfaudit.md:80` 三处「取整差」全部改为
   「训练母集扩大导致重训预测变化」，并把上面四行消融证据写进报告。
2. **不要**改任何数值；**不要**把两个全局树说成同一拟合模型。
3. 若 `full_sku_selfaudit.json` 里有对应字段/文案，一并改（机器边界也要改，不只改 md）。

### N01（minor）· 分型时点措辞自相矛盾

- 仍是「分型只用训练窗内」的地方：`out/business_phase/full_sku_eval.json` 的 `boundaries[0]`、
  `full_sku_routing.py:270`、`out/business_phase/full_sku_routing.md:75`、`control/reviews/2026-10-23-full-sku-routing.md:92`。
- 统一改为：**「截至 2026-09 现状描述；对历史评估切点 not_point_in_time」**，并带 `as_of`。
- C 的边注：「支持充足」实际只表示 **SKU 曾进入本批共同评分单元**，**不是** SKU 级路由准确性或供给证据。
  措辞改为「曾进入本批评估（仅覆盖）」，不得当采购/效果证据。

### N02（minor）· 冻结 CSV 的本地 hash 与输入 manifest

- 301 无法对拍 `full_sku_classification.csv` / `final_bundle_routing.csv`（按 D33 不进公开仓库）。
- 产出**受控本地冻结**证据：给这两个 CSV 的**内容 hash（如 sha256）**、生成时间、行数、列清单，
  以及输入 manifest（DB 路径 + destinations + final_bundle 的 hash）。写进
  `out/business_phase/frozen_artifacts.json`（**只放 hash/元数据，不放行级数据**）与报告引用。
- 这样一来以后任何人都能验证"本地这份 CSV 就是当时那份"，而无需把业务数据提交。

### N03（minor）· 「树 Bias 最接近 0」不实

- `control/reviews/2026-10-23-full-sku-routing.md:54`：`naive` Bias `+0.00911639296205232` 比树 `−0.05174124072169076` **更接近 0**。
- 删掉该句，或把 WAPE 与 Bias **分开陈述**；不得用 WAPE 最低替代"多指标最优"。

## 硬约束

- 不重跑 bootstrap、不改已通过的数字与 CI；不需要重新训练。
- DB `read_only=True`；不访问生产、不扩样、不下单。
- **不 commit、不 push**（工头唯一提交者）；不跑 `update_index.py`；不新增依赖。
- 只改：`experiments/business_phase/forecast_eval/`、`out/business_phase/`、`control/reviews/2026-10-23-full-sku-*.md`。

## 验收

- 终端输出 `DONE FULLSKU-R3`。
- 报告附：四处（M01）+ 四处（N01）+ 一处（N03）**修复前后对照**；`frozen_artifacts.json` 的 hash 值；
  **明写"数值未变"**（若确实变了，必须解释）。
