---
okf: v0.1
type: Handoff
title: Jack W1 唯一问答日志
date: 2026-10-26
owner: claude-foreman
channel: docs/jack-w1-channel
---

# Jack W1 唯一问答日志

> **这是 Jack 的唯一问答日志。** 当前有效结论在 §1；每轮详细答复在 §2。
> 新答复只追加到本文件；PR 评论只发短指针。以本文件为准，不要从 commit/评论里找口径。

## 1. 当前有效结论（速查）

| ID | 结论 |
|---|---|
| **Q01 阶段** | `contract.py` 已扩为 **7 阶段**：`on_hand / po_open / in_production / shipped_in_transit / received / partially_received / unknown`。`partially_received` **只用于分配未知**：给 `received_qty/remaining_qty/doc_qty`（和=总量），`qty=null + qty_status='unknown'`、日期 unknown；只进 `supply_unknown`。分配已知 → 拆 `received + shipped_in_transit`。`unknown` 可带 known qty，但日期必须 unknown；只进 `supply_unknown`。**21/21 passed。** |
| **Q02 库存基准** | 正式 recon 用 **sample10 的 10-22 冻结值**（`stock_latest`，DuckDB sha `0919dd8c…`）。10-26 实时只作 `provisional_live`，标 `snapshot_mismatch=true`，不得用于 B_min/B_max。 |
| **Q03 WO** | 只纳入 `creation <= 2026-10-20` 的 WO。`WO-26-03110`：`produced_qty=0` vs JC 首工序 `sum_qty=110 > qty=100` = **数据冲突**，标 `production_conflict`、**不计供给**、进 exceptions。 |
| **Q04 PO021735** | 不是日期问题，是 **status=`4`**（另两条 `0`）。按 PO 号单查；查不到标 `source_missing`，不写 0；冻结 recon 只放 B_max。 |
| **Q05 overlap** | `same_batch_suspected` = 同 `(sku, warehouse)` 且 `open_po_qty == intransit`（只是嫌疑）；`proven` 需 `batch_key`。B_min 只排除 `suspected`，B_max 全保留；`unknown` 两边都保留。`dedup_assumed` 单值可加但必须标注。 |
| **Q06 映射角色** | 9 个 SKU 的映射对在 `sku_item`，可升 `proven`；但 **6 个皮壳 → `cover`**（C/Cord-White、C/Linen、C/Velvet、CEN1607、CENCord995、CENKZ1323），**2 个成品 → `finished`**（TT0031010、TT0031038），**TT0312701 → `component`**。`scope` 仍只表示 `in_house/external_fba`，不要加 `scope=component`。 |
| **Q07 仓库** | **可以相加**：不同 `warehouse_id` 且未重复上报即可加；同 ID/别名/同量重复只算一次。`component->main` 只是本地 `warehouse_map` 清洗标签，**不是业务规则**。`FZH-DANEEY-成品仓/半成品仓` status=0、`stock_history` 无 `warehouse_id`、9 SKU 快照 0。皮壳/半成品经海外分公司填充压缩后可发成品 → 算可用供给，但标 `conversion_assumed=true`；B_min 只放已证转换，B_max 可放假设。 |
| **Q08 received** | `received_evidenced` 保持 `qty=null + qty_status='unknown'` 可接受，只进 `supply_unknown`；分 `received_booked`（Stock Entry）与 `received_evidenced`（签收）。9 SKU 覆盖 8/39 DN、1,516/4,279 行是预期，不是 39/39。 |
| **Q09 复审** | W1 v0 数据口径基本落地；**6 项必改**：代码移到 feature 分支、SC14 不 fork、PO021735 status=4 不写“作废”、WO 过滤可审计、received 28 行拆分、B_min/B_max 桥接表。详见 §2 `[W1-Q09]`。 |

## 2. 轮次记录（只追加）

| 轮次 | 日期 | 内容 | 详细答复 |
|---|---|---|---|
| R1 | 2026-10-26 | Q01–Q08 首轮；SC14 扩 7 阶段、21/21 | [`2026-10-26-jack-w1-answers-r1.md`](2026-10-26-jack-w1-answers-r1.md) |

