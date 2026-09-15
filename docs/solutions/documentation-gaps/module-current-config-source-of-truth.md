---
okf: v0.1
type: Solution
title: 判断模块「当前配置」的可信来源顺序 —— 历史快照不等于现值
date: 2026-09-15
category: docs/solutions/documentation-gaps/
module: us_openai_api_proxy
problem_type: documentation_gap
component: documentation
severity: medium
root_cause: inadequate_documentation
resolution_type: documentation_update
applies_when:
  - 需要以「模块现在是怎么配的」为依据给出建议时
  - 准备建议改配置、做迁移、换供应商之前
  - 模块文档看起来完整，但其实是刻意脱敏的
  - 准备把 `.codex_tmp/` 下的任何值当成现值之前
  - `docs/log.md` 记录了一次变更，但细节被刻意省略时
symptoms:
  - 给出的建议引用了该模块早已停用的订阅供应商
  - 当前供应商的名字只能从一篇无关的 solutions 文档交叉引用里找到
  - 模块自己的 changelog 写了「订阅换了」但不写换成什么
  - 新 Agent 只有在加载了该模块的 skill 之后才会看到「禁止从旧 markdown 抄地址」这条规则
tags:
  - documentation-sources
  - stale-snapshot
  - desensitized-docs
  - source-of-truth
  - agent-onboarding
  - config-current-state
  - privacy-boundary
  - us-openai-api-proxy
related_components:
  - documentation
  - development_workflow
---

# 判断模块「当前配置」的可信来源顺序 —— 历史快照不等于现值

## Context

一次调研任务中，Agent 需要以项目**已记录的网络资产**为底，回答一个配置类问题。它在 `grep` 结果里读到了 `.codex_tmp/sellfox-suite-pairing-audit/us_openai_api_proxy/docs/operations.md`（**gitignored 的历史快照，不在 worktree 内、也不在版本控制中**），看到里面通篇写着一个具体的代理订阅供应商名，于是**把它当成北京办公室当前使用的供应商**并据此展开建议。用户当场纠正：该供应商早已被替换。Agent 引用的是迁移前的快照。

这不是一次性失误，而是这个仓库里的一个**结构性陷阱**：模块同时保留了两套东西——一份**历史快照树**（未脱敏、内容详尽）和一份**刻意脱敏的现值文档集**（内容克制）。而脱敏恰恰意味着现值文档只会告诉你*「有个东西变了、什么时候变的」*，**永远不会告诉你*变成了什么***。于是：**越详尽的文档越可能是过期的**，而 Agent 的「哪份看起来更权威」直觉会把票投给错误的那一份。

### 为什么那次迁移是「隐形」的

三个属性叠加，让过期快照看起来完全可信：

1. **`.codex_tmp/` 里放的是历史快照，其中没有任何内容是现值。** 该快照的 `us_openai_api_proxy/docs/log.md` 停在 v0.11–v0.12 时期，描述的是那个阶段的订阅故障与应急兜底改造。它自洽、带日期、读起来就是一份真实的运维手册——因为**在当年它确实是**。

2. **现值记录是刻意脱敏的。** 线上的 `us_openai_api_proxy/docs/log.md` 里 v0.14（2026-08-25）只写了一句「更新办公室代理订阅与策略组映射」——记录了*「订阅换过」和「什么时候换的」*，但**省略了换成了什么**。边界写在同一份文件的第 10 行：「服务器、账号、授权材料、私有地址、订阅与访问凭据均不入库」。所以：**只读现值 log 的 Agent 知道发生过变更，却叫不出新供应商的名字——然后就会忍不住去快照里「补上这个名字」。**

3. **那个被隐去的名字，只能从一篇无关文档的交叉引用里找到。** `docs/solutions/best-practices/adobe-genuine-prompts-office-openclash.md:55` 提到「`us_openai_api_proxy/docs/log.md` v0.14 记录同一时期的 <供应商> 迁移与规则调整」。一篇讲 Adobe 授权弹窗的文档，反而是唯一点名当前供应商的地方。

而项目**其实早就把规则写下来了**，只是写在新 Agent 不会主动加载的地方：`.agents/skills/us-openai-api-proxy/SKILL.md:32-33` 要求占位符一律从 gitignored 的 `us_openai_api_proxy/.env` 解析，并明确写着「**禁止从旧 markdown 或 `office-lan-access.md` 抄地址**」；`SKILL.md:35-36` 与 `us_openai_api_proxy/AGENT_HANDOFF.md:43-47`（「隐私与变更边界」）进一步禁止输出私有地址与网络拓扑。**这条规则存在、正确，却依然被绕过了——因为 Agent 在伸手拿那份文件之前，从没加载过该模块的 skill。**

## Guidance

需要模块**当前**配置时，按下面的来源优先级取信。

### 1. 权威（可据此下判断）

- 模块的现值 `docs/` 文件（`us_openai_api_proxy/docs/architecture.md`、`us_openai_api_proxy/docs/index.md`、`us_openai_api_proxy/docs/lan-gateway.md`、`us_openai_api_proxy/docs/reference/` 等）。
- `us_openai_api_proxy/docs/log.md` —— **日期与变更描述是可信的，即使细节被隐去。** 用它定位变更发生的时点、判断哪个子系统被动过。
- 模块的 `AGENT_HANDOFF.md` —— 模块自述的当前状态，以及约束「允许输出什么」的边界。
- 模块 `.env`（gitignored，**不在版本控制中**；凭证在父仓库而不在 worktree）—— 占位符背后的真实取值。

