---
okf: v0.1
type: Design
title: 服务分档政策（P2a）：ABC×XYZ → A/B/C/D → q95/q90/q85
description: 用 D3b v3.11 分类 + 2026 销量做 ABC×XYZ，输出 service_policy，并接入 D6 v6.23 按 class 选分位
tags: [forecast, service-level, abc-xyz, policy, d6]
date: 2026-11-12
status: accepted
---

# 服务分档政策（P2a）

> 只做服务分档，不动 D5 窗口、不改 CNY、不写生产。

## 1. 输入 / 输出

| 项 | 路径 |
|---|---|
| 分类 | `D3b-v3_11-20261112/…D3b_v3_11_2026-11-12.xlsx` → `3_分类` |
| 2026 销量 | `D3b_v3_11_series_current_2026-11-12.parquet`（2026-01..10） |
| 政策 CSV | `analysis/service-policy-20261112/service_policy_20261112.csv` |
| 政策报告 | `analysis/service-policy-20261112/service_policy_20261112_报告.md` |
| D6 v6.23 | `scripts/d6_top50_sandbox_v6_23_20261112.py` |
| D6 输出 | `analysis/D6v6_23-1112/` |
| 动作对比 | `analysis/D6v6_23-1112/action_diff_vs_v6_22_报告.md` |

生成器：`scripts/build_service_policy_20261112.py`；纯函数：`supply_netting/service_policy.py`；
测试：`tests/service_policy/test_service_policy.py`。

## 2. 方法

- **ABC**：2026 销量降序累计 **80/15/5**；跨过 80% 的那一件留在 A（A 可略超 80%）。
- **XYZ**：X=`smooth`；Y=`intermittent`；Z=`lumpy/erratic/n/a` 或
  `obsolescent/new/short/no_demand`（用训练期 `sbc_class_train`/`demand_pattern_train`，不用 holdout）。
- **A/B/C/D**：A(X/Y)=A；A(Z)/B(X/Y)=B；B(Z)/C(X/Y)=C；C(Z)、零销量、新品、淘汰、短史=D。
- **分位**：A q95 / B q90 / C q85 / D q85。D 的 q85 是 **fill-rate 代理**，尚未直接算 fill-rate。
- 未知 class 不自动补：D6 遇到 missing/unknown 时 `net_selected=NaN`，动作转“观察”。

政策 CSV 列：`sku,pool,physical_form,canonical_uom,class,abc_class,xyz_class,
service_level_prior,quantile,quantile_label,basis,sales_2026,sales_share,cum_share,
demand_pattern,sbc_class,adi,cv2,n_obs_train,n_pos_train`。

## 3. 结果

| class | 键数 | 2026 销量 | 销量占比 | quantile |
|---|---:|---:|---:|---:|
| A | 148 | 30,246 | 39.9% | 0.95 |
| B | 323 | 32,900 | 43.4% | 0.90 |
| C | 390 | 5,307 | 7.0% | 0.85 |
| D | 888 | 7,324 | 9.7% | 0.85 |

ABC×XYZ（键数）：A/X 147、A/Y 1、A/Z 140；B/X 172、B/Y 27、B/Z 151；
C/X 55、C/Y 291、C/Z 765。

## 4. D6 v6.23 接入

- 读 `--service-policy`，按 key join `service_class/quantile/quantile_label`。
- 动作/数量使用 `net_selected`（A→net_95、B→net_90、C/D→net_85）；`net_95` 列保留作敏感性。
- 自检：class→quantile 一致、未知/缺失 class 不生成补/催、`net_used=net_selected`、selected 净额可复算；全部 PASS。
- 与 v6.22（全 q95）对比：1571 共同键，动作变化 **250**（补→不补），数量变化 **1006**；
  总建议数量 **39,834 → 19,404（−20,430）**。墙围 4 SKU 全为 B/q90：
  DM-60 波兰 66→49、KJB-60 波兰 260→192、KJB-90-BEIGE 波兰 456→428、
  KJB-90-DEEPGREY 波兰 124→95。

## 5. 边界

- 本层只做 **政策先验**，不是统计最优服务；A/B/C/D 的 CSL 需用 PIT/覆盖率回测校准（P2b）。
- D 的 fill-rate 尚未实现；当前用 q85 代理，不能对外称“fill-rate 95%”。
- 不改 D5 的 97/157 窗口；不改 CNY/pre-build；不写 EN/通途。
