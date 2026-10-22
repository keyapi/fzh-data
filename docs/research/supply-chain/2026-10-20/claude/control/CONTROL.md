---
okf: v0.1
type: Plan
title: 供应链整合项目总控页
description: 路线图、当前里程碑、执行看板与证据入口；live 状态见同目录 state.json
created: 2026-10-21
updated: 2026-10-21
---

# 供应链整合 — 项目总控页

Updated: 2026-10-22 13:40 (Asia/Shanghai)

## 已验收（窄样本契约）

> v1 `22ae9a1e` 被 Adapter Review 打回；v2 `49a142e0`、v3 `e6b3cc9a` 被交叉复审打回。
> **v4 `4b7ec55f` 已通过 Codex 交叉复审（PASS，1 个非阻塞 P3 文档计数）。**

- **G1B 10 SKU 第一阶段 SE 补齐（2026-10-22）**：闸门 `ca27163c`（Codex PASS）下
  补齐 238 个 SE 明细；10/10 SKU C1/C2/C3 完整，SE 663/663 resolved；
  C2 195 可比 / 193 通过 / 2 张 `produced_qty` 失真 / 1 张 `wo_uom_unresolved`（WO-25-07755）unverified；
  两轮回放逐字节一致。用量 239/300 请求、0.24 MiB/32 MiB、241/900 秒。
  证据 `out/dn_wo_jc_se_expand10_phase1/`，manifest `92318843…`，
  stable `1732d590…`。**仍只是 10 SKU，不是 100/全 family/G1。**

- **G1B DN/WO/JC/SE 窄样本 v4**：`4b7ec55f`（5 SKU）。
  （120 SO / 293 DN / 128 WO / 425 SE / 558 SE 行 / 105 JC 组 / 516 工序行，
  2,040 行去向）。
  在 v2 的 6 P1 + 3 P2、v3 的 3 项基础上，关闭 v3 交叉复审剩余 1 P2：
  JC 工序 payload **逐个校验**（值必须是对象且 `sum_qty` 为有限数值；null/字符串/数组
  → `jc_operation_payload_invalid`，空对象/缺 `sum_qty` → `jc_operation_sum_qty_invalid`），
  组内任一非法 → 整组 `matched=0`、`invalid++`、**不出 progress**（含组内合法工序），
  只落非法项显式 invalid 行，WO 行 `reason_detail` 标 `jc_operation_payload_invalid`。
  C1 115/115；C2 117 可比（115 通过 + 2 张 `produced_qty` 失真）+ 11 张未开工，`complete=true`；
  C3 425/425；SE 覆盖 425/425 已解决；`audit_ok=true`、`evidence_complete=true`；
  84/84 本模块离线单测、150/150 g1_contract 离线全套；两轮回放 stable/行去向一致，0 网络请求。
  v4 的 `stable_sha256` 与 `line_dispositions` 与 v3 逐字节相同（合法数据不变）。
  关键发现不变：`Work Order.produced_qty` 不可当完工账。
  Codex 复审：PASS（79 read-only tests + 8 独立 payload 探针；2,040 行两轮回放）。
  P3 已修：文档把 516 条工序行误写成 516 个 JC 组，实际为 105 组（19+18+16+32+20）；
  仅文档改动，代码/证据未变。
  证据：`out/dn_wo_jc_se/`，zip `dn_wo_jc_se_evidence_v4.zip` `6cec02bd…`；
  manifest `3b381d4d…`；payload `8a376557…`；行级去向 `95197f06…`；stable `6f12333c…`；
  报告 `g1b_dn_wo_jc_se.md`；复审 `control/reviews/2026-10-21-cross-review-v4.md`。
  **本项只证明窄样本关联/守恒契约，不是 G1 或业务验收，也不授权扩样。**

## 已验收

