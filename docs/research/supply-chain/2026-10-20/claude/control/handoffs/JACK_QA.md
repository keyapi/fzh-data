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
| **Q10 复审** | A09 大部分通过；**1 个阻塞**：`config/frozen_20261022.json` 是行级业务 JSON 进公开仓库，违反 D33；另有 4 项必改：SC14 同步测试 skip、PR312 body 过期、WO 审计时点、B 桥接 per-PO 明细。详见 §2 `[W1-Q10]`。 |
| **Q11 复审** | A11 **通过**：仓库 `scope=operator`、波兰 `assumed`、SC14 离线同步 19/0；用户已保留 `sample_skus/warehouse_map`（无数量）。**#312 技术上可进合并评审**；剩业务确认（PO status=4、子仓运营方）+ 合并决定。详见 §2 `[W1-A11]`。 |

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

### [W1-Q10] 2026-10-26 工头复审：A09

**结论：A09 大部分通过；有 1 个阻塞项（公开仓库行级 JSON）+ 4 项必改，修完再进合并评审。**

#### 通过

- Q09 #1 代码位置：docs 分支无 W1 代码；代码只在 `feature/jack-supply-timeline`；PR #312 draft。
- Q09 #2 SC14 不 fork：`sc14/contract.py` / `test_contract.py` 与 canonical **逐字节一致**（sha256 `45c2bb93…` / `f3da773d…`），`SOURCE.json` 固定来源。
- Q09 #3 PO status=4：代码只写 `po_status=4` + `po_status_semantics=unproven`，无“作废/cancelled”。
- Q09 #5 received：28 行 = 1 DN / 1 SKU / doc_qty 231；`out_of_sample=0` 为按设计不抓取，解释成立。
- Q09 #7 warning：132 = 66 行 × 2；按 stage 54/8/4 分类，解释成立。
- B_min 1,212 = on_hand 531 + transit 681；B_max 2,762 + 433 个；桥接断言自洽。

#### 阻塞（必须先改）

1. **`config/frozen_20261022.json` 是行级业务 JSON，进了公开仓库**（6.5 KB：9 SKU × 仓的 `available/intransit/waiting/defects`）。
   D33 明确：**行级业务明细的 CSV/JSON 不提交**。请移出 git：
   - 公开仓库只留 `config/frozen_20261022.schema.json`（字段/类型）+ `config/frozen_20261022.sha256`（hash）；
   - 实际值从本地 `--config` 路径读取，CI/单测用合成 fixture；
   - `wo_audit_20261022.json` 里的 WO 日期/数量同理：要么移本地，要么只留 `creation <= as_of` 的布尔/计数，不留行级量。
   - 同类需分类：`sample_skus.json`（映射行，无数量）、`warehouse_map.json`（仓 ID/映射，无数量）。至少带数量/金额的 JSON 必须移出公开仓库。

#### 必改

2. **SC14 同步测试在 feature PR 上会 skip**：`test_canonical_matches_if_present` 在 canonical 不存在时 `skipTest`；PR #312 的默认单测因此没有真正比对 canonical。
   请二选一：
   - 在 PR/CI 里 checkout `docs/jack-w1-channel` 并设 `SC14_CANONICAL_DIR`，把“17 passed / 1 skip”改成真实“18 passed / 0 skip”；或
   - 先把 #311（docs/contracts）合到 main，再 rebase #312，让 `experiments/sc14` 存在。
   - 同时修正 PR #312 body：`Q09 #3–#7 待后续提交` 已过期；`14 passed` 与 A09 的 `17 passed` 不一致。
3. **WO 审计时点**：`wo_audit_20261022.json` 的 `source` 写 “queried 2026-10-26”，`WO-26-03110` `modified=2026-10-23`，JC sum 110 是 live 证据，不是 10-20 冻结证据。
   请加 `jc_as_of` / `wo_state_as_of` / `modified_after_as_of`；`production_conflict` 保留（保守不计供给），但要标明证据是 post-as-of。
   `WO-26-03664` `modified=2026-10-22` 也请标 `modified_after_as_of=true`。
4. **B 桥接 per-PO 明细**：`po` 6 行 914 → B_min 0 的“排除原因”只有 `po_not_counted`。
   请补逐 PO 行：`doc_name / open_qty / po_status / overlap_status / date_confidence / exclusion_reason`，
   说明这 6 行是因为 `same_batch_suspected` + 无 ETA 才不进 B_min，而不是数量为 0。
5. **received 行字段**：`received_audit` 已有 28 行/1 DN/1 SKU/doc_qty 231；请确认主 supply 行也带
   `doc_qty / received_qty / posting_date / received_source`（不能只在 audit JSON 里），否则下游无法逐行回溯。
6. （minor）`run_sc14.py` 的 `contract_source_commit` 硬编码 `197901f7`；请从 `sc14/SOURCE.json` 读取，避免 canonical 更新后过期。

#### 下一步

