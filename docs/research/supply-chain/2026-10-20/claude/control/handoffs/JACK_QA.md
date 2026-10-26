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

- 测试站部署与浏览器验收：本机 SSH 别名不可达，需有 SSH 权限的人执行；#314/#2 保持 draft。
- 报表实时数据源仍只有库存快照；PO/入库桥接需要预计算/采集产物或服务层接入，未接入。
- 业务/证据待确认：PO `status=4`、`warehousingNum` 本次/累计、绝对时区、`stock_change.parquet` 桶覆盖、部分入库/换货归属、是否发布“可承诺供给”。
- 生产只读；未自动入库、未改主数据/调度。

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
