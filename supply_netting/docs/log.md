---
okf: v0.1
type: Log
title: 供给净额集成层 — 变更日志
description: 2026-10-27 首版净额引擎、上游组件引入与真实数据对账
tags: [log, netting, supply-chain]
updated: 2026-10-27
---

# 变更日志

## 2026-10-27 — 首版

- 新建 `supply_netting/`：冻结需求净额 × 库存/供应事实 → 按可售日期分桶净额。
- 原样引入上游组件（`git show`，未改写）：
  - `supply_chain_visibility/receipt_buckets.py` + `tests/test_receipt_buckets.py`（`b08acc05`，11 用例）；
  - `supply_chain_visibility/supply_row.py`、`overlap_gates.py` + 用例（`6d374085`）；
  - 三个纯函数 `bucket_gaps` / `assert_bucket_identities` / `allocate_so`（`aa93773b`）。
- 引擎：`build_buckets` 保护期 + 周桶；`net_target` / `net_all`；保守/预期两种情景；
  未知 ETA 只进条件量；无快照基准判 `unknown`。
- 供应侧：通途库存快照（0 也作为有效观测）、在途（无 ETA）、开放 PO（多为物料仓）；
  无法映射的输入保留为证据行，不静默丢弃。
- 产物：`supply_netting.parquet`、`supply_facts.parquet`、`replenishment_review.parquet/xlsx`、
  `third_party_demand.parquet`、`supply_netting_manifest.json`。
- 实跑 `as_of=2026-10-21T00:00+08:00`（快照 2026-10-20）：426 个键、保护期需求 602 件、
  10 个键有缺口共 16 件、条件供应 9,954 件；恒等式与数量账全部通过。
- 契约 v1 升级：新增 `facts.py`，落地 `stage_balances`（阶段互斥、累计交付不算供给、
  订单差额单列）、`milestones`（计划/预计/实际分列）、`availability_schedule`
  （tranche 可售日、拆分守恒、已含期初/FBA 不再补入），并把在途经 tranche 接入净额。
- 真实数据：172 条在途阶段余额 → 172 条条件态 tranche；其他阶段无本地源，明确记为缺口。
- 测试：`supply_netting` 35 个（8 条必测场景 + 契约 §7 的 9 例 + 契约边界 + 真实案例），
  引入的上游组件 23 个，全部通过。

## 2026-10-27 — 独立复审返修 + r5

- 修 F1–F4：期初资格、阶段证明端到端传递、跨阶段同批额度与重复失败关闭、
  到仓待上架可售 tranche。
- 附带 F6–F9：需求/预测严格布尔、全输入哈希与代码版本、视界外供应逐条留痕、
  空事实表固定 schema。
- 新增 `forecast.py`：消费 forecast-20261027-r2，预测资格与需求净额资格分离。
- r5：545 键、保护期缺口 71 键共 34.87、视界末未满足 449.97、条件供应 11,305；
  全部恒等式通过，`git_dirty=false`。
- 测试 147 通过（F1–F4 回归 21 个、预测 9 个）。

## 2026-10-27 — 第二轮复审 R1–R3

- R1：拆分谱系（split_of / split_total / document_key split-quota）传到计数侧；
  合法 6+4 子额度各自计数（净额 10、gap 0），只有同一额度跨阶段重放才去重；
  拆分与整批观察并存时两侧保留并上报 batch_split_conflicts。
- R2：混合已知+未证期初 → opening=null + opening_lower_bound，gap 保持 null。
- R3：预测入口按上游 manifest 校验窗口 sha256 与行数，新增 --forecast-manifest-sha256。
- r5 复算：代码 d4fc0862（git_dirty=false），数字与上一轮完全一致；预测哈希已验证。
- 测试 159 通过（supply_netting 136 + 上游 23）。

## 2026-10-27 — 第三轮复审 R3 元数据收口

- 行数契约：`outputs[].rows` 必须是显式正整数；缺失/null/bool/小数/字符串/≤0
  一律 `ForecastContractError`，并与未筛选完整表行数比较。
- 验证状态：`manifest_sha256_verified` 只在传了预期哈希且匹配时为 true，
  否则标 `unpinned`；新增 `manifest_sha256_pinned` / `manifest_sha256_verification`。
- 测试 163 通过（supply_netting 140 + 上游 23）；r5 数字不变，预测量仍是 2,378.272644。

## 2026-10-29 — 广范围补货决策包