- **G1 SO 证据门 v5**：Claude `9a04741e` / Codex `d027f981`。反向 BOM、共享 ND、数值 flag P2 均关闭；66 条离线测试通过；v5 evidence `1d6a7b33…`，回放 zip `a3b23cf1…`；20 样本全部 pending，PK/ND family=0，无 `historical_verified`。接受范围仅为 `current_structure_only` + 历史未知保留 pending。
- **无证据表 R1/R2 审计门**：`d8c473fe`；52 SO / 2,024 行；family 132 / pending 1,769 / out_of_scope 123；两轮一致；已接受。
- **历史证据边界**：Codex `d3fc4c8d`（#301）；Version/modified 不足以升级历史，需可信锚点/变化覆盖/生效证据或明确交易绑定。

## 本轮评审记录（均已完成）

- **G1B-ADAPTER-REVIEW**（Codex）：`22ae9a1e` 只读审查，**6 P1 + 3 P2**；
  报告 `control/reviews/2026-10-21-adapter-report.md`。已由 v2–v4 关闭。
- **G1B-CROSS-REVIEW v2**（Codex）：`49a142e0` FAIL（2 P1 + 1 P2）；
  报告 `control/reviews/2026-10-21-cross-review-v2.md`。
- **G1B-CROSS-REVIEW v3**（Codex）：`e6b3cc9a` FAIL（仅 1 P2）；
  报告 `control/reviews/2026-10-21-cross-review-v3.md`。
- **G1B-CROSS-REVIEW v4**（Codex）：`4b7ec55f` **PASS**（1 个非阻塞 P3）；
  报告 `control/reviews/2026-10-21-cross-review-v4.md`。

## 阻塞

- **R290-RECON（2026-10-21 21:45 解除阻塞）**：冻结包已定位在
  `D:/Work/fzh-order-store/`：`order_store.duckdb`（407,898 行 / 400,754 单，
  202301–202609）、`FREEZE_2026-10-21-prototype-corrected.md/json`（代码 `67f73c5`）、
  `RECONCILIATION_2026-10-21.md`（代码 `ae6a6793`）、`trace_examples.md/json`（五例）。
  已完成 Codex 只读对账：**5 = 已接收 5 + 待交付 0；accept 3 / scenario 1 / blocker 1**。
  有效冻结为 corrected `67f73c5`（`ae6a6793` 是旧声明；`scripts/` 仅说明文本差异）。
  accept 仅指冻结数值一致：KS0001 / KS0230 / KS0153；scenario：KS0316（cover-only 池）；
  blocker：KS0249（导出仓名与 trace 不一致；按正确“美东-CENTRADE”补查后数值吻合）。
  仍为全局 blocker/scenario：`MAX(intransit, PO)` 去重未证；未结 PO 的 ETA 全空、无字段；
  Cover 实物同池/可替代未证；需求/库存无 UOM。报告
  `control/reviews/2026-10-21-r290-reconciliation.md`。
  **注意：本轮 DN/WO/JC/SE 未使用该 DuckDB**——那是 EN 单据层；DuckDB 是通途订单历史/需求层，
  供 R290 原型与后续 G2/G3 使用。

- `historical_verified` 的历史锚点/有效期证据仍缺，历史关系保持 pending。
- 全 family 扩样未授权。
- 业务裁决：服务水平/预算、3PL 供货归属、退货回库比例。

## 下一步

1. ~~DN/WO/JC/SE 交付与复审~~ → v4 `4b7ec55f` **PASS**，窄样本契约已验收。
2. ~~方向裁决~~ → 决策 Codex 选 **A：扩样**；离线可用仅 10 SKU，已跑完并两轮一致
   （C1 10/10；C2/C3 仅原 5 个完整）。报告
   `control/reviews/2026-10-21-expand10-report.md`。
3. ~~生产闸门~~ → Codex 第五次复审 **PASS `ca27163c`**（读流异常保留在途预占；
   重定向预读/绝对截止/403 原子停机均已关闭）。生产只读已按批准边界开放。
4. ~~第一阶段 238 个 SE 明细~~ → **已完成**：239/300 请求、0.24/32 MiB、241/900 秒；
   10/10 SKU C1/C2/C3 完整，SE 663/663 resolved；两轮回放逐字节一致。
   报告 `control/reviews/2026-10-22-phase1-se-enrichment.md`。
