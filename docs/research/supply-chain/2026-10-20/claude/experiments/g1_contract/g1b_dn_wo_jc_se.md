---
okf: v0.1
type: Experiment-Results
title: G1b 窄范围 DN/WO/JC/SE 关联与数量守恒（5 个客户码快照，v2 返修）
description: 复用已有 EN 快照做 DN→SO、WO→SO 行、JC→WO、SE→WO 连边；逐行全精度 C1、UOM 分区、SE 元数据与覆盖完整性、原始行账 C4；produced_qty 不可作完工账
date: 2026-10-21
updated: 2026-10-21
tags: [supply-chain, g1b, dn, work-order, job-card, stock-entry, conservation, evidence]
---

# G1b 窄范围 DN/WO/JC/SE 关联与数量守恒（v2）

> 边界：这是**窄样本的关联/守恒契约证据**，不是 G1 验收，不是需求或补货数量，
> 不扩全 family，不写生产。所有行级输出留本地证据包，仓库只提交脚本、单测与本文件。
>
> **v2 返修**：适配器复审（`control/reviews/2026-10-21-adapter-report.md`，6 P1 + 3 P2）
> 打回 `22ae9a1e` 后，按 9 项发现收紧契约；旧证据 `evidence_v1.zip` 与旧 manifest 哈希作废。

## 0. v2 契约变更（对应复审发现）

| # | 复审发现 | v2 契约 | 反例覆盖（`test_g1b_dn_wo_jc_se.py`） |
|---|---|---|---|
| P1-1 | 聚合掩盖单行失败 | **C1 逐行全精度**判定；`delivered_qty == dn_net` 不四舍五入，任一行 false 即 C1 false；UOM 汇总只作展示 | `C1PerLinePrecisionTests`：正负抵消、0.004 舍入、audit 逐行 |
| P1-2 | 失效引用仍回退 | DN 仅在 `so_line_id` **缺失**时才按 `so+item` 唯一匹配；显式引用不存在→`dn_so_line_ref_not_found`；精确引用也校验 `item_code`→`dn_item_mismatch` | `DnJoinTests` 4 例 |
| P1-3 | UOM 缺失/混算 | DN/SO UOM 缺失→unverified；SE finished 行 UOM 不一致→`se_finished_uom_mixed`；C1/C2/窗口/关联量全部按 UOM 分区，绝不出现跨单位总量 | `UomPartitionTests` 5 例 |
| P1-4 | 缓存明细不看父元数据 | 合并前校验 `docstatus / work_order / stock_entry_type=Manufacture / posting_date`，且 `fetched_at` 不得早于快照 `generated_at`；漂移一律 unverified | `SeMetadataTests` 6 例 |
| P1-5 | 查询失败/缺失明细仍显示完整 | `se_query_error` 与每个未解决已提交 SE 传播到 WO、C2 `complete`、`audit_ok`、`evidence_complete`；C2 另出 `known_subtotal` | `SeCoverageTests` 5 例 |
| P1-6 | C4 不证明每个输入有去向 | C4 数**原始输入行**（含非对象行）；非对象→rejected、快照外 WO 的 JC 组→orphan；业务键与 `se_line`/`jc_operation` 子键全局唯一 | `C4RawLedgerTests` 4 例 |
| P2-7 | 有符号退货被当成非法 | `is_return=1` 一律取 `abs(qty)` 后只扣减一次；非退货负数仍 invalid；行内记录 `qty_raw / sign_normalized` | `SignedReturnTests` 3 例 |
| P2-8 | HTTP 预算不含探针/重试/翻页 | `HttpBudget` 是**请求级**总预算，SE 明细、探针、翻页、连接重试共用；耗尽显式记 `budget_exceeded` 并 partial | `HttpBudgetTests` 6 例（mock） |
| P2-9 | 校验和漏掉 `stable_sha256` | `finalize_manifest()` 先写 `stable_sha256`，再对最终 manifest 计算 `payload_sha256` | `PayloadHashTests` 4 例 |

单测 **78 条**全部离线通过（含上述反例；HTTP 用 mock，不联网）。

## 1. 范围与输入

复用已落盘的 `g1b_en_extract.py` 快照，**不重跑 SO/DN/WO/JC 查询**；
仅对快照里缺 line 明细的 Stock Entry 做**按单据名逐单 GET**（有界只读）。