- 新增 `decision_pack.py`：输入键 4,014（r5 净额键 ∪ 库存键 ∪ 预测键），
  去向 建议补货 91 / 无需补货 452 / 不可算 2 / 待核 3,469，合计对账一致。
- 两档情景：current 495 件，higher(+σ 参考缓冲) 777 件，额外占用 282；
  UOM 个/套分组合计，不跨 UOM。
- 产出 xlsx(6 sheet)/Parquet/JSON/manifest，manifest 记录截止日、旧报告日期、
  使用范围、输入输出哈希与 7 条限制；代码 `20b2892a`（git_dirty=false）。
- 供应侧口径对齐 r5：每行保留 protect_gap，manifest 记 34.867936 / 71 键。
- 测试 170 通过（supply_netting 147 + 上游 23）；最终代码 `85b5302b`（git_dirty=false）。

## 2026-10-29 — 决策包终审返修 r2（F1–F7）

- F1：不可算/待核的数量字段全部 null（含 Parquet/JSON/xlsx），新增
  demand_evidence_status / gap_evidence_status 与 measured_zero。
- F2：严格 JSON（NaN→null、allow_nan=False、parse_constant 回读）。
- F3：ABC 与汇总按 UOM，多 UOM 不出无单位标量（真实数据单 UOM「个」，495/777/282 不变）。
- F4：独立输入键集合对账 + 255 行预测源行排除明细（CSV/sheet/manifest）。
- F5：r5 产物、预测窗口/manifest、历史需求、sku_map 哈希全部记录并校验。
- F6：qty_low_counterfactual + 语义列；F7：first_gap_bucket_start/end + gap_today_note。
- 新包 `decision-pack-2026-10-29-r2`（原包不覆盖）；代码 `9f3285e3`（git_dirty=false）；
  测试 192 通过（新增 14 条）。

## 2026-10-27 — 同日快照 runbook（R1）

- 新增 `scripts/run_same_day.py`：一条命令串起 快照校验/冻结 → 需求净额 → 供应净额 →
  决策包 → 动作层；暂存目录成功才提升，失败归档 `.failed-*` 且不动 `latest.json`。
- 10-26 快照演练成功：129.9s（净额 58.4s / 决策包 16.2s / 动作 55.1s），
  产出 `run-2026-10-26-r1`、`decision-pack-2026-10-26-r1`、`pack-...-r1`、`actions-...-r1`；
  失败演练（错误预测版本）未产生正式目录、指针保持 r1。
- 文档：`docs/runbook-same-day.md`（前置条件/命令/校验/命名/回滚/演练记录/限制）。

## 2026-10-29 — 180 天视界（r4 预测）与春节统计

- 新增 `--allow-unpromoted-forecast`：CURRENT 未指向候选版本时，须显式开启，
  manifest 记 `forecast_promoted=false` 与 `forecast_current_run_id`。
- 决策包 CLI 增加 `--forecast-lead-days`；春节判定改为锚点 2027-02-06 ±30 天窗口，
  覆盖生产+发运路径，buffer 仍为 30+30=60 天，并输出穿越统计。
- 跑通 `run-2026-10-26-r6`（27 桶、lead 180）与 `decision-pack-2026-10-29-h180`：
  需求 13,390.221、缺口 6,207.051、建议键 207、current 6,301 / higher 7,010；
  35 天基线 2,377.665 / 449.967 / 91 / 495 / 777 未变。
- 春节穿越：97 张开放 SO 中 11 单 4,356 件（计入管线 8 单 2,600 件）跨窗口，
  生产段穿越 0；按交付月 2026-10/11/12。
- 测试 216 通过。

## 2026-10-29 — 多窗口切片（30/60/90/120/150/180）

- 新增 `scripts/horizon_windows.py`：从 r6 逐桶输出切累计窗口，按真实桶边界取整，
  窗口间不可相加；输出 CSV + 说明 + manifest，180 标 `scenario_only`。
- 结果：35/63/91/126/154/182 天实际覆盖，需求 2,396.9→13,332.2，累计未满足
  442.8→6,167.4，建议键 91→207，qty_current 490→6,266，qty_higher 904→7,065。
- 测试 222 通过（新增 6 条）。

## 2026-10-28 — 42 张不守恒 SO 逐单核对