5. **100 SKU 扩样仍暂停**（决策 Codex：先 A 库存地基、再 B 闸门，扩样需
   ETA/Cover/UOM 与明确放行）；下一步由 Codex2 决定扩样还是转 ETA/Cover/UOM。
6. ~~R290-RECON~~ → 已完成：5/5 接收，accept 3 / scenario 1 / blocker 1。
7. 收尾 `/ce-okf` 已完成（PR #306）；四轮返修与 producer 经验已归档。
8. 周期 automation 保持停用；次日 05:17 用新归档 cmd 验证库存历史。
9. **决策 Codex（09:05）：先 C（SKU 匹配只读审计）→ 再 B（10 SKU 的 ETA/Cover/UOM 证据）；
   A/D 暂停。** C 任务书 `control/reviews/2026-10-22-sku-audit-task.md`；
   旧 6,549 是 EN 订单口径，本地 GS 口径为 297 SKU / 4,115 行，不硬凑。
   Codex1 计划 11:05 审 C、13:05 审 B。
10. **Jack 头程跟踪（2026-10-22）**：`delivery_plan` 新跟踪代码已上生产并重启；
   数据仍需 Jack 的爬取/推送写入测试与生产；部分 DN 缺头程单号，需 PJ/YYS 补。
   最小输入清单 `control/reviews/2026-10-22-jack-input-request.md`；未到位前 ETA 保持 blocker。
11. **new-api 今日额度已于 2026-10-22 重置**；Claude worker 继续，避免无谓 subagent。

## 当前阶段：G2+G3 窄范围试点（2026-10-22 13:40）

- codex2 裁决（decision7）：**立即放行 G2+G3 只读试点**；不等 Jack 在途、
  不等长历史每日库存、不等 28 项 SKU 身份裁决。
- 范围：10 个 EN 链完整 SKU；预测未来 3 个月（seasonal naive + ETS 候选，P50/P90，
  6 起点回测）；补货情景 A（无在途/PO 不计到货）与 B（仅 PO 假设到货）；
  提前期 60/90/120，复核 30 天，服务水平 90%。
- 未知隔离：Cover 不并入主建议；UOM/身份不明排除或聚合；ETA 空不视为及时到货。
- 交付：60 分钟内 2 SKU 样例，今日内 10 SKU V0 报告 + 证据 JSON；Codex1 先审样例、
  再审判算与建议。
- 任务书 `control/reviews/2026-10-22-g2g3-pilot-task.md`；**不输出可直接下单的结论**。

## 修正

- #290 已有**实验原型**待对账，不是“预测/补货尚未开始”。主线尚未验收，但原型资产存在。
- **10 SKU 不等于 100**：当前准确说法是“10 SKU 已补齐至 **3,416 行**，
  C1/C2/C3 完整，SE 663/663 resolved；2 处 `produced_qty` 失真、1 张
  `wo_uom_unresolved`；非 100 SKU、非 G1 验收”。

## 数据地基：每日库存（2026-10-21 22:30）

- 任务真实存在：`FZH-TongtuStockApiDaily`，每天 **05:17**，输出
  `D:\Work\库存备份\YYYY-MM-DD\*.jsonl + manifest.json`。
- 现状：**已有 3 天**（10-20 不完整、10-21 完整、10-22 补跑完整）。
  10-20 有 1 仓 URLError 10060（400 行部分数据，`complete=false`）；
  10-21 的 05:17 结果待证，09:46 完整运行 5,314 行；
  **10-22 05:17 失败根因已定位**：`stock_daily_backup.py` 第 31 行
  `next(..., parents[7])` 的默认值被立即求值导致 `IndexError`（10-21 10:58 改动引入）。
  已改为惰性回退；07:06–07:20 手动补跑成功：14/14 仓、5,314 行、
  `run_id=20261022T070625`、`complete=true`。
- （历史）当时每日 JSONL 尚未入库；2026-10-22 07:50 已写入 `stock_history`（见下）。
- 诊断与入库方案：`control/reviews/2026-10-21-stock-daily-diagnosis.md`
  （只读、未落盘、未改任务）。