- 先处理**阻塞项 1**（公开仓库行级 JSON），这是合并前必须解决的。
- 2–6 在 PR #312 修；修完在 `JACK_QA.md` 追加 `[W1-A10]`，PR #312 只发短指针。
- #311 保持 draft；#312 合并前必须满足 D33 清关。


### [W1-A10] 2026-10-26 Jack 答复：Q10 阻塞 + 必改已落地

> 代码：`feature/jack-supply-timeline`（`62546ea7`），draft PR #312；#311 保持 docs-only / draft。

| Q10 | 状态 | 落地与证据 |
|---|---|---|
| 阻塞：行级 JSON | ✅ | `config/frozen_20261022.json`、`config/wo_audit_20261022.json` 已从 git 移除；值放本地 `local/`（gitignore）。公开侧只留 `frozen_20261022.schema.json`、`frozen_20261022.sha256`、`wo_audit_20261022.summary.json`；新增 `--config` / `--wo-audit`；单测用 `tests/fixtures/frozen_synthetic.json`；并加“公开配置无数量键”守卫。`git ls-files config/` 只剩 `sample_skus.json`、`warehouse_map.json` + schema/sha256/summary。 |
| #2 SC14 skip | ✅ | `tests/test_sc14_sync.py` 优先读 `SC14_CANONICAL_DIR`，否则从 `origin/docs/jack-w1-channel` 读取 canonical（缺失时 `git fetch --depth=1`）；`SC14_SYNC_REQUIRE=1`/GitHub Actions 下缺失即失败。默认单测 **19 passed / 0 skip**。 |
| #3 WO 时点 | ✅ | 本地 `wo_audit` 增加 `wo_state_as_of=2026-10-20`、`jc_as_of=2026-10-26`、`modified_after_as_of`；03110、03664 标 true；`production_conflict` 保留（保守不计供给），证据标 post-as-of。 |
| #4 per-PO 桥接 | ✅ | `out/b_bridge_po.csv`（本地逐 PO：doc_name/open_qty/po_status/overlap_status/date_confidence/exclusion_reason）；`recon.json.b_bridge_po_summary` 聚合：6 行 / 914 / 全部 `same_batch_suspected` + 无 ETA → `po_not_counted`。公开文档只放不含 open_qty 的视图。 |
| #5 received 字段 | ✅ | 主 supply 行带 `doc_qty / received_qty / posting_date / received_source`；evidenced 行 `received_source=shipment_signed`、`received_qty=null`。 |
| #6 contract pin | ✅ | `run_sc14.py` 从 `sc14/SOURCE.json` 读取 `contract_source_commit` 与 `contract_sha256`。 |

**验证（10-22 冻结基准）**

- W1 233 行；B_min 1,212；B_max 2,762 + 433 个；桥接断言通过。
- SC14 21/21；0 error / 132 warning（66 行；54/8/4）。
- SC04 39 DN / 47 号 / 4,279 行 / FBA 17，差 0。
- 单测 19 passed / 0 skip；`sha256sum -c config/frozen_20261022.sha256` OK。
- `git ls-files` 无 `frozen_20261022.json` / `wo_audit_20261022.json` 行级文件。

**待业务确认 / 未合并**

- `status=4` 语义仍待业务确认。
- #311、#312 保持 draft；行级 JSON 清关前不合并。

### [W1-Q11] 2026-10-26 工头复审：A10

**结论：Q10 的 D33 数量 JSON 阻塞已解除；用户已决定保留标识 JSON；剩余 2 项需改，修完可进合并评审。**

#### 通过

- 行级数量 JSON 已移出 git：`config/` 只剩 `schema` / `sha256` / `summary`；`local/` 已 gitignore；`--config` / `--wo-audit` 从本地读取。
- SC14 同步：19 passed / 0 skip；canonical 从 `origin/docs/jack-w1-channel` 读取；`SOURCE.json` pin；`run_sc14.py` 从 `SOURCE.json` 读 contract pin。
- WO：`wo_state_as_of` / `jc_as_of` / `modified_after_as_of` 已补；`production_conflict` 保留。
- per-PO 桥接：本地 `b_bridge_po.csv` + 公开 summary（6 行 / 914 / 全部 `same_batch_suspected` + 无 ETA）。
- received 主行带 `doc_qty / received_qty / posting_date / received_source`。
- 验证：233 行 / B_min 1,212 / B_max 2,762+433 / SC14 21/21 / 0 error / 132 warning / SC04 差 0。

#### 必须改

1. **仓库 confidence / scope 一致性**：
   - `warehouse_map.json` 的 `波兰-FZHPoland-covers` 是 `warehouse_confidence=confirmed`，但 `source/note` 写 `assumed EN mapping`；应为 `assumed`，除非有独立证据。
   - `FZH-DANEEY-成品仓/半成品仓` 是 `warehouse_scope=own`，而 CENTRADE/DANEEY 是 `3pl`。请写清 `warehouse_scope` 是**库存所有权**还是**仓库运营方**：
     若指所有权，3PL 仓内我方货也应是 `own`；若指运营方，子仓应是 `3pl`。当前混用会让 `supply_own_*` 误读。
   - 建议加 `warehouse_scope_basis`（ownership / operator）字段。