### R1 更正记录

| 日期 | 更正 | 说明 |
|---|---|---|
| 2026-10-26 | **Q07** | 上一版“`FZH-DANEEY-成品仓/半成品仓` 不能与主仓相加”**说过头了**。更正为：不同 `warehouse_id` 且未重复上报**可以相加**；`component->main` 只是本地映射清洗标签。 |

### [W1-Q09] 工头复审：W1 v0（2026-10-26）

**结论：Q01–Q08 的数据口径基本落地；有 6 项必须先改，再进 feature PR 复审。**

#### 通过（不用改）

- Q01：7 阶段启用；`unknown` 行（DN-26-00112）进 supply、只进 `supply_unknown`；本样本 `partially_received=0` 合理。
- Q02：正式 recon 用 10-22 冻结值；`--snapshot live` 只作 `provisional_live`。
- Q03：`WO-26-03110` 进 exceptions、不计供给；额外 `WO-26-03118`/`WO-26-03664` 按 Q03 规则计入并标 `sample10_wo_not_listed`。
- Q05/Q06/Q07/Q08：overlap 情景、6 cover/2 finished/1 component、仓库可加 + `conversion_assumed`、received 分 booked/evidenced，均按答复落地。
- SC04 对账：39 DN / 47 号 / 4,279 行 / 5 阶段 / FBA 17，全差 0。
- 9 SKU 覆盖 8/39 DN、1,516/4,279 行：符合预期，不是 39/39。
- `on_hand` 832 与 sample10 总可用一致（350+55+181+2+0+0+226+17+1=832）。

#### 必须改（按优先级）

1. **代码位置**：`140bbee6` 已从 `docs/jack-w1-channel` revert（`bb87549a`）；代码保留在 `feature/jack-supply-timeline`（`9aea4cb6`）。
   **请在 feature 分支开 draft PR**；#311 保持 docs-only + draft，不合并。
2. **不要 fork SC14**：`supply_timeline/sc14/contract.py` 是 canonical 的副本（297 行 vs 267 行）。
   改为 import `experiments/sc14/contract.py`，或至少加 source commit + 同步测试；否则 7 阶段/21 用例会漂移。
3. **PO021735 不要写“作废”**：`status=4` 语义未证；写 `po_status=4` + `po_status_semantics=unproven`，只进 B_max。
   业务确认后再改标签；确认前不得当已关闭。
4. **WO 过滤要可审计**：给 3 张额外 WO 加 `creation` / `modified` 字段；`WO-26-03110` 给 JC 首工序 sum + conflict 证据。
5. **`received` 28 行 vs 1 DN**：说明 28 行是否都在 9 SKU 内；非样本行单独 `received_out_of_sample`；给 per-SKU 计数。
6. **B_min/B_max 桥接**：给一张 from `on_hand 832 / po_open 1,021 / in_production 433 / transit 914` → `B_min 1,212 / B_max 2,762+433` 的桥接表，
   说明哪些加、哪些排除、哪些只进 B_max；避免重复/遗漏。
7. （minor）SC14 warning **132 vs 136**：解释少掉的 2 条（是否因 exceptions/unknown 移出），并给 66+66 的行级分类。

#### 下一步

- 在 feature PR 里按 1–2 改；3–7 在 `W1-RESULTS.md` 补表/字段。
- 改完在本文件追加 `[W1-A09]`，PR 评论只发短指针。
- #311 保持 draft；合并决定由用户/审核会话拍板。

### [W1-CHECK] 2026-10-26 工头检查

- 检查范围：PR #311 评论/提交、`docs/jack-w1-channel`、`feature/jack-supply-timeline`、本机 `jack_thread`、私有仓库 issue/PR。
- 结果：**04:07Z 之后没有新的 commit / 评论**；feature head 仍是 `9aea4cb6`（11:56）；docs head 是工头的 `ff197c66`。
- 如果 Jack 已更新：请 **push 到 `feature/jack-supply-timeline`**，并在本文件追加 `[W1-A09]`；PR 评论只发短指针。
- 只在本地 / Orca 终端里、未 push 的更新，工头看不到；先 push 再通知。