- 新增 `scripts/so_conservation_fix.py`：按「阶段合计（in_house，剔超产）vs SO 总量」
  逐单核对 42 张不守恒 SO，输出 `so-conservation-fix-2026-10-28/` 的 CSV/摘要/报告。
- 结论：30 单差额恰为「重复/超发」标记量的 2 倍（带标记 + 未标记孪生），
  可按 2×重复量修正，建议修正量合计 7,510，修正后可计入权威 offset 合计 900；
  10 单为 FBA 外部（不在分支口径），2 单 FBA 单混入 in-house 阶段量（来源冲突，隔离）。
- 只读，不改净额/决策包；测试 259 通过（新增 8 条）。

## 2026-10-28 — 不守恒 SO 逐行重分类 v2（Codex 复审返修）

- v1 的「2× 标记量 = 重复」被否：2× 只是拟合标签。v2 改为逐 SO 行（so_line_id）
  按订单行 qty 封顶做前后账，超过部分才进 excess。
- 只有找到未标记孪生（同 source_record/batch + 同 item + 同 qty）才标 `duplicate`；
  实测无孪生 → 重复量 0。
- 四类去向：超发 3,755 / 重复 0 / 退货待核 0 / 异常占位 3,755；
  超产 3,020、FBA 14,277 单列。SO-26-00048 反例：在途超发 20 + 异常占位 20。
- 97 单统一 in_house 重审：55 单守恒零回归，30 单差额全部可由逐行封顶解释，
  总差额 17,417 → 0。原 900 改称 `heuristic_candidate_qty`=1,045，
  `offset_allowed=false`，保持隔离。
- 输出 `so-conservation-fix-2026-10-28-v2/`（行级 reclass + 逐单 + 报告）；只读不改净额；
  测试 273 通过。

## 2026-10-28 — SO 条件供给 v3（逐行封顶候选，pending re-review）

- 新增 `scripts/so_conditional_supply_v3.py`：基于守恒 v2 逐行重分类，只取
  in_house/known/非首工序/逐行封顶的 attributable 量；duplicate=0 不补；over_ship 与
  placeholder 的超出部分不计；按 UOM 分列。
- 输出 `so-conditional-supply-2026-10-28-v3/`：1,208 条 tranche、候选 50,023
  （个 49,923 + 件 100，其中 1,045 个有日期）；在途 48,978 无 ETA 只列不抵。
- 剔除：first-op 10,298、FBA 14,277、异常占位 3,755、超产 3,020、超发 1,900、数量未证 216。
- 90/150 天缺口保守情景不变（春节 +60 天把在产最晚 ETA 推到 3-29 之后），乐观情景
  90 天不变、150 天可将相关键缺口抵减；与 v2 逐键差异 28 键、+900。
- offset_allowed=false，仍为条件附件；不改 r6/h180/r2；测试 290 通过。

## 2026-10-28 — SO 条件供给 v3 按 UOM-CANONICAL 修正

- 已读 `UOM-CANONICAL.md`：个/套分列；TJ# 按套（stock_uom=套、is_stock_item=0）；
  PK# 皮壳 1:1 按个，不是套；未知单位不合计。
- v3 初稿沿用 W1 的「个/件」；修正后 `canonical_uom` 一律取 EN `Item.stock_uom`，
  无证据的 367 行 / 16,081 件标 `uom_unproven`、`included=false`，只进待核。
- 结果：included 841 条 tranche / 候选 33,942（全部「个」；在产 1,034 有日期、
  在途 32,908 无 ETA 只列不抵）；TJ# 在供给阶段为 0 行（规则仍生效，测试覆盖）。
- 测试 295 通过（v3 新增 14 条，含单位口径 5 条）。

## 2026-10-28 — v3 补：知识清单确认与 SKU 角色

- 已读 `2026-10-28-frepple-conversation-digest.md`：SKU 角色（皮壳/成品/半成品）、
  断货删失、服务 β/τ。v3 tranche 新增 `product_role`（皮壳 357 / 成品 65 / 半成品 14 /
  unknown 772）；本层不设服务档、不使用需求历史训练，删失与 β/τ 不作用于本层。
- 下一项 ASSET-REUSE-AUDIT 已确认资产位置：`experiments/business_phase/inventory_policy.py`
  （e3727683）、`sc08_conformal.py`（9624b248）、`experiments/sc13/leadtime_config.py`。
- 测试 296 通过。

## 2026-10-28 — 资产复用审计（只读）