### 2. 陷阱（不可据此下判断）

- **`.codex_tmp/` 下的一切都是历史快照。** 它适合用来还原时间线、理解当年为什么那样决策；**它永远不是现值**。其中出现的任何供应商、端点、凭据名，一律先当可疑，直到在别处得到确认。
- **不要把脱敏文档当成完整的文档来读。** `us_openai_api_proxy/docs/log.md` 里没有名字是**刻意的删节**，不是「去别处找名字」的邀请。它只说明*变了什么类别、什么时候*，从不说明*变成了什么*。

### 3. 桥梁（可以借此收敛，但需二次确认）

- **`docs/solutions/` 里其他文档的交叉引用，常常点名模块文档刻意隐去的具体值。** 需要具体值时，用模块名跨 `docs/solutions/` 搜索：

  ```bash
  grep -rn "us_openai_api_proxy" docs/solutions/
  ```

  本次就是这样找到当前供应商名的。**但交叉引用同样是二手信息**，确认前不要直接当现值用。

### 4. 未决项

- 当 `docs/log.md` 记录了一次细节被隐去的变更时，把「当前供应商/端点是哪个」当成一个**需要向用户或受控环境确认的未决项**，而不是一件可以从旧快照里「还原」出来的事实。**还原——正是上面那个失败模式本身。**

## Why This Matters

**把过期快照当成现值，产出的是「自信的错误建议」。** 本次调研因此建立在一个已停用的供应商之上；唯一拦住它的是用户本人的纠正。

**这个失败是静默的。** 那份过期快照自洽、带日期、而且**比现值文档更详尽**——Agent 用来判断权威性的每一个信号，都指向了错误的一边。现值文档的「正确」（即它的脱敏），恰恰让它看起来更没用。没有报错、没有断链、没有失败的测试：只有一个 Agent 流畅地基于一个已经不存在的供应商做推理。

**爆炸半径是真实的建议。** 这是一次调研任务，其产出会直接喂给用户据以行动的决策。基于一个幽灵供应商给出的迁移或配置建议，比不回答更糟——因为它携带了 Agent 表面的笃定。

## When to Apply

- 任何时候要以「这个模块现在是怎么工作的」为依据下判断——尤其是准备建议改配置、做迁移、换供应商，或任何用户会照着做的事之前。
- 当模块文档看起来完整、但你要的值偏偏明显缺席时（这是**删节信号**）。
- 引用 `.codex_tmp/` 下任何值之前。
- `docs/log.md` 有一条近期条目、细节被隐去时。

## Examples

**错误路径 —— 把快照当现值。**

```text
Agent: 读 .codex_tmp/.../docs/operations.md
       通篇是一个具体的订阅供应商名，读起来很权威
       据此认定这是办公室当前使用的供应商
结果: 建议建立在一个已停用的供应商上；
      唯一发现它的是用户本人的纠正。
```

**正确路径 —— 按优先级顺序走。**

```text
1. 读 us_openai_api_proxy/docs/log.md
   -> v0.14（2026-08-25）「更新办公室代理订阅与策略组映射」
   -> 知道变更发生过、知道日期，但细节被隐去
   -> 第 10 行写明脱敏边界

2. 用模块名跨 docs/solutions/ 搜索
   grep -rn "us_openai_api_proxy" docs/solutions/
   -> adobe-genuine-prompts-office-openclash.md:55
      点名了同一时期 v0.14 迁移涉及的那个供应商
      （注意：这是二手信息，且该文档仍在仓库中明写此名）

3. 向用户 / 受控环境（父仓库 .env）确认当前值，
   而不是从快照里「还原」
结果: 判断建立在变更记录 + 交叉引用 + 一次显式确认之上，
      而不是一份过期快照。
```

按模块隐私边界，**本文不复述具体供应商名、私有地址与隧道拓扑**；这些值只能从受控环境（模块 `.env`，位于父仓库 `D:\Work\赛狐\Cursor`，worktree 内没有）解析。

## Related

- [adobe-genuine-prompts-office-openclash.md](../best-practices/adobe-genuine-prompts-office-openclash.md) — 点名了那次 v0.14 订阅迁移的交叉引用；同时也是「solutions 文档会承载模块文档刻意隐去的具体值」这一现象的实例。
- [agent-system-access-documentation-gap.md](agent-system-access-documentation-gap.md) — **同形状的姊妹案例**：Agent 因为权威区分没写在它 bootstrap 的位置，用错了数据源（FAC MCP vs REST）；修法同样是「加一个指针」。
- [unverified-external-api-claims-in-docs.md](unverified-external-api-claims-in-docs.md) — 同族：文档里被当作事实、后来被证伪的断言，以及错误如何在相互引用的文档间扩散。
- `us_openai_api_proxy/docs/log.md` — 脱敏变更日志及其边界声明（第 10 行）；v0.14 条目。
- `us_openai_api_proxy/AGENT_HANDOFF.md` — 模块状态与「隐私与变更边界」（第 43-47 行）。
- `.agents/skills/us-openai-api-proxy/SKILL.md` — 占位符解析约定与「禁止从旧 markdown 抄地址」（第 32-36 行）。
- `AGENTS.md` 规则 9（提 PR 前凭证扫描）与规则 11（OKF 文档变更后同步根索引）—— 让脱敏约定可执行的两个仓库级护栏。
- 本次调研落档：`docs/research/2026-09-15-shenzhen-office-egress-and-chatgpt-business.md`（该文档 §2 同时记录了脱敏约定与「历史快照提示」）。