### [W1-A09] 2026-10-26 Jack 答复：Q09 #1–#7 已落地

> 代码：`feature/jack-supply-timeline`（`f63af171` + `40d74491`），draft PR #312；docs 分支保持 docs-only，#311 保持 draft。

| Q09 | 状态 | 落地与证据 |
|---|---|---|
| #1 代码位置 | ✅ | `140bbee6` 已 revert（`bb87549a`）；代码只在 feature 分支；PR #312 |
| #2 SC14 不 fork | ✅ | 副本与 canonical 逐字节一致（contract 297 行 / `45c2bb93…`；test 245 行 / `f3da773d…`）；`sc14/SOURCE.json` 固定 `197901f7`；`tests/test_sc14_sync.py` 校验哈希，canonical 存在时逐字节比对 |
| #3 PO021735 | ✅ | `po_status=4` + `po_status_semantics=unproven`；删除“作废/cancelled”；只进 B_max，不等同于已关闭 |
| #4 WO 审计 | ✅ | `config/wo_audit_20261022.json`；03110 creation `2026-09-02` / modified `2026-10-23`，JC 首工序 sum=110（48 张 JC）；03118 creation `2026-09-02`；03664 creation `2026-10-19` → 均 ≤ 10-20，B_max 不变；`jc_first_op_sum` 只作证据，不改变 remaining/conflict 判定 |
| #5 received | ✅ | `recon.json.received_audit`：28 行 / 28 doc_lines / 1 DN（DN-26-00067）/ 1 SKU（CEN1607NLinen-Ivory-194）/ doc_qty 231 / posting 2026-08-21；`out_of_sample=0`（`not_fetched_by_design`）；SC04 的 6 张 received DN 中 5 张不在样本内 |
| #6 B 桥接 | ✅ | `recon.json.b_bridge` + `b_bridge.csv`；代码内断言各 UOM 合计 = B_min/B_max；桥接表见 `W1-RESULTS.md` §8.6 |
| #7 warning | ✅ | 132 = 66 行 × 2 code；`on_hand` 54 + `po_open` 8 + `shipped_in_transit` 4；exceptions/unknown 行带 `uom=个`，不产生 UOM warning；136 来自旧的 provisional-live 轮次（232 行），行级 CSV 未保留 |

**本轮验证（10-22 冻结基准）**

- W1：233 supply 行；B_min **1,212**；B_max **2,762 + 433 个**；桥接断言通过。
- SC14：**21/21**，0 error / **132 warning**（66 行；54/8/4）。
- SC04：39 DN / 47 号 / 4,279 行 / FBA 17，**差 0**。
- 单测：17 条通过（1 skip：feature 树无 canonical）。
- 复现：`python w1_supply_timeline.py --live --snapshot frozen` → `python sc14/test_contract.py` → `python run_sc14.py` → `python sc04_recon.py` → `python -m unittest discover -s tests -v`。

**未做 / 待业务确认**

- `status=4` 的业务语义仍未经业务确认；确认前只进 B_max、不当已关闭。
- 行级 CSV/JSON 留本地，未进公开仓库。

## 3. 更早的问答（归档）

| 日期 | 内容 | 文档 |
|---|---|---|
| 2026-10-23 | 第一轮七问（PO/在途、WO、海外入库、SKU 映射、仓库、PO ETA、本地数据） | [`2026-10-23-jack-w1-answers.md`](2026-10-23-jack-w1-answers.md) |

## 4. 提问格式

```text
[W1-Q09] 2026-10-27
问题：……
证据：文件/行/命令输出
影响：字段/阶段/验收
```

- 发在 PR #311 评论，或你自己的 `feature/jack-supply-timeline` PR 评论。
- 答复追加到本文件 §2；PR 评论只发「已答复，见 JACK_QA.md 第 N 条」。
- 公开侧不放行级 CSV/JSON；行级路径 + sha256 走本地或私有通道。
