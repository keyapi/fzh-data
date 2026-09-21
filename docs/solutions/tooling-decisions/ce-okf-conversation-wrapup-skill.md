---
okf: v0.1
type: Reference
title: ce-okf skill — 把「ce-compound + OKF 收尾」固化成一个命令
date: 2026-09-21
category: tooling-decisions
module: .agents/skills
problem_type: tooling_decision
component: tooling
severity: medium
applies_when:
  - "用户说「收尾 / 沉淀 / 用 ce-compound 和 okf 标准记录本次对话，然后提交 PR」"
  - "要在本仓库建新 skill，或判断该包一层外部 skill 还是直接改它"
  - "回答「为什么 ce-compound 写完不提交」"
tags: [skill, ce-compound, okf, workflow, documentation, handoff]
---

# ce-okf：把固定收尾动作固化成一个命令

## Context

2026-07-28 ~ 09-20 期间，用户在 40+ 个会话里**手打同一段**中文提示词（去重后 29 个版本，骨架完全一致）：

> 请你用 `/ce-compound`（或 `-refresh`）okf 标准，按照项目要求和以往规则，把本次对话中背景 / 过程 / 结果 / 经验教训，补充更新记录到文档、脚本、skill、handoff 文件，方便之后你自己新开对话或别的 Agent 查到并理解、不用再次踩坑，注意不要泄露隐私。之后 git 提交 并 PR。

复述这段话的成本不只是打字：它实际编码了 **AGENTS.md 第 8/9/10/11 条**四条硬规则，外加一套 8~11 个文件的级联登记。靠人每次都复述全，必然漏项——实测最容易漏的是 `scripts/update_index.py`（第 11 条）、category 级的 `index.md`、以及 `log.md` 的当日条目。

## Guidance（本学习沉淀的做法）

**建 `ce-okf`，做成「包一层」而不是「改 ce-compound」。** 三层分工：

| 组件 | 负责 |
|---|---|
| `ce-compound` / `-refresh`（用户级外部 skill，`~/.agents/skills/`） | 学习正文质量：3 个并行子代理、重叠检测、grounding 校验、`CONCEPTS.md` 词表 |
| `okf`（本仓库 `.agents/skills/okf/`） | 三条铁律：`type` 必填 / 每目录 `index.md` / 每 bundle `log.md` |
| `ce-okf`（本仓库 `.agents/skills/ce-okf/`） | schema 归一化 + 级联登记 + 索引联动 + 凭证扫描 + 提交 + PR |

三条支撑这个决策的事实：

1. **`ce-compound` 写完文档就结束回合，不提交、不开 PR。** 这是缺口所在——它的 `SKILL.md` 明确说"End the turn after the summary"。而用户每次都要"之后 git 提交 并 pr"。（`ce-compound-refresh` 反而在 Phase 5 会提交，两者行为不对称。）
2. **`ce-compound` 的 `component` 枚举是 Rails 味儿的**（`rails_model` / `hotwire_turbo` / `frontend_stimulus` / `background_job`…），而本仓库 `docs/solutions/**` 早就演化成 **OKF + ce-compound 合并 frontmatter**：既有 `okf: v0.1` + `type: Reference`，又有 `module/date/problem_type/component/severity`。`ce-compound` 自己不会写前两个字段。
3. **`ce-compound` 是外部 skill，改它不随本仓库 PR 走。** 同事的 Agent / claude desktop 拉 main 后拿不到——而"别的 Agent 也要能查到"正是用户诉求的一部分。

所以归一化（第 2、3 点）和提交/PR（第 1 点）必须落在**仓库内**的 skill 里。

另外四条实测细节：

- **`scripts/update_index.py --check` 不能当硬门禁**。它是逐字节比对，而生成的文件头 `generated:` 是**分钟级**时间戳，所以只有"刚生成完的同一分钟内"才会通过，绝大多数时候误报 `STALE`。判断索引是否同步要看**内容**（新文档有没有出现在索引表里），不看退出码。
- **索引日期列注定滞后一个 commit**：脚本优先取 git commit 日期，未跟踪文件回落 mtime。「先生成、后提交」时，本次改动的文件在索引里显示的是**上一次**提交日期。仓库现役习惯就是和文档放同一个 commit（如 `3ee5ca8`），不必为对齐日期再补一个 commit。
- `docs/solutions/` 各 category 的 `index.md` **表头不统一**：`integration-issues/index.md` 是 `| 日期 | 标题 | 文件 |`，`tooling-decisions/index.md` 是 `| 标题 | 文件 |`。追加行要**以该文件现役表头为准**。
- `<module>/AGENT_HANDOFF.md` 用的是 `type: Handoff`（**不在** okf 的 `type` 枚举里）和 `updated:`（**不在** okf 字段表里）。这是现役事实，不要去"修正"。

## Why This Matters

- 收尾动作从"每次口述 8 条要求"变成"打一个 `/ce-okf`"，且**漏项率归零**——四条硬规则由 skill 强制执行，而不是靠 Agent 记性。
- 决策本身可复用：遇到"想改一个外部 skill"时，先问它是否随仓库分发；不随 → 包一层。这条判断比本次具体实现更值钱。
- 明确了 `ce-compound` 的能力边界（正文强、收尾无），避免以后误以为它已经处理了提交。

## When to Apply

- 用户说「收尾 / 沉淀 / 总结本次对话 / 用 ce-compound 和 okf 标准记录，之后提交 PR」时。
- 在本仓库新增 skill 时（另见 `CONTRIBUTING.md` 的「新增 Skill 或模块」5 步，其中一步是往 `AGENTS.md` 模块索引表加行）。

## Examples

```
/ce-okf              # 默认：一路做到 PR
/ce-okf refresh      # 增量：只补上一次提交之后的内容
/ce-okf no-pr        # 只本地提交
```

skill 本体：`.agents/skills/ce-okf/SKILL.md`。装的机器要跑一次
`powershell -ExecutionPolicy Bypass -File setup.ps1` 才会被 Claude Code / Claude Desktop 看到（`setup.ps1` 把 `.agents/skills/*` 链进 `~/.claude/skills/`）。

## Related

- [`okf` skill](../../../.agents/skills/okf/SKILL.md) — 三条铁律的出处
- `AGENTS.md` 第 8/9/10/11 条 — 分支/PR、凭证扫描、OKF 规范、索引联动
- [`docs/solutions/conventions/`](../conventions/) — 同类的"约定型"记录
