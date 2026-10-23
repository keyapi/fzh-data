---
okf: v0.1
type: Handoff
title: 供应链项目调度交接（2026-10-22）
date: 2026-10-22
---

# 调度交接

## 项目目标

**从最新可得库存 as_of 出发，往未来算补货建议**（不是还原历史某一天的库存）。
结合已下单/未结 PO、在产、已发货，判断哪些 SKU×仓可能缺货或积压。
当前只做只读试点 + B 情景测算，**不自动下单**；业务签认不是停止本地研发的理由。

## 当前状态（2026-10-23 晚更新，替代此前 10-SKU 旧状态）

- **口径纠偏（重要）**：此前把「10/1 期初未证」当作整体阻塞，**是目标偏移**。
  10/1 未证**只阻塞历史回放**；前向计划从 **2026-10-22 库存快照**起算，并**明示陈旧度**。
- **已定结论**：
  - 10 月桶**历史回放不可算**（入库/调拨/退货/盘点调整在库中无表，`SHOW TABLES` 已核）；
  - PB 删失路线**本批无收益且更差**（Δ +0.0254，CI [+0.0110,+0.0436]），旧「删失更好」作废；
  - 538 未验证 SKU 分档：**可验证 239 / 仅影子 155 / 不足 87**，57 未映射隔离；
  - **239 长历史档**：无方法显著优于 naive（CI 全跨 0）；
  - **790 全 SKU 回测**：tree **.49386** / combo .52365 / MA3 .63113 / naive .60592。
    ⚠️ **不得把 239 的"无显著差异"泛化成"所有复杂模型没收益"**——树在 790 上优势明显，
    差异可能来自跨 SKU 借力在短史段起作用。
- **数量侧**：206 个 SKU 过四门，**A 批 = 0**（缺《补货测算依据确认单》，见 D37），206 全部 B 情景。
- **模型接入**：现有数量表仍用 **T5 AutoETS 平月率**，**新模型尚未接回**，切换点待 Codex2 裁定。
- **交付材料**：`control/reviews/2026-10-23-delivery-brief.md`、
  `control/templates/replenishment-basis-confirmation.md`。

## 进程事实（2026-10-23 晚）

- 全部历史遗留 PID 已退出；不重启、不复制旧任务。
- 当前在跑：前向净需求（打工仔1）、DN 运单桥（打工仔2）、前向交付方案（Codex2）。


## 角色注册表（重启后先校验 handle；替换必须在本表留记录）

| 角色 | 精确 handle | 当前任务 | 状态 | 最近证据 | 下一负责人 |
|---|---|---|---|---|---|
| Claude工头｜项目调度 | `term_3f397f4a-1360-4af0-900e-08f014acfed1` | 唯一日常调度 + **唯一提交者** | 工作中 | run `run_ab028056dc4e`；已落地 `dcdc430b` → `b9c9b4ed` → `b2217e4d` → `1a66d3fc` → `fd3aa72f` → `7d9f7fc7` → `9acec3db` | 工头 |
| Claude打工仔1｜全 SKU 主线 | `term_dae491ca-08bf-462c-b402-0938a02cb4f6` | R3-N04 生成器字段同步（task `task_bf74836e9f97`） | 运行中 | R3 `fd3aa72f` 已 PASS-with-minor（301 核 M01/N01/N02/N03 全 PASS，数值未变）；dispatch `ctx_25c760c246b7` | 工头收 DONE FULLSKU-R3-MINOR |
| Claude打工仔2｜PB 断货验证 | `term_696190a8-f7c6-4869-87bf-ed59c893677b` | 空闲 | 空闲 | R2 `b2217e4d` + 零分母 minor `9acec3db`；301 判 **PASS-with-minor**（唯一 minor 已修） | 待工头派新任务 |
| Codex #301｜独立审核 | `term_d0bcd5e0-9f57-43b9-8dfc-6ffe4578063a` | 空闲 | 空闲 | 四份复审：CENSOR **FAIL** / FULLSKU **FAIL** / PB-R2 **PASS-with-minor** / FULLSKU-R3 **PASS-with-minor**；5h 额度约 20%，**只接窄审** | 工头 |
| Codex2｜决策参谋 | `term_0eb8e41d-dc3e-4b3f-bbb2-7e7e4aed1a87` | 已完成有界裁决（D35） | 空闲 | 模型准入 / 538 去向 / 数量衔接三项已交付，记入 `DECISIONS.md` D35 | 工头 |
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
