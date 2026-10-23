---
okf: v0.1
type: Handoff
title: 供应链项目调度交接（2026-10-22）
date: 2026-10-22
---

# 调度交接

## 项目目标

预估未来需求；结合今天库存、已下单/未结 PO、在产、已出库，判断哪些商品可能缺货、是否需要补货。
当前只做窄范围只读试点，不自动下单。

## 当前固定版本

- V0.1：`98e1c664` **已冻结**。SO 正向求和 2,924（超发 -907 单列）、B_min/B_max、日历点预测、
  零需求处理有效；**P90/区间及衍生补货结论失效**（#301 FAIL：2 major + 1 minor，无 blocking）。
- 暂行行动清单：`8641bf87`（最终）；10 SKU，`always_replenish 0 / depends_on_arrival 6 / insufficient_evidence 4`；
  不含 P90、不含数量。
- V1 候选模型赛马：`f9df4357`（origin HEAD；= `3a19cd05` + 报告 3 行「共形标定与报告起点重叠」标注）；
  10 SKU；seasonal naive / mean3 / seasonal×YoY / peer shape（ETS 因库缺失跳过）；
  累计 P90 用滚动累计误差/共形校准；报告已生成。结论口径：**L90 总是需补 4 / 证据不足 6；无单一模型赢家；P90 仍是 estimate**。
- R290/Cover/UOM/SKU 映射：保留为局部未知，不阻塞本轮。

## 进程事实（2026-10-22 15:15 复核）

- PID 46980（V1 模型赛马）与 PID 47424（行动清单）**均已退出**；两者是遗留外部 `claude -p`，
  产物已分别固定在 `f9df4357` 与 `8641bf87`。**不重启、不复制其任务**，不作常驻角色。
- #301 的 R1 只读复审是当前唯一在跑的任务。

## 角色注册表（重启后先校验 handle；替换必须在本表留记录）

| 角色 | 精确 handle | 当前任务 | 状态 | 最近证据 | 下一负责人 |
|---|---|---|---|---|---|
| Claude工头｜项目调度 | `term_3f397f4a-1360-4af0-900e-08f014acfed1` | 唯一日常调度 + **唯一提交者** | 工作中 | run `run_ab028056dc4e`；本轮已落地 commit `dcdc430b`（清关阻塞）→ `b9c9b4ed`（全 SKU）→ `b2217e4d`（PB R2） | 工头 |
| Claude打工仔1｜全 SKU 主线 | `term_dae491ca-08bf-462c-b402-0938a02cb4f6` | R3 窄返修：A 包训练池归因 / 分型时点措辞 / 冻结 CSV hash（task `task_0fca24196c39`，base `b9c9b4ed`） | 运行中 | 前置已交付 `b9c9b4ed`；301 判 FAIL（1 major + 3 minor，数值全可复现）；dispatch `ctx_42cf3871fe7f` | 工头收 DONE FULLSKU-R3 |
| Claude打工仔2｜PB 断货验证 | `term_696190a8-f7c6-4869-87bf-ed59c893677b` | 空闲（R2 已交付） | 空闲 | session `33a53c4b…`；`task_4fe287aaeeb5` 完成，成果已提交 `b2217e4d`：M01 方向已修、旧改善作废、R2 在未删失月可测更差 | 工头按 301 窄复审结果决定是否再派 |
| Codex #301｜独立审核 | `term_d0bcd5e0-9f57-43b9-8dfc-6ffe4578063a` | 窄复审 `b2217e4d`（task `task_22bdff00ce5d`） | 运行中 | 已交两份 FAIL 报告：CENSOR-REVIEW、FULLSKU-REVIEW；5h 额度紧张，**只接窄审**；dispatch `ctx_8c64e2e56c80` | 工头收 DONE PB-R2-REVIEW |
| Codex2｜决策参谋 | `term_0eb8e41d-dc3e-4b3f-bbb2-7e7e4aed1a87` | 有界决策：模型准入 / 538 SKU 去向 / 数量衔接（task `task_1cf75e2ea940`） | 运行中 | `GPT-6.1-Sol medium`；dispatch `ctx_2575f587b47a` | 工头收决策 |
| ~~Claude打工仔｜旧实施~~ | `term_4c1c8d12-ba0a-4cdb-9dc3-b3b464bc7449` | — | **已退役（2026-10-23）** | 上下文近满；R1-FIX 已交付 commit `a59dc213`；**不再派新任务**，终端保留不删 | 无人 |
| ~~Claude打工仔｜旧终端~~ | `term_6d7a52b3-26e4-4278-b21f-4269cd5c5b89` | — | **已退役（2026-10-23）** | 读屏 `100% context used`；**不再派新任务**，终端保留不删 | 无人 |

