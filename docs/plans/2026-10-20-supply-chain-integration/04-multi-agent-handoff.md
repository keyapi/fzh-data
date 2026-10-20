---
okf: v0.1
type: Handoff
title: 供应链整合 — 多 Agent 并行分工与交接约定
description: 在 Claude / Codex / Cursor 之间拆任务、各自产出、交叉评审、合并成一份架构方案的操作约定；含可直接复制的开场提示词
date: 2026-10-20
---

# 04 — 多 Agent 并行分工

> 目标：三个 Agent **同时**做调研，但不互相踩、不重复、不产出三份互相矛盾的结论。
> 原则：**分头做不同的线，最后交叉审**；不要让三个 Agent 做同一份工作然后各说各话
> （除非你要的是「三角验证」，见 §6）。

## 1. 总体节奏

```text
Phase 0  交接（本文）            —— 已完成
Phase 1  三条调研线并行          —— Claude / Codex / Cursor 各一条
Phase 2  交叉评审 + 架构综合     —— 由一个 Agent 主笔，另两个审
Phase 3  纵向切片 PoC            —— 选 1 品类跑通「销售→预测→补货→排产→审批」
Phase 4  推广与工程化            —— 按 02 能力地图铺开
```

**Phase 1 结束前不要写业务代码。** 先把口径、事实源、架构选项定下来。

## 2. 角色分工（推荐）

| Agent | 负责调研线 | 产出文件 | 额外任务 |
|---|---|---|---|
| **Claude**（主力） | **B. AI / Agent SOTA** | `06-research-b-ai-agent-sota.md` | 架构综合主笔（Phase 2）；写 `08-architecture-options.md` |
| **Codex** | **A. 业界最佳实践** | `05-research-a-industry-practices.md` | 仓库资产二次核实（代码级），更新 `01-asset-inventory.md` 的「待复核」项 |
| **Cursor** | **C. 开源方案** | `07-research-c-open-source.md` | 跑 1~2 个最小可行性 spike（装库、跑样例），把结果写进文档 |

### 为什么这样分

- 三条线的**检索源和判断标准不同**（学术/厂商方法论 vs 论文/工程博客 vs GitHub/许可证），
  分头做能最大化覆盖；
- 每条线都有**明确的单文件所有权**，不会冲突；
- 架构综合放在 Phase 2，由读过三份产出的人写，避免「先有结论再找证据」。

### 文件所有权（硬规则）

| 文件 | 所有者 | 其他人 |
|---|---|---|
| `00-brief.md` | Claude | 只读 |
| `01-asset-inventory.md` | Codex（可补） | 只读 |
| `02-capability-map.md` | Claude | 只读 |
| `03-research-plan.md` | Claude | 只读 |
| `05-research-a-industry-practices.md` | Codex | 只读 |
| `06-research-b-ai-agent-sota.md` | Claude | 只读 |
| `07-research-c-open-source.md` | Cursor | 只读 |
| `08-architecture-options.md` | Claude（Phase 2） | 审阅意见写在自己的文件或 PR review |
| `09-roadmap.md` | Claude（Phase 2） | 同上 |

> 想改别人的文件 → 在 PR review 里提，不要直接改。避免三方同时编辑同一文件产生冲突。

## 3. 分支与提交约定

- 每个 Agent 用**自己的分支**：`research/supply-chain-a|b|c`。
- 只提交自己拥有的文件 + 必要的索引更新；**不要 `git add -A`**（工作区可能躺着别人的改动）。
- 文档改动走 PR；Phase 1 的 PR 可以合并到 main（纯文档），Phase 2 的架构方案也先 PR 评审。
- 提交前跑：
  ```bash
  uv run python scripts/check_secrets.py
  uv run python scripts/check_solutions_health.py --fix
  uv run python scripts/update_index.py
  ```
- 文档禁止写：真实客户名、员工名、邮箱、服务器 IP、凭证、内部价格（除非已有脱敏口径）。

## 4. 可直接复制的开场提示词

### 4.1 Claude（本机）

```text
请先读仓库 docs/plans/2026-10-20-supply-chain-integration/ 下全部文件（index 起），
再读 01-asset-inventory.md 里标注「未合并分支」的两份资料：
  origin/claude/frosty-hellman-58de7a:docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md
  origin/feature/ustx-cost-compare:tongtool_order_cost/docs/reference/cost-engine-spec/
然后负责调研线 B（AI/Agent SOTA），产出 06-research-b-ai-agent-sota.md。
要求：结论先行、每条结论带来源 URL 与访问日期、区分厂商主张与独立证据、
明确「AI 能做/不能做/只能辅助」三栏，并设计一个 1~3 天可完成的最小验证实验。
不要写业务代码；不要改别人的文件；完成后开 PR（分支 research/supply-chain-b）。
```