2. **SC14 同步测试默认仍可能 skip**：只有 `SC14_SYNC_REQUIRE=1` 或 `GITHUB_ACTIONS` 才 fail；离线/未 fetch 时普通单测仍 skip。PR body 写“默认不再 skip”不准确。
   - 在 CI/测试入口设 `SC14_SYNC_REQUIRE=1`，或把 canonical checkout 到 `SC14_CANONICAL_DIR`；或明确“离线 skip 是预期”。
   - 单测里的 `git fetch` 网络依赖建议放到 CI 步骤，测试保持离线。
3. **PR #312 body 措辞**：`无行级 JSON` → `无行级数量 JSON；sample_skus/warehouse_map 仍含标识/映射，待用户确认`。
4. （minor）`W1-RESULTS` §8.6 的 `po` 行排除原因补一句：6 行 / 914 全部 `same_batch_suspected` + 无 ETA；per-PO 明细在本地。
   `sample_skus.json` 的 `as_of=2026-10-23` 与快照 10-22/10-20/10-19 不一致，请注明它是“样本冻结日”。

#### 用户决定（已关闭）

- **2026-10-26 用户决定：保留** `sample_skus.json` / `warehouse_map.json`。
  理由：只有标识/映射、没有数量/金额，与已公开的 sample10 文档同级。
  **此项不再阻塞 #312**；公开仓库仍不放行级数量 JSON。

#### 下一步

- 1/2/3/4 在 #312 修；用户决定 5 已关闭（保留）。
- 修完追加 `[W1-A11]`；#311 / #312 保持 draft。

### [W1-A11] 2026-10-26 Jack 答复：Q11 两项已落地

> 代码：`feature/jack-supply-timeline`（`e15b1b91`），draft PR #312；#311 保持 docs-only / draft。

| Q11 | 状态 | 落地与证据 |
|---|---|---|
| #1 仓库 confidence/scope | ✅ | `warehouse_map.json` 增加 `warehouse_scope_basis=operator`：`warehouse_scope` 表示运营方（own/3pl/fba），不是库存所有权；in_house 库存所有权均为我方。波兰仓 confidence 由 confirmed 降为 assumed（EN 映射无独立证据）；CENTRADE/DANEEY 保留 confirmed 并写 `warehouse_confidence_basis`（DN customer + en_finished 交叉印证）。数量口径不变。 |
| #2 SC14 默认 skip | ✅ | `tests/test_sc14_sync.py` 改为纯离线：`SC14_CANONICAL_DIR` → `local/sc14_canonical` → `../sc14`；都没有时 skip（离线预期）。网络 fetch 移到 `tests/run_canonical_tests.py`，该入口 fetch 后以 `SC14_SYNC_REQUIRE=1` 运行，19 passed / 0 skip。 |
| #3 PR body | ✅ | 已更新：明确“无行级数量 JSON；sample_skus/warehouse_map 仍含标识/映射，已由用户确认保留”；SC14 离线 skip 为预期。 |
| #4 minor | ✅ | §8.6 补 `po` 行说明；`sample_skus.json` 增加 `as_of_note`（样本冻结日；快照 10-22/10-20/10-19）。 |

**验证（10-22 冻结基准）**

- W1 233 行；B_min 1,212；B_max 2,762 + 433 个；桥接断言通过。
- SC14 21/21；0 error / 132 warning（66 行；54/8/4）。
- SC04 39 DN / 47 号 / 4,279 行 / FBA 17，差 0。
- 单测：`tests/run_canonical_tests.py` → 19 passed / 0 skip；离线 unittest 无 canonical 时 1 skip（预期）。

**未合并**

- #311、#312 保持 draft；行级 JSON 清关前不合并。

### [W1-A11] 工头验收：通过（2026-10-26）

**结论：Q11 两项已修；核心逻辑未改（diff 不含 `w1_supply_timeline.py`），数字沿用 v0；#312 技术上可进合并评审。**

- 仓库：`warehouse_scope=operator` 已写明；波兰 `assumed`；CENTRADE/DANEEY `confirmed` + basis。
  `FZH-DANEEY-成品仓/半成品仓` 仍是 `own/assumed`——**运营方待业务确认**（若 DANEEY 运营应为 3pl），不阻塞技术合并。
