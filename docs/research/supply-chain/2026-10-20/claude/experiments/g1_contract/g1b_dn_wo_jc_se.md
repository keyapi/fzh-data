---
okf: v0.1
type: Experiment-Results
title: G1b 窄范围 DN/WO/JC/SE 关联与数量守恒（5 个客户码快照）
description: 复用已有 EN 快照做 DN→SO、WO→SO 行、JC→WO、SE→WO 连边；同 UOM 守恒 C1/C2/C3 与逐行去向；produced_qty 不可作完工账
date: 2026-10-21
tags: [supply-chain, g1b, dn, work-order, job-card, stock-entry, conservation, evidence]
---

# G1b 窄范围 DN/WO/JC/SE 关联与数量守恒

> 边界：这是**窄样本的关联/守恒契约证据**，不是 G1 验收，不是需求或补货数量，
> 不扩全 family，不写生产。所有行级输出留本地证据包，仓库只提交脚本、单测与本文件。

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

EN 只读预算：SE 明细 **362 次 GET**（198 + 164，0 失败，全部 200）；
异常 WO 探针 **4 次**（2 张 WO 详情 + 2 次 SE 清单）。单并发、间隔 0.2s、上限 500。

## 2. 关联规则（只认精确键，不猜）

| 边 | 规则 | 失败去向 |
|---|---|---|
| DN → SO 行 | `so_line_id` 精确命中；为空时才按 `so + item_code` **唯一**匹配 | `dn_unlinked_so_line` |
| WO → SO 行 | `sales_order` + `production_item` 精确；多行候选 → `ambiguous`，**不摊量** | `wo_no_sales_order` / `wo_sales_order_out_of_snapshot` / `wo_so_line_item_mismatch` |
| JC → WO | 工序卡 `work_order` 键（快照已聚合到工序） | `jc_missing` |
| SE → WO | `work_order` 键 | `se_unlinked_work_order` / `se_work_order_out_of_snapshot` |
| SE finished 行 → WO 成品 | `item_code == production_item`、`uom == stock_uom` | `se_line_item_mismatch` / `se_line_finished_uom_mismatch` |

### 关联结果

| 指标 | 结果 |
|---|---:|
| DN 行成功挂到 SO 行 | 292 / 293（余 1 张 `dn_cancelled`，不计净量） |
| WO 挂到 SO 行 | 90 / 128（70.3%） |
| WO 无 SO（备货工单） | 30 张 / 2,666 件 |
| WO 指向快照外 SO | 8 张 / 190 件 |
| SO 行至少 1 张 WO | 89 / 120 行 |
| WO 数量按关联：linked / no_so / outside | 7,686 / 2,666 / 190（总 10,542） |
| SE 挂到快照内 WO | 425 / 425 |
| SE finished 行身份与单位 | 425 / 425 一致 |

> 关键事实：**约 1/4 的工单量不来自销售订单**（备货/预测投产），
> 另有少量工单指向快照外 SO。SO 行与 WO 不能做 1:1 摊量，只能按“可归属量”使用。

## 3. 数量守恒（同 UOM 才求和）

| 式 | 口径 | 结果 |
|---|---|---|
| C1 SO↔DN | 每行 `delivered_qty` == 已提交 DN 净量（非退货 − 退货）；按 UOM 分组 | **5/5 scope 通过**，合计 8,467 = 8,467（`个`） |
| C2 WO↔SE | `WO.produced_qty` == 已提交 Manufacture SE finished 行合计 | 117 张可比较：115 通过，**2 不一致**；11 张未开工；0 缺证据 |
| C3 SE 内部 | Σ finished 行 == `SE.finished_qty` | **425 / 425 通过** |
| C4 行账 | 读入行 == 逐行去向（按 row_type） | `so 120/120`、`dn 293/293`、`wo 128/128`、`se 425/425`；派生 `se_line 558`、`jc_operation 516` |

- 全部 5 个快照的 UOM 都是 `个`；C1 代码按 UOM 分组，跨 UOM 不出合计。
- SO 行恒等式 `qty == delivered + open` 逐行成立（0 例反例）；`open<0` 的超发 16 行原样保留。
- 19 张 WO 出现 `SE finished > WO qty`（超产 1–11 件，最大 161/150），属正常超产，不截断。

### C2 的两处不一致（均为 `produced_qty` 失真）

| WO | WO qty | produced_qty | SE finished | 探针结果 |
|---|---:|---:|---:|---|
| WO-26-00291 | 100 | **739** | 103 | 15 张已提交 Manufacture SE 合计 103；另有 30 张 Material Consumption（15 已提交、15 草稿）；无可见单据能解释 739 |
| WO-26-00249 | 100 | **812** | 100 | 7 张已提交 Manufacture SE 合计 100；13 张 Material Consumption（6 已提交、7 草稿）；无可见单据能解释 812 |

结论（写入 manifest `wo_produced_qty`）：**`Work Order.produced_qty` 在本部署不能当完工账**，
完工量以**已提交 Manufacture SE 的 finished 行合计**为准。两处差异不是本工具的求和错误
（C3 与 SE 行证据同时成立），而是源字段不可解释。

