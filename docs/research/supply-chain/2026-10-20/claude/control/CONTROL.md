---
okf: v0.1
type: Plan
title: 供应链整合项目总控页
description: 路线图、当前里程碑、执行看板与证据入口；live 状态见同目录 state.json
created: 2026-10-21
updated: 2026-10-21
---

# 供应链整合 — 项目总控页

Updated: 2026-10-21 18:12 (Asia/Shanghai)

## 已完成（待复审，非 G1 验收）

> `22ae9a1e` 已被 Adapter Review 打回：6 个 P1 使“守恒/完整性”结论不成立，返修中。

- **G1B-DN-WO-JC-SE**：Claude `22ae9a1e`（PR #300）。5 个 top-SKU 快照
  （120 SO / 293 DN / 128 WO / 425 SE / 558 SE 行 / 516 工序组，2,040 行去向）。
  C1 SO↔DN 8,467=8,467 全通过；C2 115 通过 + 2 张 `produced_qty` 失真 + 11 张未开工；
  C3 425/425；`audit_ok=true`、`evidence_complete=true`；35/35 离线单测；两轮稳定摘要一致。
  关键发现：`Work Order.produced_qty` 不可当完工账（739/812 vs SE 103/100，
  可见单据无法解释）；JC 只作进度证据（21 张 WO 末道返工量≠完工量）。
  证据：`out/dn_wo_jc_se/`，zip `dn_wo_jc_se_evidence_v1.zip`
  `e557e0ae…`；行级去向 `436bfa97…`；报告 `g1b_dn_wo_jc_se.md`。
  **本项只证明窄样本关联/守恒契约，不是 G1 或业务验收。**

## 已验收

- **G1 SO 证据门 v5**：Claude `9a04741e` / Codex `d027f981`。反向 BOM、共享 ND、数值 flag P2 均关闭；66 条离线测试通过；v5 evidence `1d6a7b33…`，回放 zip `a3b23cf1…`；20 样本全部 pending，PK/ND family=0，无 `historical_verified`。接受范围仅为 `current_structure_only` + 历史未知保留 pending。
- **无证据表 R1/R2 审计门**：`d8c473fe`；52 SO / 2,024 行；family 132 / pending 1,769 / out_of_scope 123；两轮一致；已接受。
- **历史证据边界**：Codex `d3fc4c8d`（#301）；Version/modified 不足以升级历史，需可信锚点/变化覆盖/生效证据或明确交易绑定。

## 进行中

- **G1B-ADAPTER-REVIEW**（Codex）：已完成对 `22ae9a1e` 的只读审查，**6 P1 + 3 P2**。
  结论：需修复后才能接受适配器；报告归档
  `C:/Users/zhang/.agent-ops/fzh-data/reviews/2026-10-21-dn-wo-jc-se-adapter/report.md`。
- **G1B-DN-WO-JC-SE 返修**（Claude）：已置 `ready` 并派发；按 9 项发现修复
  （C1 逐行全精度、DN join 语义、UOM 分区、SE 父元数据、SE 覆盖完整性、C4 原始输入计数、
  有符号退货、请求级 HTTP 预算、最终 payload 校验和），生成新 commit + 新证据包。
- **G1B-CROSS-REVIEW**（Codex）：`waiting`，**不审 `22ae9a1e`**；待返修新 commit 后置 `ready`。

## 阻塞

- **R290-RECON（2026-10-21 17:56）交付阻塞**：未提供可绑定 #290 的冻结包路径/commit/hash 及五例清单；已检查交付位置未定位到包。5 = 已接收 0 + 待交付 5；accept=0、scenario=0，四项语义均未验收。未重复领取、未访问生产、未改原型。证据：[Codex 对账记录](C:/Users/zhang/.codex/worktrees/supply-chain-independent-research/Cursor/docs/plans/2026-10-20-codex-supply-chain-research/r290-reconciliation.md)。待交付后继续。

- `historical_verified` 的历史锚点/有效期证据仍缺，历史关系保持 pending。
- 全 family 扩样未授权。
- 业务裁决：服务水平/预算、3PL 供货归属、退货回库比例。

## 下一步

1. ~~Claude 提交 DN/WO/JC/SE 固定 commit + 证据包~~ → 已交付 `22ae9a1e`。
2. Codex 对 `22ae9a1e` 做关键复审（`G1B-CROSS-REVIEW` 已 ready）；R290 对账结果归档。
3. 再决定扩样到 100/全 family，还是进入 G2/G3 预测与补货。
4. 今晚收尾时跑一次 `/ce-okf`，把 SO/证据门与 producer 经验正式归档。

## 修正

- #290 已有**实验原型**待对账，不是“预测/补货尚未开始”。主线尚未验收，但原型资产存在。

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
- Claude #300 新增：`22ae9a1e`（DN/WO/JC/SE 关联与同单位守恒），
  evidence `.../g1_contract/out/dn_wo_jc_se/`，zip `out/dn_wo_jc_se_evidence_v1.zip`
- Codex #301：`d027f981`（阶段日志）、`09ec820a`（R290 交付阻塞与五例接收记录），PR https://github.com/keyapi/fzh-data/pull/301
- v5 evidence：`D:/Work/赛狐/Cursor-claude/docs/research/supply-chain/2026-10-20/claude/experiments/g1_contract/out/family_poc/evidence_d8c473fe_v5/`
- v5 replay zip：同目录 `evidence_replay_e2f9c680_v5.zip`，SHA256 `a3b23cf1684f056daea68f7e7988a12842b40528d61d74f5c5393afaed9bc13c`
- 评审/设计归档：`C:/Users/zhang/.agent-ops/fzh-data/reviews/`

## 额度

- Codex 五小时：17:37 约 **30%**，18:51:55 重置；**19:00 起**再派 Codex（重置可能延迟生效）。
- 不再固定保留 30%；以 5%–10% 作收尾余量；关键复审保持 `gpt-6.1-sol`。
- 额度读数由 `quota_check.py` 带时间/来源写入 `state.json`；19:00 后的复审要求 fresh 读数。
- 不假定周额度同步重置；每个任务结束刷新额度。