- **下游映射**：`supply_own_*` 用 `scope=in_house` 判断“我方库存”，**不要用 `warehouse_scope=own`**；`warehouse_scope` 只用于运营方展示。
- SC14：离线 unittest 无 canonical 时 1 skip 是预期；`tests/run_canonical_tests.py` 19/0；CI 应跑这个入口。
- 数字：233 / B_min 1,212 / B_max 2,762+433 / SC14 21/21 + 0 error / 132 warning / SC04 差 0 沿用。
- **合并顺序建议**：`#311`（docs/contracts）→ rebase `#312` → `#312`；#311 先把 `experiments/sc14` 带到 main，
  让 #312 的 `test_canonical_matches` 真正 0 skip。
- 待业务确认（不阻塞技术合并）：PO `status=4` 语义；FZH-DANEEY 子仓运营方（own/3pl）。
- #311/#312 仍 draft；等用户/审核会话批准。

### [P0-CODEX-2026-10-26] 原生报表与 PO 入库时间交接

用户要求额度收尾后交 Jack。见 [完整交接](2026-10-26-codex-native-report-handoff.md)：原生报表测试实现与 PO 入库只读适配器已审、75 项本地测试通过；完整七阶段/PO 去重整合尚未完成，禁止把库存证据入口当成可承诺供给。生产库存/Parquet 已运行，本次不改生产、不自动通途入库。后续优先核实 warehousingDate、部分入库、稳定事件身份、时区及采集窗口；#311 已合并，#312 独立评审。

### [P0-A-2026-10-26] Jack 接手进展：入库证据 → 采集/对账 → 数据层 → 报表 UI

> 代码：fzh-data `feature/en-native-supply-report-plan` @ `f5bf3dcc`（PR #314 draft）；key_test `feature/so-chain-report-filters` @ `e7a4f6d`（PR #2 draft）。生产未改动。

**已完成**

- 核对 app 与扁平副本：key_test `135131d` 的 12 个文件逐字节一致（`so_chain.py` 也一致；扁平 `sales_order_chain_append.js` 无对应分支文件）。
- 入库证据：`PO021704` 头 10-14，实际 **38 行 10-14 + 12 行 10-19**；按头日期 ±1.5 天漏 12/50。`PO021694` 全收 26 行 1:1，`warehousingNum == quantity`。10-01–10-26 全量 102 行 / 8 PO，无同一 PO×SKU 多批行；`warehousingNum` 本次/累计、UOM、绝对时区、库存桶覆盖仍未证。
- 采集：新增 `receipt_collector.py` + `collect_receipts_cli.py`，重叠窗口 + 仓库外缓存 + 显式弱键/截断。09-01–10-26（14 天窗/2 天重叠）：**166 输入 → 150 唯一 + 16 重叠重复**；12 PO / 113 SKU；无截断。
- 对账/覆盖：`receipt_coverage.py`；150 条唯一行全部 `unknown`（`missing_stable_id`），全部无 UOM/时区；`not_collected=0`；未自动抵扣。
- 设计：`supply_chain_visibility/docs/research/2026-10-26-receipt-supply-integration.md`（8 条不变量、来源表、时间桥接、重叠/单位 gate、验收测试）。
- 数据层：P1 `supply_row.py`；P2 `receipt_bridge.py`；P3 `overlap_gates.py`；P4 `supply_integration.py`（`report_only()` 只返回聚合/flag）；P5 `scripts/bench_supply_integration.py` + 发布清单。
- 报表 UI：Supply Timeline 增加 `source_layer / qty_status / uom_proven / timezone_status / identity_confidence / B_min/B_max 资格 / exclusion_reason`；文案明确库存证据、UOM 未证不进 B_min、不构成可承诺供给。

**验证**

- 扁平副本/数据层：**113 passed / 2 subtests**。
- key_test app：**22 passed**。
- 性能基线（合成）：4k/20k/40k 行 **0.76/3.63/7.90 秒**，peak 12.6/62.4/124.6 MB；不代表生产延迟。
- 命令：`uv run python -m pytest ... -q`；`python supply_chain_visibility/scripts/bench_supply_integration.py --sizes 1000,5000,10000`。

**未做 / 待决**

- 测试站已**文件级更新**：`8.133.254.66` 的 key_test 两个 `.py` 已备份（`/tmp/supply_timeline_query.py.bak_20261026_175147`、`/tmp/supply_timeline_report.py.bak_20261026_175147`）并覆盖；哈希与本地一致、语法通过；REST 查询已返回新列、页面 200。`bench restart` 因 dev01 无 sudo 未执行（报表端点已加载新代码）；如需全量重启，请 frappe 用户执行 `sudo -u frappe bench restart`。浏览器视觉验收待登录后确认；#314/#2 保持 draft。
- 报表实时数据源仍只有库存快照；PO/入库桥接需要预计算/采集产物或服务层接入，未接入。
- 业务/证据待确认：PO `status=4`、`warehousingNum` 本次/累计、绝对时区、`stock_change.parquet` 桶覆盖、部分入库/换货归属、是否发布“可承诺供给”。
- 生产只读；未自动入库、未改主数据/调度。

### [P0-REVIEW-FIX-2026-10-26] 复审修复与再次审核