- 对照 frepple digest §1 核查 4 个资产：inventory_policy / sc08_conformal /
  sc13/leadtime_config / supply_netting。
- 结论：inventory_policy 的 base-stock 回放被 frontier/frontier_v2 重写（A1），
  frontier 报告还误称资产不存在（A2，检索未覆盖 git 历史）；服务缓冲用正态 CV，
  与 sc08 的比率经验分位不同、且 sc08 已证名义 95% 实际 0.54–0.70（A3）；
  交期分段硬编码、sc13 合约零接线（A4，最高优先）；本仓库内部缓冲公式有两份（A5）。
- 未改任何代码；报告与 CSV 在 asset-reuse-audit-2026-10-28/。

## 2026-10-28 — LEADTIME-CONFIG-WIRE（A4 接线）

- 新增 `config/leadtime_config.json`（版本 `2026-10-28.1`）+ `leadtime.py`：90/75–90、
  发运 7、生产 60、海运 35·40、春节锚点/30+30/窗口 30、完工到仓 14 全部改为读配置，
  每条假设自报 `source=assumed`、`sample_size=0`、`notes`。
- `so_backlog.py` 与 `scripts/so_conditional_supply.py` 的模块常量改为配置派生；
  导入即加载，缺文件/缺字段/measured 无样本一律失败，无内置默认值、无环境变量回退。
- 留痕：`summarize_backlog()` 与条件供给 manifest 新增 `leadtime_config`
  （版本/生效日/来源/每条路线分段）；逐行 `eta_basis` 带配置版本号。
- **数字零变化**：301 测试通过（新增 `tests/test_leadtime.py` 22 条）；不改 r6/h180
  净额、决策包与已验收产物，不 push。
- 分段词表与 sc13 不同（production/shipping/ocean），原因见
  [leadtime-config-2026-10-28.md](leadtime-config-2026-10-28.md) §3。

## 2026-10-28 — LEADTIME-CONFIG-WIRE 补：v3 manifest + 配置哈希

- `LeadTimeConfig` 新增 `config_sha256`（按加载时读到的同一份字节）→ `to_manifest()`
  的 `sha256`；v2 / so_backlog / v3 三处 manifest 自动带上。
- `scripts/so_conditional_supply_v3.py` manifest 新增 `leadtime_config`
  （version / sha256 / sources / sample_size / 分段）：此前 v3 的日期已自动走配置，
  但 manifest 查不到用的是哪一版。
- 日期与候选量零变化：只加留痕字段，未重跑既有 v3 产物目录；既有产物下次正常出包时
  才会带新字段。
- 测试 +3（v3 manifest 端到端：合成 W1 跑 `main(--out tmp)` 后校验版本/哈希/来源，
  并与 `plan_dates` 逐值比对日期）。

## 2026-10-28 — LEADTIME-CONFIG-WIRE 补 2：v3 产物 manifest 实写留痕块

- v3 改用**最小留痕块** `provenance()`：`leadtime_config = {version, sha256, source,
  sample_size, path}`（source 各块不一致时给去重列表；sample_size 取最小值）。
- 已把该块**补写进既有产物** `so-conditional-supply-2026-10-28-v3/
  so_conditional_supply_v3_manifest.json`：`2026-10-28.1` /
  `2ce7b25fa860…73ae` / `assumed` / `0` / `supply_netting/config/leadtime_config.json`。
  写入前后对 `report.md`、两张 CSV、`summary.json` 做 sha256 比对，全部 UNCHANGED；
  只有 manifest 本身变了，`generated_at` 保持原始出包时间。
- 测试 +2（`provenance()` 5 字段与取值；混合 source → 列表且 sample_size 取最小值），
  v3 端到端断言改为校验这 5 个字段与哈希。

## 2026-10-28 — MOQ-REPLENISH-POLICY

- 新增 `scripts/moq_replenish_policy.py`：读 `items_attr.tsv`（15,230 行、无表头 10 列，
  列义已用 EN REST 逐字段核对）+ 决策包 + 预测窗口 + EN Item/Bin 只读快照。
- 21 个非零 MOQ 物料全部是**外购辅料**（缝纫线/流苏/PP棉/日字扣/自封袋/魔术贴/棉绳/
  防水布/工具配件），UOM 为卷/米/个/千克；默认仓为辅材/包材/面料/工具配件仓；
  `safety_stock` 全 0。**0/21 出现在本批 4,014 个决策键里 → MOQ 对现有建议量 0 影响。**