| 快照 | 客户码 | 捕获时间 | SO 行 | DN 行 | WO | SE |
|---|---|---|---:|---:|---:|---:|
| `g1b_en_top_1.json` | CENCord995-DKGrey-97 | 2026-10-20 18:12 | 19 | 29 | 23 | 87 |
| `g1b_en_top_2.json` | CEN003-DPBLUE-100 | 2026-10-20 18:13 | 15 | 21 | 21 | 101 |
| `g1b_en_top_7.json` | C/Cord-Grey-100-710-wow | 2026-10-20 18:17 | 18 | 40 | 17 | 63 |
| `g1b_en_top_9.json` | TT0000671K0063721 | 2026-10-20 18:19 | 42 | 103 | 45 | 111 |
| `g1b_en_rr2.json` | C/Linen-Natural-194-688-wow | 2026-10-21 11:08 | 26 | 100 | 22 | 63 |
| **合计** | 5 / 10 个 top SKU | — | **120** | **293** | **128** | **425** |

窗口 `2026-04-01..2026-09-30`（`--date-basis delivery`）只作**分区**，不过滤行：
窗内 47 行 / 5,885 件（已发 3,170，未发 2,715）；窗外 73 行 / 5,121 件
（已发 5,297，未发 −176，历史超发的负未发量保留不截零）。

EN 只读：历史取回 **362 次 SE 明细 GET**（425 条 SE 中 362 条需按单据名补明细，
其余 63 条快照自带 `lines`；0 失败，全部 200；取回时间 2026-10-21 09:58–10:01 UTC）。
**本轮 v2 证据为离线复跑（`--reuse-se-details`），0 次网络请求**；
`http_budget.used=0`。请求级预算契约由单测覆盖（翻页按页计、连接重试按次计、
明细与探针共享上限 500），在线路径下次运行才实际消耗。

## 2. 关联规则（只认精确键，不猜）

| 边 | 规则 | 失败去向 |
|---|---|---|
| DN → SO 行 | `so_line_id` 精确命中且 `item_code` 一致；**仅当引用缺失**才按 `so + item_code` 唯一匹配 | `dn_so_line_ref_not_found` / `dn_item_mismatch` / `dn_item_ambiguous` / `dn_item_not_found` / `dn_item_missing` / `dn_no_so_ref` |
| WO → SO 行 | `sales_order` + `production_item` 精确；多行候选 → `ambiguous`，**不摊量** | `wo_no_sales_order` / `wo_sales_order_out_of_snapshot` / `wo_so_line_item_mismatch` |
| JC → WO | 工序卡 `work_order` 键（快照已聚合到工序） | `jc_missing` / `jc_work_order_out_of_snapshot`（orphan） |
| SE → WO | `work_order` 键 + 父元数据校验 | `se_unlinked_work_order` / `se_work_order_out_of_snapshot` / `se_detail_*_drift` |
| SE finished 行 → WO 成品 | `item_code == production_item`、`uom == stock_uom`、同一 SE 内 finished 行 UOM 唯一 | `se_line_item_mismatch` / `se_line_finished_uom_mismatch` / `se_finished_uom_mixed` |

### 关联结果

| 指标 | 结果 |
|---|---:|
| DN 行成功挂到 SO 行 | 292 / 293（余 1 张 `dn_cancelled`，不计净量；无失效引用/物料冲突） |
| WO 挂到 SO 行 | 90 / 128（70.3%） |
| WO 无 SO（备货工单） | 30 张 / 2,666 件（UOM 未知，单列） |
| WO 指向快照外 SO | 8 张 / 190 件（UOM 未知，单列） |
| SO 行至少 1 张 WO | 89 / 120 行 |
| WO 数量按关联（UOM 分区） | linked `个` 7,686；备货 `unknown` 2,666；快照外 `unknown` 190 |
| SE 挂到快照内 WO | 425 / 425 |
| SE 父元数据一致 | 425 / 425（`docstatus/work_order/entry_type/posting_date/fetched_at` 全通过） |
| SE finished 行身份与单位 | 425 / 425 一致 |

> 关键事实：**约 1/4 的工单量不来自销售订单**（备货/预测投产），
> 另有少量工单指向快照外 SO。SO 行与 WO 不能做 1:1 摊量，只能按“可归属量”使用。
> 未挂 SO 的工单量没有可信 UOM，v2 放进 `unknown` 桶，**不与 `个` 相加**。

## 3. 数量守恒（同 UOM 才求和，C1 逐行全精度）

