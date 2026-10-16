---
okf: v0.1
type: Reference
title: 离线证据表 v3 · 4379 美中订单行的身份解析与取值来源（Codex 第四轮后）
description: 离线证据表 v3（修 Codex 第四轮 4 项）：逐行给出「命中原码/命中方式/候选/直连值+取值来源/旧路径值+取值来源/两路对比/处置分类」；取值来源**带时点**（bom_cost_verified vs unverified_*）；含完整版本清单
date: 2026-10-16
module: tongtool_order_cost
tags: [cost, ustx, evidence, offline, codex, reference]
---

# 离线证据表 v3 · 4379 美中订单行

> **状态**：**Codex 第四轮（只核 6 条）** 已审 v2，指出 4 项必须修（见 §3）；**v3 已修**。
> **仍然**：结论「表可直接采用」**不予通过** —— v3 的 `review_*` 桶就是**尚未获准**的部分，**不要整体推给财务逐行核实物**（其中一部分是代码/证据归类问题）。

## 0. v3 相对 v2 的 4 处修正（Codex 第四轮）

| # | Codex 指出 | v3 处置 |
|---|---|---|
| **1** | **来源标签混用**时点：`bom_cost` 只判「该物料**当前**有没有 BOM」，**不能证明 9/3 的值来自哪张 BOM** | 拆成 **`bom_cost_verified`**（当前 BOM 值与 9/3 值一致 → 可证）与 **`unverified_bom_changed` / `unverified_no_current_bom` / `no_item`**（不可证）→ 新增处置桶 **`review_source_unverified`** |
| **2** | **旧重量模板歧义仍取首条**（原 `setdefault`） | 改为**同键多 wt 一律阻断**：`ambiguous_weight_template`，**不解析旧路径值** |
| **3** | **`auto_ok` 不等于已批准**（含估值回退） | `auto_ok` **收窄**：来源不可证实的一律进 `review_source_unverified` |
| **4** | **T4 未完整锁版本** | manifest 补：**生成脚本 sha256 / 输出 sha256 / BOM 清单抓取时点 / 关联依据** |

> **关键诊断（由用户 2026-10-16 新导出 `EN产品BOM成本列表20261016.xlsx` 促成的结论）**：
> **20261016 导出值 vs 当前默认 BOM `total_cost` → 一致 240 / 不一致 0**。
> → **机制是对的**（**同一时点**上 `美中加工成本, USTX` ≡ 该时点 active+default BOM 的 `total_cost`）；
> → **9/3 与当前的差异是「时点漂移」，不是机制失效**。这也正是 Codex §1 的实质：**标签必须带时点**。

## 1. 产物

| 文件 | 说明 |
|---|---|
| `out/ustx_wage_sim/offline_evidence_ustx_rows_v3.csv` | **4379 行 × 17 列**（**评审对象，以 v3 为准**） |
| `out/ustx_wage_sim/offline_evidence_manifest_v3.json` | **T4 版本清单**（含脚本/输出哈希、两个时点、关联依据、别名规则版本） |
| `out/ustx_wage_sim/build_evidence_table_v3.py` | 生成脚本（**只读**，可复跑核对） |

## 2. 结果（v3，4379 行）

### 2.1 处置分类（**给业务的工作清单**）

| 处置分类 | 行数 | 含义 |
|---|---:|---|
| `auto_ok` | **3877** | 两路一致、且**来源可证**（`bom_cost_verified`）、非歧义 |
| **`review_source_unverified`** | **474** | **9/3 值无法由当前 BOM 证实**（BOM 变过 / 当前无 BOM / 无关联）—— **这是 Codex §1 的产物** |
| `review_value_diff` | **11** | 两路**都有值但不一致** |
| `review_bundle` | **4** | **五件套**（Product Bundle） |
| `review_ambiguous_customer_code` | **3** | 同一完整客户码多产品多值 → **阻断** |
| `business_exempt_zero` | **3** | 空 key 业务豁免（2 针线扣 + 1 棉包） |
| `review_ambiguous_weight_template` | **3** | **旧路径**同键多重量模板 → **阻断**（Codex §2 的产物） |
| `review_alias_pending` | **2** | 靠去 `-Cover` 才命中 → 别名待确认 |
| `review_direct_only` | **2** | 只有直连有值 |
| **合计** | **4379** | 无静默丢行 |