### 4.2 Codex

```text
请先读仓库 docs/plans/2026-10-20-supply-chain-integration/ 下全部文件（index 起），
并 `git fetch --all` 后核实 01-asset-inventory.md 的「待复核」项（代码级：路径、函数、分支）。
然后负责调研线 A（业界成熟架构与最佳实践），产出 05-research-a-industry-practices.md。
重点回答：S&OP/IBP、DDMRP、MEIO、MRP/APS、控制塔、预测治理、资金约束下的补货，
哪些适用于「工厂→头程→海外仓→平台」的多仓跨境场景，哪些不适用。
要求结论先行、证据分级、明确「该抄/不该抄/只借概念」；不要写业务代码；
不要改别人的文件；完成后开 PR（分支 research/supply-chain-a）。
```

### 4.3 Cursor

```text
请先读仓库 docs/plans/2026-10-20-supply-chain-integration/ 下全部文件（index 起），
然后负责调研线 C（开源方案），产出 07-research-c-open-source.md。
覆盖：编排、存储/变换、BI、预测库、优化库、ERP/计划、Agent 框架；
每个候选给 License、最近 release/commit、维护活跃度、部署复杂度、国内可达性、总拥有成本。
至少实际安装并跑通 1 个预测库（如 StatsForecast）和 1 个编排/看板候选的最小样例，
把命令与结果写进文档。
不要写业务代码；不要改别人的文件；完成后开 PR（分支 research/supply-chain-c）。
```

## 5. 合并协议（Phase 1 → Phase 2）

1. 三份调研各自 PR 合并到 main（纯文档）。
2. Claude 主笔 `08-architecture-options.md`：
   - 先列 3 个候选架构（轻/标准/重），各自的能力覆盖、成本、风险；
   - 给推荐 + 理由 + 不选的理由；
   - 每个结论引用 A/B/C 的哪一条证据。
3. Codex 与 Cursor **各自写一份评审意见**（PR review 或独立 md），重点找：
   - 与仓库现有资产的重复/冲突；
   - 被厂商宣传带偏的结论；
   - 成本/维护被低估的地方。
4. 主笔修订后，再写 `09-roadmap.md`（V1 纵向切片 → 推广）。

## 6. 如果你坚持「三个 Agent 做同样的工作」

（用户原话：需要 Codex/Cursor 同步进行「相同的工作」）

那就要改成**三角验证**，否则会得到三份无法合并的综述：

- 三个 Agent 都用**同一份 03-research-plan.md**；
- 各自独立产出（不要互相看），避免锚定；
- 合并时**只保留三方都找到的来源 + 分歧点单列**；
- 分歧点必须回到一手来源裁决，不能投票。

> 代价：工作量 ×3，收益是降低单一模型的偏差。**建议只在「架构选型」这一个问题上做三角验证，
> 调研三条线仍按 §2 分工。**

## 7. 反模式（不要做）

1. **三个人同时改 `02-capability-map.md`** → 冲突且口径分裂。
2. **先选框架再找证据**（例如先决定用 LangGraph，再写理由）。
3. **把厂商 benchmark 当独立结论**。
4. **用 LLM 直接生成预测数字并当成事实**。
5. **在 Phase 1 就开始写连接器/预测代码** —— 口径没定，代码会白写。
6. **只在 main 上找现有资产** —— 本项目最相关的两份资料都在未合并分支。
7. **静默丢弃未匹配数据** —— 沿用 AGENTS.md「把湖煮干」：入 N 出 M，差数必须可追溯。

## 8. Phase 1 完成定义（DoD）

- [ ] 三份调研文档合并到 main，均有来源、日期、证据强度；
- [ ] `01-asset-inventory.md` 的「待复核」项全部有结论（存在/不存在/在哪）；
- [ ] 02 能力地图的 P0 项逐条有「现有/缺口/方案」；
- [ ] 至少 1 个最小技术验证跑通（预测库或编排/看板）；
- [ ] 与用户确认 00-brief §7 的 8 个问题（尤其事实源与审批边界）；
- [ ] 输出 3 个候选架构 + 推荐 + 成本，进入 Phase 2。

## 9. 新对话的第一条消息（建议）

```text
继续供应链整合项目。先读 docs/plans/2026-10-20-supply-chain-integration/（index 起），
再按 04-multi-agent-handoff.md 的 Phase 1 执行：你负责调研线 B，产出 06。
先不要写业务代码；遇到 00-brief §7 的问题先列出来问我，不要假设。
```