| 式 | 口径 | 结果 |
|---|---|---|
| C1 SO↔DN | **每行** `delivered_qty` == 已提交 DN 净量（非退货 − 退货），全精度；再按 UOM 分组展示 | **115 / 115 行通过**，0 失败、0 未决；5 行作废单排除。UOM `个` 合计 8,467 = 8,467 |
| C2 WO↔SE | `WO.produced_qty` == 已提交 Manufacture SE finished 行合计；SE 覆盖完整才算完整总数 | 117 张可比较：115 通过，**2 不一致**；11 张未开工；0 未解决 SE；`complete=true` |
| C3 SE 内部 | Σ finished 行 == `SE.finished_qty` | **425 / 425 通过**，0 unverified |
| C4 行账 | **原始输入行** == 逐行去向（含 rejected/orphan），键唯一 | `so 120/120`、`dn 293/293`、`wo 128/128`、`se 425/425`；派生 `se_line 558`、`jc_operation 516`；0 rejected、0 重复键 |

- 全部 5 个快照的已知 UOM 都是 `个`；代码仍强制按 UOM 分区，缺失/未知 UOM 直接 unverified。
- SO 行恒等式 `qty == delivered + open` 逐行成立（0 例反例）；`open<0` 的超发 16 行原样保留。
- 19 张 WO 出现 `SE finished > WO qty`（超产 1–11 件，最大 161/150），属正常超产，不截断。
- `audit_ok=true`、`evidence_complete=true` 的前提是：C1 每行通过且无未决、C3 无 mismatch/unverified、
  行账全对、无重复键、无 rejected 行、**所有已提交 SE 都已解决**（本轮 425/425）且无 `se_query_error`。
- C2 的 2 处 mismatch 不阻止 `audit_ok`（`produced_qty` 已知不可靠，见下节），但会阻止把
  “C2 全部通过”写成结论；v2 另给 `known_subtotal` 与 `complete` 两个字段区分口径。

### C2 的两处不一致（均为 `produced_qty` 失真）

| WO | WO qty | produced_qty | SE finished | 探针结果 |
|---|---:|---:|---:|---|
| WO-26-00291 | 100 | **739** | 103 | 15 张已提交 Manufacture SE 合计 103；另有 30 张 Material Consumption（15 已提交、15 草稿）；无可见单据能解释 739 |
| WO-26-00249 | 100 | **812** | 100 | 7 张已提交 Manufacture SE 合计 100；13 张 Material Consumption（6 已提交、7 草稿）；无可见单据能解释 812 |

结论（写入 manifest `wo_produced_qty`）：**`Work Order.produced_qty` 在本部署不能当完工账**，
完工量以**已提交 Manufacture SE 的 finished 行合计**为准。两处差异不是本工具的求和错误
（C3 与 SE 行证据同时成立），而是源字段不可解释。

## 4. JC 只作进度证据，不作守恒

- 516 个工序组；124 / 128 张 WO 有工序组（4 张无卡：含未开工/草稿）；0 个 JC 组指向快照外 WO。
- **21 张 WO 的 routing 末道不是完工道**：末道常是 `通用返工` / `质检发现问题`，
  其数量只有 2–4 件；主工序在 100–107 件。例：WO-26-00291 末道 2 件、
  `质检` 103 件、工序最大 107 件，而 SE 完工 103 件。
- 工序卡按批量/返工重复开卡，同 WO 内各主工序合计也可能差 2 件（105 vs 107）；
  因此 **JC 不能与 SE 做数量守恒**，旧 `last_op_qty` 更不是完工量。
  本工具给每条 `jc_operation` 记 `jc_progress_evidence_only`，并给 WO 打
  `jc_routing_final_op_not_completion` / `jc_missing` 标记，供运营侧参考。
- v2 起，快照外 WO 的 JC 组不再消失：逐组落 `orphan`（`jc_work_order_out_of_snapshot`），
  并计入 C4 的 `jc_groups` 统计。

## 5. 逐行去向

`out/dn_wo_jc_se/line_dispositions.jsonl`（2,040 行，本地证据包）每行带：
`row_type / row_key / link{so,dn,work_order,jc_ids,se,so_line_key,...} / qty / uom /
in_window / disposition / reason_code / reason_detail`。
守恒相关行同时带 `qty_exact`（未四舍五入的原值），供复核逐行判定。

| row_type | 行数 | 去向分布 |
|---|---:|---|
| `so_line` | 120 | conserved 115（`dn_conserved` 97 + `no_dn` 18）、excluded 5（作废单） |
| `dn_line` | 293 | linked 292（`dn_submitted`）、excluded 1（`dn_cancelled`） |
| `wo` | 128 | conserved 115、mismatch 2、open 11（未开工/草稿） |
| `se` | 425 | conserved 425（全部 line 级同单位证据 + 元数据校验通过） |
| `se_line` | 558 | 成品 conserved 425、非成品 excluded 133 |
| `jc_operation` | 516 | progress 516（不参与守恒） |