## 4. JC 只作进度证据，不作守恒

- 516 个工序组；23 张 WO 无工序卡（12 Completed、7 Not Started、3 Draft、1 In Process）。
- **21 张 WO 的 routing 末道不是完工道**：末道常是 `通用返工` / `质检发现问题`，
  其数量只有 2–4 件；主工序在 100–107 件。例：WO-26-00291 末道 2 件、
  `质检` 103 件、工序最大 107 件，而 SE 完工 103 件。
- 工序卡按批量/返工重复开卡，同 WO 内各主工序合计也可能差 2 件（105 vs 107）；
  因此 **JC 不能与 SE 做数量守恒**，旧 `last_op_qty` 更不是完工量。
  本工具给每条 `jc_operation` 记 `jc_progress_evidence_only`，并给 WO 打
  `jc_routing_final_op_not_completion` / `jc_missing` 标记，供运营侧参考。

## 5. 逐行去向

`out/dn_wo_jc_se/line_dispositions.jsonl`（2,040 行，本地证据包）每行带：
`row_type / row_key / link{so,dn,work_order,jc_ids,se,so_line_key,...} / qty / uom /
in_window / disposition / reason_code / reason_detail`。

| row_type | 行数 | 去向分布 |
|---|---:|---|
| `so_line` | 120 | conserved 115（`dn_conserved` 97 + `no_dn` 18）、excluded 5（作废单） |
| `dn_line` | 293 | linked 292（`dn_submitted`）、excluded 1（`dn_cancelled`） |
| `wo` | 128 | conserved 115、mismatch 2、open 11（未开工/草稿） |
| `se` | 425 | conserved 425（全部 line 级同单位证据） |
| `se_line` | 558 | 成品 conserved 425、非成品 excluded 133 |
| `jc_operation` | 516 | progress 516（不参与守恒） |

## 6. 证据包与哈希

| 产物 | SHA256 |
|---|---|
| `out/dn_wo_jc_se/association_manifest.json` | `c5fc54994efa93fce04c332d244d689940aa47b6f8b879d508e0c3a65fad7102` |
| `out/dn_wo_jc_se/line_dispositions.jsonl` | `436bfa9774e2598e95cc3cc9f8c3687da3c41bd498daf34114fc6ccee80e0f24` |
| `out/dn_wo_jc_se/se_details.json` | `7308504794270516b246a92239e8650799013c3d0b7cb26507d58b6267a33a88` |
| `out/dn_wo_jc_se/wo_probe.json` | `11ab1606c21a9c509cc6f64eb0bba3a25ed271c4da72cca3ca45a22a37372e80` |
| `out/dn_wo_jc_se/snapshots_manifest.json` | `62539638c834eb6f55d6dffeefe10dc5950debfc40c7d2c13ad3e98cb745f10e` |
| `out/dn_wo_jc_se/run.log` | `55a575ea00d8ee80313a90dbd848f7f02904e4ed82faee787a751902fcd0fe66` |
| `out/dn_wo_jc_se_evidence_v1.zip` | `e557e0ae8f3b88d45634ec0dee0f4ad914c8b65546cb2165b94fb5d77a9d1ef5` |

- manifest `payload_sha256`：`cca9dc857ec3101bccbe66394e623147fe634f19f76ad3c5e8dee0a9b026a51a`。
- `se_details.json` 的 `detail_records=362 / detail_records_ok=362`，
  取回时间 2026-10-21 09:58–10:01 UTC；最后几次重跑 `requested=0` 表示命中本地缓存。
- 稳定摘要 `stable_sha256`（去 run_id/as_of/在线探针/enrichment 日志）：
  **`680c0c54d6cd4011533c861e3544296d2494540d4f85cb68c1f7e6bd58506c5c`**。
- 重复回放：带探针在线跑一次、离线 `--reuse-se-details` 再跑一次，
  `stable_sha256` 相同，`line_dispositions.jsonl` SHA256 相同（R1/R2 通过）。
- 快照 SHA256 记录在 `snapshots_manifest.json`；输入未被修改。
- SE 明细取回时快照与当前 `docstatus` **0 漂移**；C3 全绿说明 `finished_qty` 与行合计一致。

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

# 单测（35 条，不联网）
uv run python -m unittest test_g1b_dn_wo_jc_se
```

## 8. 未做 / 边界

- 只覆盖 5 个 top SKU 快照（120 SO 行），**不是全 family**；未扩样。
- SE 集合来自快照，未重查“快照之后新建的 SE”；C2 在 115 张 WO 上成立，
  是当前一致性的旁证，不等于证明无遗漏。
- 未做 SO 行级事件去重、未输出终端需求/补货量。
- 未改 `en_family_poc.py` 的 SO 证据门；未重开 U01 / 旧 T。
- 本文件不是 G1 验收；G1 与业务接受仍由既定评审流程决定。
