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
| Claude工头｜项目调度 | `term_3f397f4a-1360-4af0-900e-08f014acfed1` | 唯一调度：派工、收结果、送审 | 工作中 | run `run_ab028056dc4e`；task `task_84a848a8e987`；#301 派工 request `f9993dfb…`、更正 `ab1f8738…` | 工头 |
| Claude打工仔｜实施 | `term_dae491ca-08bf-462c-b402-0938a02cb4f6` | T39 下单时点回测（dispatch `ctx_1dff4226e7b4`） | 运行中 | 第三次上下文超限更换终端（`term_6d7a52b3…` 100% context）；旧终端保留未删 | 工头收结果 |
| Codex #301 | `term_d0bcd5e0-9f57-43b9-8dfc-6ffe4578063a` | R3 复审（已完成） | 空闲 | 读屏 `DONE R3`：**FAIL，无 blocking，仅剩 1 major**（六门过后仍用冻结 B_max 判充足）；报告抄入 `control/reviews/2026-10-22-v1-r3.md` | 待 R4 后再审 |
| Codex2｜决策参谋 | `term_0eb8e41d-dc3e-4b3f-bbb2-7e7e4aed1a87` | 只读待命：回答取舍与判定标准 | 待命 | 读屏 `GPT-6.1-Sol medium`；rename ok；旧终端 `term_a137bdd7…`（GPT-5.6-Terra）保留未删 | 工头 |

规则（硬约束）：

- **重启/换会话先校验**：`orca terminal show --terminal <handle>`；失效则新建并在本表追加「旧 handle → 新 handle + 原因」，**不删旧行、不改写历史**。
- **标题限制**：`terminal rename` 只改 tab 标题，Codex 侧模型会改写标题（#301 现显示 `[ . ] Action Required | 梳理供应链整合与AI调研` 即为证据）。所以**不声称侧栏名已永久固定**，每轮以读屏结果为准。
- **单一写入者**：工头与打工仔同处 `D:/Work/赛狐/Cursor-claude`，同一时刻只允许一方 `git commit`；派工期间工头不提交。
- **完成接收链路**：正式派工走 Run/Task/Dispatch + `worker_done`；复用交互终端用 `terminal send`（**文本与 `--enter` 分开发**，否则被 `agent_prompt_blocked`）+ `terminal wait` + 读屏取真实结论。**accepted ≠ 执行成功**。
- **模型**：不擅自改模型。工头 `manual mode on`；打工仔现为 `bypass permissions on`（用户选 B 后重启，仍非 auto）；
  Codex2 为 `GPT-6.1-Sol medium`（用户指定），旧 Codex2 为默认 `GPT-5.6-Terra`。

### 替换记录（只追加，不删旧行）

- 2026-10-22 15:5x 打工仔 `term_f443cc5c…`（acceptEdits）→ `term_4c1c8d12…`（bypassPermissions）。
  原因：acceptEdits 下带引号/`&&` 链的复合命令被"引号内容无法预检"反复拦截；Codex2 选 A（补 Bash 白名单）落地后本轮仍拦，
  用户改选 B，重开终端加载 `implementer-permissions.json`（defaultMode=bypassPermissions，deny 保留 `git push`/`merge`/`rm`/`reset --hard`/force）。
  旧终端保留未删，旧 Dispatch `ctx_7236059bef35` 已 `worker-abandon`（未声称其进程停止）。
- 2026-10-22 15:5x Codex2 `term_a137bdd7…`（GPT-5.6-Terra）→ `term_0eb8e41d…`（**GPT-6.1-Sol**，按用户要求）。旧终端保留未删。

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