- 政策表（5 行）：绍兴自有工厂无 MOQ；周补 7 天复核；小额阈值 = 单次补货量 < 1 周 P50
  需求建议合并/观察（建议非硬约束）；外购辅料按 `ceil(需求/MOQ)×MOQ`；**不存在渠道级 MOQ**。
- 影响（不改主表）：91 个有正建议量的键（全「个」）按周需求分档 —— 观察 2 键/5 件、
  正常 18 键/162 件、批量（>4 周覆盖）71 键/328 件；月补→周补的周期库存约 −273.3 件（个）。
- 产物：`moq-replenish-policy-2026-10-28/`（report.md + 4 张 csv/json + EN 快照）；
  测试 14 条（解析/证据/分档/MOQ 取整/政策表/落盘只写 out 目录）。

## 2026-10-28 — M3 刷新/调度/异常清单设计（不部署）

- 新增 `docs/m3-refresh-schedule-exceptions-2026-10-28.md`（Design，proposed）。
- **不改任何代码、cron、生产配置**；只定义口径与落地步骤。
- 复核既有能力：`scripts/run_same_day.py` 已实现「暂存 → 全成功才改名 → `latest.json` 只在成功时更新」，
  失败态改名 `.failed-*` 留证——**M3 不再重造失败语义**。
- 三个真缺口（本次给出设计，未实施）：① 调度触发口径与幂等键 `(snapshot_date, label, code_commit)`；
  ② 六类异常（快照陈旧 / ETA 过期 / PO 无 ETA / SO 不守恒 / 单位未证 / 占位 SKU）此前散在六个产物里、
  无汇总无闸门；③ 版本只有「谁是最新」，没有「谁批了哪一版、批了什么范围」。
- 闸门设计：`blocking_count>0 → 决策包 partial=true 且不得 approved`；
  例外须记 `accepted_risk` + 批准人。
- 版本/审批：`pipeline-manifest` 加 `version` 块；`approvals.jsonl` 只追加；
  三条不变式（无审批不得下单 / blocking 不得批准 / approved 即冻结）。
- 回滚从「手工 mv + 手改 `latest.json`」改为命令化（`latest.json.previous` + `--rollback`），
  目录改 `.rejected-*` 不删除，并记入 `approvals.jsonl`。
- 数据基线（用于验收对账，非新结论）：97 张开放 SO → 55 守恒 / 30 逐行封顶解释 / 未解释余差 0；
  在途 48,978 无 ETA 只列不抵；`item_uom_cache` 1,627 行，`PP10LB` 为已知 unknown；
  `placeholder_skus` 阈值 100,000 来自 `Buttonkit-pl` 9,999,866。
- 落地分 5 步（异常清单生成器 → 版本块 → 回滚命令化 → 审批校验器 → 调度），
  每步独立验收；**Step 5 调度需用户另行批准，本次不部署**。

## 2026-10-28 — FULL-CATALOG-NEXT

- 新增 `scripts/catalog_next.py`：读 `catalog-coverage-2026-10-28/` 的明细与 summary，
  把 4,949 个未进包物料按四类给出动作、责任角色、优先级与红线；对账（四类合计 =
  未覆盖数、有库存条目 = 64、库存件 = 1,324）不过即报错。
- **关键发现**：64 个「有库存但 UOM 未证」实查 EN `Item.stock_uom` **64/64 都有单位**
  （全「个」）——缺口在本层缓存（1,627 条只覆盖进包物料），不是 EN 主数据缺失。
  63 项刷新缓存即可进库存侧事实，1 项 EN `disabled=1` 转停售确认。
- 动作表：P0 补单位（本层）/ P1 补映射 761（运营）/ P1 停售确认 284（业务）/
  P2 组件皮壳口径 3,840（业务，不建独立 SKU）。
- 报告固定写入两条边界：4,014 键 ≠ 全目录、未覆盖 ≠ 零需求；不改主表、不 push。
- 产物 `catalog-next-2026-10-28/`（report + 2 CSV + EN 快照 + manifest）；
  测试 8 条（原因对账、未知原因报错、优先清单状态与排序、落盘只写 out）；全套 369 通过。

## 2026-10-28 — FRONTIER-DEDUP（A1/A2/A3 落地）

- 新增 `scripts/frontier_dedup_check.py`：从 git 取回既有评估器（`e3727683`
  inventory_policy.py）导入执行，与 `frontier_v2.simulate` 跑同一合成需求矩阵；只读、
  不改任何数字、不重跑已验收产物。