用户授权持续修复并复审。原审 8 个反例已收入 `supply_chain_visibility/tests/test_supply_safety.py`，全部通过；后续复审补充已证批次/冲突、来源版本/重放、时点混合、弱键内容冲突、缓存陈旧/隔离与 UI 契约用例。

- 数据层：SourceProof 默认未证；单位字符串不自动变成证据；status=4 仍仅 B_max 情景；缺映射/身份/完整源/单位时不计数量。distinct 需已证独立批次；同批同量不重复，同批异量隔离。逐 receipt 用自己的 PO 时点，缺 PO/库存为 null；两种时间错配分别标 gap/overlap 风险，不自动修正。
- 采集：保留最大观测重数，弱键内容冲突或键不完整保留疑似重复，dedup_assumed 传递；实际完整请求窗参与 coverage，业务覆盖仍未证。缓存必须账号隔离，live 刷新开放窗口/历史 TTL，frozen 仅显式重放。
- App：qty_status 描述 qty；另增 evidence_qty_status；未上报/仓库范围未知来源单独标记，B 资格仍全部 false。未接入完整七阶段，不自动下单/入库/抵扣、不改生产。
- 2026-10-27 收尾回归：160 passed / 2 subtests；app 两份报表 41 passed（Python 3.10）。原始业务数据和 W1 本地残留均不提交。生产没有写操作。
- 复审后的 4k/20k/40k 合成基线：1.13/6.23/13.68 秒，peak 20.6/102.4/204.6 MB；4k 约 1.1 秒，仅本机含新增证据校验的测量，不代表生产 SLA。
- 本轮 app 提交：`c34fa53`（PR #2 draft）；只提交修复，不部署测试站/生产。此前测试站的 Git HEAD/文件覆盖状态仍按上一条部署记录，后续发布应由已批准的 Git 版本和有权限的重启流程完成。
- 业务未证项仍为 unknown：入库本次/累计、UOM、来源绝对时区、stock_change 覆盖、PO status=4、部分/替代入库归属。它们不被本次技术修复自行确认。

### [P0-TEST-DEPLOY-2026-10-27] 测试系统已同步本轮修复

用户明确授权更新测试系统。测试域名为 ensh.vilavi.cn；该测试 bench 内站点名为 erpnext.vilavi.cn，操作未连接生产主机。

- key_test 从 Git HEAD `135131d` 快进到已提交的 `c34fa53`，分支仍为 feature/so-chain-report-filters。通过本机从 origin 获取并验证的 Git bundle 同步；两个功能 .py 及测试文件均来自提交版本，服务器工作区干净，结束先前“文件覆盖但 Git 未更新”的状态。
- 两个功能文件：`key_test/supply_timeline_query.py`、`key_test/key_test/report/supply_timeline/supply_timeline.py`。旧文件和 manifest 保存在测试机 `/tmp/supply-timeline-pre-c34fa53-4sxs_72e/`；原覆盖内容另存 Git stash，未删除。
- 测试机现有 dev01 账号获准以 frappe 运行完整路径 `/usr/local/bin/bench`。已成功执行 `sudo -n -u frappe /usr/local/bin/bench restart`，web/worker 均重启成功，并对测试 bench 站点 clear-cache。
- 测试机执行 `env/bin/python -m unittest discover -s apps/key_test/key_test/tests -p "test_supply*.py" -v`：41 tests / OK。服务器没有 pytest，本次复用标准库 unittest，不额外修改 bench 依赖。
- 真实测试站 REST：样本 SKU 返回 17 行，evidence_qty_status 新列存在，qty_status/证据状态契约均通过，B 资格仍全部 false；不存在的仓库返回 1 条 not_reported，未伪装成库存记录；报表页面 HTTP 200。只保留这些聚合验收结果，不提交业务行级响应。
- 本次仅部署已审报表修复，不把 fzh-data 的纯函数数据层接入运行中的完整供应链。生产未改动，#314/#2 仍 draft，不合并。

### [P0-PROD-DEPLOY-2026-10-27] key_test #2 生产部署

**结论：key_test #2（`c34fa53`）已合并到 main，并完成生产 pull + migrate + clear-cache + restart；冒烟通过。**

- 合并：key_test PR #2 **MERGED**；origin/main = `c34fa53`；fzh-data #314 仍 open draft（docs/handoff，不影响生产）。
- 生产 preflight：branch `main`，工作区干净；部署前 HEAD `f7ea65a`；备份分支 `backup/pre-c34fa53-20261027`。
- 部署：`git pull --ff-only origin main`（`f7ea65a..c34fa53`）→ `bench --site erpnext.vilavi.cn migrate` → `clear-cache` → `bench restart`。
- 环境：`duckdb 1.5.6`；`Tongtool Stock Latest` 存在；无新增必需 pip 依赖。
- 冒烟（生产 REST）：
  - Report 记录存在：`Supply Timeline`、`SO Chain Overview`。
  - SO Chain Overview：`SO-26-00132` → 2 行 / 14 列；`SO-26-00110` → 199 行 / 14 列。
  - Supply Timeline：157 行 / 33 列；message 提示仅库存证据、B 资格 false、仓库范围未知（预期）。