- 决策 Codex：**先修数据地基 A，再修闸门 B，暂停 100 SKU 生产扩样**；
  23:50 复审诊断，次日 05:17 后复审实际定时采集。
- 关键边界：缺失/失败标 `unknown`，不标 0；不覆盖手动快照；不补造历史；
  两天不足以做删失校正；每日快照无法定位日内断货。
- **2026-10-22 07:50 已入库本地 `order_store.duckdb`**（Codex 复审 PASS `53291689` 后）：
  `stock_run` 3 / `stock_run_warehouse` 42 / `stock_history` **15,820 行** /
  `stock_publish` 3 天。10-20：400 行部分批次 + 4,792 行完整批次（该日仍标不完整）；
  10-21/22：各 5,314 行、14/14 仓完整。`tongtool_stock` 未动；
  DB 备份 `order_store.duckdb.bak-20261022`。报告 `out/stock_history_reports/`。
- `stockout_observed` 只在完整批置位；`uom_basis='unknown'`；TEST-1 已标记；
  `stock_id_history` 3,876 条。空仓是有效结果，不写 0。
- 下一步：`run_id` 封存归档器（不改抓取逻辑）→ Codex 复审 → 次日 05:17 验证。
- **2026-10-22 08:35 归档器 PASS（1.3）并已真实归档**：
  `runs/2026-10-20/legacy-20261020T181947/`（scope/run=false，14 文件）、
  `runs/2026-10-21/legacy-20261021T094623/`（true/true）、
  `runs/2026-10-22/20261022T070625/`（true/true）；均有 `.sealed`。
  新 `run_stock_daily_backup.cmd` 已把 OUTDIR 固定为 `D:\Work\库存备份`，
  次日 05:17 起使用 run_id 封存目录；旧 `fzh-inventory` 数据不迁移。

## Agent 角色与分工（2026-10-21 20:05）

- **决策 Codex / 进度监督者**（`gpt-6.1-sol`，独立进程）：裁决方向、范围、验收标准与放行/停止；
  监督阶段完成、阻塞、逾期、ready 闲置、范围变更；输出“继续/返工/局部暂停+下一动作+期限”。
  不改代码、不做常规复审、不访问生产；不能扩大生产授权。
  协议见 `control/SUPERVISOR.md`。
- **复审 Codex**（`gpt-6.1-sol`）：独立复核固定 commit/证据，复现反例，给 PASS/FAIL；
  只读，不改文件，不重做实现。
- **Claude worker**（`deepseek-v4-flash[1m]`）：按有界任务书实现、写测试、生成证据与文档；
  不自行扩范围，不宣布验收。
- **协调（本会话）**：维护 CONTROL/state、原子领取与锁、额度、派发与止损；
  不替代复审，不擅自扩大生产访问范围。
- **交接规则**：角色之间只通过 CONTROL/state + 固定 commit + 证据哈希交接；
  不假设对方知道未记录在案的上下文。

## 规划层级与状态语义（采纳 Codex 建议）

- **L1 路线图**：最终目标、阶段成果、当前里程碑、范围边界；只在范围/阶段变化时更新。
- **L2 阶段计划**：本阶段验收条件、关键路径、已知未知、退出条件；每次阶段检查更新。
- **L3 执行看板**：`Ready → 执行中 → 待评审 → 返修/已验收`；阻塞单列。
- **L4 证据记录**：commit、输入 hash、测试、报告、验收结论；随交付附上。
- **WIP 上限**：最多 1 个主线实现 + 1 个独立对账 + 必要时 1 个关键评审；不同时改同一 worktree。
- **状态三分**：worker 完成 ≠ 评审完成 ≠ 业务验收通过；任务成功不等于里程碑完成。
- **六个指标**：本阶段已验收能力、当前关键路径、最老阻塞及等待时长、待评审积压、同一问题返修轮次、下一份可供业务查看的产物。
- **工具边界**：总控页是唯一项目入口；Orca 保存执行状态；Git/PR 保存交付证据。暂不引入 Linear/GitHub Projects；状态更新使用 `state_update.py`（全局锁），不要直接改 `state.json`。

## 持续调度（Orca automations）

