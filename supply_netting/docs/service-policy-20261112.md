---
okf: v0.1
type: Design
title: 服务分档与预设（P2a/P2c）：ABC×XYZ → A/B/C/D → q95/q90/q85
description: 三预设（balance/control/service）+ 例外覆盖 CSV + D6 v6.24 + USNJ 试点包
tags: [forecast, service-level, abc-xyz, policy, d6, usnj, cny]
date: 2026-11-12
status: accepted
---

# 服务分档与预设（P2a/P2c）

> 只做服务分档/预设，不动 D5 窗口、不改 CNY 排产、不写生产。

## 1. 输入 / 输出

| 项 | 路径 |
|---|---|
| 分类 | `D3b-v3_11-20261112/…D3b_v3_11_2026-11-12.xlsx` → `3_分类` |
| 2026 销量 | `D3b_v3_11_series_current_2026-11-12.parquet`（2026-01..10） |
| 政策 CSV | `analysis/service-policy-20261112/service_policy_20261112.csv` |
| 政策报告 | `analysis/service-policy-20261112/service_policy_20261112_报告.md` |
| D6 v6.23 | `scripts/d6_top50_sandbox_v6_23_20261112.py` |
| D6 v6.24 | `scripts/d6_top50_sandbox_v6_24_20261112.py` |
| D6 v6.24 输出 | `analysis/D6v6_24-1112/`（balance 主包；`control/`、`service/` 子目录） |
| USNJ 试点包 | `analysis/usnj_replenishment_pilot_20261112.xlsx` + 同名目录 |

生成器：`scripts/build_service_policy_20261112.py`；纯函数：`supply_netting/service_policy.py`；
USNJ 包：`scripts/build_usnj_pilot_20261112.py`；对比：`scripts/compare_usnj_pilot_20261112.py`；
测试：`tests/service_policy/test_service_policy.py`。

## 2. 方法

- **ABC**：2026 销量降序累计 **80/15/5**；跨过 80% 的那一件留在 A（A 可略超 80%）。
- **XYZ**：X=`smooth`；Y=`intermittent`；Z=`lumpy/erratic/n/a` 或
  `obsolescent/new/short/no_demand`（用训练期 `sbc_class_train`/`demand_pattern_train`，不用 holdout）。
- **A/B/C/D**：A(X/Y)=A；A(Z)/B(X/Y)=B；B(Z)/C(X/Y)=C；C(Z)、零销量、新品、淘汰、短史=D。
- **分位**：A q95 / B q90 / C q85 / D q85。D 的 q85 是 **fill-rate 代理**，尚未直接算 fill-rate。
- 未知 class 不自动补：D6 遇到 missing/unknown 时 `net_selected=NaN`，动作转“观察”。

### 2.1 三预设

| preset | A | B | C | D |
|---|---|---|---|---|
| `balance`（默认） | q95 | q90 | q85 | q85 |
| `control` | q95 | q85 | q85 | q85 |
| `service` | q95 | q95 | q90 | q85 |

- D6 `--preset balance|control|service`；默认 balance。
- 覆盖 CSV：`sku,pool,preset_or_quantile,reason,owner,as_of`；`preset_or_quantile` 可为
  preset 名、`q95/q90/q85/fill_rate` 或 0–1 数值。override 按 **sku×pool** 作用到该
  SKU×池下所有形态/UOM；未知键、重复键、空 reason/owner、非法值直接报错。
- 审计列：`preset/override_applied/override_value/override_reason/override_owner/override_as_of/override_status`；
  另出 `service_policy_overrides_audit_*.csv`。

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

## 5. D6 v6.24 + USNJ 试点包

- D6 v6.24 读 `--preset` + `--service-overrides`，动作/数量仍用 `net_selected`；
  `net_95` 保留敏感性；自检增加 preset→quantile、override 审计完整、未知 preset。
- USNJ 对比（296 键）：
  - v6.22(q95)：151 补 / 91 不补 / 35 催 / 19 观察；建议量 **7,945**，净需求 **9,716**。
  - v6.23(balance)：115 / 127 / 35 / 19；**4,180**，净需求 **5,842**。
  - v6.24(balance)：与 v6.23 相同（设计如此）。
  - v6.24(control)：108 / 134 / 35 / 19；**3,815**。
  - v6.24(service)：130 / 112 / 35 / 19；**5,496**。
- 全公司 250 个「补→不补」中 **USNJ 36 个**；按 v6.23 服务档 C13/D12/B11。
- USNJ 包：B 归属 **299** 产品；待确认 **282**（229 unassigned + 53 exception）；
  补货建议 **296** 行；特殊产品 **225**；三角靠枕 **173**；CNY 优先 **173**。
  B 清单标记：正常 234、`错/多/待确认` 53、`待确认` 12。
- 30/90 天销量为月度口径（2026-10 / 2026-08..10）；未知 C 供给标“待核”，不当 0。
- CNY：停工 2027-01-24 → 复工 2027-02-22 → 首批到货 2027-05-04（174 天）；
  97/157 窗均不足，需 D5 183 天窗/pre-build；三角靠枕优先。
- 特殊产品：三角按当前 owner（不把已迁走面料算回 USNJ）；麻将沙发/铁架/印花/短历史
  **沿用原模型，未做相似品/池化预测**，标低置信，需人工用相似品复核（不挂“相似品”名头）。
- 回测只展示该行 `采用模型` 在 D3b as-of 源键的 validation/holdout WAPE；无同模型回测显示 `—`。
  本轮 296 行中 **192 行有同模型回测、104 行 `—`**，不再混用别的模型成绩。
- CNY：`157天净需求_参考(非bridge)` 只是参考；**bridge 备货量标“待核（需 D5 183 天窗）”**，
  不把 157 当 bridge。
- 覆盖 CSV：文件缺失直接报错；reason/owner/as_of 为 NaN 也拒绝；数值分位只接受
  0.95/0.90/0.85（0.851 会被拒绝），避免把 0.851 标成 q85。
- **4 周是上线后的监控期，不是等待期；包已现在出。**

## 6. 边界

- 本层只做 **政策先验**，不是统计最优服务；A/B/C/D 的 CSL 需用 PIT/覆盖率回测校准（P2b）。
- D 的 fill-rate 尚未实现；当前用 q85 代理，不能对外称“fill-rate 95%”。
- 不改 D5 的 97/157 窗口；不改 CNY/pre-build；不写 EN/通途。