- 备注：migrate 同时重放既有 report patches / Work Order·Item 自定义字段（既有 hook，不是 #2 引入）；无错误。
- 回滚：`checkout backup/pre-c34fa53-20261027` + clear-cache + restart；未改写历史。
- 待办：key_test #2 body 与 fzh-data #314 仍写“draft / 不合并 / 生产未部署”，已过时；Jack 需更正记录。

### [W1-SUPPLY-FACTS-2026-10-27] 供应事实批量入口 v1（测试站）

**结论：三类事实 + links + manifest 的只读批量入口已在测试站跑通；9 SKU 验收待生产授权。**

- 契约与字段：`supply_chain_visibility/docs/reference/supply-facts-contract.md`（stage_balances / milestones / availability_schedule / links / manifest）。
- 代码：key_test `key_test/supply_facts.py`（whitelist `get_supply_facts`）；本地批量入口 `EN_API/supply_facts_export.py`（JSON+Excel+sha256+latest 原子指针）。
- 人工视图：SO Chain Overview 链条弹窗新增「数量阶段 / 节点 / 分批可售」，与批量入口同一方法。
- 验收：单 SO `SO-26-00026` → 3 行、三行阶段余额守恒 10/5/8，查询约 0.8s；测试站全范围（含取消订单）292 行 → 308 余额 / 656 里程碑 / 287 片段 / 404 关联，0.85s；契约单测 49 项 + 合并/版本一致性 7 项全绿。
- 审核整改（2026-10-27 第一轮）：行级权限按 `get_list` 可读集合取数；出库单位不一致不归一；退货按 `return_against` 抵扣；取消订单保留实物片段；片段 ID 加订单行前缀；manifest 相对路径、`observed_at`/`as_of` 分离、200 页上限标 `truncated`、显式 `external_sources`。
- 审核整改（2026-10-27 第二轮）：可售片段继承阶段单位；退货不再生成「待出库」供给；受限来源（含行级）无法判断的阶段置 unknown；历史 `as_of` 服务端拒绝；批次合并 `restricted` 按 OR、`sources` 按 AND、外部来源保守保留 `not_integrated`；空结果保留 `empty_reason`/`partial=true`。
- 审核整改（2026-10-27 第三轮）：在产按 `min(Σ工单量, 订单量)` 覆盖量分配，超出覆盖进未计划；退货缺口先记 unknown 再分配，不再制造虚假在产；milestones/links 与阶段余额统一单位校验（缺失/不一致不归一、工单单位不一致→unknown）；片段 ID 加仓库+DN 明细行身份并保留实际出库仓库；全部授权过滤时 `empty_reason=all_restricted`。`RULE_VERSION=2026-10-27.2`。
- 第三轮测试站验收（2026-10-27，key_test `8d8f5d7`，用户已重启 bench）：服务端 83 项 supply unittest OK；单 SO `SO-26-00026` → 3 行 / 9 余额 / 16 里程碑 / 7 片段 / 17 关联（守恒 10/5/8，查询 0.92s）；全范围 292 行 → 310 余额 / 656 里程碑 / 289 片段 / 404 关联（0.56s，`exhausted`）；片段 ID 全局无重复，非取消行全部守恒，`rule_version=2026-10-27.2`。
- 审核整改（2026-10-27 第三轮复核）：退货按原出库明细 `dn_detail` 抵扣到具体行，缺明细且原单仅一行时兜底该行，仍无法归属只保留一条 unknown（DN 净额），不再毛额+补差双计；到港要求全部关联运单状态齐全，部分缺失不判定到港；已提交生产计划覆盖但无工单的部分记 unknown，不判未计划。PR #314 入口已快进到 `feature/en-native-supply-report-plan`。
- 第三轮复核测试站验收（2026-10-27，key_test `0276c67`）：服务端 89 项 unittest OK；单 SO `SO-26-00026` → 3 行 / 9 余额 / 16 里程碑 / 7 片段 / 17 关联（守恒 10/5/8，0.79s）；全范围 292 行 → 310 余额 / 656 里程碑 / 280 片段 / 404 关联（0.56s，`exhausted`）；片段 ID 无重复、非取消行全部守恒；9 行因「已提交生产计划未建工单」由未计划转为 unknown（合计 1061 件），`rule_version=2026-10-27.2`。
- 审核整改（2026-10-27 第四轮）：`load_dns` 按 `dn_detail` 保留逐明细退货行（不再把不同原明细的退货合并成一条并只留首个明细）；生产计划单位缺失或与订单单位不一致时不计覆盖量，剩余整体 unknown，不再按订单单位分配；`RULE_VERSION` 升到 `2026-10-27.3`，服务端返回、manifest、导出 manifest 与 `latest.json` 新增 `implementation_version`。新增 `load_dns → 阶段余额 → 可售片段` 贯穿测试（校验分仓净额与原明细身份）。
- 第四轮测试站验收（2026-10-27，key_test `a619801`）：服务端 92 项 unittest OK；单 SO `SO-26-00026` → 3 行 / 9 余额 / 16 里程碑 / 7 片段 / 17 关联（守恒 10/5/8，0.80s）；全范围 292 行 → 310 余额 / 656 里程碑 / 280 片段 / 404 关联（0.33s，`exhausted`）；片段 ID 无重复、非取消行全部守恒；manifest 与 `latest.json` 均携带 `rule_version=2026-10-27.3`、`implementation_version=key_test.supply_facts@2026-10-27.3`。现网无「多仓同 DN」与「计划单位不一致」样本，这两类由 `load_dns → 阶段 → 片段` 贯穿测试覆盖。
- 审核整改（2026-10-27 第五轮）：`dispatch` 里程碑按出库单拆分（日期=该单过账日、数量=该单过账量，退货在阶段余额净额），不再把多张单数量累加到最早日期；在产必须有开工证据（工序卡实际开工或已完工），草稿/无开工工单只算计划覆盖并进 unknown；批量导出合并前校验 `schema_version`/`rule_version`/`implementation_version`/`as_of`，不一致拒绝该批次、不写新版本、`latest.json` 保持上次成功版本。`RULE_VERSION`/`IMPLEMENTATION_VERSION` 升到 `2026-10-27.4`。
- 第五轮测试站验收（2026-10-27，key_test `ce662d6`）：服务端 94 项 unittest OK；单 SO `SO-26-00026` → 3 行 / 9 余额 / 16 里程碑 / 6 片段 / 17 关联（守恒 10/5/8，0.78s）；全范围 292 行 → 310 余额 / 656 里程碑 / 259 片段 / 404 关联（0.58s，`exhausted`）；片段 ID 无重复、非取消行全部守恒；3 条 `dispatch` 节点逐单核对日期/数量与 `shipped_by` 链接一致；28 条在产中 21 条因缺开工证据转为 unknown（现网草稿工单较多）；manifest 与 `latest.json` 均携带 `schema_version=supply-facts/v1`、`rule_version=2026-10-27.4`、`implementation_version=key_test.supply_facts@2026-10-27.4`。
- 审核整改（2026-10-27 第六轮）：超订单完工不再截断——订单分配仍按订单量，但新增 `over_produced` 阶段保留来源完工总量与超出量（`demand_status=excess`，不计入订单守恒/可售供给，取消订单同样保留）；开工/完工节点数量改回来源数量并在 `note` 标注超额。超退不再整笔标记为已抵扣——`returned` 行拆为实际抵扣 / 超退 / 未关联原单三部分（之和等于退货原值），超退标「无原单可抵」。`RULE_VERSION`/`IMPLEMENTATION_VERSION` 升到 `2026-10-27.5`；SO 链条视图新增「超产未分配」标签（需 clear-cache + 浏览器缓存刷新）。
- 第六轮测试站验收（2026-10-27，key_test `37b3356`）：服务端 97 项 unittest OK；单 SO `SO-26-00026` → 3 行 / 9 余额 / 16 里程碑 / 6 片段 / 17 关联（守恒 10/5/8，0.82s）；全范围 292 行 → 312 余额 / 656 里程碑 / 259 片段 / 404 关联（0.58s，`exhausted`）；片段 ID 无重复、非取消行（排除超产）全部守恒；现网 2 行超产被保留（订单 50 / 完工 64 → 超产 14；订单 1 / 完工 11 → 超产 10），完工节点输出来源量 64 / 11 并在 note 标注超额，超产行不进可售片段；manifest 与 `latest.json` 均报告 `supply-facts/v1` / `2026-10-27.5` / `key_test.supply_facts@2026-10-27.5`。现网无退货样本，超退拆分由单测覆盖。
- 审核整改（2026-10-27 第七轮）：退货改为**先按 `dn_detail` 校验原明细身份与剩余可抵扣量，再汇总到 DN**——超出该明细容量记超退；显式明细不存在记引用冲突（不再做单行兜底）；缺明细且原单多行则不抵扣、不摊量（归属未知）；未涉冲突的明细保留已证净额。`over_produced` 语义拆分：`qty` 改为**当前超订单现存实物**（来源完工 − max(已出库, 订单量)），新增 `cumulative_excess_qty` 保留累计超产；导出 xlsx 增加该列；UI 标签改为「超产现存」。`RULE_VERSION`/`IMPLEMENTATION_VERSION` 升到 `2026-10-27.6`。
- 第七轮测试站验收（2026-10-27，key_test `3ae8b46`）：服务端 100 项 unittest OK；单 SO `SO-26-00026` → 3 行 / 9 余额 / 16 里程碑 / 6 片段 / 17 关联（守恒 10/5/8，0.79s）；全范围 292 行 → 312 余额 / 656 里程碑 / 259 片段 / 404 关联（0.60s，`exhausted`）；片段 ID 无重复、非取消行（排除超产）全部守恒；2 行超产现存与累计字段一致（14/14、10/10；这两行未出库，故现存=累计），xlsx 已含 `cumulative_excess_qty` 列；manifest 与 `latest.json` 报告 `supply-facts/v1` / `2026-10-27.6` / `key_test.supply_facts@2026-10-27.6`。现网无退货样本，明细容量/引用冲突/缺明细拆分由单测覆盖。
- 审核整改（2026-10-27 第八轮）：退货容量改为**单一按原始明细记账的账本**——显式 `dn_detail` 与缺引用兜底共用同一 `matched_by_item`，调换退货顺序结果不变；单行兜底改按**原始明细行数**判断（聚合组保留 `item_qty` 逐明细数量），同仓同单位多明细聚合后缺引用一律不抵扣并标归属未知。新增顺序不变性、聚合组缺引用与 `load_dns` 贯穿测试。`RULE_VERSION`/`IMPLEMENTATION_VERSION` 升到 `2026-10-27.7`。
- 第八轮测试站验收（2026-10-27，key_test `ab5a766`）：服务端 103 项 unittest OK；单 SO `SO-26-00026` → 3 行 / 9 余额 / 16 里程碑 / 6 片段 / 17 关联（守恒 10/5/8，0.78s）；全范围 292 行 → 312 余额 / 656 里程碑 / 259 片段 / 404 关联（0.59s，`exhausted`）；片段 ID 无重复、非取消行（排除超产）全部守恒；输出与上轮一致（现网无退货样本）；manifest 与 `latest.json` 报告 `supply-facts/v1` / `2026-10-27.7` / `key_test.supply_facts@2026-10-27.7`。退货顺序不变性、同仓聚合缺引用与逐明细容量由新增单测覆盖。
- 审核整改（2026-10-27 第九轮）：SO 链条弹窗按具体订单行请求时补 `include_delivered=1`，已发完订单行仍可下钻历史事实，与机器导出范围一致；新增服务端 `include_delivered` 过滤与弹窗 JS 参数两项回归测试。仅 JS/测试变更，服务端数量规则与版本不变。
- 第九轮测试站验收（2026-10-27，key_test `54a7132`，已 clear-cache + restart）：服务端 105 项 unittest OK；`Sales Order` meta `__js` 已含 `include_delivered: 1`；REST 带参数实查 297 行（其中 5 条已发完），样本 `SO-24-00012` 行不带参数返回 0 行（`empty_reason=no_matching_lines`）、带参数返回 1 行 / 1 条阶段余额。服务端数量规则与版本仍为 `2026-10-27.7`（本轮仅 JS/测试变更）。
- 9 SKU：生产只读解析出 99 张 SO；测试站无该样本（0 张），生产未部署新模块（本任务不授权生产部署），**待授权后验收**。
- 边界：到仓/上架无 EN 证据 → `delivered_sellable` 不产出、`eligible=false`；多运单不摊量；无独立承诺字段；时区未证；PO/入库/预留/新鲜度未并入 EN 事实。
- 生产未部署；#314 仍 open，由 #318 接管。PR 评论只发本段短指针。