**当前状态（19:36）：Claude / Cross-Review / Adapter / R290 四个 automation 已停用**
（本阶段验收完成，避免空跑）；仅保留 Handoff Check。下一阶段需要时再按下方参数启用。

已验证：心跳 run `2eab6670-729e-4646-b216-0852b0470693` 在 `D:/Work/赛狐/Cursor-claude` **completed**（17:37），随后停用。旧 `.claude/worktrees` 路径被 Orca 判为 unavailable，worktree 已移到 `D:/Work/赛狐/Cursor-claude`。Handoff check 已在 fresh session 成功读取控制页与 v5 证据。

- `G1b-Claude-DN-WO-JC-SE`：`17,47 * * * *`，workspace `D:/Work/赛狐/Cursor-claude`，precheck `G1B-DN-WO-JC-SE`；原子领取 + 180 分钟超时**只标 needs_verification，不自动重派**。
- `G1b-Codex-R290-Recon`：`52 17 * * *`（今天 17:52），Codex #301，precheck `R290-RECON`，`gpt-6.1-sol`；90 分钟超时。
- `G1b-Codex-Adapter-Review`：`10 18 * * *`（18:10），只读审查 DN/WO/JC/SE 抽取器/契约缺口，`gpt-6.1-sol`。
- `G1b-Codex-Cross-Review`：`*/15 19-23 * * *`（19:00 起每 15 分钟），precheck 先刷新额度再判 `G1B-CROSS-REVIEW`；复审不通过会把 Claude 任务设回 ready。
- `G1b-Handoff-Check`：17:41 已成功；验证 fresh session 可读 CONTROL/state/v5 证据。
- 状态真相：`state.json`；`state_update.py` 带全局锁；`precheck.py` 原子领取（`locks/<task>.lock`）、超时回收、`schedule_end=2026-10-22 02:00`；Codex 19:00 后要求新鲜额度读数。
- 新 automation 会话是 **fresh session，不是 fork**；依赖 CONTROL/state/handoff 文档，handoff check 已验证。

## Commit / 证据路径

- Claude #300：`9a04741e`（producer P2 修复），PR https://github.com/keyapi/fzh-data/pull/300
- Claude #300 返修 v2：`49a142e0`（已被交叉复审打回，作废）
- Claude #300 返修 v3：`e6b3cc9a`（UOM 分桶 / 子行传播 / JC 组级非法披露；已被 v3 交叉复审打回，作废）
- Claude #300 返修 v4：`4b7ec55f`（JC 工序 payload 逐个校验 / 整组 invalid 不出 progress），
  evidence `.../g1_contract/out/dn_wo_jc_se/`，zip `out/dn_wo_jc_se_evidence_v4.zip`
  `6cec02bd…`；manifest `3b381d4d…`；payload `8a376557…`；行去向 `95197f06…`；
  stable `6f12333c…`；84/84 本模块离线单测、150/150 g1_contract 离线全套；
  v1/v2/v3 证据作废。
- Codex #301：`d027f981`（阶段日志）、`09ec820a`（R290 交付阻塞与五例接收记录），PR https://github.com/keyapi/fzh-data/pull/301
- v5 evidence：`D:/Work/赛狐/Cursor-claude/docs/research/supply-chain/2026-10-20/claude/experiments/g1_contract/out/family_poc/evidence_d8c473fe_v5/`
- v5 replay zip：同目录 `evidence_replay_e2f9c680_v5.zip`，SHA256 `a3b23cf1684f056daea68f7e7988a12842b40528d61d74f5c5393afaed9bc13c`
- 评审/设计归档：`C:/Users/zhang/.agent-ops/fzh-data/reviews/`

## 额度

- Codex 五小时：18:51:55 已重置；19:00 后完成 3 轮关键复审（v2/v3/v4）与 2 次小探针。
- 重置后页脚在健康额度下不再显示 `5h limit: X%`；`quota_check.py` 无页脚时会跑一次极小
  `codex exec` 探针，成功才标记 `fresh`、`pause=false`（已实测通过）。
- 关键复审保持 `gpt-6.1-sol`；收尾保留 5%–10% 余量；不假定周额度同步重置。