> **业务只需看 502 行**（= 4379 − 3877）。**其中 474 行是「来源不可证」，不是「费用错」**——先分类，再决定是否逐行核。

### 2.2 直连/旧路径取值来源

| 直连取值来源 | 行数 | | 旧路径取值来源 | 行数 |
|---|---:|---|---|---:|
| `bom_cost_verified` | 3894 | | `bom_cost_verified` | 3893 |
| `no_item`（产品编号无 USTX 包装成品） | 306 | | `no_item` | 289 |
| `unverified_bom_changed` | 87 | | `unverified_no_current_bom` | 81 |
| `unverified_no_current_bom` | 82 | | `unverified_bom_changed` | 69 |
| `no_customer_code` | 7 | | `no_weight_template` | 44 |
| `ambiguous_customer_code` | 3 | | `ambiguous_weight_template` | 3 |

### 2.3 两路对比

`same 4308 / direct_only 44 / DIFF 17 / neither 7 / old_only 3`（合计 4379）。
> 注意：`DIFF 17` 已**扣除** 3 行旧路径歧义（它们现在单独归 `ambiguous_weight_template`）。

## 3. 我对 Codex 第四轮的**完整接受**（含我此前的口径错误）

- ✅ §1 来源时点 —— 接受（我已用你的 20261016 导出**反证**：同时点 240/240 一致）
- ✅ §2 旧 WT 歧义仍取首条 —— 接受，已阻断
- ✅ §3 `auto_ok` 过宽 —— 接受，已收窄
- ✅ §4 T4 未锁全 —— 接受，已补
- ✅ **「405 行」算错**（应为 404；v3 为 **502**）
- ✅ **`old_only` 是 3 不是 0**（我 v2 已按 3 报；更早口径有误）
- ✅ **「T1–T4 全部落地」说早了** —— 主要缺口正是**来源时点**与**计算版本**

## 4. 对 **7–9 月**的实际影响（实测）

把同一套分桶逻辑套到 8/9 月订单（**只读 GS**：`通途订单202608/202609` 的 `写回2026年N月订单`）：

| 处置分类 | 2026-07（4379 行） | 2026-08（5479 行） | 2026-09（2959 行） |
|---|---:|---:|---:|
| `auto_ok` | 3894 | 4822 | 2172 |
| **`review_source_unverified`** | **475（10.8%）** | **632（11.5%）** | **736（24.9%）** |
| `review_ambiguous_customer_code` | 3 | 9 | 8 |
| `business_exempt_zero` | 3 | 7 | **38** |
| `review_bundle` | 4 | 5 | 0 |
| `review_no_customer_code` | 0 | 4 | 5 |

**三条结论**：
1. **`review_source_unverified` 三个月都是最大桶**（10.8% / 11.5% / 24.9%）。
   ⚠️ **但它不是「费用错」** —— 机制已被 **240/240** 证明；它只表示「**用 10-15 的 BOM 无法证实 9/3 的值**」。
2. **9 月占比翻倍到 24.9%**，**大概率是「映射时点」造成的假象**：8/9 月我用的仍是 **9/3 冻结的客户码映射**，
   而 9 月订单**晚于**该快照 → 时点错得更远。**这正好再次印证：一切都要带时点。**
3. **真正需要业务判断的很少**：`ambiguous + bundle + exempt + no_customer_code` = **10 / 25 / 51 行**。

> ⚠️ **口径保留**：8/9 月用的是 **9/3 冻结映射**，属跨时点套用，**结论只能作指示**；
> 要精确必须**按当月重新冻结映射与 BOM 状态**（这正是「分月冻结」的意义）。

## 5. 未证实

- **`review_source_unverified` 的真实来源**（要回放各月**当时**的 BOM 才能证）——**这是最大的未证实块**。
- 8/9 月的精确数字（受 9/3 映射套用影响）。
- 各桶的业务最终归属。
- 7 月当时的登记状态（[20](20-codex-round3-corrections.md) §6）。