### [W1-DELIVERY-FACTS-R2-2026-10-30] 第二轮复审修复

对照 Codex 第二轮复审中断前确认的缺口，已修复并补 RED→GREEN：

| 缺口 | 修复 |
|---|---|
| 公共 API 可伪造 `status=provided` scope 绕过 hash | `normalize_scope` 对任何客户端 scope 重算 hash，失败→invalid |
| `snapshot_id` 只含行 ID，原地改数量不漂移 | 改为全行内容指纹（qty/UOM/仓/客户/关联/退货状态） |
| 未匹配/冲突退货落 0 且守恒报正常 | `actual_qty=null`、`quantity_status=unknown`，守恒 `ok=false` |
| 守恒只数未知行，不校验算术 | 新增 `expected_actual_qty` / `arithmetic_ok` |
| 适配器 conflict 行判 `candidate_no_action` | 强制 `manual_review_association_conflict` |
| 适配器 scope hash 与非 ASCII 不兼容 | 与 key_test 同构（`ensure_ascii=False`、去重） |
| 适配器不校验 schema / 截断快照 | schema 白名单 + `total` 与行数一致 |

版本：`RULE=2026-10-30.3` / `IMPLEMENTATION=key_test.delivery_facts@2026-10-30.3`。
测试：key_test 310 passed / 3 skipped / 4 subtests；fzh 200 passed / 5 subtests。

未完成（不得写成通过）：权威业务 scope、受限用户真实 HTTP、浏览器会话、
真实通途入库/QI、测试站真实退货样本、生产部署。

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
