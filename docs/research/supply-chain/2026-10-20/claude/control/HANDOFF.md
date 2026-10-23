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
| Claude工头｜项目调度 | `term_3f397f4a-1360-4af0-900e-08f014acfed1` | 唯一日常调度：派工、收 worker_done、送审 | 工作中 | 2026-10-23 原终端 `/clear` 后同 handle 恢复；run `run_ab028056dc4e`（coordinator_handle 实测一致）；本轮三次 dispatch `ctx_88424bd7d26f` / `ctx_a3e08d14c590` / `ctx_3a0b09995bad` | 工头 |
| Claude打工仔1｜全 SKU 主线 | `term_dae491ca-08bf-462c-b402-0938a02cb4f6` | 全 SKU 预测分型 + 全局 LightGBM / 供需主线衔接（task `task_8a0d035f4046`） | 运行中 | dispatch `ctx_a3e08d14c590`，`injected=true`，读屏已见读 `RESEARCH_ADOPTION.md` + `duckdb read_only` 查询（turn 已起，24s） | 工头收 DONE FULLSKU |
| Claude打工仔2｜PB 断货验证 | `term_696190a8-f7c6-4869-87bf-ed59c893677b` | PB 删失实验核查与改进（task `task_fcbda0190e33`） | 运行中 | 用户新授权（非 Codex）；session `33a53c4b…`；READY WORKER2 已核（`deepseek-v4-flash[1m]`、bypass、cwd 正确）；dispatch `ctx_88424bd7d26f`，读屏已见读 `stockout_intervals.csv` + `2026-10-23-pb-stockout.md`（turn 已起） | 工头收 DONE PB-AUDIT |
| Codex #301｜独立审核 | `term_d0bcd5e0-9f57-43b9-8dfc-6ffe4578063a` | e1b9b5d7 删失对照 + D32 三源交叉复审（task `task_cba657429b75`） | 运行中 | dispatch `ctx_3a0b09995bad`，`GPT-6.1-Sol medium`，读屏 `Working` | 工头收 DONE CENSOR-REVIEW |
| Codex2｜决策参谋 | `term_0eb8e41d-dc3e-4b3f-bbb2-7e7e4aed1a87` | 只读待命：回答取舍与判定标准 | 待命 | 读屏 `GPT-6.1-Sol medium`；rename ok；旧终端 `term_a137bdd7…`（GPT-5.6-Terra）保留未删 | 工头 |
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