## 6. 证据包与哈希（v2）

| 产物 | SHA256 |
|---|---|
| `out/dn_wo_jc_se/association_manifest.json` | `5d3fdabba86d9a02a0b9a8d4c597578f4c6e2037e654bf7b049482d4621dc6e7` |
| `out/dn_wo_jc_se/line_dispositions.jsonl` | `2941ea1c6a0bbcc467ce97fd1a941634cd4c5bfafcccd5de871657ba1c25a763` |
| `out/dn_wo_jc_se/se_details.json` | `7308504794270516b246a92239e8650799013c3d0b7cb26507d58b6267a33a88` |
| `out/dn_wo_jc_se/wo_probe.json` | `11ab1606c21a9c509cc6f64eb0bba3a25ed271c4da72cca3ca45a22a37372e80` |
| `out/dn_wo_jc_se/snapshots_manifest.json` | `62539638c834eb6f55d6dffeefe10dc5950debfc40c7d2c13ad3e98cb745f10e` |
| `out/dn_wo_jc_se/run.log` | `f21cfd12f47ea59b1543257b7c021368b30b95b237eb7d9688eacf1745a9df89` |
| `out/dn_wo_jc_se_evidence_v2.zip` | `a0d8bb45c7f7e5e1269c8f688727b3d1c27059dd22fe73769baf69c8ca399384` |

- manifest `payload_sha256`：`457ccf1e1c549bd5e7fae3df430ce26ad45e7be193d914c16a341198f8acfa97`。
  该值在写入 `stable_sha256` **之后**对最终 manifest 计算；复核方式：
  `canonical_sha({k: v for k, v in manifest.items() if k != "payload_sha256"})`。
- `se_details.json` 的 `detail_records=362 / detail_records_ok=362`；最后几次复跑
  `requested=0` 表示命中本地缓存。
- 稳定摘要 `stable_sha256`（去 run_id/as_of/在线探针/预算事件/enrichment 日志）：
  **`c45a08383be407e3e32f559300cdd0161d3bfa5baa88524558b5ad2394a1782a`**。
- 重复回放：同一缓存连跑两次（run_id 不同），`stable_sha256` 与
  `line_dispositions.jsonl` SHA256 完全相同（R1/R2 通过）。
- 快照 SHA256 记录在 `snapshots_manifest.json`；输入未被修改。
- SE 明细取回时快照与当前 `docstatus` **0 漂移**；C3 全绿说明 `finished_qty` 与行合计一致。
- 旧 v1 证据（zip `e557e0ae…`、manifest `c5fc5499…`、行去向 `436bfa97…`）**作废**，仅留作返修对照。

## 7. 复现

```bash
cd docs/research/supply-chain/2026-10-20/claude/experiments/g1_contract

# 离线（复用已有 SE 明细，不联网）
uv run python g1b_dn_wo_jc_se.py \
  --snapshot out/g1b_en_top_1.json --snapshot out/g1b_en_top_2.json \
  --snapshot out/g1b_en_top_7.json --snapshot out/g1b_en_top_9.json \
  --snapshot out/g1b_en_rr2.json --out-dir out/dn_wo_jc_se \
  --reuse-se-details

# 有界 EN 只读（补齐 SE 明细 + 探针），需 EN 凭证
uv run python g1b_dn_wo_jc_se.py ... --enrich-se --probe-mismatch-wos 5 \
  --max-http 500 --sleep 0.2 --env-file <主仓库>/EN_API/.env

# 单测（78 条，不联网；HTTP 用 mock）
uv run python -m unittest test_g1b_dn_wo_jc_se
```

## 8. 未做 / 边界

- 只覆盖 5 个 top SKU 快照（120 SO 行），**不是全 family**；未扩样。
- SE 集合来自快照，未重查“快照之后新建的 SE”；C2 的 `complete=true` 只表示
  **已提交 SE 集合在快照范围内全部解决**，不等于 EN 侧不存在快照外新建 SE。
- 未做 SO 行级事件去重、未输出终端需求/补货量。
- 未改 `en_family_poc.py` 的 SO 证据门；未重开 U01 / 旧 T。
- 本文件不是 G1 验收；G1 与业务接受仍由既定评审流程决定。