- **实测结论**：逐日复核（R=1）两边满足量/缺货量/β/平均库存**完全相等**（差 0）→ 核心语义
  同一套；周复核（R=7）差异来自**复核相位**（期初 t≡0 vs 期末 t≡R−1）与暖机在途，
  提前期越长越被稀释（L=7 差 36 件、L=30 差 1、L=60 差 3）。
- **α ≠ CSL**：α 按「有需求期间」计（198 个），CSL 按「复核周期」计（29 个），同一次回放
  α=0.8586 vs CSL=0.2759；β 与 fill_rate 公式相同。
- **backorder**：既有评估器有 `semantics` 显式参数（S=25 场景：lost_sales 丢 935/期末欠单 0；
  backorder 丢 0/期末欠单 935）；frontier_v2 只有 lost_sales。
- **定规**：frontier_v2 冻结（冻结面 6 个函数，测试守护），后续政策实验只包既有评估器；
  `frontier_v2` docstring 与 `docs/frontier-dedup-2026-10-28.md` 都写明。
- 产物 `frontier-dedup-2026-10-28/`（report + comparison.json + manifest）；测试 9 条；全套 378 通过。

## 2026-10-28 — 最新库存快照 + 决策包 r1（对比 10-26）

- 新增 `scripts/fetch_stock_snapshot.py`：通途 ERP2 MCP `erp2_stocks_stocksquery` → `en_stock` 快照，
  字段映射与历史快照逐列一致；12.5 秒限流（5 次/分钟）、526 退避、**不覆盖 `en_stock.parquet`**。
- 新增 `scripts/compare_packs.py` + 4 条用例：两版决策包逐键对比，**只对两侧都有的键相减**，
  `only_old` / `only_new` 单列落盘（`compare_one_sided.csv`），单位不同永不合并。
- `decision_pack.py` / `decision_join.py` / `run_same_day.py` 增加 `--decision-date`
  （默认 `2026-10-29`，**只影响标注与文件名，不参与任何数量计算**）；
  顺带把硬编码的免责声明与「2.779 天」改成按本轮实际快照/计算值生成。
- 授权排查：`wms_wms_wmsinventory_query`、`erp3_wms_wmswarehouse_query`、
  `listing_warehouse_getwarehouse` 两把 key 均返 **524 未授权该接口**；
  `erp2_product_goodsquery` 返 200 证明 key 有效 → 是**接口未授权**，不是凭证问题。
- 快照：5,219 行 / 7 仓 / 56 次调用 / 零错误，`snapshot_at=2026-10-28T09:46:16`。
  **CG 仓（WayfairCG-*3 个）不在通途仓库列表**，本轮缺失（10-26 有 98 行）。
- 全链：`run/decision-pack/pack/actions-2026-10-28-r1`，176.2 秒，`latest.json` → r1，
  `decision_date=2026-10-28`、`as_of=2026-10-28T09:46:16`、`gap_from_as_of_days=0.593`、`git_dirty=true`。
- 对比（同 demand / 同预测，只换快照）：建议补货 91→**94**、待核 3,469→3,378、
  `qty_current` 495→**524**、`gap_today` 449.97→**471.65**。仅 5 个键改判。
- **归因**：待核 −91 = −92（CG 键消失）+1（波兰新键）；92 个 CG 键数量均为 null，
  不影响 `qty_current` / `gap_today`，故 +29 / +21.68 是可比的库存变化。
- 报告：`D:/Work/fzh-order-store/en-demand-v1/supply-netting/compare-2026-10-26-vs-2026-10-28/report.md`。

## 2026-10-28 — 交期配置 2026-10-28.2（P50/P90）

- 依据 leadtime-measurement：production P90 50 / P50 20，shipping P90 20 / P50 11.5，
  ocean 35/40 不变；source=measured、sample_size=197（海运部分仍假设）。
- leadtime.py 增 P50 分段（校验 P50≤P90），plan_dates 最早用 P50（11.5→12 天）、
  最晚用 P90 + 春节 60；冻结测试期望。
- 重跑 so_conditional_supply（v2），manifest 记 version 2026-10-28.2 + sha256
  `bb82760a…`；条件量 145 与缺口不变（150 天乐观 -8 件）。
- 未改 r6/h180/决策包；测试 405 通过。