规则（硬约束）：

- **重启/换会话先校验**：`orca terminal show --terminal <handle>`；失效则新建并在本表追加「旧 handle → 新 handle + 原因」，**不删旧行、不改写历史**。
- **标题限制**：`terminal rename` 只改 tab 标题，Codex 侧模型会改写标题（#301 现显示 `[ . ] Action Required | 梳理供应链整合与AI调研` 即为证据）。所以**不声称侧栏名已永久固定**，每轮以读屏结果为准。
- **单一写入者（2026-10-23 修订）**：两名打工仔 + 工头同处 `D:/Work/赛狐/Cursor-claude` 这一个 worktree。
  因此本轮起改为：**打工仔一律不 commit、不 push，只回报文件路径；工头是唯一提交者**，在两个任务都 settle 后一次性提交。
  提交前逐文件确认不含行级业务数据（见 `DECISIONS.md` D33 清关阻塞）。
- **完成接收链路**：正式派工走 Run/Task/Dispatch + `worker_done`；复用交互终端用 `terminal send`（**文本与 `--enter` 分开发**，否则被 `agent_prompt_blocked`）+ `terminal wait` + 读屏取真实结论。**accepted ≠ 执行成功**。
- **模型**：不擅自改模型。工头 `manual mode on`；打工仔现为 `bypass permissions on`（用户选 B 后重启，仍非 auto）；
  Codex2 为 `GPT-6.1-Sol medium`（用户指定），旧 Codex2 为默认 `GPT-5.6-Terra`。

### 替换记录（只追加，不删旧行）

- 2026-10-22 15:5x 打工仔 `term_f443cc5c…`（acceptEdits）→ `term_4c1c8d12…`（bypassPermissions）。
  原因：acceptEdits 下带引号/`&&` 链的复合命令被"引号内容无法预检"反复拦截；Codex2 选 A（补 Bash 白名单）落地后本轮仍拦，
  用户改选 B，重开终端加载 `implementer-permissions.json`（defaultMode=bypassPermissions，deny 保留 `git push`/`merge`/`rm`/`reset --hard`/force）。
  旧终端保留未删，旧 Dispatch `ctx_7236059bef35` 已 `worker-abandon`（未声称其进程停止）。
- 2026-10-22 15:5x Codex2 `term_a137bdd7…`（GPT-5.6-Terra）→ `term_0eb8e41d…`（**GPT-6.1-Sol**，按用户要求）。旧终端保留未删。
- 2026-10-23 Claude 打工仔**扩编为 2 名**（用户授权，用 Claude 而非 Codex 以保留 Codex 额度）：
  新增 `term_696190a8-f7c6-4869-87bf-ed59c893677b`（session `33a53c4b-fb73-4903-881f-2707ae5636a8`，Flash + bypass）。
  旧 `term_4c1c8d12…`、`term_6d7a52b3…` 上下文近满/已满，**登记退役、不再派任务**，终端保留未删。
- 2026-10-23 工头本机 DeepSeek 上游额度重置后，**在原终端 `term_3f397f4a…` 内 `/clear` 恢复**（未另开总调度、未新建工头）。
  上一轮 99% 上下文 + 网关 403 `need123727` 导致消息无法执行；旧会话保留未删。

## 下一步（完成即流转）

1. ~~收 V1 与行动清单的最终 commit~~ **已完成**：V1 `f9df4357`、清单 `8641bf87`（均已 push 为 origin HEAD）。
2. R1 复审已出 **FAIL**（无 blocking，4 major + 3 minor）；原始报告在 #301 自己 worktree，
   已抄入本仓库 `control/reviews/2026-10-22-v1-r1.md`（内容逐字一致）。
3. FAIL 结论的处理：major 交 **Claude打工仔**（`term_f443cc5c…`）做局部离线返修，返修后再交 #301 复审；
   取舍类问题（范围/口径）先问 **Codex2**（`term_a137bdd7…`）。已授权的窄范围离线返修与再审不逐次问用户。
4. 任何新增全局阻塞必须证明所有任务都无法继续；局部缺数隔离。
5. 不访问生产、不扩样、不下单、不合并 PR。

## 禁止

- 不再从旧会话派新工；旧会话只作历史资料。
- 不杀正在收尾的进程，不重复启动同一任务。
- 不用外部 `claude -p` 绕过 Orca；无法使用指定入口时报告阻塞。
